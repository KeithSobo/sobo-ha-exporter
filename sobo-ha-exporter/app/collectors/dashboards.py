"""Collector and recursive card parser for Home Assistant Lovelace dashboards and panels."""

import logging
import re
from pathlib import Path
from typing import Any

import yaml

from app.models.area import AreaModel
from app.models.dashboard import CardModel, DashboardModel, PanelModel, ViewModel
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

    # 1. Direct entity field or condition entities
    ent_val = raw_card.get("entity")
    if isinstance(ent_val, str) and ENTITY_ID_REGEX.match(ent_val):
        entities.add(ent_val)
    elif isinstance(ent_val, dict) and isinstance(ent_val.get("entity"), str):
        if ENTITY_ID_REGEX.match(ent_val["entity"]):
            entities.add(ent_val["entity"])

    conds_val = raw_card.get("conditions")
    if isinstance(conds_val, list):
        for c in conds_val:
            if isinstance(c, dict):
                c_ent = c.get("entity")
                if isinstance(c_ent, str) and ENTITY_ID_REGEX.match(c_ent):
                    entities.add(c_ent)

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
                for val in e.values():
                    if isinstance(val, str):
                        extracted = extract_template_entities(val, warnings, title)
                        entities.update(extracted)
                        if "{{" in val or "{%" in val:
                            templates.append(val)

    # 3. Actions & Navigation Path
    if isinstance(raw_card.get("navigation_path"), str):
        navigation_path = raw_card["navigation_path"]

    for act_key in ["tap_action", "hold_action", "double_tap_action"]:
        act_dict = raw_card.get(act_key)
        if isinstance(act_dict, dict):
            actions.append(act_dict)
            act_type = act_dict.get("action")
            if act_type == "navigate" and isinstance(act_dict.get("navigation_path"), str):
                navigation_path = act_dict["navigation_path"]
            elif act_type == "call-service" or "service" in act_dict:
                if isinstance(act_dict.get("service"), str):
                    services.add(act_dict["service"])
                t_dict = act_dict.get("target")
                if isinstance(t_dict, dict):
                    t_ent = t_dict.get("entity_id")
                    if isinstance(t_ent, str) and ENTITY_ID_REGEX.match(t_ent):
                        entities.add(t_ent)
                    elif isinstance(t_ent, list):
                        for te in t_ent:
                            if isinstance(te, str) and ENTITY_ID_REGEX.match(te):
                                entities.add(te)

    # 4. Templates in card properties
    for key, val in raw_card.items():
        if key in ["content", "template", "text", "state"] and isinstance(val, str):
            extracted = extract_template_entities(val, warnings, title)
            entities.update(extracted)
            if "{{" in val or "{%" in val:
                templates.append(val)

    # 5. Pillar Custom Component Detection
    pillar_comp: dict[str, Any] | None = None
    if card_type.startswith("custom:pillar-") or (
        custom_name and custom_name.startswith("pillar-")
    ):
        pillar_comp = {
            "card_type": card_type,
            "title": title,
            "entities": sorted(entities),
            "navigation_path": navigation_path,
        }

    # 6. Nested cards traversal (check ALL keys, not just first truthy)
    for sub_key in ["cards", "elements", "chips", "badges"]:
        sub_val = raw_card.get(sub_key)
        if isinstance(sub_val, list):
            for sc in sub_val:
                if isinstance(sc, dict):
                    nested_cards.append(parse_card(sc, warnings))

    # Single nested card (e.g. conditional card)
    single_card = raw_card.get("card")
    if isinstance(single_card, dict):
        nested_cards.append(parse_card(single_card, warnings))

    # Sections layout support
    sections_val = raw_card.get("sections")
    if isinstance(sections_val, list):
        for sec in sections_val:
            if isinstance(sec, dict):
                sec_cards = sec.get("cards")
                if isinstance(sec_cards, list):
                    for sc in sec_cards:
                        if isinstance(sc, dict):
                            nested_cards.append(parse_card(sc, warnings))

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


