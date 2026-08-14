"""Unit tests for collectors module."""

from unittest.mock import MagicMock

import pytest

from app.collectors.areas import collect_areas
from app.collectors.automations import collect_automations
from app.collectors.configuration import collect_configuration_files
from app.collectors.devices import collect_devices
from app.collectors.entities import collect_entities
from app.collectors.integrations import collect_integrations
from app.collectors.labels import collect_labels
from app.ha_client import HomeAssistantClientError
from app.models.device import DeviceModel
from app.models.entity import EntityModel


def test_collectors_fail_closed_on_api_error():
    mock_client = MagicMock()
    mock_client.get_states.side_effect = HomeAssistantClientError("API connection failed")
    mock_client.get_entity_registry.side_effect = HomeAssistantClientError("API connection failed")
    mock_client.get_device_registry.side_effect = HomeAssistantClientError("API connection failed")
    mock_client.get_area_registry.side_effect = HomeAssistantClientError("API connection failed")

    with pytest.raises(HomeAssistantClientError):
        collect_entities(mock_client)

    with pytest.raises(HomeAssistantClientError):
        collect_devices(mock_client)

    with pytest.raises(HomeAssistantClientError):
        collect_areas(mock_client)


def test_collect_labels_optional_fallback():
    mock_client = MagicMock()
    mock_client.get_label_registry.side_effect = HomeAssistantClientError("Labels unavailable")

    labels = collect_labels(mock_client, required=False)
    assert labels == []

    with pytest.raises(HomeAssistantClientError):
        collect_labels(mock_client, required=True)


def test_collect_configuration_files_edge_cases(tmp_path):
    # Non-existent directory
    missing_path = tmp_path / "does_not_exist"
    files = collect_configuration_files(missing_path)
    assert files == {}

    # Allow custom components and www
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "www").mkdir()
    (config_dir / "www" / "card.yaml").write_text("type: custom\n")
    (config_dir / "custom_components" / "test").mkdir(parents=True)
    (config_dir / "custom_components" / "test" / "sensor.yaml").write_text("platform: test\n")

    files_www = collect_configuration_files(
        config_dir, allow_custom_components=True, allow_www=True
    )
    assert "www/card.yaml" in files_www
    assert "custom_components/test/sensor.yaml" in files_www


def test_entity_area_resolution_hierarchy_and_rich_metadata():
    mock_client = MagicMock()
    mock_client.get_states.return_value = [
        {
            "entity_id": "light.override",
            "attributes": {"friendly_name": "Override Light", "state_class": "measurement"},
        },
        {"entity_id": "sensor.inherited", "attributes": {"friendly_name": "Inherited Sensor"}},
        {"entity_id": "switch.unassigned", "attributes": {"friendly_name": "Unassigned Switch"}},
    ]
    mock_client.get_entity_registry.return_value = [
        {
            "entity_id": "light.override",
            "device_id": "dev1",
            "area_id": "kitchen",
            "platform": "hue",
            "disabled_by": "user",
            "hidden_by": None,
            "device_class": "light",
            "entity_category": "config",
            "config_entry_id": "cfg123",
            "id": "reg_entry_1",
        },
        {
            "entity_id": "sensor.inherited",
            "device_id": "dev1",
            "area_id": None,
            "platform": "hue",
            "disabled_by": None,
            "hidden_by": "integration",
        },
        {
            "entity_id": "switch.unassigned",
            "device_id": None,
            "area_id": None,
            "platform": "demo",
        },
    ]

    devices = [DeviceModel(device_id="dev1", name="Hue Hub", area_id="garage")]
    area_map = {"kitchen": "Kitchen", "garage": "Garage"}

    entities = collect_entities(
        client=mock_client,
        device_name_map={"dev1": "Hue Hub"},
        area_name_map=area_map,
        devices=devices,
    )

    ent_dict = {e.entity_id: e for e in entities}

    # 1. Entity override wins over device area
    e_override = ent_dict["light.override"]
    assert e_override.effective_area_id == "kitchen"
    assert e_override.effective_area_name == "Kitchen"
    assert e_override.area_source == "entity"
    assert e_override.disabled_by == "user"
    assert e_override.device_class == "light"
    assert e_override.state_class == "measurement"

    # 2. Device area inherited when entity area missing
    e_inherited = ent_dict["sensor.inherited"]
    assert e_inherited.effective_area_id == "garage"
    assert e_inherited.effective_area_name == "Garage"
    assert e_inherited.area_source == "device"
    assert e_inherited.hidden_by == "integration"

    # 3. Unassigned when neither entity nor device has area
    e_unassigned = ent_dict["switch.unassigned"]
    assert e_unassigned.effective_area_id == ""
    assert e_unassigned.area_source == "none"


def test_device_multi_platform_integration_domains():
    mock_client = MagicMock()
    mock_client.get_device_registry.return_value = [
        {"id": "dev1", "name": "Multi Sensor", "area_id": "garage", "identifiers": [["zha", "123"]]}
    ]

    entities = [
        EntityModel(entity_id="sensor.temp", device_id="dev1", platform="zha"),
        EntityModel(entity_id="button.reset", device_id="dev1", platform="mqtt"),
    ]

    devices = collect_devices(client=mock_client, entities=entities)
    assert len(devices) == 1
    d = devices[0]
    assert set(d.integration_domains) == {"mqtt", "zha"}


