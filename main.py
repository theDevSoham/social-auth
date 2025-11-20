"""
Simple Social Authentication Service (main.py)

- Entry point: async `main()` (suitable for uv runtime / astral uv)
- Provides `Authenticator` class which can validate social tokens for providers
  (facebook, twitter) and issue an application JWT after successful validation.

Design priorities:
- simplicity: single-file reference implementation with clear extension points
- scalability: async I/O, pluggable HTTP client, Redis-backed token store with TTL
- room for error: robust error handling, retries with exponential backoff, timeouts
- caveats: provider validators are small adapters; network errors and changing
  provider APIs are handled gracefully and easy to update

Requirements (install in your environment):
  pip install aiohttp aioredis PyJWT cryptography

Environment variables (recommended):
  - AUTH_JWT_SECRET       : secret used to sign JWTs (required)
  - AUTH_JWT_ALGORITHM    : e.g. HS256 (default HS256)
  - AUTH_JWT_EXP_SECONDS  : integer seconds for app token expiration (default 3600)
  - REDIS_URL             : e.g. redis://localhost:6379/0 (if not present uses sqlite fallback)
  - FACEBOOK_APP_ID       : Facebook App ID (optional but recommended)
  - FACEBOOK_APP_SECRET   : Facebook App Secret (optional but recommended)
  - TWITTER_OAUTH2_ENABLE  : Twitter Bearer token (optional but recommended)

How it is organized:
  - Authenticator: public API. use `await authenticate(provider, token)`
  - Provider adapters: _validate_facebook, _validate_twitter (pluggable)
  - TokenStore: Redis-backed TTL store with sqlite fallback
  - Utilities: hashing, retries, structured errors

This file purposely keeps implementation clear and easy to adapt for FastAPI
integration. For FastAPI, import `Authenticator` and call `authenticate()` inside
an endpoint.
"""
from fastapi import FastAPI, HTTPException, Header, Depends
from pydantic import BaseModel
from contextlib import asynccontextmanager
from fastapi import Request
from fastapi.responses import JSONResponse

import asyncio
from utils import util

from config.Config import REDIS_URL, debug_print_config
from exceptions import *
from logger.Logger import LOG
from token_store.TokenStore import TokenStore
from datastore.MongoDataStore import MongoDataStore
from authenticator.Authenticator import Authenticator

# ---------- Request / Response Schemas ----------
class AuthRequest(BaseModel):
    provider: str  # 'facebook' or 'twitter'
    token: str     # social access token

class AuthResponse(BaseModel):
    app_token: str
    claims: dict
    
async def init_services():
    global initialized
    async with startup_lock:
        if not initialized:
            LOG.info("Initializing token store and authenticator...")
            await token_store.init()
            await mongo_store.init()
            initialized = True
    
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize resources
    await init_services()
    debug_print_config()
    yield
    # Shutdown: cleanup
    LOG.info("Shutting down services...")
    await authenticator.close()
    await token_store.close()
    await mongo_store.close()
    
# ---------- FastAPI app ----------
app = FastAPI(title="Simple Social Auth Service", lifespan=lifespan)

# ---------- Handle exceptions ----------
@app.exception_handler(ProviderValidationError)
async def provider_validation_exception_handler(request: Request, exc: ProviderValidationError):
    return JSONResponse(
        status_code=401,
        content={"detail": f"Social provider validation failed: {str(exc)}"},
    )

@app.exception_handler(TokenStoreError)
async def token_store_exception_handler(request: Request, exc: TokenStoreError):
    return JSONResponse(
        status_code=500,
        content={"detail": f"Token store error: {str(exc)}"},
    )

@app.exception_handler(DataError)
async def data_exception_handler(request: Request, exc: DataError):
    return JSONResponse(
        status_code=400,
        content={"detail": f"Data error: {str(exc)}"},
    )

# Single global instances (async init)
token_store: TokenStore = TokenStore(redis_url=REDIS_URL)
mongo_store: MongoDataStore = MongoDataStore()
authenticator: Authenticator = Authenticator(token_store=token_store, mongo_store=mongo_store)
startup_lock = asyncio.Lock()
initialized = False

@app.get("/health")
def health_check():
    return {"status": "success", "message": "service running"}

# ---------- Auth endpoint ----------
@app.post("/authenticate", response_model=AuthResponse)
async def authenticate(req: AuthRequest):
    """Authenticate a social token and issue app JWT."""
    await init_services()  # ensure initialized
    provider = req.provider.lower()
    token = req.token.strip()
    if provider not in ("facebook", "twitter"):
        raise HTTPException(status_code=400, detail="Invalid provider")

    if not token:
        raise HTTPException(status_code=400, detail="Token is required")

    try:
        out = await authenticator.authenticate(provider, token)
        return AuthResponse(app_token=out["app_token"], claims=out["claims"])
    except ProviderValidationError as pve:
        LOG.warning(f"Provider validation failed: {pve}")
        raise HTTPException(status_code=401, detail=f"Validation failed: {pve}")
    except Exception as e:
        LOG.exception(f"Unexpected error during authentication: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

# ---------- Get user endpoint ----------
@app.get("/get_user", response_model=AuthResponse)
async def get_user(authorization: str = Header(None)):
    """
    Get user details associated with a valid app token.
    Requires Authorization header: Bearer <app_token>
    """
    await init_services()

    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid Authorization header format")

    app_token = authorization.split(" ")[1].strip()

    if not app_token:
        raise HTTPException(status_code=401, detail="App token missing")

    try:
        # Validate token (decode + verify)
        claims = await authenticator.verify_app_token(app_token)
        claims_provider = claims["provider"]
        claims_uid = claims["uid"]
        if not claims:
            raise HTTPException(status_code=401, detail="Invalid or expired token")

        # Optionally, fetch additional user data from Mongo store
        user_data = await mongo_store.get_user(provider=claims_provider, social_id=claims_uid)

        if not user_data:
            raise HTTPException(status_code=404, detail="User not found")

        return AuthResponse(app_token=app_token, claims=util.normalize_mongo_doc(user_data))

    except TokenStoreError as tse:
        LOG.error(f"Token store error: {tse}")
        raise HTTPException(status_code=500, detail="Token store error")
    except Exception as e:
        LOG.exception(f"Error fetching user: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")