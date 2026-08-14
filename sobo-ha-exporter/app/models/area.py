"""Normalized Home Assistant Area Model."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AreaModel:
    area_id: str
    name: str = ""
    picture: str = ""
    aliases: list[str] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize area model to dictionary."""
        return {
            "area_id": self.area_id,
            "name": self.name,
            "picture": self.picture,
            "aliases": sorted(self.aliases),
            "labels": sorted(self.labels),
        }
