"""
Telegram Content Copy Bot - Entry Point
========================================
Flat architecture (all files in root, no subfolders):
  bot.py            - Application setup, lifecycle hooks, main()
  copy_bot.py       - ContentCopyBot and UserbotConfig
  state.py          - Global shared state (db, copy_bot instances)
  database.py       - MongoDB operations
  start_handler.py  - /start command and main menu
  button_handler.py - Inline button callbacks
  link_handler.py   - Telegram link processing
  config_handler.py - Userbot config conversation
  admin_handler.py  - Admin actions (premium, broadcast)
  config.py         - Configuration constants
  exceptions.py     - Custom exception classes
  logging_utils.py  - Logging setup and sanitization
  memory.py         - Memory and disk monitoring
  progress.py       - File transfer progress tracker
  strings.py        - Centralized UI strings
"""

import os
import signal
import sys
import asyncio
import logging
import threading
import warnings
from http.server import HTTPServer, BaseHTTPRequestHandler

warnings.filterwarnings('ignore', category=UserWarning, module='telegram')

# ============== Setup logging FIRST ==============
from logging_utils import setup_logging
setup_logging()

logger = logging.getLogger(__name__)


# ============== Health check server — start IMMEDIATELY ==============
# Render requires a bound port; start before any heavy imports (DB, Pyrogram).

class _HealthHandler(BaseHTTPRequestHandler):
    """Minimal HTTP handler for Render health checks."""
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'OK')
    def log_message(self, *args):
        pass  # Suppress per-request logs


def _start_health_server(port: int) -> None:
    """Start a background HTTP server so Render detects an open port."""
    try:
        server = HTTPServer(('0.0.0.0', port), _HealthHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        logger.info(f"Health-check server escuchando en puerto {port}")
    except Exception as e:
        logger.warning(f"No se pudo iniciar health-check server: {e}")


# Start health server at import time (before DB/Pyrogram initialization)
_PORT = int(os.getenv('PORT', '10000'))
_ENV = os.getenv('ENVIRONMENT', 'development')
_USE_WEBHOOK = (_ENV == 'production' and os.getenv('WEBHOOK_URL'))

if not _USE_WEBHOOK:
    _start_health_server(_PORT)


# ============== Now load heavy modules (DB, Pyrogram, handlers) ==============
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ConversationHandler, ContextTypes, filters
)

from config import (
    BOT_TOKEN, ADMIN_ID,
    CONFIG_API_ID, CONFIG_API_HASH, CONFIG_PHONE, CONFIG_CODE, CONFIG_2FA
)
from memory import log_memory_usage
from state import db, copy_bot, get_premium_users

from start_handler import start
from button_handler import button_handler
from link_handler import handle_link
from config_handler import (
    config_api_id, config_api_hash, config_phone,
    config_code, config_2fa, cancel_config
)


# ============== Error & config message handlers ==============

async def handle_config_messages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Fallback guard: reply with a warning if a message arrives while
    the admin is mid-configuration and then clear the conversation state."""
    if not context.user_data.get('configuring_userbot'):
        return
    await update.message.reply_text(
        "⚠️ Proceso de configuración interrumpido.\nUsa /start para volver a configurar."
    )
    context.user_data.clear()


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Global error handler: logs the full traceback and sends a generic
    error notice to the user so they know something went wrong."""
    logger.error(f"Update {update} caused error {context.error}", exc_info=context.error)
    if update and update.effective_message:
        await update.effective_message.reply_text(
            "❌ Ocurrió un error interno. Por favor intenta nuevamente."
        )


# ============== Premium check job ==============

