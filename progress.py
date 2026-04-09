"""Reusable progress tracking for file transfers - eliminates duplicate code"""

import time
import asyncio
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)


class ProgressTracker:
    """Unified progress tracker for Pyrogram download/upload operations.

    The tracker is passed directly as Pyrogram's ``progress`` callback
    to both ``download_media`` and ``send_*`` methods.  It auto-detects
    the phase transition (download → upload) and updates the UI
    message to show the correct label and progress bar for each phase.

    Phase detection logic:
      - Starts in "download" phase.
      - When ``current == total`` during download, marks download_complete.
      - When a NEW progress call arrives after download_complete
        (i.e., ``current < total``), switches to "upload" phase.
    """

    def __init__(self, message: 'telegram.Message' = None,
                 user_id: int = None, with_cancel: bool = True) -> None:
        self.message = message
        self.user_id = user_id
        self.with_cancel = with_cancel

        # Phase tracking
        self.phase = "download"
        self.download_complete = False

        # Update throttling
        self.last_bytes = 0
        self.last_time = 0.0

        # Cancel support
        self.cancel_requested = False

    def _build_bar(self, percent: float) -> str:
        """Return an 8-segment emoji progress bar."""
        filled = int(percent / 12.5)
        return '⬢' * filled + '⬡' * (8 - filled)

    def _phase_info(self) -> tuple:
        """Return ``(emoji, label)`` for the current transfer phase."""
        if self.phase == "download":
            return "📥", "Descargando desde Telegram"
        elif self.phase == "upload":
            return "📤", "Subiendo a Telegram"
        return "⚙️", "Procesando"

    async def __call__(self, current: int, total: int):
        """Progress callback compatible with Pyrogram's progress parameter.

        Called by Pyrogram during both download and upload operations.
        Auto-detects the phase transition when download completes and
        a new progress stream starts.
        """
        # Check cancellation
        if self.cancel_requested:
            raise asyncio.CancelledError("Cancelado por el usuario")

        # --- Auto-detect phase transition ---
        if self.download_complete and self.phase == "download":
            # New progress stream after download completed → upload phase
            self.phase = "upload"
            self.last_bytes = 0
            self.last_time = 0.0
            logger.info(f"📤 Fase UPLOAD iniciada ({total/(1024*1024):.1f} MB)")

        if current == total and self.phase == "download" and not self.download_complete:
            self.download_complete = True
            logger.info(f"✅ Descarga completada ({total/(1024*1024):.1f} MB)")

        if not self.message:
            return

        try:
            current_time = time.time()
            current_mb = current / (1024 * 1024)
            total_mb = total / (1024 * 1024)
            percent = (current / total * 100) if total > 0 else 0

            # Throttle: every 10 MB or 4 seconds, or first/last
            mb_since = current_mb - (self.last_bytes / (1024 * 1024))
            time_since = current_time - self.last_time

            should_update = (
                mb_since >= 10 or
                time_since >= 4 or
                current == total or
                self.last_bytes == 0
            )

            if not should_update:
                return

            # Calculate speed
            if self.last_time > 0 and time_since > 0:
                bytes_delta = current - self.last_bytes
                speed_mbps = (bytes_delta / (1024 * 1024)) / time_since
                speed_text = f"⚡ **Velocidad:** {speed_mbps:.1f} MB/s"
            else:
                speed_text = ""

            self.last_bytes = current
            self.last_time = current_time

            emoji, text = self._phase_info()
            bar = self._build_bar(percent)

            msg_text = (
                f"{emoji} **{text}**\n\n"
                f"{bar} **{percent:.0f}%**\n\n"
                f"📦 **Progreso:** {current_mb:.1f} MB / {total_mb:.1f} MB"
            )
            if speed_text:
                msg_text += f"\n{speed_text}"
            msg_text += f"\n💾 **Tamaño:** {total_mb:.1f} MB"

            reply_markup = None
            if self.with_cancel and self.user_id:
                reply_markup = InlineKeyboardMarkup([
                    [InlineKeyboardButton(
                        "❌ Cancelar",
                        callback_data=f"cancel_download_{self.user_id}"
                    )]
                ])

            await self.message.edit_text(
                msg_text,
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            if "message is not modified" not in str(e).lower():
                logger.debug(f"Error actualizando progreso: {e}")

    def request_cancel(self) -> None:
        """Signal cancellation; the next progress callback will raise ``CancelledError``."""
        self.cancel_requested = True
        logger.info(f"🛑 Cancelación solicitada para usuario {self.user_id}")
