from typing import Dict, Any, Optional
from config.Config import FACEBOOK_APP_ID, FACEBOOK_APP_SECRET
from logger.Logger import LOG
from utils.http_client import get_aiohttp_session
from exceptions import ProviderValidationError
import aiohttp


async def validate_facebook_token(
    token: str, session: Optional[aiohttp.ClientSession] = None
) -> Dict[str, Any]:
    """
    Validate a Facebook access token and fetch user info.

    Returns:
        {
            "uid": str,
            "name": str,
            "email": str,
            "expires_at": Optional[int],
            "scopes": Optional[list],
            "raw": dict,
        }
    """
    if not FACEBOOK_APP_ID or not FACEBOOK_APP_SECRET:
        LOG.warning("FACEBOOK_APP_ID or SECRET not set; trying best-effort validation")

    # Build app access token if available
    app_access_token = (
        f"{FACEBOOK_APP_ID}|{FACEBOOK_APP_SECRET}"
        if FACEBOOK_APP_ID and FACEBOOK_APP_SECRET
        else None
    )

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
        # 1️⃣ Validate token
        async with session.get(debug_url, params=params, timeout=timeout) as resp:
            text = await resp.text()
            if resp.status != 200:
                LOG.error(f"Facebook token debug failed: {resp.status}, {text}")
                raise ProviderValidationError("Facebook validation failed")

            data = await resp.json()

        info = data.get("data")
        if not info:
            raise ProviderValidationError("Malformed Facebook response")

        if not info.get("is_valid"):
            raise ProviderValidationError("Facebook token invalid")

        if FACEBOOK_APP_ID and info.get("app_id") != FACEBOOK_APP_ID:
            raise ProviderValidationError("Facebook token app_id mismatch")

        uid = info.get("user_id") or info.get("uid")

        # 2️⃣ Fetch user info
        user_data = await get_user_info(token, session=session)

        return {
            "uid": str(uid),
            "name": user_data.get("name", ""),
            "email": user_data.get("email", ""),
            "expires_at": info.get("expires_at"),
            "scopes": info.get("scopes"),
            "raw": {"validation": info, "user": user_data},
        }

    except aiohttp.ClientError as e:
        LOG.error(f"Facebook HTTP error: {str(e)}")
        raise ProviderValidationError(f"Facebook HTTP error: {e}")

    finally:
        if should_close:
            await session.close()


async def get_user_info(
    token: str, session: Optional[aiohttp.ClientSession] = None
) -> Dict[str, Any]:
    """
    Fetch the user's profile info (id, name, email) from Facebook Graph API.
    """
    user_info_url = "https://graph.facebook.com/me"
    params = {"fields": "id,name,email", "access_token": token}

    timeout = aiohttp.ClientTimeout(total=10)
    should_close = False

    if session is None:
        session = get_aiohttp_session()
        should_close = True

    try:
        async with session.get(user_info_url, params=params, timeout=timeout) as resp:
            text = await resp.text()
            if resp.status != 200:
                LOG.error(f"Facebook user info fetch failed: {resp.status}, {text}")
                raise ProviderValidationError("Failed to fetch Facebook user info")

            data = await resp.json()
            return data

    except aiohttp.ClientError as e:
        LOG.error(f"Facebook HTTP error: {str(e)}")
        raise ProviderValidationError(f"Facebook HTTP error: {e}")

    finally:
        if should_close:
            await session.close()
