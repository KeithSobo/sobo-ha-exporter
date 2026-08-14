"""Collector for approved Home Assistant configuration files."""

import logging
from pathlib import Path

from app.config import get_config_dir
from app.security.exclusions import is_excluded_file

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".yaml", ".yml"}


def collect_configuration_files(
    config_dir: Path | str | None = None,
    allow_custom_components: bool = False,
    allow_www: bool = False,
) -> dict[str, str]:
    """Collect user-authored configuration YAML files from read-only config directory.

    Allowed files include:
    - Root-level configuration YAML files (configuration.yaml, automations.yaml, etc.)
    - YAML files under packages/, dashboards/, blueprints/, or user config subfolders

    Always excluded:
    - secrets.yaml, .storage/**, translations/**, strings.json, node_modules/**,
      backups/**, *.db, *.log, certificates, private keys, cache directories
    - custom_components/** (unless allow_custom_components=True)
    - www/** (unless allow_www=True)

    Args:
        config_dir: Path to mounted read-only Home Assistant configuration directory.
        allow_custom_components: Whether to include custom_components YAML files.
        allow_www: Whether to include www assets.

    Returns:
        Dictionary mapping relative file paths to their string contents.
    """
    base_path = Path(config_dir) if config_dir is not None else get_config_dir()
    collected_files: dict[str, str] = {}

    if not base_path.exists():
        logger.info("Configuration directory %s does not exist.", base_path)
        return collected_files

    for file_path in base_path.rglob("*"):
        if not file_path.is_file():
            continue

        rel_path = file_path.relative_to(base_path)
        rel_str = str(rel_path).replace("\\", "/")
        parts = [p.lower() for p in rel_path.parts]

        # Check explicit exclusions (secrets.yaml, .storage, translations, strings.json, etc.)
        if is_excluded_file(rel_path):
            continue

        # Exclude custom_components unless explicitly enabled
        if "custom_components" in parts and not allow_custom_components:
            continue

        # Exclude www unless explicitly enabled
        if "www" in parts and not allow_www:
            continue

        # Configuration file export only collects user-authored YAML files
        if file_path.suffix.lower() not in ALLOWED_EXTENSIONS:
            continue

        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            collected_files[rel_str] = content
        except Exception as e:
            logger.warning("Could not read configuration file %s: %s", rel_path, e)

    return collected_files
