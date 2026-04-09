"""Userbot configuration handlers - API ID, Hash, Phone, Code, 2FA"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from state import copy_bot
from config import ADMIN_ID, CONFIG_API_ID, CONFIG_API_HASH, CONFIG_PHONE, CONFIG_CODE, CONFIG_2FA

logger = logging.getLogger(__name__)

async def config_api_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recibir API ID"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⚠️ Solo el administrador puede configurar el userbot")
        return ConversationHandler.END
    
    try:
        api_id = int(update.message.text)
        context.user_data['temp_api_id'] = api_id
        
        cancel_btn = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data='cancel_config_btn')]])
        await update.message.reply_text(
            "✅ API ID guardado.\n\n"
            "🔧 **Paso 2: API Hash**\n\n"
            "Ahora envía tu API Hash.",
            parse_mode='Markdown',
            reply_markup=cancel_btn
        )
        return CONFIG_API_HASH
        
    except ValueError:
        cancel_btn = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data='cancel_config_btn')]])
        await update.message.reply_text(
            "❌ API ID inválido. Debe ser un número.\n\n"
            "Por favor, intenta nuevamente.",
            reply_markup=cancel_btn
        )
        return CONFIG_API_ID

async def config_api_hash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recibir API Hash"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⚠️ Solo el administrador puede configurar el userbot")
        return ConversationHandler.END
    
    api_hash = update.message.text.strip()
    context.user_data['temp_api_hash'] = api_hash
    
    cancel_btn = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data='cancel_config_btn')]])
    await update.message.reply_text(
        "✅ API Hash guardado.\n\n"
        "🔧 **Paso 3: Número de Teléfono**\n\n"
        "Envía tu número de teléfono con código de país.\n"
        "Ejemplo: +1234567890",
        parse_mode='Markdown',
        reply_markup=cancel_btn
    )
    return CONFIG_PHONE

async def config_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recibir número de teléfono"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⚠️ Solo el administrador puede configurar el userbot")
        return ConversationHandler.END
    
    phone = update.message.text.strip()
    
    # Validar formato básico
    if not phone.startswith('+'):
        cancel_btn = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data='cancel_config_btn')]])
        await update.message.reply_text(
            "❌ El número debe incluir el código de país con +\n"
            "Ejemplo: +1234567890\n\n"
            "Intenta nuevamente.",
            reply_markup=cancel_btn
        )
        return CONFIG_PHONE
    
    # Guardar configuración temporal
    copy_bot.config.set('api_id', context.user_data['temp_api_id'])
    copy_bot.config.set('api_hash', context.user_data['temp_api_hash'])
    copy_bot.config.set('phone_number', phone)
    
    await update.message.reply_text(
        "✅ Número guardado.\n\n"
        "🔄 Enviando código de verificación...",
        parse_mode='Markdown'
    )
    
    # Enviar código de verificación
    success = await copy_bot.send_code_request()
    
    if success:
        cancel_btn = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data='cancel_config_btn')]])
        await update.message.reply_text(
            "📱 **Código de verificación enviado**\n\n"
            "Revisa tu Telegram y envía el código que recibiste.\n"
            "Formato: 12345",
            parse_mode='Markdown',
            reply_markup=cancel_btn
        )
        return CONFIG_CODE
    else:
        await update.message.reply_text(
            "❌ Error al enviar código de verificación.\n"
            "Verifica tus credenciales e intenta nuevamente.\n\n"
            "Usa /start para volver a configurar."
        )
        return ConversationHandler.END

async def config_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recibir código de verificación"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⚠️ Solo el administrador puede configurar el userbot")
        return ConversationHandler.END
    
    code = update.message.text.strip()
    
    await update.message.reply_text("🔄 Verificando código...")
    
    success, message = await copy_bot.sign_in_with_code(code)
    
    if success:
        await update.message.reply_text(
            "✅ **¡Configuración Completada!**\n\n"
            "El userbot está ahora conectado y funcionando.\n"
            "Puedes comenzar a usar el bot.\n\n"
            "Usa /start para ver el menú principal.",
            parse_mode='Markdown'
        )
        
        # Limpiar datos temporales
        context.user_data.clear()
        return ConversationHandler.END
        
    elif message == "2FA requerido":
        cancel_btn = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data='cancel_config_btn')]])
        await update.message.reply_text(
            "🔐 **Autenticación de Dos Factores Detectada**\n\n"
            "Tu cuenta tiene 2FA activado.\n"
            "Por favor, envía tu contraseña de 2FA.",
            parse_mode='Markdown',
            reply_markup=cancel_btn
        )
        context.user_data['temp_code'] = code
        return CONFIG_2FA
        
    else:
        cancel_btn = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data='cancel_config_btn')]])
        await update.message.reply_text(
            f"❌ {message}\n\n"
            "Verifica el código e intenta nuevamente.",
            reply_markup=cancel_btn
        )
        return CONFIG_CODE

async def config_2fa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recibir contraseña de 2FA"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⚠️ Solo el administrador puede configurar el userbot")
        return ConversationHandler.END
    
    password = update.message.text.strip()
    code = context.user_data.get('temp_code', '')
    
    await update.message.reply_text("🔄 Verificando contraseña...")
    
    success, message = await copy_bot.sign_in_with_code(code, password)
    
    if success:
        await update.message.reply_text(
            "✅ **¡Configuración Completada!**\n\n"
            "El userbot está ahora conectado y funcionando con 2FA.\n"
            "Puedes comenzar a usar el bot.\n\n"
            "Usa /start para ver el menú principal.",
            parse_mode='Markdown'
        )
        
        # Limpiar datos temporales
        context.user_data.clear()
        return ConversationHandler.END
    else:
        cancel_btn = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data='cancel_config_btn')]])
        await update.message.reply_text(
            f"❌ {message}\n\n"
            "Verifica la contraseña e intenta nuevamente.",
            reply_markup=cancel_btn
        )
        return CONFIG_2FA

async def cancel_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancelar configuración (vía /cancel o botón)"""
    context.user_data.clear()
    
    # Funciona tanto para mensajes como para callback queries
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menú Principal", callback_data='back_to_menu')]])
    
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            "❌ **Configuración cancelada.**\n\n"
            "Puedes volver al menú principal con el botón de abajo.",
            parse_mode='Markdown',
            reply_markup=keyboard
        )
    else:
        await update.message.reply_text(
            "❌ **Configuración cancelada.**\n\n"
            "Puedes volver al menú principal con el botón de abajo.",
            parse_mode='Markdown',
            reply_markup=keyboard
        )
    return ConversationHandler.END
