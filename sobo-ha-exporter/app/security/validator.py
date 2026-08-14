"""Export integrity and relationship graph validator."""

import logging

from app.models.area import AreaModel
from app.models.device import DeviceModel
from app.models.entity import EntityModel
from app.models.label import LabelModel

logger = logging.getLogger(__name__)


class IntegrityValidationError(Exception):
    """Raised when exported models fail relationship or uniqueness validation."""

    pass


def validate_export_integrity(
    entities: list[EntityModel],
    devices: list[DeviceModel],
    areas: list[AreaModel],
    labels: list[LabelModel] | None = None,
) -> None:
    """Validate export models for duplicate identifiers and dangling references.

    Args:
        entities: List of collected EntityModel instances.
        devices: List of collected DeviceModel instances.
        areas: List of collected AreaModel instances.
        labels: Optional list of collected LabelModel instances.

    Raises:
        IntegrityValidationError: If duplicate IDs or dangling references exist.
    """
    logger.info("Validating export relationship integrity...")

    # 1. Uniqueness checks
    entity_ids: set[str] = set()
    for ent in entities:
        if ent.entity_id in entity_ids:
            raise IntegrityValidationError(f"Duplicate entity ID found: '{ent.entity_id}'")
        entity_ids.add(ent.entity_id)

    device_ids: set[str] = set()
    for dev in devices:
        if dev.device_id in device_ids:
            raise IntegrityValidationError(f"Duplicate device ID found: '{dev.device_id}'")
        device_ids.add(dev.device_id)

    area_ids: set[str] = set()
    for ar in areas:
        if ar.area_id in area_ids:
            raise IntegrityValidationError(f"Duplicate area ID found: '{ar.area_id}'")
        area_ids.add(ar.area_id)

    label_ids: set[str] = set()
    if labels:
        for lbl in labels:
            if lbl.label_id in label_ids:
                raise IntegrityValidationError(f"Duplicate label ID found: '{lbl.label_id}'")
            label_ids.add(lbl.label_id)

    reg_entry_ids: set[str] = set()
    for ent in entities:
        if ent.registry_entry_id:
            if ent.registry_entry_id in reg_entry_ids:
                raise IntegrityValidationError(
                    f"Duplicate registry entry ID found: '{ent.registry_entry_id}'"
                )
            reg_entry_ids.add(ent.registry_entry_id)

    # 2. Dangling reference checks
    for ent in entities:
        if ent.device_id and device_ids and ent.device_id not in device_ids:
            raise IntegrityValidationError(
                f"Entity '{ent.entity_id}' references unknown device ID '{ent.device_id}'"
            )
        if ent.effective_area_id and area_ids and ent.effective_area_id not in area_ids:
            raise IntegrityValidationError(
                f"Entity '{ent.entity_id}' references unknown area ID '{ent.effective_area_id}'"
            )
        if labels and label_ids:
            for lbl_ref in ent.labels:
                if lbl_ref not in label_ids:
                    raise IntegrityValidationError(
                        f"Entity '{ent.entity_id}' references unknown label ID '{lbl_ref}'"
                    )

    for dev in devices:
        if dev.area_id and area_ids and dev.area_id not in area_ids:
            raise IntegrityValidationError(
                f"Device '{dev.device_id}' references unknown area ID '{dev.area_id}'"
            )
        if labels and label_ids:
            for lbl_ref in dev.labels:
                if lbl_ref not in label_ids:
                    raise IntegrityValidationError(
                        f"Device '{dev.device_id}' references unknown label ID '{lbl_ref}'"
                    )

    logger.info("Export relationship integrity validation passed cleanly.")
