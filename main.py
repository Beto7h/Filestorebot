import asyncio, uuid
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import Config
import database as db

bot = Client("filestore", api_id=Config.API_ID, api_hash=Config.API_HASH, bot_token=Config.BOT_TOKEN)

# --- PROCESO DE REENVÍO POR BLOQUES ---
@bot.on_message(filters.command("batch") & filters.user(Config.ADMIN_ID))
async def batch_process(client, message):
    conf = await db.get_config()
    if not conf.get("log_channel"):
        return await message.reply("❌ Primero configura el canal con /set_almacen en el canal.")

    msg1 = await client.ask(message.chat.id, "Envíame el PRIMER mensaje del canal origen.")
    msg2 = await client.ask(message.chat.id, "Envíame el ÚLTIMO mensaje del canal origen.")
    
    start_id, end_id = msg1.forward_from_message_id, msg2.forward_from_message_id
    canal_origen = msg1.forward_from_chat.id
    
    await message.reply(f"Iniciando reenvío de {end_id - start_id} mensajes...")
    
    # Bucle de reenvío al Canal Almacén
    for i in range(start_id, end_id + 1):
        try:
            await client.copy_message(conf["log_channel"], canal_origen, i)
            if (i - start_id) % 100 == 0 and i != start_id:
                await asyncio.sleep(15) # Pausa de seguridad
        except: continue

    # Generar Link Permanente
    batch_id = str(uuid.uuid4())[:8]
    await db.save_link(batch_id, start_id, end_id)
    await message.reply(f"✅ ¡Listo! Enlace permanente:\n`https://t.me/{bot.me.username}?start={batch_id}`")

# --- MENÚ ADMIN ---
@bot.on_message(filters.command("admin") & filters.user(Config.ADMIN_ID))
async def admin_menu(client, message):
    conf = await db.get_config()
    botones = InlineKeyboardMarkup([
        [InlineKeyboardButton("⏱ Tiempo de Borrado", callback_data="set_time")],
        [InlineKeyboardButton("📊 Estadísticas", callback_data="stats")]
    ])
    await message.reply(f"⚙️ **Config actual:**\nCanal: `{conf['log_channel']}`\nBorrado: `{conf['delete_time']}s`", reply_markup=botones)

# --- MANEJADOR DE LINKS (START) ---
@bot.on_message(filters.command("start") & filters.private)
async def handle_start(client, message):
    if len(message.command) > 1:
        batch_data = await db.links.find_one({"batch_id": message.command[1]})
        if batch_data:
            conf = await db.get_config()
            sent_msgs = []
            # Enviamos archivos al usuario
            for m_id in range(batch_data["start_id"], batch_data["end_id"] + 1):
                m = await client.copy_message(message.chat.id, conf["log_channel"], m_id)
                sent_msgs.append(m.id)
            
            # Programar autodestrucción
            await asyncio.sleep(conf["delete_time"])
            await client.delete_messages(message.chat.id, sent_msgs)

bot.run()
