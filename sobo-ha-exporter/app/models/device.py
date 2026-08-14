"""Normalized Home Assistant Device Model."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DeviceModel:
    device_id: str
    name: str = ""
    manufacturer: str = ""
    model: str = ""
    integration: str = ""
    integration_domains: list[str] = field(default_factory=list)
    identifier_domains: list[str] = field(default_factory=list)
    area_id: str = ""
    area_name: str = ""
    labels: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize device model to dictionary."""
        return {
            "device_id": self.device_id,
            "name": self.name,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "integration": self.integration,
            "integration_domains": sorted(set(self.integration_domains)),
            "identifier_domains": sorted(set(self.identifier_domains)),
            "area_id": self.area_id,
            "area_name": self.area_name,
            "labels": sorted(self.labels),
            "entities": sorted(self.entities),
        }
