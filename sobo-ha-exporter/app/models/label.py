"""Normalized Home Assistant Label Model."""

from dataclasses import dataclass
from typing import Any


@dataclass
class LabelModel:
    label_id: str
    name: str = ""
    icon: str = ""
    color: str = ""
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize label model to dictionary."""
        return {
            "label_id": self.label_id,
            "name": self.name,
            "icon": self.icon,
            "color": self.color,
            "description": self.description,
        }
