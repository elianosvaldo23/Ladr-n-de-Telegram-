"""Centralized configuration - loads .env and defines all constants"""

import os
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ============== BOT CREDENTIALS ==============
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGODB_URI = os.getenv("MONGODB_URI")

try:
    ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
except ValueError:
    ADMIN_ID = 0
    logger.warning("ADMIN_ID no configurado correctamente")

# ============== CHANNEL IDS ==============
LOGGING_CHANNEL_ID = -1003837793827

# Canal intermedio para transferencias: el userbot sube aquí y el bot reenvía al usuario.
# El bot DEBE ser administrador con permisos completos en este canal.
INTERMEDIATE_CHANNEL_ID = int(os.getenv('INTERMEDIATE_CHANNEL_ID', '-1003807861240'))

# ============== CONCURRENCY ==============
# Máximo de descargas/transferencias simultáneas
# NOTA: Con 3+ uploads concurrentes, Pyrogram recibe demasiados FloodWaits
# de upload.SaveBigFilePart que se acumulan y causan TimeoutErrors.
# 2 es el óptimo: permite concurrencia sin saturar la sesión de Pyrogram.
MAX_CONCURRENT_TRANSFERS = int(os.getenv('MAX_CONCURRENT_TRANSFERS', '2'))

# ============== DISK LIMITS ==============
# Límite total de disco del servidor en bytes (4.88 GB)
SERVER_DISK_LIMIT = float(os.getenv('SERVER_DISK_LIMIT_GB', '4.88')) * 1024 * 1024 * 1024
# Reserva de disco mínima para que el sistema funcione (500 MB)
DISK_RESERVE_MB = int(os.getenv('DISK_RESERVE_MB', '500'))

# ============== FREE TRIAL ==============
FREE_TRIAL_REQUIRED_CHANNEL = "https://t.me/BotProyectoRedAi"
FREE_TRIAL_REQUIRED_CHANNEL_USERNAME = "@BotProyectoRedAi"
FREE_TRIAL_USES = 5

# ============== CONVERSATION STATES ==============
(CONFIG_API_ID, CONFIG_API_HASH, CONFIG_PHONE, CONFIG_CODE, CONFIG_2FA) = range(5)

# ============== FILE LIMITS ==============
MAX_FILE_SIZE = 2000 * 1024 * 1024        # 2 GB (Telegram hard limit)
SAFE_MEMORY_LIMIT = 1950 * 1024 * 1024    # ~1.95 GB ceiling (streaming mode above 1.5 GB)
STREAMING_THRESHOLD = 1500 * 1024 * 1024  # 1.5 GB - use streaming download/upload above this

# ============== TEMP DIRECTORY ==============
# Directory for temporary downloads.  Must be on a partition with ENOUGH free
# space (at least 2 GB recommended).
#
# IMPORTANT for Pterodactyl VPS:
#   /tmp is often a tiny tmpfs (~1 GB).  The bot downloads files up to 2 GB,
#   so /tmp will ALWAYS be too small for large files.  Use ./tmp (next to
#   bot.py, on the main disk) or set TEMP_DOWNLOAD_DIR explicitly.
#
# Override with TEMP_DOWNLOAD_DIR env var if needed.
TEMP_DOWNLOAD_DIR = os.getenv('TEMP_DOWNLOAD_DIR', '')

if not TEMP_DOWNLOAD_DIR:
    # Use a 'tmp' directory next to bot.py (works on Pterodactyl /home/container/)
    _script_dir = os.path.dirname(os.path.abspath(__file__))
    TEMP_DOWNLOAD_DIR = os.path.join(_script_dir, 'tmp')

# Try to create the temp dir; if it fails (read-only FS), fall back to /tmp
try:
    os.makedirs(TEMP_DOWNLOAD_DIR, exist_ok=True)
except OSError as e:
    logger.warning(f"No se pudo crear {TEMP_DOWNLOAD_DIR}: {e}. Intentando /tmp...")
    TEMP_DOWNLOAD_DIR = '/tmp'
    try:
        os.makedirs(TEMP_DOWNLOAD_DIR, exist_ok=True)
    except OSError:
        logger.warning("Tampoco se pudo usar /tmp. Usando directorio actual.")
        TEMP_DOWNLOAD_DIR = '.'

# Log which temp dir is being used and how much space is available
import shutil as _shutil
try:
    _stat = _shutil.disk_usage(TEMP_DOWNLOAD_DIR)
    _free_mb = _stat.free / (1024 * 1024)
    _total_mb = _stat.total / (1024 * 1024)
    logger.info(
        f"TEMP_DOWNLOAD_DIR={TEMP_DOWNLOAD_DIR} "
        f"(libre: {_free_mb:.0f} MB / {_total_mb:.0f} MB)"
    )
    if _free_mb < 2048:
        logger.warning(
            f"⚠️ POCO ESPACIO en {TEMP_DOWNLOAD_DIR}: solo {_free_mb:.0f} MB libres. "
            f"Archivos grandes pueden fallar.  Configura TEMP_DOWNLOAD_DIR a una "
            f"partición con más espacio."
        )
except Exception:
    logger.info(f"TEMP_DOWNLOAD_DIR={TEMP_DOWNLOAD_DIR}")

# ============== VALIDATION ==============
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN requerido - verifica tu archivo .env")
if not MONGODB_URI:
    raise ValueError("MONGODB_URI requerido - verifica tu archivo .env")
