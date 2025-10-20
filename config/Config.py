# Config.py
"""
Configuration module for Social Auth Service.

- Loads environment variables using python-dotenv (if available)
- Provides typed constants for all configuration fields
- Designed for clean imports: `from config import *`
"""

import os
import logging
from dotenv import load_dotenv

# Load .env file if present
load_dotenv()

# ---------- Core App Config ----------
AUTH_JWT_SECRET: str = os.getenv("AUTH_JWT_SECRET", "please-change-this-secret")
AUTH_JWT_ALGORITHM: str = os.getenv("AUTH_JWT_ALGORITHM", "HS256")

try:
    AUTH_JWT_EXP_SECONDS: int = int(os.getenv("AUTH_JWT_EXP_SECONDS", "3600"))
except ValueError:
    AUTH_JWT_EXP_SECONDS = 3600

REDIS_URL: str | None = os.getenv("REDIS_URL")

# ---------- Provider Credentials ----------
FACEBOOK_APP_ID: str | None = os.getenv("FACEBOOK_APP_ID")
FACEBOOK_APP_SECRET: str | None = os.getenv("FACEBOOK_APP_SECRET")
TWITTER_OAUTH2_ENABLE: bool | None = os.getenv("TWITTER_OAUTH2_ENABLE") == "Yes"

# ---------- Optional Fallback Config ----------
SQLITE_PATH: str = os.getenv("SQLITE_PATH", ":memory:")

# ---------- Logging ----------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(message)s")

# --------- DB config ----------
MONGO_URL: str = os.getenv("MONGO_URL", "mongodb://localhost:27017")
DB_NAME: str = os.getenv("MONGO_DB_NAME", "")
USERS_COLLECTION: str = os.getenv("MONGO_DB_NAME", "")

# ---------- Helper for Debug ----------
def debug_print_config():
    """Print current config values for debugging (masking secrets)."""
    def mask(val: str | None):
        if not val:
            return None
        if len(val) <= 6:
            return "***"
        return f"{val[:3]}...{val[-3:]}"
    print("Auth Service Configuration:")
    print(f"  AUTH_JWT_ALGORITHM = {AUTH_JWT_ALGORITHM}")
    print(f"  AUTH_JWT_EXP_SECONDS = {AUTH_JWT_EXP_SECONDS}")
    print(f"  REDIS_URL = {mask(REDIS_URL)}")
    print(f"  FACEBOOK_APP_ID = {mask(FACEBOOK_APP_ID)}")
    print(f"  FACEBOOK_APP_SECRET = {mask(FACEBOOK_APP_SECRET)}")
    print(f"  MONGO_URL = {mask(MONGO_URL)}")
    print(f"  DB_NAME = {mask(DB_NAME)}")
    print(f"  USERS_COLLECTION = {mask(USERS_COLLECTION)}")
    print(f"  TWITTER_OAUTH2_ENABLE = {TWITTER_OAUTH2_ENABLE}")
    print(f"  SQLITE_PATH = {SQLITE_PATH}")
