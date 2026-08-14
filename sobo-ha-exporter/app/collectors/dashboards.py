"""Collector and recursive card parser for Home Assistant Lovelace dashboards."""

import logging
import re
from pathlib import Path
from typing import Any

import yaml

from app.models.area import AreaModel
from app.models.dashboard import CardModel, DashboardModel, ViewModel
from app.models.device import DeviceModel
from app.models.entity import EntityModel
from app.models.label import LabelModel

logger = logging.getLogger(__name__)

# Jinja2 template entity extraction regexes
JINJA_ENTITY_REGEXES = [
    re.compile(
        r"(?:states|is_state|state_attr|is_state_attr|has_value)\(\s*['\"]([a-zA-Z0-9_]+\.[a-zA-Z0-9_]+)['\"]"
    ),
    re.compile(r"states\[['\"]([a-zA-Z0-9_]+\.[a-zA-Z0-9_]+)['\"]\]"),
    re.compile(r"\bstates\.([a-zA-Z0-9_]+\.[a-zA-Z0-9_]+)\b"),
]

# Strict entity ID pattern
ENTITY_ID_REGEX = re.compile(r"^[a-zA-Z0-9_]+\.[a-zA-Z0-9_]+$")


def extract_template_entities(
    text: str, warnings: list[str] | None = None, card_title: str | None = None
) -> list[str]:
    """Extract entity IDs from Jinja2 templates safely."""
    found: set[str] = set()
    if not isinstance(text, str) or not ("{{" in text or "{%" in text or "states" in text):
        return []

    for rx in JINJA_ENTITY_REGEXES:
        for match in rx.findall(text):
            if ENTITY_ID_REGEX.match(match):
                found.add(match)

    # Record unresolved warning if template exists but no entity was extracted
    if ("{{" in text or "{%" in text) and not found and warnings is not None:
        name = card_title or "card"
        snippet = text.strip()[:60]
        warnings.append(f"Unresolved Jinja2 template in {name}: '{snippet}'")

    return sorted(found)


