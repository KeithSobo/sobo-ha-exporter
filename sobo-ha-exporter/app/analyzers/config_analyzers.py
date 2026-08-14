"""Structural configuration analyzers for Home Assistant, ESPHome, and integrations."""

import logging
from pathlib import Path
from typing import Any

from app.analyzers.config_parser import SafeYamlParser, is_safe_path
from app.models.area import AreaModel
from app.models.device import DeviceModel
from app.models.entity import EntityModel
from app.models.label import LabelModel

logger = logging.getLogger(__name__)

SENSITIVE_KEYS = {
    "password",
    "passwd",
    "token",
    "api_key",
    "apikey",
    "secret",
    "encryption",
    "encryption_key",
    "access_token",
    "refresh_token",
    "webhook_id",
    "client_secret",
    "private_key",
    "network_key",
    "wifi_password",
    "ota_password",
}


def sanitize_summary_val(key_name: str, val: Any) -> str:
    """Return safe semantic marker for sensitive fields in summaries."""
    k = key_name.lower()
    if any(s in k for s in SENSITIVE_KEYS):
        if isinstance(val, str) and "secret reference" in val.lower():
            return val
        if val is None or val == "":
            return "not configured"
        return "configured"
    return str(val)


def analyze_all_configuration(
    config_dir: Path,
    entities: list[EntityModel] | None = None,
    devices: list[DeviceModel] | None = None,
    areas: list[AreaModel] | None = None,
    labels: list[LabelModel] | None = None,
) -> dict[str, Any]:
    """Execute all structural analyzers on Home Assistant configuration directory.

    Args:
        config_dir: Path to Home Assistant configuration directory.
        entities: Optional list of collected entity models.
        devices: Optional list of collected device models.
        areas: Optional list of collected area models.
        labels: Optional list of collected label models.

    Returns:
        Dictionary of analysis summaries for all domains.
    """
    parser = SafeYamlParser(config_dir)
    entity_list = entities or []
    device_list = devices or []

    # 1. Main Home Assistant Analyzer
    ha_data, ha_warns = parser.parse_file("configuration.yaml")
    parser.warnings.extend(ha_warns)

    ha_summary = analyze_home_assistant(data=ha_data, config_dir=config_dir, parser=parser)

    # 2. ESPHome Analyzer
    esphome_summary = analyze_esphome(config_dir=config_dir, parser=parser)

    # 3. Packages Analyzer
    packages_summary = analyze_packages(data=ha_data, config_dir=config_dir, parser=parser)

    # 4. Automation / Script / Scene Analyzer
    auto_summary = analyze_automations_scripts_scenes(
        data=ha_data, config_dir=config_dir, parser=parser, entities=entity_list
    )

    # 5. Dashboard Analyzer
    dashboard_summary = analyze_dashboards(
        data=ha_data, config_dir=config_dir, parser=parser, entities=entity_list
    )

    # 6. MQTT Analyzer
    mqtt_summary = analyze_mqtt(
        data=ha_data, config_dir=config_dir, parser=parser, entities=entity_list
    )

    # 7. Frigate Analyzer
    frigate_summary = analyze_frigate(data=ha_data, config_dir=config_dir, parser=parser)

    # 8. Zigbee2MQTT Analyzer
    z2m_summary = analyze_zigbee2mqtt(data=ha_data, config_dir=config_dir, parser=parser)

    # 9. Custom Component Analyzer
    cc_summary = analyze_custom_components(
        config_dir=config_dir, entities=entity_list, devices=device_list
    )

    # Overview rollup
    overview_summary = {
        "config_dir": str(config_dir),
        "files_analyzed_count": len(parser.analyzed_files),
        "warnings_count": len(parser.warnings),
        "esphome_node_count": len(esphome_summary.get("nodes", [])),
        "package_count": len(packages_summary.get("packages", [])),
        "automation_count": auto_summary.get("automation_count", 0),
        "script_count": auto_summary.get("script_count", 0),
        "scene_count": auto_summary.get("scene_count", 0),
        "dashboard_count": dashboard_summary.get("dashboard_count", 0),
        "frigate_detected": frigate_summary.get("detected", False),
        "zigbee2mqtt_detected": z2m_summary.get("detected", False),
        "mqtt_detected": mqtt_summary.get("detected", False),
        "custom_components_count": len(cc_summary.get("components", [])),
    }

    return {
        "overview": overview_summary,
        "home_assistant": ha_summary,
        "esphome": esphome_summary,
        "packages": packages_summary,
        "automations_scripts_scenes": auto_summary,
        "dashboards": dashboard_summary,
        "mqtt": mqtt_summary,
        "frigate": frigate_summary,
        "zigbee2mqtt": z2m_summary,
        "custom_components": cc_summary,
        "warnings": parser.warnings,
    }


