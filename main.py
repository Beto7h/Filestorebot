import asyncio, uuid
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import Config
import database as db
from pyromod import listen 

bot = Client(
    "filestore", 
    api_id=Config.API_ID, 
    api_hash=Config.API_HASH, 
    bot_token=Config.BOT_TOKEN
)

# --- CONFIGURACIÓN AUTOMÁTICA DEL CANAL ---
@bot.on_chat_member_updated()
async def auto_configure_channel(client, update):
    if update.new_chat_member and update.new_chat_member.status == "administrator":
        channel_id = update.chat.id
        await db.update_config({"log_channel": channel_id})
        await client.send_message(
            channel_id, 
            "✅ **¡BODEGA VINCULADA!**\n\nLos archivos guardados aquí son PERMANENTES."
        )

# --- PANEL DE CONTROL ADMIN ---
@bot.on_message(filters.command("admin") & filters.user(Config.ADMIN_ID))
async def admin_menu(client, message):
    conf = await db.get_config()
    t_min = conf.get('delete_time', 600) // 60
    texto = (
        "🛠 **PANEL DE CONTROL**\n\n"
        f"📡 **Almacén:** `{conf.get('log_channel', 'No detectado')}`\n"
        f"⏳ **Autoborrado:** `{t_min} min`"
    )
    botones = InlineKeyboardMarkup([
        [InlineKeyboardButton("⏱ Cambiar Tiempo", callback_data="set_time")],
        [InlineKeyboardButton("📊 Estadísticas", callback_data="stats")]
    ])
    await message.reply(texto, reply_markup=botones)

# --- CALLBACKS ADMIN ---
@bot.on_callback_query(filters.regex(r"^(set_time|time_|back_admin)"))
async def admin_callbacks(client, query):
    if query.data == "set_time":
        botones = InlineKeyboardMarkup([
            [InlineKeyboardButton("5 min", callback_data="time_300"), InlineKeyboardButton("15 min", callback_data="time_900")],
            [InlineKeyboardButton("1 hora", callback_data="time_3600"), InlineKeyboardButton("Desactivar", callback_data="time_0")],
            [InlineKeyboardButton("⬅️ Volver", callback_data="back_admin")]
        ])
        await query.edit_message_text("Tiempo de vida en el chat del usuario:", reply_markup=botones)
    elif query.data.startswith("time_"):
        segundos = int(query.data.split("_")[1])
        await db.update_config({"delete_time": segundos})
        await query.answer("Configuración guardada ✅")
        await admin_menu(client, query.message)

# --- PROCESO BATCH (CON CORRECCIÓN DE IDS) ---
@bot.on_message(filters.command("batch") & filters.user(Config.ADMIN_ID))
async def batch_process(client, message):
    conf = await db.get_config()
    if not conf.get("log_channel"):
        return await message.reply("❌ Primero hazme admin en un canal privado.")

    m1 = await client.ask(message.chat.id, "Envíame el PRIMER mensaje del origen.")
    m2 = await client.ask(message.chat.id, "Envíame el ÚLTIMO mensaje del origen.")
    
    s_id = m1.forward_from_message_id if m1.forward_from_message_id else int(m1.text)
    e_id = m2.forward_from_message_id if m2.forward_from_message_id else int(m2.text)
    c_ori = m1.forward_from_chat.id if m1.forward_from_chat else (await client.ask(message.chat.id, "ID del Canal Origen:")).text

    pje = await message.reply("📦 Copiando a bodega y generando IDs nuevos...")
    
    new_start_id = None
    new_end_id = None

    for i in range(s_id, e_id + 1):
        try:
            # Copiamos al almacén y guardamos el nuevo ID que Telegram le asigna en TU canal
            copied_msg = await client.copy_message(conf["log_channel"], c_ori, i)
            
            if new_start_id is None: new_start_id = copied_msg.id
            new_end_id = copied_msg.id # Al final del bucle, este será el último ID

            if (i - s_id) % 100 == 0 and i != s_id:
                await asyncio.sleep(15)
        except: continue

    b_id = str(uuid.uuid4())[:8]
    # GUARDAMOS LOS IDS DEL ALMACÉN, NO DEL ORIGEN
    await db.save_link(b_id, new_start_id, new_end_id)
    await pje.edit(f"✅ **Lote Listo**\nLink: `https://t.me/{bot.me.username}?start={b_id}`")

# --- MANEJADOR DE START ---
@bot.on_message(filters.command("start") & filters.private)
async def handle_start(client, message):
    if len(message.command) > 1:
        data = await db.links.find_one({"batch_id": message.command[1]})
        if data:
            conf = await db.get_config()
            temp_msgs = []
            status = await message.reply("📥 Entregando archivos...")

            for m_id in range(data["start_id"], data["end_id"] + 1):
                try:
                    m = await client.copy_message(message.chat.id, conf["log_channel"], m_id)
                    temp_msgs.append(m.id)
                    await asyncio.sleep(0.5) # Evitar flood
                except: continue
            
            if conf.get("delete_time", 0) > 0:
                wait_min = conf['delete_time'] // 60
                await status.edit(f"⏳ Borrado automático en: **{wait_min} min**.")
                await asyncio.sleep(conf["delete_time"])
                
                await client.delete_messages(message.chat.id, temp_msgs)
                await status.delete()
                await message.reply("🗑 Mensajes temporales eliminados.")
            else:
                await status.delete()
        else:
            await message.reply("❌ Enlace no válido.")

bot.run()
