"""Collector for Home Assistant device models."""

import logging

from app.ha_client import HomeAssistantClient
from app.models.device import DeviceModel
from app.models.entity import EntityModel

logger = logging.getLogger(__name__)


def collect_devices(
    client: HomeAssistantClient,
    area_name_map: dict[str, str] | None = None,
    entities: list[EntityModel] | None = None,
) -> list[DeviceModel]:
    """Collect device records from Home Assistant device registry.

    Required collector: raises HomeAssistantClientError if API call fails.

    Args:
        client: HomeAssistantClient instance.
        area_name_map: Optional mapping of area_id to area name.
        entities: Optional list of EntityModel instances to derive device integration domains.

    Returns:
        List of populated DeviceModel instances.
    """
    logger.info("Collecting device models from Home Assistant...")
    area_map = area_name_map or {}

    # Map device_id to unique entity platforms and associated entity IDs
    dev_platforms: dict[str, set[str]] = {}
    dev_entities: dict[str, set[str]] = {}
    if entities:
        for ent in entities:
            if ent.device_id:
                dev_entities.setdefault(ent.device_id, set()).add(ent.entity_id)
                if ent.platform:
                    dev_platforms.setdefault(ent.device_id, set()).add(ent.platform)

    device_reg = client.get_device_registry()
    devices: list[DeviceModel] = []

    for dev in device_reg:
        device_id = dev.get("id", "")
        if not device_id:
            continue

        name = dev.get("name_by_user") or dev.get("name") or device_id
        area_id = dev.get("area_id") or ""
        area_name = area_map.get(area_id, "")
        manufacturer = dev.get("manufacturer") or ""
        model = dev.get("model") or ""
        labels = dev.get("labels", [])

        # Identifiers and domains
        identifiers = dev.get("identifiers", [])
        identifier_domains: list[str] = []
        for ident in identifiers:
            if isinstance(ident, (list, tuple)) and len(ident) > 0 and ident[0]:
                identifier_domains.append(str(ident[0]))

        integration_domains = sorted(dev_platforms.get(device_id, set()))
        primary_integration = integration_domains[0] if integration_domains else ""
        ent_ids = sorted(dev_entities.get(device_id, set()))

        device = DeviceModel(
            device_id=device_id,
            name=name,
            area_id=area_id,
            area_name=area_name,
            manufacturer=manufacturer,
            model=model,
            integration=primary_integration,
            integration_domains=integration_domains,
            identifier_domains=identifier_domains,
            labels=labels,
            entities=ent_ids,
        )
        devices.append(device)

    logger.info("Collected %d device models.", len(devices))
    return devices
