"""Unit tests for export integrity validator."""

import pytest

from app.models.area import AreaModel
from app.models.device import DeviceModel
from app.models.entity import EntityModel
from app.models.label import LabelModel
from app.security.validator import IntegrityValidationError, validate_export_integrity


def test_validate_export_integrity_success():
    areas = [AreaModel(area_id="living_room", name="Living Room")]
    devices = [DeviceModel(device_id="dev1", name="Smart Plug", area_id="living_room")]
    entities = [
        EntityModel(
            entity_id="switch.plug",
            device_id="dev1",
            effective_area_id="living_room",
            area_source="device",
        )
    ]
    labels = [LabelModel(label_id="l1", name="Important")]

    validate_export_integrity(entities, devices, areas, labels)


def test_validate_export_integrity_duplicate_ids():
    areas = [AreaModel(area_id="room1"), AreaModel(area_id="room1")]
    with pytest.raises(IntegrityValidationError, match="Duplicate area ID"):
        validate_export_integrity([], [], areas, [])

    devices = [DeviceModel(device_id="dev1"), DeviceModel(device_id="dev1")]
    with pytest.raises(IntegrityValidationError, match="Duplicate device ID"):
        validate_export_integrity([], devices, [], [])

    entities = [EntityModel(entity_id="e1"), EntityModel(entity_id="e1")]
    with pytest.raises(IntegrityValidationError, match="Duplicate entity ID"):
        validate_export_integrity(entities, [], [], [])

    labels = [LabelModel(label_id="l1"), LabelModel(label_id="l1")]
    with pytest.raises(IntegrityValidationError, match="Duplicate label ID"):
        validate_export_integrity([], [], [], labels)

    reg_entities = [
        EntityModel(entity_id="e1", registry_entry_id="reg1"),
        EntityModel(entity_id="e2", registry_entry_id="reg1"),
    ]
    with pytest.raises(IntegrityValidationError, match="Duplicate registry entry ID"):
        validate_export_integrity(reg_entities, [], [], [])


def test_validate_export_integrity_dangling_references():
    areas = [AreaModel(area_id="room1")]
    devices = [DeviceModel(device_id="dev1", area_id="room1")]

    # Entity referencing non-existent device ID
    dangling_dev_entities = [EntityModel(entity_id="e1", device_id="non_existent_dev")]
    with pytest.raises(IntegrityValidationError, match="references unknown device ID"):
        validate_export_integrity(dangling_dev_entities, devices, areas, [])

    # Entity referencing non-existent area ID
    dangling_area_entities = [EntityModel(entity_id="e1", effective_area_id="non_existent_area")]
    with pytest.raises(IntegrityValidationError, match="references unknown area ID"):
        validate_export_integrity(dangling_area_entities, devices, areas, [])

    # Entity referencing non-existent label ID
    labels = [LabelModel(label_id="l1")]
    dangling_lbl_entities = [EntityModel(entity_id="e1", labels=["unknown_lbl"])]
    with pytest.raises(IntegrityValidationError, match="references unknown label ID"):
        validate_export_integrity(dangling_lbl_entities, [], [], labels)
