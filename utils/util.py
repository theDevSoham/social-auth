import hashlib
from bson import ObjectId
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
            LOG.warning(f"Transient error calling {func.__name__}: {str(e)} — retrying in {sleep}s (attempt {attempt})")
            await asyncio.sleep(sleep)

def normalize_mongo_doc(doc):
    """Convert ObjectIds and other non-JSON types to string."""
    if isinstance(doc, list):
        return [normalize_mongo_doc(x) for x in doc]
    if isinstance(doc, dict):
        return {k: normalize_mongo_doc(v) for k, v in doc.items()}
    if isinstance(doc, ObjectId):
        return str(doc)
    return doc