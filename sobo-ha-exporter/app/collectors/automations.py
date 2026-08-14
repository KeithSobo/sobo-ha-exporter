"""Automation collector and reference extraction engine for Home Assistant."""

import logging
import re
from pathlib import Path
from typing import Any

from app.analyzers.config_parser import SafeYamlParser
from app.config import get_config_dir
from app.models.automation import AutomationModel

logger = logging.getLogger(__name__)

# Entity ID regex matching domain.object_id
ENTITY_ID_REGEX = re.compile(
    r"\b(?:light|switch|sensor|binary_sensor|climate|cover|fan|media_player|camera|lock|"
    r"vacuum|alarm_control_panel|automation|script|scene|person|zone|input_boolean|"
    r"input_number|input_select|input_text|input_datetime|input_button|counter|timer|"
    r"schedule|group|template)\.[a-z0-9_]+\b"
)

# Helper domain prefixes
HELPER_DOMAINS = {
    "input_boolean",
    "input_number",
    "input_select",
    "input_text",
    "input_datetime",
    "input_button",
    "counter",
    "timer",
    "schedule",
    "group",
    "template",
}

# Service call suffixes to avoid treating light.turn_on as an entity
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
    "trigger",
}

# Jinja pattern matching for entity IDs
JINJA_ENTITY_PATTERNS = [
    re.compile(r"states\(\s*['\"]([a-z0-9_]+\.[a-z0-9_]+)['\"]"),
    re.compile(r"is_state\(\s*['\"]([a-z0-9_]+\.[a-z0-9_]+)['\"]"),
    re.compile(r"state_attr\(\s*['\"]([a-z0-9_]+\.[a-z0-9_]+)['\"]"),
    re.compile(r"is_state_attr\(\s*['\"]([a-z0-9_]+\.[a-z0-9_]+)['\"]"),
    re.compile(r"\bstates\.([a-z0-9_]+\.[a-z0-9_]+)\.(?:state|attributes)\b"),
    re.compile(r"expand\(\s*['\"]([a-z0-9_]+\.[a-z0-9_]+)['\"]"),
]


def collect_automations(
    config_dir: Path | str | None = None,
) -> tuple[dict[str, list[str]], list[str]]:
    """Parse automations and extract entity references per automation.

    Args:
        config_dir: Read-only mounted HA config directory.

    Returns:
        Tuple of (automation_to_entities_map, warnings_list).
    """
    models, warnings = collect_automation_models(config_dir)
    auto_map: dict[str, list[str]] = {}
    for m in models:
        auto_map[m.alias] = m.entities
    return auto_map, warnings


def collect_automation_models(
    config_dir: Path | str | None = None,
) -> tuple[list[AutomationModel], list[str]]:
    """Discover and parse automations from all Home Assistant config sources.

    Args:
        config_dir: Config directory path.

    Returns:
        Tuple of (automation_models_list, warnings_list).
    """
    c_dir = Path(config_dir).resolve() if config_dir is not None else get_config_dir().resolve()
    warnings: list[str] = []
    models: list[AutomationModel] = []
    seen_keys: set[tuple[str, str]] = set()

    if not c_dir.exists():
        return [], [f"Configuration directory not found at {c_dir}"]

    parser = SafeYamlParser(c_dir)

    # 1. Parse automations.yaml if it exists
    auto_file = c_dir / "automations.yaml"
    if auto_file.exists():
        _discover_automations_in_file(auto_file, c_dir, parser, models, seen_keys, warnings)

    # 2. Parse configuration.yaml if it exists to resolve includes/packages
    cfg_file = c_dir / "configuration.yaml"
    if cfg_file.exists():
        _discover_automations_in_file(cfg_file, c_dir, parser, models, seen_keys, warnings)

    # 3. Scan all remaining YAML files in config_dir (e.g. packages/, automations/ subdirs)
    for yaml_path in c_dir.rglob("*.yaml"):
        if yaml_path.name in ["automations.yaml", "configuration.yaml"]:
            continue
        # Avoid hidden directories or temp files
        if any(part.startswith(".") for part in yaml_path.parts):
            continue
        _discover_automations_in_file(yaml_path, c_dir, parser, models, seen_keys, warnings)

    # Add parser warnings
    for w in parser.warnings:
        if w not in warnings:
            warnings.append(w)

    # Validate duplicates and missing properties
    _validate_automation_models(models, warnings)

    models.sort(key=lambda x: (x.alias.lower(), x.id))
    return models, warnings


