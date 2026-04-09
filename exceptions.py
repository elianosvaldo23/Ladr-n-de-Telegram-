"""Custom exceptions for the bot"""


class BotError(Exception):
    """Base exception for all bot-specific errors.

    Attributes:
        user_message: A user-friendly string suitable for display in
            Telegram messages.  Defaults to the technical *message*.
    """

    def __init__(self, message: str, user_message: str = None) -> None:
        super().__init__(message)
        self.user_message: str = user_message or message


class ChannelAccessError(BotError):
    """The userbot cannot resolve or access a Telegram channel."""
    pass


class RateLimitError(BotError):
    """A Telegram FloodWait or internal rate-limit was hit.

    Attributes:
        wait_seconds: How many seconds the caller should wait before retrying.
    """

    def __init__(self, message: str, wait_seconds: float = 0, user_message: str = None) -> None:
        super().__init__(message, user_message)
        self.wait_seconds: float = wait_seconds


class FileTransferError(BotError):
    """A file download or upload failed (too large, disk full, timeout, etc.).

    Attributes:
        file_size: Size of the file in bytes (0 if unknown).
    """

    def __init__(self, message: str, file_size: int = 0, user_message: str = None) -> None:
        super().__init__(message, user_message)
        self.file_size: int = file_size


class AuthenticationError(BotError):
    """Userbot authentication failed (wrong code, missing 2FA, etc.)."""
    pass


class ConfigurationError(BotError):
    """Required configuration keys are missing or invalid."""
    pass
