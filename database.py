from motor.motor_asyncio import AsyncIOMotorClient
from config import Config

# Conexión a MongoDB
client = AsyncIOMotorClient(Config.MONGO_URI)
db = client["filestore_db"]
settings = db["settings"]
links = db["links"]

async def get_config():
    """Obtiene la configuración global (ID del canal y tiempo de borrado)."""
    doc = await settings.find_one({"id": "bot_config"})
    if not doc:
        # Valores por defecto: 600 segundos = 10 minutos
        return {"log_channel": None, "delete_time": 600}
    return doc

async def update_config(data):
    """Actualiza o crea la configuración del bot."""
    await settings.update_one({"id": "bot_config"}, {"$set": data}, upsert=True)

async def save_link(batch_id, start_id, end_id):
    """Guarda un nuevo lote de mensajes vinculado a un ID único (UUID)."""
    await links.insert_one({
        "batch_id": batch_id,
        "start_id": start_id,
        "end_id": end_id
    })

async def get_link(batch_id):
    """Busca los datos de un lote específico usando su batch_id."""
    return await links.find_one({"batch_id": batch_id})
