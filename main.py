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

# --- CONFIGURACIÓN AUTOMÁTICA DEL CANAL (ALMACÉN PERMANENTE) ---
@bot.on_chat_member_updated()
async def auto_configure_channel(client, update):
    if update.new_chat_member and update.new_chat_member.status == "administrator":
        channel_id = update.chat.id
        await db.update_config({"log_channel": channel_id})
        await client.send_message(
            channel_id, 
            "✅ **¡BODEGA VINCULADA!**\n\nLos archivos guardados aquí son PERMANENTES. "
            "El bot solo borrará las copias que envíe por privado a los usuarios."
        )

# --- PANEL DE CONTROL ADMIN ---
@bot.on_message(filters.command("admin") & filters.user(Config.ADMIN_ID))
async def admin_menu(client, message):
    conf = await db.get_config()
    t_min = conf.get('delete_time', 600) // 60
    
    texto = (
        "🛠 **PANEL DE CONTROL**\n\n"
        f"📡 **Almacén Seguro:** `{conf.get('log_channel', 'No detectado')}`\n"
        f"⏳ **Autoborrado en Chat Privado:** `{t_min} min`"
    )
    
    botones = InlineKeyboardMarkup([
        [InlineKeyboardButton("⏱ Cambiar Tiempo de Borrado", callback_data="set_time")],
        [InlineKeyboardButton("📊 Estadísticas", callback_data="stats")]
    ])
    await message.reply(texto, reply_markup=botones)

# --- LÓGICA DE CAMBIO DE TIEMPO (CALLBACKS) ---
@bot.on_callback_query(filters.regex(r"^(set_time|time_|back_admin)"))
async def admin_callbacks(client, query):
    if query.data == "set_time":
        botones = InlineKeyboardMarkup([
            [InlineKeyboardButton("5 min", callback_data="time_300"), InlineKeyboardButton("15 min", callback_data="time_900")],
            [InlineKeyboardButton("1 hora", callback_data="time_3600"), InlineKeyboardButton("Desactivar", callback_data="time_0")],
            [InlineKeyboardButton("⬅️ Volver", callback_data="back_admin")]
        ])
        await query.edit_message_text("¿Cuánto tiempo deben durar los mensajes en el chat del usuario?", reply_markup=botones)
    
    elif query.data.startswith("time_"):
        segundos = int(query.data.split("_")[1])
        await db.update_config({"delete_time": segundos})
        await query.answer("Configuración guardada ✅")
        await admin_menu(client, query.message)

# --- PROCESO BATCH (COPIA AL ALMACÉN) ---
@bot.on_message(filters.command("batch") & filters.user(Config.ADMIN_ID))
async def batch_process(client, message):
    conf = await db.get_config()
    if not conf.get("log_channel"):
        return await message.reply("❌ Error: Primero hazme admin en un canal privado.")

    m1 = await client.ask(message.chat.id, "Envíame el PRIMER mensaje (o el ID) del origen.")
    m2 = await client.ask(message.chat.id, "Envíame el ÚLTIMO mensaje (o el ID) del origen.")
    
    # Obtener IDs y Chat ID del origen
    s_id = m1.forward_from_message_id if m1.forward_from_message_id else int(m1.text)
    e_id = m2.forward_from_message_id if m2.forward_from_message_id else int(m2.text)
    c_ori = m1.forward_from_chat.id if m1.forward_from_chat else (await client.ask(message.chat.id, "ID del Canal Origen:")).text

    pje = await message.reply("📦 Copiando archivos a la bodega permanente...")
    
    for i in range(s_id, e_id + 1):
        try:
            # COPIA AL CANAL (Esto no se borra nunca)
            await client.copy_message(conf["log_channel"], c_ori, i)
            if (i - s_id) % 100 == 0 and i != s_id:
                await asyncio.sleep(15) # Flood protection
        except: continue

    b_id = str(uuid.uuid4())[:8]
    await db.save_link(b_id, s_id, e_id)
    await pje.edit(f"✅ **Lote Listo**\nLink: `https://t.me/{bot.me.username}?start={b_id}`")

# --- MANEJADOR DE START (ENTREGA Y BORRADO LOCAL) ---
@bot.on_message(filters.command("start") & filters.private)
async def handle_start(client, message):
    if len(message.command) > 1:
        data = await db.links.find_one({"batch_id": message.command[1]})
        if data:
            conf = await db.get_config()
            temp_msgs = []
            
            # Avisar al usuario
            status = await message.reply("📥 Preparando tus archivos...")

            for m_id in range(data["start_id"], data["end_id"] + 1):
                try:
                    # COPIA DEL ALMACÉN AL USUARIO
                    m = await client.copy_message(message.chat.id, conf["log_channel"], m_id)
                    temp_msgs.append(m.id)
                    await asyncio.sleep(0.3)
                except: continue
            
            # Lógica de autodestrucción SOLO en el chat del usuario
            if conf.get("delete_time", 0) > 0:
                wait_min = conf['delete_time'] // 60
                await status.edit(f"⏳ **Aviso:** Estos archivos se borrarán de este chat en {wait_min} min.")
                await asyncio.sleep(conf["delete_time"])
                
                # Borramos los archivos en el chat del usuario
                await client.delete_messages(message.chat.id, temp_msgs)
                # También borramos el mensaje de aviso
                await status.delete()
                await message.reply("🗑 Los archivos temporales han sido eliminados. Usa el link para verlos de nuevo.")
            else:
                await status.delete()
        else:
            await message.reply("❌ Enlace no válido.")

bot.run()
