"""Windows/Git Bash path normalization utilities."""
import os
import re
from pathlib import Path


def normalize_path(path_str: str) -> str:
    """
    Convert Git Bash /c/Users/... to Windows C:\\Users\\...

    Git Bash (MSYS2) uses Unix-style paths like /c/Users/... but Python subprocess
    on Windows requires native paths like C:\\Users\\...

    Args:
        path_str: Path string (may be MSYS2 format or Windows format)

    Returns:
        Windows-style path string
    """
    if not path_str:
        return path_str
    # Git Bash MSYS2 path pattern: /c/path or /C/path
    match = re.match(r'^/([a-zA-Z])(/.*)?$', path_str)
    if match:
        drive = match.group(1).upper()
        rest = match.group(2) or ''
        return f"{drive}:{rest}".replace('/', '\\')
    return path_str


def to_windows_path(path) -> Path:
    """
    Ensure path is Windows-style Path object.

    Args:
        path: str or Path object (may be MSYS2 format)

    Returns:
        pathlib.Path object with Windows-style path
    """
    if isinstance(path, str):
        path = normalize_path(path)
    return Path(path)


def to_posix_string(path) -> str:
    """
    Convert path to POSIX string for subprocess.

    Some CLI tools expect forward slashes even on Windows.

    Args:
        path: str or Path object

    Returns:
        POSIX-style path string (forward slashes)
    """
    p = Path(path)
    return str(p).replace('\\', '/')
