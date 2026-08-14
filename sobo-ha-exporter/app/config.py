"""Configuration parser and validator for Sobo HA Exporter."""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class ConfigurationError(Exception):
    """Raised when configuration validation fails."""

    pass


# Strict GitHub SSH URL regex patterns
# Matches git@github.com:owner/repo.git or ssh://git@github.com/owner/repo.git
GITHUB_SSH_REGEX = re.compile(
    r"^(?:git@github\.com:([a-zA-Z0-9_\-]+)/([a-zA-Z0-9_\-\.]+?)(?:\.git)?|"
    r"ssh://git@github\.com/([a-zA-Z0-9_\-]+)/([a-zA-Z0-9_\-\.]+?)(?:\.git)?)$"
)

# Safe Git branch name regex (alphanumeric, underscore, hyphen, dot, slash)
SAFE_BRANCH_REGEX = re.compile(r"^[a-zA-Z0-9_\-\./]+$")


@dataclass
class ScheduleConfig:
    enabled: bool = True
    time: str = "03:00"


@dataclass
class ExportConfig:
    entities: bool = True
    devices: bool = True
    areas: bool = True
    labels: bool = True
    integrations: bool = True
    relationships: bool = True
    automations: bool = True
    configuration_files: bool = False
    dashboards: bool = False
    custom_components: bool = False
    www: bool = False


@dataclass
class SanitizationConfig:
    enabled: bool = True
    remove_coordinates: bool = True
    remove_ip_addresses: bool = False
    remove_mac_addresses: bool = True
    remove_user_ids: bool = True
    remove_webhook_ids: bool = True
    remove_tokens: bool = True
    remove_urls_with_credentials: bool = True


@dataclass
class GitConfig:
    author_name: str = "Sobo HA Exporter"
    author_email: str = "sobo-ha-exporter@localhost"
    commit_message: str = "Update Home Assistant reference export"


@dataclass
class AppConfig:
    repository: str = ""
    branch: str = "main"
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)
    export: ExportConfig = field(default_factory=ExportConfig)
    sanitization: SanitizationConfig = field(default_factory=SanitizationConfig)
    git: GitConfig = field(default_factory=GitConfig)

    def validate(self) -> None:
        """Validate configuration settings.

        Raises:
            ConfigurationError: If any configuration value is invalid.
        """
        if not self.repository:
            raise ConfigurationError("Repository URL is required and cannot be empty.")

        # Reject unencrypted or non-SSH protocols
        if (
            self.repository.startswith("git://")
            or self.repository.startswith("http://")
            or self.repository.startswith("https://")
        ):
            raise ConfigurationError(
                f"Invalid repository protocol in '{self.repository}'. "
                "Only GitHub SSH URLs are supported (e.g., git@github.com:OWNER/REPO.git)."
            )

        match = GITHUB_SSH_REGEX.match(self.repository)
        if not match:
            raise ConfigurationError(
                f"Invalid GitHub SSH repository URL: '{self.repository}'. "
                "URL must follow the format 'git@github.com:OWNER/REPO.git' or 'ssh://git@github.com/OWNER/REPO.git'."
            )

        owner = match.group(1) or match.group(3)
        repo = match.group(2) or match.group(4)
        if not owner or not repo:
            raise ConfigurationError(
                f"Malformed GitHub SSH URL '{self.repository}': "
                "owner and repository must not be empty."
            )

        if not self.branch:
            raise ConfigurationError("Git branch cannot be empty.")

        from app.github.git_client import validate_branch_name

        if not validate_branch_name(self.branch):
            raise ConfigurationError(
                f"Unsafe or invalid Git branch name '{self.branch}'. "
                "Branch ref format must be valid according to git check-ref-format."
            )

        if self.schedule.enabled and self.schedule.time:
            if not re.match(r"^(?:[01]\d|2[0-3]):[0-5]\d$", self.schedule.time):
                raise ConfigurationError(
                    f"Invalid schedule time format: '{self.schedule.time}'. Expected HH:MM format."
                )


def load_config(options_path: Path | str = "/data/options.json") -> AppConfig:
    """Load and parse application configuration from JSON options file.

    Args:
        options_path: Path to options.json.

    Returns:
        Validated AppConfig instance.
    """
    path = Path(options_path)
    if not path.exists():
        raise ConfigurationError(f"Options file not found at {path}")

    try:
        with open(path, encoding="utf-8") as f:
            data: dict[str, Any] = json.load(f)
    except Exception as e:
        raise ConfigurationError(f"Failed to read options file at {path}: {e}") from e

    return parse_config_dict(data)


def parse_config_dict(data: dict[str, Any]) -> AppConfig:
    """Parse dictionary into AppConfig with validation.

    Args:
        data: Dictionary of options.

    Returns:
        Validated AppConfig.
    """
    repo = str(data.get("repository", "")).strip()
    branch = str(data.get("branch", "main")).strip()

    sched_raw = data.get("schedule", {})
    sched = ScheduleConfig(
        enabled=bool(sched_raw.get("enabled", True)),
        time=str(sched_raw.get("time", "03:00")),
    )

    exp_raw = data.get("export", {})
    exp = ExportConfig(
        entities=bool(exp_raw.get("entities", True)),
        devices=bool(exp_raw.get("devices", True)),
        areas=bool(exp_raw.get("areas", True)),
        labels=bool(exp_raw.get("labels", True)),
        integrations=bool(exp_raw.get("integrations", True)),
        relationships=bool(exp_raw.get("relationships", True)),
        automations=bool(exp_raw.get("automations", True)),
        configuration_files=bool(exp_raw.get("configuration_files", False)),
        dashboards=bool(exp_raw.get("dashboards", False)),
        custom_components=bool(exp_raw.get("custom_components", False)),
        www=bool(exp_raw.get("www", False)),
    )

    san_raw = data.get("sanitization", {})
    san = SanitizationConfig(
        enabled=bool(san_raw.get("enabled", True)),
        remove_coordinates=bool(san_raw.get("remove_coordinates", True)),
        remove_ip_addresses=bool(san_raw.get("remove_ip_addresses", False)),
        remove_mac_addresses=bool(san_raw.get("remove_mac_addresses", True)),
        remove_user_ids=bool(san_raw.get("remove_user_ids", True)),
        remove_webhook_ids=bool(san_raw.get("remove_webhook_ids", True)),
        remove_tokens=bool(san_raw.get("remove_tokens", True)),
        remove_urls_with_credentials=bool(san_raw.get("remove_urls_with_credentials", True)),
    )

    git_raw = data.get("git", {})
    git_cfg = GitConfig(
        author_name=str(git_raw.get("author_name", "Sobo HA Exporter")),
        author_email=str(git_raw.get("author_email", "sobo-ha-exporter@localhost")),
        commit_message=str(git_raw.get("commit_message", "Update Home Assistant reference export")),
    )

    config = AppConfig(
        repository=repo,
        branch=branch,
        schedule=sched,
        export=exp,
        sanitization=san,
        git=git_cfg,
    )
    config.validate()
    return config
