"""Deterministic JSON exporter."""

import json
from pathlib import Path
from typing import Any

from app.models.area import AreaModel
from app.models.dashboard import DashboardModel
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
    dashboards: list[DashboardModel] | None = None,
) -> None:
    """Export inventory JSON files into inventory/ subdirectory."""
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

    # 6. dashboards.json
    if dashboards is not None:
        export_dashboards_json(output_dir, dashboards)

    # 7. relationships.json
    write_stable_json(inv_dir / "relationships.json", relationships.to_dict())


def export_dashboards_json(
    output_dir: Path,
    dashboards: list[DashboardModel],
) -> None:
    """Export dashboards inventory file into inventory/dashboards.json."""
    inv_dir = output_dir / "inventory"
    dash_data = [d.to_dict() for d in sorted(dashboards, key=lambda x: (x.title.lower(), x.id))]
    write_stable_json(inv_dir / "dashboards.json", dash_data)


def export_panels_json(
    output_dir: Path,
    panels: list[Any],
) -> None:
    """Export panels inventory file into inventory/panels.json."""
    inv_dir = output_dir / "inventory"
    panel_data = [
        p.to_dict() if hasattr(p, "to_dict") else p
        for p in sorted(panels, key=lambda x: (x.title.lower(), x.url_path))
    ]
    write_stable_json(inv_dir / "panels.json", panel_data)


def export_references_json(
    output_dir: Path,
    relationships: RelationshipModel,
    entity_usage_data: dict[str, Any] | None = None,
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
        entity_usage_data if entity_usage_data is not None else relationships.entity_to_automations,
    )
    write_stable_json(
        ref_dir / "dashboard-entity-map.json",
        relationships.dashboard_to_entities,
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


def build_entity_usage_map(
    automation_models: list[Any] | None = None,
    scripts_detailed: list[dict[str, Any]] | None = None,
    dashboards: list[Any] | None = None,
    entities: list[EntityModel] | None = None,
) -> dict[str, Any]:
    """Build reverse usage mapping for entities across automations, scripts, and dashboards."""
    usage_data: dict[str, dict[str, list[Any]]] = {}

    if entities:
        for e in entities:
            usage_data[e.entity_id] = {"automations": [], "dashboards": [], "scripts": []}

    if automation_models:
        for m in automation_models:
            m_id = getattr(m, "id", "")
            m_alias = getattr(m, "alias", "")
            m_ents = getattr(m, "entities", [])
            for eid in m_ents:
                if eid not in usage_data:
                    usage_data[eid] = {"automations": [], "dashboards": [], "scripts": []}
                ctx: list[str] = []
                if hasattr(m, "entity_usage_map") and eid in m.entity_usage_map:
                    ctx = sorted(m.entity_usage_map[eid])
                else:
                    ctx = ["automation_reference"]
                usage_data[eid]["automations"].append(
                    {
                        "id": m_id,
                        "alias": m_alias,
                        "usage": ctx,
                    }
                )

    if scripts_detailed:
        for sc in scripts_detailed:
            sc_id = sc.get("id") or sc.get("alias")
            for ref in sc.get("references", []):
                if ref not in usage_data:
                    usage_data[ref] = {"automations": [], "dashboards": [], "scripts": []}
                usage_data[ref]["scripts"].append(
                    {
                        "id": sc_id,
                        "alias": sc.get("alias"),
                        "usage": ["action"],
                    }
                )

    if dashboards:

        def _walk_card(c: Any, d: Any, v_title: str) -> None:
            for ref in getattr(c, "entities", []):
                if ref not in usage_data:
                    usage_data[ref] = {"automations": [], "dashboards": [], "scripts": []}
                d_entries = usage_data[ref]["dashboards"]
                existing = next((item for item in d_entries if item["id"] == d.id), None)
                if existing:
                    if v_title not in existing["views"]:
                        existing["views"].append(v_title)
                else:
                    d_entries.append(
                        {
                            "id": d.id,
                            "title": d.title,
                            "views": [v_title],
                            "card_type": getattr(c, "type", "unknown"),
                        }
                    )
            for nc in getattr(c, "nested_cards", []):
                _walk_card(nc, d, v_title)

        for d in dashboards:
            for v in d.views:
                v_title = v.title
                for card in v.cards:
                    _walk_card(card, d, v_title)

    sorted_result: dict[str, Any] = {}
    for eid, data in sorted(usage_data.items()):
        sorted_result[eid] = {
            "automations": sorted(data["automations"], key=lambda x: str(x["id"])),
            "dashboards": sorted(data["dashboards"], key=lambda x: str(x["id"])),
            "scripts": sorted(data["scripts"], key=lambda x: str(x["id"])),
        }
    return sorted_result