def _discover_automations_in_file(
    file_path: Path,
    base_dir: Path,
    parser: SafeYamlParser,
    models: list[AutomationModel],
    seen_keys: set[tuple[str, str]],
    warnings: list[str],
) -> None:
    """Read and parse a YAML file looking for automation definitions."""
    try:
        rel_str = str(file_path.relative_to(base_dir)).replace("\\", "/")
    except ValueError:
        rel_str = str(file_path).replace("\\", "/")

    data, file_warns = parser.parse_file(file_path)
    warnings.extend(file_warns)

    if not data:
        return

    _extract_automations_from_node(data, rel_str, models, seen_keys)


def _extract_automations_from_node(
    data: Any,
    source_file: str,
    models: list[AutomationModel],
    seen_keys: set[tuple[str, str]],
) -> None:
    """Recursively extract automation nodes from parsed YAML structure."""
    if isinstance(data, list):
        for idx, item in enumerate(data):
            if isinstance(item, dict) and _is_automation_dict(item):
                _add_automation_model(item, source_file, idx, models, seen_keys)
            elif isinstance(item, dict):
                _extract_automations_from_node(item, source_file, models, seen_keys)

    elif isinstance(data, dict):
        if _is_automation_dict(data):
            _add_automation_model(data, source_file, 0, models, seen_keys)
            return

        for key, val in data.items():
            if str(key).startswith("automation"):
                if isinstance(val, list):
                    for idx, item in enumerate(val):
                        if isinstance(item, dict) and _is_automation_dict(item):
                            _add_automation_model(item, source_file, idx, models, seen_keys)
                        else:
                            _extract_automations_from_node(item, source_file, models, seen_keys)
                elif isinstance(val, dict):
                    if _is_automation_dict(val):
                        _add_automation_model(val, source_file, 0, models, seen_keys)
                    else:
                        for sub_k, sub_v in val.items():
                            if isinstance(sub_v, dict) and _is_automation_dict(sub_v):
                                _add_automation_model(
                                    sub_v, source_file, 0, models, seen_keys, default_id=str(sub_k)
                                )
                            else:
                                _extract_automations_from_node(
                                    sub_v, source_file, models, seen_keys
                                )
            elif key == "packages":
                _extract_automations_from_node(val, source_file, models, seen_keys)
            elif isinstance(val, (dict, list)):
                # If key is an automation ID mapping
                # (e.g. enable_guest_mode: {alias: ..., trigger: ...})
                if isinstance(val, dict) and _is_automation_dict(val):
                    _add_automation_model(
                        val, source_file, 0, models, seen_keys, default_id=str(key)
                    )


def _is_automation_dict(item: dict[str, Any]) -> bool:
    """Check if a dictionary node represents a Home Assistant automation."""
    has_trigger = "trigger" in item or "triggers" in item or "platform" in item
    has_action = "action" in item or "actions" in item or "sequence" in item
    has_alias_id = "alias" in item or "id" in item
    return (has_trigger and has_action) or (has_alias_id and (has_trigger or has_action))


def _add_automation_model(
    item: dict[str, Any],
    source_file: str,
    idx: int,
    models: list[AutomationModel],
    seen_keys: set[tuple[str, str]],
    default_id: str | None = None,
) -> None:
    """Parse dict into AutomationModel and append if not previously seen."""
    model = parse_automation_dict(item, source_file, idx, default_id=default_id)
    key = (model.id, model.alias)
    if key in seen_keys:
        return
    seen_keys.add(key)
    models.append(model)


