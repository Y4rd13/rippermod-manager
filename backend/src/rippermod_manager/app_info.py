"""Application identity sent to Nexus Mods on every API call."""

import logging
from importlib.metadata import PackageNotFoundError, version

logger = logging.getLogger(__name__)

APP_NAME = "RipperMod Manager"
_PACKAGE_NAME = "rippermod-manager"

_identity_logged = False


def app_version() -> str:
    """Release version from the installed package metadata, or ``"dev"`` without it."""
    try:
        return version(_PACKAGE_NAME)
    except PackageNotFoundError:
        return "dev"


def nexus_identity_headers() -> dict[str, str]:
    """Headers Nexus asks every third-party app to send."""
    app_ver = app_version()
    return {
        "Application-Name": APP_NAME,
        "Application-Version": app_ver,
        "User-Agent": f"RipperModManager/{app_ver}",
    }


def log_identity_once() -> None:
    """Log the identity the first time a Nexus client is built in this process."""
    global _identity_logged
    if _identity_logged:
        return
    _identity_logged = True
    logger.info("Nexus client identifies as %s %s", APP_NAME, app_version())