def parse_view(raw_view: dict[str, Any], warns: list[str]) -> ViewModel:
    """Parse a raw view dictionary into a ViewModel instance."""
    if not isinstance(raw_view, dict):
        return ViewModel(title="Unknown View")

    title = str(raw_view.get("title") or raw_view.get("path") or "Untitled View")
    path = str(raw_view.get("path")) if raw_view.get("path") else None
    icon = str(raw_view.get("icon")) if raw_view.get("icon") else None

    raw_badges = raw_view.get("badges")
    badges: list[dict[str, Any]] = list(raw_badges) if isinstance(raw_badges, list) else []
    raw_chips = raw_view.get("chips")
    chips: list[dict[str, Any]] = list(raw_chips) if isinstance(raw_chips, list) else []
    raw_sections = raw_view.get("sections")
    sections: list[dict[str, Any]] = list(raw_sections) if isinstance(raw_sections, list) else []

    card_models: list[CardModel] = []
    raw_cards = raw_view.get("cards")
    if isinstance(raw_cards, list):
        for c_raw in raw_cards:
            if isinstance(c_raw, dict):
                card_models.append(parse_card(c_raw, warns))

    for sec in sections:
        if isinstance(sec, dict):
            sec_cards = sec.get("cards")
            if isinstance(sec_cards, list):
                for sc_raw in sec_cards:
                    if isinstance(sc_raw, dict):
                        card_models.append(parse_card(sc_raw, warns))

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


def classify_panel(
    url_path: str,
    panel_data: dict[str, Any],
    custom_dash_regs: list[dict[str, Any]],
) -> str:
    """Classify Home Assistant panel into normalized category.

    Categories:
        - lovelace_storage
        - lovelace_yaml
        - lovelace_strategy
        - builtin_panel
        - integration_panel
        - redirect_panel
        - unknown_panel
    """
    comp_name = str(panel_data.get("component_name") or "")
    cfg = panel_data.get("config") or {}
    mode = cfg.get("mode") if isinstance(cfg, dict) else panel_data.get("mode")
    strategy = cfg.get("strategy") if isinstance(cfg, dict) else panel_data.get("strategy")

    if strategy or mode == "strategy":
        return "lovelace_strategy"

    if (
        comp_name == "lovelace"
        or url_path in ["lovelace", "default"]
        or any(r.get("url_path") == url_path for r in custom_dash_regs)
    ):
        if mode == "yaml":
            return "lovelace_yaml"
        return "lovelace_storage"

    builtin_slugs = {
        "map",
        "logbook",
        "history",
        "media-browser",
        "config",
        "developer-tools",
        "profile",
        "energy",
        "todo",
        "calendar",
        "area",
        "areas",
    }
    if comp_name in builtin_slugs or url_path in builtin_slugs:
        return "builtin_panel"

    integration_slugs = {
        "zha",
        "zigbee2mqtt",
        "hacs",
        "nodered",
        "esphome",
        "portainer",
        "grafana",
    }
    if (
        comp_name in integration_slugs
        or url_path in integration_slugs
        or panel_data.get("module_url")
    ):
        return "integration_panel"

    if panel_data.get("embed_iframe") or comp_name == "iframe":
        return "redirect_panel"

    if comp_name:
        return "builtin_panel"
    return "unknown_panel"


