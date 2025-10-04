from typing import Any, Dict, List, Optional
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId

client = AsyncIOMotorClient("mongodb://localhost:27017")
db = client["mydb"]

def to_object_id(id_str: str):
    try:
        return ObjectId(id_str)
    except:
        return id_str

async def find(
    collection: str,
    query: Dict = {},
    projection: Optional[Dict] = None,
    sort: Optional[List] = None,
    limit: int = 10,
    skip: int = 0,
    return_count: bool = False,
):
    coll = db[collection]
    cursor = coll.find(query, projection)
    
    if sort:
        cursor = cursor.sort(sort)
    if limit:
        cursor = cursor.limit(limit).skip(skip)

    results = await cursor.to_list(length=limit if not return_count else None)
    
    if return_count:
        total = await coll.count_documents(query)
        return {"hits": results, "total": total}
    
    return results

async def find_one(collection: str, query: Dict = {}, projection: Optional[Dict] = None):
    return await db[collection].find_one(query, projection)

async def create(collection: str, data: Dict):
    result = await db[collection].insert_one(data)
    return str(result.inserted_id)

async def update_one(collection: str, query: Dict, data: Dict):
    result = await db[collection].update_one(query, {"$set": data})
    return result.modified_count

async def delete_one(collection: str, query: Dict):
    result = await db[collection].delete_one(query)
    return result.deleted_count