"""Unit tests for main execution, status writing, exception handling, and deploy key guard."""

import json
from unittest.mock import MagicMock, patch

import pytest

from app.config import AppConfig
from app.github.deploy_key import DeployKeyError
from app.main import get_ha_timezone, main, run_export, sanitize_error_message, update_status


def test_sanitize_error_message():
    raw_err = (
        "Error reading /data/ssh/id_ed25519 with Bearer "
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9 and https://admin:pass@host/api"
    )
    san = sanitize_error_message(raw_err)
    assert "/data/ssh/id_ed25519" not in san
    assert "[PRIVATE_KEY_PATH]" in san
    assert "pass" not in san
    assert "eyJ" not in san


def test_update_status(tmp_path):
    status_dir = tmp_path / "status"
    update_status(
        status_dir=status_dir,
        status_str="success",
        last_commit="abc1234",
        entities_count=10,
        devices_count=2,
        warnings_count=0,
    )

    status_file = status_dir / "status.json"
    assert status_file.exists()

    data = json.loads(status_file.read_text(encoding="utf-8"))
    assert data["status"] == "success"
    assert data["last_commit"] == "abc1234"
    assert data["entities_exported"] == 10
    assert data["devices_exported"] == 2


def test_pipeline_unexpected_exception_writes_error_status(tmp_path, monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "test_token")
    data_dir = tmp_path / "data"
    config_dir = tmp_path / "config"
    data_dir.mkdir()
    config_dir.mkdir()

    config = AppConfig(
        repository="git@github.com:KeithSobo/sobo-ha-exporter.git",
        branch="main",
    )

    with (
        patch("app.main.ensure_deploy_key") as mock_key,
        patch("app.main.HomeAssistantClient") as mock_client_cls,
        patch(
            "app.main.collect_areas",
            side_effect=RuntimeError("Unexpected collector crash with secret_token_123"),
        ),
    ):
        mock_key.return_value = (
            tmp_path / "priv",
            tmp_path / "pub",
            "ssh-ed25519 AAAAKEY",
        )
        mock_client_cls.return_value.validate_connection.return_value = True

        res = run_export(config, data_dir=data_dir, config_dir=config_dir)
        assert res is False

        status_file = data_dir / "status" / "status.json"
        assert status_file.exists()
        status_data = json.loads(status_file.read_text(encoding="utf-8"))
        assert status_data["status"] == "error"
        assert status_data["status"] != "running"
        assert "Unexpected collector crash" in status_data["message"]


def test_get_ha_timezone_invalid_timezone_string():
    mock_client = MagicMock()
    mock_client.get_config_timezone.return_value = "Invalid/TZ_String"
    _tz_obj, tz_name = get_ha_timezone(client=mock_client)
    assert tz_name == "UTC"


def test_deploy_key_failure_exits_main(tmp_path):
    with (
        patch("app.main.os.getenv") as mock_getenv,
        patch(
            "app.main.ensure_deploy_key",
            side_effect=DeployKeyError("Permission denied on /data/ssh"),
        ),
        patch("app.main.run_export") as mock_export,
    ):
        mock_getenv.side_effect = lambda k, d=None: (
            str(tmp_path) if k in ["DATA_DIR", "CONFIG_DIR"] else d
        )

        with pytest.raises(SystemExit):
            main()

        assert mock_export.call_count == 0
        status_file = tmp_path / "status" / "status.json"
        assert status_file.exists()
        data = json.loads(status_file.read_text(encoding="utf-8"))
        assert data["status"] == "error"