def parse_card(raw_card: dict[str, Any], warnings: list[str]) -> CardModel:
    """Recursively parse a raw card dictionary into a CardModel instance."""
    if not isinstance(raw_card, dict):
        return CardModel(type="unknown")

    card_type = str(raw_card.get("type") or "unknown")
    subtype = str(raw_card.get("subtype")) if raw_card.get("subtype") else None
    title = str(raw_card.get("title")) if raw_card.get("title") else None

    custom_name: str | None = None
    if card_type.startswith("custom:"):
        custom_name = card_type[7:]

    entities: set[str] = set()
    navigation_path: str | None = None
    actions: list[dict[str, Any]] = []
    services: set[str] = set()
    templates: list[str] = []
    variables: list[str] = []
    nested_cards: list[CardModel] = []

    # 1. Direct entity field
    ent_val = raw_card.get("entity")
    if isinstance(ent_val, str) and ENTITY_ID_REGEX.match(ent_val):
        entities.add(ent_val)
    elif isinstance(ent_val, dict) and isinstance(ent_val.get("entity"), str):
        if ENTITY_ID_REGEX.match(ent_val["entity"]):
            entities.add(ent_val["entity"])

    # 2. Entities array field
    ents_val = raw_card.get("entities")
    if isinstance(ents_val, list):
        for e in ents_val:
            if isinstance(e, str) and ENTITY_ID_REGEX.match(e):
                entities.add(e)
            elif isinstance(e, dict):
                sub_e = e.get("entity")
                if isinstance(sub_e, str) and ENTITY_ID_REGEX.match(sub_e):
                    entities.add(sub_e)
                # Check entity in attribute or name templates
                for val in e.values():
                    if isinstance(val, str):
                        extracted = extract_template_entities(val, warnings, title)
                        entities.update(extracted)
                        if "{{" in val or "{%" in val:
                            templates.append(val)

    # 3. Actions (tap_action, hold_action, double_tap_action)
    for act_key in ["tap_action", "hold_action", "double_tap_action"]:
        act = raw_card.get(act_key)
        if isinstance(act, dict):
            actions.append({"action_type": act_key, "data": act})
            act_type = act.get("action")
            if act_type == "navigate" and isinstance(act.get("navigation_path"), str):
                navigation_path = act["navigation_path"]
            elif act_type == "call-service" or act_type == "perform-action":
                srv = act.get("service") or act.get("perform_action")
                if isinstance(srv, str):
                    services.add(srv)
                # Service data / target entity extraction
                t_data = act.get("target") or act.get("service_data") or act.get("data") or {}
                if isinstance(t_data, dict):
                    t_ent = t_data.get("entity_id")
                    if isinstance(t_ent, str) and ENTITY_ID_REGEX.match(t_ent):
                        entities.add(t_ent)
                    elif isinstance(t_ent, list):
                        for item in t_ent:
                            if isinstance(item, str) and ENTITY_ID_REGEX.match(item):
                                entities.add(item)

    # 4. Target entity_id field at card level
    target_val = raw_card.get("target")
    if isinstance(target_val, dict):
        t_ent = target_val.get("entity_id")
        if isinstance(t_ent, str) and ENTITY_ID_REGEX.match(t_ent):
            entities.add(t_ent)
        elif isinstance(t_ent, list):
            for item in t_ent:
                if isinstance(item, str) and ENTITY_ID_REGEX.match(item):
                    entities.add(item)

    # 5. Conditions field (e.g. in conditional card)
    conds = raw_card.get("conditions")
    if isinstance(conds, list):
        for cond in conds:
            if isinstance(cond, dict) and isinstance(cond.get("entity"), str):
                if ENTITY_ID_REGEX.match(cond["entity"]):
                    entities.add(cond["entity"])

    # 6. Deep template search in string values
    for k, v in raw_card.items():
        if k in {"type", "title", "entities", "cards", "sections", "elements", "badges", "chips"}:
            continue
        if isinstance(v, str):
            extracted = extract_template_entities(v, warnings, title)
            if extracted:
                entities.update(extracted)
            if "{{" in v or "{%" in v:
                templates.append(v)

    # 7. Navigation path direct field
    if not navigation_path and isinstance(raw_card.get("navigation_path"), str):
        navigation_path = raw_card["navigation_path"]

    # 8. Check Pillar Component
    pillar_comp: dict[str, Any] | None = None
    if card_type.startswith("custom:pillar") or "pillar" in card_type.lower():
        pillar_comp = {
            "card_type": card_type,
            "title": title or card_type,
            "entities": sorted(entities),
            "navigation_path": navigation_path,
        }

    # 9. Recursively process nested child cards / sections / chips / elements
    child_card_lists: list[list[Any]] = []
    if isinstance(raw_card.get("cards"), list):
        child_card_lists.append(raw_card["cards"])
    if isinstance(raw_card.get("card"), dict):
        child_card_lists.append([raw_card["card"]])
    if isinstance(raw_card.get("sections"), list):
        for sec in raw_card["sections"]:
            if isinstance(sec, dict) and isinstance(sec.get("cards"), list):
                child_card_lists.append(sec["cards"])
    if isinstance(raw_card.get("chips"), list):
        for chip in raw_card["chips"]:
            if isinstance(chip, dict):
                child_card_lists.append([chip])
    if isinstance(raw_card.get("badges"), list):
        for badge in raw_card["badges"]:
            if isinstance(badge, dict):
                child_card_lists.append([badge])
    if isinstance(raw_card.get("elements"), list):
        for elem in raw_card["elements"]:
            if isinstance(elem, dict):
                child_card_lists.append([elem])

    for card_list in child_card_lists:
        for sub_c in card_list:
            if isinstance(sub_c, dict):
                child_model = parse_card(sub_c, warnings)
                nested_cards.append(child_model)

    return CardModel(
        type=card_type,
        subtype=subtype,
        title=title,
        entities=sorted(entities),
        navigation_path=navigation_path,
        actions=actions,
        services=sorted(services),
        templates=templates,
        variables=variables,
        custom_card_name=custom_name,
        pillar_component=pillar_comp,
        nested_cards=nested_cards,
    )