def analyze_home_assistant(data: Any, config_dir: Path, parser: SafeYamlParser) -> dict[str, Any]:
    """Analyze configuration.yaml structure safely."""
    if not isinstance(data, dict):
        return {
            "top_level_domains": [],
            "includes_detected": [],
            "unresolved_includes": [],
            "sensitive_sections": {},
        }

    domains = sorted(data.keys())
    sensitive_sections: dict[str, str] = {}

    for k, v in data.items():
        k_lower = k.lower()
        if any(s in k_lower for s in SENSITIVE_KEYS) or k_lower in {
            "mqtt",
            "http",
            "api",
            "homeassistant",
        }:
            if isinstance(v, dict):
                sub_status = []
                for sub_k, sub_v in v.items():
                    sub_status.append(f"{sub_k}: {sanitize_summary_val(sub_k, sub_v)}")
                sensitive_sections[k] = ", ".join(sub_status)
            else:
                sensitive_sections[k] = sanitize_summary_val(k, v)

    return {
        "top_level_domains": domains,
        "sensitive_sections": sensitive_sections,
    }


def analyze_esphome(config_dir: Path, parser: SafeYamlParser) -> dict[str, Any]:
    """Analyze ESPHome configuration files safely."""
    esphome_dir = config_dir / "esphome"
    yaml_files: list[Path] = []

    if esphome_dir.exists() and esphome_dir.is_dir():
        yaml_files.extend(esphome_dir.glob("*.yaml"))
        yaml_files.extend(esphome_dir.glob("*.yml"))

    # Also check root for files containing esphome:
    for root_file in config_dir.glob("*.yaml"):
        if root_file.name.startswith("esphome"):
            yaml_files.append(root_file)

    nodes: list[dict[str, Any]] = []
    for f in sorted(set(yaml_files)):
        if not is_safe_path(config_dir, f):
            continue

        data, _warns = parser.parse_file(f)
        if not isinstance(data, dict) or "esphome" not in data:
            continue

        esp_block = data.get("esphome", {})
        node_name = (
            esp_block.get("name") or data.get("substitutions", {}).get("devicename") or f.stem
        )

        wifi_block = data.get("wifi", {})
        ota_block = data.get("ota", {})
        api_block = data.get("api", {})

        subs_keys = (
            list(data.get("substitutions", {}).keys())
            if isinstance(data.get("substitutions"), dict)
            else []
        )

        nodes.append(
            {
                "file": f.name,
                "node_name": str(node_name),
                "friendly_name": str(esp_block.get("friendly_name") or node_name),
                "platform": str(
                    data.get("esp32", {}).get("board")
                    or data.get("esp8266", {}).get("board")
                    or "unknown"
                ),
                "framework": "esp-idf" if "esp32" in data else "arduino",
                "substitutions_keys": subs_keys,
                "components": [k for k in data.keys() if k not in {"esphome", "substitutions"}],
                "api_enabled": bool(api_block),
                "api_encryption": "enabled"
                if (isinstance(api_block, dict) and "encryption" in api_block)
                else "disabled",
                "ota_enabled": bool(ota_block),
                "ota_password": "configured"
                if (isinstance(ota_block, dict) and "password" in ota_block)
                else "not configured",
                "wifi_enabled": bool(wifi_block),
                "wifi_password": "configured"
                if (isinstance(wifi_block, dict) and "ssid" in wifi_block)
                else "not configured",
                "captive_portal": "captive_portal" in data,
                "web_server": "web_server" in data,
                "bluetooth_proxy": "esp32_ble_tracker" in data or "bluetooth_proxy" in data,
                "logger": "logger" in data,
            }
        )

    return {"nodes": nodes}


def analyze_packages(data: Any, config_dir: Path, parser: SafeYamlParser) -> dict[str, Any]:
    """Analyze packages directory and homeassistant.packages."""
    packages_dir = config_dir / "packages"
    packages: list[dict[str, Any]] = []

    if packages_dir.exists() and packages_dir.is_dir():
        for pf in sorted(packages_dir.rglob("*.yaml")):
            if not is_safe_path(config_dir, pf):
                continue
            rel = str(pf.relative_to(config_dir)).replace("\\", "/")
            pkg_data, _ = parser.parse_file(pf)
            domains = list(pkg_data.keys()) if isinstance(pkg_data, dict) else []
            packages.append({"package_file": rel, "domains": domains})

    return {"packages": packages}


def analyze_automations_scripts_scenes(
    data: Any, config_dir: Path, parser: SafeYamlParser, entities: list[EntityModel]
) -> dict[str, Any]:
    """Analyze automation, script, and scene counts and entity usage."""
    auto_file = config_dir / "automations.yaml"
    script_file = config_dir / "scripts.yaml"
    scene_file = config_dir / "scenes.yaml"

    auto_data, _ = parser.parse_file(auto_file) if auto_file.exists() else ([], [])
    script_data, _ = parser.parse_file(script_file) if script_file.exists() else ({}, [])
    scene_data, _ = parser.parse_file(scene_file) if scene_file.exists() else ([], [])

    auto_count = len(auto_data) if isinstance(auto_data, list) else 0
    script_count = len(script_data) if isinstance(script_data, (list, dict)) else 0
    scene_count = len(scene_data) if isinstance(scene_data, list) else 0

    return {
        "automation_count": auto_count,
        "script_count": script_count,
        "scene_count": scene_count,
    }


