import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    API_ID = int(os.environ.get("API_ID", 12345))
    API_HASH = os.environ.get("API_HASH", "tu_hash")
    BOT_TOKEN = os.environ.get("BOT_TOKEN", "tu_token")
    ADMIN_ID = int(os.environ.get("ADMIN_ID", 12345678))
    # URL de MongoDB Atlas (Koyeb requiere DB externa o Add-on)
    MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://...")
