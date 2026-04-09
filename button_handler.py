"""Inline button callback handler - handles all callback_query events"""

import asyncio
import logging
from datetime import datetime
from typing import Optional, Tuple
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from state import (
    db, copy_bot, is_user_premium,
    save_user_to_db, check_user_in_channel,
    get_user_config_from_db
)
from start_handler import get_main_menu_keyboard
from config import (
    ADMIN_ID, FREE_TRIAL_USES, FREE_TRIAL_REQUIRED_CHANNEL,
    CONFIG_API_ID
)
from strings import FILTER_NAMES, FILTER_LABELS

logger = logging.getLogger(__name__)


def _build_filter_display(filters: dict) -> Tuple[str, list]:
    """Build the filter-status text and inline keyboard.

    Args:
        filters: Mapping of filter key (e.g. ``'videos'``) to enabled flag.

    Returns:
        A ``(config_text, keyboard_rows)`` tuple ready for
        ``edit_message_text``.
    """
    config_text = (
        "🎯 **Filtros de Contenido**\n\n"
        "Activa o desactiva los tipos de contenido que deseas extraer en las copias masivas.\n\n"
        "**Estado actual:**\n"
    )
    for key, label in FILTER_NAMES.items():
        status = '✅ Activo' if filters.get(key, True) else '❌ Desactivado'
        config_text += f"• {label}: {status}\n"
    config_text += "\nToca un botón para activar/desactivar:"

    # Button pairs: videos/photos, documents/audio, text/stickers
    keys = list(FILTER_NAMES.keys())
    keyboard = []
    for i in range(0, len(keys), 2):
        row = []
        for k in keys[i:i+2]:
            icon = FILTER_NAMES[k].split()[0]
            short = FILTER_LABELS[k]
            tick = '✅' if filters.get(k, True) else '❌'
            row.append(InlineKeyboardButton(
                f"{icon} {short} {tick}",
                callback_data=f'toggle_filter_{k}'
            ))
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("🔙 Volver", callback_data='user_config_menu')])
    
    return config_text, keyboard

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[int]:
    """Central callback-query router for all inline-keyboard buttons.

    Returns:
        A ``ConversationHandler`` state int when entering the config
        flow, or ``None`` otherwise.
    """
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    is_admin = user_id == ADMIN_ID
    is_premium = is_user_premium(user_id)
    
    # Guardar interacción del usuario
    save_user_to_db({
        'user_id': user_id,
        'username': query.from_user.username,
        'first_name': query.from_user.first_name,
        'last_name': query.from_user.last_name,
        'is_premium': is_premium,
        'is_admin': is_admin
    })
    
    data = query.data
    
    if data == 'help':
        help_text = """📋 **Ayuda del Bot**

🔗 **Copia Simple:**
Envía un enlace de canal como:
`https://t.me/canal/123`

🎯 **Formatos Soportados:**
• Texto
• Imágenes
• Videos
• Documentos
• Audio
• Stickers
• GIFs

⚠️ **Importante:**
- Respeta los derechos de autor
- Usa responsablemente
- El userbot debe estar configurado"""
        
        keyboard = [[InlineKeyboardButton("🔙 Volver", callback_data='back_to_menu')]]
        
        if is_premium:
            help_text += "\n\n**Funciones Premium:**\n• Usa el botón 'Info de Canal' para ver detalles\n• Envía enlaces para copia masiva con formato:\n`[enlace] [cantidad]`"
        
        await query.edit_message_text(
            help_text, 
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    elif data == 'premium':
        if is_premium:
            # Obtener información de premium
            premium_info = db.get_premium_info(user_id)
            
            if premium_info:
                days_remaining = premium_info['days_remaining']
                expiry_date = premium_info['premium_expiry_date']
                
                text = f"""⭐ **Versión Premium Activa**

✅ Funciones disponibles:
• Copia de canales públicos y privados
• Copia masiva de contenido (sin límite de mensajes)
• Configuración de canal destino
• Filtros de contenido personalizados
• Información detallada de canales

📅 **Tu Suscripción:**
• Expira el: {expiry_date.strftime('%d/%m/%Y')}
• Días restantes: **{days_remaining} días**

🚀 ¡Disfruta de todas las funciones!"""
            else:
                text = """⭐ **Versión Premium Activa**

✅ Funciones disponibles:
• Copia de canales públicos y privados
• Copia masiva de contenido
• Configuración de canal destino
• Filtros de contenido personalizados
• Información detallada de canales

🚀 ¡Disfruta de todas las funciones!"""
            
            keyboard = [[InlineKeyboardButton("🔙 Volver", callback_data='back_to_menu')]]
        else:
            # Usuario gratuito - mostrar opciones incluyendo prueba gratuita
            trial_info = db.get_free_trial_info(user_id)
            trial_activated = trial_info.get('trial_activated', False)
            trial_uses_left = trial_info.get('trial_uses_left', 0)
            
            if trial_activated and trial_uses_left > 0:
                trial_section = f"\n\n🎁 **Prueba Activa:** {trial_uses_left} extracción(es) restantes"
            elif trial_activated and trial_uses_left == 0:
                trial_section = "\n\n🎁 **Prueba gratuita:** Agotada"
            else:
                trial_section = f"\n\n🎁 **¡Prueba Premium GRATIS!**\nObtén {FREE_TRIAL_USES} extracciones sin costo."
            
            text = f"""⭐ **Versión Premium**

🔓 **Desbloquea funciones adicionales:**

📱 **Acceso Completo:**
• Copiar de canales públicos y privados
• Copia masiva de contenido (sin límite de mensajes)

⚙️ **Configuración Avanzada:**
• Canal destino personalizado
• Filtros de contenido personalizados
• Información detallada de canales

💰 **Activación:**
Contacta al administrador para activar Premium con el plan que prefieras (30, 90, 365 días){trial_section}"""
            
            keyboard = [
                [InlineKeyboardButton("⭐ Ver Detalles Premium", callback_data='premium_details')],
            ]
            if not trial_activated:
                keyboard.append([InlineKeyboardButton("🎁 ¡Prueba Premium Gratis!", callback_data='free_trial_info')])
            elif trial_uses_left > 0:
                keyboard.append([InlineKeyboardButton(f"🎁 Mi Prueba ({trial_uses_left} usos)", callback_data='free_trial_info')])
            keyboard.append([InlineKeyboardButton("🔙 Volver", callback_data='back_to_menu')])
        
        await query.edit_message_text(
            text, 
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    elif data == 'premium_details':
        text = f"""⭐ **Detalles de Premium**

📋 **Comparación de Planes:**

🆓 **Versión Gratuita:**
✅ Copia de canales públicos

⭐ **Versión Premium:**
✅ Copia de canales públicos
✅ Copia de canales privados
✅ Copia masiva (sin límite, con pausas inteligentes)
✅ Configuración de canal destino
✅ Filtros de contenido personalizados
✅ Información detallada de canales

💳 **Activación:**
Para activar Premium, envía tu ID al administrador:
🆔 Tu ID: `{user_id}`

El administrador configurará los días de premium que necesites."""
        
        keyboard = [
            [InlineKeyboardButton("💳 Contactar Admin", url='https://t.me/m/jaRYjhuaNGM5')],
            [InlineKeyboardButton("🔙 Volver", callback_data='premium')]
        ]
        
        await query.edit_message_text(
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    elif data == 'activate_premium':
        text = ("💳 *Activar Premium*\n\n"
               f"Para activar Premium, contacta al administrador con la siguiente información:\n\n"
               f"👤 Usuario: {query.from_user.first_name}\n"
               f"🆔 ID: `{query.from_user.id}`\n"
               f"📱 Username: @{query.from_user.username or 'Sin username'}\n\n"
               f"💰 Precio: $5/mes")
        
        await query.edit_message_text(
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Volver", callback_data='premium')]])
        )
    
    elif data == 'free_trial_info':
        # Mostrar información sobre la prueba gratuita
        trial_info = db.get_free_trial_info(user_id)
        
        if is_premium:
            await query.answer("✅ ¡Ya tienes Premium activo!", show_alert=True)
            return
        
        if trial_info.get('trial_activated', False):
            uses_left = trial_info.get('trial_uses_left', 0)
            if uses_left > 0:
                # Trial activo con usos disponibles
                text = f"""🎁 **Tu Prueba Premium Activa**

✅ Tienes **{uses_left} extracción(es) premium** disponibles.

🔓 **Con tus usos restantes puedes:**
• Extraer de canales con restricciones
• Acceso a canales privados (con enlace de invitación)
• Extracción masiva de mensajes
• Todas las funciones Premium

📌 **Para usar:** Simplemente envía el enlace del canal y el bot usará automáticamente tu prueba.

💡 Cuando se agoten tus {FREE_TRIAL_USES} usos, necesitarás Premium para continuar."""
                keyboard = [
                    [InlineKeyboardButton("⭐ Obtener Premium Completo", callback_data='premium_details')],
                    [InlineKeyboardButton("🔙 Menú Principal", callback_data='back_to_menu')]
                ]
            else:
                # Trial usado completamente
                text = f"""🎁 **Prueba Gratuita Agotada**

Has utilizado tus **{FREE_TRIAL_USES} extracciones gratuitas** de prueba.

🔒 Para continuar usando las funciones premium necesitas:
• Acceso a canales privados
• Extracción masiva
• Sin restricciones

⭐ **¡Obtén Premium y desbloquea todo!**
Contacta al administrador para activar tu suscripción."""
                keyboard = [
                    [InlineKeyboardButton("⭐ Ver Planes Premium", callback_data='premium_details')],
                    [InlineKeyboardButton("🔙 Menú Principal", callback_data='back_to_menu')]
                ]
        else:
            # Trial no activado - mostrar oferta
            text = f"""🎁 **¡Prueba Premium GRATIS!**

🚀 Descubre todo el poder del bot sin pagar nada

✨ **Obtén {FREE_TRIAL_USES} extracciones Premium gratuitas:**
• ✅ Extraer de canales privados y restringidos
• ✅ Extraer desde enlaces de invitación
• ✅ Extracción masiva de mensajes
• ✅ Todas las funciones Premium

━━━━━━━━━━━━━━━━━━━━━━
📌 **ÚNICO REQUISITO:**
Únete a nuestro canal oficial para activar tu prueba gratuita.

👉 **Canal:** {FREE_TRIAL_REQUIRED_CHANNEL}

Es rápido, fácil y completamente gratuito.
━━━━━━━━━━━━━━━━━━━━━━

⚠️ **Importante:** Esta prueba es **solo una vez** y te da exactamente **{FREE_TRIAL_USES} extracciones premium**. Una vez agotadas, necesitarás Premium para continuar.

🔥 **¡No pierdas esta oportunidad!** Únete al canal y activa tu prueba ahora."""
            keyboard = [
                [InlineKeyboardButton("📢 Unirme al Canal", url=FREE_TRIAL_REQUIRED_CHANNEL)],
                [InlineKeyboardButton("✅ Ya me uní - Activar Prueba", callback_data='activate_free_trial')],
                [InlineKeyboardButton("⭐ Prefiero Premium Completo", callback_data='premium_details')],
                [InlineKeyboardButton("🔙 Volver", callback_data='back_to_menu')]
            ]
        
        await query.edit_message_text(
            text,
            parse_mode='Markdown',
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif data == 'activate_free_trial':
        # Intentar activar la prueba gratuita
        if is_premium:
            await query.answer("✅ ¡Ya tienes Premium activo!", show_alert=True)
            return
        
        trial_info = db.get_free_trial_info(user_id)
        
        if trial_info.get('trial_activated', False):
            uses_left = trial_info.get('trial_uses_left', 0)
            if uses_left > 0:
                await query.answer(f"✅ ¡Tu prueba ya está activa! Te quedan {uses_left} usos.", show_alert=True)
            else:
                await query.answer("❌ Ya usaste tu prueba gratuita. Obtén Premium para continuar.", show_alert=True)
            return
        
        # Verificar que el usuario esté en el canal requerido
        await query.answer("🔍 Verificando tu membresía en el canal...", show_alert=False)
        
        is_member = await check_user_in_channel(context.bot, user_id)
        
        if not is_member:
            text = f"""❌ **No estás en el canal requerido**

Para activar tu prueba gratuita, primero debes unirte a nuestro canal:

👉 **{FREE_TRIAL_REQUIRED_CHANNEL}**

1️⃣ Toca el botón "Unirme al Canal"
2️⃣ Únete al canal
3️⃣ Regresa y toca "Ya me uní - Activar Prueba"

⚠️ El bot verifica automáticamente tu membresía."""
            keyboard = [
                [InlineKeyboardButton("📢 Unirme al Canal", url=FREE_TRIAL_REQUIRED_CHANNEL)],
                [InlineKeyboardButton("✅ Ya me uní - Activar Prueba", callback_data='activate_free_trial')],
                [InlineKeyboardButton("🔙 Volver", callback_data='free_trial_info')]
            ]
            await query.edit_message_text(
                text,
                parse_mode='Markdown',
                disable_web_page_preview=True,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
        
        # Usuario está en el canal - activar trial
        success = db.activate_free_trial(user_id)
        
        if success:
            text = f"""🎉 **¡Prueba Premium Activada!**

✅ ¡Enhorabuena! Ahora tienes **{FREE_TRIAL_USES} extracciones premium gratuitas**.

🔓 **Funciones desbloqueadas:**
• Extraer de canales privados y restringidos
• Acceder con enlaces de invitación
• Extracción masiva de mensajes
• Todas las funciones Premium

📌 **Cómo usarlas:**
Simplemente envía el enlace de cualquier canal privado o con restricciones, ¡el bot lo manejará automáticamente!

💡 **Recuerda:** Solo tienes **{FREE_TRIAL_USES} extracciones**. Úsalas sabiamente.

⭐ Cuando se agoten, considera obtener **Premium** para acceso ilimitado."""
            keyboard = [
                [InlineKeyboardButton("🚀 ¡Empezar a extraer!", callback_data='back_to_menu')],
                [InlineKeyboardButton("⭐ Ver Planes Premium", callback_data='premium_details')]
            ]
            await query.edit_message_text(
                text,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await query.answer("❌ Error al activar la prueba. Intenta nuevamente.", show_alert=True)
        
    elif data == 'status':
        # Verificar estado del cliente
        client_status = "🟢 Conectado" if copy_bot.is_initialized and copy_bot.client and copy_bot.client.is_connected() else "🔴 Desconectado"
        config_status = "✅ Configurado" if copy_bot.config.is_configured() else "❌ Sin configurar"
        
        # Obtener info del trial
        trial_info = db.get_free_trial_info(user_id)
        trial_activated = trial_info.get('trial_activated', False)
        trial_uses_left = trial_info.get('trial_uses_left', 0)
        is_trial_active = trial_activated and trial_uses_left > 0
        
        if is_premium:
            plan_text = "⭐ Premium"
        elif is_trial_active:
            plan_text = f"🎁 Prueba Gratuita ({trial_uses_left} usos restantes)"
        elif trial_activated and trial_uses_left == 0:
            plan_text = "🆓 Gratuito (prueba agotada)"
        else:
            plan_text = "🆓 Gratuito"
        
        can_premium_features = is_premium or is_trial_active
        
        status_text = f"""📊 **Estado de Usuario**

👤 Usuario: {query.from_user.first_name}
🆔 ID: {query.from_user.id}
📋 Plan: {plan_text}
🔌 Cliente: {client_status}
⚙️ Configuración: {config_status}

📈 **Funciones Disponibles:**
{'✅' if copy_bot.is_initialized else '❌'} Canales públicos
{'✅' if can_premium_features and copy_bot.is_initialized else '❌'} Canales privados
{'✅' if can_premium_features and copy_bot.is_initialized else '❌'} Copia masiva
{'✅' if can_premium_features and copy_bot.is_initialized else '❌'} Info detallada"""

        status_keyboard = [[InlineKeyboardButton("🔙 Volver", callback_data='back_to_menu')]]
        if not is_premium and not trial_activated:
            status_keyboard.insert(0, [InlineKeyboardButton("🎁 ¡Prueba Premium Gratis!", callback_data='free_trial_info')])

        await query.edit_message_text(
            status_text, 
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(status_keyboard)
        )
        

        
    elif data == 'config_userbot':
        if not is_admin:
            await query.answer("⚠️ Solo el administrador puede configurar el userbot", show_alert=True)
            return
        
        config_text = "⚙️ **Configuración del Userbot**\n\n"
        
        if copy_bot.config.is_configured():
            api_id = copy_bot.config.get('api_id', 'No configurado')
            phone = copy_bot.config.get('phone_number', 'No configurado')
            session_status = "✅ Activa" if copy_bot.config.get('session_string') else "❌ No iniciada"
            
            config_text += f"**Estado actual:**\n"
            config_text += f"• API ID: `{api_id}`\n"
            config_text += f"• Teléfono: `{phone}`\n"
            config_text += f"• Sesión: {session_status}\n\n"
            
            keyboard = [
                [InlineKeyboardButton("🔄 Reconfigurar", callback_data='reconfig_userbot')],
                [InlineKeyboardButton("🔌 Probar Conexión", callback_data='test_connection')],
                [InlineKeyboardButton("🔙 Volver", callback_data='back_to_menu')]
            ]
        else:
            config_text += "El userbot no está configurado.\n\n"
            config_text += "Para configurarlo, necesitarás:\n"
            config_text += "• API ID de Telegram\n"
            config_text += "• API Hash de Telegram\n"
            config_text += "• Número de teléfono\n"
            config_text += "• Código de verificación (se enviará)\n\n"
            config_text += "Obtén tus credenciales en: https://my.telegram.org"
            
            keyboard = [
                [InlineKeyboardButton("▶️ Iniciar Configuración", callback_data='start_config')],
                [InlineKeyboardButton("🔙 Volver", callback_data='back_to_menu')]
            ]
        
        await query.edit_message_text(
            config_text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard),
            disable_web_page_preview=True
        )
        
    elif data == 'start_config':
        if not is_admin:
            await query.answer("⚠️ Solo el administrador puede configurar el userbot", show_alert=True)
            return
        
        context.user_data['configuring_userbot'] = True
        await query.edit_message_text(
            "🔧 **Paso 1: API ID**\n\n"
            "Por favor, envía tu API ID de Telegram.\n"
            "Lo puedes obtener en: https://my.telegram.org",
            parse_mode='Markdown',
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data='cancel_config_btn')]])
        )
        return CONFIG_API_ID
        
    elif data == 'test_connection':
        if not is_admin:
            await query.answer("⚠️ Solo el administrador puede probar la conexión", show_alert=True)
            return
        
        await query.edit_message_text("🔄 Probando conexión...", parse_mode='Markdown')
        
        success = await copy_bot.initialize_client(force_recreate=True)
        
        if success:
            text = "✅ **Conexión Exitosa**\n\nEl userbot está funcionando correctamente."
        else:
            text = "❌ **Error de Conexión**\n\nNo se pudo conectar el userbot. Verifica la configuración."
        
        keyboard = [[InlineKeyboardButton("🔙 Volver", callback_data='config_userbot')]]
        await query.edit_message_text(
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    elif data == 'reconfig_userbot':
        if not is_admin:
            await query.answer("⚠️ Solo el administrador puede reconfigurar el userbot", show_alert=True)
            return
        
        # Limpiar configuración anterior
        copy_bot.config.config = {}
        copy_bot.config.save_config()
        copy_bot.is_initialized = False
        
        await query.edit_message_text(
            "🔄 **Reconfigurando Userbot**\n\n"
            "Configuración anterior eliminada.\n"
            "Iniciando nueva configuración...",
            parse_mode='Markdown'
        )
        
        await asyncio.sleep(1)
        
        context.user_data['configuring_userbot'] = True
        await query.edit_message_text(
            "🔧 **Paso 1: API ID**\n\n"
            "Por favor, envía tu API ID de Telegram.\n"
            "Lo puedes obtener en: https://my.telegram.org",
            parse_mode='Markdown',
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data='cancel_config_btn')]])
        )
        return CONFIG_API_ID
        
    elif data == 'admin_premium':
        if not is_admin:
            await query.answer("⚠️ Solo el administrador puede gestionar usuarios premium", show_alert=True)
            return
        
        # Obtener estadísticas
        stats = db.get_stats()
        premium_users = db.get_premium_users()
        
        admin_text = f"""👥 **Panel de Administración - Premium**

📊 **Estadísticas:**
• Total de usuarios: {stats['total_users']}
• Usuarios Premium: {stats['premium_users']}
• Usuarios Gratuitos: {stats['free_users']}

🔧 **Acciones disponibles:**"""
        
        keyboard = [
            [InlineKeyboardButton("➕ Otorgar Premium", callback_data='admin_grant_premium')],
            [InlineKeyboardButton("➖ Revocar Premium", callback_data='admin_revoke_premium')],
            [InlineKeyboardButton("📋 Ver Usuarios Premium", callback_data='admin_list_premium')],
            [InlineKeyboardButton("🔙 Volver", callback_data='back_to_menu')]
        ]
        
        await query.edit_message_text(
            admin_text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    elif data == 'admin_grant_premium':
        if not is_admin:
            await query.answer("⚠️ Solo el administrador puede gestionar usuarios premium", show_alert=True)
            return
        
        context.user_data['admin_action'] = 'grant_premium'
        context.user_data['grant_premium_step'] = 'awaiting_user_id'
        await query.edit_message_text(
            "➕ **Otorgar Premium**\n\n"
            "**Paso 1 de 2:** Envía el ID o @username del usuario al que deseas otorgar Premium.\n\n"
            "📌 **Ejemplo:** `123456789` o `@usuario`",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data='admin_premium')]])
        )
        
    elif data == 'admin_revoke_premium':
        if not is_admin:
            await query.answer("⚠️ Solo el administrador puede gestionar usuarios premium", show_alert=True)
            return
        
        context.user_data['admin_action'] = 'revoke_premium'
        await query.edit_message_text(
            "➖ **Revocar Premium**\n\n"
            "Envía el ID o @username del usuario al que deseas revocar Premium.\n\n"
            "📌 **Ejemplo:** `123456789` o `@usuario`",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data='admin_premium')]])
        )
        
    elif data == 'admin_list_premium':
        if not is_admin:
            await query.answer("⚠️ Solo el administrador puede gestionar usuarios premium", show_alert=True)
            return
        
        # Obtener todos los usuarios
        all_users = db.get_all_users()
        premium_users_list = [u for u in all_users if u.get('is_premium', False)]
        
        if not premium_users_list:
            list_text = "📋 **Usuarios Premium**\n\nNo hay usuarios con Premium actualmente."
        else:
            list_text = "📋 **Usuarios Premium**\n\n"
            for user in premium_users_list:
                username = user.get('username', 'Sin username')
                first_name = user.get('first_name', 'Sin nombre')
                user_id = user.get('user_id')
                
                # Obtener información de expiración
                expiry_date = user.get('premium_expiry_date')
                if expiry_date:
                    if isinstance(expiry_date, str):
                        expiry_date = datetime.fromisoformat(expiry_date)
                    days_remaining = (expiry_date - datetime.utcnow()).days
                    expiry_str = f"\n  📅 Expira: {expiry_date.strftime('%d/%m/%Y')} ({days_remaining} días)"
                else:
                    expiry_str = "\n  📅 Sin fecha de expiración"
                
                list_text += f"• {first_name} (@{username})\n  🆔 ID: `{user_id}`{expiry_str}\n\n"
        
        keyboard = [[InlineKeyboardButton("🔙 Volver", callback_data='admin_premium')]]
        await query.edit_message_text(
            list_text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    elif data == 'admin_broadcast':
        if not is_admin:
            await query.answer("⚠️ Solo el administrador puede enviar broadcasts", show_alert=True)
            return
        
        # Obtener estadísticas de usuarios
        stats = db.get_stats()
        
        broadcast_text = f"""📢 **Panel de Broadcast**

📊 **Alcance:**
• Total de usuarios: {stats['total_users']}
• Usuarios Premium: {stats['premium_users']}
• Usuarios Gratuitos: {stats['free_users']}

💬 **Enviar Mensaje:**
Selecciona el grupo de usuarios al que deseas enviar el mensaje."""
        
        keyboard = [
            [InlineKeyboardButton("📢 Enviar a Todos", callback_data='broadcast_all')],
            [InlineKeyboardButton("⭐ Enviar a Premium", callback_data='broadcast_premium')],
            [InlineKeyboardButton("🆓 Enviar a Gratuitos", callback_data='broadcast_free')],
            [InlineKeyboardButton("🔙 Volver", callback_data='back_to_menu')]
        ]
        
        await query.edit_message_text(
            broadcast_text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    elif data.startswith('broadcast_'):
        if not is_admin:
            await query.answer("⚠️ Solo el administrador puede enviar broadcasts", show_alert=True)
            return
        
        broadcast_type = data.replace('broadcast_', '')
        context.user_data['admin_action'] = 'broadcast'
        context.user_data['broadcast_type'] = broadcast_type
        
        type_name = {
            'all': 'todos los usuarios',
            'premium': 'usuarios Premium',
            'free': 'usuarios Gratuitos'
        }.get(broadcast_type, 'usuarios')
        
        await query.edit_message_text(
            f"📢 **Broadcast a {type_name}**\n\n"
            f"Envía el mensaje que deseas transmitir.\n\n"
            f"**Puedes enviar:**\n"
            f"• Texto con formato Markdown\n"
            f"• Imágenes con caption\n"
            f"• Videos con caption\n"
            f"• Documentos\n"
            f"• Stickers\n"
            f"• Mensajes con botones inline\n\n"
            f"**Para botones inline:**\n"
            f"Incluye al final del mensaje:\n"
            f"`[BUTTON:Texto|URL]`",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data='admin_broadcast')]])
        )
        
    elif data.startswith('cancel_download_'):
        # Extraer user_id del callback data
        try:
            target_user_id = int(data.split('_')[-1])
            
            # Verificar que sea el mismo usuario
            if user_id != target_user_id:
                await query.answer("⚠️ No puedes cancelar operaciones de otros usuarios", show_alert=True)
                return
            
            # Marcar cancelación en el contexto de la aplicación
            if not hasattr(context.application, 'cancel_flags'):
                context.application.cancel_flags = {}
            
            context.application.cancel_flags[user_id] = True
            
            # Buscar la tarea en background del usuario y cancelarla inmediatamente
            if hasattr(context.application, 'user_tasks') and user_id in context.application.user_tasks:
                task = context.application.user_tasks[user_id]
                if not task.done():
                    task.cancel()
                    logger.info(f"🛑 Tarea del usuario {user_id} cancelada inmediatamente")
            
            await query.edit_message_text(
                "🛑 **Operación cancelada**\n\n"
                "La descarga/subida ha sido detenida inmediatamente.",
                parse_mode='Markdown'
            )
            
            logger.info(f"🛑 Usuario {user_id} canceló descarga/subida")
            
        except Exception as e:
            logger.error(f"Error procesando cancelación: {e}")
            await query.answer("❌ Error procesando cancelación", show_alert=True)
    
    elif data == 'user_config_menu':
        # CORRECCIÓN: Limpiar flag awaiting_target_channel al volver al menú
        context.user_data['awaiting_target_channel'] = False
        
        # Mostrar configuración a todos, pero solo permitir editar a premium
        config_text = "⚙️ **Configuración de Extracción**\n\n"
        
        if not is_premium:
            config_text += "⭐ **Esta función requiere Premium**\n\n"
            config_text += "Con Premium podrás personalizar cómo se extraerá el contenido de los canales:\n\n"
            config_text += "**Opciones disponibles:**\n"
            config_text += "• 📺 Canal Destino - Envía automáticamente a un canal específico\n"
            config_text += "• 🎯 Filtros de Contenido - Selecciona qué tipos de contenido extraer\n\n"
            config_text += "Toca '⭐ Ver Premium' para más información."
            
            keyboard = [
                [InlineKeyboardButton("⭐ Ver Premium", callback_data='premium')],
                [InlineKeyboardButton("🔙 Volver", callback_data='back_to_menu')]
            ]
        else:
            config_text += "Personaliza cómo se extraerá el contenido de los canales.\n\n"
            config_text += "**Opciones disponibles:**\n"
            config_text += "• 📺 Canal Destino\n"
            config_text += "• 🎯 Filtros de Contenido\n\n"
            config_text += "Selecciona una opción:"
            
            keyboard = [
                [InlineKeyboardButton("📺 Configurar Canal Destino", callback_data='config_target_channel')],
                [InlineKeyboardButton("🎯 Configurar Filtros", callback_data='config_filters')],
                [InlineKeyboardButton("🔙 Volver", callback_data='back_to_menu')]
            ]
        
        await query.edit_message_text(
            config_text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif data == 'config_target_channel':
        if not is_premium:
            # Mostrar mensaje con botón para ver Premium
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("⭐ Ver Premium", callback_data='premium')],
                [InlineKeyboardButton("🔙 Volver", callback_data='user_config_menu')]
            ])
            
            await query.edit_message_text(
                "⭐ **La configuración de canal destino requiere Premium**\n\n"
                "Con esta función podrás enviar automáticamente el contenido extraído a un canal específico.\n\n"
                "Toca el botón '⭐ Ver Premium' abajo para más información.",
                parse_mode='Markdown',
                reply_markup=keyboard
            )
            return
        
        # Obtener configuración actual del usuario
        user_config = await get_user_config_from_db(user_id)
        target_channel = user_config.get('target_channel', None)
        
        # Marcar que estamos esperando configuración de canal
        context.user_data['awaiting_target_channel'] = True
        
        config_text = "📺 **Configurar Canal Destino**\n\n"
        
        if target_channel:
            config_text += f"**Canal actual:** `{target_channel}`\n\n"
            config_text += "Puedes:\n"
            config_text += "• Enviar un nuevo canal para reemplazarlo\n"
            config_text += "• Tocar '🗑️ Eliminar Canal' para enviar al chat privado\n\n"
        
        config_text += "**Para configurar un nuevo canal:**\n"
        config_text += "Envía el ID o @username del canal donde deseas que se envíe automáticamente el contenido extraído.\n\n"
        config_text += "**Formatos aceptados:**\n"
        config_text += "• `@micanal`\n"
        config_text += "• `-1001234567890` (ID con prefijo -100)\n\n"
        config_text += "⚠️ **Solo** se aceptan IDs que comiencen con `-100` o usernames con `@`.\n\n"
        config_text += "**Importante:** El bot debe ser administrador del canal destino."
        
        keyboard = []
        if target_channel:
            keyboard.append([InlineKeyboardButton("🗑️ Eliminar Canal", callback_data='delete_target_channel')])
        keyboard.append([InlineKeyboardButton("🔙 Cancelar", callback_data='user_config_menu')])
        
        await query.edit_message_text(
            config_text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif data == 'config_filters':
        if not is_premium:
            # Mostrar mensaje con botón para ver Premium
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("⭐ Ver Premium", callback_data='premium')],
                [InlineKeyboardButton("🔙 Volver", callback_data='user_config_menu')]
            ])
            
            await query.edit_message_text(
                "⭐ **La configuración de filtros requiere Premium**\n\n"
                "Con esta función podrás seleccionar qué tipos de contenido extraer en las copias masivas:\n"
                "• 🎥 Videos\n"
                "• 📸 Fotos\n"
                "• 📎 Documentos\n"
                "• 🎵 Audio\n"
                "• 📝 Texto\n"
                "• 🎭 Stickers\n\n"
                "Toca el botón '⭐ Ver Premium' abajo para más información.",
                parse_mode='Markdown',
                reply_markup=keyboard
            )
            return
        
        # Obtener configuración actual del usuario desde MongoDB
        user_config = await get_user_config_from_db(user_id)
        filters = user_config.get('filters', {
            'videos': True, 'photos': True, 'documents': True,
            'audio': True, 'text': True, 'stickers': True
        })
        
        config_text, keyboard = _build_filter_display(filters)
        await query.edit_message_text(
            config_text, parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif data.startswith('toggle_filter_'):
        if not is_premium:
            await query.answer("⭐ Esta función requiere Premium", show_alert=True)
            return
        
        # Extraer el tipo de filtro
        filter_type = data.replace('toggle_filter_', '')
        
        # Obtener configuración actual de forma atómica
        user_config = await get_user_config_from_db(user_id)
        filters = user_config.get('filters', {
            'videos': True,
            'photos': True,
            'documents': True,
            'audio': True,
            'text': True,
            'stickers': True
        })
        
        # Toggle el filtro - obtener valor actual y cambiar
        current_value = filters.get(filter_type, True)
        new_value = not current_value
        
        # Guardar en MongoDB usando método atómico
        db.update_user_filter(user_id, filter_type, new_value)
        
        # Actualizar el diccionario local para reflejar el cambio
        filters[filter_type] = new_value
        
        # Actualizar el mensaje con el nuevo estado usando helper reutilizable
        config_text, keyboard = _build_filter_display(filters)
        await query.edit_message_text(
            config_text, parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        status = "activado" if filters[filter_type] else "desactivado"
        await query.answer(f"✅ Filtro de {FILTER_LABELS[filter_type]} {status}", show_alert=False)
    
    elif data == 'delete_target_channel':
        if not is_premium:
            await query.answer("⭐ Esta función requiere Premium", show_alert=True)
            return
        
        # Limpiar flag awaiting_target_channel
        context.user_data['awaiting_target_channel'] = False
        
        # CORRECCIÓN: Usar update directo en MongoDB para evitar problemas de lectura-escritura
        try:
            success = db.update_user_target_channel(user_id, None)
            
            if not success:
                raise Exception("update_user_target_channel retornó False")
            
            logger.info(f"✅ Canal destino eliminado correctamente para usuario {user_id}")
            
            await query.edit_message_text(
                "✅ **Canal destino eliminado**\n\n"
                "El contenido extraído ahora se enviará a tu chat privado.\n\n"
                "Puedes volver a configurar un canal cuando lo desees.",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Volver al Menú", callback_data='user_config_menu')]])
            )
            
            await query.answer("✅ Canal destino eliminado correctamente", show_alert=False)
            
        except Exception as e:
            logger.error(f"❌ Error eliminando canal destino para usuario {user_id}: {e}")
            await query.edit_message_text(
                "❌ **Error al eliminar canal**\n\n"
                "Hubo un problema al eliminar la configuración. Intenta nuevamente.",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Volver al Menú", callback_data='user_config_menu')]])
            )
    
    elif data == 'back_to_menu':
        # CORRECCIÓN: Limpiar flags de configuración al volver al menú
        context.user_data['awaiting_target_channel'] = False
        
        userbot_status = "✅ Conectado" if copy_bot.is_initialized else "⚠️ No configurado"
        
        welcome_text = (
            f"👋 ¡Hola {query.from_user.first_name}!\n\n"
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

        keyboard = get_main_menu_keyboard(is_premium, is_admin, user_id)
        await query.edit_message_text(welcome_text, parse_mode='Markdown', reply_markup=keyboard)