def parse_automation_dict(
    item: dict[str, Any],
    source_file: str = "automations.yaml",
    idx: int = 0,
    default_id: str | None = None,
) -> AutomationModel:
    """Parse automation dictionary into normalized AutomationModel."""
    alias = str(item.get("alias") or item.get("id") or default_id or f"automation_{idx + 1}")
    auto_id = str(item.get("id") or default_id or alias)
    description = str(item.get("description")) if item.get("description") is not None else None
    mode = str(item.get("mode") or "single")
    enabled = bool(item.get("initial_state", item.get("enabled", True)))

    raw_triggers = item.get("trigger") or item.get("triggers")
    raw_conditions = item.get("condition") or item.get("conditions")
    raw_actions = item.get("action") or item.get("actions") or item.get("sequence")

    triggers_summary = _summarize_triggers(raw_triggers)
    conditions_summary = _summarize_conditions(raw_conditions)
    actions_summary = _summarize_actions(raw_actions)

    entities: set[str] = set()
    devices: set[str] = set()
    areas: set[str] = set()
    called_services: set[str] = set()
    called_scripts: set[str] = set()
    called_scenes: set[str] = set()
    called_automations: set[str] = set()
    event_types: set[str] = set()
    navigation_targets: set[str] = set()
    unresolved_templates: set[str] = set()
    warnings: list[str] = []
    entity_usage_map: dict[str, set[str]] = {}

    # Recursive walk
    _walk_node(
        raw_triggers,
        "trigger",
        entities,
        devices,
        areas,
        called_services,
        called_scripts,
        called_scenes,
        called_automations,
        event_types,
        navigation_targets,
        unresolved_templates,
        warnings,
        entity_usage_map,
        alias,
    )
    _walk_node(
        raw_conditions,
        "condition",
        entities,
        devices,
        areas,
        called_services,
        called_scripts,
        called_scenes,
        called_automations,
        event_types,
        navigation_targets,
        unresolved_templates,
        warnings,
        entity_usage_map,
        alias,
    )
    _walk_node(
        raw_actions,
        "action",
        entities,
        devices,
        areas,
        called_services,
        called_scripts,
        called_scenes,
        called_automations,
        event_types,
        navigation_targets,
        unresolved_templates,
        warnings,
        entity_usage_map,
        alias,
    )

    helpers = sorted(
        {e for e in entities if e.split(".")[0] in HELPER_DOMAINS or e.startswith("template.")}
    )

    return AutomationModel(
        id=auto_id,
        alias=alias,
        source_file=source_file,
        source_path=f"id:{auto_id}" if auto_id != alias else None,
        description=description,
        mode=mode,
        enabled=enabled,
        triggers=triggers_summary,
        conditions=conditions_summary,
        actions=actions_summary,
        entities=sorted(entities),
        devices=sorted(devices),
        areas=sorted(areas),
        helpers=helpers,
        called_services=sorted(called_services),
        called_scripts=sorted(called_scripts),
        called_scenes=sorted(called_scenes),
        called_automations=sorted(called_automations),
        event_types=sorted(event_types),
        navigation_targets=sorted(navigation_targets),
        unresolved_templates=sorted(unresolved_templates),
        warnings=warnings,
        entity_usage_map=entity_usage_map,
    )


