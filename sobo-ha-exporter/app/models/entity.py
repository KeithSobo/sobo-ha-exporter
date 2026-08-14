"""Normalized Home Assistant Entity Model."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class EntityModel:
    entity_id: str
    domain: str = ""
    name: str = ""
    device_id: str = ""
    device_name: str = ""
    labels: list[str] = field(default_factory=list)
    platform: str = ""
    original_name: str = ""
    unit_of_measurement: str = ""

    # Area resolution hierarchy fields
    entity_area_id: str = ""
    device_area_id: str = ""
    effective_area_id: str = ""
    effective_area_name: str = ""
    area_source: str = "none"  # "entity", "device", or "none"

    # Rich metadata fields
    disabled_by: str | None = None
    hidden_by: str | None = None
    device_class: str | None = None
    entity_category: str | None = None
    config_entry_id: str | None = None
    registry_entry_id: str | None = None
    state_class: str | None = None
    icon: str | None = None
    original_device_class: str | None = None
    has_entity_name: bool | None = None
    supported_features: int | None = None

    @property
    def area_id(self) -> str:
        """Backward-compatible property for resolved area ID."""
        return self.effective_area_id

    @property
    def area_name(self) -> str:
        """Backward-compatible property for resolved area name."""
        return self.effective_area_name

    def to_dict(self) -> dict[str, Any]:
        """Serialize entity model to dictionary."""
        return {
            "entity_id": self.entity_id,
            "domain": self.domain,
            "name": self.name,
            "device_id": self.device_id,
            "device_name": self.device_name,
            "area_id": self.effective_area_id,
            "area_name": self.effective_area_name,
            "entity_area_id": self.entity_area_id,
            "device_area_id": self.device_area_id,
            "effective_area_id": self.effective_area_id,
            "effective_area_name": self.effective_area_name,
            "area_source": self.area_source,
            "labels": sorted(self.labels),
            "platform": self.platform,
            "original_name": self.original_name,
            "unit_of_measurement": self.unit_of_measurement,
            "disabled_by": self.disabled_by,
            "hidden_by": self.hidden_by,
            "device_class": self.device_class,
            "entity_category": self.entity_category,
            "config_entry_id": self.config_entry_id,
            "registry_entry_id": self.registry_entry_id,
            "state_class": self.state_class,
            "icon": self.icon,
            "original_device_class": self.original_device_class,
            "has_entity_name": self.has_entity_name,
            "supported_features": self.supported_features,
        }