async def check_premium_expirations(application: Application) -> None:
    """Notify users whose premium expires within 3 days, and
    deactivate any fully-expired premiums."""
    try:
        expiring_users = db.get_users_expiring_soon(days=3)
        if not expiring_users:
            return

        for user in expiring_users:
            user_id = user['user_id']
            first_name = user.get('first_name', 'Usuario')
            days_remaining = user['days_remaining']
            expiry_date = user['expiry_date']

            message = (
                f"⚠️ **Tu Premium está por expirar**\n\n"
                f"👤 Hola {first_name},\n\n"
                f"📅 Tu suscripción Premium expira el "
                f"**{expiry_date.strftime('%d/%m/%Y')}** "
                f"(en **{days_remaining} días**).\n\n"
                f"💳 Contacta al administrador para renovar."
            )

            try:
                await application.bot.send_message(
                    chat_id=user_id, text=message, parse_mode='Markdown'
                )
                db.mark_expiry_notified(user_id)
                await asyncio.sleep(0.3)
            except Exception:
                pass

        # Deactivate expired premiums
        expired_ids = db.check_expired_premium()
        if expired_ids:
            logger.info(f"⚠️ {len(expired_ids)} premiums desactivados")
            for uid in expired_ids:
                try:
                    await application.bot.send_message(
                        chat_id=uid,
                        text="ℹ️ **Tu Premium ha expirado**\n\n"
                             "Contacta al administrador para renovar.\n"
                             "Usa /start para ver opciones.",
                        parse_mode='Markdown'
                    )
                    await asyncio.sleep(0.3)
                except Exception:
                    pass
    except Exception as e:
        logger.error(f"Error verificando premiums: {e}")


async def premium_check_job(context: ContextTypes.DEFAULT_TYPE):
    """Scheduled job wrapper for premium checks"""
    await check_premium_expirations(context.application)


# ============== Lifecycle hooks ==============

async def shutdown_handler(application: Application) -> None:
    """Graceful shutdown hook: wait up to 30 s for in-flight background
    tasks, then disconnect the Pyrogram userbot client."""
    logger.info("🛑 Iniciando shutdown graceful...")

    try:
        if hasattr(application, 'background_tasks') and application.background_tasks:
            active = len(application.background_tasks)
            logger.info(f"⏳ Esperando {active} tareas en background...")
            try:
                await asyncio.wait_for(
                    asyncio.gather(*application.background_tasks, return_exceptions=True),
                    timeout=30.0
                )
                logger.info("✅ Tareas completadas")
            except asyncio.TimeoutError:
                cancelled = sum(1 for t in application.background_tasks if not t.done() and t.cancel())
                logger.warning(f"⚠️ {cancelled} tareas canceladas por timeout")
                await asyncio.sleep(5)
    except Exception as e:
        logger.error(f"Error en shutdown: {e}")

    try:
        if copy_bot.client and copy_bot.client.is_connected:
            await asyncio.wait_for(copy_bot.client.stop(), timeout=30.0)
            logger.info("✅ Pyrogram desconectado")
    except Exception as e:
        logger.error(f"Error desconectando Pyrogram: {e}")

    logger.info("✅ Shutdown completado")


