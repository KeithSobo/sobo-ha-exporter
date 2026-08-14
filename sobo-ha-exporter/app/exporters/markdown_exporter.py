"""Markdown summary exporter module."""

from pathlib import Path
from typing import Any

from app.models.area import AreaModel
from app.models.device import DeviceModel
from app.models.entity import EntityModel


def export_summaries_markdown(
    output_dir: Path,
    entities: list[EntityModel],
    devices: list[DeviceModel],
    areas: list[AreaModel],
    integrations: list[dict[str, Any]],
) -> None:
    """Generate markdown summaries into summaries/ subdirectory.

    Args:
        output_dir: Staging base directory.
        entities: List of EntityModel.
        devices: List of DeviceModel.
        areas: List of AreaModel.
        integrations: List of integration summary dictionaries.
    """
    sum_dir = output_dir / "summaries"
    sum_dir.mkdir(parents=True, exist_ok=True)

    # 1. entity-summary.md
    ent_lines = [
        "# Entity Summary",
        "",
        f"Total Entities: {len(entities)}",
        "",
        "| Entity ID | Name | Domain | Platform | Area | Device |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for e in sorted(entities, key=lambda x: x.entity_id):
        area_str = e.area_name or "-"
        dev_str = e.device_name or "-"
        ent_lines.append(
            f"| `{e.entity_id}` | {e.name} | {e.domain} | {e.platform} | {area_str} | {dev_str} |"
        )
    (sum_dir / "entity-summary.md").write_text("\n".join(ent_lines) + "\n", encoding="utf-8")

    # 2. device-summary.md
    dev_lines = [
        "# Device Summary",
        "",
        f"Total Devices: {len(devices)}",
        "",
        "| Device Name | Integration | Manufacturer | Model | Area | Associated Entities |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for d in sorted(devices, key=lambda x: (x.name.lower(), x.device_id)):
        ent_count = len(d.entities)
        integ_str = d.integration or "-"
        mfr_str = d.manufacturer or "-"
        model_str = d.model or "-"
        area_str = d.area_name or "-"
        dev_lines.append(
            f"| {d.name} | {integ_str} | {mfr_str} | {model_str} | {area_str} | {ent_count} |"
        )
    (sum_dir / "device-summary.md").write_text("\n".join(dev_lines) + "\n", encoding="utf-8")

    # 3. area-summary.md
    area_lines = [
        "# Area Summary",
        "",
        f"Total Areas: {len(areas)}",
        "",
        "| Area ID | Name | Aliases | Labels |",
        "| --- | --- | --- | --- |",
    ]
    for a in sorted(areas, key=lambda x: (x.name.lower(), x.area_id)):
        aliases_str = ", ".join(a.aliases) if a.aliases else "-"
        labels_str = ", ".join(a.labels) if a.labels else "-"
        area_lines.append(f"| `{a.area_id}` | {a.name} | {aliases_str} | {labels_str} |")
    (sum_dir / "area-summary.md").write_text("\n".join(area_lines) + "\n", encoding="utf-8")

    # 4. integration-summary.md
    integ_lines = [
        "# Integration Summary",
        "",
        f"Total Integrations: {len(integrations)}",
        "",
        "| Domain | Name | Devices | Entities | Built-in |",
        "| --- | --- | --- | --- | --- |",
    ]
    for i in sorted(integrations, key=lambda x: x.get("domain", "")):
        domain = i.get("domain")
        name = i.get("name")
        dev_cnt = i.get("device_count", 0)
        ent_cnt = i.get("entity_count", 0)
        builtin = i.get("is_built_in")
        integ_lines.append(f"| `{domain}` | {name} | {dev_cnt} | {ent_cnt} | {builtin} |")
    (sum_dir / "integration-summary.md").write_text("\n".join(integ_lines) + "\n", encoding="utf-8")