def parse_view(
    raw_view: dict[str, Any],
    warns: list[str],
) -> ViewModel:
    """Parse a raw view dict into a ViewModel."""
    title = str(raw_view.get("title", "Unnamed View"))
    path = str(raw_view.get("path")) if raw_view.get("path") else None
    icon = str(raw_view.get("icon")) if raw_view.get("icon") else None

    badges: list[dict[str, Any]] = (
        [b for b in raw_view["badges"] if isinstance(b, dict)]
        if isinstance(raw_view.get("badges"), list)
        else []
    )
    chips: list[dict[str, Any]] = (
        [c for c in raw_view["chips"] if isinstance(c, dict)]
        if isinstance(raw_view.get("chips"), list)
        else []
    )
    sections: list[dict[str, Any]] = (
        [s for s in raw_view["sections"] if isinstance(s, dict)]
        if isinstance(raw_view.get("sections"), list)
        else []
    )
    cards_raw: list[dict[str, Any]] = (
        [c for c in raw_view["cards"] if isinstance(c, dict)]
        if isinstance(raw_view.get("cards"), list)
        else []
    )

    card_models: list[CardModel] = []
    for c_raw in cards_raw:
        c_model = parse_card(c_raw, warns)
        card_models.append(c_model)

    for sec in sections:
        sec_cards_raw = sec.get("cards") if isinstance(sec, dict) else None
        sec_cards: list[Any] = sec_cards_raw if isinstance(sec_cards_raw, list) else []
        for sc_raw in sec_cards:
            if isinstance(sc_raw, dict):
                sc_model = parse_card(sc_raw, warns)
                card_models.append(sc_model)

    return ViewModel(
        title=title,
        path=path,
        icon=icon,
        badges=badges,
        chips=chips,
        sections=sections,
        cards=card_models,
        visible=raw_view.get("visible"),
    )


