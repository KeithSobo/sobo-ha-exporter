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


def test_automation_model_to_dict():
    from app.models.automation import AutomationModel

    auto = AutomationModel(
        id="auto_test",
        alias="Test Automation",
        entity_usage_map={"light.kitchen": {"action", "trigger"}},
    )
    d = auto.to_dict()
    assert d["id"] == "auto_test"
    assert d["alias"] == "Test Automation"
    assert d["entity_usage_map"]["light.kitchen"] == ["action", "trigger"]


def test_dashboard_model_to_dict():
    from app.models.dashboard import CardModel, DashboardModel, PanelModel, ViewModel

    panel = PanelModel(
        title="Home",
        url_path="lovelace",
        component_name="lovelace",
        panel_type="lovelace_storage",
    )
    assert panel.to_dict()["url_path"] == "lovelace"

    dash = DashboardModel(
        id="dash1",
        title="Main",
        url_path=None,
        icon=None,
        mode="storage",
        warnings=["Template warning"],
        views=[
            ViewModel(
                title="View 1",
                cards=[
                    CardModel(
                        type="vertical-stack",
                        nested_cards=[CardModel(type="button", entities=["light.kitchen"])],
                    )
                ],
            )
        ],
    )
    dd = dash.to_dict()
    assert dd["stats"]["view_count"] == 1
    assert dd["stats"]["card_count"] == 2
    assert dd["stats"]["entity_count"] == 1
    assert dd["stats"]["unresolved_template_count"] == 1
