"""Deterministic JSON exporter."""

import json
from pathlib import Path
from typing import Any

from app.models.area import AreaModel
from app.models.device import DeviceModel
from app.models.entity import EntityModel
from app.models.label import LabelModel
from app.models.relationship import RelationshipModel


def write_stable_json(target_path: Path, data: Any) -> None:
    """Write data as stable, formatted, deterministic JSON.

    Args:
        target_path: File path to save JSON file.
        data: Data structure to serialize.
    """
    target_path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    target_path.write_text(content, encoding="utf-8")


def export_inventory_json(
    output_dir: Path,
    entities: list[EntityModel],
    devices: list[DeviceModel],
    areas: list[AreaModel],
    labels: list[LabelModel],
    integrations: list[dict[str, Any]],
    relationships: RelationshipModel,
) -> None:
    """Export inventory JSON files into inventory/ subdirectory.

    Args:
        output_dir: Staging base directory.
        entities: List of EntityModel.
        devices: List of DeviceModel.
        areas: List of AreaModel.
        labels: List of LabelModel.
        integrations: List of integration dictionaries.
        relationships: RelationshipModel instance.
    """
    inv_dir = output_dir / "inventory"

    # 1. entities.json
    entities_data = [e.to_dict() for e in sorted(entities, key=lambda x: x.entity_id)]
    write_stable_json(inv_dir / "entities.json", entities_data)

    # 2. devices.json
    devices_data = [
        d.to_dict() for d in sorted(devices, key=lambda x: (x.name.lower(), x.device_id))
    ]
    write_stable_json(inv_dir / "devices.json", devices_data)

    # 3. areas.json
    areas_data = [a.to_dict() for a in sorted(areas, key=lambda x: (x.name.lower(), x.area_id))]
    write_stable_json(inv_dir / "areas.json", areas_data)

    # 4. labels.json
    labels_data = [
        lbl.to_dict() for lbl in sorted(labels, key=lambda x: (x.name.lower(), x.label_id))
    ]
    write_stable_json(inv_dir / "labels.json", labels_data)

    # 5. integrations.json
    integrations_sorted = sorted(integrations, key=lambda x: x.get("domain", ""))
    write_stable_json(inv_dir / "integrations.json", integrations_sorted)

    # 6. relationships.json
    write_stable_json(inv_dir / "relationships.json", relationships.to_dict())


def export_references_json(
    output_dir: Path,
    relationships: RelationshipModel,
) -> None:
    """Export inverted reference maps into references/ subdirectory."""
    ref_dir = output_dir / "references"

    write_stable_json(
        ref_dir / "automation-entity-map.json",
        relationships.automation_to_entities,
    )
    write_stable_json(
        ref_dir / "device-entity-map.json",
        relationships.device_to_entities,
    )
    write_stable_json(
        ref_dir / "area-device-map.json",
        relationships.area_to_devices,
    )
    write_stable_json(
        ref_dir / "label-target-map.json",
        {
            "entities": relationships.label_to_entities,
            "devices": relationships.label_to_devices,
        },
    )
    write_stable_json(
        ref_dir / "entity-usage.json",
        relationships.entity_to_automations,
    )


def export_metadata_json(
    output_dir: Path,
    export_info: dict[str, Any],
    exporter_version: dict[str, Any],
    sanitization_report: dict[str, Any],
    warnings: list[str],
) -> None:
    """Export metadata information into metadata/ subdirectory."""
    meta_dir = output_dir / "metadata"

    write_stable_json(meta_dir / "export-info.json", export_info)
    write_stable_json(meta_dir / "exporter-version.json", exporter_version)
    write_stable_json(meta_dir / "sanitization-report.json", sanitization_report)
    write_stable_json(meta_dir / "warnings.json", sorted(warnings))
