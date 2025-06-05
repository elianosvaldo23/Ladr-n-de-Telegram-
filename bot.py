import logging
import re
from typing import Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from telethon import TelegramClient
from telethon.tl.functions.messages import GetHistoryRequest
from telethon.errors import ChannelPrivateError, UsernameNotOccupiedError
import os
from dotenv import load_dotenv
from telethon.sessions import StringSession

# Configurar logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Cargar variables de entorno
load_dotenv()

# Configuración
BOT_TOKEN = "7755147755:AAFwEVI5vL2BOWWxJGjqRnJamVk2djNQ-EM"
API_ID = 21410894
API_HASH = "abc158fa56ca252ed9cf0e3aa530f658"
PHONE_NUMBER = "+15812425775"

# Lista de usuarios premium (puedes modificar esta lista según necesites)
PREMIUM_USERS = {1742433244}  # Agrega los IDs de usuarios premium aquí

class ContentCopyBot:
    def __init__(self):
        self.client = TelegramClient(StringSession(), API_ID, API_HASH)
        
    async def start_client(self):
        """Iniciar cliente de Telethon"""
        await self.client.connect()
        if not await self.client.is_user_authorized():
            await self.client.send_code_request(PHONE_NUMBER)
            try:
                await self.client.sign_in(PHONE_NUMBER, input('Ingrese el código recibido: '))
            except Exception as e:
                logger.error(f"Error en autenticación: {e}")
                raise

    async def copy_content(self, channel_url: str, message_id: int, is_premium: bool = False):
        """Copiar contenido de un canal"""
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

    @staticmethod
    def extract_username(url: str) -> Optional[str]:
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

    @staticmethod
    def extract_message_id(url: str) -> Optional[int]:
        """Extraer ID del mensaje de la URL"""
        match = re.search(r'/(\d+)$', url)
        if match:
            return int(match.group(1))
        return None

# Instancia global del bot
copy_bot = ContentCopyBot()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /start"""
    user = update.effective_user
    welcome_text = f"""👋 ¡Hola {user.first_name}!

💬 Puedo ayudarte a copiar contenido de canales.

🔗 Envíame el enlace de una publicación para copiar su contenido aquí.

• Versión Gratuita:
- Permite copiar de canales públicos

• Versión Premium:
- Permite copiar de canales públicos y privados
- Permite copia masiva de contenido

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

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
• Enlaces"""

    await update.message.reply_text(help_text, parse_mode='Markdown')

async def premium_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /premium"""
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

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /status"""
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

async def bulk_copy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /bulk"""
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

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manejar enlaces de Telegram"""
    text = update.message.text
    user_id = update.effective_user.id
    is_premium = user_id in PREMIUM_USERS
    
    if not re.search(r't\.me|telegram\.me', text):
        await update.message.reply_text("❌ Por favor envía un enlace válido de Telegram")
        return
    
    message_id = copy_bot.extract_message_id(text)
    if not message_id:
        await update.message.reply_text("❌ No se pudo extraer el ID del mensaje del enlace")
        return
    
    await update.message.reply_text("🔄 Procesando enlace...")
    
    message, error = await copy_bot.copy_content(text, message_id, is_premium)
    
    if error:
        await update.message.reply_text(error)
        return
    
    try:
        if message.text:
            await update.message.reply_text(message.text)
        elif message.photo:
            await update.message.reply_photo(message.photo, caption=message.caption or "")
        elif message.video:
            await update.message.reply_video(message.video, caption=message.caption or "")
        elif message.document:
            await update.message.reply_document(message.document, caption=message.caption or "")
        else:
            await update.message.reply_text("✅ Contenido procesado (tipo no soportado)")
    except Exception as e:
        await update.message.reply_text(f"❌ Error al enviar contenido: {str(e)}")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manejar botones inline"""
    query = update.callback_query
    await query.answer()
    
    if query.data == 'help':
        await help_command(update, context)
    elif query.data == 'premium':
        await premium_info(update, context)
    elif query.data == 'activate_premium':
        await query.edit_message_text(
            "💳 Para activar Premium, contacta a @admin con tu ID: " + str(query.from_user.id)
        )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manejar errores"""
    logger.error(f"Update {update} caused error {context.error}")

def main():
    """Función principal"""
    try:
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
        
        # Configuración para Render
        PORT = int(os.getenv('PORT', '8080'))
        
        # Mensaje de inicio
        print("🤖 Bot iniciado...")
        
        # Iniciar el bot
        if os.getenv('ENVIRONMENT') == 'production':
            # Modo producción (Render)
            app.run_webhook(
                listen="0.0.0.0",
                port=PORT,
                webhook_url=os.getenv('WEBHOOK_URL', f"https://{os.getenv('RENDER_EXTERNAL_URL')}")
            )
        else:
            # Modo desarrollo (local)
            app.run_polling(allowed_updates=Update.ALL_TYPES)
            
    except Exception as e:
        logger.error(f"Error en la ejecución del bot: {e}")

if __name__ == '__main__':
    main()
