"""Collectors for HA entities, devices, areas, labels, integrations, automations, and config."""

from app.collectors.areas import collect_areas
from app.collectors.automations import collect_automations
from app.collectors.configuration import collect_configuration_files
from app.collectors.dashboards import collect_dashboards
from app.collectors.devices import collect_devices
from app.collectors.entities import collect_entities
from app.collectors.integrations import collect_integrations
from app.collectors.labels import collect_labels

__all__ = [
    "collect_areas",
    "collect_automations",
    "collect_configuration_files",
    "collect_dashboards",
    "collect_devices",
    "collect_entities",
    "collect_integrations",
    "collect_labels",
]