def collect_dashboards(
    client: Any | None,
    config_dir: Path,
    entities: list[EntityModel] | None = None,
    devices: list[DeviceModel] | None = None,
    areas: list[AreaModel] | None = None,
    labels: list[LabelModel] | None = None,
) -> tuple[list[DashboardModel], list[str], str | None]:
    """Collect Lovelace dashboards via HA WebSocket API (UI-managed) or YAML fallback.

    Returns:
        Tuple of (list of DashboardModel, list of warnings, discovery error string if any).
    """
    dashboards: list[DashboardModel] = []
    warnings: list[str] = []
    discovery_error: str | None = None

    entity_ids = {e.entity_id for e in (entities or [])}

    # Attempt 1: Fetch via WebSocket API
    if client is not None:
        try:
            # 1. Fetch registered dashboards
            custom_dash_regs: list[dict[str, Any]] = []
            try:
                custom_dash_regs = client.get_lovelace_dashboards()
            except Exception as e:
                logger.debug("get_lovelace_dashboards call exception: %s", e)

            # 2. Fetch default main dashboard config
            default_config: dict[str, Any] | None = None
            try:
                default_config = client.get_lovelace_config(None)
            except Exception as e:
                logger.warning("Failed to fetch default Lovelace dashboard config: %s", e)
                warnings.append(f"Failed to fetch default Lovelace dashboard config: {e}")
                discovery_error = f"Failed to fetch default Lovelace dashboard: {e}"

            if default_config and isinstance(default_config, dict):
                d_model = _build_dashboard_model(
                    dash_id="lovelace-default",
                    title=default_config.get("title") or "Home",
                    url_path=None,
                    icon=None,
                    mode="storage",
                    source="websocket",
                    require_admin=False,
                    default_dashboard=True,
                    raw_config=default_config,
                    entity_ids=entity_ids,
                    warns=warnings,
                )
                dashboards.append(d_model)

            # 3. Fetch custom dashboards
            for reg in custom_dash_regs:
                url_path = reg.get("url_path")
                if not url_path:
                    continue
                d_title = reg.get("title") or url_path.title()
                d_mode = reg.get("mode", "storage")
                d_id = f"lovelace-{url_path}"

                try:
                    c_config = client.get_lovelace_config(url_path)
                    if c_config and isinstance(c_config, dict):
                        c_model = _build_dashboard_model(
                            dash_id=d_id,
                            title=c_config.get("title") or d_title,
                            url_path=url_path,
                            icon=reg.get("icon"),
                            mode=d_mode,
                            source="websocket",
                            require_admin=bool(reg.get("require_admin", False)),
                            default_dashboard=False,
                            raw_config=c_config,
                            entity_ids=entity_ids,
                            warns=warnings,
                        )
                        dashboards.append(c_model)
                except Exception as e:
                    logger.warning(
                        "Failed to fetch Lovelace config for dashboard '%s': %s", url_path, e
                    )
                    warnings.append(
                        f"Failed to fetch Lovelace config for dashboard '{url_path}': {e}"
                    )

        except Exception as e:
            err_msg = f"Lovelace WebSocket discovery failed: {e}"
            logger.warning(err_msg)
            warnings.append(err_msg)
            discovery_error = err_msg

    # Attempt 2: Fallback to YAML dashboards if zero dashboards retrieved
    if not dashboards:
        yaml_files = sorted(config_dir.glob("ui-lovelace*.yaml"))
        for yfile in yaml_files:
            try:
                content = yfile.read_text(encoding="utf-8", errors="ignore")
                data = yaml.safe_load(content)
                if isinstance(data, dict):
                    slug = yfile.stem
                    y_model = _build_dashboard_model(
                        dash_id=f"yaml-{slug}",
                        title=data.get("title") or slug.replace("-", " ").title(),
                        url_path=slug if slug != "ui-lovelace" else None,
                        icon=None,
                        mode="yaml",
                        source="yaml",
                        require_admin=False,
                        default_dashboard=slug == "ui-lovelace",
                        raw_config=data,
                        entity_ids=entity_ids,
                        warns=warnings,
                    )
                    dashboards.append(y_model)
            except Exception as e:
                warnings.append(f"Failed to parse YAML dashboard {yfile.name}: {e}")

    return dashboards, warnings, discovery_error


def _build_dashboard_model(
    dash_id: str,
    title: str,
    url_path: str | None,
    icon: str | None,
    mode: str,
    source: str,
    require_admin: bool,
    default_dashboard: bool,
    raw_config: dict[str, Any],
    entity_ids: set[str],
    warns: list[str],
) -> DashboardModel:
    """Helper to convert raw dashboard dict into DashboardModel."""
    dash_warns: list[str] = []
    views_raw_val = raw_config.get("views")
    views_raw: list[Any] = views_raw_val if isinstance(views_raw_val, list) else []

    view_models: list[ViewModel] = []
    for v_raw in views_raw:
        if isinstance(v_raw, dict):
            view_models.append(parse_view(v_raw, dash_warns))

    custom_cards: set[str] = set()
    pillar_components: list[dict[str, Any]] = []
    ref_entities: set[str] = set()

    def _traverse_card(card: CardModel) -> None:
        if card.custom_card_name:
            custom_cards.add(card.custom_card_name)
        if card.pillar_component:
            pillar_components.append(card.pillar_component)
        ref_entities.update(card.entities)
        for nested in card.nested_cards:
            _traverse_card(nested)

    for vm in view_models:
        for card in vm.cards:
            _traverse_card(card)

    matched_entities = sorted(ref_entities.intersection(entity_ids))

    relationships: dict[str, list[str]] = {
        "entities": matched_entities or sorted(ref_entities),
        "devices": [],
        "areas": [],
    }

    warns.extend(dash_warns)

    return DashboardModel(
        id=dash_id,
        title=title,
        url_path=url_path,
        icon=icon,
        mode=mode,
        source=source,
        require_admin=require_admin,
        default_dashboard=default_dashboard,
        views=view_models,
        custom_cards=sorted(custom_cards),
        pillar_components=pillar_components,
        relationships=relationships,
        warnings=dash_warns,
    )
