"""Link handler - processes Telegram links for content extraction"""

import re
import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from state import (
    db, copy_bot, is_user_premium, is_user_free_trial,
    get_free_trial_uses_left, save_user_to_db, get_user_config_from_db
)
from admin_handler import handle_admin_action
from config import ADMIN_ID, FREE_TRIAL_USES
from progress import ProgressTracker
from exceptions import FileTransferError
from strings import (
    ERR_USERBOT_NOT_CONFIGURED, ERR_USERBOT_CONNECT_FAILED,
    ERR_CHANNEL_ACCESS, ERR_MESSAGE_ID,
    ERR_TIMEOUT, ERR_CHAT_NOT_FOUND, CANCEL_SUCCESS,
    TRIAL_USED, TRIAL_EXHAUSTED,
    INVITE_JOINED, INVITE_ALREADY_MEMBER, INVITE_PENDING,
    INVITE_EXPIRED, INVITE_INVALID, BACK_TO_MENU_BTN
)

logger = logging.getLogger(__name__)

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Top-level handler for incoming text messages that may contain
    Telegram links.  Dispatches work into a background ``asyncio.Task``
    so the bot remains responsive to other users."""
    # Verificar si está configurando canal destino
    if context.user_data.get('awaiting_target_channel'):
        context.user_data['awaiting_target_channel'] = False
        
        text = update.message.text.strip()
        user_id = update.effective_user.id
        bot_username = context.bot.username or "bot"
        
        # Validar formato del canal: solo @username o ID que empiece con -100
        if text.startswith('@'):
            channel_target = text
        elif text.startswith('-100') and text[4:].isdigit() and len(text) > 4:
            channel_target = int(text)
        else:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Volver al Menú", callback_data='user_config_menu')]
            ])
            await update.message.reply_text(
                "❌ **Formato inválido**\n\n"
                "Solo se aceptan estos formatos:\n"
                "• `@micanal` (username del canal)\n"
                "• `-1001234567890` (ID que comience con -100)\n\n"
                "⚠️ Los IDs numéricos sin el prefijo `-100` no son aceptados.\n\n"
                "Envía el canal en un formato válido o toca el botón para volver.",
                parse_mode='Markdown',
                reply_markup=keyboard
            )
            # Reactivar la espera para que pueda intentar de nuevo
            context.user_data['awaiting_target_channel'] = True
            return
        
        # VERIFICAR que el bot tiene acceso de administrador al canal
        try:
            # Primero intentar obtener info del chat para verificar que existe
            chat_info = await context.bot.get_chat(chat_id=channel_target)
            
            # Luego verificar si el bot es admin
            chat_member = await context.bot.get_chat_member(
                chat_id=channel_target,
                user_id=context.bot.id
            )
            
            bot_is_admin = chat_member.status in ['administrator', 'creator']
            
            if not bot_is_admin:
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Volver al Menú", callback_data='user_config_menu')]
                ])
                await update.message.reply_text(
                    "❌ **El bot no es administrador del canal**\n\n"
                    f"📺 Canal: `{channel_target}`\n\n"
                    "Para que funcione correctamente:\n"
                    f"1. Abre el canal\n"
                    f"2. Agrega al bot `@{bot_username}` como administrador\n"
                    "3. Dale permiso de 'Publicar Mensajes'\n"
                    "4. Vuelve a enviar el ID o @username del canal\n\n"
                    "Envía el canal nuevamente cuando esté configurado.",
                    parse_mode='Markdown',
                    reply_markup=keyboard
                )
                context.user_data['awaiting_target_channel'] = True
                return
                
        except Exception as e:
            error_str = str(e).lower()
            logger.error(f"Error verificando acceso al canal {channel_target}: {e}")
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Volver al Menú", callback_data='user_config_menu')]
            ])
            
            # CORRECCIÓN: Todos los errores de get_chat/get_chat_member significan que
            # el bot NO tiene acceso al canal (no es miembro o no es admin)
            await update.message.reply_text(
                "❌ **El bot no tiene acceso a este canal**\n\n"
                f"📺 Canal: `{channel_target}`\n\n"
                "El bot necesita ser administrador del canal para poder enviar contenido.\n\n"
                "**Pasos para configurar:**\n"
                f"1. Abre el canal\n"
                f"2. Agrega al bot `@{bot_username}` como administrador\n"
                "3. Dale permiso de 'Publicar Mensajes'\n"
                "4. Vuelve aquí y envía el ID o @username nuevamente\n\n"
                "Envía el canal nuevamente o toca el botón para volver.",
                parse_mode='Markdown',
                reply_markup=keyboard
            )
            context.user_data['awaiting_target_channel'] = True
            return
        
        # CORRECCIÓN: Usar update directo en MongoDB para guardar el canal
        channel_to_save = channel_target if isinstance(channel_target, str) else str(channel_target)
        success = db.update_user_target_channel(user_id, channel_to_save)
        
        if not success:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Volver al Menú", callback_data='user_config_menu')]
            ])
            await update.message.reply_text(
                "❌ **Error al guardar la configuración**\n\n"
                "Hubo un problema al guardar el canal destino. Intenta nuevamente.",
                parse_mode='Markdown',
                reply_markup=keyboard
            )
            return
        
        # Verificar que se guardó correctamente leyendo de la BD
        verify_config = await get_user_config_from_db(user_id)
        saved_channel = verify_config.get('target_channel')
        
        # Obtener nombre del canal si está disponible
        channel_name = ""
        try:
            if chat_info and chat_info.title:
                channel_name = f"\n📝 Nombre: **{chat_info.title}**"
        except Exception:
            pass
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Volver al Menú", callback_data='user_config_menu')]
        ])
        await update.message.reply_text(
            f"✅ **Canal destino configurado**\n\n"
            f"📺 Canal: `{saved_channel}`{channel_name}\n\n"
            f"El bot ya tiene permisos de administrador en este canal y enviará automáticamente el contenido extraído.\n\n"
            f"Usa /start para volver al menú principal.",
            parse_mode='Markdown',
            reply_markup=keyboard
        )
        return
    
    # Ignorar si está en proceso de configuración
    if context.user_data.get('configuring_userbot'):
        return
    
    # Manejar acciones de administración
    admin_action = context.user_data.get('admin_action')
    if admin_action:
        return await handle_admin_action(update, context)
    
    # CORRECCIÓN CRÍTICA: Procesar en background para no bloquear otras peticiones
    # Crear tarea en background y almacenar referencia FUERTE para evitar garbage collection
    task = asyncio.create_task(_process_link_request(update, context))
    
    # CORRECCIÓN #3: Almacenar referencia FUERTE a la tarea
    # Esto previene que el garbage collector elimine la tarea mientras está corriendo
    if not hasattr(context.application, 'background_tasks'):
        context.application.background_tasks = set()
    
    context.application.background_tasks.add(task)
    
    # Guardar tarea por usuario para poder cancelarla individualmente
    if not hasattr(context.application, 'user_tasks'):
        context.application.user_tasks = {}
    
    context.application.user_tasks[update.effective_user.id] = task
    
    # CORRECCIÓN #3: Callback mejorado que maneja excepciones
    def task_done_callback(t):
        try:
            # Remover de la lista de tareas activas
            context.application.background_tasks.discard(t)
            
            # Remover del diccionario de tareas por usuario
            if hasattr(context.application, 'user_tasks'):
                user_id = update.effective_user.id
                if user_id in context.application.user_tasks and context.application.user_tasks[user_id] == t:
                    del context.application.user_tasks[user_id]
            
            # Verificar si hubo excepción
            if t.exception():
                logger.error(f"Tarea en background falló: {t.exception()}")
        except Exception as e:
            logger.error(f"Error en callback de tarea: {e}")
    
    task.add_done_callback(task_done_callback)
    
async def _process_link_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Wrapper executed inside a background task; catches and reports
    exceptions so the user always gets feedback."""
    try:
        await _handle_link_internal(update, context)
    except asyncio.CancelledError:
        logger.warning("Tarea de procesamiento cancelada")
        try:
            await update.message.reply_text("⚠️ Procesamiento cancelado.")
        except Exception:
            pass
    except Exception as e:
        logger.error(f"Error procesando enlace en background: {type(e).__name__}: {e}", exc_info=True)
        try:
            error_msg = str(e)
            error_type = type(e).__name__
            is_timeout = (
                isinstance(e, (asyncio.TimeoutError, TimeoutError)) or
                "timeout" in error_msg.lower() or
                "TimeoutError" in error_type
            )
            if isinstance(e, FileTransferError) and e.user_message:
                await update.message.reply_text(
                    e.user_message,
                    parse_mode='Markdown'
                )
            elif is_timeout:
                await update.message.reply_text(
                    "⏱️ **Timeout al procesar archivo**\n\n"
                    "El archivo es muy grande o hay mucho tráfico.\n"
                    "Intenta nuevamente en unos minutos.",
                    parse_mode='Markdown'
                )
            elif "Chat not found" in error_msg:
                await update.message.reply_text(
                    "❌ **Chat no encontrado**\n\n"
                    "El canal puede ser privado o inaccesible.\n\n"
                    "**Para canales privados:**\n"
                    "1️⃣ Asegúrate de tener acceso Premium\n"
                    "2️⃣ Envía el enlace de invitación del canal primero\n"
                    "3️⃣ Luego envía el enlace del contenido",
                    parse_mode='Markdown'
                )
            elif "espacio insuficiente" in error_msg.lower() or "disk" in error_msg.lower():
                await update.message.reply_text(
                    "❌ **Espacio en disco insuficiente**\n\n"
                    "Hay otras descargas en curso. Intenta en unos minutos.",
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text(
                    f"❌ **Error procesando solicitud**\n\n"
                    f"Intenta nuevamente o contacta al soporte.",
                    parse_mode='Markdown'
                )
        except Exception as reply_error:
            logger.error(f"Error enviando mensaje de error: {reply_error}")

async def _handle_link_internal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Core link-processing logic: parse the URL, resolve the channel,
    fetch the message(s), and forward the content to the user or their
    configured target channel."""
    
    text = update.message.text
    user_id = update.effective_user.id
    is_admin = user_id == ADMIN_ID
    is_premium = is_user_premium(user_id)
    # Verificar si el usuario tiene prueba gratuita disponible
    is_trial = is_user_free_trial(user_id) if not is_premium else False
    # Para efectos de acceso, un usuario con trial activo puede usar funciones premium
    can_use_premium = is_premium or is_trial
    
    # Guardar interacción del usuario
    save_user_to_db({
        'user_id': user_id,
        'username': update.effective_user.username,
        'first_name': update.effective_user.first_name,
        'last_name': update.effective_user.last_name,
        'is_premium': is_premium,
        'is_admin': is_admin
    })
    
    # Verificar si es un enlace de invitación a canal privado
    invite_hash = copy_bot.extract_invite_hash(text)
    if invite_hash:
        await update.message.reply_text("🔗 Detectado enlace de invitación a canal privado...")
        
        if not can_use_premium:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🎁 ¡Prueba Premium Gratis!", callback_data='free_trial_info')],
                [InlineKeyboardButton("⭐ Ver Premium Completo", callback_data='premium')],
                [InlineKeyboardButton("🔙 Menú Principal", callback_data='back_to_menu')]
            ])
            await update.message.reply_text(
                "⭐ **Función Premium Requerida**\n\n"
                "Para unirte a canales privados necesitas Premium.\n\n"
                "🎁 **¿Sabías que puedes probar el Premium GRATIS?**\n"
                f"Únete a nuestro canal y obtén **{FREE_TRIAL_USES} extracciones gratuitas**.",
                parse_mode='Markdown',
                reply_markup=keyboard
            )
            return
        
        # Si usa trial, consumir un uso
        if is_trial:
            uses_left = get_free_trial_uses_left(user_id)
            await update.message.reply_text(
                f"🎁 **Usando tu Prueba Gratuita** ({uses_left} usos restantes)\n\n"
                f"Procesando enlace de invitación...",
                parse_mode='Markdown'
            )
        
        # Verificar que el userbot esté configurado
        if not copy_bot.config.is_configured():
            await update.message.reply_text(ERR_USERBOT_NOT_CONFIGURED, parse_mode='Markdown')
            return
        
        # Verificar que esté conectado
        if not copy_bot.is_initialized:
            await update.message.reply_text("🔄 Iniciando conexión...")
            success = await copy_bot.initialize_client()
            if not success:
                await update.message.reply_text(ERR_USERBOT_CONNECT_FAILED)
                return
        
        # Intentar unirse al canal
        await update.message.reply_text("🔄 Uniéndome al canal...")
        success, error, status = await copy_bot.join_private_channel_by_hash(invite_hash, user_id)
        
        if status == 'joined':
            if is_trial:
                db.use_free_trial(user_id)
                uses_left = get_free_trial_uses_left(user_id)
                uses_msg = f"\n\n{TRIAL_USED.format(uses_left=uses_left)}" if uses_left > 0 else f"\n\n{TRIAL_EXHAUSTED}"
            else:
                uses_msg = ""
            await update.message.reply_text(f"{INVITE_JOINED}{uses_msg}", parse_mode='Markdown')
        elif status == 'already_member':
            await update.message.reply_text(INVITE_ALREADY_MEMBER, parse_mode='Markdown')
        elif status == 'pending_approval':
            await update.message.reply_text(INVITE_PENDING, parse_mode='Markdown')
        elif status == 'expired':
            await update.message.reply_text(INVITE_EXPIRED, parse_mode='Markdown')
        elif status == 'invalid':
            await update.message.reply_text(INVITE_INVALID, parse_mode='Markdown')
        else:
            # Error genérico
            await update.message.reply_text(error if error else "❌ Error desconocido al unirse al canal")
        return
    
    # Verificar si es un enlace de Telegram
    if not re.search(r't\.me|telegram\.me', text):
        return
    
    # Verificar si el userbot está configurado
    if not copy_bot.config.is_configured():
        await update.message.reply_text(ERR_USERBOT_NOT_CONFIGURED, parse_mode='Markdown')
        return
    
    # Verificar si el userbot está conectado
    if not copy_bot.is_initialized:
        await update.message.reply_text("🔄 Iniciando tarea...")
        success = await copy_bot.initialize_client()
        if not success:
            await update.message.reply_text(ERR_USERBOT_CONNECT_FAILED)
            return
    
    # Parsear enlace con posible contador de mensajes
    url, message_id, count = copy_bot.parse_link_with_count(text)
    
    # Log del parseo (una sola línea)
    logger.debug(f"Parseado: URL={url}, msg_id={message_id}, count={count}, texto={text}")
    
    if not message_id:
        await update.message.reply_text(ERR_MESSAGE_ID, parse_mode='Markdown')
        return
    
    # Si hay un contador de mensajes (copia múltiple)
    if count and count > 1:
        if not can_use_premium:
            # Crear botón directo al menú premium y trial
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🎁 ¡Prueba Premium Gratis!", callback_data='free_trial_info')],
                [InlineKeyboardButton("⭐ Ver Premium Completo", callback_data='premium')],
                [InlineKeyboardButton("🔙 Menú Principal", callback_data='back_to_menu')]
            ])
            
            await update.message.reply_text(
                "⭐ **La extracción múltiple requiere Premium**\n\n"
                f"🎁 ¿Sabías que puedes probar el Premium GRATIS? "
                f"Únete a nuestro canal y obtén **{FREE_TRIAL_USES} extracciones gratuitas**.",
                parse_mode='Markdown',
                reply_markup=keyboard
            )
            return
        
        # Si usa trial, notificar usos restantes
        if is_trial:
            uses_left = get_free_trial_uses_left(user_id)
            await update.message.reply_text(
                f"🎁 **Usando tu Prueba Gratuita** ({uses_left} usos restantes)\n\n"
                f"🔄 Procesando {count} mensajes consecutivos...",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                f"🔄 Procesando {count} mensajes consecutivos desde el post {message_id}...\n\n"
                f"⏳ Esto puede tomar unos momentos..."
            )
        
        # Obtener configuración de filtros y canal destino del usuario
        user_config = await get_user_config_from_db(user_id)
        filters = user_config.get('filters', {
            'videos': True,
            'photos': True,
            'documents': True,
            'audio': True,
            'text': True,
            'stickers': True
        })
        target_channel = user_config.get('target_channel', None)
        
        # Determinar el destino de envío: canal configurado o chat del usuario
        send_to_chat_id = target_channel if target_channel else update.effective_chat.id
        
        # Informar al usuario sobre el destino
        if target_channel:
            await update.message.reply_text(
                f"📺 **Canal destino configurado**\n\n"
                f"El contenido se enviará automáticamente a: `{target_channel}`\n\n"
                f"💡 Para cambiar el destino, usa el menú ⚙️ Configuración",
                parse_mode='Markdown'
            )
        
        # Verificar si hay filtros activos (alguno desactivado)
        has_active_filters = not all(filters.values())
        
        if has_active_filters:
            # Usar extracción con filtros
            await update.message.reply_text(
                f"🎯 **Filtros activos detectados**\n\n"
                f"Buscando solo:\n" +
                (f"• 🎥 Videos\n" if filters.get('videos') else "") +
                (f"• 📸 Fotos\n" if filters.get('photos') else "") +
                (f"• 📎 Documentos\n" if filters.get('documents') else "") +
                (f"• 🎵 Audio\n" if filters.get('audio') else "") +
                (f"• 📝 Texto\n" if filters.get('text') else "") +
                (f"• 🎭 Stickers\n" if filters.get('stickers') else ""),
                parse_mode='Markdown'
            )
            messages, error, has_protection, entity = await copy_bot.copy_multiple_messages_filtered(url, message_id, count, filters, can_use_premium)
        else:
            # Usar extracción normal (todos los mensajes)
            messages, error, has_protection, entity = await copy_bot.copy_multiple_messages(url, message_id, count, can_use_premium)
        
        if error:
            if error == "NEEDS_JOIN":
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton(BACK_TO_MENU_BTN, callback_data='back_to_menu')]
                ])
                await update.message.reply_text(
                    ERR_CHANNEL_ACCESS, parse_mode='Markdown', reply_markup=keyboard
                )
            elif error == "PREMIUM_REQUIRED":
                # Crear botones para premium y trial
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🎁 ¡Prueba Premium Gratis!", callback_data='free_trial_info')],
                    [InlineKeyboardButton("⭐ Ver Premium Completo", callback_data='premium')],
                    [InlineKeyboardButton("🔙 Menú Principal", callback_data='back_to_menu')]
                ])
                
                await update.message.reply_text(
                    "⭐ **La extracción múltiple requiere Premium**\n\n"
                    "Toca el botón '⭐ Ver Premium' abajo para más información.",
                    parse_mode='Markdown',
                    reply_markup=keyboard
                )
            else:
                await update.message.reply_text(error)
            return
        
        if not messages:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Menú Principal", callback_data='back_to_menu')]
            ])
            await update.message.reply_text(
                "❌ No se pudieron obtener los mensajes. Intenta nuevamente.",
                reply_markup=keyboard
            )
            return
        
        await update.message.reply_text(
            f"✅ Encontrados {len(messages)} mensajes de {count} solicitados.\n"
            f"📤 Enviando contenido..."
        )
        
        # Consumir un uso de trial si aplica (en extracción masiva)
        if is_trial:
            db.use_free_trial(user_id)
            uses_left = get_free_trial_uses_left(user_id)
            if uses_left > 0:
                await update.message.reply_text(
                    f"🎁 *Prueba gratuita utilizada.* Te quedan **{uses_left}** uso(s) más.",
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text(
                    "⚠️ *Has agotado tu prueba gratuita.* Considera obtener Premium para continuar.",
                    parse_mode='Markdown'
                )
        
        # PROCESAMIENTO CONCURRENTE de mensajes
        sent_count = 0
        failed_count = 0
        _count_lock = asyncio.Lock()
        
        # Almacenar entity y has_protection para uso en send_single_message
        channel_entity = entity
        channel_has_protection = has_protection
        
        async def send_single_message(msg, index):
            """Enviar un mensaje individual con soporte de concurrencia.
            El semáforo de transferencia se maneja dentro de _send_message_content."""
            nonlocal sent_count, failed_count
            
            try:
                if not msg:
                    return
                
                # Determinar si es un archivo grande
                file_size = 0
                if hasattr(msg, 'document') and msg.document:
                    file_size = getattr(msg.document, 'file_size', 0) or 0
                elif hasattr(msg, 'video') and msg.video:
                    file_size = getattr(msg.video, 'file_size', 0) or 0
                has_large_file = file_size > 50 * 1024 * 1024
                
                # Solo mostrar progreso si es archivo grande
                progress_msg = None
                tracker = None
                if has_large_file:
                    try:
                        progress_msg = await update.message.reply_text(
                            f"📥 **[{index+1}/{len(messages)}] Descargando contenido** ({file_size/(1024*1024):.1f}MB)\n\n"
                            f"⬡⬡⬡⬡⬡⬡⬡⬡ **0%**\n\n"
                            f"📦 **Progreso:** 0MB / {file_size/(1024*1024):.1f}MB",
                            parse_mode='Markdown'
                        )
                        tracker = ProgressTracker(
                            message=progress_msg,
                            user_id=user_id,
                            with_cancel=False
                        )
                    except Exception:
                        pass
                
                try:
                    result = await copy_bot._send_message_content(
                        context, send_to_chat_id, msg,
                        progress_callback=tracker
                    )
                    
                    async with _count_lock:
                        sent_count += 1
                        current_sent = sent_count
                    logger.info(f"✓ Mensaje {msg.id} procesado ({current_sent}/{len(messages)})")
                    
                    if progress_msg:
                        try:
                            await progress_msg.delete()
                        except Exception:
                            pass
                            
                except Exception as e2:
                    error_str = str(e2).lower()
                    logger.error(f"Error enviando mensaje {msg.id}: {e2}")
                    async with _count_lock:
                        failed_count += 1
                    
                    error_text = f"❌ Error procesando mensaje {msg.id}"
                    if "can't forward" in error_str or "protected" in error_str:
                        error_text += "\n⚠️ Canal con protección de contenido."
                    elif "espacio insuficiente" in error_str or "disk" in error_str:
                        error_text += "\n💾 Espacio en disco insuficiente. Esperando…"
                    else:
                        error_text += f":\n{str(e2)[:100]}"
                    
                    if progress_msg:
                        try:
                            await progress_msg.edit_text(error_text)
                        except Exception:
                            pass
                    
            except Exception as outer_error:
                logger.error(f"Error general procesando mensaje {msg.id if msg else 'unknown'}: {outer_error}")
                async with _count_lock:
                    failed_count += 1
        
        # PROCESAMIENTO CONCURRENTE en lotes
        # El semáforo en _send_message_content limita descargas simultáneas
        # Enviamos en lotes para mantener un orden razonable y respetar rate limits
        from config import MAX_CONCURRENT_TRANSFERS
        BATCH_SIZE = MAX_CONCURRENT_TRANSFERS  # Procesar en lotes del tamaño del semáforo
        
        logger.info(
            f"📝 Procesando {len(messages)} mensajes "
            f"(concurrencia máx: {MAX_CONCURRENT_TRANSFERS})..."
        )
        batch_sent_count = 0
        
        for batch_start in range(0, len(messages), BATCH_SIZE):
            batch = messages[batch_start:batch_start + BATCH_SIZE]
            
            # === PAUSA INTELIGENTE CADA 50 MENSAJES ===
            if batch_sent_count > 0 and batch_sent_count % copy_bot.batch_pause_threshold == 0:
                pause_seconds = copy_bot.batch_pause_duration
                logger.info(f"⏸️ Pausa automática después de {batch_sent_count} mensajes ({pause_seconds}s)...")
                try:
                    await update.message.reply_text(
                        f"⏸️ **Pausa automática de protección**\n\n"
                        f"Se han enviado **{sent_count}** de **{len(messages)}** mensajes.\n\n"
                        f"⏱️ Pausa de **{pause_seconds} segundos** para cumplir normas de Telegram.\n\n"
                        f"🔄 El proceso continuará automáticamente...",
                        parse_mode='Markdown'
                    )
                except Exception:
                    pass
                await asyncio.sleep(pause_seconds)
                batch_sent_count = 0
                logger.info(f"▶️ Reanudando procesamiento después de pausa...")
            
            # Verificar rate limit antes de cada lote
            allowed, rate_msg = await copy_bot.rate_limit_check(user_id)
            if not allowed:
                pause_notice = await update.message.reply_text(
                    f"{rate_msg}\n\n"
                    f"✅ Se procesaron **{sent_count}** de **{len(messages)}** mensajes.\n\n"
                    f"🔄 **El proceso se reanudará automáticamente** cuando pase el tiempo de espera.",
                    parse_mode='Markdown'
                )
                logger.info(f"⏳ Rate limit alcanzado. Esperando 60s para auto-reanudar...")
                await asyncio.sleep(60)
                
                allowed_retry, _ = await copy_bot.rate_limit_check(user_id)
                if not allowed_retry:
                    logger.info(f"⏳ Aún no permitido. Esperando otros 60s...")
                    await asyncio.sleep(60)
                    allowed_retry2, _ = await copy_bot.rate_limit_check(user_id)
                    if not allowed_retry2:
                        try:
                            await pause_notice.edit_text(
                                f"⏹️ **Proceso detenido temporalmente**\n\n"
                                f"✅ Se procesaron **{sent_count}** de **{len(messages)}** mensajes.\n\n"
                                f"💡 Intenta nuevamente en unos minutos para continuar.",
                                parse_mode='Markdown'
                            )
                        except Exception:
                            pass
                        break
                
                try:
                    await pause_notice.edit_text(
                        f"▶️ **Proceso reanudado automáticamente**\n\n"
                        f"Continuando con el envío de mensajes...",
                        parse_mode='Markdown'
                    )
                except Exception:
                    pass
                logger.info(f"▶️ Auto-reanudado después de pausa por rate limit")
            
            # Lanzar tareas concurrentes para el lote
            prev_sent = sent_count
            tasks = [
                send_single_message(msg, batch_start + idx)
                for idx, msg in enumerate(batch)
            ]
            await asyncio.gather(*tasks, return_exceptions=True)
            batch_sent_count += (sent_count - prev_sent)
            
            # Pausa corta entre lotes para respetar rate limits
            if batch_start + BATCH_SIZE < len(messages):
                await asyncio.sleep(1.5)
        
        # Resumen final del proceso
        summary = f"✅ **Proceso completado**\n\n"
        summary += f"📤 Mensajes enviados: {sent_count}/{len(messages)}\n"
        
        if failed_count > 0:
            summary += f"⚠️ Mensajes fallidos: {failed_count}\n"
        
        if target_channel:
            summary += f"\n📺 Enviado a: `{target_channel}`"
        
        await update.message.reply_text(summary, parse_mode='Markdown')
        return
    
    # Copia simple de un solo mensaje
    processing_msg = await update.message.reply_text("🔄 Procesando enlace...")
    
    # Obtener configuración del usuario para canal destino
    user_config = await get_user_config_from_db(user_id)
    target_channel_single = user_config.get('target_channel', None)
    send_to_chat_id_single = target_channel_single if target_channel_single else update.effective_chat.id
    
    # Informar al usuario sobre el destino si está configurado
    if target_channel_single:
        await update.message.reply_text(
            f"📺 **Canal destino configurado**\n\n"
            f"El contenido se enviará a: `{target_channel_single}`",
            parse_mode='Markdown'
        )
    
    # Copiar contenido con Pyrogram (envío directo, sin canal intermedio)
    message, error, has_protection, via_intermediate_info = await copy_bot.copy_content(
        url, 
        message_id, 
        can_use_premium
    )
    
    if error:
        try:
            await processing_msg.delete()
        except Exception:
            pass
            
        if error == "NEEDS_JOIN":
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(BACK_TO_MENU_BTN, callback_data='back_to_menu')]
            ])
            await update.message.reply_text(
                ERR_CHANNEL_ACCESS, parse_mode='Markdown', reply_markup=keyboard
            )
        else:
            await update.message.reply_text(error)
        return
    
    # Verificar que tenemos el mensaje
    if not message:
        try:
            await processing_msg.delete()
        except Exception:
            pass
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Menú Principal", callback_data='back_to_menu')]
        ])
        await update.message.reply_text(
            "❌ No se pudo obtener el contenido. Intenta nuevamente.",
            reply_markup=keyboard
        )
        return
    
    # Consumir un uso de trial si aplica (en extracción de canal privado)
    if is_trial:
        is_private_url = copy_bot.is_private_channel_link(url)
        if is_private_url:
            db.use_free_trial(user_id)
            uses_left = get_free_trial_uses_left(user_id)
            if uses_left > 0:
                await update.message.reply_text(
                    f"🎁 *Prueba gratuita utilizada.* Te quedan **{uses_left}** uso(s) más.",
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text(
                    "⚠️ *Has agotado tu prueba gratuita.* Considera obtener Premium para continuar.",
                    parse_mode='Markdown'
                )
    
    # ====== ENVÍO DIRECTO CON PYROGRAM (sin canal intermedio) ======
    
    # Determinar si es un archivo grande
    file_size = 0
    if message.document:
        file_size = getattr(message.document, 'file_size', 0) or 0
    elif message.video:
        file_size = getattr(message.video, 'file_size', 0) or 0
    has_large_file = file_size > 50 * 1024 * 1024
    
    # Crear ProgressTracker reusable para single-message flow
    tracker = ProgressTracker(
        message=processing_msg,
        user_id=user_id,
        with_cancel=True
    )
    
    # Sincronizar cancelación desde context.application
    _orig_call = tracker.__call__
    async def _synced_progress(current, total):
        if hasattr(context.application, 'cancel_flags'):
            if context.application.cancel_flags.get(user_id, False):
                tracker.request_cancel()
        await _orig_call(current, total)
    
    # Actualizar mensaje inicial si es archivo grande
    if has_large_file:
        try:
            cancel_keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Cancelar", callback_data=f"cancel_download_{user_id}")]
            ])
            await processing_msg.edit_text(
                f"📥 **Descargando desde Telegram**\n\n"
                f"⬡⬡⬡⬡⬡⬡⬡⬡ **0%**\n\n"
                f"📦 **Progreso:** 0MB / {file_size/(1024*1024):.1f}MB\n"
                f"💾 **Tamaño:** {file_size/(1024*1024):.1f}MB",
                parse_mode='Markdown',
                reply_markup=cancel_keyboard
            )
        except Exception:
            pass
    
    # Enviar contenido con ProgressTracker
    try:
        result = await copy_bot._send_message_content(
            context, 
            send_to_chat_id_single, 
            message, 
            progress_callback=_synced_progress,
            cancel_flag=[tracker.cancel_requested]
        )
        
        logger.debug(f"Contenido enviado a {send_to_chat_id_single}")
        
        # Eliminar mensaje de procesamiento
        try:
            await processing_msg.delete()
        except Exception:
            pass
        
        # Notificar al usuario si el contenido se envió a un canal destino
        if target_channel_single:
            back_keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Menú Principal", callback_data='back_to_menu')]
            ])
            await update.message.reply_text(
                f"✅ **Contenido enviado exitosamente**\n\n"
                f"📺 Enviado a: `{target_channel_single}`",
                parse_mode='Markdown',
                reply_markup=back_keyboard
            )

    except FileTransferError as fte:
        # Archivo demasiado grande — mostrar mensaje claro al usuario
        logger.warning(f"Archivo excede límite: {fte}")
        try:
            await processing_msg.delete()
        except Exception:
            pass
        back_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Menú Principal", callback_data='back_to_menu')]
        ])
        await update.message.reply_text(
            fte.user_message, parse_mode='Markdown', reply_markup=back_keyboard
        )
    except Exception as e2:
        error_str = str(e2).lower()
        error_type = type(e2).__name__
        logger.error(f"Error copiando contenido: {error_type}: {e2}")

        # Eliminar mensaje de procesamiento
        try:
            await processing_msg.delete()
        except Exception:
            pass

        # Verificar si fue cancelación del usuario
        if isinstance(e2, asyncio.CancelledError) or "cancelada por el usuario" in error_str or "cancelled" in error_str:
            logger.info(f"✅ Descarga cancelada exitosamente por usuario {user_id}")
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(BACK_TO_MENU_BTN, callback_data='back_to_menu')]
            ])
            await update.message.reply_text(
                CANCEL_SUCCESS, parse_mode='Markdown', reply_markup=keyboard
            )
            if hasattr(context.application, 'cancel_flags'):
                context.application.cancel_flags.pop(user_id, None)
            return

        bot_username = context.bot.username or "bot"
        back_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Menú Principal", callback_data='back_to_menu')]
        ])

        # Mensaje de error específico según el tipo
        # NOTA: asyncio.TimeoutError tiene str() vacío, hay que verificar el tipo
        is_timeout = (
            isinstance(e2, (asyncio.TimeoutError, TimeoutError)) or
            "timeout" in error_str or
            "TimeoutError" in error_type
        )
        
        if is_timeout:
            await update.message.reply_text(
                ERR_TIMEOUT, parse_mode='Markdown', reply_markup=back_keyboard
            )
        elif "chat not found" in error_str:
            await update.message.reply_text(
                ERR_CHAT_NOT_FOUND, parse_mode='Markdown', reply_markup=back_keyboard
            )
        elif "espacio insuficiente" in error_str or "disk" in error_str:
            # Error de disco — mostrar mensaje amigable
            if isinstance(e2, FileTransferError) and e2.user_message:
                await update.message.reply_text(
                    e2.user_message, parse_mode='Markdown', reply_markup=back_keyboard
                )
            else:
                await update.message.reply_text(
                    "❌ **Espacio en disco insuficiente**\n\n"
                    "Hay otras descargas en curso que ocupan espacio.\n"
                    "Intenta nuevamente en unos minutos.",
                    parse_mode='Markdown',
                    reply_markup=back_keyboard
                )
        elif isinstance(e2, FileTransferError) and e2.user_message:
            await update.message.reply_text(
                e2.user_message, parse_mode='Markdown', reply_markup=back_keyboard
            )
        else:
            # Verificar si es un error de canal destino
            if "canal destino" in error_str or "no se pudo enviar" in error_str or "no tiene permisos" in error_str:
                await update.message.reply_text(
                    str(e2)[:1000],
                    parse_mode='Markdown',
                    reply_markup=back_keyboard
                )
            elif "not enough rights" in error_str or "forbidden" in error_str:
                user_config_err = await get_user_config_from_db(update.effective_user.id)
                target_ch = user_config_err.get('target_channel')
                if target_ch:
                    await update.message.reply_text(
                        f"❌ **Error al enviar al canal destino**\n\n"
                        f"📺 Canal configurado: `{target_ch}`\n\n"
                        f"El bot no tiene permisos para publicar en este canal.\n\n"
                        f"**Solución:**\n"
                        f"1. Abre el canal `{target_ch}`\n"
                        f"2. Verifica que el bot `@{bot_username}` sea administrador\n"
                        f"3. Dale permiso de 'Publicar Mensajes'\n"
                        f"4. Intenta nuevamente\n\n"
                        f"O ve a ⚙️ Configuración > 📺 Canal Destino para cambiar o eliminar el canal.",
                        parse_mode='Markdown',
                        reply_markup=back_keyboard
                    )
                else:
                    await update.message.reply_text(
                        "❌ **Error al enviar contenido**\n\n"
                        "No se pudo enviar el contenido. Intenta nuevamente.",
                        parse_mode='Markdown',
                        reply_markup=back_keyboard
                    )
            else:
                await update.message.reply_text(
                    "❌ **Error al reenviar contenido**\n\n"
                    "Hubo un problema al procesar tu solicitud. Intenta nuevamente.\n\n"
                    "Si el problema persiste, verifica tu configuración de canal destino en ⚙️ Configuración.",
                    parse_mode='Markdown',
                    reply_markup=back_keyboard
                )