def _walk_node(
    obj: Any,
    context_section: str,
    entities: set[str],
    devices: set[str],
    areas: set[str],
    called_services: set[str],
    called_scripts: set[str],
    called_scenes: set[str],
    called_automations: set[str],
    event_types: set[str],
    navigation_targets: set[str],
    unresolved_templates: set[str],
    warnings: list[str],
    entity_usage_map: dict[str, set[str]],
    alias: str,
    key_ctx: str = "",
) -> None:
    """Recursively walk automation structures extracting references."""
    if isinstance(obj, dict):
        # Service or Action call
        srv = obj.get("service") or obj.get("action")
        if isinstance(srv, str) and "." in srv:
            called_services.add(srv)
            domain = srv.split(".", 1)[0]
            if domain == "script":
                called_scripts.add(srv)
            elif domain == "scene":
                called_scenes.add(srv)
            elif domain == "automation":
                called_automations.add(srv)

        # Device ID
        dev_id = obj.get("device_id")
        if isinstance(dev_id, str):
            devices.add(dev_id)
        elif isinstance(dev_id, list):
            for d in dev_id:
                if isinstance(d, str):
                    devices.add(d)

        # Area ID
        a_id = obj.get("area_id")
        if isinstance(a_id, str):
            areas.add(a_id)
        elif isinstance(a_id, list):
            for a in a_id:
                if isinstance(a, str):
                    areas.add(a)

        # Event type
        evt = obj.get("event_type") or obj.get("event")
        if isinstance(evt, str) and not evt.startswith("{"):
            event_types.add(evt)

        # Navigation or URL target
        nav = obj.get("navigation_path") or obj.get("url")
        if isinstance(nav, str):
            navigation_targets.add(nav)

        for k, v in obj.items():
            str_k = str(k)
            if str_k in ["entity_id", "entity", "entities"]:
                _record_entity_val(v, context_section, entities, entity_usage_map)
            elif str_k == "target" and isinstance(v, dict):
                if "entity_id" in v:
                    _record_entity_val(
                        v["entity_id"], context_section, entities, entity_usage_map, extra="target"
                    )
                if "device_id" in v:
                    d_val = v["device_id"]
                    if isinstance(d_val, str):
                        devices.add(d_val)
                    elif isinstance(d_val, list):
                        for d in d_val:
                            if isinstance(d, str):
                                devices.add(d)
                if "area_id" in v:
                    a_val = v["area_id"]
                    if isinstance(a_val, str):
                        areas.add(a_val)
                    elif isinstance(a_val, list):
                        for a in a_val:
                            if isinstance(a, str):
                                areas.add(a)
            else:
                _walk_node(
                    v,
                    context_section,
                    entities,
                    devices,
                    areas,
                    called_services,
                    called_scripts,
                    called_scenes,
                    called_automations,
                    event_types,
                    navigation_targets,
                    unresolved_templates,
                    warnings,
                    entity_usage_map,
                    alias,
                    key_ctx=str_k,
                )

    elif isinstance(obj, list):
        for item in obj:
            _walk_node(
                item,
                context_section,
                entities,
                devices,
                areas,
                called_services,
                called_scripts,
                called_scenes,
                called_automations,
                event_types,
                navigation_targets,
                unresolved_templates,
                warnings,
                entity_usage_map,
                alias,
                key_ctx,
            )

    elif isinstance(obj, str):
        # Extract direct entity IDs if key matches entity context
        if key_ctx in ["entity_id", "entity", "entities"]:
            _record_entity_val(obj, context_section, entities, entity_usage_map)

        # Generic regex match for entity IDs
        for match in ENTITY_ID_REGEX.findall(obj):
            if _is_valid_entity_id(match):
                _record_entity_val(match, context_section, entities, entity_usage_map)

        # Template pattern matching
        if "{" in obj:
            found_template_entity = False
            for pat in JINJA_ENTITY_PATTERNS:
                for match in pat.findall(obj):
                    if _is_valid_entity_id(match):
                        _record_entity_val(
                            match, context_section, entities, entity_usage_map, extra="template"
                        )
                        found_template_entity = True

            # Dynamic expression recording
            if "{{" in obj or "{%" in obj:
                if re.search(r"states\(\s*[^'\"]", obj) or re.search(r"is_state\(\s*[^'\"]", obj):
                    unresolved_templates.add(obj.strip())
                    if not found_template_entity and alias:
                        warnings.append(
                            f"Ambiguous dynamic template expression in '{alias}': {obj[:60]}"
                        )


def _record_entity_val(
    val: Any,
    section: str,
    entities: set[str],
    usage_map: dict[str, set[str]],
    extra: str | None = None,
) -> None:
    """Record entity ID and tag its usage context."""
    if isinstance(val, str):
        if _is_valid_entity_id(val):
            entities.add(val)
            if val not in usage_map:
                usage_map[val] = set()
            usage_map[val].add(section)
            if extra:
                usage_map[val].add(extra)
    elif isinstance(val, list):
        for item in val:
            if isinstance(item, str) and _is_valid_entity_id(item):
                entities.add(item)
                if item not in usage_map:
                    usage_map[item] = set()
                usage_map[item].add(section)
                if extra:
                    usage_map[item].add(extra)


def _is_valid_entity_id(entity_id: str) -> bool:
    """Check if string is a valid entity ID and not a service call."""
    if "." not in entity_id:
        return False
    parts = entity_id.split(".", 1)
    if parts[1] in SERVICE_SUFFIXES:
        return False
    return True


def _summarize_triggers(raw: Any) -> list[str]:
    """Build clean human-readable trigger descriptions."""
    if not raw:
        return []
    items = raw if isinstance(raw, list) else [raw]
    summaries: list[str] = []

    for item in items:
        if isinstance(item, dict):
            plat = str(item.get("trigger") or item.get("platform") or "unknown")
            ent = item.get("entity_id") or item.get("entity")
            if isinstance(ent, list):
                ent_str = ", ".join(str(e) for e in ent)
            else:
                ent_str = str(ent) if ent else ""

            to_st = item.get("to")
            from_st = item.get("from")
            at_time = item.get("at")

            if plat == "state":
                desc = f"state of {ent_str}" if ent_str else "state change"
                if to_st is not None:
                    desc += f" to '{to_st}'"
                if from_st is not None:
                    desc += f" from '{from_st}'"
                summaries.append(desc)
            elif plat == "numeric_state":
                desc = f"numeric_state of {ent_str}" if ent_str else "numeric state"
                above = item.get("above")
                below = item.get("below")
                if above is not None:
                    desc += f" > {above}"
                if below is not None:
                    desc += f" < {below}"
                summaries.append(desc)
            elif plat == "time":
                summaries.append(f"time at {at_time or 'specified time'}")
            elif plat == "event":
                evt = item.get("event_type") or "event"
                summaries.append(f"event '{evt}'")
            elif plat == "webhook":
                hook = item.get("webhook_id") or "webhook"
                summaries.append(f"webhook '{hook}'")
            elif plat == "template":
                summaries.append("template trigger")
            else:
                s = f"{plat} trigger"
                if ent_str:
                    s += f" ({ent_str})"
                summaries.append(s)
        elif isinstance(item, str):
            summaries.append(item)

    return summaries


