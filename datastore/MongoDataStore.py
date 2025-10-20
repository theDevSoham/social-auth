from pymongo import ASCENDING
from pymongo.errors import DuplicateKeyError
from pymongo import AsyncMongoClient
from typing import Optional, Dict, Any
from logger.Logger import LOG
from config.Config import MONGO_URL, DB_NAME, USERS_COLLECTION
from exceptions.DataError import DataError


class MongoDataStore:
    """
    MongoDB wrapper for user data operations using pymongo asyncio API.
    """
    def __init__(self, mongo_url: str = MONGO_URL, db_name: str = DB_NAME, collection_name: str = USERS_COLLECTION):
        self.mongo_url = mongo_url
        self.db_name = db_name
        self.collection_name = collection_name
        self.client: Optional[AsyncMongoClient] = None
        self.db = None
        self.users = None

    async def init(self):
        self.client = AsyncMongoClient(self.mongo_url)
        self.db = self.client[self.db_name]
        self.users = self.db[self.collection_name]

        # Ensure unique index for provider + social_id
        await self.users.create_index([("provider", ASCENDING), ("social_id", ASCENDING)], unique=True)
        LOG.info("Connected to MongoDB at %s, DB: %s", self.mongo_url, self.db_name)

    async def get_user(self, provider: str, social_id: str) -> Optional[Dict[str, Any]]:
        return await self.users.find_one({"provider": provider, "social_id": social_id})

    async def upsert_user(
        self,
        provider: str,
        social_id: str,
        name: Optional[str] = None,
        email: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Insert user if not exists, otherwise return existing user.
        """
        doc = {
            "provider": provider,
            "social_id": social_id,
            "name": name or "",
            "email": email or "",
            "extra": extra or {},
        }

        try:
            result = await self.users.insert_one(doc)
            doc["_id"] = result.inserted_id
            LOG.info("Inserted new user %s (%s)", social_id, provider)
            return doc
        except DuplicateKeyError:
            # Already exists, fetch existing
            existing = await self.get_user(provider, social_id)
            LOG.info("User already exists %s (%s)", social_id, provider)
            raise DataError("User already exists with name %s", existing.get("name") if existing else "unknown")

    async def close(self):
        if self.client:
            self.client.close()
            LOG.info("Closed MongoDB connection")
