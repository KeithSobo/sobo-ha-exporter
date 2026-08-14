"""Unit tests for configuration_summary, raw_configuration_export, and analyzers."""

import json
import logging
from unittest.mock import MagicMock, patch

from app.analyzers.config_analyzers import (
    analyze_esphome,
    analyze_frigate,
    analyze_zigbee2mqtt,
)
from app.analyzers.config_parser import SafeYamlParser, is_safe_path
from app.config import AppConfig, parse_config_dict
from app.exporters.ai_config_exporter import export_ai_configuration_summary
from app.main import run_export


def test_config_summary_and_raw_defaults():
    config = parse_config_dict({"repository": "git@github.com:KeithSobo/sobo-ha-exporter.git"})
    assert config.export.configuration_summary is True
    assert config.advanced.raw_configuration_export is False


def test_legacy_configuration_files_migration(caplog):
    caplog.set_level(logging.INFO)
    data = {
        "repository": "git@github.com:KeithSobo/sobo-ha-exporter.git",
        "export": {"configuration_files": True},
    }
    config = parse_config_dict(data)

    assert config.export.configuration_summary is True
    assert config.advanced.raw_configuration_export is False
    assert "migrated to configuration_summary" in caplog.text


def test_safe_yaml_parser_secret_reference(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "configuration.yaml").write_text(
        "api_key: !secret my_api_key\n", encoding="utf-8"
    )

    parser = SafeYamlParser(config_dir)
    data, _warns = parser.parse_file("configuration.yaml")

    assert data["api_key"] == "secret reference (my_api_key)"
    assert not (config_dir / "secrets.yaml").exists()


