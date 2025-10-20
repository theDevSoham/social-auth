# utils/http_client.py
import aiohttp
import ssl
import certifi
from typing import Optional


def get_aiohttp_session(timeout_seconds: int = 10, session: Optional[aiohttp.ClientSession] = None) -> aiohttp.ClientSession:
    """
    Returns a configured aiohttp.ClientSession with SSL verification using certifi.
    
    Args:
        timeout_seconds (int): Request timeout in seconds.
        session (Optional[aiohttp.ClientSession]): If provided, returns it directly.
    
    Returns:
        aiohttp.ClientSession: Async HTTP session ready to use.
    """
    if session:
        return session  # reuse existing session

    ssl_context = ssl.create_default_context(cafile=certifi.where())
    timeout = aiohttp.ClientTimeout(total=timeout_seconds)

    return aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_context), timeout=timeout)
