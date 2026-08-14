"""AI-friendly Configuration Summary Exporter.

Generates safe, structured Markdown analysis files under ai/configuration/.
"""

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def export_ai_configuration_summary(output_dir: Path, analysis_data: dict[str, Any]) -> None:
    """Generate safe Markdown configuration summaries under ai/configuration/.

    Args:
        output_dir: Staging root directory.
        analysis_data: Dictionary of analysis results returned by analyze_all_configuration.
    """
    config_out = output_dir / "ai" / "configuration"
    config_out.mkdir(parents=True, exist_ok=True)

    overview = analysis_data.get("overview", {})
    ha_summary = analysis_data.get("home_assistant", {})
    esphome_summary = analysis_data.get("esphome", {})
    packages_summary = analysis_data.get("packages", {})
    auto_summary = analysis_data.get("automations_scripts_scenes", {})
    dashboard_summary = analysis_data.get("dashboards", {})
    mqtt_summary = analysis_data.get("mqtt", {})
    frigate_summary = analysis_data.get("frigate", {})
    z2m_summary = analysis_data.get("zigbee2mqtt", {})
    cc_summary = analysis_data.get("custom_components", {})
    warnings = analysis_data.get("warnings", [])

    # 1. README.md
    readme_content = (
        "# AI Configuration Summary Layer\n\n"
        "> **NOTICE**: Generated structural summaries for AI reference context.\n>\n"
        "> - **NOT A BACKUP**: These summaries do not contain raw YAML or raw "
        "configuration files.\n"
        "> - **NO RAW SECRETS**: Secret-bearing fields (passwords, tokens, API keys, Wi-Fi keys, "
        "encryption keys) are replaced with safe semantic markers (`configured`, `enabled`, "
        "`secret reference`, or `redacted`).\n"
        "> - **INVENTORY LOCATION**: Authoritative entity, device, and area registries remain in "
        "`inventory/` and `references/`.\n"
        "> - **ADVANCED RAW EXPORT**: Copying raw configuration files is controlled by "
        "`advanced.raw_configuration_export` (disabled by default).\n"
    )
    (config_out / "README.md").write_text(readme_content, encoding="utf-8")

    # 2. overview.md
    frigate_st = "Detected" if overview.get("frigate_detected") else "Not Detected"
    z2m_st = "Detected" if overview.get("zigbee2mqtt_detected") else "Not Detected"
    mqtt_st = "Detected" if overview.get("mqtt_detected") else "Not Detected"

    overview_md = f"""# Configuration Overview

| Metric | Value |
| :--- | :--- |
| **Analyzed Directory** | `{overview.get("config_dir", "")}` |
| **Analyzed Configuration Files** | {overview.get("files_analyzed_count", 0)} |
| **Analysis Warnings** | {overview.get("warnings_count", 0)} |
| **ESPHome Nodes** | {overview.get("esphome_node_count", 0)} |
| **Packages Discovered** | {overview.get("package_count", 0)} |
| **Automations Defined** | {overview.get("automation_count", 0)} |
| **Scripts Defined** | {overview.get("script_count", 0)} |
| **Scenes Defined** | {overview.get("scene_count", 0)} |
| **Dashboards Discovered** | {overview.get("dashboard_count", 0)} |
| **MQTT Integration** | {mqtt_st} |
| **Frigate NVR Integration** | {frigate_st} |
| **Zigbee2MQTT Integration** | {z2m_st} |
| **Custom Components** | {overview.get("custom_components_count", 0)} |
"""
    (config_out / "overview.md").write_text(overview_md, encoding="utf-8")

    # 3. home-assistant.md
    ha_lines = ["# Home Assistant Structural Configuration Summary\n"]
    ha_lines.append("## Top-Level Domains")
    for d in ha_summary.get("top_level_domains", []):
        ha_lines.append(f"- `{d}`")

    ha_lines.append("\n## Sensitive & Core Section Status")
    sens = ha_summary.get("sensitive_sections", {})
    if sens:
        for k, v in sens.items():
            ha_lines.append(f"- **{k}**: `{v}`")
    else:
        ha_lines.append("No special sensitive sections flagged.")

    (config_out / "home-assistant.md").write_text("\n".join(ha_lines) + "\n", encoding="utf-8")

    # 4. esphome.md
    esp_lines = ["# ESPHome Structural Summary\n"]
    nodes = esphome_summary.get("nodes", [])
    if nodes:
        for n in nodes:
            esp_lines.append(f"## Node: {n['node_name']}")
            esp_lines.append(f"- **Friendly Name**: {n['friendly_name']}")
            esp_lines.append(f"- **Platform / Board**: `{n['platform']}` ({n['framework']})")
            esp_lines.append(f"- **Wi-Fi Password**: `{n['wifi_password']}`")
            esp_lines.append(f"- **OTA Password**: `{n['ota_password']}`")
            esp_lines.append(f"- **API Encryption**: `{n['api_encryption']}`")
            esp_lines.append(f"- **Bluetooth Proxy**: {'Yes' if n['bluetooth_proxy'] else 'No'}")
            esp_lines.append(f"- **Components**: {', '.join(n['components'])}")
            if n["substitutions_keys"]:
                esp_lines.append(f"- **Substitutions Keys**: {', '.join(n['substitutions_keys'])}")
            esp_lines.append("")
    else:
        esp_lines.append("No ESPHome configuration files detected.")

    (config_out / "esphome.md").write_text("\n".join(esp_lines) + "\n", encoding="utf-8")

    # 5. packages.md
    pkg_lines = ["# Packages Summary\n"]
    pkgs = packages_summary.get("packages", [])
    if pkgs:
        for p in pkgs:
            pkg_lines.append(f"### Package: `{p['package_file']}`")
            pkg_lines.append(f"- **Domains Configured**: {', '.join(p['domains'])}")
    else:
        pkg_lines.append("No Home Assistant package files detected.")

    (config_out / "packages.md").write_text("\n".join(pkg_lines) + "\n", encoding="utf-8")

    # 6. automations.md, 7. scripts.md, 8. scenes.md
    (config_out / "automations.md").write_text(
        f"# Automations Summary\n\nTotal Automations: {auto_summary.get('automation_count', 0)}\n",
        encoding="utf-8",
    )
    (config_out / "scripts.md").write_text(
        f"# Scripts Summary\n\nTotal Scripts: {auto_summary.get('script_count', 0)}\n",
        encoding="utf-8",
    )
    (config_out / "scenes.md").write_text(
        f"# Scenes Summary\n\nTotal Scenes: {auto_summary.get('scene_count', 0)}\n",
        encoding="utf-8",
    )

    # 9. dashboards.md
    dash_cnt = dashboard_summary.get("dashboard_count", 0)
    dash_content = f"# Dashboards Summary\n\nTotal Dashboards Discovered: {dash_cnt}\n"
    (config_out / "dashboards.md").write_text(dash_content, encoding="utf-8")

    # 10. mqtt.md
    mqtt_lines = [
        "# MQTT Summary\n",
        f"- **Detected**: {'Yes' if mqtt_summary.get('detected') else 'No'}",
        f"- **Discovery Enabled**: {'Yes' if mqtt_summary.get('discovery_enabled') else 'No'}",
        f"- **Entity Count**: {mqtt_summary.get('entity_count', 0)}",
        f"- **TLS Status**: `{mqtt_summary.get('tls_enabled', 'not configured')}`",
        f"- **Username**: `{mqtt_summary.get('username_configured', 'not configured')}`",
        f"- **Password**: `{mqtt_summary.get('password_configured', 'not configured')}`",
    ]
    (config_out / "mqtt.md").write_text("\n".join(mqtt_lines) + "\n", encoding="utf-8")

    # 11. frigate.md
    frig_lines = [
        "# Frigate Summary\n",
        f"- **Detected**: {'Yes' if frigate_summary.get('detected') else 'No'}",
    ]
    if frigate_summary.get("detected"):
        frig_lines.append(f"- **Camera Count**: {frigate_summary.get('camera_count', 0)}")
        frig_lines.append(f"- **Cameras**: {', '.join(frigate_summary.get('cameras', []))}")
        frig_lines.append(
            f"- **Detectors**: {', '.join(frigate_summary.get('detector_types', []))}"
        )
        frig_lines.append(
            f"- **MQTT Enabled**: {'Yes' if frigate_summary.get('mqtt_enabled') else 'No'}"
        )
        frig_lines.append(
            f"- **go2rtc Enabled**: {'Yes' if frigate_summary.get('go2rtc_enabled') else 'No'}"
        )
    (config_out / "frigate.md").write_text("\n".join(frig_lines) + "\n", encoding="utf-8")

    # 12. zigbee2mqtt.md
    z2m_lines = [
        "# Zigbee2MQTT Summary\n",
        f"- **Detected**: {'Yes' if z2m_summary.get('detected') else 'No'}",
    ]
    if z2m_summary.get("detected"):
        z2m_lines.append(f"- **Frontend**: `{z2m_summary.get('frontend_status', 'disabled')}`")
        z2m_lines.append(f"- **MQTT Status**: `{z2m_summary.get('mqtt_status', 'not configured')}`")
        z2m_lines.append(f"- **Permit Join**: {'Yes' if z2m_summary.get('permit_join') else 'No'}")
    (config_out / "zigbee2mqtt.md").write_text("\n".join(z2m_lines) + "\n", encoding="utf-8")

    # 13. custom-components.md
    cc_lines = ["# Custom Components Summary\n"]
    comps = cc_summary.get("components", [])
    if comps:
        for c in comps:
            cc_lines.append(f"### Component: `{c['domain']}`")
            cc_lines.append(f"- **Name**: {c['name']}")
            cc_lines.append(f"- **Version**: {c['version']}")
            cc_lines.append(f"- **Config Flow**: {'Yes' if c['config_flow'] else 'No'}")
            if c["documentation"]:
                cc_lines.append(f"- **Documentation**: {c['documentation']}")
    else:
        cc_lines.append("No custom components detected.")

    (config_out / "custom-components.md").write_text("\n".join(cc_lines) + "\n", encoding="utf-8")

    # 14. warnings.md
    warn_lines = ["# Configuration Analysis Warnings\n"]
    if warnings:
        for w in warnings:
            warn_lines.append(f"- {w}")
    else:
        warn_lines.append("No configuration analysis warnings reported.")

    (config_out / "warnings.md").write_text("\n".join(warn_lines) + "\n", encoding="utf-8")

    logger.info("Generated 14 AI configuration summary files in %s", config_out)
