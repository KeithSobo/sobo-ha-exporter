"""Collector for Home Assistant area models."""

import logging

from app.ha_client import HomeAssistantClient
from app.models.area import AreaModel

logger = logging.getLogger(__name__)


def collect_areas(client: HomeAssistantClient) -> list[AreaModel]:
    """Collect area records from Home Assistant area registry.

    Required collector: raises HomeAssistantClientError if API call fails.

    Args:
        client: HomeAssistantClient instance.

    Returns:
        List of populated AreaModel instances.
    """
    logger.info("Collecting area models from Home Assistant...")

    area_reg = client.get_area_registry()
    areas: list[AreaModel] = []

    for area_data in area_reg:
        area_id = area_data.get("area_id") or area_data.get("id") or ""
        if not area_id:
            continue

        name = area_data.get("name") or area_id
        aliases = area_data.get("aliases", [])

        area = AreaModel(
            area_id=area_id,
            name=name,
            aliases=aliases,
        )
        areas.append(area)

    logger.info("Collected %d area models.", len(areas))
    return areas