def analyze_dashboards(
    data: Any, config_dir: Path, parser: SafeYamlParser, entities: list[EntityModel]
) -> dict[str, Any]:
    """Analyze UI and YAML dashboards."""
    dash_count = 0
    dash_files = list(config_dir.glob("ui-lovelace*.yaml"))
    dash_count += len(dash_files)

    storage_dir = config_dir / ".storage"
    if storage_dir.exists() and storage_dir.is_dir():
        lovelace_storage = storage_dir / "lovelace"
        if lovelace_storage.exists():
            dash_count += 1

    return {"dashboard_count": dash_count, "yaml_dashboards": [f.name for f in dash_files]}


def analyze_mqtt(
    data: Any, config_dir: Path, parser: SafeYamlParser, entities: list[EntityModel]
) -> dict[str, Any]:
    """Analyze MQTT configuration safely without exposing credentials."""
    mqtt_config = {}
    if isinstance(data, dict) and "mqtt" in data:
        mqtt_config = data["mqtt"]

    mqtt_entities = [e.entity_id for e in entities if e.platform == "mqtt" or e.domain == "mqtt"]

    detected = bool(mqtt_config) or len(mqtt_entities) > 0
    return {
        "detected": detected,
        "discovery_enabled": True if detected else False,
        "entity_count": len(mqtt_entities),
        "tls_enabled": "enabled"
        if (isinstance(mqtt_config, dict) and "certificate" in mqtt_config)
        else "not configured",
        "username_configured": "configured"
        if (isinstance(mqtt_config, dict) and "username" in mqtt_config)
        else "not configured",
        "password_configured": "configured"
        if (isinstance(mqtt_config, dict) and "password" in mqtt_config)
        else "not configured",
    }


def analyze_frigate(data: Any, config_dir: Path, parser: SafeYamlParser) -> dict[str, Any]:
    """Analyze Frigate NVR configuration safely."""
    frigate_file = config_dir / "frigate.yaml"
    if not frigate_file.exists():
        frigate_file = config_dir / "frigate.yml"

    if not frigate_file.exists():
        return {"detected": False}

    f_data, _ = parser.parse_file(frigate_file)
    if not isinstance(f_data, dict):
        return {"detected": True, "cameras": []}

    cameras = (
        list(f_data.get("cameras", {}).keys()) if isinstance(f_data.get("cameras"), dict) else []
    )
    detectors = (
        list(f_data.get("detectors", {}).keys())
        if isinstance(f_data.get("detectors"), dict)
        else []
    )

    return {
        "detected": True,
        "camera_count": len(cameras),
        "cameras": cameras,
        "detector_types": detectors,
        "mqtt_enabled": "mqtt" in f_data,
        "go2rtc_enabled": "go2rtc" in f_data,
    }


def analyze_zigbee2mqtt(data: Any, config_dir: Path, parser: SafeYamlParser) -> dict[str, Any]:
    """Analyze Zigbee2MQTT configuration safely."""
    z2m_file = config_dir / "zigbee2mqtt" / "configuration.yaml"
    if not z2m_file.exists():
        return {"detected": False}

    z_data, _ = parser.parse_file(z2m_file)
    if not isinstance(z_data, dict):
        return {"detected": True}

    frontend = "enabled" if "frontend" in z_data else "disabled"
    mqtt_cfg = "configured" if "mqtt" in z_data else "not configured"

    return {
        "detected": True,
        "frontend_status": frontend,
        "mqtt_status": mqtt_cfg,
        "permit_join": bool(z_data.get("permit_join", False)),
    }


def analyze_custom_components(
    config_dir: Path, entities: list[EntityModel], devices: list[DeviceModel]
) -> dict[str, Any]:
    """Analyze installed custom components safely."""
    cc_dir = config_dir / "custom_components"
    components: list[dict[str, Any]] = []

    if cc_dir.exists() and cc_dir.is_dir():
        for d in sorted(cc_dir.iterdir()):
            if d.is_dir() and not d.name.startswith("."):
                manifest_file = d / "manifest.json"
                manifest: dict[str, Any] = {}
                if manifest_file.exists():
                    try:
                        import json

                        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
                    except Exception:
                        pass

                components.append(
                    {
                        "domain": d.name,
                        "name": manifest.get("name", d.name),
                        "version": manifest.get("version", "unknown"),
                        "documentation": manifest.get("documentation", ""),
                        "codeowners": manifest.get("codeowners", []),
                        "config_flow": bool(manifest.get("config_flow", False)),
                    }
                )

    return {"components": components}
