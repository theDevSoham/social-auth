from typing import Dict, Any, Optional
from config.Config import FACEBOOK_APP_ID, FACEBOOK_APP_SECRET
from logger.Logger import LOG
from utils.http_client import get_aiohttp_session
from exceptions import ProviderValidationError
import aiohttp


async def validate_facebook_token(token: str, session: Optional[aiohttp.ClientSession] = None) -> Dict[str, Any]:
    """
    Validate an OAuth access token from Facebook using the debug_token endpoint.

    Args:
        token (str): The OAuth access token to validate.
        session (Optional[aiohttp.ClientSession]): Optional aiohttp session to reuse.
    
    Returns:
        Dict[str, Any]: User and token information from Facebook.
    
    Raises:
        ProviderValidationError: If validation fails or response is malformed.
    """
    if not FACEBOOK_APP_ID or not FACEBOOK_APP_SECRET:
        LOG.warning("FACEBOOK_APP_ID or SECRET not set; trying best-effort validation")

    # Build app access token if we have secret
    app_access_token = None
    if FACEBOOK_APP_ID and FACEBOOK_APP_SECRET:
        app_access_token = f"{FACEBOOK_APP_ID}|{FACEBOOK_APP_SECRET}"

    debug_url = "https://graph.facebook.com/debug_token"
    params = {"input_token": token}
    if app_access_token:
        params["access_token"] = app_access_token

    timeout = aiohttp.ClientTimeout(total=10)
    should_close = False

    if session is None:
        session = get_aiohttp_session()
        should_close = True

    try:
        async with session.get(debug_url, params=params, timeout=timeout) as resp:
            text = await resp.text()
            if resp.status != 200:
                LOG.error("Facebook token debug failed: %s %s", resp.status, text)
                raise ProviderValidationError("Facebook validation failed")
            data = await resp.json()
    finally:
        if should_close:
            await session.close()

    # Handle structure defensively
    info = data.get("data") if isinstance(data, dict) else None
    if not info:
        raise ProviderValidationError("Malformed Facebook response")
    if not info.get("is_valid"):
        raise ProviderValidationError("Facebook token invalid")

    uid = info.get("user_id") or info.get("uid")
    return {
        "uid": str(uid),
        "scopes": info.get("scopes"),
        "expires_at": info.get("expires_at"),
        "raw": info,
    }
