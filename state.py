"""Global shared state - database and copy_bot instances.

This module provides a single place to initialize and access the global
database and ContentCopyBot instances, avoiding circular imports.

All handler modules import ``db``, ``copy_bot``, and the user-helper
functions from here so there is exactly one initialisation path.
"""

import logging
from database import MongoDB, initialize_database
from copy_bot import ContentCopyBot
from config import MONGODB_URI, ADMIN_ID, FREE_TRIAL_REQUIRED_CHANNEL_USERNAME

logger = logging.getLogger(__name__)

# ============== DATABASE ==============
try:
    db = initialize_database(MONGODB_URI)
    if not db.is_connected:
        logger.warning("⚠️ MongoDB no disponible al arrancar.")
except Exception as e:
    logger.error(f"❌ Error inicializando base de datos: {e}")
    db = MongoDB.__new__(MongoDB)
    db.uri = MONGODB_URI
    db.client = None
    db.db = None
    db.is_connected = False
    db._last_reconnect_attempt = 0.0
    db._reconnect_cooldown = 30.0

# ============== COPY BOT ==============
copy_bot = ContentCopyBot(db)


# ============== USER HELPERS ==============
def get_premium_users() -> set:
    """Return the set of user-IDs that currently have active premium.

    Returns:
        A ``set[int]`` of Telegram user IDs with premium access.
    """
    try:
        return set(db.get_premium_users())
    except Exception as e:
        logger.error(f"Error obteniendo usuarios premium: {e}")
        return set()


def is_user_premium(user_id: int) -> bool:
    """Check if *user_id* has active premium.

    Automatically deactivates expired premiums and returns ``False``
    in that case.  The admin is always considered premium.
    """
    from datetime import datetime
    if user_id == ADMIN_ID:
        return True
    user = db.get_user(user_id)
    if user and user.get('is_premium', False):
        expiry_date = user.get('premium_expiry_date')
        if expiry_date and datetime.utcnow() > expiry_date:
            try:
                db.set_user_premium(user_id, is_premium=False)
                logger.info(f"Premium expirado y desactivado para usuario {user_id}")
            except Exception as e:
                logger.error(f"Error desactivando premium expirado: {e}")
            return False
        return True
    return False


def is_user_free_trial(user_id: int) -> bool:
    """Return True when *user_id* has activated a free trial with uses remaining."""
    if user_id == ADMIN_ID:
        return False
    trial_info = db.get_free_trial_info(user_id)
    return trial_info.get('trial_activated', False) and trial_info.get('trial_uses_left', 0) > 0


def get_free_trial_uses_left(user_id: int) -> int:
    """Return the number of free-trial uses left for *user_id*."""
    trial_info = db.get_free_trial_info(user_id)
    return trial_info.get('trial_uses_left', 0)


def save_user_to_db(user_data: dict) -> None:
    """Persist user interaction data (upsert) to MongoDB."""
    try:
        db.save_user(user_data)
    except Exception as e:
        logger.error(f"Error guardando usuario en BD: {e}")


async def check_user_in_channel(bot: 'telegram.Bot', user_id: int) -> bool:
    """Verify *user_id* is a member of the required free-trial channel.

    Returns True (permissive) when the bot lacks permission to check.
    """
    try:
        member = await bot.get_chat_member(
            chat_id=FREE_TRIAL_REQUIRED_CHANNEL_USERNAME,
            user_id=user_id
        )
        return member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        error_msg = str(e).lower()
        if any(p in error_msg for p in ['bot is not a member', 'not enough rights',
                                         'chat_admin_required', 'user_not_participant',
                                         'forbidden', 'bad request']):
            logger.warning(f"⚠️ Bot sin permisos para verificar canal trial: {e}")
            return True
        logger.warning(f"⚠️ Error verificando membresía: {e}")
        return True


async def get_user_config_from_db(user_id: int) -> dict:
    """Fetch per-user extraction config (target channel, filters) from MongoDB.

    Returns a default config dict when the DB entry is missing.
    """
    try:
        config = db.get_user_config(user_id)
        if config:
            return config
    except Exception as e:
        logger.error(f"Error obteniendo config de usuario {user_id}: {e}")
    return {
        'target_channel': None,
        'filters': {
            'videos': True, 'photos': True, 'documents': True,
            'audio': True, 'text': True, 'stickers': True
        }
    }


async def save_user_config_to_db(user_id: int, config: dict) -> None:
    """Persist the extraction *config* for *user_id* in MongoDB."""
    try:
        db.save_user_config(user_id, config)
    except Exception as e:
        logger.error(f"Error guardando config de usuario {user_id}: {e}")
