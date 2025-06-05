import logging
import re
from typing import Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from telethon import TelegramClient
from telethon.tl.functions.messages import GetHistoryRequest
from telethon.errors import ChannelPrivateError, UsernameNotOccupiedError
import os
from dotenv import load_dotenv
from telethon.sessions import StringSession
import sys
import asyncio
from contextlib import suppress

# Configurar logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Cargar variables de entorno
load_dotenv()

# Configuración
BOT_TOKEN = os.getenv('BOT_TOKEN')
API_ID = int(os.getenv('API_ID'))
API_HASH = os.getenv('API_HASH')
PHONE_NUMBER = os.getenv('PHONE_NUMBER')
SESSION_STRING = os.getenv('SESSION_STRING')

# Lista de usuarios premium
PREMIUM_USERS = set()

class ContentCopyBot:
    def __init__(self):
        self.client = None
        
    async def start_client(self):
        """Inicializar cliente de Telethon"""
        if self.client is None:
            self.client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
        
        if not self.client.is_connected():
            await self.client.connect()
            
        if not await self.client.is_user_authorized():
            logger.error("Cliente no autorizado. Verifique SESSION_STRING")
            raise Exception("Cliente no autorizado")

    async def stop_client(self):
        """Detener cliente de Telethon"""
        if self.client and self.client.is_connected():
            await self.client.disconnect()
        
    async def copy_content(self, channel_url: str, message_id: int, is_premium: bool = False):
        """Copiar contenido de un canal protegido"""
        try:
            # Extraer username del canal
            username = self.extract_username(channel_url)
            if not username:
                return None, "❌ URL de canal inválida"
            
            # Obtener entidad del canal
            try:
                entity = await self.client.get_entity(username)
            except (ChannelPrivateError, UsernameNotOccupiedError):
                if not is_premium:
                    return None, "🔒 Este es un canal privado. Necesitas la versión Premium."
                return None, "❌ Canal no encontrado o inaccesible"
            
            # Obtener mensaje específico
            try:
                message = await self.client.get_messages(entity, ids=message_id)
                if not message:
                    return None, "❌ Mensaje no encontrado"
                
                return message, None
                
            except Exception as e:
                return None, f"❌ Error al obtener el mensaje: {str(e)}"
                
        except Exception as e:
            return None, f"❌ Error general: {str(e)}"
    
    async def bulk_copy(self, channel_url: str, limit: int = 10):
        """Copia masiva de contenido (solo premium)"""
        try:
            username = self.extract_username(channel_url)
            if not username:
                return None, "❌ URL de canal inválida"
            
            entity = await self.client.get_entity(username)
            messages = await self.client.get_messages(entity, limit=limit)
            
            return messages, None
            
        except Exception as e:
            return None, f"❌ Error en copia masiva: {str(e)}"
    
    def extract_username(self, url: str) -> Optional[str]:
        """Extraer username de URL de Telegram"""
        patterns = [
            r't\.me/([^/]+)',
            r'telegram\.me/([^/]+)',
            r'@([a-zA-Z0-9_]+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None
    
    def extract_message_id(self, url: str) -> Optional[int]:
        """Extraer ID del mensaje de la URL"""
        match = re.search(r'/(\d+)$', url)
        if match:
            return int(match.group(1))
        return None

# Instancia del bot
copy_bot = ContentCopyBot()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /start"""
    user = update.effective_user
    
    welcome_text = f"""👋 ¡Hola {user.first_name}!

💬 Puedo saltar las restricciones de copia, descarga y reenvío de los canales.

🔗 Envíame el enlace de una publicación, realizada en un Canal con Protección de Contenido, para copiar su contenido aquí.

• Versión Gratuita:
- Permite copiar de canales públicos.

• Versión Premium:
- Permite copiar de canales públicos.
- Permite copiar de canales privados.
- Permite la copia masiva del contenido.

📋 Comandos disponibles:
/help - Ver ayuda
/premium - Información sobre versión premium
/status - Ver tu estado actual"""

    keyboard = [
        [InlineKeyboardButton("📋 Ver Comandos", callback_data='help')],
        [InlineKeyboardButton("⭐ Premium", callback_data='premium')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(welcome_text, reply_markup=reply_markup)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /help"""
    help_text = """📋 **Comandos Disponibles:**

🔗 **Copia Simple:**
Envía un enlace de canal como:
`https://t.me/canal/123`

📊 **Comandos:**
/start - Iniciar el bot
/help - Ver esta ayuda
/premium - Info sobre versión premium
/status - Ver tu estado
/bulk [enlace] [cantidad] - Copia masiva (Premium)

🎯 **Formatos Soportados:**
• Texto
• Imágenes
• Videos
• Documentos
• Enlaces

⚠️ **Importante:**
- Respeta los derechos de autor
- Usa responsablemente"""

    await update.message.reply_text(help_text, parse_mode='Markdown')

async def premium_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Información sobre premium"""
    user_id = update.effective_user.id
    is_premium = user_id in PREMIUM_USERS
    
    if is_premium:
        text = """⭐ **Versión Premium Activa**

✅ Funciones disponibles:
• Copia de canales públicos
• Copia de canales privados
• Copia masiva de contenido
• Soporte prioritario

🚀 ¡Disfruta de todas las funciones!"""
    else:
        text = """⭐ **Versión Premium**

🔓 Desbloquea funciones adicionales:
• Acceso a canales privados
• Copia masiva de contenido
• Soporte prioritario
• Sin límites de uso

💰 Precio: $5/mes

Para activar Premium, contacta: @admin"""

    keyboard = []
    if not is_premium:
        keyboard.append([InlineKeyboardButton("💳 Activar Premium", callback_data='activate_premium')])
    
    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    await update.message.reply_text(text, parse_mode='Markdown', reply_markup=reply_markup)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ver estado del usuario"""
    user = update.effective_user
    is_premium = user.id in PREMIUM_USERS
    
    status_text = f"""📊 **Estado de Usuario**

👤 Usuario: {user.first_name}
🆔 ID: {user.id}
⭐ Plan: {'Premium' if is_premium else 'Gratuito'}

📈 **Funciones Disponibles:**
{'✅' if True else '❌'} Canales públicos
{'✅' if is_premium else '❌'} Canales privados
{'✅' if is_premium else '❌'} Copia masiva"""

    await update.message.reply_text(status_text, parse_mode='Markdown')

async def bulk_copy_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando para copia masiva"""
    user_id = update.effective_user.id
    
    if user_id not in PREMIUM_USERS:
        await update.message.reply_text("⭐ Esta función requiere Premium. Usa /premium para más info.")
        return
    
    if len(context.args) < 1:
        await update.message.reply_text("📋 Uso: /bulk [enlace_canal] [cantidad]\nEjemplo: /bulk https://t.me/canal 10")
        return
    
    channel_url = context.args[0]
    limit = int(context.args[1]) if len(context.args) > 1 else 10
    
    if limit > 50:
        await update.message.reply_text("⚠️ Límite máximo: 50 mensajes")
        return
    
    await update.message.reply_text("🔄 Iniciando copia masiva...")
    
    messages, error = await copy_bot.bulk_copy(channel_url, limit)
    
    if error:
        await update.message.reply_text(error)
        return
    
    await update.message.reply_text(f"✅ Copiando {len(messages)} mensajes...")
    
    for msg in messages:
        try:
            if msg.text:
                await update.message.reply_text(msg.text)
            elif msg.photo:
                await update.message.reply_photo(msg.photo, caption=msg.caption or "")
            elif msg.video:
                await update.message.reply_video(msg.video, caption=msg.caption or "")
            elif msg.document:
                await update.message.reply_document(msg.document, caption=msg.caption or "")
            
            await asyncio.sleep(1)  # Evitar spam
            
        except Exception as e:
            logger.error(f"Error copiando mensaje: {e}")
            continue

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Manejar enlaces de Telegram"""
    text = update.message.text
    user_id = update.effective_user.id
    is_premium = user_id in PREMIUM_USERS
    
    # Verificar si es un enlace de Telegram
    if not re.search(r't\.me|telegram\.me', text):
        await update.message.reply_text("❌ Por favor envía un enlace válido de Telegram")
        return
    
    # Extraer información
    message_id = copy_bot.extract_message_id(text)
    if not message_id:
        await update.message.reply_text("❌ No se pudo extraer el ID del mensaje del enlace")
        return
    
    await update.message.reply_text("🔄 Procesando enlace...")
    
    # Copiar contenido
    message, error = await copy_bot.copy_content(text, message_id, is_premium)
    
    if error:
        await update.message.reply_text(error)
        return
    
    if not message:
        await update.message.reply_text("❌ No se pudo obtener el contenido")
        return
    
    # Enviar contenido copiado
    try:
        if message.text:
            await update.message.reply_text(f"📋 **Contenido copiado:**\n\n{message.text}", parse_mode='Markdown')
        elif message.photo:
            await update.message.reply_photo(message.photo, caption=f"📋 Imagen copiada\n{message.caption or ''}")
        elif message.video:
            await update.message.reply_video(message.video, caption=f"📋 Video copiado\n{message.caption or ''}")
        elif message.document:
            await update.message.reply_document(message.document, caption=f"📋 Documento copiado\n{message.caption or ''}")
        else:
            await update.message.reply_text("✅ Contenido procesado (tipo no soportado para vista previa)")
            
    except Exception as e:
        await update.message.reply_text(f"❌ Error al enviar contenido: {str(e)}")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Manejar botones inline"""
    query = update.callback_query
    await query.answer()
    
    if query.data == 'help':
        await help_command(query, context)
    elif query.data == 'premium':
        await premium_info(query, context)
    elif query.data == 'activate_premium':
        await query.edit_message_text("💳 Para activar Premium, contacta a @admin con tu ID: " + str(query.from_user.id))

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Manejar errores"""
    logger.error(f"Update {update} caused error {context.error}")

async def start_bot():
    """Iniciar el bot con manejo apropiado de recursos"""
    # Crear aplicación
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Registrar handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("premium", premium_info))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("bulk", bulk_copy_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    app.add_error_handler(error_handler)

    try:
        # Iniciar cliente de Telethon
        await copy_bot.start_client()
        
        # Iniciar bot
        print("🤖 Bot iniciado...")
        await app.initialize()
        await app.start()
        await app.run_polling(allowed_updates=Update.ALL_TYPES, stop_signals=None)
        
    except Exception as e:
        logger.error(f"Error al iniciar el bot: {e}")
        raise
    finally:
        # Limpiar recursos
        with suppress(Exception):
            await app.stop()
        with suppress(Exception):
            await copy_bot.stop_client()

def main():
    """Función principal con manejo de eventos del sistema"""
    try:
        # Configurar y ejecutar el event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(start_bot())
    except KeyboardInterrupt:
        logger.info("Bot detenido por el usuario")
    except Exception as e:
        logger.error(f"Error fatal: {e}")
    finally:
        # Limpiar el event loop
        with suppress(Exception):
            loop.close()

if __name__ == '__main__':
    main()
