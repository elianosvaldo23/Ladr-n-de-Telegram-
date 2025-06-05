import logging
import re
import asyncio
from typing import Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from telethon import TelegramClient
from telethon.tl.functions.messages import GetHistoryRequest
from telethon.errors import ChannelPrivateError, UsernameNotOccupiedError, SessionPasswordNeededError
import os
from dotenv import load_dotenv
from telethon.sessions import StringSession
import time

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
        # Usar StringSession vacía para comenzar
        self.session_string = ""
        self.client = None
        self.is_initialized = False
        
    async def initialize_client(self):
        """Inicializar y autenticar el cliente de Telethon"""
        if self.is_initialized:
            return True
            
        try:
            # Crear cliente con StringSession
            self.client = TelegramClient(StringSession(self.session_string), API_ID, API_HASH)
            
            # Conectar cliente
            await self.client.connect()
            
            # Verificar si ya está autorizado
            if not await self.client.is_user_authorized():
                logger.info("Cliente no autorizado, iniciando proceso de autenticación...")
                
                # Enviar código
                await self.client.send_code_request(PHONE_NUMBER)
                logger.info(f"Código enviado a {PHONE_NUMBER}")
                
                # Nota: En producción, necesitarías una forma de manejar esto
                # Por ahora, asumimos que ya tienes una sesión válida guardada
                return False
            
            self.is_initialized = True
            logger.info("Cliente de Telethon inicializado correctamente")
            return True
            
        except Exception as e:
            logger.error(f"Error inicializando cliente: {e}")
            return False

    async def ensure_connected(self):
        """Asegurar que el cliente esté conectado"""
        if not self.client:
            await self.initialize_client()
            
        if not self.client.is_connected():
            await self.client.connect()
            
        return self.client.is_connected()

    async def copy_content(self, channel_url: str, message_id: int, is_premium: bool = False):
        """Copiar contenido de un canal"""
        try:
            # Asegurar conexión
            if not await self.ensure_connected():
                return None, "❌ Error de conexión al cliente"
            
            # Extraer username del canal
            username = self.extract_username(channel_url)
            if not username:
                return None, "❌ URL de canal inválida"
            
            logger.info(f"Intentando acceder al canal: {username}")
            
            # Obtener entidad del canal
            try:
                entity = await self.client.get_entity(username)
                logger.info(f"Canal encontrado: {entity.title if hasattr(entity, 'title') else username}")
            except ChannelPrivateError:
                if not is_premium:
                    return None, "🔒 Este es un canal privado. Necesitas la versión Premium."
                return None, "❌ Canal privado inaccesible"
            except UsernameNotOccupiedError:
                return None, "❌ Canal no encontrado"
            except Exception as e:
                return None, f"❌ Error accediendo al canal: {str(e)}"
            
            # Obtener mensaje específico
            try:
                messages = await self.client.get_messages(entity, ids=message_id)
                
                # get_messages puede devolver una lista o un mensaje único
                if isinstance(messages, list):
                    message = messages[0] if messages else None
                else:
                    message = messages
                
                if not message:
                    return None, "❌ Mensaje no encontrado"
                
                logger.info(f"Mensaje obtenido: ID {message.id}")
                return message, None
                
            except Exception as e:
                logger.error(f"Error obteniendo mensaje: {e}")
                return None, f"❌ Error al obtener el mensaje: {str(e)}"
                
        except Exception as e:
            logger.error(f"Error general en copy_content: {e}")
            return None, f"❌ Error general: {str(e)}"

    async def bulk_copy(self, channel_url: str, limit: int = 10):
        """Copia masiva de contenido (solo premium)"""
        try:
            # Asegurar conexión
            if not await self.ensure_connected():
                return None, "❌ Error de conexión al cliente"
            
            username = self.extract_username(channel_url)
            if not username:
                return None, "❌ URL de canal inválida"
            
            logger.info(f"Iniciando copia masiva de {username}, límite: {limit}")
            
            try:
                entity = await self.client.get_entity(username)
                logger.info(f"Canal encontrado para copia masiva: {entity.title if hasattr(entity, 'title') else username}")
            except Exception as e:
                return None, f"❌ Error accediendo al canal: {str(e)}"
            
            # Obtener mensajes
            try:
                messages = await self.client.get_messages(entity, limit=limit)
                logger.info(f"Obtenidos {len(messages)} mensajes")
                return messages, None
                
            except Exception as e:
                logger.error(f"Error obteniendo mensajes: {e}")
                return None, f"❌ Error obteniendo mensajes: {str(e)}"
            
        except Exception as e:
            logger.error(f"Error en bulk_copy: {e}")
            return None, f"❌ Error en copia masiva: {str(e)}"

    async def get_channel_info(self, channel_url: str):
        """Obtener información del canal"""
        try:
            if not await self.ensure_connected():
                return None, "❌ Error de conexión"
                
            username = self.extract_username(channel_url)
            if not username:
                return None, "❌ URL inválida"
                
            entity = await self.client.get_entity(username)
            
            info = {
                'title': getattr(entity, 'title', 'Sin título'),
                'username': getattr(entity, 'username', username),
                'id': entity.id,
                'participants_count': getattr(entity, 'participants_count', 0),
                'is_private': hasattr(entity, 'access_hash')
            }
            
            return info, None
            
        except Exception as e:
            return None, f"❌ Error obteniendo info: {str(e)}"

    @staticmethod
    def extract_username(url: str) -> Optional[str]:
        """Extraer username de URL de Telegram"""
        patterns = [
            r't\.me/([^/\?]+)',
            r'telegram\.me/([^/\?]+)',
            r'@([a-zA-Z0-9_]+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                username = match.group(1)
                # Limpiar parámetros adicionales
                username = username.split('?')[0]
                return username
        return None

    @staticmethod
    def extract_message_id(url: str) -> Optional[int]:
        """Extraer ID del mensaje de la URL"""
        match = re.search(r'/(\d+)(?:\?|$)', url)
        if match:
            return int(match.group(1))
        return None

# Instancia global del bot
copy_bot = ContentCopyBot()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /start"""
    user = update.effective_user
    
    # Inicializar cliente en el primer uso
    if not copy_bot.is_initialized:
        await update.message.reply_text("🔄 Inicializando sistema...")
        success = await copy_bot.initialize_client()
        if not success:
            await update.message.reply_text("⚠️ Sistema en modo limitado. Algunas funciones pueden no estar disponibles.")
    
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
/status - Ver tu estado actual
/info [enlace] - Ver información del canal"""

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
/info [enlace] - Ver información del canal

🎯 **Formatos Soportados:**
• Texto
• Imágenes
• Videos
• Documentos
• Audio
• Stickers
• Enlaces

⚠️ **Importante:**
- Respeta los derechos de autor
- Usa responsablemente"""

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
• Información detallada de canales
• Soporte prioritario

🚀 ¡Disfruta de todas las funciones!"""
    else:
        text = """⭐ **Versión Premium**

🔓 Desbloquea funciones adicionales:
• Acceso a canales privados
• Copia masiva de contenido
• Información detallada de canales
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
    
    # Verificar estado del cliente
    client_status = "🟢 Conectado" if copy_bot.is_initialized and copy_bot.client and copy_bot.client.is_connected() else "🔴 Desconectado"
    
    status_text = f"""📊 **Estado de Usuario**

👤 Usuario: {user.first_name}
🆔 ID: {user.id}
⭐ Plan: {'Premium' if is_premium else 'Gratuito'}
🔌 Cliente: {client_status}

📈 **Funciones Disponibles:**
{'✅' if True else '❌'} Canales públicos
{'✅' if is_premium else '❌'} Canales privados
{'✅' if is_premium else '❌'} Copia masiva
{'✅' if is_premium else '❌'} Info detallada"""

    await update.message.reply_text(status_text, parse_mode='Markdown')

async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /info"""
    user_id = update.effective_user.id
    is_premium = user_id in PREMIUM_USERS
    
    if not is_premium:
        await update.message.reply_text("⭐ Esta función requiere Premium. Usa /premium para más info.")
        return
    
    if len(context.args) < 1:
        await update.message.reply_text("📋 Uso: /info [enlace_canal]\nEjemplo: /info https://t.me/canal")
        return
    
    channel_url = context.args[0]
    await update.message.reply_text("🔍 Obteniendo información del canal...")
    
    info, error = await copy_bot.get_channel_info(channel_url)
    
    if error:
        await update.message.reply_text(error)
        return
    
    info_text = f"""📊 **Información del Canal**

📛 Título: {info['title']}
👤 Username: @{info['username']}
🆔 ID: {info['id']}
👥 Miembros: {info['participants_count']:,}
🔒 Tipo: {'Privado' if info['is_private'] else 'Público'}"""

    await update.message.reply_text(info_text, parse_mode='Markdown')

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
    limit = int(context.args[1]) if len(context.args) > 1 and context.args[1].isdigit() else 10
    
    if limit > 50:
        await update.message.reply_text("⚠️ Límite máximo: 50 mensajes")
        return
    
    await update.message.reply_text("🔄 Iniciando copia masiva...")
    
    messages, error = await copy_bot.bulk_copy(channel_url, limit)
    
    if error:
        await update.message.reply_text(error)
        return
    
    if not messages:
        await update.message.reply_text("❌ No se encontraron mensajes")
        return
    
    await update.message.reply_text(f"✅ Encontrados {len(messages)} mensajes. Iniciando copia...")
    
    copied_count = 0
    for i, msg in enumerate(messages):
        try:
            if not msg:
                continue
                
            # Enviar mensaje según su tipo
            if msg.text:
                await update.message.reply_text(f"📝 **Mensaje {i+1}:**\n\n{msg.text}", parse_mode='Markdown')
            elif msg.photo:
                await update.message.reply_photo(msg.photo, caption=f"📸 Imagen {i+1}\n{msg.caption or ''}")
            elif msg.video:
                await update.message.reply_video(msg.video, caption=f"🎥 Video {i+1}\n{msg.caption or ''}")
            elif msg.document:
                await update.message.reply_document(msg.document, caption=f"📎 Documento {i+1}\n{msg.caption or ''}")
            elif msg.audio:
                await update.message.reply_audio(msg.audio, caption=f"🎵 Audio {i+1}\n{msg.caption or ''}")
            elif msg.sticker:
                await update.message.reply_sticker(msg.sticker)
            else:
                await update.message.reply_text(f"📄 Mensaje {i+1}: Tipo de contenido no soportado")
            
            copied_count += 1
            
            # Pausa para evitar límites de rate
            if i < len(messages) - 1:
                await asyncio.sleep(1)
            
        except Exception as e:
            logger.error(f"Error copiando mensaje {i+1}: {e}")
            await update.message.reply_text(f"❌ Error copiando mensaje {i+1}: {str(e)}")
            continue
    
    await update.message.reply_text(f"✅ Copia masiva completada: {copied_count}/{len(messages)} mensajes copiados")

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manejar enlaces de Telegram"""
    text = update.message.text
    user_id = update.effective_user.id
    is_premium = user_id in PREMIUM_USERS
    
    # Verificar si es un enlace de Telegram
    if not re.search(r't\.me|telegram\.me', text):
        await update.message.reply_text("❌ Por favor envía un enlace válido de Telegram")
        return
    
    # Extraer ID del mensaje
    message_id = copy_bot.extract_message_id(text)
    if not message_id:
        await update.message.reply_text("❌ No se pudo extraer el ID del mensaje del enlace.\nAsegúrate de enviar un enlace completo como: https://t.me/canal/123")
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
    
    # Enviar contenido copiado según su tipo
    try:
        if message.text:
            await update.message.reply_text(f"📋 **Contenido copiado:**\n\n{message.text}", parse_mode='Markdown')
        elif message.photo:
            await update.message.reply_photo(
                message.photo, 
                caption=f"📸 **Imagen copiada**\n{message.caption or ''}"
            )
        elif message.video:
            await update.message.reply_video(
                message.video, 
                caption=f"🎥 **Video copiado**\n{message.caption or ''}"
            )
        elif message.document:
            await update.message.reply_document(
                message.document, 
                caption=f"📎 **Documento copiado**\n{message.caption or ''}"
            )
        elif message.audio:
            await update.message.reply_audio(
                message.audio, 
                caption=f"🎵 **Audio copiado**\n{message.caption or ''}"
            )
        elif message.voice:
            await update.message.reply_voice(
                message.voice, 
                caption="🎤 **Nota de voz copiada**"
            )
        elif message.sticker:
            await update.message.reply_sticker(message.sticker)
            await update.message.reply_text("🎭 **Sticker copiado**")
        elif message.animation:
            await update.message.reply_animation(
                message.animation, 
                caption=f"🎬 **GIF copiado**\n{message.caption or ''}"
            )
        else:
            await update.message.reply_text("✅ Contenido procesado (tipo de mensaje no soportado para vista previa)")
            
    except Exception as e:
        logger.error(f"Error enviando contenido: {e}")
        await update.message.reply_text(f"❌ Error al enviar contenido: {str(e)}")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manejar botones inline"""
    query = update.callback_query
    await query.answer()
    
    if query.data == 'help':
        # Crear update falso para reutilizar la función
        fake_update = Update(
            update_id=query.message.message_id,
            message=query.message
        )
        await help_command(fake_update, context)
    elif query.data == 'premium':
        fake_update = Update(
            update_id=query.message.message_id,
            message=query.message,
            effective_user=query.from_user
        )
        fake_update.effective_user = query.from_user
        await premium_info(fake_update, context)
    elif query.data == 'activate_premium':
        await query.edit_message_text(
            f"💳 **Activar Premium**\n\n"
            f"Para activar Premium, contacta a @admin con la siguiente información:\n\n"
            f"👤 Usuario: {query.from_user.first_name}\n"
            f"🆔 ID: {query.from_user.id}\n"
            f"📱 Username: @{query.from_user.username or 'Sin username'}\n\n"
            f"💰 Precio: $5/mes",
            parse_mode='Markdown'
        )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manejar errores"""
    logger.error(f"Update {update} caused error {context.error}")
    
    if update and update.effective_message:
        await update.effective_message.reply_text(
            "❌ Ocurrió un error interno. Por favor intenta nuevamente."
        )

async def shutdown_handler(application: Application):
    """Manejar cierre del bot"""
    if copy_bot.client and copy_bot.client.is_connected():
        await copy_bot.client.disconnect()
    logger.info("Bot desconectado correctamente")

def main():
    """Función principal"""
    try:
        # Crear aplicación
        app = Application.builder().token(BOT_TOKEN).build()
        
        # Configurar shutdown handler
        app.add_handler(CommandHandler("shutdown", shutdown_handler))
        
        # Registrar handlers
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("help", help_command))
        app.add_handler(CommandHandler("premium", premium_info))
        app.add_handler(CommandHandler("status", status_command))
        app.add_handler(CommandHandler("bulk", bulk_copy_command))
        app.add_handler(CommandHandler("info", info_command))
        app.add_handler(CallbackQueryHandler(button_handler))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
        app.add_error_handler(error_handler)
        
        # Configuración para producción/desarrollo
        PORT = int(os.getenv('PORT', '8080'))
        
        # Mensaje de inicio
        print("🤖 Bot iniciado correctamente...")
        logger.info("Bot iniciado correctamente")
        
        # Iniciar el bot
        if os.getenv('ENVIRONMENT') == 'production':
            # Modo producción
            webhook_url = os.getenv('WEBHOOK_URL')
            if webhook_url:
                app.run_webhook(
                    listen="0.0.0.0",
                    port=PORT,
                    webhook_url=webhook_url
                )
            else:
                logger.error("WEBHOOK_URL no configurada para producción")
                app.run_polling(allowed_updates=Update.ALL_TYPES)
        else:
            # Modo desarrollo
            app.run_polling(allowed_updates=Update.ALL_TYPES)
            
    except Exception as e:
        logger.error(f"Error crítico en la ejecución del bot: {e}")
        raise

if __name__ == '__main__':
    main()
