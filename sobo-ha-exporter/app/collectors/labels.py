"""Collector for Home Assistant label models."""

import logging

from app.ha_client import HomeAssistantClient, HomeAssistantClientError
from app.models.label import LabelModel

logger = logging.getLogger(__name__)


def collect_labels(client: HomeAssistantClient, required: bool = True) -> list[LabelModel]:
    """Collect label records from Home Assistant label registry.

    Args:
        client: HomeAssistantClient instance.
        required: If True, API failures raise HomeAssistantClientError.

    Returns:
        List of populated LabelModel instances.
    """
    logger.info("Collecting label models from Home Assistant...")

    if required:
        label_reg = client.get_label_registry()
    else:
        try:
            label_reg = client.get_label_registry()
        except HomeAssistantClientError as e:
            logger.warning("Optional label collection failed: %s", e)
            return []

    labels: list[LabelModel] = []

    for label_data in label_reg:
        label_id = label_data.get("label_id") or label_data.get("id") or ""
        if not label_id:
            continue

        name = label_data.get("name") or label_id
        description = label_data.get("description") or ""

        label = LabelModel(
            label_id=label_id,
            name=name,
            description=description,
        )
        labels.append(label)

    logger.info("Collected %d label models.", len(labels))
    return labels
