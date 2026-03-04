"""OS keychain integration for storing API keys securely."""

import logging

logger = logging.getLogger(__name__)

SERVICE_NAME = "rippermod-manager"
SECRET_KEYS = {"nexus_api_key", "openai_api_key", "tavily_api_key"}

_available: bool | None = None


def _is_available() -> bool:
    """Check if a real keyring backend is available (not Fail/Null)."""
    global _available
    if _available is not None:
        return _available
    try:
        import keyring
        from keyring.backends.fail import Keyring as FailKeyring
        from keyring.backends.null import Keyring as NullKeyring

        backend = keyring.get_keyring()
        _available = not isinstance(backend, (FailKeyring, NullKeyring))
        if _available:
            logger.info("Keyring backend: %s", type(backend).__name__)
        else:
            logger.info("No usable keyring backend, falling back to SQLite")
    except (ImportError, RuntimeError):
        _available = False
        logger.info("Keyring not available, falling back to SQLite")
    return _available


def get_secret(key: str) -> str | None:
    """Retrieve a secret from the OS keychain. Returns None if unavailable."""
    if not _is_available():
        return None
    try:
        import keyring

        return keyring.get_password(SERVICE_NAME, key)
    except (ImportError, RuntimeError, keyring.errors.KeyringError):
        logger.debug("Failed to read '%s' from keyring", key)
        return None


def set_secret(key: str, value: str) -> bool:
    """Store a secret in the OS keychain. Returns True on success."""
    if not _is_available():
        return False
    try:
        import keyring

        keyring.set_password(SERVICE_NAME, key, value)
        return True
    except (ImportError, RuntimeError, keyring.errors.KeyringError):
        logger.debug("Failed to write '%s' to keyring", key)
        return False


def delete_secret(key: str) -> bool:
    """Remove a secret from the OS keychain. Returns True on success."""
    if not _is_available():
        return False
    try:
        import keyring

        keyring.delete_password(SERVICE_NAME, key)
        return True
    except (ImportError, RuntimeError, keyring.errors.KeyringError):
        logger.debug("Failed to delete '%s' from keyring", key)
        return False
