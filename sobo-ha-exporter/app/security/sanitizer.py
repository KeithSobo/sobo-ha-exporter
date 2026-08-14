"""Data sanitizer for redacting sensitive fields and patterns."""

import re
from dataclasses import dataclass, field
from typing import Any

from app.config import SanitizationConfig
from app.models.area import AreaModel
from app.models.device import DeviceModel
from app.models.entity import EntityModel
from app.models.label import LabelModel

USER_ID_KEYS = {
    "user_id",
    "user_ids",
    "owner_user_id",
    "created_by_user_id",
    "updated_by_user_id",
    "actor_user_id",
}

HEX_32_REGEX = re.compile(r"^[0-9a-fA-F]{32}$")


@dataclass
class SanitizationReport:
    enabled: bool
    warnings_count: int = 0
    categories: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "total_values_redacted": sum(self.categories.values()),
            "categories": self.categories,
        }


class DataSanitizer:
    """Sanitizes dict structures, strings, and configuration output."""

    MAC_REGEX = re.compile(r"\b(?:[0-9A-Fa-f]{2}[:-]){5}(?:[0-9A-Fa-f]{2})\b")
    IP_REGEX = re.compile(
        r"\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b"
    )
    COORD_KEY_REGEX = re.compile(
        r"""(?i)(["']?(?:latitude|longitude|lat|lon)["']?\s*[:=]\s*)[-+]?\d+(?:\.\d+)?"""
    )

    URL_CREDENTIAL_REGEX = re.compile(r"https?://[^:@\s]+:[^:@\s]+@[^\s]+")
    BEARER_TOKEN_REGEX = re.compile(
        r"(?i)(bearer\s+[a-zA-Z0-9\._\-]{20,}|eyJ[a-zA-Z0-9\._\-]{20,})"
    )

    def __init__(self, config: SanitizationConfig):
        self.config = config
        self.stats: dict[str, int] = {
            "coordinates_removed": 0,
            "mac_addresses_removed": 0,
            "ip_addresses_removed": 0,
            "user_ids_removed": 0,
            "webhook_ids_removed": 0,
            "tokens_removed": 0,
            "urls_sanitized": 0,
        }

    def sanitize_entity(self, entity: EntityModel) -> EntityModel:
        """Sanitize fields of an EntityModel instance."""
        if not self.config.enabled:
            return entity
        entity.name = self.sanitize_string(entity.name, "name")
        entity.original_name = self.sanitize_string(entity.original_name, "original_name")
        entity.device_name = self.sanitize_string(entity.device_name, "device_name")
        entity.effective_area_name = self.sanitize_string(
            entity.effective_area_name, "effective_area_name"
        )
        entity.effective_area_id = self.sanitize_string(
            entity.effective_area_id, "effective_area_id"
        )
        entity.unit_of_measurement = self.sanitize_string(
            entity.unit_of_measurement, "unit_of_measurement"
        )
        return entity

    def sanitize_device(self, device: DeviceModel) -> DeviceModel:
        """Sanitize fields of a DeviceModel instance."""
        if not self.config.enabled:
            return device
        device.name = self.sanitize_string(device.name, "name")
        device.area_name = self.sanitize_string(device.area_name, "area_name")
        device.manufacturer = self.sanitize_string(device.manufacturer, "manufacturer")
        device.model = self.sanitize_string(device.model, "model")
        return device

    def sanitize_area(self, area: AreaModel) -> AreaModel:
        """Sanitize fields of an AreaModel instance."""
        if not self.config.enabled:
            return area
        area.name = self.sanitize_string(area.name, "name")
        area.aliases = [self.sanitize_string(a, "alias") for a in area.aliases]
        return area

    def sanitize_label(self, label: LabelModel) -> LabelModel:
        """Sanitize fields of a LabelModel instance."""
        if not self.config.enabled:
            return label
        label.name = self.sanitize_string(label.name, "name")
        label.description = self.sanitize_string(label.description, "description")
        return label

    def sanitize_config_files(self, config_files: dict[str, str]) -> dict[str, str]:
        """Sanitize contents of configuration YAML files dictionary."""
        if not self.config.enabled:
            return config_files
        sanitized = {}
        for path_str, content in config_files.items():
            sanitized[path_str] = self.sanitize_string(content, key_name=path_str)
        return sanitized

    def sanitize_value(self, value: Any, key_name: str = "") -> Any:
        """Recursively sanitize data structure or primitive value."""
        if not self.config.enabled:
            return value

        if isinstance(value, dict):
            sanitized_dict: dict[str, Any] = {}
            for k, v in value.items():
                key_str = str(k).lower()
                if self._should_redact_key(str(k)):
                    sanitized_dict[k] = "[REDACTED]"
                    self.stats["tokens_removed"] += 1
                elif (
                    self.config.remove_coordinates
                    and key_str in ["latitude", "longitude", "lat", "lon"]
                    and isinstance(v, (int, float))
                ):
                    sanitized_dict[k] = 0.0
                    self.stats["coordinates_removed"] += 1
                elif self.config.remove_user_ids and key_str in USER_ID_KEYS:
                    sanitized_dict[k] = self._sanitize_user_id_field(v)
                else:
                    sanitized_dict[k] = self.sanitize_value(v, key_name=str(k))
            return sanitized_dict

        if isinstance(value, list):
            if self.config.remove_user_ids and key_name.lower() in USER_ID_KEYS:
                return [self._sanitize_user_id_field(item) for item in value]
            return [self.sanitize_value(item, key_name=key_name) for item in value]

        if isinstance(value, str):
            if self.config.remove_user_ids and key_name.lower() in USER_ID_KEYS:
                return self._sanitize_user_id_field(value)
            return self.sanitize_string(value, key_name=key_name)

        if isinstance(value, (float, int)) and self.config.remove_coordinates:
            if key_name.lower() in ["latitude", "longitude", "lat", "lon", "elevation"]:
                self.stats["coordinates_removed"] += 1
                return 0.0

        return value

    def _sanitize_user_id_field(self, val: Any) -> Any:
        """Sanitize a value specifically under a user ID key context."""
        if not self.config.remove_user_ids:
            return val

        if isinstance(val, str) and HEX_32_REGEX.match(val):
            self.stats["user_ids_removed"] += 1
            return "[REDACTED_USER_ID]"

        if isinstance(val, list):
            res = []
            for item in val:
                if isinstance(item, str) and HEX_32_REGEX.match(item):
                    self.stats["user_ids_removed"] += 1
                    res.append("[REDACTED_USER_ID]")
                else:
                    res.append(item)
            return res

        return val

    def sanitize_string(self, text: str, key_name: str = "") -> str:
        """Apply regex sanitization to string."""
        if not text:
            return text

        result = text

        if self.config.remove_urls_with_credentials:
            if self.URL_CREDENTIAL_REGEX.search(result):
                result = self.URL_CREDENTIAL_REGEX.sub("https://[REDACTED]@[HOST]", result)
                self.stats["urls_sanitized"] += 1

        if self.config.remove_tokens:
            if self.BEARER_TOKEN_REGEX.search(result):
                result = self.BEARER_TOKEN_REGEX.sub("[REDACTED_TOKEN]", result)
                self.stats["tokens_removed"] += 1

        if self.config.remove_mac_addresses:
            matches = self.MAC_REGEX.findall(result)
            if matches:
                result = self.MAC_REGEX.sub("XX:XX:XX:XX:XX:XX", result)
                self.stats["mac_addresses_removed"] += len(matches)

        if self.config.remove_ip_addresses:
            matches = self.IP_REGEX.findall(result)
            if matches:
                result = self.IP_REGEX.sub("XXX.XXX.XXX.XXX", result)
                self.stats["ip_addresses_removed"] += len(matches)

        if self.config.remove_coordinates:
            if self.COORD_KEY_REGEX.search(result):
                matches = self.COORD_KEY_REGEX.findall(result)
                result = self.COORD_KEY_REGEX.sub(r"\g<1>0.0", result)
                self.stats["coordinates_removed"] += len(matches)

        if self.config.remove_webhook_ids and (
            "webhook" in key_name.lower() or "webhook" in result.lower()
        ):
            if re.search(r"[a-zA-Z0-9_\-]{24,}", result):
                self.stats["webhook_ids_removed"] += 1
                result = "[REDACTED_WEBHOOK_ID]"

        return result

    def _should_redact_key(self, key: str) -> bool:
        """Check if dictionary key represents a sensitive field."""
        k = key.lower()
        sensitive_keywords = [
            "password",
            "api_key",
            "apikey",
            "secret",
            "token",
            "access_token",
            "refresh_token",
            "auth_token",
            "private_key",
            "encryption_key",
        ]
        return any(kw in k for kw in sensitive_keywords)

    @property
    def report(self) -> SanitizationReport:
        """Generate sanitization report summary."""
        return SanitizationReport(enabled=self.config.enabled, categories=self.stats)

    def get_report(self) -> dict[str, Any]:
        """Generate sanitization report dictionary."""
        return self.report.to_dict()
