"""Core module: ContentCopyBot and UserbotConfig
Handles Pyrogram userbot client, rate limiting, content copy, and channel operations.
"""

import re
import time
import asyncio
import logging
import tempfile
import os as os_module
import gc
import shutil
import glob as glob_module
from typing import Optional, Dict, Any, Tuple, List

from pyrogram import Client as PyrogramClient
from pyrogram.errors import (
    ChannelPrivate as ChannelPrivateError,
    UsernameNotOccupied as UsernameNotOccupiedError,
    SessionPasswordNeeded as SessionPasswordNeededError,
    PhoneCodeInvalid as PhoneCodeInvalidError,
    InviteHashExpired as InviteHashExpiredError,
    InviteHashInvalid as InviteHashInvalidError,
    UserAlreadyParticipant as UserAlreadyParticipantError,
    FloodWait as FloodWaitError
)
from pyrogram import raw

# ========== FIX: Pyrogram 2.0.106 "Peer id invalid" para canales nuevos ==========
# Telegram creó canales con IDs > 2^31 (e.g. -1002488429336) pero Pyrogram 2.0.106
# tiene MIN_CHANNEL_ID = -1002147483647 (basado en int32). Esto causa ValueError
# en get_peer_type() para canales recientes. Parche aplicado al importar.
import pyrogram.utils as _pyrogram_utils
_pyrogram_utils.MIN_CHANNEL_ID = -1009999999999
_pyrogram_utils.MIN_CHAT_ID = -999999999999

from database import MongoDB
from logging_utils import mask_phone
from config import (
    MAX_FILE_SIZE, SAFE_MEMORY_LIMIT, TEMP_DOWNLOAD_DIR,
    INTERMEDIATE_CHANNEL_ID, MAX_CONCURRENT_TRANSFERS,
    SERVER_DISK_LIMIT, DISK_RESERVE_MB
)
from exceptions import (
    FileTransferError, RateLimitError, ChannelAccessError, AuthenticationError
)

logger = logging.getLogger(__name__)

