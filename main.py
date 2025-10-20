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
import asyncio
import json

from config.Config import REDIS_URL
from exceptions import *
from logger.Logger import LOG
from token_store.TokenStore import TokenStore
from authenticator.Authenticator import Authenticator

# ---------- Example CLI / uv entrypoint ----------

async def main():
    """Main for local testing and as an entrypoint for uv runtimes.

    Example usage (dev):
      - set environment variables
      - run `python main.py`
      - the script will attempt to validate a token interactively

    In production, import Authenticator from this module and use in FastAPI endpoints.
    """
    LOG.info("Starting auth service (standalone). Initializing token store...")
    store = TokenStore(redis_url=REDIS_URL)
    await store.init()
    auth = Authenticator(token_store=store)

    try:
        # quick interactive test loop
        print("Simple Auth CLI — type 'quit' to exit")
        while True:
            provider = input("provider (facebook|twitter)> ").strip()
            if provider in ("", "quit", "exit"):
                break
            token = input("social token> ").strip()
            if not token:
                print("empty token")
                continue
            try:
                out = await auth.authenticate(provider, token)
                print("OK — app_token (first 120 chars):", out["app_token"][:120])
                print("claims:", json.dumps(out["claims"], indent=2))
            except ProviderValidationError as pve:
                print("Validation failed:", pve)
            except Exception as e:
                LOG.exception("Unexpected error during authentication: %s", e)
                print("Error: ", e)
    finally:
        await auth.close()
        await store.close()
        LOG.info("Shutting down")


if __name__ == "__main__":
    asyncio.run(main())
