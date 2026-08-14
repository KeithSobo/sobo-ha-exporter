"""Unit tests for HomeAssistantClient (REST and WebSocket)."""

import json
from unittest.mock import MagicMock, patch

import pytest
import requests

from app.ha_client import HomeAssistantClient, HomeAssistantClientError


def test_token_enforcement(monkeypatch):
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    monkeypatch.delenv("HASSIO_TOKEN", raising=False)

    with pytest.raises(
        HomeAssistantClientError, match="SUPERVISOR_TOKEN environment variable not available"
    ):
        HomeAssistantClient()

    client = HomeAssistantClient(supervisor_token="test_token")
    assert client.token == "test_token"

    monkeypatch.setenv("HASSIO_TOKEN", "legacy_token")
    client_legacy = HomeAssistantClient()
    assert client_legacy.token == "legacy_token"


def test_validate_connection_success(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "valid_token")
    client = HomeAssistantClient()

    with patch.object(client.session, "get") as mock_get:
        mock_get.return_value = MagicMock(
            status_code=200, json=lambda: {"time_zone": "America/New_York"}
        )
        assert client.validate_connection() is True
        assert client.get_config_timezone() == "America/New_York"


def test_validate_connection_failures(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "invalid_token")
    client = HomeAssistantClient()

    with patch.object(client.session, "get") as mock_get:
        mock_get.return_value = MagicMock(status_code=401, text="Unauthorized")
        with pytest.raises(HomeAssistantClientError, match="HTTP 401"):
            client.validate_connection()

    with patch.object(client.session, "get") as mock_get:
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.side_effect = json.JSONDecodeError("msg", "doc", 0)
        mock_get.return_value = mock_resp
        with pytest.raises(HomeAssistantClientError, match="Invalid JSON"):
            client.validate_connection()

    with patch.object(client.session, "get") as mock_get:
        mock_resp = MagicMock(status_code=200, json=lambda: ["unexpected_list"])
        mock_get.return_value = mock_resp
        with pytest.raises(HomeAssistantClientError, match="expected dict"):
            client.validate_connection()

    with patch.object(
        client.session, "get", side_effect=requests.RequestException("Connection refused")
    ):
        with pytest.raises(HomeAssistantClientError, match="Failed to connect"):
            client.validate_connection()


def test_get_states_required_method_failures(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "test_token")
    client = HomeAssistantClient()

    with patch.object(client.session, "get") as mock_get:
        mock_get.return_value = MagicMock(status_code=500, text="Internal Error")
        with pytest.raises(HomeAssistantClientError, match="HTTP 500"):
            client.get_states()

    with patch.object(client.session, "get") as mock_get:
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {"error": "wrong shape"})
        with pytest.raises(HomeAssistantClientError, match="expected list"):
            client.get_states()


def test_websocket_command_failures_and_cleanup(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "test_token")
    client = HomeAssistantClient()

    with patch("websocket.create_connection", side_effect=Exception("WS connection refused")):
        with pytest.raises(HomeAssistantClientError, match="Failed to establish WebSocket"):
            client._websocket_command("config/entity_registry/list")

    # WS unexpected initial message type
    mock_ws_bad_type = MagicMock()
    mock_ws_bad_type.recv.return_value = json.dumps({"type": "wrong_type"})
    with patch("websocket.create_connection", return_value=mock_ws_bad_type):
        with pytest.raises(
            HomeAssistantClientError, match="Unexpected initial WebSocket message type"
        ):
            client._websocket_command("config/entity_registry/list")
        mock_ws_bad_type.close.assert_called_once()

    # WS auth failure
    mock_ws = MagicMock()
    mock_ws.recv.side_effect = [
        json.dumps({"type": "auth_required"}),
        json.dumps({"type": "auth_invalid", "message": "Invalid token"}),
    ]
    with patch("websocket.create_connection", return_value=mock_ws):
        with pytest.raises(HomeAssistantClientError, match="WebSocket authentication failed"):
            client._websocket_command("config/entity_registry/list")
        mock_ws.close.assert_called_once()

    # WS success=false response
    mock_ws2 = MagicMock()
    mock_ws2.recv.side_effect = [
        json.dumps({"type": "auth_required"}),
        json.dumps({"type": "auth_ok"}),
        json.dumps(
            {
                "id": 1,
                "success": False,
                "error": {"code": "unauthorized", "message": "Access denied"},
            }
        ),
    ]
    with patch("websocket.create_connection", return_value=mock_ws2):
        with pytest.raises(
            HomeAssistantClientError, match="failed \\(unauthorized\\): Access denied"
        ):
            client._websocket_command("config/entity_registry/list")
        mock_ws2.close.assert_called_once()

    # WS malformed result type (dict instead of list)
    mock_ws3 = MagicMock()
    mock_ws3.recv.side_effect = [
        json.dumps({"type": "auth_required"}),
        json.dumps({"type": "auth_ok"}),
        json.dumps({"id": 1, "success": True, "result": {"not": "a_list"}}),
    ]
    with patch("websocket.create_connection", return_value=mock_ws3):
        with pytest.raises(HomeAssistantClientError, match="expected list"):
            client.get_entity_registry()
        mock_ws3.close.assert_called_once()


def test_get_label_registry_raises_client_error(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "test_token")
    client = HomeAssistantClient()

    with patch.object(
        client,
        "_websocket_command",
        side_effect=HomeAssistantClientError("Label registry unsupported"),
    ):
        with pytest.raises(HomeAssistantClientError, match="Label registry unsupported"):
            client.get_label_registry()


def test_get_registries_and_lovelace(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "test_token")
    client = HomeAssistantClient()

    with patch.object(
        client,
        "_websocket_command",
        return_value=[{"id": "dev1"}],
    ):
        devs = client.get_device_registry()
        areas = client.get_area_registry()
        dashboards = client.get_lovelace_dashboards()
        assert devs == [{"id": "dev1"}]
        assert areas == [{"id": "dev1"}]
        assert dashboards == [{"id": "dev1"}]

    with patch.object(
        client,
        "_websocket_command",
        return_value={"title": "Main Home"},
    ):
        cfg = client.get_lovelace_config(None)
        assert cfg == {"title": "Main Home"}

    with patch.object(
        client,
        "_websocket_command",
        return_value={"lovelace": {"component_name": "lovelace"}},
    ):
        panels = client.get_panels()
        assert panels == {"lovelace": {"component_name": "lovelace"}}

    with patch.object(
        client,
        "_websocket_command",
        return_value="not_a_dict",
    ):
        assert client.get_lovelace_config("custom") == {}
        assert client.get_panels() == {}