async def post_init(application: Application) -> None:
    """Post-initialization lifecycle hook.

    Starts the heartbeat task (every 5 min), the pending-joins monitor
    (every 30 s), connects the Pyrogram userbot (up to 3 retries), and
    deactivates any expired premium accounts.
    """

    # --- Heartbeat task (every 5 minutes) ---
    async def heartbeat_task():
        consecutive_errors = 0
        heartbeat_count = 0
        while True:
            try:
                await asyncio.sleep(300)
                heartbeat_count += 1
                consecutive_errors = 0

                active = len(getattr(application, 'background_tasks', set()))
                transfers = copy_bot._active_transfers
                reserved_mb = copy_bot._reserved_disk_bytes / (1024*1024)
                logger.info(
                    f"💓 Heartbeat - Bot ACTIVO. Tareas: {active}, "
                    f"Transferencias: {transfers}, Disco reservado: {reserved_mb:.0f} MB"
                )

                if heartbeat_count % 5 == 0:
                    log_memory_usage("heartbeat")

                # Periodic cleanup: remove temp files OLDER THAN 30 MINUTES.
                # IMPORTANT: Do NOT use max_age_seconds=0 here!
                # That was the ROOT CAUSE of upload failures: the heartbeat
                # was deleting files while they were being uploaded (a 1.4 GB
                # upload takes 4+ minutes, and the heartbeat runs every 5 min).
                # The _transfer_active flag adds extra protection, but using
                # a safe max_age of 30 min ensures we only clean true orphans.
                try:
                    freed = copy_bot._cleanup_temp_files(max_age_seconds=1800)
                    if freed > 0:
                        disk_free = copy_bot._get_disk_free()
                        logger.info(
                            f"🧹 Heartbeat cleanup: {freed/(1024*1024):.1f} MB "
                            f"liberados, disco libre: {disk_free/(1024*1024):.0f} MB"
                        )
                    elif copy_bot._transfer_active:
                        logger.debug(
                            "🛡️ Heartbeat: transferencia activa, "
                            "cleanup omitido para proteger archivos"
                        )
                except Exception as cleanup_err:
                    logger.debug(f"Cleanup en heartbeat: {cleanup_err}")

                if copy_bot.config.is_configured():
                    if not copy_bot.is_initialized or not copy_bot.client or not copy_bot.client.is_connected:
                        logger.warning("⚠️ Userbot desconectado, reconectando...")
                        try:
                            await copy_bot.initialize_client(force_recreate=True)
                        except Exception as e:
                            logger.error(f"❌ Error reconectando: {e}")
                            consecutive_errors += 1

                try:
                    await application.bot.get_me()
                except Exception as e:
                    logger.error(f"❌ Bot no responde: {e}")
                    consecutive_errors += 1

                if consecutive_errors >= 5:
                    logger.error("❌ Demasiados errores, reiniciando conexiones...")
                    if copy_bot.config.is_configured():
                        await copy_bot.initialize_client(force_recreate=True)
                    consecutive_errors = 0

            except asyncio.CancelledError:
                break
            except Exception as e:
                consecutive_errors += 1
                logger.error(f"❌ Error en heartbeat: {e}")

    # --- Pending joins monitor (every 30s) ---
    async def monitor_pending_joins():
        while True:
            try:
                await asyncio.sleep(30)
                if copy_bot.pending_join:
                    await copy_bot.check_pending_join_approvals(application.bot)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Error en monitor joins: {e}")

    # Start background tasks
    if not hasattr(application, 'background_tasks'):
        application.background_tasks = set()

    for coro_fn in (heartbeat_task, monitor_pending_joins):
        task = asyncio.create_task(coro_fn())
        application.background_tasks.add(task)
        task.add_done_callback(application.background_tasks.discard)

    # --- Connect userbot (3 retries) ---
    if copy_bot.config.is_configured():
        logger.info("Conectando userbot...")
        for attempt in range(1, 4):
            try:
                success = await copy_bot.initialize_client(force_recreate=(attempt > 1))
                if success:
                    logger.info("✅ Userbot conectado")
                    if ADMIN_ID:
                        try:
                            await application.bot.send_message(
                                chat_id=ADMIN_ID,
                                text="✅ **Bot Iniciado**\n\nUserbot conectado correctamente.",
                                parse_mode='Markdown'
                            )
                        except Exception:
                            pass
                    break
                elif attempt < 3:
                    await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"❌ Intento {attempt}/3: {e}")
                if attempt < 3:
                    await asyncio.sleep(5)
        else:
            logger.error("❌ Userbot no conectado después de 3 intentos")
            if ADMIN_ID:
                try:
                    await application.bot.send_message(
                        chat_id=ADMIN_ID,
                        text="⚠️ **Bot Iniciado - Userbot No Disponible**\n\n"
                             "Usa /start → '⚙️ Configurar Userbot' para reconfigurar.",
                        parse_mode='Markdown'
                    )
                except Exception:
                    pass
    else:
        logger.info("Userbot no configurado")
        if ADMIN_ID:
            try:
                await application.bot.send_message(
                    chat_id=ADMIN_ID,
                    text="🔧 **Bot Iniciado - Configuración Requerida**\n\n"
                         "Usa /start → '⚙️ Configurar Userbot'.",
                    parse_mode='Markdown'
                )
            except Exception:
                pass

    # --- Check expired premiums on startup ---
    try:
        expired_ids = db.check_expired_premium()
        if expired_ids:
            logger.info(f"⚠️ {len(expired_ids)} premiums desactivados al inicio")
            for uid in expired_ids:
                try:
                    await application.bot.send_message(
                        chat_id=uid,
                        text="ℹ️ **Tu Premium ha expirado**\n\nUsa /start para ver opciones.",
                        parse_mode='Markdown'
                    )
                    await asyncio.sleep(0.3)
                except Exception:
                    pass
    except Exception as e:
        logger.error(f"Error verificando premiums: {e}")


