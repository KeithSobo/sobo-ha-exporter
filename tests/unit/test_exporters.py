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
