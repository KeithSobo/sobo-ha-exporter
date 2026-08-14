"""Collector for approved Home Assistant configuration files."""

import logging
from pathlib import Path

from app.config import get_config_dir
from app.security.exclusions import is_excluded_file

logger = logging.getLogger(__name__)


def collect_configuration_files(
    config_dir: Path | str | None = None,
) -> dict[str, str]:
    """Collect non-excluded configuration files from read-only config directory.

    Args:
        config_dir: Path to mounted read-only Home Assistant configuration directory.

    Returns:
        Dictionary mapping relative file paths to their string contents.
    """
    base_path = Path(config_dir) if config_dir is not None else get_config_dir()
    collected_files: dict[str, str] = {}

    if not base_path.exists():
        logger.info("Configuration directory %s does not exist.", base_path)
        return collected_files

    approved_extensions = [".yaml", ".yml", ".json", ".txt", ".md", ".conf"]

    for file_path in base_path.rglob("*"):
        if not file_path.is_file():
            continue

        rel_path = file_path.relative_to(base_path)

        if is_excluded_file(rel_path):
            continue

        if file_path.suffix.lower() not in approved_extensions:
            continue

        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            collected_files[str(rel_path).replace("\\", "/")] = content
        except Exception as e:
            logger.warning("Could not read configuration file %s: %s", rel_path, e)

    return collected_files
