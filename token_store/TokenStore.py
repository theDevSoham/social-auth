# token_store.py
from typing import Optional, Dict, Any
from logger.Logger import LOG
from config.Config import SQLITE_PATH
import aiosqlite
import json
import time
import certifi
from exceptions import TokenStoreError

try:
    import valkey
    _HAS_VALKEY = True
except ImportError:
    _HAS_VALKEY = False


class TokenStore:
    """
    Minimal async token store with TTL. Primary: valkey (Redis). Fallback: SQLite.
    Stores small JSON blobs keyed by jti (JWT ID) for lookups.
    """
    def __init__(self, redis_url: Optional[str] = None):
        self.redis_url = redis_url
        self._kv = None
        self._sqlite_conn = None
        self._sqlite_initialized = False

    async def init(self):
        if self.redis_url and _HAS_VALKEY:
            self._kv = valkey.from_url(
                self.redis_url, 
                db=0, 
                decode_responses=True,
                ssl_ca_certs=certifi.where()
            )
            LOG.info(f"Connected to Valkey at {self.redis_url}")
        else:
            # sqlite fallback
            db_path = SQLITE_PATH
            self._sqlite_conn = await aiosqlite.connect(db_path)
            await self._init_sqlite()
            LOG.info(f"Using sqlite fallback at {db_path}")

    async def _init_sqlite(self):
        if self._sqlite_initialized:
            return
        await self._sqlite_conn.execute("""
            CREATE TABLE IF NOT EXISTS tokens (
                jti TEXT PRIMARY KEY,
                payload TEXT,
                expires_at INTEGER
            )
        """)
        await self._sqlite_conn.commit()
        self._sqlite_initialized = True

    async def set(self, jti: str, payload: Dict[str, Any], ttl_seconds: int):
        payload_json = json.dumps(payload)
        expires_at = int(time.time()) + ttl_seconds
        if self._kv:
            try:
                self._kv.set(jti, payload_json, ex=ttl_seconds)
                return
            except Exception as e:
                LOG.error(f"Valkey set failed: {str(e)}")
                raise TokenStoreError(e)
        else:
            try:
                await self._sqlite_conn.execute(
                    "REPLACE INTO tokens (jti, payload, expires_at) VALUES (?, ?, ?)",
                    (jti, payload_json, expires_at)
                )
                await self._sqlite_conn.commit()
            except Exception as e:
                LOG.error(f"SQLite set failed: {str(e)}")
                raise TokenStoreError(e)

    async def get(self, jti: str) -> Optional[Dict[str, Any]]:
        if self._kv:
            try:
                val = self._kv.get(jti)
                if not val:
                    return None
                return json.loads(val)
            except Exception as e:
                LOG.error(f"Valkey get failed: {str(e)}")
                raise TokenStoreError(e)
        else:
            cur = await self._sqlite_conn.execute(
                "SELECT payload, expires_at FROM tokens WHERE jti = ?",
                (jti,)
            )
            row = await cur.fetchone()
            if not row:
                return None
            payload_json, expires_at = row
            if int(time.time()) > expires_at:
                # expired; delete
                await self._sqlite_conn.execute("DELETE FROM tokens WHERE jti = ?", (jti,))
                await self._sqlite_conn.commit()
                return None
            return json.loads(payload_json)
        
    # ---------------------------------------------------------------------
    # DELETE (single token)
    # ---------------------------------------------------------------------
    async def delete(self, jti: str):
        """
        Delete one token by JTI.
        """
        if self._kv:
            try:
                deleted = self._kv.delete(jti)
                print(f"Deleted Key: {deleted}")
                return
            except Exception as e:
                LOG.error(f"Valkey delete failed: {str(e)}")
                raise TokenStoreError(e)

        try:
            await self._sqlite_conn.execute("DELETE FROM tokens WHERE jti = ?", (jti,))
            await self._sqlite_conn.commit()
        except Exception as e:
            LOG.error(f"SQLite delete failed: {str(e)}")
            raise TokenStoreError(e)

    # ---------------------------------------------------------------------
    # CLEANUP EXPIRED (SQLite only)
    # ---------------------------------------------------------------------
    async def cleanup_expired(self):
        """
        Removes expired tokens from SQLite.
        No-op for Valkey because Redis handles TTL automatically.
        """
        if self._kv:
            return  # Redis already handles TTL expiry

        try:
            now = int(time.time())
            await self._sqlite_conn.execute(
                "DELETE FROM tokens WHERE expires_at <= ?", (now,)
            )
            await self._sqlite_conn.commit()
            LOG.info("SQLite token cleanup complete")
        except Exception as e:
            LOG.error(f"SQLite cleanup failed: {str(e)}")
            raise TokenStoreError(e)

    # ---------------------------------------------------------------------
    # OPTIONAL: CLEANUP BY USER (provider + uid → delete all tokens)
    # ---------------------------------------------------------------------
    async def cleanup_user(self, provider: str, uid: str):
        """
        Removes all tokens belonging to a given user.
        Requires tokens to include provider + uid inside payload.
        """
        if self._kv:
            # Valkey doesn't have scan cursor by default — add only if needed
            return

        try:
            cur = await self._sqlite_conn.execute(
                "SELECT jti, payload FROM tokens"
            )
            rows = await cur.fetchall()

            to_delete = []
            for jti, payload_json in rows:
                try:
                    data = json.loads(payload_json)
                    if data.get("provider") == provider and data.get("uid") == uid:
                        to_delete.append(jti)
                except:
                    pass

            for jti in to_delete:
                await self.delete(jti)

            LOG.info(f"Cleaned up {len(to_delete)} tokens for user {provider}:{uid}")

        except Exception as e:
            raise TokenStoreError(f"Cleanup user failed: {e}")

    async def close(self):
        if self._kv:
            self._kv.close()
        if self._sqlite_conn:
            await self._sqlite_conn.close()
