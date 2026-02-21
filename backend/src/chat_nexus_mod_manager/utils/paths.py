"""Path conversion utilities for Windows/WSL compatibility.

Game install paths are stored as Windows format (e.g. ``G:\\SteamLibrary\\...``).
When the backend runs on WSL, these must be converted to ``/mnt/g/SteamLibrary/...``.
Mod file paths from the scanner use backslash separators.
"""

import os
import re
import sys


def to_native_path(windows_path: str) -> str:
    """Convert a Windows path to a native OS path.

    On Linux (WSL): ``G:\\Foo\\Bar`` → ``/mnt/g/Foo/Bar``
    On Windows: returns the path unchanged (with normalized separators).
    """
    if not windows_path:
        return windows_path

    if sys.platform == "linux":
        # Match drive letter pattern: X:\ or X:/
        m = re.match(r"^([A-Za-z]):[/\\]", windows_path)
        if m:
            drive = m.group(1).lower()
            rest = windows_path[3:].replace("\\", "/")
            return f"/mnt/{drive}/{rest}"
        # Already a Unix path
        if windows_path.startswith("/"):
            return windows_path

    # Windows or unrecognized: normalize separators
    return os.path.normpath(windows_path)


def build_file_path(install_path: str, relative_path: str) -> str:
    """Build a full native file path from install_path + a relative mod file path.

    Handles the case where ``relative_path`` uses backslash separators
    (as stored by the Windows scanner) while running on WSL/Linux.
    """
    native_base = to_native_path(install_path)
    # Normalize separators in relative path
    native_rel = relative_path.replace("\\", "/") if sys.platform == "linux" else relative_path
    return os.path.join(native_base, native_rel)
