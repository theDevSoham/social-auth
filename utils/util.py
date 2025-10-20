import hashlib
from logger.Logger import LOG
import asyncio

def sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

async def async_retry(func, *args, retries=3, backoff_factor=0.5, **kwargs):
    """Simple retry helper with exponential backoff."""
    attempt = 0
    while True:
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            attempt += 1
            if attempt > retries:
                raise
            sleep = backoff_factor * (2 ** (attempt - 1))
            LOG.warning("Transient error calling %s: %s — retrying in %.2fs (attempt %d)", func.__name__, e, sleep, attempt)
            await asyncio.sleep(sleep)