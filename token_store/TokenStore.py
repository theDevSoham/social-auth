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
            LOG.info("Connected to Valkey at %s", self.redis_url)
        else:
            # sqlite fallback
            db_path = SQLITE_PATH
            self._sqlite_conn = await aiosqlite.connect(db_path)
            await self._init_sqlite()
            LOG.info("Using sqlite fallback at %s", db_path)

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
                LOG.error("Valkey set failed: %s", e)
                raise TokenStoreError(e)
        else:
            try:
                await self._sqlite_conn.execute(
                    "REPLACE INTO tokens (jti, payload, expires_at) VALUES (?, ?, ?)",
                    (jti, payload_json, expires_at)
                )
                await self._sqlite_conn.commit()
            except Exception as e:
                LOG.error("SQLite set failed: %s", e)
                raise TokenStoreError(e)

    async def get(self, jti: str) -> Optional[Dict[str, Any]]:
        if self._kv:
            try:
                val = self._kv.get(jti)
                if not val:
                    return None
                return json.loads(val)
            except Exception as e:
                LOG.error("Valkey get failed: %s", e)
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

    async def close(self):
        if self._kv:
            self._kv.close()
        if self._sqlite_conn:
            await self._sqlite_conn.close()
