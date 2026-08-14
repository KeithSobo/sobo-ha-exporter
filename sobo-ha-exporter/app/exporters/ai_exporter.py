"""AI Reference Layer Exporter.

Generates compact, navigable, deterministic files in the `ai/` directory
to assist AI coding and context tools (ChatGPT, Antigravity, etc.) in
understanding the Home Assistant installation without scanning raw records.
"""

import json
import logging
import re
from pathlib import Path
from typing import Any

import yaml

from app.config import ExportConfig
from app.models.area import AreaModel
from app.models.dashboard import DashboardModel
from app.models.device import DeviceModel
from app.models.entity import EntityModel
from app.models.label import LabelModel
from app.models.relationship import RelationshipModel

logger = logging.getLogger(__name__)

HELPER_DOMAINS = {
    "input_boolean",
    "input_number",
    "input_text",
    "input_select",
    "input_datetime",
    "input_button",
    "counter",
    "timer",
    "schedule",
    "group",
}


def write_stable_json(target_path: Path, data: Any) -> None:
    """Write data as stable, formatted, deterministic JSON."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    target_path.write_text(content, encoding="utf-8")


def write_text(target_path: Path, text: str) -> None:
    """Write text file ensuring parent directory exists and trailing newline."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if not text.endswith("\n"):
        text += "\n"
    target_path.write_text(text, encoding="utf-8")


def parse_scripts_file(config_dir: Path) -> tuple[dict[str, Any], list[str]]:
    """Parse scripts.yaml if present in config directory."""
    path = config_dir / "scripts.yaml"
    if not path.exists():
        return {}, ["scripts.yaml file not found"]

    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
        data = yaml.safe_load(content)
        if isinstance(data, dict):
            return data, []
        return {}, ["scripts.yaml content is not a dictionary"]
    except Exception as e:
        return {}, [f"Error reading scripts.yaml: {e}"]


def parse_automations_detailed(config_dir: Path) -> list[dict[str, Any]]:
    """Parse automations.yaml into structured detailed automation records."""
    path = config_dir / "automations.yaml"
    if not path.exists():
        return []

    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
        data = yaml.safe_load(content)
        if not isinstance(data, list):
            if isinstance(data, dict):
                data = [data]
            else:
                return []
    except Exception:
        return []

    results = []
    for idx, item in enumerate(data):
        if not isinstance(item, dict):
            continue

        alias = str(item.get("alias") or item.get("id") or f"automation_{idx + 1}")
        auto_id = str(item.get("id") or alias)

        triggers = _extract_section_entities(item.get("trigger"))
        conditions = _extract_section_entities(item.get("condition"))
        actions = _extract_section_entities(item.get("action"))
        services = _extract_services(item.get("action"))

        all_refs = sorted(triggers | conditions | actions)
        helpers = sorted({e for e in all_refs if e.split(".")[0] in HELPER_DOMAINS})

        has_dynamic = _has_dynamic_template(item)

        results.append(
            {
                "id": auto_id,
                "alias": alias,
                "triggers": sorted(triggers),
                "conditions": sorted(conditions),
                "actions": sorted(actions),
                "services": sorted(services),
                "all_references": all_refs,
                "helpers": helpers,
                "has_dynamic_template": has_dynamic,
            }
        )

    return sorted(results, key=lambda x: (x["alias"].lower(), x["id"]))


def parse_scripts_detailed(config_dir: Path) -> list[dict[str, Any]]:
    """Parse scripts.yaml into structured detailed script records."""
    data, _ = parse_scripts_file(config_dir)
    if not data:
        return []

    results = []
    for script_id, item in sorted(data.items(), key=lambda x: str(x[0]).lower()):
        if not isinstance(item, dict):
            continue

        alias = str(item.get("alias") or script_id)
        sequence = item.get("sequence") or item.get("action")

        referenced_entities = _extract_section_entities(sequence)
        services = _extract_services(sequence)
        called_scripts = sorted({s for s in services if s.startswith("script.")})
        has_dynamic = _has_dynamic_template(item)

        results.append(
            {
                "id": str(script_id),
                "alias": alias,
                "references": sorted(referenced_entities),
                "services": sorted(services),
                "called_scripts": called_scripts,
                "has_dynamic_template": has_dynamic,
            }
        )

    return results


def _extract_section_entities(obj: Any) -> set[str]:
    """Extract entity IDs from an automation/script section."""
    entities: set[str] = set()
    regex = re.compile(
        r"\b(?:light|switch|sensor|binary_sensor|climate|cover|fan|media_player|camera|lock|"
        r"vacuum|alarm_control_panel|automation|script|scene|person|zone|input_boolean|"
        r"input_number|input_select|input_text|input_datetime|counter|timer)\.[a-z0-9_]+\b"
    )

    def _walk(o: Any) -> None:
        if isinstance(o, dict):
            for k, v in o.items():
                if k in ["entity_id", "entities"]:
                    if isinstance(v, str) and "." in v:
                        entities.add(v)
                    elif isinstance(v, list):
                        for item in v:
                            if isinstance(item, str) and "." in item:
                                entities.add(item)
                else:
                    _walk(v)
        elif isinstance(o, list):
            for item in o:
                _walk(item)
        elif isinstance(o, str):
            for match in regex.findall(o):
                if "." in match:
                    entities.add(match)

    _walk(obj)
    return entities


def _extract_services(obj: Any) -> set[str]:
    """Extract service names called within an action sequence."""
    services: set[str] = set()

    def _walk(o: Any) -> None:
        if isinstance(o, dict):
            srv = o.get("service") or o.get("action")
            if isinstance(srv, str) and "." in srv:
                services.add(srv)
            for v in o.values():
                _walk(v)
        elif isinstance(o, list):
            for item in o:
                _walk(item)

    _walk(obj)
    return services


