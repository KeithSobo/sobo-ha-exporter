"""Collector for active integrations derived from entities and devices."""

import logging
from typing import Any

from app.ha_client import HomeAssistantClient
from app.models.device import DeviceModel
from app.models.entity import EntityModel

logger = logging.getLogger(__name__)


def collect_integrations(
    client: HomeAssistantClient,
    entities: list[EntityModel] | None = None,
    devices: list[DeviceModel] | None = None,
) -> list[dict[str, Any]]:
    """Derive list of active integration records from collected entities and devices.

    Derives integrations deterministically using supported registry information
    (Entity.platform and Device.integration_domains) without guessing.

    Args:
        client: HomeAssistantClient instance.
        entities: Optional list of previously collected EntityModel instances.
        devices: Optional list of previously collected DeviceModel instances.

    Returns:
        List of integration record dictionaries.
    """
    logger.info("Deriving integration models from collected entities and devices...")

    domains: set[str] = set()

    if entities:
        for ent in entities:
            if ent.platform and ent.platform.strip():
                domains.add(ent.platform.strip())

    if devices:
        for dev in devices:
            for d in dev.integration_domains:
                if d and d.strip():
                    domains.add(d.strip())

    integrations: list[dict[str, Any]] = []
    for domain in sorted(domains):
        ent_count = sum(1 for e in (entities or []) if e.platform == domain)
        dev_count = sum(
            1 for d in (devices or []) if d.integration == domain or domain in d.integration_domains
        )
        integrations.append(
            {
                "domain": domain,
                "name": domain.replace("_", " ").title(),
                "entity_count": ent_count,
                "device_count": dev_count,
            }
        )

    return integrations
