"""Normalized dashboard models for Home Assistant Lovelace dashboards."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CardModel:
    type: str
    subtype: str | None = None
    title: str | None = None
    entities: list[str] = field(default_factory=list)
    navigation_path: str | None = None
    actions: list[dict[str, Any]] = field(default_factory=list)
    services: list[str] = field(default_factory=list)
    templates: list[str] = field(default_factory=list)
    variables: list[str] = field(default_factory=list)
    custom_card_name: str | None = None
    pillar_component: dict[str, Any] | None = None
    nested_cards: list["CardModel"] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert CardModel instance to dictionary."""
        data: dict[str, Any] = {
            "type": self.type,
            "subtype": self.subtype,
            "title": self.title,
            "entities": sorted(set(self.entities)),
            "navigation_path": self.navigation_path,
            "actions": self.actions,
            "services": sorted(set(self.services)),
            "templates": self.templates,
            "variables": self.variables,
            "custom_card_name": self.custom_card_name,
            "pillar_component": self.pillar_component,
            "nested_cards": [c.to_dict() for c in self.nested_cards],
        }
        return data


@dataclass
class ViewModel:
    title: str
    path: str | None = None
    icon: str | None = None
    badges: list[dict[str, Any]] = field(default_factory=list)
    chips: list[dict[str, Any]] = field(default_factory=list)
    sections: list[dict[str, Any]] = field(default_factory=list)
    cards: list[CardModel] = field(default_factory=list)
    visible: Any = None

    def to_dict(self) -> dict[str, Any]:
        """Convert ViewModel instance to dictionary."""
        return {
            "title": self.title,
            "path": self.path,
            "icon": self.icon,
            "badges_count": len(self.badges),
            "chips_count": len(self.chips),
            "sections_count": len(self.sections),
            "cards_count": len(self.cards),
            "cards": [c.to_dict() for c in self.cards],
            "visible": self.visible,
        }


@dataclass
class DashboardModel:
    id: str
    title: str
    url_path: str | None = None
    icon: str | None = None
    mode: str = "storage"  # 'storage' or 'yaml'
    source: str = "websocket"  # 'websocket' or 'yaml'
    require_admin: bool = False
    default_dashboard: bool = False
    views: list[ViewModel] = field(default_factory=list)
    custom_cards: list[str] = field(default_factory=list)
    pillar_components: list[dict[str, Any]] = field(default_factory=list)
    relationships: dict[str, list[str]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert DashboardModel instance to dictionary."""
        all_entities: set[str] = set()
        total_cards = 0

        for v in self.views:

            def _t_cards(cards: list[CardModel]) -> None:
                nonlocal total_cards
                for c in cards:
                    total_cards += 1
                    all_entities.update(c.entities)
                    if c.nested_cards:
                        _t_cards(c.nested_cards)

            _t_cards(v.cards)

        rel = self.relationships or {}
        return {
            "id": self.id,
            "title": self.title,
            "url_path": self.url_path,
            "icon": self.icon,
            "mode": self.mode,
            "source": self.source,
            "require_admin": self.require_admin,
            "default_dashboard": self.default_dashboard,
            "stats": {
                "view_count": len(self.views),
                "card_count": total_cards,
                "custom_card_count": len(self.custom_cards),
                "pillar_component_count": len(self.pillar_components),
                "entity_count": len(all_entities),
                "unresolved_template_count": len(
                    [w for w in self.warnings if "template" in w.lower()]
                ),
            },
            "custom_cards": sorted(set(self.custom_cards)),
            "pillar_components": self.pillar_components,
            "relationships": {
                "entities": sorted(rel.get("entities", [])),
                "devices": sorted(rel.get("devices", [])),
                "areas": sorted(rel.get("areas", [])),
                "labels": sorted(rel.get("labels", [])),
                "automations": sorted(rel.get("automations", [])),
                "scripts": sorted(rel.get("scripts", [])),
            },
            "warnings": self.warnings,
            "views": [v.to_dict() for v in self.views],
        }