def test_identifier_namespace_alone_does_not_create_integration():
    mock_client = MagicMock()
    mock_client.get_device_registry.return_value = [
        {"id": "dev1", "name": "Unlinked Device", "identifiers": [["zha", "12345"]]}
    ]

    # No entities linked to this device
    devices = collect_devices(client=mock_client, entities=[])
    assert len(devices) == 1
    d = devices[0]
    assert d.integration_domains == []
    assert d.integration == ""
    assert d.identifier_domains == ["zha"]

    # Integrations derived from this device must be empty
    integrations = collect_integrations(mock_client, entities=[], devices=devices)
    assert integrations == []


def test_collect_integrations_derived_from_entities_and_devices():
    mock_client = MagicMock()
    entities = [
        EntityModel(entity_id="light.demo1", name="Demo 1", platform="hue"),
        EntityModel(entity_id="sensor.temp", name="Temp", platform="zha"),
    ]
    devices = [
        DeviceModel(device_id="d1", name="Hue Hub", integration="hue", integration_domains=["hue"]),
        DeviceModel(
            device_id="d2", name="ZHA Plug", integration="zha", integration_domains=["zha", "mqtt"]
        ),
    ]

    integrations = collect_integrations(mock_client, entities=entities, devices=devices)
    domains = [i["domain"] for i in integrations]
    assert "hue" in domains
    assert "mqtt" in domains
    assert "zha" in domains
    assert len(integrations) == 3


def test_collect_automations_and_configuration_files(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    (config_dir / "automations.yaml").write_text(
        "- id: '12345'\n"
        "  alias: 'Turn on lights'\n"
        "  trigger:\n"
        "    - platform: state\n"
        "      entity_id: light.living_room\n"
        "  action:\n"
        "    - service: light.turn_on\n"
        "      target:\n"
        "        entity_id: light.kitchen\n",
        encoding="utf-8",
    )

    (config_dir / "configuration.yaml").write_text(
        "homeassistant:\n  name: Home\n",
        encoding="utf-8",
    )

    auto_map, warnings = collect_automations(config_dir)
    assert "Turn on lights" in auto_map
    assert "light.living_room" in auto_map["Turn on lights"]
    assert "light.kitchen" in auto_map["Turn on lights"]
    assert len(warnings) == 0

    cfg_files = collect_configuration_files(config_dir)
    assert "configuration.yaml" in cfg_files
    assert "automations.yaml" in cfg_files


def test_device_entities_population_sorted_and_deduplicated():
    mock_client = MagicMock()
    mock_client.get_device_registry.return_value = [
        {"id": "dev1", "name": "Multi Entity Device", "area_id": "garage"}
    ]

    entities = [
        EntityModel(entity_id="sensor.temp_z", device_id="dev1", platform="zha"),
        EntityModel(entity_id="sensor.temp_a", device_id="dev1", platform="zha"),
        EntityModel(entity_id="sensor.temp_a", device_id="dev1", platform="zha"),
    ]

    devices = collect_devices(client=mock_client, entities=entities)
    assert len(devices) == 1
    d = devices[0]
    assert d.entities == ["sensor.temp_a", "sensor.temp_z"]


def test_configuration_collector_excludes_translations_and_strings_json(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    (config_dir / "configuration.yaml").write_text(
        "homeassistant:\n  name: Home\n", encoding="utf-8"
    )
    (config_dir / "strings.json").write_text('{"title": "Test"}', encoding="utf-8")

    trans_dir = config_dir / "translations"
    trans_dir.mkdir()
    (trans_dir / "en.json").write_text('{"password": "Password"}', encoding="utf-8")
    (trans_dir / "water.yaml").write_text("name: Water", encoding="utf-8")

    cfg_files = collect_configuration_files(config_dir)
    assert "configuration.yaml" in cfg_files
    assert "strings.json" not in cfg_files
    assert "translations/en.json" not in cfg_files
    assert "translations/water.yaml" not in cfg_files


def test_configuration_collector_excludes_custom_components_unless_enabled(tmp_path):
    config_dir = tmp_path / "config"
    cc_dir = config_dir / "custom_components" / "my_integration"
    cc_dir.mkdir(parents=True)

    (config_dir / "configuration.yaml").write_text(
        "homeassistant:\n  name: Home\n", encoding="utf-8"
    )
    (cc_dir / "sensor.py").write_text("# code", encoding="utf-8")
    (cc_dir / "config.yaml").write_text("name: Custom", encoding="utf-8")

    # Disabled by default
    cfg_disabled = collect_configuration_files(config_dir, allow_custom_components=False)
    assert "configuration.yaml" in cfg_disabled
    assert "custom_components/my_integration/config.yaml" not in cfg_disabled

    # Enabled
    cfg_enabled = collect_configuration_files(config_dir, allow_custom_components=True)
    assert "configuration.yaml" in cfg_enabled
    assert "custom_components/my_integration/config.yaml" in cfg_enabled
