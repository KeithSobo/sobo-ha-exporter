"""Unit tests for AI Reference Layer exporter and config directory resolution."""

import json
from pathlib import Path

from app.config import ExportConfig, get_config_dir
from app.exporters.ai_exporter import export_ai_reference_layer
from app.models.area import AreaModel
from app.models.device import DeviceModel
from app.models.entity import EntityModel
from app.models.label import LabelModel
from app.models.relationship import RelationshipModel


def test_get_config_dir_default_and_override(monkeypatch):
    """Test get_config_dir defaults to /homeassistant and respects CONFIG_DIR."""
    monkeypatch.delenv("CONFIG_DIR", raising=False)
    assert get_config_dir() == Path("/homeassistant")

    monkeypatch.setenv("CONFIG_DIR", "/custom/path")
    assert get_config_dir() == Path("/custom/path")


def test_export_ai_reference_layer(tmp_path):
    """Test generation of all 14 files in ai/ directory."""
    config_dir = tmp_path / "config_source"
    config_dir.mkdir(parents=True, exist_ok=True)

    # Write sample automations.yaml and scripts.yaml
    automations_yaml = (
        "- id: '123'\n"
        "  alias: 'Turn on Living Room Light'\n"
        "  trigger:\n"
        "    - platform: state\n"
        "      entity_id: input_boolean.guest_mode\n"
        "  action:\n"
        "    - service: light.turn_on\n"
        "      target:\n"
        "        entity_id: light.living_room_light\n"
    )
    (config_dir / "automations.yaml").write_text(automations_yaml, encoding="utf-8")

    scripts_yaml = (
        "goodnight_script:\n"
        "  alias: 'Goodnight Script'\n"
        "  sequence:\n"
        "    - service: switch.turn_off\n"
        "      target:\n"
        "        entity_id: switch.bedroom_switch\n"
    )
    (config_dir / "scripts.yaml").write_text(scripts_yaml, encoding="utf-8")

    entities = [
        EntityModel(
            entity_id="light.living_room_light",
            name="Living Room Light",
            domain="light",
            platform="hue",
            device_id="dev1",
            entity_area_id="living_room",
            effective_area_name="Living Room",
            area_source="device",
        ),
        EntityModel(
            entity_id="switch.bedroom_switch",
            name="Bedroom Switch",
            domain="switch",
            platform="zwave",
            device_id="dev2",
            entity_area_id="bedroom",
            effective_area_name="Bedroom",
            area_source="entity",
        ),
        EntityModel(
            entity_id="input_boolean.guest_mode",
            name="Guest Mode",
            domain="input_boolean",
            platform="input_boolean",
            labels=["house_mode"],
        ),
        EntityModel(
            entity_id="sensor.unassigned_sensor",
            name="Unassigned Sensor",
            domain="sensor",
            platform="demo",
        ),
    ]

    devices = [
        DeviceModel(
            device_id="dev1",
            name="Hue Hub Device",
            manufacturer="Philips",
            model="LWB014",
            area_id="living_room",
            area_name="Living Room",
            integration="hue",
            integration_domains=["hue"],
            entities=["light.living_room_light"],
        ),
        DeviceModel(
            device_id="dev2",
            name="Z-Wave Plug",
            manufacturer="Zooz",
            model="ZEN04",
            area_id="bedroom",
            area_name="Bedroom",
            integration="zwave",
            integration_domains=["zwave"],
            entities=["switch.bedroom_switch"],
        ),
        DeviceModel(
            device_id="dev_empty",
            name="Empty Device",
            entities=[],
        ),
    ]

    areas = [
        AreaModel(area_id="living_room", name="Living Room"),
        AreaModel(area_id="bedroom", name="Bedroom"),
    ]

    labels = [
        LabelModel(label_id="house_mode", name="House Mode"),
    ]

    integrations = [
        {"domain": "hue", "name": "Philips Hue", "device_count": 1, "entity_count": 1},
        {"domain": "zwave", "name": "Z-Wave JS", "device_count": 1, "entity_count": 1},
    ]

    relationships = RelationshipModel()
    export_cfg = ExportConfig()
    export_info = {"timestamp": "2026-08-14T12:00:00Z", "exporter_version": "0.1.7"}

    out_dir = tmp_path / "staging"
    export_ai_reference_layer(
        output_dir=out_dir,
        config_dir=config_dir,
        entities=entities,
        devices=devices,
        areas=areas,
        labels=labels,
        integrations=integrations,
        relationships=relationships,
        export_config=export_cfg,
        export_info=export_info,
        warnings=[],
    )

    ai_dir = out_dir / "ai"
    assert ai_dir.exists()

    expected_files = [
        "README.md",
        "overview.md",
        "areas.md",
        "devices-by-area.md",
        "entities-by-domain.md",
        "helpers.md",
        "automations.md",
        "scripts.md",
        "integrations.md",
        "labels.md",
        "dashboards/overview.md",
        "orphaned-and-unassigned.md",
        "impact-index.json",
        "search-index.json",
    ]

    for fname in expected_files:
        fpath = ai_dir / fname
        assert fpath.exists(), f"Missing expected AI file: {fname}"
        assert fpath.stat().st_size > 0, f"File {fname} is empty"

    # Verify impact-index.json structure
    impact_data = json.loads((ai_dir / "impact-index.json").read_text(encoding="utf-8"))
    assert "entities" in impact_data
    assert "devices" in impact_data
    assert "areas" in impact_data
    assert "input_boolean.guest_mode" in impact_data["entities"]

    # Verify search-index.json structure
    search_data = json.loads((ai_dir / "search-index.json").read_text(encoding="utf-8"))
    assert "records" in search_data
    assert len(search_data["records"]) > 0
