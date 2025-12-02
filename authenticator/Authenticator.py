from token_store.TokenStore import TokenStore
from config.Config import AUTH_JWT_SECRET, AUTH_JWT_ALGORITHM, AUTH_JWT_EXP_SECONDS
from utils.util import sha256_hex, async_retry
from utils.http_client import get_aiohttp_session
from typing import Dict, Any
from exceptions import ProviderValidationError, DataError
from social_media_adapter_functions import *
from datastore.MongoDataStore import MongoDataStore
from logger.Logger import LOG
import uuid
import jwt
import time
import aiohttp

# ---------- Authenticator ----------

class Authenticator:
    def __init__(self, token_store: TokenStore, mongo_store: MongoDataStore, jwt_secret: str = AUTH_JWT_SECRET, jwt_algo: str = AUTH_JWT_ALGORITHM, jwt_exp_seconds: int = AUTH_JWT_EXP_SECONDS):
        self.token_store = token_store
        self.mongo_store = mongo_store
        self.jwt_secret = jwt_secret
        self.jwt_algo = jwt_algo
        self.jwt_exp_seconds = jwt_exp_seconds
        self._session = get_aiohttp_session()

    async def close(self):
        await self._session.close()

    async def authenticate(self, provider: str, social_token: str) -> Dict[str, Any]:
        """
        Public entrypoint. Returns a dict with 'app_token' (JWT) and 'payload' (claims).
        """
        provider = provider.lower()
        if provider == "facebook":
            info = await async_retry(validate_facebook_token, token=social_token)
        elif provider == "twitter":
            info = await async_retry(validate_twitter_token, token=social_token)
        else:
            raise ProviderValidationError(f"Unsupported provider: {provider}")

        # info should include 'uid' (user id at provider) and optionally 'scopes', 'expires_at'
        uid = info.get("uid")
        if not uid:
            raise ProviderValidationError("Provider response missing uid")
        
         # ---------------- MongoDB user insert/upsert ----------------
        name = info.get("name")
        email = info.get("email")
        extra = {k: v for k, v in info.items() if k not in ("uid", "name", "email")}
        user_doc = await self.mongo_store.upsert_user(provider, uid, name=name, email=email, extra=extra, social_token=social_token)
        LOG.info(f"User upserted/verified in MongoDB: {user_doc.get('_id')}")

        # Create app JWT
        jti = str(uuid.uuid4())
        now = int(time.time())
        exp = now + self.jwt_exp_seconds
        social_token_hash = sha256_hex(social_token)

        claims = {
            "iss": "auth_service",
            "sub": f"{provider}:{uid}",
            "provider": provider,
            "uid": uid,
            "iat": now,
            "exp": exp,
            "jti": jti,
            # include minimal verification evidence
            "st_hash": social_token_hash,
        }

        app_token = jwt.encode(claims, self.jwt_secret, algorithm=self.jwt_algo)

        # store mapping so we can revoke or validate server-side if needed
        store_payload = {
            "provider": provider,
            "uid": uid,
            "st_hash": social_token_hash,
            "issued_at": now,
            "expires_at": exp,
            "meta": {k: v for k, v in info.items() if k not in ("uid",)},
        }

        await self.token_store.set(jti, store_payload, ttl_seconds=self.jwt_exp_seconds)

        return {"app_token": app_token, "claims": claims}
    
    async def verify_app_token(self, token: str):
        """Verify and decode the issued JWT app token."""
        try:
            payload = jwt.decode(
                token,
                self.jwt_secret,
                algorithms=[self.jwt_algo]
            )
            return payload
        except jwt.ExpiredSignatureError:
            LOG.warning("Expired app token")
            return None
        except jwt.InvalidTokenError as e:
            LOG.warning(f"Invalid app token: {e}")
            return None
        
    async def delete_user(self, provider: str, uid: str, jti: str):
        # Delete from Mongo
        deleted = await self.mongo_store.delete_user(provider, uid)
        if not deleted:
            raise DataError("User not found or already deleted")

        # Also delete from token store (optional but recommended)
        try:
            await self.token_store.delete(jti=jti)
        except Exception:
            # token store cleanup failures should NOT block the delete
            pass

        return True