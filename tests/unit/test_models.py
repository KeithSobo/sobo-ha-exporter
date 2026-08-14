"""Unit tests for data models."""

from app.models.area import AreaModel
from app.models.device import DeviceModel
from app.models.entity import EntityModel
from app.models.label import LabelModel
from app.models.relationship import RelationshipModel


def test_entity_model_to_dict():
    entity = EntityModel(
        entity_id="sensor.basement_temperature",
        name="Basement Temperature",
        domain="sensor",
        platform="zha",
        device_id="dev123",
        effective_area_id="basement",
        effective_area_name="Basement",
        area_source="device",
        labels=["env", "temp"],
        disabled_by="user",
        hidden_by=None,
    )
    d = entity.to_dict()
    assert d["entity_id"] == "sensor.basement_temperature"
    assert d["area_id"] == "basement"
    assert d["area_name"] == "Basement"
    assert d["effective_area_id"] == "basement"
    assert d["area_source"] == "device"
    assert d["labels"] == ["env", "temp"]
    assert d["disabled_by"] == "user"
    assert d["hidden_by"] is None
    assert entity.area_id == "basement"
    assert entity.area_name == "Basement"


def test_device_model_to_dict():
    dev = DeviceModel(
        device_id="dev123",
        name="Basement Sensor",
        manufacturer="Third Reality",
        model="3RMS16BZ",
        integration="zha",
        integration_domains=["zha", "mqtt"],
        identifier_domains=["zha"],
        entities=["sensor.basement_temperature"],
    )
    d = dev.to_dict()
    assert d["device_id"] == "dev123"
    assert d["integration_domains"] == ["mqtt", "zha"]
    assert d["entities"] == ["sensor.basement_temperature"]


def test_area_model_to_dict():
    area = AreaModel(area_id="basement", name="Basement", aliases=["cellar"])
    assert area.to_dict()["aliases"] == ["cellar"]


def test_label_model_to_dict():
    label = LabelModel(label_id="env", name="Environment", description="Env Label")
    assert label.to_dict()["description"] == "Env Label"


def test_relationship_model_to_dict():
    rel = RelationshipModel()
    rel.device_to_entities["dev1"] = ["sensor.b", "sensor.a"]
    d = rel.to_dict()
    assert d["device_to_entities"]["dev1"] == ["sensor.a", "sensor.b"]
