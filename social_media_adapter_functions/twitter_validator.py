from typing import Dict, Any, Optional
from config.Config import TWITTER_OAUTH2_ENABLE
from utils.http_client import get_aiohttp_session
from logger.Logger import LOG
from exceptions import ProviderValidationError
import aiohttp


async def validate_twitter_token(token: str, session: Optional[aiohttp.ClientSession] = None) -> Dict[str, Any]:
    """
    Validate a Twitter OAuth token using available API endpoints.

    Uses v2 'users/me' endpoint for OAuth2 bearer tokens if TWITTER_OAUTH2_ENABLE is set.
    Otherwise falls back to v1.1 'verify_credentials' for OAuth1.0a or other tokens.

    Args:
        token (str): The OAuth access token to validate.
        session (Optional[aiohttp.ClientSession]): Optional aiohttp session to reuse.

    Returns:
        Dict[str, Any]: {'uid': str, 'raw': Dict[str, Any]}

    Raises:
        ProviderValidationError: If validation fails or response is malformed.
    """
    headers = {"Authorization": f"Bearer {token}", "User-Agent": "auth-service/1.0"}
    timeout = aiohttp.ClientTimeout(total=10)
    should_close = False

    if session is None:
        session = get_aiohttp_session()
        should_close = True
        
    print(TWITTER_OAUTH2_ENABLE)

    try:
        # OAuth2 / v2 endpoint
        if TWITTER_OAUTH2_ENABLE:
            url = "https://api.twitter.com/2/users/me"
        else:
            # Fallback v1.1 endpoint
            url = "https://api.twitter.com/1.1/account/verify_credentials.json"

        async with session.get(url, headers=headers, timeout=timeout) as resp:
            text = await resp.text()
            if resp.status != 200:
                LOG.error("Twitter token validation failed: %s %s", resp.status, text)
                raise ProviderValidationError(f"Twitter validation failed, status={resp.status}")

            data = await resp.json()
            # extract user id
            if TWITTER_OAUTH2_ENABLE:
                user_data = data.get("data") if isinstance(data, dict) else None
                if not user_data:
                    raise ProviderValidationError("Malformed Twitter response (missing data)")
                uid = user_data.get("id")
                if not uid:
                    raise ProviderValidationError("Twitter response missing user ID")
                return {"uid": str(uid), "raw": user_data}
            else:
                uid = data.get("id_str") or data.get("id")
                if not uid:
                    raise ProviderValidationError("Twitter response missing user ID")
                return {"uid": str(uid), "raw": data}

    except aiohttp.ClientError as e:
        LOG.error("Twitter HTTP error: %s", e)
        raise ProviderValidationError(f"Twitter HTTP error: {e}")

    finally:
        if should_close:
            await session.close()
