"""Unit tests for Lovelace dashboard collection, parsing, Pillar components, and exporters."""

import json
from unittest.mock import MagicMock

from app.collectors.dashboards import (
    collect_dashboards,
    extract_template_entities,
    parse_card,
)
from app.exporters.ai_exporter import export_ai_reference_layer
from app.exporters.json_exporter import export_inventory_json, export_references_json
from app.ha_client import HomeAssistantClientError
from app.models.dashboard import CardModel, DashboardModel, ViewModel
from app.models.entity import EntityModel
from app.models.relationship import RelationshipModel


def test_jinja2_template_entity_extraction():
    tpl1 = "{{ states('sensor.living_room_temp') > 20 }}"
    tpl2 = "{% if is_state('light.kitchen', 'on') and state_attr('switch.fan', 'mode') == 'auto' %}"
    tpl3 = "{{ states.climate.bedroom_ac.state }}"

    warns: list[str] = []
    ents1 = extract_template_entities(tpl1, warns, "Card 1")
    ents2 = extract_template_entities(tpl2, warns, "Card 2")
    ents3 = extract_template_entities(tpl3, warns, "Card 3")

    assert ents1 == ["sensor.living_room_temp"]
    assert ents2 == ["light.kitchen", "switch.fan"]
    assert ents3 == ["climate.bedroom_ac"]
    assert len(warns) == 0

    # Unresolved template warning check
    unresolved_tpl = "{{ custom_calc(123) }}"
    unres_ents = extract_template_entities(unresolved_tpl, warns, "Unresolved Card")
    assert unres_ents == []
    assert len(warns) == 1
    assert "Unresolved Jinja2 template in Unresolved Card" in warns[0]


def test_parse_card_recursive_and_pillar_detection():
    raw_card = {
        "type": "vertical-stack",
        "title": "Main Stack",
        "cards": [
            {
                "type": "entities",
                "title": "Sensor Entities",
                "entities": [
                    "sensor.temperature",
                    {"entity": "light.living_room", "name": "Living Light"},
                    "invalid_string_not_entity",
                ],
            },
            {
                "type": "custom:pillar-main-group-card",
                "title": "Pillar Living Room",
                "navigation_path": "/lovelace/living",
                "entities": ["switch.main_power", "sensor.power_usage"],
                "chips": [
                    {
                        "type": "custom:pillar-chips",
                        "entity": "binary_sensor.motion",
                    }
                ],
            },
            {
                "type": "button",
                "title": "Action Button",
                "entity": "script.turn_off_all",
                "tap_action": {
                    "action": "call-service",
                    "service": "light.turn_off",
                    "target": {"entity_id": "light.all_lights"},
                },
            },
        ],
    }

    warns: list[str] = []
    card_model = parse_card(raw_card, warns)

    assert card_model.type == "vertical-stack"
    assert card_model.title == "Main Stack"
    assert len(card_model.nested_cards) == 3

    # Entities card check
    ent_card = card_model.nested_cards[0]
    assert ent_card.type == "entities"
    assert "sensor.temperature" in ent_card.entities
    assert "light.living_room" in ent_card.entities

    # Pillar component check
    pillar_card = card_model.nested_cards[1]
    assert pillar_card.type == "custom:pillar-main-group-card"
    assert pillar_card.custom_card_name == "pillar-main-group-card"
    assert pillar_card.pillar_component is not None
    assert pillar_card.pillar_component["card_type"] == "custom:pillar-main-group-card"
    assert pillar_card.navigation_path == "/lovelace/living"

    # Action button check
    btn_card = card_model.nested_cards[2]
    assert btn_card.type == "button"
    assert "script.turn_off_all" in btn_card.entities
    assert "light.all_lights" in btn_card.entities
    assert "light.turn_off" in btn_card.services


