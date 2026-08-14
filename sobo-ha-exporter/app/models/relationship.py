"""Relationship maps model."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RelationshipModel:
    device_to_entities: dict[str, list[str]] = field(default_factory=dict)
    entity_to_device: dict[str, str] = field(default_factory=dict)
    device_to_area: dict[str, str] = field(default_factory=dict)
    area_to_devices: dict[str, list[str]] = field(default_factory=dict)
    label_to_entities: dict[str, list[str]] = field(default_factory=dict)
    label_to_devices: dict[str, list[str]] = field(default_factory=dict)
    integration_to_devices: dict[str, list[str]] = field(default_factory=dict)
    integration_to_entities: dict[str, list[str]] = field(default_factory=dict)
    automation_to_entities: dict[str, list[str]] = field(default_factory=dict)
    entity_to_automations: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize relationship model with sorted keys and lists."""
        return {
            "device_to_entities": {
                k: sorted(v) for k, v in sorted(self.device_to_entities.items())
            },
            "entity_to_device": dict(sorted(self.entity_to_device.items())),
            "device_to_area": dict(sorted(self.device_to_area.items())),
            "area_to_devices": {k: sorted(v) for k, v in sorted(self.area_to_devices.items())},
            "label_to_entities": {k: sorted(v) for k, v in sorted(self.label_to_entities.items())},
            "label_to_devices": {k: sorted(v) for k, v in sorted(self.label_to_devices.items())},
            "integration_to_devices": {
                k: sorted(v) for k, v in sorted(self.integration_to_devices.items())
            },
            "integration_to_entities": {
                k: sorted(v) for k, v in sorted(self.integration_to_entities.items())
            },
            "automation_to_entities": {
                k: sorted(v) for k, v in sorted(self.automation_to_entities.items())
            },
            "entity_to_automations": {
                k: sorted(v) for k, v in sorted(self.entity_to_automations.items())
            },
        }
