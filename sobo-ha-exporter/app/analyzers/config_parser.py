"""Safe YAML parser and structural configuration loader for Home Assistant."""

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
MAX_RECURSION_DEPTH = 10


def is_safe_path(base_dir: Path, target_path: Path) -> bool:
    """Verify that target_path resolves strictly within base_dir without symlink escape."""
    try:
        resolved_base = base_dir.resolve()
        resolved_target = target_path.resolve()
        return resolved_target == resolved_base or resolved_base in resolved_target.parents
    except Exception:
        return False


class HomeAssistantSafeLoader(yaml.SafeLoader):
    """Custom PyYAML SafeLoader for Home Assistant YAML constructs."""

    pass


def _secret_constructor(loader: yaml.Loader, node: yaml.Node) -> str:
    secret_name = loader.construct_scalar(node) if isinstance(node, yaml.ScalarNode) else "secret"
    return f"secret reference ({secret_name})"


def _unknown_tag_constructor(loader: yaml.Loader, tag_suffix: str, node: yaml.Node) -> Any:
    if isinstance(node, yaml.ScalarNode):
        val = loader.construct_scalar(node)
        return f"![{tag_suffix}] {val}"
    elif isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    elif isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node)
    return f"![{tag_suffix}]"


HomeAssistantSafeLoader.add_constructor("!secret", _secret_constructor)
HomeAssistantSafeLoader.add_multi_constructor("!", _unknown_tag_constructor)


class SafeYamlParser:
    """Safe YAML parser supporting Home Assistant include constructs and security constraints."""

    def __init__(self, config_dir: Path):
        self.config_dir = config_dir.resolve()
        self.warnings: list[str] = []
        self.analyzed_files: set[str] = set()

    def parse_file(self, rel_or_abs_path: Path | str, depth: int = 0) -> tuple[Any, list[str]]:
        """Parse a YAML file safely.

        Args:
            rel_or_abs_path: Path relative to config_dir or absolute.
            depth: Current recursion depth.

        Returns:
            Tuple of (parsed_data, local_warnings).
        """
        local_warnings: list[str] = []
        file_path = (
            Path(rel_or_abs_path)
            if Path(rel_or_abs_path).is_absolute()
            else self.config_dir / rel_or_abs_path
        )

        rel_str = str(file_path).replace("\\", "/")
        try:
            if file_path.is_relative_to(self.config_dir):
                rel_str = str(file_path.relative_to(self.config_dir)).replace("\\", "/")
        except ValueError:
            pass

        if depth > MAX_RECURSION_DEPTH:
            msg = f"Include depth limit ({MAX_RECURSION_DEPTH}) exceeded at {rel_str}"
            logger.warning(msg)
            local_warnings.append(msg)
            return None, local_warnings

        if not is_safe_path(self.config_dir, file_path):
            msg = f"Security error: path traversal or symlink escape rejected for {rel_str}"
            logger.warning(msg)
            local_warnings.append(msg)
            return None, local_warnings

        if not file_path.exists() or not file_path.is_file():
            msg = f"Referenced configuration file missing: {rel_str}"
            local_warnings.append(msg)
            return None, local_warnings

        try:
            stat = file_path.stat()
            if stat.st_size > MAX_FILE_SIZE_BYTES:
                msg = (
                    f"Configuration file {rel_str} exceeds maximum size "
                    f"({MAX_FILE_SIZE_BYTES} bytes)"
                )
                local_warnings.append(msg)
                return None, local_warnings
        except Exception as e:
            msg = f"Error reading file stats for {rel_str}: {e}"
            local_warnings.append(msg)
            return None, local_warnings

        self.analyzed_files.add(rel_str)

        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
            # Parse YAML safely using custom loader
            data = yaml.load(content, Loader=HomeAssistantSafeLoader)
            return self._resolve_includes(
                data, file_path.parent, depth, local_warnings
            ), local_warnings
        except yaml.YAMLError as e:
            msg = f"Malformed YAML in {rel_str}: {e}"
            logger.warning(msg)
            local_warnings.append(msg)
            return None, local_warnings
        except Exception as e:
            msg = f"Unexpected error reading {rel_str}: {e}"
            logger.warning(msg)
            local_warnings.append(msg)
            return None, local_warnings

    def _resolve_includes(
        self, data: Any, current_dir: Path, depth: int, local_warnings: list[str]
    ) -> Any:
        if isinstance(data, dict):
            resolved_dict: dict[str, Any] = {}
            for k, v in data.items():
                resolved_dict[k] = self._resolve_includes(v, current_dir, depth, local_warnings)
            return resolved_dict
        elif isinstance(data, list):
            return [
                self._resolve_includes(item, current_dir, depth, local_warnings) for item in data
            ]
        elif isinstance(data, str) and data.startswith("![include"):
            # Custom tag representation from loader
            return f"[include reference: {data}]"
        return data
