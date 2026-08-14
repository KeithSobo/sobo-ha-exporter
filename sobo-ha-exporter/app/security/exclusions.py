"""Exclusion pattern matcher for Home Assistant configuration files."""

import fnmatch
from pathlib import Path

# Explicit relative path patterns and file extensions that must NEVER be exported
EXCLUDED_PATTERNS = [
    "secrets.yaml",
    "*/secrets.yaml",
    ".storage",
    ".storage/*",
    "*/.storage/*",
    ".cloud",
    ".cloud/*",
    "*/.cloud/*",
    ".auth",
    ".auth/*",
    "*/.auth/*",
    "*.db",
    "*.db-shm",
    "*.db-wal",
    "*.log",
    "*.log.*",
    "backups",
    "backups/*",
    "*/backups/*",
    "*.tar",
    "*.gz",
    "*.zip",
    "id_ed25519",
    "id_ed25519.pub",
    "*.key",
    "*.crt",
    "*.pem",
]


def is_excluded_file(file_path: Path | str) -> bool:
    """Check if a file or directory path matches exclusion patterns.

    Args:
        file_path: Relative or absolute path to check.

    Returns:
        True if the file is prohibited from export, False otherwise.
    """
    path_str = str(file_path).replace("\\", "/")
    parts = path_str.split("/")

    # Check filename and directory segments
    name = parts[-1]
    if name in ["secrets.yaml", ".storage", ".cloud", ".auth", "backups"]:
        return True

    for segment in parts:
        if segment in [".storage", ".cloud", ".auth", "backups"]:
            return True

    for pattern in EXCLUDED_PATTERNS:
        if fnmatch.fnmatch(path_str, pattern) or fnmatch.fnmatch(name, pattern):
            return True

    return False
