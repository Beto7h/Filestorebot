from motor.motor_asyncio import AsyncIOMotorClient
from config import Config

client = AsyncIOMotorClient(Config.MONGO_URI)
db = client["filestore_db"]
settings = db["settings"]
links = db["links"]

async def get_config():
    doc = await settings.find_one({"id": "bot_config"})
    if not doc:
        # Valores por defecto
        return {"log_channel": None, "delete_time": 600}
    return doc

async def update_config(data):
    await settings.update_one({"id": "bot_config"}, {"$set": data}, upsert=True)

async def save_link(batch_id, start_id, end_id):
    await links.insert_one({
        "batch_id": batch_id,
        "start_id": start_id,
        "end_id": end_id
    })
