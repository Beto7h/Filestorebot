import asyncio, uuid
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ChatPrivileges
from config import Config
import database as db

# Nota: Asegúrate de tener instalada la librería pyromod (pip install pyromod) 
# para que client.ask funcione correctamente.
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
    # Si el bot es añadido como administrador en un canal o grupo
    if update.new_chat_member and update.new_chat_member.status == "administrator":
        channel_id = update.chat.id
        channel_name = update.chat.title
        
        await db.update_config({"log_channel": channel_id})
        
        await client.send_message(
            channel_id, 
            f"✅ **Almacén Vinculado Automáticamente**\n\n"
            f"He detectado que me has unido a **{channel_name}**.\n"
            "Todos los archivos del proceso /batch se copiarán aquí."
        )

# --- MENÚ ADMIN CON BOTONES ---
@bot.on_message(filters.command("admin") & filters.user(Config.ADMIN_ID))
async def admin_menu(client, message):
    conf = await db.get_config()
    # Convertimos segundos a minutos para mostrarlo mejor
    tiempo_min = conf.get('delete_time', 600) // 60
    
    texto = (
        "🛠 **PANEL DE CONTROL - ADMIN**\n\n"
        f"📡 **Almacén:** `{conf.get('log_channel', 'No configurado')}`\n"
        f"⏳ **Autoborrado:** `{tiempo_min} minutos`"
    )
    
    botones = InlineKeyboardMarkup([
        [InlineKeyboardButton("⏱ Ajustar Tiempo", callback_data="set_time")],
        [InlineKeyboardButton("📊 Estadísticas", callback_data="stats")],
        [InlineKeyboardButton("❌ Cerrar Panel", callback_data="close")]
    ])
    await message.reply(texto, reply_markup=botones)

# --- CALLBACKS DEL PANEL ADMIN (AUTODESTRUCCIÓN) ---
@bot.on_callback_query()
async def callback_handler(client, query):
    if query.data == "set_time":
        botones = InlineKeyboardMarkup([
            [InlineKeyboardButton("5 Min", callback_data="time_300"), 
             InlineKeyboardButton("15 Min", callback_data="time_900")],
            [InlineKeyboardButton("1 Hora", callback_data="time_3600"),
             InlineKeyboardButton("Desactivar", callback_data="time_0")],
            [InlineKeyboardButton("⬅️ Volver", callback_data="back_admin")]
        ])
        await query.edit_message_text("Selecciona el tiempo de autodestrucción:", reply_markup=botones)
    
    elif query.data.startswith("time_"):
        nuevo_tiempo = int(query.data.split("_")[1])
        await db.update_config({"delete_time": nuevo_tiempo})
        await query.answer(f"✅ Tiempo actualizado a {nuevo_tiempo // 60} min")
        await admin_menu(client, query.message) # Refresca el menú
        
    elif query.data == "back_admin":
        await admin_menu(client, query.message)

# --- PROCESO DE REENVÍO POR BLOQUES ---
@bot.on_message(filters.command("batch") & filters.user(Config.ADMIN_ID))
async def batch_process(client, message):
    conf = await db.get_config()
    if not conf.get("log_channel"):
        return await message.reply("❌ Error: Primero añade al bot como administrador en tu canal privado.")

    # Usamos client.ask para flujo secuencial (Requiere pyromod)
    msg1 = await client.ask(message.chat.id, "1️⃣ Envíame el **PRIMER** mensaje del canal origen.")
    msg2 = await client.ask(message.chat.id, "2️⃣ Ahora envíame el **ÚLTIMO** mensaje del canal origen.")
    
    # Extraemos info. Si el mensaje no fue reenviado, pediremos los IDs manualmente.
    try:
        start_id = msg1.forward_from_message_id or int(msg1.text)
        end_id = msg2.forward_from_message_id or int(msg2.text)
        # Si fue reenviado, tomamos el ID del chat origen, si no, lo pedimos
        canal_origen = msg1.forward_from_chat.id if msg1.forward_from_chat else (await client.ask(message.chat.id, "Envíame el ID del canal origen:")).text
    except Exception as e:
        return await message.reply(f"❌ Error al procesar IDs: {e}")

    await message.reply(f"🚀 Iniciando copia de **{end_id - start_id + 1}** mensajes al almacén...")
    
    for i in range(start_id, end_id + 1):
        try:
            # Copy_message no muestra el remitente original
            await client.copy_message(conf["log_channel"], canal_origen, i)
            
            # Pausa cada 100 mensajes (Autoajustable)
            if (i - start_id) % 100 == 0 and i != start_id:
                await message.reply(f"⏳ Bloque de 100 enviado. Esperando 15s...")
                await asyncio.sleep(15)
            else:
                await asyncio.sleep(0.1) # Evitar Flood moderado
        except: continue

    batch_id = str(uuid.uuid4())[:8]
    # Guardamos el rango correspondiente pero en NUESTRO canal almacén
    # (Asumiendo que los IDs en el almacén son idénticos o correlativos)
    await db.save_link(batch_id, start_id, end_id) 
    
    await message.reply(f"✅ **¡Lote Guardado!**\nEnlace Permanente:\n`https://t.me/{bot.me.username}?start={batch_id}`")

# --- MANEJADOR DE LINKS (START CON AUTODESTRUCCIÓN) ---
@bot.on_message(filters.command("start") & filters.private)
async def handle_start(client, message):
    if len(message.command) > 1:
        batch_id = message.command[1]
        batch_data = await db.links.find_one({"batch_id": batch_id})
        
        if batch_data:
            conf = await db.get_config()
            sent_msgs = []
            info_msg = await message.reply("📦 Entregando archivos... Espere.")

            for m_id in range(batch_data["start_id"], batch_data["end_id"] + 1):
                try:
                    m = await client.copy_message(message.chat.id, conf["log_channel"], m_id)
                    sent_msgs.append(m.id)
                    await asyncio.sleep(0.5)
                except: continue
            
            if conf.get("delete_time", 0) > 0:
                await info_msg.edit(f"⚠️ Estos archivos se borrarán en {conf['delete_time'] // 60} minutos.")
                await asyncio.sleep(conf["delete_time"])
                await client.delete_messages(message.chat.id, sent_msgs)
                await message.reply("🗑 Mensajes eliminados. Usa el link de nuevo para recuperarlos.")
        else:
            await message.reply("❌ Enlace no válido o expirado.")
    else:
        await message.reply("Bienvenido al File Store Bot.")

bot.run()
