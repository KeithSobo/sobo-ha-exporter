"""Collector for Home Assistant entity models."""

import logging
from typing import Any

from app.ha_client import HomeAssistantClient
from app.models.device import DeviceModel
from app.models.entity import EntityModel

logger = logging.getLogger(__name__)


def collect_entities(
    client: HomeAssistantClient,
    device_name_map: dict[str, str] | None = None,
    area_name_map: dict[str, str] | None = None,
    devices: list[DeviceModel] | None = None,
) -> list[EntityModel]:
    """Collect entity metadata and state records from Home Assistant API.

    Required collector: raises HomeAssistantClientError if API calls fail.

    Args:
        client: HomeAssistantClient instance.
        device_name_map: Optional mapping of device_id to device name.
        area_name_map: Optional mapping of area_id to area name.
        devices: Optional list of DeviceModel instances to derive device area mapping.

    Returns:
        List of populated EntityModel instances.
    """
    logger.info("Collecting entity models from Home Assistant...")
    dev_name_map = device_name_map or {}
    area_map = area_name_map or {}

    dev_area_map: dict[str, str] = {}
    if devices:
        for d in devices:
            if d.area_id:
                dev_area_map[d.device_id] = d.area_id

    states = client.get_states()
    entity_reg = client.get_entity_registry()

    states_by_id: dict[str, dict[str, Any]] = {
        s.get("entity_id", ""): s for s in states if "entity_id" in s
    }
    reg_by_id: dict[str, dict[str, Any]] = {
        r.get("entity_id", ""): r for r in entity_reg if "entity_id" in r
    }

    all_entity_ids = set(states_by_id.keys()) | set(reg_by_id.keys())
    entities: list[EntityModel] = []

    for entity_id in sorted(all_entity_ids):
        state_data = states_by_id.get(entity_id, {})
        reg_data = reg_by_id.get(entity_id, {})

        domain = entity_id.split(".")[0] if "." in entity_id else ""
        attributes = state_data.get("attributes", {})
        friendly_name = attributes.get("friendly_name", "")

        device_id = reg_data.get("device_id") or ""
        labels = reg_data.get("labels", [])
        platform = reg_data.get("platform") or ""
        original_name = reg_data.get("name") or reg_data.get("original_name") or ""
        unit_of_measurement = attributes.get("unit_of_measurement", "")

        # Area resolution hierarchy
        entity_area_id = reg_data.get("area_id") or ""
        device_area_id = dev_area_map.get(device_id, "")

        if entity_area_id:
            effective_area_id = entity_area_id
            area_source = "entity"
        elif device_area_id:
            effective_area_id = device_area_id
            area_source = "device"
        else:
            effective_area_id = ""
            area_source = "none"

        effective_area_name = area_map.get(effective_area_id, "")
        device_name = dev_name_map.get(device_id, "")

        # Rich metadata fields
        disabled_by = reg_data.get("disabled_by")
        hidden_by = reg_data.get("hidden_by")
        device_class = reg_data.get("device_class") or attributes.get("device_class")
        entity_category = reg_data.get("entity_category")
        config_entry_id = reg_data.get("config_entry_id")
        registry_entry_id = reg_data.get("id")
        state_class = attributes.get("state_class")
        icon = reg_data.get("icon") or attributes.get("icon")
        original_device_class = reg_data.get("original_device_class")
        has_entity_name = reg_data.get("has_entity_name")
        supp_feat = attributes.get("supported_features")
        supported_features = int(supp_feat) if isinstance(supp_feat, (int, float)) else None

        entity = EntityModel(
            entity_id=entity_id,
            domain=domain,
            name=friendly_name or original_name or entity_id,
            device_id=device_id,
            device_name=device_name,
            entity_area_id=entity_area_id,
            device_area_id=device_area_id,
            effective_area_id=effective_area_id,
            effective_area_name=effective_area_name,
            area_source=area_source,
            labels=labels,
            platform=platform,
            original_name=original_name,
            unit_of_measurement=unit_of_measurement,
            disabled_by=disabled_by,
            hidden_by=hidden_by,
            device_class=device_class,
            entity_category=entity_category,
            config_entry_id=config_entry_id,
            registry_entry_id=registry_entry_id,
            state_class=state_class,
            icon=icon,
            original_device_class=original_device_class,
            has_entity_name=has_entity_name,
            supported_features=supported_features,
        )
        entities.append(entity)

    logger.info("Collected %d entity models.", len(entities))
    return entities
