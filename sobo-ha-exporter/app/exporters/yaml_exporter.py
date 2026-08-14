"""YAML exporter module."""

from pathlib import Path


def export_config_yaml(output_dir: Path, config_files: dict[str, str]) -> None:
    """Export collected configuration files into config/ subdirectory.

    Args:
        output_dir: Staging base directory.
        config_files: Dictionary mapping relative file path to string content.
    """
    config_base = output_dir / "config"
    for rel_path_str, content in sorted(config_files.items()):
        file_path = config_base / rel_path_str
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