def test_safe_yaml_parser_path_traversal_rejection(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    outside_file = tmp_path / "outside.yaml"
    outside_file.write_text("secret: leak\n", encoding="utf-8")

    assert not is_safe_path(config_dir, outside_file)

    parser = SafeYamlParser(config_dir)
    data, warns = parser.parse_file(outside_file)
    assert data is None
    assert any("path traversal" in w.lower() for w in warns)


def test_esphome_analyzer_never_exposes_real_passwords(tmp_path):
    config_dir = tmp_path / "config"
    esphome_dir = config_dir / "esphome"
    esphome_dir.mkdir(parents=True)

    esphome_yaml = """
esphome:
  name: test-sensor
  friendly_name: Test Sensor

wifi:
  ssid: "MyHomeWiFi"
  password: "REAL_SECRET_WIFI_PASSWORD_12345"

ota:
  password: "REAL_SECRET_OTA_PASSWORD_99999"

api:
  encryption:
    key: "REAL_SECRET_API_KEY_32_BYTES_HEX"
"""
    (esphome_dir / "node1.yaml").write_text(esphome_yaml, encoding="utf-8")

    parser = SafeYamlParser(config_dir)
    summary = analyze_esphome(config_dir, parser)

    nodes = summary["nodes"]
    assert len(nodes) == 1
    node = nodes[0]

    assert node["node_name"] == "test-sensor"
    assert node["wifi_password"] == "configured"
    assert node["ota_password"] == "configured"
    assert node["api_encryption"] == "enabled"

    # Verify real secret strings NEVER appear anywhere in summary structure
    raw_str = json.dumps(summary)
    assert "REAL_SECRET_WIFI_PASSWORD_12345" not in raw_str
    assert "REAL_SECRET_OTA_PASSWORD_99999" not in raw_str
    assert "REAL_SECRET_API_KEY_32_BYTES_HEX" not in raw_str


def test_frigate_and_z2m_analyzers_never_expose_credentials(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    frigate_yaml = """
cameras:
  front_door:
    ffmpeg:
      inputs:
        - path: rtsp://admin:SECRET_RTSP_PASSWORD@192.168.1.50:554/live
          roles:
            - detect
"""
    (config_dir / "frigate.yaml").write_text(frigate_yaml, encoding="utf-8")

    z2m_dir = config_dir / "zigbee2mqtt"
    z2m_dir.mkdir()
    (z2m_dir / "configuration.yaml").write_text(
        "mqtt:\n  password: 'SECRET_Z2M_PASSWORD'\n", encoding="utf-8"
    )

    parser = SafeYamlParser(config_dir)
    frig_sum = analyze_frigate({}, config_dir, parser)
    z2m_sum = analyze_zigbee2mqtt({}, config_dir, parser)

    assert frig_sum["detected"] is True
    assert "front_door" in frig_sum["cameras"]

    raw_frig = json.dumps(frig_sum)
    raw_z2m = json.dumps(z2m_sum)
    assert "SECRET_RTSP_PASSWORD" not in raw_frig
    assert "SECRET_Z2M_PASSWORD" not in raw_z2m


def test_ai_configuration_summary_exporter(tmp_path):
    output_dir = tmp_path / "staging"
    analysis_data = {
        "overview": {"config_dir": str(tmp_path), "files_analyzed_count": 5},
        "home_assistant": {"top_level_domains": ["sensor", "light"]},
        "esphome": {"nodes": []},
        "packages": {"packages": []},
        "automations_scripts_scenes": {"automation_count": 2},
        "dashboards": {"dashboard_count": 1},
        "mqtt": {"detected": False},
        "frigate": {"detected": False},
        "zigbee2mqtt": {"detected": False},
        "custom_components": {"components": []},
        "warnings": [],
    }

    export_ai_configuration_summary(output_dir, analysis_data)

    config_out = output_dir / "ai" / "configuration"
    assert (config_out / "README.md").exists()
    assert (config_out / "overview.md").exists()
    assert (config_out / "home-assistant.md").exists()
    assert (config_out / "esphome.md").exists()
    assert (config_out / "packages.md").exists()
    assert (config_out / "warnings.md").exists()

    content = (config_out / "README.md").read_text(encoding="utf-8")
    assert "NOT A BACKUP" in content


def test_partial_publication_when_raw_export_blocked(tmp_path, monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "test_token")
    data_dir = tmp_path / "data"
    config_dir = tmp_path / "config"
    data_dir.mkdir()
    config_dir.mkdir()
    (data_dir / "repo" / ".git").mkdir(parents=True)

    # Create safe homeassistant config with a leaked token
    secret_str = "ghp_1234567890abcdefghijklmnopqrstuvwxyz"
    (config_dir / "configuration.yaml").write_text(
        f"homeassistant:\n  name: Safe Home\n# leaked password: {secret_str}\n",
        encoding="utf-8",
    )

    config = AppConfig(
        repository="git@github.com:KeithSobo/sobo-ha-exporter.git",
        branch="main",
        export=parse_config_dict(
            {"repository": "git@github.com:KeithSobo/sobo-ha-exporter.git"}
        ).export,
    )
    # Enable raw configuration export which contains a secret
    config.advanced.raw_configuration_export = True

    mock_ha_client = MagicMock()
    mock_ha_client.validate_connection.return_value = True

    mock_git_client = MagicMock()
    mock_git_client.commit_and_push.return_value = (True, "abc1234")

    mock_repo_mgr = MagicMock()
    mock_repo_mgr.validate_safe_destination.return_value = True

    with (
        patch("app.main.ensure_deploy_key") as mock_key,
        patch("app.main.HomeAssistantClient", return_value=mock_ha_client),
        patch("app.main.GitClient", return_value=mock_git_client),
        patch("app.main.RepositoryManager", return_value=mock_repo_mgr),
    ):
        mock_key.return_value = (
            tmp_path / "priv",
            tmp_path / "pub",
            "ssh-ed25519 AAAAKEY",
        )

        res = run_export(config, data_dir=data_dir, config_dir=config_dir)
        # Safe outputs publish cleanly even though raw export was blocked!
        assert res is True

        # Failed export manifest records the blocked finding
        manifest_file = data_dir / "status" / "failed-export-manifest.json"
        assert manifest_file.exists()

        status_file = data_dir / "status" / "status.json"
        status_data = json.loads(status_file.read_text(encoding="utf-8"))
        assert status_data["secret_scan_status"] == "BLOCKED"
