"""Unit tests for app.security.sanitizer and app.security.exclusions."""

from app.config import SanitizationConfig
from app.models.area import AreaModel
from app.models.device import DeviceModel
from app.models.entity import EntityModel
from app.models.label import LabelModel
from app.models.relationship import RelationshipModel
from app.security.exclusions import is_excluded_file
from app.security.sanitizer import DataSanitizer


def test_is_excluded_file():
    assert is_excluded_file("secrets.yaml") is True
    assert is_excluded_file("sub/folder/secrets.yaml") is True
    assert is_excluded_file(".storage/core.entity_registry") is True
    assert is_excluded_file("home-assistant.log") is True
    assert is_excluded_file("home_assistant_v2.db") is True
    assert is_excluded_file("id_ed25519") is True
    assert is_excluded_file("configuration.yaml") is False
    assert is_excluded_file("automations.yaml") is False


def test_context_aware_user_id_redaction():
    config = SanitizationConfig(
        enabled=True,
        remove_user_ids=True,
        remove_ip_addresses=True,
        remove_webhook_ids=True,
    )
    sanitizer = DataSanitizer(config)

    user_id_hex = "a1b2c3d4e5f60718293a4b5c6d7e8f90"
    device_id_hex = "0123456789abcdef0123456789abcdef"
    config_entry_id_hex = "fedcba9876543210fedcba9876543210"

    data = {
        "user_id": user_id_hex,
        "owner_user_id": user_id_hex,
        "user_ids": [user_id_hex, "other_user"],
        "device_id": device_id_hex,
        "config_entry_id": config_entry_id_hex,
        "ip_address": "192.168.1.100",
        "webhook_id": "a_very_long_webhook_identifier_string_1234567890",
        "description": f"Created with ID {user_id_hex}",
    }

    sanitized = sanitizer.sanitize_value(data)

    assert sanitized["user_id"] == "[REDACTED_USER_ID]"
    assert sanitized["owner_user_id"] == "[REDACTED_USER_ID]"
    assert sanitized["user_ids"][0] == "[REDACTED_USER_ID]"

    assert sanitized["device_id"] == device_id_hex
    assert sanitized["config_entry_id"] == config_entry_id_hex
    assert user_id_hex in sanitized["description"]
    assert "192.168.1.100" not in sanitized["ip_address"]
    assert sanitized["webhook_id"] == "[REDACTED_WEBHOOK_ID]"


def test_sanitizer_models():
    config = SanitizationConfig(enabled=True, remove_mac_addresses=True)
    sanitizer = DataSanitizer(config)

    ent = EntityModel(entity_id="light.demo", name="Light AA:BB:CC:DD:EE:FF")
    san_ent = sanitizer.sanitize_entity(ent)
    assert "XX:XX:XX:XX:XX:XX" in san_ent.name

    dev = DeviceModel(device_id="d1", name="Dev AA:BB:CC:DD:EE:FF")
    san_dev = sanitizer.sanitize_device(dev)
    assert "XX:XX:XX:XX:XX:XX" in san_dev.name

    area = AreaModel(area_id="a1", name="Room AA:BB:CC:DD:EE:FF")
    san_area = sanitizer.sanitize_area(area)
    assert "XX:XX:XX:XX:XX:XX" in san_area.name

    label = LabelModel(label_id="l1", name="Lbl AA:BB:CC:DD:EE:FF")
    san_label = sanitizer.sanitize_label(label)
    assert "XX:XX:XX:XX:XX:XX" in san_label.name


def test_relationship_mapping_preserved_after_sanitization():
    config = SanitizationConfig(enabled=True, remove_user_ids=True)
    sanitizer = DataSanitizer(config)

    device_id_hex = "0123456789abcdef0123456789abcdef"
    rel_model = RelationshipModel()
    rel_model.device_to_entities[device_id_hex] = ["light.demo_1", "light.demo_2"]
    rel_model.entity_to_device["light.demo_1"] = device_id_hex

    sanitized_rel = sanitizer.sanitize_value(rel_model.to_dict())

    assert device_id_hex in sanitized_rel["device_to_entities"]
    assert sanitized_rel["entity_to_device"]["light.demo_1"] == device_id_hex


def test_disabled_user_id_sanitization_preserves_values():
    config = SanitizationConfig(enabled=True, remove_user_ids=False)
    sanitizer = DataSanitizer(config)

    user_id_hex = "a1b2c3d4e5f60718293a4b5c6d7e8f90"
    data = {"user_id": user_id_hex, "user_ids": [user_id_hex]}

    sanitized = sanitizer.sanitize_value(data)
    assert sanitized["user_id"] == user_id_hex
    assert sanitized["user_ids"][0] == user_id_hex


def test_coordinate_sanitization_formats():
    config = SanitizationConfig(enabled=True, remove_coordinates=True)
    sanitizer = DataSanitizer(config)

    text_input = (
        "latitude: 41.12345, longitude: -81.98765, "
        "'lat' = 37.77, \"longitude\" = -122.41, version: 1.2"
    )
    sanitized = sanitizer.sanitize_string(text_input)

    assert "41.12345" not in sanitized
    assert "-81.98765" not in sanitized
    assert "-122.41" not in sanitized
    assert "latitude: 0.0" in sanitized
    assert "longitude: 0.0" in sanitized
    assert "version: 1.2" in sanitized