def collect_dashboards(
    client: Any | None,
    config_dir: Path,
    entities: list[EntityModel] | None = None,
    devices: list[DeviceModel] | None = None,
    areas: list[AreaModel] | None = None,
    labels: list[LabelModel] | None = None,
) -> tuple[list[DashboardModel], list[PanelModel], list[str], str | None]:
    """Collect Lovelace dashboards and classify panels via HA WebSocket API or YAML fallback.

    Returns:
        Tuple of (list of DashboardModel, list of PanelModel,
        list of warnings, discovery error string if any).
    """
    dashboards: list[DashboardModel] = []
    panels: list[PanelModel] = []
    warnings: list[str] = []
    discovery_error: str | None = None

    entity_ids = {e.entity_id for e in (entities or [])}

    # Attempt 1: Fetch via WebSocket API
    if client is not None:
        try:
            # 1. Fetch registered panels and custom dashboards
            panel_map: dict[str, dict[str, Any]] = {}
            try:
                res = client.get_panels()
                if isinstance(res, dict):
                    panel_map = res
            except Exception as e:
                logger.debug("get_panels call exception: %s", e)

            custom_dash_regs: list[dict[str, Any]] = []
            try:
                c_regs = client.get_lovelace_dashboards()
                if isinstance(c_regs, list):
                    custom_dash_regs = c_regs
            except Exception as e:
                logger.debug("get_lovelace_dashboards call exception: %s", e)

            # Ensure default dashboard panel exists in panel_map if missing
            if "lovelace" not in panel_map:
                panel_map["lovelace"] = {
                    "component_name": "lovelace",
                    "title": "Home",
                    "icon": "mdi:home",
                    "config": {"mode": "storage"},
                }

            # Add custom dashboards to panel_map if missing
            for reg in custom_dash_regs:
                if isinstance(reg, dict):
                    u_path = reg.get("url_path")
                    if u_path and u_path not in panel_map:
                        panel_map[u_path] = {
                            "component_name": "lovelace",
                            "title": reg.get("title") or u_path.title(),
                            "icon": reg.get("icon"),
                            "require_admin": bool(reg.get("require_admin", False)),
                            "config": {"mode": reg.get("mode", "storage")},
                        }

            # 2. Process and classify each panel (lovelace first for deterministic side-effects)
            sorted_panels = sorted(
                panel_map.items(),
                key=lambda x: (0 if x[0] in ["lovelace", "default"] else 1, str(x[0])),
            )
            for url_path, p_data in sorted_panels:
                comp_name = str(p_data.get("component_name") or "")
                p_title = str(
                    p_data.get("title") or url_path.replace("-", " ").replace("_", " ").title()
                )
                p_type = classify_panel(url_path, p_data, custom_dash_regs)
                require_admin = bool(p_data.get("require_admin", False))
                icon = p_data.get("icon")

                lovelace_avail = False
                reason: str | None = None

                # Call lovelace/config ONLY for panels expected to expose Lovelace configuration
                if p_type in ["lovelace_storage", "lovelace_yaml"]:
                    req_path = None if url_path in ["lovelace", "default"] else url_path
                    try:
                        cfg = client.get_lovelace_config(req_path)
                        if cfg and isinstance(cfg, dict) and "views" in cfg:
                            lovelace_avail = True
                            d_id = (
                                "lovelace-default" if req_path is None else f"lovelace-{url_path}"
                            )
                            is_def = req_path is None
                            d_model = _build_dashboard_model(
                                dash_id=d_id,
                                title=cfg.get("title") or p_title,
                                url_path=url_path if not is_def else None,
                                icon=icon,
                                mode=p_data.get("config", {}).get("mode", "storage")
                                if isinstance(p_data.get("config"), dict)
                                else "storage",
                                source="websocket",
                                require_admin=require_admin,
                                default_dashboard=is_def,
                                raw_config=cfg,
                                entity_ids=entity_ids,
                                warns=warnings,
                            )
                            dashboards.append(d_model)
                        else:
                            reason = (
                                f"Lovelace config for '{url_path}' not available or returned empty"
                            )
                            warnings.append(reason)
                    except Exception as e:
                        reason = f"Failed to fetch Lovelace config for '{url_path}': {e}"
                        if req_path is None:
                            discovery_error = reason
                        warnings.append(reason)

                elif p_type == "lovelace_strategy":
                    req_path = None if url_path in ["lovelace", "default"] else url_path
                    try:
                        cfg = client.get_lovelace_config(req_path)
                        if cfg and isinstance(cfg, dict) and "views" in cfg:
                            lovelace_avail = True
                            d_id = f"lovelace-{url_path}"
                            d_model = _build_dashboard_model(
                                dash_id=d_id,
                                title=cfg.get("title") or p_title,
                                url_path=url_path,
                                icon=icon,
                                mode="strategy",
                                source="websocket",
                                require_admin=require_admin,
                                default_dashboard=False,
                                raw_config=cfg,
                                entity_ids=entity_ids,
                                warns=warnings,
                            )
                            dashboards.append(d_model)
                        else:
                            reason = (
                                f"Strategy panel '{url_path}' does not expose"
                                " raw Lovelace configuration"
                            )
                    except Exception as e:
                        reason = f"Strategy panel '{url_path}' configuration not expandable: {e}"

                else:
                    reason = (
                        f"Built-in or non-Lovelace panel ({p_type}), no Lovelace config expected"
                    )

                panels.append(
                    PanelModel(
                        title=p_title,
                        url_path=url_path,
                        component_name=comp_name,
                        panel_type=p_type,
                        icon=icon,
                        require_admin=require_admin,
                        source="websocket",
                        lovelace_config_available=lovelace_avail,
                        warning_or_reason=reason,
                    )
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
                    is_def = slug == "ui-lovelace"
                    u_path = None if is_def else slug
                    y_model = _build_dashboard_model(
                        dash_id=f"yaml-{slug}",
                        title=data.get("title") or slug.replace("-", " ").title(),
                        url_path=u_path,
                        icon=None,
                        mode="yaml",
                        source="yaml",
                        require_admin=False,
                        default_dashboard=is_def,
                        raw_config=data,
                        entity_ids=entity_ids,
                        warns=warnings,
                    )
                    dashboards.append(y_model)

                    panels.append(
                        PanelModel(
                            title=y_model.title,
                            url_path=slug,
                            component_name="lovelace",
                            panel_type="lovelace_yaml",
                            icon=None,
                            require_admin=False,
                            source="yaml",
                            lovelace_config_available=True,
                            warning_or_reason=None,
                        )
                    )
            except Exception as e:
                warnings.append(f"Failed to parse YAML dashboard {yfile.name}: {e}")

    return dashboards, panels, warnings, discovery_error


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