def _has_dynamic_template(obj: Any) -> bool:
    """Check if object contains dynamic Jinja template expressions."""
    text = json.dumps(obj, ensure_ascii=False)
    return "{{" in text or "{%" in text


def export_ai_reference_layer(
    output_dir: Path,
    config_dir: Path,
    entities: list[EntityModel],
    devices: list[DeviceModel],
    areas: list[AreaModel],
    labels: list[LabelModel],
    integrations: list[dict[str, Any]],
    relationships: RelationshipModel,
    export_config: ExportConfig,
    export_info: dict[str, Any],
    warnings: list[str],
    dashboards: list[DashboardModel] | None = None,
    dash_discovery_error: str | None = None,
    automation_models: list[Any] | None = None,
    panels: list[Any] | None = None,
) -> None:
    """Export complete AI reference layer into `ai/` subdirectory."""
    ai_dir = output_dir / "ai"
    ai_dir.mkdir(parents=True, exist_ok=True)

    if automation_models is not None:
        auto_models = automation_models
    else:
        from app.collectors.automations import collect_automation_models

        auto_models, _ = (
            collect_automation_models(config_dir) if export_config.automations else ([], [])
        )

    detailed_autos = [
        {
            "id": a.id,
            "alias": a.alias,
            "all_references": a.entities,
            "services": a.called_services,
            "helpers": a.helpers,
            "has_dynamic_template": len(a.unresolved_templates) > 0,
        }
        for a in auto_models
    ]
    detailed_scripts = parse_scripts_detailed(config_dir)

    ent_map = {e.entity_id: e for e in entities}
    dev_map = {d.device_id: d for d in devices}

    auto_ref_map: dict[str, set[str]] = {}
    for auto in detailed_autos:
        alias = auto["alias"]
        for ref_ent in auto["all_references"]:
            auto_ref_map.setdefault(ref_ent, set()).add(alias)

    script_ref_map: dict[str, set[str]] = {}
    for sc in detailed_scripts:
        alias = sc["alias"]
        for ref_ent in sc["references"]:
            script_ref_map.setdefault(ref_ent, set()).add(alias)

    # 1. ai/README.md
    readme_content = (
        "# Home Assistant AI Reference Layer\n\n"
        "This directory contains compact, structured, deterministic reference files derived "
        "from your Home Assistant setup for consumption by AI models "
        "(ChatGPT, Antigravity, etc.).\n\n"
        "## Key Guidelines for AI Tools:\n"
        "- **Authoritative Raw Data**: Primary structured data remains under `inventory/` and "
        "`references/`.\n"
        "- **Navigational Layer**: Use `ai/overview.md`, `ai/impact-index.json`, and "
        "`ai/search-index.json` to quickly resolve context.\n"
        "- **Security & Privacy**: All secrets, passwords, tokens, coordinates, and MAC addresses "
        "are scrubbed.\n"
        "- **No Live History**: No historical state logs or recorder data are exported.\n"
    )
    write_text(ai_dir / "README.md", readme_content)

    # 2. ai/overview.md
    disabled_ents = sum(1 for e in entities if e.disabled_by)
    hidden_ents = sum(1 for e in entities if e.hidden_by)
    unassigned_ents = sum(1 for e in entities if not e.area_id)
    devs_no_ents = sum(1 for d in devices if not d.entities)
    helpers_count = sum(
        1 for e in entities if e.domain in HELPER_DOMAINS or e.platform == "template"
    )

    overview_content = (
        "# Home Assistant Installation Overview\n\n"
        f"- **Exporter Version**: {export_info.get('exporter_version', '0.1.7')}\n"
        f"- **Export Timestamp**: {export_info.get('timestamp', 'N/A')}\n\n"
        "## System Totals\n"
        f"- **Areas**: {len(areas)}\n"
        f"- **Devices**: {len(devices)}\n"
        f"- **Entities**: {len(entities)}\n"
        f"- **Integrations**: {len(integrations)}\n"
        f"- **Labels**: {len(labels)}\n"
        f"- **Automations**: {len(detailed_autos)}\n"
        f"- **Scripts**: {len(detailed_scripts)}\n"
        f"- **Helpers**: {helpers_count}\n"
        f"- **Disabled Entities**: {disabled_ents}\n"
        f"- **Hidden Entities**: {hidden_ents}\n"
        f"- **Unassigned Entities (No Area)**: {unassigned_ents}\n"
        f"- **Devices with No Entities**: {devs_no_ents}\n\n"
        "## Navigation\n"
        "- [Areas](areas.md)\n"
        "- [Devices by Area](devices-by-area.md)\n"
        "- [Entities by Domain](entities-by-domain.md)\n"
        "- [Helpers](helpers.md)\n"
        "- [Automations](automations.md)\n"
        "- [Scripts](scripts.md)\n"
        "- [Integrations](integrations.md)\n"
        "- [Labels](labels.md)\n"
        "- [Dashboards](dashboards/overview.md)\n"
        "- [Orphaned and Unassigned](orphaned-and-unassigned.md)\n"
    )
    write_text(ai_dir / "overview.md", overview_content)

    # 3. ai/areas.md
    area_lines = ["# Areas Summary\n"]
    for area in sorted(areas, key=lambda x: (x.name.lower(), x.area_id)):
        area_devs = [d for d in devices if d.area_id == area.area_id]
        area_ents = [e for e in entities if e.area_id == area.area_id]
        explicit_ents = [e for e in area_ents if e.area_source == "entity"]
        inherited_ents = [e for e in area_ents if e.area_source == "device"]

        area_auto_count = sum(
            1
            for auto in detailed_autos
            if any(
                ent_map.get(ref, EntityModel("")).area_id == area.area_id
                for ref in auto["all_references"]
            )
        )

        area_labels = sorted(
            {lbl for d in area_devs for lbl in d.labels}
            | {lbl for e in area_ents for lbl in e.labels}
        )
        area_integrations = sorted(
            {d.integration for d in area_devs if d.integration}
            | {e.platform for e in area_ents if e.platform}
        )

        area_lines.append(
            f"## {area.name} (`{area.area_id}`)\n"
            f"- **Devices**: {len(area_devs)}\n"
            f"- **Entities**: {len(area_ents)} (Explicit Area Override: {len(explicit_ents)}, "
            f"Inherited from Device: {len(inherited_ents)})\n"
            f"- **Automations Referencing Area**: {area_auto_count}\n"
            f"- **Labels**: {', '.join(area_labels) if area_labels else 'None'}\n"
            f"- **Integrations**: {', '.join(area_integrations) if area_integrations else 'None'}\n"
        )
    write_text(ai_dir / "areas.md", "\n".join(area_lines))

    # 4. ai/devices-by-area.md
    dev_area_lines = ["# Devices by Area\n"]
    for area in sorted(areas, key=lambda x: (x.name.lower(), x.area_id)):
        area_devs = sorted(
            [d for d in devices if d.area_id == area.area_id],
            key=lambda x: (x.name.lower(), x.device_id),
        )
        dev_area_lines.append(f"## {area.name} (`{area.area_id}`)\n")
        if not area_devs:
            dev_area_lines.append("_No devices in this area._\n")
        for dev in area_devs:
            d_ents = [ent_map[eid] for eid in dev.entities if eid in ent_map]
            dis_c = sum(1 for e in d_ents if e.disabled_by)
            hid_c = sum(1 for e in d_ents if e.hidden_by)
            dev_area_lines.append(
                f"### {dev.name} (`{dev.device_id}`)\n"
                f"- **Manufacturer / Model**: {dev.manufacturer or 'Unknown'} / "
                f"{dev.model or 'Unknown'}\n"
                f"- **Integration Domains**: "
                f"{', '.join(dev.integration_domains) if dev.integration_domains else 'None'}\n"
                f"- **Labels**: {', '.join(dev.labels) if dev.labels else 'None'}\n"
                f"- **Entity Count**: {len(dev.entities)} (Disabled: {dis_c}, Hidden: {hid_c})\n"
                f"- **Entities**: {', '.join(dev.entities) if dev.entities else 'None'}\n"
            )

    unassigned_devs = sorted(
        [d for d in devices if not d.area_id],
        key=lambda x: (x.name.lower(), x.device_id),
    )
    dev_area_lines.append("## Unassigned Devices\n")
    if not unassigned_devs:
        dev_area_lines.append("_No unassigned devices._\n")
    for dev in unassigned_devs:
        d_ents = [ent_map[eid] for eid in dev.entities if eid in ent_map]
        dis_c = sum(1 for e in d_ents if e.disabled_by)
        hid_c = sum(1 for e in d_ents if e.hidden_by)
        dev_area_lines.append(
            f"### {dev.name} (`{dev.device_id}`)\n"
            f"- **Manufacturer / Model**: {dev.manufacturer or 'Unknown'} / "
            f"{dev.model or 'Unknown'}\n"
            f"- **Integration Domains**: "
            f"{', '.join(dev.integration_domains) if dev.integration_domains else 'None'}\n"
            f"- **Labels**: {', '.join(dev.labels) if dev.labels else 'None'}\n"
            f"- **Entity Count**: {len(dev.entities)} (Disabled: {dis_c}, Hidden: {hid_c})\n"
            f"- **Entities**: {', '.join(dev.entities) if dev.entities else 'None'}\n"
        )
    write_text(ai_dir / "devices-by-area.md", "\n".join(dev_area_lines))

    # 5. ai/entities-by-domain.md
    domain_groups: dict[str, list[EntityModel]] = {}
    for ent in entities:
        domain_groups.setdefault(ent.domain, []).append(ent)

    ent_dom_lines = ["# Entities by Domain\n"]
    for dom in sorted(domain_groups.keys()):
        d_ents = domain_groups[dom]
        tot = len(d_ents)
        dis = sum(1 for e in d_ents if e.disabled_by)
        hid = sum(1 for e in d_ents if e.hidden_by)
        ena = tot - dis

        d_classes = sorted({e.device_class for e in d_ents if e.device_class})
        e_cats = sorted({e.entity_category for e in d_ents if e.entity_category})
        areas_rep = sorted({e.area_name for e in d_ents if e.area_name})
        platforms_rep = sorted({e.platform for e in d_ents if e.platform})

        ent_dom_lines.append(
            f"## Domain: `{dom}`\n"
            f"- **Total Entities**: {tot} (Enabled: {ena}, Disabled: {dis}, Hidden: {hid})\n"
            f"- **Device Classes**: {', '.join(d_classes) if d_classes else 'None'}\n"
            f"- **Categories**: {', '.join(e_cats) if e_cats else 'None'}\n"
            f"- **Areas Represented**: {', '.join(areas_rep) if areas_rep else 'None'}\n"
            f"- **Platforms**: {', '.join(platforms_rep) if platforms_rep else 'None'}\n"
        )
    write_text(ai_dir / "entities-by-domain.md", "\n".join(ent_dom_lines))

    # 6. ai/helpers.md
    helper_ents = sorted(
        [e for e in entities if e.domain in HELPER_DOMAINS or e.platform == "template"],
        key=lambda x: x.entity_id,
    )
    helper_lines = ["# Home Assistant Helpers\n"]
    if not helper_ents:
        helper_lines.append("_No helper entities found._\n")
    for h in helper_ents:
        h_autos = sorted(auto_ref_map.get(h.entity_id, set()))
        h_scripts = sorted(script_ref_map.get(h.entity_id, set()))
        is_unused = not h_autos and not h_scripts
        helper_lines.append(
            f"### `{h.entity_id}`\n"
            f"- **Name**: {h.name}\n"
            f"- **Domain**: `{h.domain}` (Platform: `{h.platform or 'unknown'}`)\n"
            f"- **Area**: {h.area_name or 'Unassigned'}\n"
            f"- **Labels**: {', '.join(h.labels) if h.labels else 'None'}\n"
            f"- **Referencing Automations**: {', '.join(h_autos) if h_autos else 'None'}\n"
            f"- **Referencing Scripts**: {', '.join(h_scripts) if h_scripts else 'None'}\n"
            f"- **Appears Unused**: {'Yes' if is_unused else 'No'}\n"
        )
    write_text(ai_dir / "helpers.md", "\n".join(helper_lines))
    auto_lines = ["# Automations Summary\n"]
    if not export_config.automations:
        auto_lines.append("_Automation export is disabled in config.yaml._\n")
    elif not auto_models:
        auto_lines.append("_No automations found in automations configuration._\n")
    else:
        auto_lines.append(f"Total Automations Discovered: {len(auto_models)}\n")
        for auto in auto_models:
            auto_devs = sorted(
                {
                    ent_map[ref].device_id
                    for ref in auto.entities
                    if ref in ent_map and ent_map[ref].device_id
                }
            )
            auto_areas = sorted(
                {
                    ent_map[ref].area_name
                    for ref in auto.entities
                    if ref in ent_map and ent_map[ref].area_name
                }
            )

            tr_str = ", ".join(auto.triggers) if auto.triggers else "None"
            co_str = ", ".join(auto.conditions) if auto.conditions else "None"
            ac_str = ", ".join(auto.actions) if auto.actions else "None"
            srv_str = ", ".join(auto.called_services) if auto.called_services else "None"
            ent_str = ", ".join(auto.entities) if auto.entities else "None"
            hlp_str = ", ".join(auto.helpers) if auto.helpers else "None"
            dev_str = ", ".join(auto_devs) if auto_devs else "None"
            area_str = ", ".join(auto_areas) if auto_areas else "None"
            tmpl_str = ", ".join(auto.unresolved_templates) if auto.unresolved_templates else "None"
            warn_str = ", ".join(auto.warnings) if auto.warnings else "None"

            auto_lines.append(
                f"## {auto.alias} (`{auto.id}`)\n"
                f"- **Source File**: `{auto.source_file}`\n"
                f"- **Triggers**: {tr_str}\n"
                f"- **Conditions**: {co_str}\n"
                f"- **Actions**: {ac_str}\n"
                f"- **Services Called**: {srv_str}\n"
                f"- **Entities Referenced**: {ent_str}\n"
                f"- **Helpers Referenced**: {hlp_str}\n"
                f"- **Areas Touched**: {area_str}\n"
                f"- **Devices Touched**: {dev_str}\n"
                f"- **Unresolved Templates**: {tmpl_str}\n"
                f"- **Warnings**: {warn_str}\n"
            )

        auto_lines.append("## Rollup Summaries\n")
        auto_lines.append(f"- **Total Automation Count**: {len(auto_models)}")
        no_ref = [a.alias for a in auto_models if not a.entities]
        auto_lines.append(
            f"- **Automations with No Entity References ({len(no_ref)})**: "
            f"{', '.join(no_ref) if no_ref else 'None'}"
        )
        unres_t = [a.alias for a in auto_models if a.unresolved_templates]
        auto_lines.append(
            f"- **Automations with Unresolved Templates ({len(unres_t)})**: "
            f"{', '.join(unres_t) if unres_t else 'None'}"
        )

        auto_lines.append("\n### Most Referenced Entities in Automations")
        ref_counts: dict[str, int] = {}
        for a in auto_models:
            for e in a.entities:
                ref_counts[e] = ref_counts.get(e, 0) + 1
        for eid, cnt in sorted(ref_counts.items(), key=lambda x: (-x[1], x[0]))[:10]:
            auto_lines.append(f"- `{eid}`: referenced by {cnt} automation(s)")

        auto_lines.append("\n### Most Used Services in Automations")
        srv_counts: dict[str, int] = {}
        for a in auto_models:
            for s in a.called_services:
                srv_counts[s] = srv_counts.get(s, 0) + 1
        for srv, cnt in sorted(srv_counts.items(), key=lambda x: (-x[1], x[0]))[:10]:
            auto_lines.append(f"- `{srv}`: called by {cnt} automation(s)")

        auto_lines.append("\n### Helper Usage Summary")
        all_helpers = sorted({h for a in auto_models for h in a.helpers})
        if all_helpers:
            for h in all_helpers:
                auto_lines.append(f"- `{h}`")
        else:
            auto_lines.append("- _None_")

        auto_lines.append("\n### Missing Entity References")
        all_known_ents = {e.entity_id for e in entities}
        missing_refs = sorted(
            {e for a in auto_models for e in a.entities if e not in all_known_ents}
        )
        if missing_refs:
            for m_ref in missing_refs:
                auto_lines.append(
                    f"- ⚠️ `{m_ref}` (referenced in automation, not registered in Home Assistant)"
                )
        else:
            auto_lines.append("- _None_")

    write_text(ai_dir / "automations.md", "\n".join(auto_lines))

    # 8. ai/scripts.md
    script_lines = ["# Scripts Summary\n"]
    if not detailed_scripts:
        script_lines.append("_No scripts.yaml file found or no scripts configured._\n")
    else:
        for sc in detailed_scripts:
            sc_devs = sorted(
                {
                    ent_map[ref].device_id
                    for ref in sc["references"]
                    if ref in ent_map and ent_map[ref].device_id
                }
            )
            sc_areas = sorted(
                {
                    ent_map[ref].area_name
                    for ref in sc["references"]
                    if ref in ent_map and ent_map[ref].area_name
                }
            )
            script_lines.append(
                f"## {sc['alias']} (`{sc['id']}`)\n"
                f"- **Referenced Entities**: "
                f"{', '.join(sc['references']) if sc['references'] else 'None'}\n"
                f"- **Services Called**: "
                f"{', '.join(sc['services']) if sc['services'] else 'None'}\n"
                f"- **Scripts Called**: "
                f"{', '.join(sc['called_scripts']) if sc['called_scripts'] else 'None'}\n"
                f"- **Areas Touched**: {', '.join(sc_areas) if sc_areas else 'None'}\n"
                f"- **Devices Touched**: {', '.join(sc_devs) if sc_devs else 'None'}\n"
                f"- **Dynamic Templates Present**: "
                f"{'Yes' if sc['has_dynamic_template'] else 'No'}\n"
            )
    write_text(ai_dir / "scripts.md", "\n".join(script_lines))

    # 9. ai/integrations.md
    integ_lines = ["# Integrations Summary\n"]
    for integ in sorted(integrations, key=lambda x: x.get("domain", "")):
        dom = integ.get("domain", "")
        i_ents = [e for e in entities if e.platform == dom]
        i_devs = [d for d in devices if dom in d.integration_domains]

        areas_rep = sorted(
            {e.area_name for e in i_ents if e.area_name}
            | {d.area_name for d in i_devs if d.area_name}
        )
        doms_rep = sorted({e.domain for e in i_ents})
        dis_ents = sum(1 for e in i_ents if e.disabled_by)
        diag_ents = sum(1 for e in i_ents if e.entity_category == "diagnostic")
        cfg_ents = sum(1 for e in i_ents if e.entity_category == "config")

        integ_lines.append(
            f"## Integration: `{dom}`\n"
            f"- **Entity Count**: {len(i_ents)} (Disabled: {dis_ents}, "
            f"Diagnostic: {diag_ents}, Config: {cfg_ents})\n"
            f"- **Device Count**: {len(i_devs)}\n"
            f"- **Areas Represented**: {', '.join(areas_rep) if areas_rep else 'None'}\n"
            f"- **Entity Domains**: {', '.join(doms_rep) if doms_rep else 'None'}\n"
        )
    write_text(ai_dir / "integrations.md", "\n".join(integ_lines))

    # 10. ai/labels.md
    label_lines = ["# Labels Summary\n"]
    for lbl in sorted(labels, key=lambda x: (x.name.lower(), x.label_id)):
        l_ents = [e for e in entities if lbl.label_id in e.labels or lbl.name in e.labels]
        l_devs = [d for d in devices if lbl.label_id in d.labels or lbl.name in d.labels]

        l_areas = sorted(
            {e.area_name for e in l_ents if e.area_name}
            | {d.area_name for d in l_devs if d.area_name}
        )
        l_doms = sorted({e.domain for e in l_ents})

        l_autos = sorted(
            {
                auto.alias
                for auto in auto_models
                if any(ref in [e.entity_id for e in l_ents] for ref in auto.entities)
            }
        )
        l_scripts = sorted(
            {
                sc["alias"]
                for sc in detailed_scripts
                if any(ref in [e.entity_id for e in l_ents] for ref in sc["references"])
            }
        )

        label_lines.append(
            f"## Label: {lbl.name} (`{lbl.label_id}`)\n"
            f"- **Entity Count**: {len(l_ents)}\n"
            f"- **Device Count**: {len(l_devs)}\n"
            f"- **Areas Represented**: {', '.join(l_areas) if l_areas else 'None'}\n"
            f"- **Entity Domains**: {', '.join(l_doms) if l_doms else 'None'}\n"
            f"- **Referencing Automations**: {', '.join(l_autos) if l_autos else 'None'}\n"
            f"- **Referencing Scripts**: {', '.join(l_scripts) if l_scripts else 'None'}\n"
        )
    write_text(ai_dir / "labels.md", "\n".join(label_lines))

    # 11. ai/dashboards/ directory
    dash_dir = ai_dir / "dashboards"
    dash_dir.mkdir(parents=True, exist_ok=True)

    dash_list = dashboards or []
    panel_list = panels or []
    overview_lines = [
        "# Home Assistant Dashboards & Panels Overview\n",
    ]

    if dash_discovery_error:
        overview_lines.append(
            f"> [!WARNING]\n> **Dashboard Discovery Issue**: {dash_discovery_error}\n"
        )

    if not export_config.dashboards:
        overview_lines.append(
            "_Dashboard analysis was disabled in configuration (`export.dashboards: false`)._\n"
        )
    else:
        # Section 1: Analyzed Lovelace Dashboards
        overview_lines.append("## 1. Analyzed Lovelace Dashboards\n")
        if dash_list:
            overview_lines.append(
                "| Dashboard Title | Mode | Default | Views |"
                " Cards | Custom Cards | Pillar Cards |\n"
                "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n"
            )
            for dash in sorted(dash_list, key=lambda x: (x.title.lower(), x.id)):
                st = dash.to_dict()["stats"]
                def_str = "Yes" if dash.default_dashboard else "No"
                slug_name = (dash.title or dash.id).strip().replace(" ", "_").replace("/", "_")
                overview_lines.append(
                    f"| [{dash.title}]({slug_name}.md) | `{dash.mode}` | {def_str} | "
                    f"{st['view_count']} | {st['card_count']} | {st['custom_card_count']} | "
                    f"{st['pillar_component_count']} |"
                )

                # Individual dashboard file
                d_lines = [
                    f"# Dashboard: {dash.title}\n",
                    f"- **ID**: `{dash.id}`",
                    f"- **URL Path**: `{dash.url_path or 'default'}`",
                    f"- **Mode**: `{dash.mode}` (Source: `{dash.source}`)",
                    f"- **Default Dashboard**: {'Yes' if dash.default_dashboard else 'No'}",
                    f"- **Admin Only**: {'Yes' if dash.require_admin else 'No'}\n",
                    "## Summary Metrics\n",
                    f"- **Views**: {st['view_count']}",
                    f"- **Total Cards**: {st['card_count']}",
                    f"- **Custom Cards Used**: {st['custom_card_count']}",
                    f"- **Pillar Components**: {st['pillar_component_count']}",
                    f"- **Referenced Entities**: {st['entity_count']}\n",
                ]

                if dash.custom_cards:
                    d_lines.append("## Custom Cards Used\n")
                    for cc in dash.custom_cards:
                        d_lines.append(f"- `{cc}`")
                    d_lines.append("")

                if dash.pillar_components:
                    d_lines.append("## Pillar Components\n")
                    for pc in dash.pillar_components:
                        p_title = pc.get("title") or pc.get("card_type")
                        d_lines.append(f"### {p_title}")
                        d_lines.append(f"- **Card Type**: `{pc.get('card_type')}`")
                        if pc.get("navigation_path"):
                            d_lines.append(f"- **Navigation Path**: `{pc['navigation_path']}`")
                        p_ents = pc.get("entities") or []
                        if p_ents:
                            d_lines.append(
                                f"- **Referenced Entities ({len(p_ents)})**: "
                                f"{', '.join([f'`{e}`' for e in p_ents])}"
                            )
                        d_lines.append("")

                if dash.views:
                    d_lines.append("## Views & Layout\n")
                    for idx, v in enumerate(dash.views, 1):
                        v_icon = f" ({v.icon})" if v.icon else ""
                        d_lines.append(f"### View {idx}: {v.title}{v_icon}\n")
                        if v.path:
                            d_lines.append(f"- **Path**: `{v.path}`")
                        d_lines.append(f"- **Cards in View**: {len(v.cards)}")
                        if v.sections:
                            d_lines.append(f"- **Sections in View**: {len(v.sections)}")
                        d_lines.append("")

                        def _format_cards(
                            cards: list, target_lines: list[str], indent_level: int = 0
                        ) -> None:
                            prefix = "  " * indent_level
                            for card in cards:
                                c_t = card.title or card.type
                                target_lines.append(f"{prefix}- **{c_t}** (`{card.type}`)")
                                if card.entities:
                                    target_lines.append(
                                        f"{prefix}  - Entities: "
                                        f"{', '.join([f'`{e}`' for e in card.entities])}"
                                    )
                                if card.navigation_path:
                                    target_lines.append(
                                        f"{prefix}  - Navigation: `{card.navigation_path}`"
                                    )
                                if card.services:
                                    target_lines.append(
                                        f"{prefix}  - Services Called: "
                                        f"{', '.join([f'`{s}`' for s in card.services])}"
                                    )
                                if card.nested_cards:
                                    _format_cards(card.nested_cards, target_lines, indent_level + 1)

                        _format_cards(v.cards, d_lines)
                        d_lines.append("")

                if dash.warnings:
                    d_lines.append("## Warnings & Unresolved Templates\n")
                    for w in dash.warnings:
                        d_lines.append(f"- ⚠️ {w}")
                    d_lines.append("")

                write_text(dash_dir / f"{slug_name}.md", "\n".join(d_lines))
        else:
            overview_lines.append("_No standard Lovelace dashboards analyzed._\n")

        # Section 2: Strategy Dashboards
        strat_panels = [
            p for p in panel_list if getattr(p, "panel_type", "") == "lovelace_strategy"
        ]
        overview_lines.append("\n## 2. Strategy Dashboards\n")
        if strat_panels:
            overview_lines.append(
                "| Title | URL Path | Config Expandable | Details |\n"
                "| :--- | :--- | :--- | :--- |\n"
            )
            for p in strat_panels:
                exp_str = "Yes" if getattr(p, "lovelace_config_available", False) else "No"
                r_str = getattr(p, "warning_or_reason", None) or "Strategy-based generation"
                overview_lines.append(f"| {p.title} | `{p.url_path}` | {exp_str} | {r_str} |\n")
        else:
            overview_lines.append("_No strategy dashboards discovered._\n")

        # Section 3: Built-in Home Assistant Panels
        builtin_panels = [p for p in panel_list if getattr(p, "panel_type", "") == "builtin_panel"]
        overview_lines.append("\n## 3. Built-in Home Assistant Panels\n")
        if builtin_panels:
            overview_lines.append(
                "| Title | URL Path | Component | Admin Required | Details |\n"
                "| :--- | :--- | :--- | :--- | :--- |\n"
            )
            for p in builtin_panels:
                adm_str = "Yes" if getattr(p, "require_admin", False) else "No"
                r_str = (
                    getattr(p, "warning_or_reason", None)
                    or "Built-in panel, no Lovelace config expected"
                )
                overview_lines.append(
                    f"| {p.title} | `{p.url_path}` | `{p.component_name}` | {adm_str} | {r_str} |\n"
                )
        else:
            overview_lines.append("_No built-in panels discovered._\n")

        # Section 4: Integration-Provided Panels
        integ_panels = [
            p
            for p in panel_list
            if getattr(p, "panel_type", "")
            in [
                "integration_panel",
                "redirect_panel",
                "unknown_panel",
            ]
        ]
        overview_lines.append("\n## 4. Integration-Provided Panels\n")
        if integ_panels:
            overview_lines.append(
                "| Title | URL Path | Component | Admin Required | Details |\n"
                "| :--- | :--- | :--- | :--- | :--- |\n"
            )
            for p in integ_panels:
                adm_str = "Yes" if getattr(p, "require_admin", False) else "No"
                r_str = getattr(p, "warning_or_reason", None) or "Integration panel"
                overview_lines.append(
                    f"| {p.title} | `{p.url_path}` | `{p.component_name}` | {adm_str} | {r_str} |\n"
                )
        else:
            overview_lines.append("_No integration-provided panels discovered._\n")

        # Section 5: Unavailable or Failed Dashboard Configurations
        unavail_panels = [
            p
            for p in panel_list
            if not getattr(p, "lovelace_config_available", False)
            and getattr(p, "panel_type", "")
            in [
                "lovelace_storage",
                "lovelace_yaml",
                "lovelace_strategy",
            ]
        ]
        overview_lines.append("\n## 5. Unavailable or Failed Dashboard Configurations\n")
        if unavail_panels:
            overview_lines.append(
                "| Title | URL Path | Type | Reason / Failure |\n| :--- | :--- | :--- | :--- |\n"
            )
            for p in unavail_panels:
                overview_lines.append(
                    f"| {p.title} | `{p.url_path}` | `{p.panel_type}` | "
                    f"{getattr(p, 'warning_or_reason', None) or 'Configuration unresolvable'} |\n"
                )
        else:
            overview_lines.append(
                "_All expected Lovelace dashboards were successfully resolved._\n"
            )

    write_text(dash_dir / "overview.md", "\n".join(overview_lines))

    # 12. ai/orphaned-and-unassigned.md
    ents_no_dev = sorted([e.entity_id for e in entities if not e.device_id])
    ents_no_area = sorted([e.entity_id for e in entities if not e.area_id])
    devs_no_area = sorted([d.device_id for d in devices if not d.area_id])
    devs_no_ents_list = sorted([d.device_id for d in devices if not d.entities])

    ents_missing_dev = sorted(
        [e.entity_id for e in entities if e.device_id and e.device_id not in dev_map]
    )

    unref_ents = sorted(
        [
            e.entity_id
            for e in entities
            if e.entity_id not in auto_ref_map
            and e.entity_id not in script_ref_map
            and e.domain not in HELPER_DOMAINS
            and e.platform != "template"
        ]
    )

    orph_lines = [
        "# Orphaned and Unassigned Entities / Devices\n\n",
        "## Unassigned Entities (No Area)\n",
        f"Total: {len(ents_no_area)}\n",
        f"{', '.join(ents_no_area) if ents_no_area else 'None'}\n\n",
        "## Standalone Entities (No Device)\n",
        f"Total: {len(ents_no_dev)}\n",
        f"{', '.join(ents_no_dev) if ents_no_dev else 'None'}\n\n",
        "## Devices with No Area\n",
        f"Total: {len(devs_no_area)}\n",
        f"{', '.join(devs_no_area) if devs_no_area else 'None'}\n\n",
        "## Devices with No Entities\n",
        f"Total: {len(devs_no_ents_list)}\n",
        f"{', '.join(devs_no_ents_list) if devs_no_ents_list else 'None'}\n\n",
        "## Entities Referencing Missing Devices\n",
        f"Total: {len(ents_missing_dev)}\n",
        f"{', '.join(ents_missing_dev) if ents_missing_dev else 'None'}\n\n",
        "## Unreferenced Entities (Not in Automations or Scripts)\n",
        f"Total: {len(unref_ents)}\n",
        "_(Note: These entities may be used directly in Home Assistant UI dashboards.)_\n",
    ]
    write_text(ai_dir / "orphaned-and-unassigned.md", "".join(orph_lines))

    # Build dashboard impact mapping
    dash_entity_usage: dict[str, list[dict[str, Any]]] = {}
    dash_device_usage: dict[str, set[str]] = {}
    dash_area_usage: dict[str, set[str]] = {}

    for dash in dash_list:
        cur_dash_id = dash.id
        cur_dash_title = dash.title
        for view in dash.views:
            cur_view_title = view.title

            def _map_card_entities(cards: list, d_id: str, d_t: str, v_t: str) -> None:
                for card in cards:
                    c_type = card.type
                    nav_p = card.navigation_path
                    p_comp = card.pillar_component
                    for ent_id in card.entities:
                        dash_entity_usage.setdefault(ent_id, []).append(
                            {
                                "dashboard_id": d_id,
                                "dashboard_title": d_t,
                                "view_title": v_t,
                                "card_type": c_type,
                                "navigation_path": nav_p,
                                "pillar_component": p_comp,
                            }
                        )
                        if ent_id in ent_map and ent_map[ent_id].device_id:
                            dev_id_val = ent_map[ent_id].device_id
                            if dev_id_val:
                                dash_device_usage.setdefault(dev_id_val, set()).add(d_t)
                        if ent_id in ent_map and ent_map[ent_id].area_id:
                            area_id_val = ent_map[ent_id].area_id
                            if area_id_val:
                                dash_area_usage.setdefault(area_id_val, set()).add(d_t)
                    if card.nested_cards:
                        _map_card_entities(card.nested_cards, d_id, d_t, v_t)

            _map_card_entities(view.cards, cur_dash_id, cur_dash_title, cur_view_title)

    # 13. ai/impact-index.json
    impact_entities: dict[str, Any] = {}
    for e in sorted(entities, key=lambda x: x.entity_id):
        impact_entities[e.entity_id] = {
            "area_id": e.area_id or None,
            "automations": sorted(auto_ref_map.get(e.entity_id, set())),
            "dashboards": dash_entity_usage.get(e.entity_id, []),
            "device_id": e.device_id or None,
            "labels": sorted(e.labels),
            "related_entities": [],
            "scripts": sorted(script_ref_map.get(e.entity_id, set())),
        }

    impact_devices: dict[str, Any] = {}
    for d in sorted(devices, key=lambda x: x.device_id):
        d_autos = sorted(
            {
                auto["alias"]
                for auto in detailed_autos
                if any(ref in d.entities for ref in auto["all_references"])
            }
        )
        d_scripts = sorted(
            {
                sc["alias"]
                for sc in detailed_scripts
                if any(ref in d.entities for ref in sc["references"])
            }
        )
        impact_devices[d.device_id] = {
            "area_id": d.area_id or None,
            "automations": d_autos,
            "dashboards": sorted(dash_device_usage.get(d.device_id, set())),
            "entities": sorted(d.entities),
            "scripts": d_scripts,
        }

    impact_areas: dict[str, Any] = {}
    for a in sorted(areas, key=lambda x: x.area_id):
        a_devs = sorted([d.device_id for d in devices if d.area_id == a.area_id])
        a_ents = sorted([e.entity_id for e in entities if e.area_id == a.area_id])
        a_autos = sorted(
            {
                auto["alias"]
                for auto in detailed_autos
                if any(ref in a_ents for ref in auto["all_references"])
            }
        )
        a_scripts = sorted(
            {
                sc["alias"]
                for sc in detailed_scripts
                if any(ref in a_ents for ref in sc["references"])
            }
        )
        impact_areas[a.area_id] = {
            "automations": a_autos,
            "dashboards": sorted(dash_area_usage.get(a.area_id, set())),
            "devices": a_devs,
            "entities": a_ents,
            "scripts": a_scripts,
        }

    impact_index = {
        "areas": impact_areas,
        "devices": impact_devices,
        "entities": impact_entities,
    }
    write_stable_json(ai_dir / "impact-index.json", impact_index)

    # 14. ai/search-index.json
    search_records: list[dict[str, Any]] = []

    for dash in sorted(dash_list, key=lambda x: (x.title.lower(), x.id)):
        keywords = _build_keywords(dash.title, dash.id, dash.url_path, "dashboard")
        slug_name = (dash.title or dash.id).strip().replace(" ", "_").replace("/", "_")
        search_records.append(
            {
                "area": None,
                "device": None,
                "domain": "dashboard",
                "id": dash.id,
                "integration": None,
                "keywords": keywords,
                "labels": [],
                "name": dash.title,
                "summary": (
                    f"Lovelace dashboard '{dash.title}' ({dash.mode} mode) "
                    f"with {len(dash.views)} views."
                ),
                "type": "dashboard",
                "file_path": f"ai/dashboards/{slug_name}.md",
            }
        )

    for a in sorted(areas, key=lambda x: x.area_id):
        a_dev_cnt = sum(1 for d in devices if d.area_id == a.area_id)
        a_ent_cnt = sum(1 for e in entities if e.area_id == a.area_id)
        keywords = _build_keywords(a.name, a.area_id, "area")
        search_records.append(
            {
                "area": a.name,
                "device": None,
                "domain": "area",
                "id": a.area_id,
                "integration": None,
                "keywords": keywords,
                "labels": [],
                "name": a.name,
                "summary": f"Area {a.name} with {a_dev_cnt} devices and {a_ent_cnt} entities.",
                "type": "area",
            }
        )

    for d in sorted(devices, key=lambda x: x.device_id):
        keywords = _build_keywords(
            d.name, d.device_id, d.manufacturer, d.model, d.integration, "device"
        )
        search_records.append(
            {
                "area": d.area_name or None,
                "device": d.name,
                "domain": "device",
                "id": d.device_id,
                "integration": d.integration or None,
                "keywords": keywords,
                "labels": sorted(d.labels),
                "name": d.name,
                "summary": f"Device {d.name} in {d.area_name or 'Unassigned'}.",
                "type": "device",
            }
        )

    for e in sorted(entities, key=lambda x: x.entity_id):
        dev_name = dev_map[e.device_id].name if e.device_id in dev_map else None
        keywords = _build_keywords(
            e.name, e.entity_id, e.domain, e.platform, e.device_class, "entity"
        )
        search_records.append(
            {
                "area": e.area_name or None,
                "device": dev_name,
                "domain": e.domain,
                "id": e.entity_id,
                "integration": e.platform or None,
                "keywords": keywords,
                "labels": sorted(e.labels),
                "name": e.name,
                "summary": f"{e.name} ({e.entity_id}) in {e.area_name or 'Unassigned'}.",
                "type": "entity",
            }
        )

    for auto in detailed_autos:
        keywords = _build_keywords(auto["alias"], auto["id"], "automation")
        search_records.append(
            {
                "area": None,
                "device": None,
                "domain": "automation",
                "id": auto["id"],
                "integration": None,
                "keywords": keywords,
                "labels": [],
                "name": auto["alias"],
                "summary": f"Automation {auto['alias']} ({len(auto['all_references'])} refs).",
                "type": "automation",
            }
        )

    for sc in detailed_scripts:
        keywords = _build_keywords(sc["alias"], sc["id"], "script")
        search_records.append(
            {
                "area": None,
                "device": None,
                "domain": "script",
                "id": sc["id"],
                "integration": None,
                "keywords": keywords,
                "labels": [],
                "name": sc["alias"],
                "summary": f"Script {sc['alias']} ({len(sc['references'])} refs).",
                "type": "script",
            }
        )

    for lbl in sorted(labels, key=lambda x: x.label_id):
        keywords = _build_keywords(lbl.name, lbl.label_id, "label")
        search_records.append(
            {
                "area": None,
                "device": None,
                "domain": "label",
                "id": lbl.label_id,
                "integration": None,
                "keywords": keywords,
                "labels": [lbl.name],
                "name": lbl.name,
                "summary": f"Label {lbl.name} ({lbl.label_id}).",
                "type": "label",
            }
        )

    search_index = {"records": search_records}
    write_stable_json(ai_dir / "search-index.json", search_index)
    logger.info("Successfully exported AI reference layer into %s", ai_dir)


def _build_keywords(*args: str | None) -> list[str]:
    """Generate normalized, deduplicated list of search keywords."""
    tokens: set[str] = set()
    for arg in args:
        if not arg:
            continue
        cleaned = re.sub(r"[^a-zA-Z0-9_\-]", " ", str(arg)).lower()
        for token in cleaned.split():
            if len(token) >= 2:
                tokens.add(token)
    return sorted(tokens)