def test_collect_dashboards_websocket_storage_mode(tmp_path):
    mock_client = MagicMock()
    mock_client.get_lovelace_dashboards.return_value = [
        {
            "id": "network",
            "url_path": "network",
            "title": "Network Overview",
            "icon": "mdi:router-wireless",
            "mode": "storage",
            "require_admin": False,
        }
    ]
    mock_client.get_lovelace_config.side_effect = lambda url_path: (
        {
            "title": "My Home",
            "views": [
                {
                    "title": "Main View",
                    "path": "home",
                    "cards": [
                        {"type": "tile", "entity": "light.hallway"},
                    ],
                }
            ],
        }
        if url_path is None
        else {
            "title": "Network Overview",
            "views": [
                {
                    "title": "Routers",
                    "path": "routers",
                    "cards": [
                        {"type": "entities", "entities": ["sensor.router_status"]},
                    ],
                }
            ],
        }
    )

    entities = [
        EntityModel(entity_id="light.hallway", name="Hallway Light"),
        EntityModel(entity_id="sensor.router_status", name="Router Status"),
    ]

    dashboards, panels, _warns, discovery_err = collect_dashboards(
        client=mock_client,
        config_dir=tmp_path,
        entities=entities,
    )

    assert discovery_err is None
    assert len(dashboards) == 2
    assert len(panels) >= 2

    # Default dashboard check
    def_dash = next(d for d in dashboards if d.default_dashboard)
    assert def_dash.id == "lovelace-default"
    assert def_dash.title == "My Home"
    assert def_dash.mode == "storage"
    assert len(def_dash.views) == 1
    assert "light.hallway" in def_dash.relationships["entities"]

    # Custom network dashboard check
    net_dash = next(d for d in dashboards if d.url_path == "network")
    assert net_dash.id == "lovelace-network"
    assert net_dash.title == "Network Overview"
    assert "sensor.router_status" in net_dash.relationships["entities"]