# ============== Main ==============

def main() -> None:
    """Application entry point - builds and runs the Telegram bot."""
    shutdown_initiated = False

    def signal_handler(signum, frame):
        nonlocal shutdown_initiated
        if shutdown_initiated:
            sys.exit(1)
        shutdown_initiated = True
        logger.info(f"🛑 Señal {signal.Signals(signum).name} recibida, shutdown graceful...")

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # Health server already started at module level (before heavy imports)
    PORT = _PORT
    env = _ENV
    use_webhook = _USE_WEBHOOK

    try:
        app = (Application.builder()
               .token(BOT_TOKEN)
               .post_init(post_init)
               .post_shutdown(shutdown_handler)
               .read_timeout(3600)
               .write_timeout(3600)
               .connect_timeout(60)
               .pool_timeout(60)
               .get_updates_read_timeout(60)
               .get_updates_write_timeout(60)
               .get_updates_connect_timeout(60)
               .get_updates_pool_timeout(10)
               .build())

        # Conversation handler for userbot config
        config_conv = ConversationHandler(
            entry_points=[
                CallbackQueryHandler(button_handler, pattern='^start_config$'),
                CallbackQueryHandler(button_handler, pattern='^reconfig_userbot$')
            ],
            states={
                CONFIG_API_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, config_api_id),
                                CallbackQueryHandler(cancel_config, pattern='^cancel_config_btn$')],
                CONFIG_API_HASH: [MessageHandler(filters.TEXT & ~filters.COMMAND, config_api_hash),
                                  CallbackQueryHandler(cancel_config, pattern='^cancel_config_btn$')],
                CONFIG_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, config_phone),
                               CallbackQueryHandler(cancel_config, pattern='^cancel_config_btn$')],
                CONFIG_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, config_code),
                              CallbackQueryHandler(cancel_config, pattern='^cancel_config_btn$')],
                CONFIG_2FA: [MessageHandler(filters.TEXT & ~filters.COMMAND, config_2fa),
                             CallbackQueryHandler(cancel_config, pattern='^cancel_config_btn$')],
            },
            fallbacks=[
                CommandHandler('cancel', cancel_config),
                CallbackQueryHandler(cancel_config, pattern='^cancel_config_btn$')
            ],
            per_message=False,
        )

        app.background_tasks = set()

        # Premium check job every 6 hours
        if app.job_queue:
            app.job_queue.run_repeating(premium_check_job, interval=21600, first=10)
            logger.info("📅 Job de premium configurado (cada 6h)")

        # Register handlers
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("cancel", cancel_config))
        app.add_handler(config_conv)
        app.add_handler(CallbackQueryHandler(button_handler))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
        app.add_error_handler(error_handler)

        # Startup log (una sola vez, consolidado)
        premium_count = len(get_premium_users())
        userbot_status = 'SÍ' if copy_bot.config.is_configured() else 'NO'
        logger.info(
            f"🚀 INICIANDO BOT | Entorno: {env} | Admin: {ADMIN_ID} "
            f"| Premium: {premium_count} | Puerto: {PORT} | Userbot: {userbot_status}"
        )

        if use_webhook:
            app.run_webhook(
                listen="0.0.0.0", port=PORT,
                webhook_url=os.getenv('WEBHOOK_URL'),
                drop_pending_updates=True
            )
        else:
            app.run_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True,
                poll_interval=1.0, timeout=30
            )

    except KeyboardInterrupt:
        logger.info("🛑 Interrupción por teclado")
    except Exception as e:
        logger.error(f"❌ Error crítico: {e}", exc_info=True)
        raise
    finally:
        logger.info("✅ Bot detenido")
        print("\n✅ Bot detenido correctamente\n")


if __name__ == '__main__':
    main()