class UserbotConfig:
    """Manages userbot configuration backed by MongoDB.

    Attributes:
        db: MongoDB instance used for persistence.
        config: In-memory dict of the current configuration.
    """

    REQUIRED_KEYS: List[str] = ['api_id', 'api_hash', 'phone_number']

    def __init__(self, database: MongoDB) -> None:
        self.db: MongoDB = database
        self.config: Dict[str, Any] = self.load_config()

    def load_config(self) -> Dict[str, Any]:
        """Load the full userbot config from MongoDB.

        Returns:
            A dict of config values, or empty dict on error.
        """
        try:
            config = self.db.get_userbot_config()
            return config if config else {}
        except Exception as e:
            logger.error("Error cargando configuración del userbot")
            return {}

    def save_config(self, silent: bool = False) -> None:
        """Persist the in-memory config to MongoDB.

        Args:
            silent: If True, suppress the DEBUG log line.
        """
        try:
            self.db.save_userbot_config(self.config)
            if not silent:
                logger.debug("Configuración guardada en MongoDB")
        except Exception as e:
            logger.error("Error guardando configuración del userbot")

    def get(self, key: str, default: Any = None) -> Any:
        """Return a single config value (in-memory)."""
        return self.config.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set a config value and persist silently."""
        self.config[key] = value
        self.save_config(silent=True)

    def is_configured(self) -> bool:
        """Return True when all required keys have truthy values."""
        return all(self.config.get(key) for key in self.REQUIRED_KEYS)

class ContentCopyBot:
    def __init__(self, database: MongoDB):
        self.db = database
        self.config = UserbotConfig(database)
        self.client = None
        self.is_initialized = False
        self.pending_auth = None  # Para almacenar el objeto de autenticación pendiente
        
        # ==================== CANAL INTERMEDIO ====================
        # Canal donde el userbot sube archivos y el bot los reenvía al usuario.
        self.intermediate_channel_id = INTERMEDIATE_CHANNEL_ID
        
        # ==================== CONCURRENCIA ====================
        # Semáforo para controlar descargas/transferencias simultáneas
        self._transfer_semaphore = asyncio.Semaphore(MAX_CONCURRENT_TRANSFERS)
        # Contador de transferencias activas (para logging y cleanup guard)
        self._active_transfers = 0
        self._active_transfers_lock = asyncio.Lock()
        
        # Flag legacy para indicar que hay al menos una transferencia activa.
        # Mientras es True, _cleanup_temp_files() NO borra archivos.
        self._transfer_active = False
        
        # ==================== LÍMITE DE DISCO ====================
        # Disco total del servidor: 4.88 GB
        self._server_disk_limit = SERVER_DISK_LIMIT
        self._disk_reserve_bytes = DISK_RESERVE_MB * 1024 * 1024
        # Rastrear bytes en uso por transferencias activas
        self._reserved_disk_bytes = 0
        self._disk_lock = asyncio.Lock()
        
        # ==================== DIRECTORIO TEMPORAL ====================
        # Usar directorio configurable para descargas temporales
        self.temp_dir = TEMP_DOWNLOAD_DIR
        os_module.makedirs(self.temp_dir, exist_ok=True)
        # Limpieza inicial de archivos huérfanos al arrancar
        self._cleanup_temp_files(max_age_seconds=0, force=True)  # Limpiar TODO al iniciar
        
        # ==================== SISTEMA ANTI-BAN ROBUSTO ====================
        # Telegram tiene límites estrictos: excederlos = FloodWait o ban temporal/permanente
        # Normas reales de Telegram (basadas en userbots que procesan 50-100+ msgs sin ban):
        # - Máximo ~30 mensajes/segundo a diferentes chats
        # - Máximo ~20 mensajes/minuto al mismo chat  
        # - FloodWait: Telegram pide esperar X segundos antes de continuar
        # - En la práctica, userbots procesan 50-100 mensajes seguidos con pausas cortas
        
        self.last_request_time = 0
        self.min_delay_between_requests = 1.0  # 1 segundo entre peticiones (equilibrado)
        self.request_count = 0
        self.request_limit_per_minute = 28  # 28 peticiones/minuto (bajo el límite real de ~30)
        self.request_times = []
        
        # Límites adicionales para protección anti-ban (relajados para procesamiento masivo)
        self.hourly_request_times = []  # Control por hora
        self.hourly_request_limit = 500  # Máximo 500 peticiones por hora
        self.daily_request_count = 0
        self.daily_request_limit = 5000  # Máximo 5000 peticiones por día
        self.daily_reset_time = time.time()
        
        # Control de FloodWait
        self.flood_wait_until = 0  # Timestamp hasta cuando esperar por FloodWait
        self.flood_wait_count = 0  # Veces consecutivas que hemos recibido FloodWait
        self.max_flood_waits = 8  # Máximo de FloodWaits consecutivos antes de pausar
        
        # Control de descargas/subidas por usuario
        self.user_request_times = {}  # {user_id: [timestamps]}
        self.user_request_limit_per_minute = 28  # 28 peticiones por minuto por usuario (similar al global)
        
        # Sistema de pausas inteligentes para copia masiva
        # Pausa automática cada N mensajes enviados exitosamente, luego continúa
        self.batch_pause_threshold = 50  # Pausar cada 50 mensajes enviados
        self.batch_pause_duration = 10  # Segundos de pausa entre lotes
        
        # Estado para manejar unión a canales
        self.pending_join = {}  # {user_id: {'invite_link': str, 'channel_title': str, 'status': str, 'timestamp': float}}
        
        # ISSUE #1 FIX: Sistema de monitoreo para notificar cuando el admin acepta solicitudes
        self._monitoring_pending_joins = False
        
    async def initialize_client(self, force_recreate: bool = False):
        """Inicializar el cliente de Pyrogram usando session_string.
        
        IMPORTANTE: Si no hay session_string guardada, NO intenta conectar
        (evita EOFError por stdin en servidor headless como Render).
        La session_string se obtiene solo a través del flujo de configuración
        (send_code_request → sign_in_with_code).
        """
        if self.is_initialized and not force_recreate:
            return True
            
        if not self.config.is_configured():
            logger.warning("Userbot no configurado")
            return False
        
        session_string = self.config.get('session_string', '')
        
        # SIN session_string no podemos conectar (Pyrogram pediría código por stdin)
        if not session_string:
            logger.warning("⚠️ No hay session_string. Usa el menú de configuración para autenticar.")
            return False
            
        try:
            api_id = int(self.config.get('api_id'))
            api_hash = self.config.get('api_hash')
            
            # Desconectar cliente anterior si existe
            if self.client:
                try:
                    if self.client.is_connected:
                        await self.client.stop()
                except Exception:
                    pass
                self.client = None
            
            # Crear cliente Pyrogram SOLO con session_string (nunca con phone_number directo)
            self.client = PyrogramClient(
                name="userbot",
                api_id=api_id,
                api_hash=api_hash,
                session_string=session_string,
                in_memory=True,
                no_updates=True,  # No procesar updates (solo API calls)
                device_model="Server",
                system_version="Linux",
                app_version="1.0",
                lang_code="es"
            )
            
            # Conectar cliente con timeout
            logger.info("Conectando cliente de Pyrogram (session_string)...")
            await asyncio.wait_for(self.client.start(), timeout=30.0)
            
            self.is_initialized = True
            logger.info("✅ Cliente de Pyrogram conectado correctamente")
            
            return True
            
        except asyncio.TimeoutError:
            logger.error("❌ Timeout al conectar cliente de Pyrogram")
            self.is_initialized = False
            return False
        except Exception as e:
            logger.error(f"❌ Error inicializando cliente: {e}", exc_info=True)
            self.is_initialized = False
            return False

    async def send_code_request(self) -> bool:
        """Request a Telegram verification code via Pyrogram.

        Creates a temporary connect-only client so that Pyrogram
        never prompts for a code on stdin (safe for headless servers).

        Returns:
            True if the code was sent successfully.

        Raises:
            AuthenticationError: (internal) when the config is incomplete.
        """
        try:
            if not self.config.is_configured():
                logger.warning("send_code_request: config incompleta")
                raise AuthenticationError(
                    "Configuración incompleta",
                    user_message="⚙️ Configura primero api_id, api_hash y teléfono."
                )

            api_id = int(self.config.get('api_id'))
            api_hash = self.config.get('api_hash')
            phone_number = self.config.get('phone_number')

            if not phone_number:
                logger.error("send_code_request: phone_number vacío")
                raise AuthenticationError(
                    "Número de teléfono faltante",
                    user_message="❌ Número de teléfono no configurado."
                )
            
            # Desconectar cliente previo si existe (para evitar conflictos)
            if self.client:
                try:
                    if self.client.is_connected:
                        await self.client.disconnect()
                except Exception:
                    pass
            
            # Crear cliente SOLO para autenticación (connect, NO start)
            self.client = PyrogramClient(
                name="userbot_auth",
                api_id=api_id,
                api_hash=api_hash,
                in_memory=True,
                no_updates=True
            )
            # connect() establece conexión con Telegram SIN pedir código por stdin
            await self.client.connect()
            
            # Enviar código al teléfono del usuario
            self.pending_auth = await self.client.send_code(phone_number)
            logger.info(f"✅ Código de verificación enviado a {mask_phone(phone_number)}")
            return True
            
        except AuthenticationError:
            return False
        except Exception as e:
            logger.error(f"❌ Error enviando código de verificación: {type(e).__name__}: {e}")
            return False
    
    async def sign_in_with_code(self, code: str, password: Optional[str] = None) -> Tuple[bool, str]:
        """Complete Pyrogram sign-in with a verification code.

        Args:
            code: The verification code received on the phone.
            password: Optional 2FA password if the account requires it.

        Returns:
            A tuple ``(success, message)``.
        """
        try:
            if not self.client or not self.pending_auth:
                return False, "No hay autenticación pendiente"
            
            phone_number = self.config.get('phone_number')
            
            try:
                # Intentar iniciar sesión con el código
                await self.client.sign_in(
                    phone_number, 
                    self.pending_auth.phone_code_hash, 
                    code
                )
                
                # Guardar sesión
                session_string = await self.client.export_session_string()
                self.config.set('session_string', session_string)
                
                self.is_initialized = True
                self.pending_auth = None
                logger.info("Autenticación exitosa")
                return True, "Autenticación exitosa"
                
            except SessionPasswordNeededError:
                # Se requiere contraseña de 2FA
                if password:
                    await self.client.check_password(password)
                    
                    # Guardar sesión
                    session_string = await self.client.export_session_string()
                    self.config.set('session_string', session_string)
                    
                    self.is_initialized = True
                    self.pending_auth = None
                    logger.info("Autenticación exitosa con 2FA")
                    return True, "Autenticación exitosa"
                else:
                    return False, "2FA requerido"
                    
            except PhoneCodeInvalidError:
                return False, "Código inválido"
                
        except Exception as e:
            logger.error("Error en proceso de sign_in (detalles omitidos por seguridad)")
            return False, "Error de autenticación"

    async def check_pending_join_approvals(self, bot):
        """Verificar si hay solicitudes pendientes que fueron aceptadas"""
        if not self.pending_join or not await self.ensure_connected():
            return
        
        current_time = time.time()
        users_to_notify = []
        
        for user_id, join_info in list(self.pending_join.items()):
            if join_info.get('status') != 'pending_approval':
                continue
            if current_time - join_info.get('timestamp', 0) < 10:
                continue
            
            invite_link = join_info.get('invite_link')
            if not invite_link:
                continue
            
            try:
                # Intentar obtener info del chat - si funciona, ya somos miembros
                chat = await self.client.get_chat(invite_link)
                if chat:
                    logger.info(f"✅ Solicitud aceptada para usuario {user_id}!")
                    users_to_notify.append((user_id, join_info))
                    del self.pending_join[user_id]
            except Exception as e:
                logger.debug(f"Error verificando aprobación para user {user_id}: {e}")
        
        # Notificar a los usuarios cuyas solicitudes fueron aceptadas
        for user_id, join_info in users_to_notify:
            try:
                channel_title = join_info.get('channel_title', 'Canal')
                invite_link = join_info.get('invite_link', '')
                
                notification_msg = (
                    f"✅ **¡Solicitud Aceptada!**\n\n"
                    f"🎉 El administrador ha aceptado tu solicitud para unirte al canal:\n"
                    f"📢 **{channel_title}**\n\n"
                )
                
                if invite_link:
                    notification_msg += f"🔗 [Enlace del canal]({invite_link})\n\n"
                
                notification_msg += (
                    f"📌 **Ahora puedes:**\n"
                    f"• Enviar el enlace del contenido que deseas extraer\n"
                    f"• Ejemplo: `https://t.me/c/1234567890/123`\n\n"
                    f"💡 El bot ya está unido al canal y listo para extraer contenido."
                )
                
                await bot.send_message(
                    chat_id=user_id,
                    text=notification_msg,
                    parse_mode='Markdown'
                )
                logger.info(f"✅ Notificación enviada a usuario {user_id} sobre solicitud aceptada")
            except Exception as e:
                logger.error(f"Error enviando notificación a usuario {user_id}: {e}")
    
    async def ensure_connected(self) -> bool:
        """Ensure the Pyrogram client is connected, reconnecting if needed.

        Returns:
            True when the client is ready to make API calls.
        """
        if not self.client:
            return await self.initialize_client()
        
        if not self.client.is_connected:
            try:
                await self.client.start()
            except Exception:
                return await self.initialize_client(force_recreate=True)
            
        return self.client.is_connected and self.is_initialized
    
    async def rate_limit_check(self, user_id: int = None) -> tuple:
        """Control de rate limiting EQUILIBRADO para evitar ban de Telegram
        
        Basado en límites reales observados en userbots que procesan 50-100+ mensajes
        sin ser baneados. Telegram permite mucho más de lo que se pensaba, siempre
        que se respeten los FloodWait y se hagan pausas periódicas.
        
        Estrategia: auto-esperar cuando se alcanzan límites en vez de bloquear.
        Solo bloquea en casos críticos (FloodWait excesivos, límite diario).
        
        Returns:
            tuple: (allowed: bool, user_message: str or None)
            - allowed: True si se puede proceder, False si hay que esperar
            - user_message: Mensaje explicativo para el usuario si allowed=False
        """
        current_time = time.time()
        
        # === 1. VERIFICAR FLOODWAIT ACTIVO ===
        # Si Telegram nos pidió esperar, AUTO-ESPERAR en vez de bloquear
        if current_time < self.flood_wait_until:
            wait_remaining = self.flood_wait_until - current_time
            if wait_remaining <= 120:  # Si son 2 minutos o menos, esperar automáticamente
                logger.debug(f"⏳ FloodWait activo: esperando {wait_remaining:.0f}s automáticamente...")
                await asyncio.sleep(wait_remaining + 1)
                self.flood_wait_until = 0  # Resetear después de esperar
            else:
                minutes = int(wait_remaining // 60)
                seconds = int(wait_remaining % 60)
                user_msg = (
                    f"⏸️ **Proceso pausado temporalmente**\n\n"
                    f"Telegram nos pidió esperar para proteger la cuenta del bot.\n\n"
                    f"⏱️ **Tiempo restante:** {minutes}m {seconds}s\n\n"
                    f"🔒 Esto es normal y protege tu cuenta.\n\n"
                    f"💡 Intenta nuevamente en {minutes} minutos y {seconds} segundos."
                )
                logger.warning(f"FloodWait activo largo: {wait_remaining:.0f}s restantes")
                return False, user_msg
        
        # === 2. VERIFICAR MÁXIMO DE FLOODWAITS CONSECUTIVOS ===
        if self.flood_wait_count >= self.max_flood_waits:
            # Auto-reset después de 15 minutos
            if current_time - self.flood_wait_until > 900:
                self.flood_wait_count = 0
                logger.debug("FloodWait counter reseteado después de 15 minutos")
            else:
                user_msg = (
                    f"⛔ **Servicio pausado por protección**\n\n"
                    f"Se han recibido demasiadas advertencias de Telegram seguidas.\n\n"
                    f"🛡️ **Esto protege la cuenta del bot** contra un posible ban.\n\n"
                    f"⏱️ El servicio se reactivará automáticamente en **15 minutos**.\n\n"
                    f"💡 Espera un momento y vuelve a intentar."
                )
                logger.error(f"Demasiados FloodWaits consecutivos ({self.flood_wait_count}), pausando servicio")
                return False, user_msg
        
        # === 3. RESETEAR CONTADOR DIARIO SI PASÓ UN DÍA ===
        if current_time - self.daily_reset_time > 86400:  # 24 horas
            self.daily_request_count = 0
            self.daily_reset_time = current_time
            logger.debug("Contador diario de peticiones reseteado")
        
        # === 4. VERIFICAR LÍMITE DIARIO ===
        if self.daily_request_count >= self.daily_request_limit:
            user_msg = (
                f"📊 **Límite diario alcanzado**\n\n"
                f"Se han procesado {self.daily_request_limit} peticiones hoy.\n\n"
                f"⏱️ El límite se reinicia en las próximas horas.\n\n"
                f"💡 Intenta nuevamente mañana."
            )
            logger.warning(f"Límite diario alcanzado: {self.daily_request_count}/{self.daily_request_limit}")
            return False, user_msg
        
        # === 5. LIMPIAR Y VERIFICAR LÍMITE POR HORA ===
        # Auto-esperar en vez de bloquear para límite horario
        self.hourly_request_times = [t for t in self.hourly_request_times if current_time - t < 3600]
        if len(self.hourly_request_times) >= self.hourly_request_limit:
            oldest = self.hourly_request_times[0]
            wait_time = 3600 - (current_time - oldest)
            if wait_time <= 120:  # Si son 2 minutos o menos, esperar automáticamente
                logger.debug(f"⏳ Límite horario alcanzado, esperando {wait_time:.0f}s automáticamente...")
                await asyncio.sleep(wait_time + 1)
                self.hourly_request_times = [t for t in self.hourly_request_times if time.time() - t < 3600]
            else:
                minutes = int(wait_time // 60)
                user_msg = (
                    f"⏸️ **Muchas peticiones esta hora**\n\n"
                    f"Se han procesado {self.hourly_request_limit} peticiones en la última hora.\n\n"
                    f"⏱️ **Tiempo estimado:** ~{minutes} minutos\n\n"
                    f"💡 El bot reanudará automáticamente cuando sea seguro."
                )
                logger.warning(f"Límite por hora alcanzado: {len(self.hourly_request_times)}/{self.hourly_request_limit}")
                return False, user_msg
        
        # === 6. LIMPIAR Y VERIFICAR LÍMITE POR MINUTO (AUTO-ESPERAR) ===
        self.request_times = [t for t in self.request_times if current_time - t < 60]
        if len(self.request_times) >= self.request_limit_per_minute:
            wait_time = 60 - (current_time - self.request_times[0])
            if wait_time > 0:
                logger.debug(f"⏳ Rate limit por minuto alcanzado. Auto-esperando {wait_time:.1f}s...")
                await asyncio.sleep(wait_time + 0.5)
                self.request_times = [t for t in self.request_times if time.time() - t < 60]
        
        # === 7. VERIFICAR LÍMITE POR USUARIO POR MINUTO (AUTO-ESPERAR) ===
        if user_id:
            if user_id not in self.user_request_times:
                self.user_request_times[user_id] = []
            
            self.user_request_times[user_id] = [
                t for t in self.user_request_times[user_id] if current_time - t < 60
            ]
            
            if len(self.user_request_times[user_id]) >= self.user_request_limit_per_minute:
                wait_time = 60 - (current_time - self.user_request_times[user_id][0])
                if wait_time > 0:
                    logger.debug(f"⏳ Límite por usuario alcanzado para {user_id}. Auto-esperando {wait_time:.1f}s...")
                    await asyncio.sleep(wait_time + 0.5)
                    self.user_request_times[user_id] = [
                        t for t in self.user_request_times[user_id] if time.time() - t < 60
                    ]
            
            self.user_request_times[user_id].append(time.time())
        
        # === 8. DELAY MÍNIMO ENTRE PETICIONES ===
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.min_delay_between_requests:
            wait_time = self.min_delay_between_requests - time_since_last
            await asyncio.sleep(wait_time)
        
        # === REGISTRAR PETICIÓN ===
        self.last_request_time = time.time()
        self.request_times.append(self.last_request_time)
        self.hourly_request_times.append(self.last_request_time)
        self.request_count += 1
        self.daily_request_count += 1
        
        return True, None
    
    def register_flood_wait(self, wait_seconds: int, api_method: str = ""):
        """Registrar un FloodWait recibido de Telegram.

        FloodWait warnings (e.g. for ``upload.SaveBigFilePart`` or
        ``upload.GetFile``) are **normal** Telegram rate-limiting signals.
        They do NOT indicate account risk.  Telegram throttles large file
        operations to balance server load, especially during upload/download
        of files >100 MB.  Pyrogram automatically waits the required time
        and retries the request, so the transfer always continues.

        The bot only pauses the *user queue* when it receives many
        consecutive FloodWaits in a short period, as a safety measure.

        Args:
            wait_seconds: Seconds that Telegram requested to wait.
            api_method: The Telegram API method that triggered the wait
                        (e.g. ``upload.SaveBigFilePart``).
        """
        self.flood_wait_until = time.time() + wait_seconds
        self.flood_wait_count += 1
        method_info = f" [{api_method}]" if api_method else ""
        logger.info(
            f"⏳ FloodWait{method_info}: esperando {wait_seconds}s "
            f"(normal para archivos grandes – "
            f"consecutivos: {self.flood_wait_count}/{self.max_flood_waits})"
        )
    
    def reset_flood_wait(self):
        """Resetear el contador de FloodWait después de una operación exitosa"""
        if self.flood_wait_count > 0:
            self.flood_wait_count = 0
            logger.debug("✅ FloodWait counter reseteado después de operación exitosa")

    async def check_channel_has_protection(self, chat: Any) -> bool:
        """Check whether a Telegram chat has content protection enabled.

        Args:
            chat: A Pyrogram ``Chat`` object.

        Returns:
            True if the chat has protected content (defaults to True on error).
        """
        try:
            has_protection = getattr(chat, 'has_protected_content', False)
            title = getattr(chat, 'title', 'unknown')
            logger.debug(f"Canal {title} - Protección: {'SÍ' if has_protection else 'NO'}")
            return has_protection
        except Exception as e:
            logger.warning(f"No se pudo verificar protección: {e}")
            return True  # Asumir protección por seguridad
    
    async def copy_content(self, channel_url: str, message_id: int, is_premium: bool = False, intermediate_channel_id: int = None):
        """Copiar contenido de un canal usando Pyrogram (envío directo, sin canal intermedio)
        
        NUEVA ESTRATEGIA con Pyrogram:
        1. Obtener el mensaje del canal fuente
        2. El mensaje se descargará y enviará directamente al usuario cuando sea necesario
        
        Returns:
            Tuple: (message, error, has_protection, via_intermediate_info)
        """
        try:
            allowed, rate_msg = await self.rate_limit_check()
            if not allowed:
                return None, rate_msg, False, None
            
            if not await self.ensure_connected():
                return None, "❌ Userbot no conectado. Configúralo primero.", False, None
            
            is_private = self.is_private_channel_link(channel_url)
            if is_private and not is_premium:
                return None, "🔒 Este es un canal privado. Necesitas la versión Premium.", False, None
            
            username = self.extract_username(channel_url)
            if not username:
                return None, "❌ URL de canal inválida", False, None
            
            logger.debug(f"Accediendo al canal: {username} (privado: {is_private})")
            
            try:
                # Obtener chat con Pyrogram
                chat_id = int(username) if is_private else username
                chat = await self.client.get_chat(chat_id)
                
                title = getattr(chat, 'title', username)
                logger.debug(f"Canal encontrado: {title}")
                
                has_protection = await self.check_channel_has_protection(chat)
                
                # Obtener mensaje con Pyrogram
                messages = await self.client.get_messages(chat.id, message_id)
                message = messages if not isinstance(messages, list) else (messages[0] if messages else None)
                
                if not message or message.empty:
                    return None, "❌ Mensaje no encontrado", has_protection, None
                
                logger.debug(f"✅ Mensaje {message.id} obtenido - Protección: {'SÍ' if has_protection else 'NO'}")
                self.reset_flood_wait()
                return message, None, has_protection, None
                    
            except ChannelPrivateError:
                raise ChannelAccessError(
                    "Canal privado inaccesible",
                    user_message=(
                        "❌ **No tienes acceso a este canal privado**\n\n"
                        "🔑 **Para acceder al contenido:**\n\n"
                        "**PASO 1:** Obtén el enlace de invitación del admin\n"
                        "   • Formato: `https://t.me/+ABC123...`\n\n"
                        "**PASO 2:** Envía el enlace de invitación aquí\n\n"
                        "**PASO 3:** Envía el enlace del contenido a extraer"
                    )
                )
            except UsernameNotOccupiedError:
                return None, "❌ Canal no encontrado", False, None
            except FloodWaitError as fw:
                wait_seconds = fw.value
                api_method = getattr(fw, 'x', '') or ''
                self.register_flood_wait(wait_seconds, api_method=str(api_method))
                if wait_seconds <= 120:
                    await asyncio.sleep(wait_seconds + 2)
                    self.flood_wait_until = 0
                    return None, f"🔄 FloodWait completado ({wait_seconds}s). Intenta de nuevo.", False, None
                else:
                    minutes = wait_seconds // 60
                    return None, f"⏸️ **Telegram pidió una pausa**\n\n⏱️ ~{minutes} minutos\n\n🔄 Intenta después.", False, None
            except ValueError as e:
                err_str = str(e)
                if 'Peer id invalid' in err_str or 'ID not found' in err_str:
                    logger.warning(f"Peer no encontrado en caché: {err_str}")
                    raise ChannelAccessError(
                        f"Peer no encontrado: {err_str}",
                        user_message=(
                            "❌ **El bot no tiene acceso a este canal**\n\n"
                            "El userbot no ha visitado o no se ha unido a este canal.\n\n"
                            "🔑 **Soluciones:**\n"
                            "1. Envía primero el enlace de invitación del canal\n"
                            "2. Asegúrate de que el userbot se haya unido al canal\n"
                            "3. Intenta nuevamente después de unirse"
                        )
                    )
                logger.error(f"Error accediendo al canal: {e}")
                return None, f"❌ Error accediendo al canal: {str(e)}", False, None
            except Exception as e:
                logger.error(f"Error accediendo al canal: {e}")
                return None, f"❌ Error accediendo al canal: {str(e)}", False, None
                
        except ChannelAccessError as cae:
            return None, cae.user_message, False, None
        except FloodWaitError as fw:
            wait_seconds = fw.value
            api_method = getattr(fw, 'x', '') or ''
            self.register_flood_wait(wait_seconds, api_method=str(api_method))
            if wait_seconds <= 120:
                await asyncio.sleep(wait_seconds + 2)
                self.flood_wait_until = 0
                return None, f"🔄 FloodWait completado. Intenta de nuevo.", False, None
            else:
                minutes = wait_seconds // 60
                return None, f"⏸️ **Pausa de ~{minutes} minutos**", False, None
        except Exception as e:
            logger.error(f"Error general en copy_content: {e}")
            return None, f"❌ Error general: {str(e)}", False, None

    async def bulk_copy(self, channel_url: str, limit: int = 10):
        """Copia masiva de contenido (solo premium) - Pyrogram"""
        try:
            allowed, rate_msg = await self.rate_limit_check()
            if not allowed:
                return None, rate_msg
            
            if not await self.ensure_connected():
                return None, "❌ Userbot no conectado. Configúralo primero."
            
            username = self.extract_username(channel_url)
            if not username:
                return None, "❌ URL de canal inválida"
            
            logger.debug(f"Copia masiva de {username}, límite: {limit}")
            
            try:
                chat_id = int(username) if username.lstrip('-').isdigit() else username
                chat = await self.client.get_chat(chat_id)
                logger.debug(f"Canal encontrado: {getattr(chat, 'title', username)}")
            except ValueError as e:
                if 'Peer id invalid' in str(e) or 'ID not found' in str(e):
                    return None, "❌ El bot no tiene acceso a este canal. Envía primero el enlace de invitación."
                return None, f"❌ Error accediendo al canal: {str(e)}"
            except Exception as e:
                return None, f"❌ Error accediendo al canal: {str(e)}"
            
            try:
                messages = []
                async for msg in self.client.get_chat_history(chat.id, limit=limit):
                    messages.append(msg)
                logger.debug(f"Obtenidos {len(messages)} mensajes")
                return messages, None
            except Exception as e:
                return None, f"❌ Error obteniendo mensajes: {str(e)}"
            
        except Exception as e:
            return None, f"❌ Error en copia masiva: {str(e)}"

    async def get_channel_info(self, channel_url: str):
        """Obtener información del canal - Pyrogram"""
        try:
            allowed, rate_msg = await self.rate_limit_check()
            if not allowed:
                return None, rate_msg
            
            if not await self.ensure_connected():
                return None, "❌ Userbot no conectado. Configúralo primero."
            
            is_private = self.is_private_channel_link(channel_url)
            username = self.extract_username(channel_url)
            if not username:
                return None, "❌ URL inválida"
            
            try:
                chat_id = int(username) if is_private else username
                chat = await self.client.get_chat(chat_id)
            except ChannelPrivateError:
                return None, (
                    "❌ **No tienes acceso a este canal privado**\n\n"
                    "🔑 Envía primero el enlace de invitación para unirte."
                )
            except ValueError as e:
                if 'Peer id invalid' in str(e) or 'ID not found' in str(e):
                    return None, "❌ El bot no tiene acceso a este canal. Envía primero el enlace de invitación."
                return None, f"❌ Error accediendo al canal: {str(e)}"
            except Exception as e:
                return None, f"❌ Error accediendo al canal: {str(e)}"
            
            members_count = getattr(chat, 'members_count', 0) or 0
            
            info = {
                'title': getattr(chat, 'title', 'Sin título'),
                'username': getattr(chat, 'username', None),
                'id': chat.id,
                'participants_count': members_count,
                'is_private': is_private or not getattr(chat, 'username', None)
            }
            
            return info, None
            
        except Exception as e:
            logger.error(f"Error obteniendo info del canal: {e}")
            return None, f"❌ Error obteniendo info: {str(e)}"

    @staticmethod
    def extract_username(url: str) -> Optional[str]:
        """Extract a channel username or numeric ID from a Telegram URL.

        Private-channel URLs (``t.me/c/<ID>/...``) return a string like
        ``-100<ID>``.  Public-channel URLs return the plain username.

        Returns:
            The extracted identifier, or ``None`` if parsing failed.
        """
        # Verificar si es un canal privado (formato t.me/c/ID/mensaje)
        private_channel_match = re.search(r't\.me/c/(\d+)', url)
        if private_channel_match:
            # Retornar el ID como entero negativo con -100 prefijo
            channel_id = int(private_channel_match.group(1))
            return f"-100{channel_id}"
        
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
                # Ignorar 'c' que es usado para canales privados
                if username == 'c':
                    continue
                return username
        return None

    @staticmethod
    def extract_message_id(url: str) -> Optional[int]:
        """Extraer ID del mensaje de la URL.

        Soporta formatos:
          t.me/c/CHANNEL_ID/MSG_ID
          t.me/c/CHANNEL_ID/TOPIC_ID/MSG_ID  (foros/topics)
          t.me/USERNAME/MSG_ID
        Siempre retorna el ÚLTIMO número de la ruta (el message_id real).
        """
        # Para canales privados (t.me/c/ID/... — puede tener topic_id)
        private_match = re.search(r't\.me/c/\d+/([\d/]+)', url)
        if private_match:
            # Tomar el último segmento numérico: "1913/2242" → 2242
            segments = private_match.group(1).rstrip('/').split('/')
            return int(segments[-1])

        # Para canales públicos (t.me/username/MSG_ID o t.me/username/TOPIC/MSG_ID)
        match = re.search(r't\.me/[^/]+/([\d/]+)', url)
        if match:
            segments = match.group(1).rstrip('/').split('/')
            return int(segments[-1])
        return None
    
    @staticmethod
    def extract_invite_hash(url: str) -> Optional[str]:
        """Extraer hash de invitación de URL privada (+hash o joinchat)"""
        patterns = [
            r't\.me/\+(\w+)',
            r't\.me/joinchat/(\w+)',
            r'telegram\.me/\+(\w+)',
            r'telegram\.me/joinchat/(\w+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None
    
    @staticmethod
    def parse_link_with_count(text: str) -> Tuple[str, Optional[int], Optional[int]]:
        """Parsear enlace con opción de múltiples posts consecutivos
        
        Ejemplos:
        - https://t.me/c/3506591340/6 5 -> extrae desde mensaje 6, los siguientes 5 mensajes
        - https://t.me/canal/123 3 -> extrae desde mensaje 123, los siguientes 3 mensajes
        - https://t.me/canal/123 -> extrae solo el mensaje 123
        
        Returns:
            Tuple[str, Optional[int], Optional[int]]: (url, message_id, count)
        """
        parts = text.strip().split()
        url = parts[0]
        message_id = ContentCopyBot.extract_message_id(url)
        count = None
        
        # Verificar si hay un número después del URL
        if len(parts) > 1 and parts[1].isdigit():
            count = int(parts[1])
            # Sin límite de mensajes - el sistema de rate limiting de Telegram ya gestiona las pausas
            # (El RateLimiter interno pausa automáticamente cada 50 mensajes para respetar límites)
        
        return url, message_id, count
    
    @staticmethod
    def is_private_channel_link(url: str) -> bool:
        """Return True if *url* points to a private Telegram channel (``t.me/c/...``)."""
        return bool(re.search(r't\.me/c/\d+', url))
    
    async def join_private_channel_by_hash(self, invite_hash: str, user_id: int = None) -> Tuple[bool, Optional[str], Optional[str]]:
        """Unirse a un canal privado mediante hash de invitación - Pyrogram"""
        try:
            if not await self.ensure_connected():
                return False, "❌ Userbot no conectado", 'error'
            
            invite_link = f"https://t.me/+{invite_hash}"
            
            try:
                chat = await self.client.join_chat(invite_link)
                channel_title = getattr(chat, 'title', 'Canal')
                logger.info(f"Unido exitosamente al canal: {channel_title}")
                return True, None, 'joined'
                
            except UserAlreadyParticipantError:
                return True, None, 'already_member'
            
            except InviteHashExpiredError:
                return False, "❌ El enlace de invitación ha expirado", 'expired'
            
            except InviteHashInvalidError:
                return False, "❌ El enlace de invitación es inválido", 'invalid'
            
            except Exception as e:
                error_str = str(e).lower()
                
                # Detectar solicitud pendiente de aprobación
                pending_patterns = ["successfully requested", "join request", "waiting for approval"]
                is_pending = any(p in error_str for p in pending_patterns)
                
                if is_pending:
                    logger.info(f"✅ Solicitud de unión enviada (requiere aprobación)")
                    if user_id:
                        self.pending_join[user_id] = {
                            'invite_hash': invite_hash,
                            'invite_link': invite_link,
                            'channel_title': 'Canal',
                            'status': 'pending_approval',
                            'timestamp': time.time()
                        }
                    return False, None, 'pending_approval'
                
                return False, f"❌ Error al unirse al canal: {str(e)}", 'error'
                
        except Exception as e:
            return False, f"❌ Error general: {str(e)}", 'error'
    
    def _convert_entities_to_telegram_format(self, message: Any) -> Optional[list]:
        """Convert Pyrogram message entities to python-telegram-bot format.

        Args:
            message: A Pyrogram ``Message`` with optional ``.entities``.

        Returns:
            A list of ``telegram.MessageEntity`` objects, or ``None``.
        """
        from telegram import MessageEntity
        from pyrogram.enums import MessageEntityType
        
        if not message.entities:
            return None
        
        type_map = {
            MessageEntityType.BOLD: MessageEntity.BOLD,
            MessageEntityType.ITALIC: MessageEntity.ITALIC,
            MessageEntityType.CODE: MessageEntity.CODE,
            MessageEntityType.PRE: MessageEntity.PRE,
            MessageEntityType.TEXT_LINK: MessageEntity.TEXT_LINK,
            MessageEntityType.MENTION: MessageEntity.MENTION,
            MessageEntityType.URL: MessageEntity.URL,
            MessageEntityType.UNDERLINE: MessageEntity.UNDERLINE,
            MessageEntityType.STRIKETHROUGH: MessageEntity.STRIKETHROUGH,
            MessageEntityType.SPOILER: MessageEntity.SPOILER,
        }
        
        entities = []
        for entity in message.entities:
            tg_type = type_map.get(entity.type)
            if tg_type:
                entities.append(MessageEntity(
                    type=tg_type,
                    offset=entity.offset,
                    length=entity.length,
                    url=getattr(entity, 'url', None),
                    language=getattr(entity, 'language', None)
                ))
        
        return entities if entities else None
    
    # ------------------------------------------------------------------
    # Helpers: cleanup & thumbnail
    # ------------------------------------------------------------------

    def _cleanup_temp_files(self, max_age_seconds: int = 3600, force: bool = False) -> int:
        """Remove stale temporary files from the download directory.

        Cleans up orphaned .tmp, .jpg (thumbnails), and split directories
        left over from failed or interrupted transfers.

        **IMPORTANT**: If ``_transfer_active`` is True (a download/upload
        is in progress), this method does NOTHING unless *force* is True.
        This prevents the heartbeat from deleting files that are being
        uploaded, which was the root cause of the upload-failure bug.

        Args:
            max_age_seconds: Files older than this are removed.
                Use 0 to remove ALL temp files (startup cleanup).
            force: If True, ignore ``_transfer_active`` flag.
                Only used at startup before any transfers begin.

        Returns:
            Number of bytes freed.
        """
        # ---- GUARD: never delete files during an active transfer ----
        if self._transfer_active and not force:
            logger.debug(
                "🛡️ Cleanup omitido: transferencia activa "
                "(archivos protegidos contra borrado)"
            )
            return 0

        freed = 0
        now = time.time()
        try:
            # Clean temp files (.tmp, .jpg thumbnails)
            for pattern in ('*.tmp', '*.jpg', '*.part*'):
                for fpath in glob_module.glob(
                    os_module.path.join(self.temp_dir, pattern)
                ):
                    try:
                        age = now - os_module.path.getmtime(fpath)
                        if max_age_seconds == 0 or age > max_age_seconds:
                            size = os_module.path.getsize(fpath)
                            os_module.unlink(fpath)
                            freed += size
                    except Exception:
                        pass

            # Clean split directories (tg_split_*)
            for dpath in glob_module.glob(
                os_module.path.join(self.temp_dir, 'tg_split_*')
            ):
                try:
                    if os_module.path.isdir(dpath):
                        age = now - os_module.path.getmtime(dpath)
                        if max_age_seconds == 0 or age > max_age_seconds:
                            dir_size = sum(
                                os_module.path.getsize(
                                    os_module.path.join(dp, f)
                                )
                                for dp, _, fnames in os_module.walk(dpath)
                                for f in fnames
                            )
                            shutil.rmtree(dpath, ignore_errors=True)
                            freed += dir_size
                except Exception:
                    pass

            if freed > 0:
                logger.info(
                    f"🧹 Limpieza temporal: {freed / (1024*1024):.1f} MB liberados "
                    f"de {self.temp_dir}"
                )
        except Exception as e:
            logger.warning(f"Error en limpieza temporal: {e}")
        return freed

    def _get_disk_free(self) -> int:
        """Return free disk space in bytes for the temp download directory.

        Uses the ACTUAL partition where temp files are stored, not /tmp
        which may be a different (smaller) partition.
        """
        try:
            stat = shutil.disk_usage(self.temp_dir)
            return stat.free
        except Exception:
            # Fallback to /tmp if custom dir fails
            try:
                stat = shutil.disk_usage('/tmp')
                return stat.free
            except Exception:
                return 0

    async def _reserve_disk_space(self, needed_bytes: int) -> bool:
        """Reserve disk space for a download. Returns True if space is available.
        
        Takes into account:
        - Actual free disk space
        - Space already reserved by other concurrent transfers
        - The server's 4.88 GB total disk limit
        - Minimum reserve for system operation (500 MB)
        """
        async with self._disk_lock:
            disk_free = self._get_disk_free()
            effective_free = disk_free - self._reserved_disk_bytes - self._disk_reserve_bytes
            
            if effective_free < needed_bytes:
                # Try cleanup first
                self._cleanup_temp_files(max_age_seconds=300)
                disk_free = self._get_disk_free()
                effective_free = disk_free - self._reserved_disk_bytes - self._disk_reserve_bytes
            
            if effective_free >= needed_bytes:
                self._reserved_disk_bytes += needed_bytes
                logger.debug(
                    f"💾 Disco reservado: +{needed_bytes/(1024*1024):.1f} MB "
                    f"(total reservado: {self._reserved_disk_bytes/(1024*1024):.1f} MB, "
                    f"libre real: {disk_free/(1024*1024):.0f} MB)"
                )
                return True
            
            logger.warning(
                f"⚠️ Espacio insuficiente para reservar {needed_bytes/(1024*1024):.1f} MB. "
                f"Libre efectivo: {effective_free/(1024*1024):.0f} MB "
                f"(libre real: {disk_free/(1024*1024):.0f} MB, "
                f"reservado: {self._reserved_disk_bytes/(1024*1024):.0f} MB, "
                f"sistema: {self._disk_reserve_bytes/(1024*1024):.0f} MB)"
            )
            return False
    
    async def _release_disk_space(self, reserved_bytes: int) -> None:
        """Release previously reserved disk space."""
        async with self._disk_lock:
            self._reserved_disk_bytes = max(0, self._reserved_disk_bytes - reserved_bytes)
            logger.debug(
                f"💾 Disco liberado: -{reserved_bytes/(1024*1024):.1f} MB "
                f"(total reservado: {self._reserved_disk_bytes/(1024*1024):.1f} MB)"
            )
    
    async def _increment_active_transfers(self) -> None:
        """Increment active transfer counter and set legacy flag."""
        async with self._active_transfers_lock:
            self._active_transfers += 1
            self._transfer_active = True
            logger.debug(f"📊 Transferencias activas: {self._active_transfers}")
    
    async def _decrement_active_transfers(self) -> None:
        """Decrement active transfer counter and clear legacy flag if zero."""
        async with self._active_transfers_lock:
            self._active_transfers = max(0, self._active_transfers - 1)
            if self._active_transfers == 0:
                self._transfer_active = False
            logger.debug(f"📊 Transferencias activas: {self._active_transfers}")

    async def _download_thumbnail(self, message) -> Optional[str]:
        """Download the original thumbnail of a media message.

        Pyrogram's ``download_media`` accepts a ``file_id`` string to
        download any specific file – including thumbnail PhotoSizes.
        We pick the LARGEST available thumb for best quality.

        Returns:
            Absolute path to the JPEG thumbnail file, or ``None``.
        """
        try:
            thumb_obj = None
            for attr in ('video', 'document', 'audio', 'animation'):
                media = getattr(message, attr, None)
                if media and getattr(media, 'thumbs', None):
                    # Pick the largest thumbnail for best quality
                    thumbs = media.thumbs
                    thumb_obj = max(
                        thumbs,
                        key=lambda t: (getattr(t, 'file_size', 0) or 0)
                    )
                    break

            if not thumb_obj or not getattr(thumb_obj, 'file_id', None):
                return None

            with tempfile.NamedTemporaryFile(
                delete=False, suffix='.jpg', dir=self.temp_dir
            ) as tmp:
                thumb_path = tmp.name

            result = await self.client.download_media(
                thumb_obj.file_id,
                file_name=thumb_path
            )

            if result and os_module.path.exists(result):
                fsize = os_module.path.getsize(result)
                if fsize > 0:
                    logger.debug(f"🖼️ Thumbnail descargado: {fsize} bytes")
                    return result
                os_module.unlink(result)

            if os_module.path.exists(thumb_path):
                os_module.unlink(thumb_path)
            return None

        except Exception as e:
            logger.debug(f"Thumbnail no disponible: {e}")
            return None

    # ------------------------------------------------------------------
    # Main send method
    # ------------------------------------------------------------------

    # NOTE: _try_zero_disk_forward removed — replaced by _try_zero_disk_to_intermediate
    # which sends to the intermediate channel instead of directly to the user.

    async def _send_message_content(self, context, chat_id: int, message, progress_callback=None, cancel_flag=None):
        """Send content to the user via the BOT (not the userbot).

        NUEVA ARQUITECTURA:
          El userbot NUNCA envía al usuario directamente.
          El bot es quien envía al usuario usando el canal intermedio.

        Strategy:
          PHASE 1 — ZERO DISK: Intentar copiar al canal intermedio server-side
          PHASE 2 — DOWNLOAD + UPLOAD al canal intermedio (fallback)
          PHASE 3 — El BOT copia desde el canal intermedio al usuario

        Esto resuelve:
          - El userbot no envía al usuario (solo el bot lo hace)
          - Concurrencia: múltiples transferencias simultáneas via semáforo
          - Control de disco: reserva de espacio antes de descargar
        """
        TELEGRAM_HARD_LIMIT = 2000 * 1024 * 1024  # 2 GB
        reserved_bytes = 0

        try:
            caption = message.caption or message.text or None

            # --- Determine file size ---
            file_size = 0
            for attr in ('document', 'video', 'audio', 'voice', 'photo'):
                media = getattr(message, attr, None)
                if media:
                    file_size = getattr(media, 'file_size', 0) or 0
                    break

            if file_size > TELEGRAM_HARD_LIMIT:
                raise FileTransferError(
                    f"Archivo excede 2 GB ({file_size/(1024*1024):.1f}MB)",
                    file_size=file_size,
                    user_message=(
                        f"❌ **Archivo demasiado grande** "
                        f"({file_size/(1024*1024):.1f} MB)\n\n"
                        f"Telegram no permite archivos mayores a 2 GB."
                    )
                )

            size_mb = file_size / (1024 * 1024) if file_size > 0 else 10

            file_path = None
            thumb_path = None

            # ====== Acquire semaphore for concurrent transfer control ======
            async with self._transfer_semaphore:
                await self._increment_active_transfers()
                try:
                    # ====== CASE 1: Plain text — bot sends directly ======
                    if not message.media and message.text:
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text=message.text
                        )
                        return {'via_intermediate': False}

                    # ==========================================================
                    # PHASE 1: ZERO-DISK — copiar al canal intermedio server-side
                    # ==========================================================
                    intermediate_msg = await self._try_zero_disk_to_intermediate(message)
                    if intermediate_msg:
                        # Bot copia desde intermedio al usuario
                        await self._bot_forward_from_intermediate(
                            context, chat_id, intermediate_msg, caption
                        )
                        return {'via_intermediate': True}

                    # ==========================================================
                    # PHASE 2: DOWNLOAD + UPLOAD al canal intermedio
                    # ==========================================================
                    logger.info(
                        f"⚠️ Zero-disk falló para msg {message.id}. "
                        f"Descarga+upload ({size_mb:.1f} MB)…"
                    )

                    # --- Reserve disk space BEFORE downloading ---
                    overhead = 20 * 1024 * 1024  # 20 MB overhead
                    needed = file_size + overhead
                    reserved_bytes = needed

                    if not await self._reserve_disk_space(needed):
                        raise FileTransferError(
                            f"Espacio insuficiente para {size_mb:.1f} MB",
                            file_size=file_size,
                            user_message=(
                                f"❌ **Espacio insuficiente en disco**\n\n"
                                f"📁 Archivo: {size_mb:.1f} MB\n"
                                f"💾 Disco del servidor: {self._server_disk_limit/(1024*1024*1024):.2f} GB\n\n"
                                f"Hay otras descargas en curso que ocupan espacio.\n\n"
                                f"💡 **Soluciones:**\n"
                                f"• Espera a que terminen las descargas actuales\n"
                                f"• Intenta con un archivo más pequeño"
                            )
                        )

                    # --- Timeout GENEROSO para descargas ---
                    # Con FloodWaits de upload.GetFile en descargas concurrentes,
                    # la velocidad efectiva puede bajar mucho.
                    # Fórmula: 1 MB/s worst case + 300s buffer
                    timeout = max(size_mb / 1.0 + 300.0, 600.0)
                    timeout = min(timeout, 10800.0)  # máximo 3 horas

                    try:
                        # --- Photo ---
                        if message.photo:
                            logger.debug("📸 Descargando foto → canal intermedio…")
                            with tempfile.NamedTemporaryFile(
                                delete=False, suffix='.jpg', dir=self.temp_dir
                            ) as tmp:
                                file_path = tmp.name
                            downloaded = await self.client.download_media(
                                message, file_name=file_path
                            )
                            if downloaded and os_module.path.exists(downloaded):
                                file_path = downloaded
                                intermediate_msg = await self.client.send_photo(
                                    chat_id=self.intermediate_channel_id,
                                    photo=file_path,
                                    caption=caption
                                )
                                await self._bot_forward_from_intermediate(
                                    context, chat_id, intermediate_msg, caption
                                )
                            return {'via_intermediate': True}

                        # --- Sticker ---
                        if message.sticker:
                            logger.debug("🎭 Descargando sticker → canal intermedio…")
                            with tempfile.NamedTemporaryFile(
                                delete=False, suffix='.webp', dir=self.temp_dir
                            ) as tmp:
                                file_path = tmp.name
                            downloaded = await self.client.download_media(
                                message, file_name=file_path
                            )
                            if downloaded and os_module.path.exists(downloaded):
                                file_path = downloaded
                                intermediate_msg = await self.client.send_sticker(
                                    chat_id=self.intermediate_channel_id,
                                    sticker=file_path
                                )
                                await self._bot_forward_from_intermediate(
                                    context, chat_id, intermediate_msg, caption
                                )
                            return {'via_intermediate': True}

                        # --- Media files (video/doc/audio/voice/GIF) ---
                        if message.video or message.document or message.audio or message.voice or message.animation:
                            media_type = (
                                "video" if message.video else
                                "documento" if message.document else
                                "audio" if message.audio else
                                "voz" if message.voice else "GIF"
                            )

                            disk_free = self._get_disk_free()
                            logger.info(
                                f"📥 Descargando {media_type} ({size_mb:.1f} MB), "
                                f"disco libre: {disk_free/(1024*1024):.0f} MB…"
                            )

                            # Temp file for download
                            with tempfile.NamedTemporaryFile(
                                delete=False, suffix='.tmp', dir=self.temp_dir
                            ) as tmp_file:
                                file_path = tmp_file.name

                            # --- Download thumbnail ---
                            thumb_path = await self._download_thumbnail(message)

                            # --- DOWNLOAD with progress ---
                            if progress_callback and hasattr(progress_callback, '__self__'):
                                tracker = progress_callback.__self__
                                if hasattr(tracker, 'phase'):
                                    tracker.phase = "download"

                            download_start = time.time()
                            downloaded_path = await asyncio.wait_for(
                                self.client.download_media(
                                    message,
                                    file_name=file_path,
                                    progress=progress_callback
                                ),
                                timeout=timeout
                            )

                            if not downloaded_path or not os_module.path.exists(downloaded_path):
                                raise FileTransferError(
                                    f"Descarga fallida: {media_type}",
                                    user_message=f"❌ No se pudo descargar el {media_type}"
                                )

                            file_path = downloaded_path
                            actual_size = os_module.path.getsize(file_path)
                            dl_time = time.time() - download_start
                            speed = actual_size / (1024*1024*dl_time) if dl_time > 0 else 0
                            logger.info(
                                f"✅ Descarga completada: {actual_size/(1024*1024):.1f} MB "
                                f"en {dl_time:.1f}s ({speed:.1f} MB/s)"
                            )

                            # --- SWITCH to UPLOAD phase ---
                            if progress_callback:
                                try:
                                    await progress_callback(actual_size, actual_size)
                                except Exception:
                                    pass

                            # --- UPLOAD to INTERMEDIATE CHANNEL (not to user!) ---
                            logger.info(
                                f"📤 Subiendo {media_type} ({actual_size/(1024*1024):.1f} MB) "
                                f"al canal intermedio {self.intermediate_channel_id}…"
                            )

                            # Timeout GENEROSO para uploads:
                            # - Con 3 uploads concurrentes, Pyrogram recibe FloodWaits
                            #   de 5s por cada upload.SaveBigFilePart, que se acumulan
                            # - Un archivo de 1.7 GB con FloodWaits puede tardar 20+ min
                            # - Fórmula: base speed 0.5 MB/s (peor caso con throttling)
                            #   + 600s buffer para FloodWaits acumulados
                            upload_timeout = max(
                                actual_size / (1024*1024) / 0.5 + 600.0,  # 0.5 MB/s worst case
                                1200.0  # mínimo 20 minutos
                            )
                            upload_timeout = min(upload_timeout, 14400.0)  # máximo 4 horas
                            upload_start = time.time()

                            _thumb = (
                                thumb_path
                                if thumb_path and os_module.path.exists(thumb_path)
                                else None
                            )

                            intermediate_msg = None
                            if message.video:
                                intermediate_msg = await asyncio.wait_for(
                                    self.client.send_video(
                                        chat_id=self.intermediate_channel_id,
                                        video=file_path,
                                        caption=caption,
                                        thumb=_thumb,
                                        duration=message.video.duration or 0,
                                        width=message.video.width or 0,
                                        height=message.video.height or 0,
                                        supports_streaming=True,
                                        progress=progress_callback
                                    ),
                                    timeout=upload_timeout
                                )
                            elif message.document:
                                file_name = message.document.file_name or 'document'
                                intermediate_msg = await asyncio.wait_for(
                                    self.client.send_document(
                                        chat_id=self.intermediate_channel_id,
                                        document=file_path,
                                        caption=caption,
                                        thumb=_thumb,
                                        file_name=file_name,
                                        progress=progress_callback
                                    ),
                                    timeout=upload_timeout
                                )
                            elif message.audio:
                                intermediate_msg = await asyncio.wait_for(
                                    self.client.send_audio(
                                        chat_id=self.intermediate_channel_id,
                                        audio=file_path,
                                        caption=caption,
                                        thumb=_thumb,
                                        duration=getattr(message.audio, 'duration', 0),
                                        performer=getattr(message.audio, 'performer', None),
                                        title=getattr(message.audio, 'title', None),
                                        progress=progress_callback
                                    ),
                                    timeout=upload_timeout
                                )
                            elif message.voice:
                                intermediate_msg = await asyncio.wait_for(
                                    self.client.send_voice(
                                        chat_id=self.intermediate_channel_id,
                                        voice=file_path,
                                        caption=caption,
                                        progress=progress_callback
                                    ),
                                    timeout=upload_timeout
                                )
                            elif message.animation:
                                intermediate_msg = await asyncio.wait_for(
                                    self.client.send_animation(
                                        chat_id=self.intermediate_channel_id,
                                        animation=file_path,
                                        caption=caption,
                                        thumb=_thumb,
                                        progress=progress_callback
                                    ),
                                    timeout=upload_timeout
                                )

                            upload_time = time.time() - upload_start
                            up_speed = actual_size / (1024*1024*upload_time) if upload_time > 0 else 0
                            logger.info(
                                f"✅ Upload al canal intermedio completado: "
                                f"{actual_size/(1024*1024):.1f} MB "
                                f"en {upload_time:.1f}s ({up_speed:.1f} MB/s)"
                            )

                            # --- PHASE 3: Bot forwards from intermediate to user ---
                            if intermediate_msg:
                                await self._bot_forward_from_intermediate(
                                    context, chat_id, intermediate_msg, caption
                                )

                            return {'via_intermediate': True}

                        # Fallback for unknown types
                        if message.text:
                            await context.bot.send_message(
                                chat_id=chat_id, text=message.text
                            )
                            return {'via_intermediate': False}
                        raise ValueError(
                            "Mensaje sin contenido que se pueda copiar"
                        )

                    finally:
                        # Clean up temp files
                        for p in (file_path, thumb_path):
                            if p and os_module.path.exists(p):
                                try:
                                    os_module.unlink(p)
                                except Exception as ce:
                                    logger.warning(f"⚠️ Limpieza fallida: {ce}")
                        gc.collect()

                        # Release reserved disk space
                        if reserved_bytes > 0:
                            await self._release_disk_space(reserved_bytes)

                finally:
                    await self._decrement_active_transfers()

        except FloodWaitError as fw:
            wait_seconds = fw.value
            api_method = getattr(fw, 'x', '') or ''
            self.register_flood_wait(wait_seconds, api_method=str(api_method))
            if wait_seconds <= 120:
                logger.info(
                    f"⏳ FloodWait corto ({wait_seconds}s) – "
                    f"esperando automáticamente…"
                )
                await asyncio.sleep(wait_seconds + 2)
                self.flood_wait_until = 0
                raise RateLimitError(
                    f"FloodWait de {wait_seconds}s completado",
                    wait_seconds=wait_seconds,
                    user_message=(
                        f"🔄 FloodWait de {wait_seconds}s completado. "
                        f"Reintentando…"
                    )
                )
            else:
                minutes = wait_seconds // 60
                raise RateLimitError(
                    f"FloodWait largo: {wait_seconds}s",
                    wait_seconds=wait_seconds,
                    user_message=f"⏸️ **Pausa de ~{minutes} minutos**"
                )
        except FileTransferError:
            raise
        except (asyncio.TimeoutError, TimeoutError) as e:
            # asyncio.TimeoutError tiene str() vacío, loggear con contexto
            logger.error(
                f"⏱️ TimeoutError en _send_message_content: "
                f"archivo de {size_mb:.1f} MB (upload al canal intermedio)"
            )
            raise FileTransferError(
                f"Timeout subiendo archivo de {size_mb:.1f} MB",
                file_size=file_size,
                user_message=(
                    f"⏱️ **Timeout al subir archivo** ({size_mb:.0f} MB)\n\n"
                    f"La subida al servidor tardó demasiado.\n"
                    f"Esto puede pasar con archivos muy grandes o cuando\n"
                    f"hay varias descargas simultáneas.\n\n"
                    f"💡 **Intenta nuevamente** — el archivo se procesará\n"
                    f"cuando haya menos tráfico."
                )
            )
        except Exception as e:
            logger.error(f"Error en _send_message_content: {type(e).__name__}: {e}")
            raise

    # ------------------------------------------------------------------
    # Intermediate channel helpers
    # ------------------------------------------------------------------

    async def _try_zero_disk_to_intermediate(self, message) -> Optional[Any]:
        """Try to copy message to intermediate channel server-side (0 disk).
        
        Returns the intermediate channel message if successful, None otherwise.
        """
        source_chat = message.chat.id
        source_msg = message.id

        # --- Strategy 1: copy_message to intermediate ---
        try:
            logger.debug("🔄 [0-disco→intermedio] Intentando copy_message…")
            result = await self.client.copy_message(
                chat_id=self.intermediate_channel_id,
                from_chat_id=source_chat,
                message_id=source_msg
            )
            logger.debug("✅ copy_message a intermedio exitoso (0 disco)")
            return result
        except Exception as e1:
            logger.debug(f"copy_message a intermedio falló: {type(e1).__name__}")

        # --- Strategy 2: forward_messages to intermediate ---
        try:
            logger.debug("🔄 [0-disco→intermedio] Intentando forward_messages…")
            result = await self.client.forward_messages(
                chat_id=self.intermediate_channel_id,
                from_chat_id=source_chat,
                message_ids=source_msg
            )
            if isinstance(result, list):
                result = result[0] if result else None
            logger.debug("✅ forward_messages a intermedio exitoso (0 disco)")
            return result
        except Exception as e2:
            logger.debug(f"forward_messages a intermedio falló: {type(e2).__name__}")

        # --- Strategy 3: Saved Messages relay to intermediate ---
        relay_msg = None
        try:
            logger.debug("🔄 [0-disco→intermedio] Intentando relay via Saved Messages…")
            forwarded = await self.client.forward_messages(
                chat_id="me",
                from_chat_id=source_chat,
                message_ids=source_msg
            )
            relay_msg = forwarded if not isinstance(forwarded, list) else forwarded[0]

            if not relay_msg or getattr(relay_msg, 'empty', True):
                return None

            me = await self.client.get_me()
            my_id = me.id

            try:
                result = await self.client.copy_message(
                    chat_id=self.intermediate_channel_id,
                    from_chat_id=my_id,
                    message_id=relay_msg.id
                )
            except Exception:
                result = await self.client.forward_messages(
                    chat_id=self.intermediate_channel_id,
                    from_chat_id=my_id,
                    message_ids=relay_msg.id
                )
                if isinstance(result, list):
                    result = result[0] if result else None

            logger.info("✅ Relay via Saved Messages a intermedio exitoso (0 disco)")
            return result

        except Exception as e3:
            logger.debug(
                f"Relay via Saved Messages a intermedio falló: "
                f"{type(e3).__name__}: {e3}"
            )
            return None
        finally:
            if relay_msg and not getattr(relay_msg, 'empty', True):
                try:
                    await self.client.delete_messages("me", relay_msg.id)
                except Exception:
                    pass

    async def _bot_forward_from_intermediate(
        self, context, chat_id: int, intermediate_msg, caption: Optional[str] = None
    ) -> None:
        """Use the BOT to copy/forward a message from the intermediate channel to the user.
        
        This is the key difference: the BOT sends to the user, NOT the userbot.
        After forwarding, the intermediate message is deleted for cleanup.
        """
        inter_chat_id = self.intermediate_channel_id
        inter_msg_id = intermediate_msg.id if hasattr(intermediate_msg, 'id') else intermediate_msg

        try:
            # Try copy_message first (clean, no "forwarded from" header)
            try:
                await context.bot.copy_message(
                    chat_id=chat_id,
                    from_chat_id=inter_chat_id,
                    message_id=inter_msg_id
                )
                logger.debug(f"✅ Bot copió msg {inter_msg_id} desde intermedio a {chat_id}")
            except Exception as copy_err:
                logger.debug(f"Bot copy_message falló: {copy_err}, intentando forward…")
                # Fallback: forward (includes "forwarded from" header)
                await context.bot.forward_message(
                    chat_id=chat_id,
                    from_chat_id=inter_chat_id,
                    message_id=inter_msg_id
                )
                logger.debug(f"✅ Bot reenvió msg {inter_msg_id} desde intermedio a {chat_id}")
        except Exception as e:
            logger.error(
                f"❌ Bot no pudo enviar desde intermedio a {chat_id}: "
                f"{type(e).__name__}: {e}"
            )
            raise FileTransferError(
                f"Bot no pudo enviar al usuario: {e}",
                user_message=(
                    "❌ **Error al enviar el contenido**\n\n"
                    "El bot no pudo enviar el archivo al destino.\n\n"
                    "💡 Verifica que el bot tenga permisos en el canal destino "
                    "o intenta nuevamente."
                )
            )
        finally:
            # Cleanup: delete the intermediate message to free space
            try:
                await self.client.delete_messages(inter_chat_id, inter_msg_id)
                logger.debug(f"🧹 Mensaje intermedio {inter_msg_id} eliminado")
            except Exception as del_err:
                logger.debug(f"No se pudo eliminar msg intermedio: {del_err}")

    async def copy_multiple_messages(self, channel_url: str, start_message_id: int, count: int, is_premium: bool = False) -> Tuple[Optional[List], Optional[str], bool, Optional[Any]]:
        """Copiar múltiples mensajes consecutivos - Pyrogram"""
        try:
            if not is_premium:
                return None, "PREMIUM_REQUIRED", False, None
            
            allowed, rate_msg = await self.rate_limit_check()
            if not allowed:
                return None, rate_msg, False, None
            
            if not await self.ensure_connected():
                return None, "❌ Userbot no conectado.", False, None
            
            is_private = self.is_private_channel_link(channel_url)
            username = self.extract_username(channel_url)
            if not username:
                return None, "❌ URL de canal inválida", False, None
            
            logger.info(f"Copiando {count} mensajes desde {start_message_id} del canal: {username}")
            
            try:
                chat_id = int(username) if is_private else username
                chat = await self.client.get_chat(chat_id)
                has_protection = await self.check_channel_has_protection(chat)
            except ChannelPrivateError:
                return None, "NEEDS_JOIN", False, None
            except Exception as e:
                return None, f"❌ Error accediendo al canal: {str(e)}", False, None
            
            try:
                messages = []
                missing_messages = []
                message_ids = [start_message_id + i for i in range(count)]
                
                for expected_id in message_ids:
                    try:
                        msg = await self.client.get_messages(chat.id, expected_id)
                        if msg and not msg.empty:
                            messages.append(msg)
                        else:
                            missing_messages.append(expected_id)
                    except Exception:
                        missing_messages.append(expected_id)
                    await asyncio.sleep(0.1)
                
                logger.info(f"Obtenidos {len(messages)} de {count}. Faltantes: {len(missing_messages)}")
                return messages, None, has_protection, chat
                
            except Exception as e:
                return None, f"❌ Error al obtener mensajes: {str(e)}", False, None
                
        except Exception as e:
            return None, f"❌ Error general: {str(e)}", False, None
    
    async def copy_multiple_messages_filtered(self, channel_url: str, start_message_id: int, count: int, filters: Dict[str, bool], is_premium: bool = False) -> Tuple[Optional[List], Optional[str], bool, Optional[Any]]:
        """Copiar múltiples mensajes con filtros de tipo de contenido
        
        Args:
            channel_url: URL del canal
            start_message_id: ID del primer mensaje a copiar
            count: Número de mensajes filtrados a copiar
            filters: Diccionario con tipos de contenido a incluir
            is_premium: Si el usuario es premium
            
        Returns:
            Tuple[Optional[List], Optional[str], bool, Optional[Any]]: (messages, error, has_protection, entity)
        """
        try:
            if not is_premium:
                return None, "PREMIUM_REQUIRED", False, None
            
            allowed, rate_msg = await self.rate_limit_check()
            if not allowed:
                return None, rate_msg, False, None
            
            if not await self.ensure_connected():
                return None, "❌ Userbot no conectado.", False, None
            
            is_private = self.is_private_channel_link(channel_url)
            username = self.extract_username(channel_url)
            if not username:
                return None, "❌ URL de canal inválida", False, None
            
            try:
                chat_id_val = int(username) if is_private else username
                chat = await self.client.get_chat(chat_id_val)
                has_protection = await self.check_channel_has_protection(chat)
            except ChannelPrivateError:
                return None, "NEEDS_JOIN", False, None
            except Exception as e:
                return None, f"❌ Error accediendo al canal: {str(e)}", False, None
            
            try:
                filtered_messages = []
                current_id = start_message_id
                max_search = count * 5
                messages_checked = 0
                
                while len(filtered_messages) < count and messages_checked < max_search:
                    try:
                        msg = await self.client.get_messages(chat.id, current_id)
                        if msg and not msg.empty:
                            should_include = False
                            mime = getattr(msg.document, 'mime_type', '') if msg.document else ''
                            
                            if msg.video or (msg.document and 'video' in mime):
                                should_include = filters.get('videos', True)
                            elif msg.photo:
                                should_include = filters.get('photos', True)
                            elif msg.document and 'video' not in mime:
                                should_include = filters.get('documents', True)
                            elif msg.audio or msg.voice:
                                should_include = filters.get('audio', True)
                            elif msg.sticker:
                                should_include = filters.get('stickers', True)
                            elif msg.text and not msg.media:
                                should_include = filters.get('text', True)
                            
                            if should_include:
                                filtered_messages.append(msg)
                    except Exception:
                        pass
                    
                    current_id += 1
                    messages_checked += 1
                    await asyncio.sleep(0.1)
                
                logger.info(f"Filtrados: {len(filtered_messages)} de {count} ({messages_checked} revisados)")
                
                if not filtered_messages:
                    return None, f"❌ No se encontraron mensajes con los filtros activos", has_protection, chat
                
                return filtered_messages, None, has_protection, chat
                
            except Exception as e:
                return None, f"❌ Error al obtener mensajes: {str(e)}", False, None
                
        except Exception as e:
            return None, f"❌ Error general: {str(e)}", False, None