def test_collect_dashboards_yaml_mode(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    yaml_content = """
title: Garage Dashboard
views:
  - title: Door Control
    cards:
      - type: button
        entity: cover.garage_door
"""
    (config_dir / "ui-lovelace.yaml").write_text(yaml_content, encoding="utf-8")

    entities = [EntityModel(entity_id="cover.garage_door", name="Garage Door")]

    dashboards, panels, _warns, discovery_err = collect_dashboards(
        client=None,
        config_dir=config_dir,
        entities=entities,
    )

    assert discovery_err is None
    assert len(dashboards) == 1
    assert len(panels) == 1
    dash = dashboards[0]

    assert dash.id == "yaml-ui-lovelace"
    assert dash.title == "Garage Dashboard"
    assert dash.mode == "yaml"
    assert dash.default_dashboard is True
    assert "cover.garage_door" in dash.relationships["entities"]


def test_collect_dashboards_discovery_failure_handling(tmp_path):
    mock_client = MagicMock()
    mock_client.get_panels.side_effect = HomeAssistantClientError("WebSocket connection refused")
    mock_client.get_lovelace_dashboards.side_effect = HomeAssistantClientError(
        "WebSocket connection refused"
    )
    mock_client.get_lovelace_config.side_effect = HomeAssistantClientError(
        "WebSocket connection refused"
    )

    dashboards, _panels, warns, discovery_err = collect_dashboards(
        client=mock_client,
        config_dir=tmp_path,
    )

    assert len(dashboards) == 0
    assert discovery_err is not None
    assert "WebSocket connection refused" in discovery_err
    assert any("WebSocket connection refused" in w for w in warns)


def test_inventory_and_ai_dashboards_exporter(tmp_path):
    output_dir = tmp_path / "staging"
    config_dir = tmp_path / "config"
    output_dir.mkdir()
    config_dir.mkdir()

    card1 = CardModel(
        type="custom:pillar-main-group-card",
        title="Living Room Pillar",
        entities=["light.living_room"],
        navigation_path="/lovelace/living",
        custom_card_name="pillar-main-group-card",
        pillar_component={
            "card_type": "custom:pillar-main-group-card",
            "title": "Living Room Pillar",
            "entities": ["light.living_room"],
            "navigation_path": "/lovelace/living",
        },
    )
    view1 = ViewModel(title="Living Room", path="living", cards=[card1])
    dash1 = DashboardModel(
        id="lovelace-default",
        title="Home",
        url_path=None,
        mode="storage",
        default_dashboard=True,
        views=[view1],
        custom_cards=["pillar-main-group-card"],
        pillar_components=[card1.pillar_component],
        relationships={"entities": ["light.living_room"]},
    )

    entities = [EntityModel(entity_id="light.living_room", name="Living Room Light")]
    devices = []
    areas = []
    labels = []
    integrations = []
    rel_model = RelationshipModel()
    rel_model.dashboard_to_entities["lovelace-default"] = ["light.living_room"]
    rel_model.entity_to_dashboards["light.living_room"] = ["Home"]

    # 1. Export inventory
    export_inventory_json(
        output_dir=output_dir,
        entities=entities,
        devices=devices,
        areas=areas,
        labels=labels,
        integrations=integrations,
        relationships=rel_model,
        dashboards=[dash1],
    )
    export_references_json(output_dir=output_dir, relationships=rel_model)

    dash_inv = output_dir / "inventory" / "dashboards.json"
    assert dash_inv.exists()
    dash_data = json.loads(dash_inv.read_text(encoding="utf-8"))
    assert len(dash_data) == 1
    assert dash_data[0]["id"] == "lovelace-default"
    assert dash_data[0]["stats"]["pillar_component_count"] == 1

    ref_map = output_dir / "references" / "dashboard-entity-map.json"
    assert ref_map.exists()

    # 2. Export AI reference layer
    export_config = MagicMock(dashboards=True, automations=False)
    export_info = {"exporter_version": "0.3.1", "timestamp": "2026-08-14T12:00:00Z"}

    export_ai_reference_layer(
        output_dir=output_dir,
        config_dir=config_dir,
        entities=entities,
        devices=devices,
        areas=areas,
        labels=labels,
        integrations=integrations,
        relationships=rel_model,
        export_config=export_config,
        export_info=export_info,
        warnings=[],
        dashboards=[dash1],
        dash_discovery_error=None,
    )

    ai_dash_dir = output_dir / "ai" / "dashboards"
    assert ai_dash_dir.exists()
    assert (ai_dash_dir / "overview.md").exists()
    assert (ai_dash_dir / "Home.md").exists()

    home_md = (ai_dash_dir / "Home.md").read_text(encoding="utf-8")
    assert "Living Room Pillar" in home_md
    assert "pillar-main-group-card" in home_md

    # Check search index and impact index
    impact_file = output_dir / "ai" / "impact-index.json"
    search_file = output_dir / "ai" / "search-index.json"
    assert impact_file.exists()
    assert search_file.exists()

    impact_data = json.loads(impact_file.read_text(encoding="utf-8"))
    assert "light.living_room" in impact_data["entities"]
    ent_dash_ref = impact_data["entities"]["light.living_room"]["dashboards"]
    assert len(ent_dash_ref) == 1
    assert ent_dash_ref[0]["dashboard_title"] == "Home"
    assert ent_dash_ref[0]["card_type"] == "custom:pillar-main-group-card"

    search_data = json.loads(search_file.read_text(encoding="utf-8"))
    dash_search = [s for s in search_data["records"] if s["type"] == "dashboard"]
    assert len(dash_search) == 1
    assert dash_search[0]["name"] == "Home"


def test_parse_card_additional_layouts():
    raw_card = {
        "type": "grid",
        "title": "Grid Layout",
        "cards": [{"type": "button", "entity": "light.bedroom"}],
        "sections": [
            {
                "title": "Section 1",
                "cards": [{"type": "tile", "entity": "sensor.temp"}],
            }
        ],
        "chips": [{"type": "template", "entity": "sensor.humidity"}],
        "badges": [{"type": "entity", "entity": "binary_sensor.door"}],
        "elements": [{"type": "state-badge", "entity": "light.kitchen"}],
    }

    warns: list[str] = []
    card = parse_card(raw_card, warns)
    assert card.type == "grid"
    assert len(card.nested_cards) >= 5


def test_parse_card_card_field_and_elements():
    raw_card = {
        "type": "conditional",
        "conditions": [{"entity": "binary_sensor.motion", "state": "on"}],
        "card": {
            "type": "picture-elements",
            "image": "/local/floorplan.png",
            "elements": [
                {
                    "type": "state-icon",
                    "entity": "light.living_room",
                    "tap_action": {
                        "action": "navigate",
                        "navigation_path": "/lovelace/living",
                    },
                }
            ],
        },
    }

    warns: list[str] = []
    card = parse_card(raw_card, warns)
    assert card.type == "conditional"
    assert "binary_sensor.motion" in card.entities
    assert len(card.nested_cards) == 1
    sub = card.nested_cards[0]
    assert sub.type == "picture-elements"
    assert len(sub.nested_cards) == 1
    elem = sub.nested_cards[0]
    assert "light.living_room" in elem.entities
    assert elem.navigation_path == "/lovelace/living"


def test_collect_dashboards_custom_dashboards_error(tmp_path):
    mock_client = MagicMock()
    mock_client.get_lovelace_dashboards.return_value = [
        {"id": "broken", "url_path": "broken", "title": "Broken Dash"}
    ]
    mock_client.get_lovelace_config.side_effect = [
        {"title": "Home", "views": []},
        HomeAssistantClientError("Dashboard not found"),
    ]

    dashboards, _panels, warns, discovery_err = collect_dashboards(
        client=mock_client,
        config_dir=tmp_path,
    )

    assert discovery_err is None
    assert len(dashboards) == 1
    assert any("Failed to fetch Lovelace config for 'broken'" in w for w in warns)
