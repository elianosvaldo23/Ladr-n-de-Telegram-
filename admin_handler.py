"""Admin action handlers - grant/revoke premium, broadcast.

Processes text messages while ``context.user_data['admin_action']`` is set.
Supports:
  - ``broadcast``     – send a message to all / premium / free users.
  - ``grant_premium`` – two-step flow (user-ID → days).
  - ``revoke_premium``– single-step revocation by user-ID / @username.
"""

import re
import asyncio
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from state import db
from config import ADMIN_ID

logger = logging.getLogger(__name__)

async def handle_admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Route admin text messages to the appropriate sub-handler based on
    ``context.user_data['admin_action']``.

    Supported actions:
      - ``broadcast``      -- send a message to all / premium / free users.
      - ``grant_premium``  -- two-step (user-ID, then days).
      - ``revoke_premium`` -- single-step revocation by user-ID / @username.
    """
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⚠️ Solo el administrador puede ejecutar esta acción")
        context.user_data.clear()
        return
    
    action = context.user_data.get('admin_action')
    
    if action == 'broadcast':
        # Manejar broadcast EN SEGUNDO PLANO para no bloquear el bot
        broadcast_type = context.user_data.get('broadcast_type', 'all')
        
        # Obtener usuarios según el tipo
        all_users = db.get_all_users()
        
        if broadcast_type == 'premium':
            target_users = [u for u in all_users if u.get('is_premium', False)]
        elif broadcast_type == 'free':
            target_users = [u for u in all_users if not u.get('is_premium', False)]
        else:  # all
            target_users = all_users
        
        if not target_users:
            await update.message.reply_text("❌ No hay usuarios en el grupo seleccionado.")
            context.user_data.clear()
            return
        
        # Extraer botones si existen
        text = update.message.text or update.message.caption or ""
        reply_markup = None
        
        # Buscar patrón de botones: [BUTTON:Texto|URL]
        button_pattern = r'\[BUTTON:(.*?)\|(.*?)\]'
        buttons = re.findall(button_pattern, text)
        
        if buttons:
            # Crear teclado inline
            keyboard = [[InlineKeyboardButton(btn_text, url=btn_url)] for btn_text, btn_url in buttons]
            reply_markup = InlineKeyboardMarkup(keyboard)
            # Eliminar los marcadores de botones del texto
            text = re.sub(button_pattern, '', text).strip()
        
        # Enviar mensaje de confirmación
        type_name = {
            'all': 'todos los usuarios',
            'premium': 'usuarios Premium',
            'free': 'usuarios Gratuitos'
        }.get(broadcast_type, 'usuarios')
        
        status_msg = await update.message.reply_text(
            f"📢 **Enviando broadcast a {type_name} en segundo plano...**\n\n"
            f"👥 Total de destinatarios: {len(target_users)}\n"
            f"⏳ Progreso: 0/{len(target_users)}\n\n"
            f"💡 El bot sigue funcionando normalmente mientras se envía.",
            parse_mode='Markdown'
        )
        
        # Capturar datos necesarios del mensaje antes de limpiar context
        # (el contexto puede cambiar cuando se ejecute la tarea en background)
        broadcast_photo = update.message.photo[-1].file_id if update.message.photo else None
        broadcast_video = update.message.video.file_id if update.message.video else None
        broadcast_document = update.message.document.file_id if update.message.document else None
        broadcast_sticker = update.message.sticker.file_id if update.message.sticker else None
        broadcast_text = text
        broadcast_reply_markup = reply_markup
        bot_instance = context.bot
        
        context.user_data.clear()
        
        # Ejecutar broadcast en segundo plano con asyncio.create_task
        async def _run_broadcast():
            """Tarea en segundo plano para enviar broadcast sin bloquear el bot"""
            success_count = 0
            fail_count = 0
            
            try:
                for idx, user in enumerate(target_users):
                    try:
                        uid = user['user_id']
                        
                        # Enviar según el tipo de contenido
                        if broadcast_photo:
                            await bot_instance.send_photo(
                                chat_id=uid,
                                photo=broadcast_photo,
                                caption=broadcast_text if broadcast_text else None,
                                parse_mode='Markdown',
                                reply_markup=broadcast_reply_markup
                            )
                        elif broadcast_video:
                            await bot_instance.send_video(
                                chat_id=uid,
                                video=broadcast_video,
                                caption=broadcast_text if broadcast_text else None,
                                parse_mode='Markdown',
                                reply_markup=broadcast_reply_markup
                            )
                        elif broadcast_document:
                            await bot_instance.send_document(
                                chat_id=uid,
                                document=broadcast_document,
                                caption=broadcast_text if broadcast_text else None,
                                parse_mode='Markdown',
                                reply_markup=broadcast_reply_markup
                            )
                        elif broadcast_sticker:
                            await bot_instance.send_sticker(
                                chat_id=uid,
                                sticker=broadcast_sticker
                            )
                            if broadcast_text:
                                await bot_instance.send_message(
                                    chat_id=uid,
                                    text=broadcast_text,
                                    parse_mode='Markdown',
                                    reply_markup=broadcast_reply_markup
                                )
                        else:
                            # Texto simple
                            await bot_instance.send_message(
                                chat_id=uid,
                                text=broadcast_text,
                                parse_mode='Markdown',
                                reply_markup=broadcast_reply_markup
                            )
                        
                        success_count += 1
                        
                        # Actualizar progreso cada 10 usuarios
                        if (idx + 1) % 10 == 0 or (idx + 1) == len(target_users):
                            try:
                                await status_msg.edit_text(
                                    f"📢 **Enviando broadcast a {type_name}...**\n\n"
                                    f"👥 Total de destinatarios: {len(target_users)}\n"
                                    f"✅ Enviados: {success_count}\n"
                                    f"❌ Fallidos: {fail_count}\n"
                                    f"⏳ Progreso: {idx + 1}/{len(target_users)}\n\n"
                                    f"💡 El bot sigue funcionando normalmente.",
                                    parse_mode='Markdown'
                                )
                            except Exception:
                                pass  # Ignorar errores de edición
                        
                        # Pequeña pausa para evitar rate limits
                        await asyncio.sleep(0.05)
                        
                    except Exception as e:
                        fail_count += 1
                        logger.warning(f"Error enviando broadcast a usuario {uid}: {e}")
                
                # Mensaje final
                try:
                    await status_msg.edit_text(
                        f"✅ **Broadcast completado**\n\n"
                        f"👥 Total de destinatarios: {len(target_users)}\n"
                        f"✅ Enviados exitosamente: {success_count}\n"
                        f"❌ Fallidos: {fail_count}\n\n"
                        f"Usa /start para volver al menú principal.",
                        parse_mode='Markdown'
                    )
                except Exception:
                    pass
                    
            except asyncio.CancelledError:
                logger.warning("Broadcast cancelado")
                try:
                    await status_msg.edit_text(
                        f"🛑 **Broadcast cancelado**\n\n"
                        f"✅ Enviados: {success_count}\n"
                        f"❌ Fallidos: {fail_count}",
                        parse_mode='Markdown'
                    )
                except Exception:
                    pass
            except Exception as e:
                logger.error(f"Error en broadcast en segundo plano: {e}")
                try:
                    await status_msg.edit_text(
                        f"❌ **Error en broadcast**\n\n"
                        f"✅ Enviados antes del error: {success_count}\n"
                        f"❌ Error: {str(e)[:200]}",
                        parse_mode='Markdown'
                    )
                except Exception:
                    pass
        
        # Crear tarea en segundo plano
        broadcast_task = asyncio.create_task(_run_broadcast())
        
        # Almacenar referencia fuerte para evitar garbage collection
        if not hasattr(context.application, 'background_tasks'):
            context.application.background_tasks = set()
        context.application.background_tasks.add(broadcast_task)
        
        def broadcast_done(t):
            try:
                context.application.background_tasks.discard(t)
                if t.exception():
                    logger.error(f"Broadcast task falló: {t.exception()}")
            except Exception:
                pass
        
        broadcast_task.add_done_callback(broadcast_done)
        logger.info(f"📢 Broadcast iniciado en segundo plano para {len(target_users)} usuarios")
        return
    
    # Resto del código para grant_premium y revoke_premium
    text = update.message.text.strip()
    
    if action == 'grant_premium':
        step = context.user_data.get('grant_premium_step', 'awaiting_user_id')
        
        if step == 'awaiting_user_id':
            # Paso 1: Validar y guardar el ID del usuario
            try:
                # Intentar extraer ID numérico o username
                if text.startswith('@'):
                    # Es un username - buscar en la base de datos
                    username_clean = text[1:]  # Remover @
                    user_found = db.get_user_by_username(username_clean)
                    
                    if user_found:
                        target_user_id = user_found['user_id']
                        logger.info(f"Usuario encontrado por username @{username_clean}: ID {target_user_id}")
                    else:
                        await update.message.reply_text(
                            f"❌ **Usuario no encontrado**\n\n"
                            f"No se encontró ningún usuario con el username `{text}` en la base de datos.\n\n"
                            f"Verifica que:\n"
                            f"• El username sea correcto\n"
                            f"• El usuario haya interactuado con el bot al menos una vez (enviar /start)\n\n"
                            f"También puedes usar el ID numérico del usuario.\n\n"
                            f"Envía el ID o @username nuevamente.",
                            parse_mode='Markdown',
                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data='admin_premium')]])
                        )
                        return
                else:
                    # Es un ID numérico
                    target_user_id = int(text)
                
                context.user_data['target_user_id'] = target_user_id
                context.user_data['grant_premium_step'] = 'awaiting_days'
                
                # Mostrar info del usuario si existe
                user_info = db.get_user(target_user_id)
                user_display = ""
                if user_info:
                    name = user_info.get('first_name', '')
                    uname = user_info.get('username', '')
                    user_display = f"\n👤 Nombre: {name}"
                    if uname:
                        user_display += f"\n📛 Username: @{uname}"
                
                await update.message.reply_text(
                    f"✅ Usuario identificado correctamente.\n"
                    f"🆔 ID: `{target_user_id}`{user_display}\n\n"
                    "**Paso 2 de 2:** ¿Por cuántos días deseas otorgar Premium?\n\n"
                    "📌 **Ejemplos:**\n"
                    "• `30` - Un mes\n"
                    "• `90` - Tres meses\n"
                    "• `365` - Un año\n\n"
                    "Envía el número de días.",
                    parse_mode='Markdown',
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data='admin_premium')]])
                )
                return
                
            except ValueError:
                await update.message.reply_text(
                    "❌ Formato inválido. Debe ser un ID numérico o @username.\n\nIntenta nuevamente.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data='admin_premium')]])
                )
                return
        
        elif step == 'awaiting_days':
            # Paso 2: Validar días y otorgar premium
            try:
                days = int(text)
                if days <= 0:
                    raise ValueError("Días debe ser positivo")
                
                target_user_id = context.user_data.get('target_user_id')
                
                # Verificar si el usuario existe en la BD
                user = db.get_user(target_user_id)
                if not user:
                    # Crear usuario si no existe
                    db.save_user({
                        'user_id': target_user_id,
                        'is_premium': True
                    })
                
                # Otorgar premium con días especificados
                success = db.set_user_premium(target_user_id, True, days)
                
                if success:
                    expiry_date = datetime.utcnow() + timedelta(days=days)
                    
                    # Obtener info del usuario para mostrar
                    user_info_display = db.get_user(target_user_id)
                    user_name_display = ""
                    if user_info_display:
                        name = user_info_display.get('first_name', '')
                        uname = user_info_display.get('username', '')
                        if name:
                            user_name_display = f"\n👤 Nombre: {name}"
                        if uname:
                            user_name_display += f"\n📛 Username: @{uname}"
                    
                    await update.message.reply_text(
                        f"✅ **Premium Otorgado Exitosamente**\n\n"
                        f"🆔 ID: `{target_user_id}`{user_name_display}\n"
                        f"⏱️ Duración: **{days} días**\n"
                        f"📅 Expira: {expiry_date.strftime('%d/%m/%Y')}\n\n"
                        f"El usuario ahora tiene acceso a todas las funciones Premium.\n\n"
                        f"Usa /start para volver al menú principal.",
                        parse_mode='Markdown'
                    )
                    
                    # Intentar notificar al usuario
                    try:
                        await context.bot.send_message(
                            chat_id=target_user_id,
                            text=f"🎉 **¡Felicidades!**\n\n"
                                 f"Has recibido acceso **Premium por {days} días**.\n"
                                 f"📅 Tu premium expira el: {expiry_date.strftime('%d/%m/%Y')}\n\n"
                                 f"Ahora puedes acceder a todas las funciones avanzadas:\n"
                                 f"• Copiar de canales públicos y privados\n"
                                 f"• Copia masiva de contenido\n"
                                 f"• Configuración de canal destino\n"
                                 f"• Filtros de contenido personalizados\n"
                                 f"• Información detallada de canales\n\n"
                                 f"Usa /start para ver las nuevas opciones disponibles.",
                            parse_mode='Markdown'
                        )
                    except Exception as e:
                        logger.warning(f"No se pudo notificar al usuario {target_user_id}: {e}")
                else:
                    await update.message.reply_text(
                        f"❌ Error al otorgar Premium al usuario `{target_user_id}`.\n\n"
                        f"Verifica que el ID sea correcto.",
                        parse_mode='Markdown'
                    )
                
                # Limpiar datos del contexto
                context.user_data.clear()
                return
                
            except ValueError:
                await update.message.reply_text(
                    "❌ Número de días inválido. Debe ser un número positivo.\n\nIntenta nuevamente.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data='admin_premium')]])
                )
                return
    
    elif action == 'revoke_premium':
        # Validar que sea un ID numérico o @username
        try:
            if text.startswith('@'):
                # Es un username - buscar en la base de datos
                username_clean = text[1:]
                user_found = db.get_user_by_username(username_clean)
                
                if user_found:
                    target_user_id = user_found['user_id']
                    logger.info(f"Usuario encontrado por username @{username_clean}: ID {target_user_id}")
                else:
                    await update.message.reply_text(
                        f"❌ **Usuario no encontrado**\n\n"
                        f"No se encontró ningún usuario con el username `{text}` en la base de datos.\n\n"
                        f"Verifica que:\n"
                        f"• El username sea correcto\n"
                        f"• El usuario haya interactuado con el bot al menos una vez\n\n"
                        f"También puedes usar el ID numérico del usuario.\n\n"
                        f"Envía el ID o @username nuevamente.",
                        parse_mode='Markdown',
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data='admin_premium')]])
                    )
                    return
            else:
                target_user_id = int(text)
        except ValueError:
            await update.message.reply_text(
                "❌ ID inválido. Debe ser un número.\n\nIntenta nuevamente.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data='admin_premium')]])
            )
            return
        
        # Revocar premium
        success = db.set_user_premium(target_user_id, False)
        
        if success:
            await update.message.reply_text(
                f"✅ **Premium Revocado**\n\n"
                f"El usuario `{target_user_id}` ya no tiene acceso Premium.\n\n"
                f"Usa /start para volver al menú principal.",
                parse_mode='Markdown'
            )
            
            # Intentar notificar al usuario
            try:
                await context.bot.send_message(
                    chat_id=target_user_id,
                    text="ℹ️ **Actualización de Cuenta**\n\n"
                         "Tu acceso Premium ha sido desactivado.\n"
                         "Ahora tienes acceso a las funciones gratuitas.\n\n"
                         "Usa /start para más información.",
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.warning(f"No se pudo notificar al usuario {target_user_id}: {e}")
        else:
            await update.message.reply_text(
                f"❌ Error al revocar Premium del usuario `{target_user_id}`.\n\n"
                f"Verifica que el ID sea correcto.",
                parse_mode='Markdown'
            )
        
        # Limpiar datos del contexto
        context.user_data.clear()