def _summarize_conditions(raw: Any) -> list[str]:
    """Build clean human-readable condition descriptions."""
    if not raw:
        return []
    items = raw if isinstance(raw, list) else [raw]
    summaries: list[str] = []

    for item in items:
        if isinstance(item, dict):
            cond = str(item.get("condition") or item.get("platform") or "unknown")
            ent = item.get("entity_id") or item.get("entity")
            ent_str = str(ent) if ent else ""
            st = item.get("state")

            if cond == "state":
                s = f"state {ent_str}" if ent_str else "state condition"
                if st is not None:
                    s += f" == '{st}'"
                summaries.append(s)
            elif cond == "numeric_state":
                s = f"numeric_state {ent_str}" if ent_str else "numeric state condition"
                above = item.get("above")
                below = item.get("below")
                if above is not None:
                    s += f" > {above}"
                if below is not None:
                    s += f" < {below}"
                summaries.append(s)
            elif cond == "time":
                after = item.get("after")
                before = item.get("before")
                s = "time condition"
                if after:
                    s += f" after {after}"
                if before:
                    s += f" before {before}"
                summaries.append(s)
            elif cond == "template":
                summaries.append("template condition")
            elif cond in ["and", "or", "not"]:
                nested = item.get("conditions")
                n_cnt = len(nested) if isinstance(nested, list) else 0
                summaries.append(f"logical {cond} ({n_cnt} conditions)")
            else:
                s = f"{cond} condition"
                if ent_str:
                    s += f" ({ent_str})"
                summaries.append(s)
        elif isinstance(item, str):
            summaries.append(item)

    return summaries


def _summarize_actions(raw: Any) -> list[str]:
    """Build clean human-readable action descriptions."""
    if not raw:
        return []
    items = raw if isinstance(raw, list) else [raw]
    summaries: list[str] = []

    for item in items:
        if isinstance(item, dict):
            srv = item.get("service") or item.get("action")
            tgt = item.get("target") or {}
            ent = item.get("entity_id") or (tgt.get("entity_id") if isinstance(tgt, dict) else None)
            ent_str = ", ".join(ent) if isinstance(ent, list) else (str(ent) if ent else "")

            if srv:
                s = f"call {srv}"
                if ent_str:
                    s += f" on {ent_str}"
                summaries.append(s)
            elif "choose" in item:
                branches = item.get("choose")
                b_cnt = len(branches) if isinstance(branches, list) else 0
                summaries.append(f"choose ({b_cnt} branches)")
            elif "repeat" in item:
                summaries.append("repeat loop")
            elif "if" in item:
                summaries.append("if-then-else action")
            elif "wait_for_trigger" in item:
                summaries.append("wait_for_trigger")
            elif "delay" in item:
                summaries.append(f"delay {item.get('delay')}")
            else:
                summaries.append("action block")
        elif isinstance(item, str):
            summaries.append(item)

    return summaries


def _validate_automation_models(
    models: list[AutomationModel],
    warnings: list[str],
) -> None:
    """Check automation integrity and record non-fatal warnings."""
    seen_ids: set[str] = set()
    seen_aliases: set[str] = set()

    for m in models:
        if m.id in seen_ids:
            msg = f"Duplicate automation ID '{m.id}' found in {m.source_file}"
            if msg not in warnings:
                warnings.append(msg)
                m.warnings.append(msg)
        else:
            seen_ids.add(m.id)

        if m.alias in seen_aliases:
            m.warnings.append(f"Duplicate automation alias '{m.alias}'")
        else:
            seen_aliases.add(m.alias)

        if not m.triggers:
            msg = f"Automation '{m.alias}' in {m.source_file} has no trigger defined"
            m.warnings.append(msg)

        if not m.actions:
            msg = f"Automation '{m.alias}' in {m.source_file} has no action defined"
            m.warnings.append(msg)
