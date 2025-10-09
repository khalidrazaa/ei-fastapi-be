from typing import Dict, List, Optional, Any, Union
from motor.motor_asyncio import AsyncIOMotorCollection
from pymongo import UpdateOne, IndexModel
from bson import ObjectId
from app.db.mongodb import get_mongo_db


class MongoWrapper:
    def __init__(self, collection:AsyncIOMotorCollection):
        """Initialize wrapper with a specific collection name."""
        self.collection = collection

    # -------------------------
    # Utility
    # -------------------------
    @staticmethod
    def to_object_id(id_str: Union[str, ObjectId]):
        try:
            return ObjectId(id_str)
        except Exception:
            return id_str

    # -------------------------
    # CRUD Operations
    # -------------------------
    async def find(
        self,
        query: Dict = {},
        projection: Optional[Dict] = None,
        sort: Optional[List] = None,
        limit: int = 10,
        skip: int = 0,
        return_count: bool = False,
    ):
        cursor = self.collection.find(query, projection)

        if sort:
            cursor = cursor.sort(sort)
        if limit:
            cursor = cursor.limit(limit).skip(skip)

        results = await cursor.to_list(length=limit if not return_count else None)

        if return_count:
            total = await self.collection.count_documents(query)
            return {"hits": results, "total": total}

        return results

    async def find_one(self, query: Dict, projection: Optional[Dict] = None):
        return await self.collection.find_one(query, projection)

    async def create(self, data: Dict):
        result = await self.collection.insert_one(data)
        return str(result.inserted_id)

    async def create_many(self, data_list: List[Dict]):
        result = await self.collection.insert_many(data_list)
        return [str(r) for r in result.inserted_ids]

    async def update_one(self, query: Dict, data: Dict):
        result = await self.collection.update_one(query, {"$set": data})
        return result.modified_count

    async def update_many(self, query: Dict, data: Dict):
        result = await self.collection.update_many(query, {"$set": data})
        return result.modified_count

    async def delete_one(self, query: Dict):
        result = await self.collection.delete_one(query)
        return result.deleted_count

    async def delete_many(self, query: Dict):
        result = await self.collection.delete_many(query)
        return result.deleted_count

    async def aggregate(self, pipeline: List[Dict]):
        cursor = self.collection.aggregate(pipeline)
        return await cursor.to_list(length=None)

    # -------------------------
    # Index Management
    # -------------------------
    async def create_index(self, keys: Union[str, List[tuple]], **kwargs):
        """Create single or compound index."""
        return await self.collection.create_index(keys, **kwargs)

    async def create_indexes(self, indexes: List[IndexModel]):
        """Create multiple indexes at once."""
        return await self.collection.create_indexes(indexes)

    async def bulk_write(self, operations: list):
        """
        operations: list of pymongo UpdateOne / UpdateMany / DeleteOne operations
        """
        if not operations:
            return None
        result = await self.collection.bulk_write(operations, ordered=False)
        return result