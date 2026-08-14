"""Home Assistant API client abstraction for Supervisor token authentication."""

import json
import logging
import os
from typing import Any

import requests

logger = logging.getLogger(__name__)


class HomeAssistantClientError(Exception):
    """Raised when communication with Home Assistant fails or returns an API error."""

    pass


class HomeAssistantClient:
    """Client for retrieving Home Assistant data via Supervisor API."""

    def __init__(
        self,
        supervisor_token: str | None = None,
        base_url: str = "http://supervisor/core/api",
        timeout: int = 10,
    ):
        token = supervisor_token or os.getenv("SUPERVISOR_TOKEN")
        if not token:
            hassio_token = os.getenv("HASSIO_TOKEN")
            if hassio_token:
                logger.warning(
                    "HASSIO_TOKEN environment variable is deprecated. Please use SUPERVISOR_TOKEN."
                )
                token = hassio_token

        if not token:
            raise HomeAssistantClientError("SUPERVISOR_TOKEN environment variable not available.")

        self.token = token
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            }
        )

    def validate_connection(self) -> bool:
        """Validate authenticated connection to Home Assistant Supervisor API.

        Raises:
            HomeAssistantClientError: If token is invalid, HTTP status is non-200,
                or JSON is malformed.

        Returns:
            True if connection validation succeeded.
        """
        url = f"{self.base_url}/config"
        try:
            resp = self.session.get(url, timeout=self.timeout)
        except Exception as e:
            raise HomeAssistantClientError(
                f"Failed to connect to Home Assistant at {url}: {e}"
            ) from e

        if resp.status_code != 200:
            err_text = resp.text.strip()
            raise HomeAssistantClientError(
                "Home Assistant API connection check failed. "
                f"Endpoint: GET /config, Status: HTTP {resp.status_code}, Reason: {err_text}"
            )

        try:
            data = resp.json()
        except Exception as e:
            raise HomeAssistantClientError(
                f"Invalid JSON received from Home Assistant GET /config: {e}"
            ) from e

        if not isinstance(data, dict):
            raise HomeAssistantClientError(
                "Unexpected response shape from GET /config: "
                f"expected dict, got {type(data).__name__}"
            )

        return True

    def get_config_timezone(self) -> str:
        """Retrieve Home Assistant configured timezone string (e.g. 'America/New_York').

        Optional method: logs warning on failure and returns empty string.

        Returns:
            Timezone name string or empty string if unavailable.
        """
        url = f"{self.base_url}/config"
        try:
            resp = self.session.get(url, timeout=self.timeout)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict):
                    return str(data.get("time_zone") or data.get("timezone") or "")
            logger.warning(
                "GET /config returned status HTTP %s when fetching timezone", resp.status_code
            )
            return ""
        except Exception as e:
            logger.warning("Failed to fetch HA timezone from API: %s", e)
            return ""

    def get_states(self) -> list[dict[str, Any]]:
        """Fetch entity states list from REST API.

        Required method: raises HomeAssistantClientError on failure.

        Returns:
            List of state dictionaries.
        """
        url = f"{self.base_url}/states"
        try:
            resp = self.session.get(url, timeout=self.timeout)
        except Exception as e:
            raise HomeAssistantClientError(
                f"Failed retrieving entity states from {url}: {e}"
            ) from e

        if resp.status_code != 200:
            raise HomeAssistantClientError(
                "Failed retrieving entity states. "
                f"Endpoint: GET /states, Status: HTTP {resp.status_code}"
            )

        try:
            data = resp.json()
        except Exception as e:
            raise HomeAssistantClientError(
                f"Invalid JSON received from Home Assistant GET /states: {e}"
            ) from e

        if not isinstance(data, list):
            raise HomeAssistantClientError(
                "Unexpected response shape from GET /states: "
                f"expected list, got {type(data).__name__}"
            )

        return data

    def get_entity_registry(self) -> list[dict[str, Any]]:
        """Fetch entity registry items via WebSocket. Required method.

        Returns:
            List of registered entity records.
        """
        return self._websocket_command("config/entity_registry/list")

    def get_device_registry(self) -> list[dict[str, Any]]:
        """Fetch device registry items via WebSocket. Required method.

        Returns:
            List of registered device records.
        """
        return self._websocket_command("config/device_registry/list")

    def get_area_registry(self) -> list[dict[str, Any]]:
        """Fetch area registry items via WebSocket. Required method.

        Returns:
            List of registered area records.
        """
        return self._websocket_command("config/area_registry/list")

    def get_label_registry(self) -> list[dict[str, Any]]:
        """Fetch label registry items via WebSocket.

        Raises HomeAssistantClientError if API call fails.

        Returns:
            List of registered label records.
        """
        return self._websocket_command("config/label_registry/list")

    def _websocket_command(self, message_type: str) -> list[dict[str, Any]]:
        """Execute WebSocket command to retrieve registry data.

        Guarantees socket closure and raises HomeAssistantClientError on any failure.

        Args:
            message_type: Command message type (e.g. 'config/entity_registry/list').

        Returns:
            List of result dictionaries.
        """
        ws_url = self.base_url.replace("http://", "ws://").replace("https://", "wss://")
        if ws_url.endswith("/api"):
            ws_url = ws_url[:-4] + "/websocket"
        else:
            ws_url = ws_url + "/websocket"

        try:
            import websocket
        except ImportError as e:
            raise HomeAssistantClientError("websocket-client library is not installed.") from e

        ws = None
        try:
            try:
                ws = websocket.create_connection(ws_url, timeout=self.timeout)
            except Exception as e:
                raise HomeAssistantClientError(
                    f"Failed to establish WebSocket connection to {ws_url}: {e}"
                ) from e

            try:
                auth_msg = json.loads(ws.recv())
            except Exception as e:
                raise HomeAssistantClientError(
                    f"WebSocket error waiting for auth_required message: {e}"
                ) from e

            if auth_msg.get("type") != "auth_required":
                msg_type = auth_msg.get("type")
                raise HomeAssistantClientError(
                    "Unexpected initial WebSocket message type: "
                    f"expected 'auth_required', got '{msg_type}'"
                )

            ws.send(json.dumps({"type": "auth", "access_token": self.token}))

            try:
                auth_resp = json.loads(ws.recv())
            except Exception as e:
                raise HomeAssistantClientError(
                    f"WebSocket error waiting for auth_ok message: {e}"
                ) from e

            if auth_resp.get("type") != "auth_ok":
                msg = auth_resp.get("message", "Authentication rejected by Home Assistant")
                raise HomeAssistantClientError(f"WebSocket authentication failed: {msg}")

            msg_id = 1
            ws.send(json.dumps({"id": msg_id, "type": message_type}))

            try:
                result_msg = json.loads(ws.recv())
            except Exception as e:
                raise HomeAssistantClientError(
                    f"WebSocket error waiting for command '{message_type}' response: {e}"
                ) from e

            if result_msg.get("success") is not True:
                err_info = result_msg.get("error", {})
                code = err_info.get("code", "unknown_error")
                err_text = err_info.get("message", "no message")
                raise HomeAssistantClientError(
                    f"WebSocket command '{message_type}' failed ({code}): {err_text}"
                )

            res = result_msg.get("result")
            if not isinstance(res, list):
                raise HomeAssistantClientError(
                    f"Unexpected response shape for WebSocket command '{message_type}': "
                    f"expected list, got {type(res).__name__}"
                )

            return res

        finally:
            if ws:
                try:
                    ws.close()
                except Exception:
                    pass
