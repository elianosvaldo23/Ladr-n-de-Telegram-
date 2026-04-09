"""Logging utilities - sanitization, masking, channel logging"""

import re
import logging

logger = logging.getLogger(__name__)


class _PeerIdFilter(logging.Filter):
    """Suppress Pyrogram's internal 'Peer id invalid' ValueError spam."""
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        if 'Peer id invalid' in msg or 'handle_updates' in msg:
            return False
        return True


class _FloodWaitDemoteFilter(logging.Filter):
    """Demote Pyrogram's noisy FloodWait retry logs to DEBUG."""
    _PATTERNS = ('Waiting for', 'before continuing', 'required by')

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno == logging.WARNING:
            msg = record.getMessage()
            if all(p in msg for p in ('Waiting for', 'before continuing')):
                record.levelno = logging.DEBUG
                record.levelname = 'DEBUG'
        return True


def setup_logging() -> None:
    """Configure the root logger (INFO level) and suppress noisy libraries."""
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    for lib in ('pyrogram', 'telegram', 'httpx', 'httpcore', 'apscheduler'):
        logging.getLogger(lib).setLevel(logging.WARNING)

    logging.getLogger('asyncio').addFilter(_PeerIdFilter())
    logging.getLogger('pyrogram').addFilter(_FloodWaitDemoteFilter())


def mask_sensitive(value: str) -> str:
    """Replace the middle portion of *value* with asterisks."""
    if not value:
        return '(vacío)'
    value = str(value)
    if len(value) <= 4:
        return '****'
    return f"{value[:2]}{'*' * (len(value) - 4)}{value[-2:]}"


def mask_phone(phone: str) -> str:
    """Mask a phone number, keeping the country code prefix and last 2 digits."""
    if not phone:
        return '(vacío)'
    phone = str(phone).strip()
    if len(phone) <= 4:
        return '****'
    return f"{phone[:3]}{'*' * (len(phone) - 5)}{phone[-2:]}"


def sanitize_log_message(message: str) -> str:
    """Scrub phone numbers, bot tokens, and session strings from *message*."""
    message = re.sub(
        r'(\+\d{1,3})[\d\s\-]{5,}',
        lambda m: mask_phone(m.group(0)),
        message
    )
    message = re.sub(
        r'\d{8,10}:[A-Za-z0-9_\-]{35}',
        '[BOT_TOKEN_REDACTADO]',
        message
    )
    message = re.sub(
        r'[A-Za-z0-9+/=]{50,}',
        '[SESSION_REDACTADA]',
        message
    )
    return message


async def send_log_to_channel(bot: 'telegram.Bot', message: str) -> None:
    """Send a sanitized debug log entry to the monitoring Telegram channel."""
    from config import LOGGING_CHANNEL_ID
    try:
        safe_message = sanitize_log_message(message)
        await bot.send_message(
            chat_id=LOGGING_CHANNEL_ID,
            text=f"🔍 **LOG DEBUG**\n\n{safe_message}",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.debug(f"No se pudo enviar log al canal: {e}")
