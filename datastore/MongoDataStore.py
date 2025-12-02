from pymongo import ASCENDING
from pymongo.errors import DuplicateKeyError, PyMongoError
from pymongo import AsyncMongoClient
from typing import Optional, Dict, Any
from logger.Logger import LOG
from config.Config import MONGO_URL, DB_NAME, USERS_COLLECTION
from exceptions.DataError import DataError
import certifi


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
        self.client = AsyncMongoClient(self.mongo_url, tls=True, tlsCAFile=certifi.where())
        self.db = self.client[self.db_name]
        self.users = self.db[self.collection_name]

        # Ensure unique index for provider + social_id
        await self.users.create_index([("provider", ASCENDING), ("social_id", ASCENDING)], unique=True)
        LOG.info(f"Connected to MongoDB, DB: {self.db_name}")

    async def get_user(self, provider: str, social_id: str) -> Optional[Dict[str, Any]]:
        return await self.users.find_one({"provider": provider, "social_id": social_id})

    async def upsert_user(
        self,
        provider: str,
        social_id: str,
        social_token: str,
        name: Optional[str] = None,
        email: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Insert user if not exists. 
        If duplicate key found, compare with existing and update only changed fields.
        """
        doc = {
            "provider": provider,
            "social_id": social_id,
            "social_token": social_token,
            "name": name or "",
            "email": email or "",
            "extra": extra or {},
        }

        try:
            result = await self.users.insert_one(doc)
            doc["_id"] = result.inserted_id
            LOG.info(f"Inserted new user {social_id} ({provider})")
            return doc

        except DuplicateKeyError:
            try:
                # Fetch existing user
                existing = await self.get_user(provider, social_id)
                if not existing:
                    raise Exception("Duplicate key but user not found in DB")

                # Determine changed fields
                updates = {}
                for key, value in doc.items():
                    if key == "_id":
                        continue
                    # Compare dicts deeply for 'extra'
                    if key == "extra":
                        if existing.get("extra", {}) != value:
                            updates[key] = value
                    elif existing.get(key) != value:
                        updates[key] = value

                if updates:
                    await self.users.update_one(
                        {"provider": provider, "social_id": social_id},
                        {"$set": updates}
                    )
                    LOG.info(f"Updated user {social_id} ({provider}) fields: {list(updates.keys())}")
                    existing.update(updates)
                else:
                    LOG.info(f"No updates required for user {social_id} ({provider})")

                return existing

            except Exception as e:
                LOG.error(f"Error updating existing user {social_id} ({provider}): {e}")
                raise

        except PyMongoError as e:
            LOG.error(f"Database error in upsert_user for {social_id} ({provider}): {e}")
            raise Exception(f"Database operation failed: {str(e)}")

        except Exception as e:
            LOG.error(f"Unexpected error in upsert_user for {social_id} ({provider}): {e}")
            raise Exception(f"Unexpected error: {str(e)}")
        
    async def delete_user(self, provider: str, social_id: str):
        try:
            result = await self.users.delete_one({
                "provider": provider,
                "social_id": social_id
            })
            return result.deleted_count > 0
        except Exception as e:
            raise DataError(f"Failed to delete user: {e}")
    
    async def close(self):
        if self.client:
            self.client.close()
            LOG.info("Closed MongoDB connection")
