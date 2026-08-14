"""Unit tests for JSON, YAML, and Markdown exporters."""

from app.exporters.json_exporter import (
    export_inventory_json,
    export_metadata_json,
    export_references_json,
)
from app.exporters.markdown_exporter import export_summaries_markdown
from app.exporters.yaml_exporter import export_config_yaml
from app.models.area import AreaModel
from app.models.device import DeviceModel
from app.models.entity import EntityModel
from app.models.label import LabelModel
from app.models.relationship import RelationshipModel


def test_export_pipeline(tmp_path):
    entities = [
        EntityModel(entity_id="sensor.b", name="Sensor B"),
        EntityModel(entity_id="sensor.a", name="Sensor A"),
    ]
    devices = [DeviceModel(device_id="dev1", name="Device One")]
    areas = [AreaModel(area_id="living_room", name="Living Room")]
    labels = [LabelModel(label_id="test", name="Test Label")]
    integrations = [{"domain": "zha", "name": "Zigbee", "device_count": 1, "entity_count": 2}]
    relationships = RelationshipModel()

    export_inventory_json(
        output_dir=tmp_path,
        entities=entities,
        devices=devices,
        areas=areas,
        labels=labels,
        integrations=integrations,
        relationships=relationships,
    )

    export_references_json(output_dir=tmp_path, relationships=relationships)

    export_summaries_markdown(
        output_dir=tmp_path,
        entities=entities,
        devices=devices,
        areas=areas,
        integrations=integrations,
    )

    export_config_yaml(
        output_dir=tmp_path,
        config_files={"configuration.yaml": "homeassistant:\n  name: Home\n"},
    )

    export_metadata_json(
        output_dir=tmp_path,
        export_info={"test": 1},
        exporter_version={"version": "0.1.0"},
        sanitization_report={"enabled": True},
        warnings=["warning 1"],
    )

    # Check generated paths
    assert (tmp_path / "inventory" / "entities.json").exists()
    assert (tmp_path / "inventory" / "devices.json").exists()
    assert (tmp_path / "references" / "automation-entity-map.json").exists()
    assert (tmp_path / "summaries" / "entity-summary.md").exists()
    assert (tmp_path / "config" / "configuration.yaml").exists()
    assert (tmp_path / "metadata" / "export-info.json").exists()


def test_export_panels_json_and_usage_map(tmp_path):
    from app.exporters.json_exporter import build_entity_usage_map, export_panels_json
    from app.models.automation import AutomationModel
    from app.models.dashboard import CardModel, DashboardModel, PanelModel, ViewModel

    panel = PanelModel(
        title="Home Panel",
        url_path="lovelace",
        component_name="lovelace",
        panel_type="lovelace_storage",
        icon="mdi:home",
        require_admin=False,
        source="websocket",
        lovelace_config_available=True,
    )
    export_panels_json(output_dir=tmp_path, panels=[panel])
    assert (tmp_path / "inventory" / "panels.json").exists()

    dash = DashboardModel(
        id="dash1",
        title="Main Dash",
        url_path=None,
        icon=None,
        mode="storage",
        source="websocket",
        require_admin=False,
        default_dashboard=True,
        views=[
            ViewModel(
                title="Overview",
                cards=[
                    CardModel(
                        type="tile",
                        entities=["light.kitchen"],
                        nested_cards=[CardModel(type="button", entities=["switch.fan"])],
                    )
                ],
            )
        ],
    )

    auto = AutomationModel(
        id="auto1",
        alias="Kitchen Auto",
        source_file="automations.yaml",
        entities=["light.kitchen"],
        entity_usage_map={"light.kitchen": {"action"}},
    )

    scripts = [
        {
            "id": "script_bed",
            "alias": "Bed Script",
            "references": ["light.bedroom"],
        }
    ]

    usage_map = build_entity_usage_map(
        automation_models=[auto],
        scripts_detailed=scripts,
        dashboards=[dash],
        entities=[EntityModel(entity_id="light.kitchen", name="Kitchen Light")],
    )

    assert "light.kitchen" in usage_map
    assert "light.bedroom" in usage_map
    assert "switch.fan" in usage_map
    assert len(usage_map["light.kitchen"]["automations"]) == 1
    assert len(usage_map["light.kitchen"]["dashboards"]) == 1
    assert len(usage_map["light.bedroom"]["scripts"]) == 1


def test_export_ai_config_analysis_full(tmp_path):
    from app.exporters.ai_config_exporter import export_ai_configuration_summary

    analysis_data = {
        "overview": {"ha_name": "Home"},
        "home_assistant": {"name": "Home", "version": "2026.8.0"},
        "esphome": {
            "nodes": [
                {
                    "node_name": "living-room-sensor",
                    "friendly_name": "Living Room Sensor",
                    "platform": "esp32",
                    "framework": "arduino",
                    "wifi_password": "[REDACTED_PASSWORD]",
                    "ota_password": "[REDACTED_PASSWORD]",
                    "api_encryption": "configured",
                    "bluetooth_proxy": True,
                    "components": ["sensor", "binary_sensor"],
                    "substitutions_keys": ["dev_name"],
                }
            ]
        },
        "packages": {
            "packages": [{"package_file": "packages/lights.yaml", "domains": ["light", "switch"]}]
        },
        "automations_scripts_scenes": {"automation_count": 5, "script_count": 2, "scene_count": 1},
        "dashboards": {"dashboard_count": 3},
        "mqtt": {
            "detected": True,
            "discovery_enabled": True,
            "entity_count": 10,
            "tls_enabled": "disabled",
            "username_configured": "configured",
            "password_configured": "configured",
        },
        "frigate": {
            "detected": True,
            "camera_count": 2,
            "cameras": ["front", "back"],
            "detector_types": ["cpu"],
            "mqtt_enabled": True,
            "go2rtc_enabled": True,
        },
        "zigbee2mqtt": {
            "detected": True,
            "frontend_status": "enabled",
            "mqtt_status": "connected",
            "permit_join": False,
        },
        "custom_components": {
            "components": [
                {
                    "domain": "hacs",
                    "name": "HACS",
                    "version": "1.33.0",
                    "config_flow": True,
                    "documentation": "https://hacs.xyz",
                }
            ]
        },
        "warnings": ["Warning 1"],
    }

    export_ai_configuration_summary(output_dir=tmp_path, analysis_data=analysis_data)

    ai_config_dir = tmp_path / "ai" / "configuration"
    assert (ai_config_dir / "esphome.md").exists()
    assert (ai_config_dir / "packages.md").exists()
    assert (ai_config_dir / "frigate.md").exists()
    assert (ai_config_dir / "zigbee2mqtt.md").exists()
    assert (ai_config_dir / "custom-components.md").exists()
