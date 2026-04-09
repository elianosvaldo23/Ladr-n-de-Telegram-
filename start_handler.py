"""Start command handler and main menu keyboard builder"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from state import (
    db, copy_bot, is_user_premium, save_user_to_db
)
from config import ADMIN_ID, FREE_TRIAL_USES

logger = logging.getLogger(__name__)


def get_main_menu_keyboard(is_premium: bool = False, is_admin: bool = False, user_id: int = 0) -> InlineKeyboardMarkup:
    """Build the main-menu inline keyboard.

    The layout adapts based on the caller's role: admin users see
    management buttons, non-premium users see a free-trial CTA, etc.
    """
    keyboard = [
        [InlineKeyboardButton("📋 Ayuda", callback_data='help')],
        [InlineKeyboardButton("📊 Mi Estado", callback_data='status')],
        [InlineKeyboardButton("⭐ Premium", callback_data='premium')],
        [InlineKeyboardButton("⚙️ Configuración", callback_data='user_config_menu')]
    ]

    if not is_premium and user_id:
        trial_info = db.get_free_trial_info(user_id)
        if not trial_info.get('trial_activated', False):
            keyboard.insert(2, [InlineKeyboardButton("🎁 ¡Prueba Premium Gratis!", callback_data='free_trial_info')])
        elif trial_info.get('trial_uses_left', 0) > 0:
            uses_left = trial_info['trial_uses_left']
            keyboard.insert(2, [InlineKeyboardButton(f"🎁 Prueba Premium ({uses_left} usos restantes)", callback_data='free_trial_info')])

    if is_admin:
        keyboard.append([InlineKeyboardButton("⚙️ Configurar Userbot", callback_data='config_userbot')])
        keyboard.append([InlineKeyboardButton("👥 Admin: Gestionar Premium", callback_data='admin_premium')])
        keyboard.append([InlineKeyboardButton("📢 Admin: Broadcast", callback_data='admin_broadcast')])

    return InlineKeyboardMarkup(keyboard)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the ``/start`` command: greet the user, persist their data,
    and display the main-menu keyboard."""
    user = update.effective_user
    is_admin = user.id == ADMIN_ID
    is_premium = is_user_premium(user.id)

    save_user_to_db({
        'user_id': user.id,
        'username': user.username,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'is_premium': is_premium,
        'is_admin': is_admin
    })

    userbot_status = "✅ Conectado" if copy_bot.is_initialized else "⚠️ No configurado"

    if is_admin and not copy_bot.config.is_configured():
        await update.message.reply_text(
            "🔧 **Configuración Inicial Requerida**\n\n"
            "Bienvenido administrador. Para que el bot funcione correctamente, "
            "necesitas configurar el userbot.\n\n"
            f"Estado actual: {userbot_status}\n\n"
            "Usa el botón '⚙️ Configurar Userbot' para comenzar.",
            parse_mode='Markdown'
        )

    welcome_text = (
        f"👋 ¡Hola {user.first_name}!\n\n"
        f"💬 Puedo saltar las restricciones de copia, descarga y reenvío de los canales.\n\n"
        f"🔗 Envíame el enlace de una publicación, realizada en un Canal con Protección de Contenido, para copiar su contenido aquí.\n\n"
        f"• *Versión Gratuita:*\n"
        f"  - Permite copiar de canales públicos.\n\n"
        f"• *🎁 Prueba Premium Gratis:*\n"
        f"  - {FREE_TRIAL_USES} extracciones en canales privados/restringidos.\n"
        f"  - Solo una vez, requiere unirse al canal oficial.\n\n"
        f"• *Versión Premium:*\n"
        f"  - Permite copiar de canales públicos.\n"
        f"  - Permite copiar de canales privados.\n"
        f"  - Permite la copia masiva del contenido.\n"
        f"  - Configuración de canal destino.\n"
        f"  - Filtros de contenido personalizados.\n"
        f"  - Información detallada de canales.\n\n"
        f"🤖 Estado del Userbot: {userbot_status}"
    )

    keyboard = get_main_menu_keyboard(is_premium, is_admin, user.id)
    await update.message.reply_text(welcome_text, parse_mode='Markdown', reply_markup=keyboard)
