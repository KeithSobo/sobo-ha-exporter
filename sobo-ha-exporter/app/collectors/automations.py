"""Automation collector and entity reference extractor."""

import logging
import re
from pathlib import Path
from typing import Any

import yaml

from app.config import get_config_dir

logger = logging.getLogger(__name__)

# Basic regex for entity_id matching: domain.object_id e.g. light.living_room
ENTITY_ID_REGEX = re.compile(
    r"\b(?:light|switch|sensor|binary_sensor|climate|cover|fan|media_player|camera|lock|"
    r"vacuum|alarm_control_panel|automation|script|scene|person|zone|input_boolean|"
    r"input_number|input_select|input_text|input_datetime|counter|timer)\.[a-z0-9_]+\b"
)

SERVICE_SUFFIXES = {
    "turn_on",
    "turn_off",
    "toggle",
    "open_cover",
    "close_cover",
    "stop_cover",
    "set_temperature",
    "set_hvac_mode",
    "set_preset_mode",
    "set_fan_mode",
    "set_percentage",
    "set_value",
    "select_option",
    "play_media",
    "media_play",
    "media_pause",
    "media_stop",
    "lock",
    "unlock",
    "reload",
    "update",
}


def collect_automations(
    config_dir: Path | str | None = None,
) -> tuple[dict[str, list[str]], list[str]]:
    """Parse automations.yaml and extract entity references per automation.

    Args:
        config_dir: Read-only mounted HA config directory.

    Returns:
        Tuple of (automation_to_entities_map, warnings_list).
    """
    path = (Path(config_dir) if config_dir is not None else get_config_dir()) / "automations.yaml"
    if not path.exists():
        logger.info("No automations.yaml found at %s", path)
        return {}, ["automations.yaml file not found"]

    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
        return parse_automations_content(content)
    except Exception as e:
        logger.error("Error reading automations.yaml: %s", e)
        return {}, [f"Error reading automations.yaml: {e}"]


def parse_automations_content(
    yaml_content: str,
) -> tuple[dict[str, list[str]], list[str]]:
    """Parse YAML string content of automations.yaml.

    Args:
        yaml_content: YAML content string.

    Returns:
        Tuple of (automation_to_entities_map, warnings_list).
    """
    warnings: list[str] = []
    auto_map: dict[str, list[str]] = {}

    try:
        data = yaml.safe_load(yaml_content)
    except Exception as e:
        return {}, [f"YAML syntax error in automations.yaml: {e}"]

    if not isinstance(data, list):
        if isinstance(data, dict):
            data = [data]
        else:
            return {}, ["automations.yaml content is not a list or dictionary"]

    for idx, item in enumerate(data):
        if not isinstance(item, dict):
            continue

        alias = item.get("alias") or item.get("id") or f"automation_{idx + 1}"
        referenced_entities: set[str] = set()

        _extract_entities_recursive(item, referenced_entities, warnings, alias)

        auto_map[alias] = sorted(referenced_entities)

    return auto_map, warnings


def _extract_entities_recursive(
    obj: Any,
    entity_set: set[str],
    warnings: list[str],
    context: str,
    key_context: str = "",
) -> None:
    """Recursively inspect object fields for entity_id references or Jinja expressions."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ["entity_id", "entities"]:
                if isinstance(v, str):
                    if _is_valid_entity_id(v):
                        entity_set.add(v)
                elif isinstance(v, list):
                    for item in v:
                        if isinstance(item, str) and _is_valid_entity_id(item):
                            entity_set.add(item)
            elif k == "service":
                # Ignore service name string e.g. service: light.turn_on
                continue
            else:
                _extract_entities_recursive(v, entity_set, warnings, context, key_context=str(k))

    elif isinstance(obj, list):
        for item in obj:
            _extract_entities_recursive(item, entity_set, warnings, context, key_context)

    elif isinstance(obj, str):
        if key_context == "service":
            return

        matches = ENTITY_ID_REGEX.findall(obj)
        for m in matches:
            if _is_valid_entity_id(m):
                entity_set.add(m)

        if "{" in obj and ("states(" in obj or "is_state(" in obj or "state_attr(" in obj):
            if re.search(r"states\(\s*['\"][^'\"]*\{\{", obj):
                warnings.append(
                    f"Ambiguous dynamic entity expression in automation '{context}': {obj[:60]}"
                )


def _is_valid_entity_id(entity_id: str) -> bool:
    """Check if string is a valid entity ID and not a service call."""
    if "." not in entity_id:
        return False
    parts = entity_id.split(".", 1)
    if parts[1] in SERVICE_SUFFIXES:
        return False
    return True
