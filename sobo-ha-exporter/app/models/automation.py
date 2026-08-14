"""Automation dataclass model representing Home Assistant automation definitions."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AutomationModel:
    """Dataclass representing a Home Assistant automation definition."""

    id: str
    alias: str
    source_file: str = "automations.yaml"
    source_path: str | None = None
    description: str | None = None
    mode: str = "single"
    enabled: bool = True
    triggers: list[str] = field(default_factory=list)
    conditions: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    devices: list[str] = field(default_factory=list)
    areas: list[str] = field(default_factory=list)
    helpers: list[str] = field(default_factory=list)
    called_services: list[str] = field(default_factory=list)
    called_scripts: list[str] = field(default_factory=list)
    called_scenes: list[str] = field(default_factory=list)
    called_automations: list[str] = field(default_factory=list)
    event_types: list[str] = field(default_factory=list)
    navigation_targets: list[str] = field(default_factory=list)
    unresolved_templates: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    entity_usage_map: dict[str, set[str]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert model instance to deterministic JSON-serializable dictionary."""
        return {
            "id": self.id,
            "alias": self.alias,
            "source_file": self.source_file,
            "source_path": self.source_path,
            "description": self.description,
            "mode": self.mode,
            "enabled": self.enabled,
            "triggers": self.triggers,
            "conditions": self.conditions,
            "actions": self.actions,
            "entities": self.entities,
            "devices": self.devices,
            "areas": self.areas,
            "helpers": self.helpers,
            "called_services": self.called_services,
            "called_scripts": self.called_scripts,
            "called_scenes": self.called_scenes,
            "called_automations": self.called_automations,
            "event_types": self.event_types,
            "navigation_targets": self.navigation_targets,
            "unresolved_templates": self.unresolved_templates,
            "warnings": self.warnings,
            "entity_usage_map": {k: sorted(v) for k, v in sorted(self.entity_usage_map.items())},
        }
