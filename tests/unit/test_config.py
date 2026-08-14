"""Unit tests for app.config module."""

import pytest

from app.config import (
    AppConfig,
    ConfigurationError,
    load_config,
    parse_config_dict,
)


def test_app_config_validation():
    # Valid config
    config = AppConfig(
        repository="git@github.com:KeithSobo/sobo-ha-exporter.git",
        branch="main",
    )
    config.validate()  # Should not raise

    # Empty repo URL
    invalid_config = AppConfig(repository="", branch="main")
    with pytest.raises(ConfigurationError, match="Repository URL is required"):
        invalid_config.validate()

    # Invalid schedule time
    invalid_schedule = AppConfig(
        repository="git@github.com:KeithSobo/sobo-ha-exporter.git",
        branch="main",
    )
    invalid_schedule.schedule.time = "25:00"
    with pytest.raises(ConfigurationError, match="Invalid schedule time format"):
        invalid_schedule.validate()


def test_parse_config_dict():
    data = {
        "repository": "git@github.com:KeithSobo/sobo-ha-exporter.git",
        "branch": "main",
        "schedule": {"enabled": True, "time": "04:30"},
        "export": {"entities": True, "automations": False},
        "sanitization": {"enabled": True, "remove_coordinates": True},
        "git": {"author_name": "Test Bot", "author_email": "bot@example.com"},
    }
    cfg = parse_config_dict(data)
    assert cfg.repository == "git@github.com:KeithSobo/sobo-ha-exporter.git"
    assert cfg.schedule.time == "04:30"
    assert cfg.export.automations is False
    assert cfg.git.author_name == "Test Bot"


def test_load_config_file_not_found(tmp_path):
    missing_file = tmp_path / "non_existent_options.json"
    with pytest.raises(ConfigurationError, match="Options file not found"):
        load_config(missing_file)


def test_load_config_valid_file(tmp_path):
    options_file = tmp_path / "options.json"
    options_file.write_text(
        '{"repository": "git@github.com:KeithSobo/sobo-ha-exporter.git", "branch": "main"}',
        encoding="utf-8",
    )
    cfg = load_config(options_file)
    assert cfg.repository == "git@github.com:KeithSobo/sobo-ha-exporter.git"
