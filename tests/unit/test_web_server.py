"""Unit tests for Ingress WebServer and API endpoints."""

import json
import threading
import urllib.request
from unittest.mock import MagicMock

import pytest

from app.status_manager import StatusManager
from app.web_server import WebServer


@pytest.fixture
def test_server(tmp_path):
    data_dir = tmp_path / "data"
    status_dir = data_dir / "status"
    data_dir.mkdir(parents=True)
    status_dir.mkdir(parents=True)

    ssh_dir = data_dir / "ssh"
    ssh_dir.mkdir(parents=True)
    (ssh_dir / "id_ed25519.pub").write_text("ssh-ed25519 AAAATESTKEY", encoding="utf-8")
    (ssh_dir / "id_ed25519").write_text("PRIVATE_KEY_MATERIAL", encoding="utf-8")

    status_mgr = StatusManager(status_dir)
    status_mgr.update_status(
        status_str="success", destination_repository="KeithSobo/sobo-ha-exporter"
    )

    export_lock = threading.Lock()
    mock_run_export = MagicMock(return_value=True)
    mock_test_git = MagicMock(return_value={"success": True, "message": "Connected"})

    server = WebServer(
        host="127.0.0.1",
        port=8099,
        status_mgr=status_mgr,
        data_dir=data_dir,
        export_lock=export_lock,
        run_export_fn=mock_run_export,
        test_git_fn=mock_test_git,
    )
    server.start()
    yield server, status_mgr, data_dir, export_lock, mock_run_export, mock_test_git
    server.stop()


def test_web_server_get_index_and_static_files(test_server):
    url = "http://127.0.0.1:8099/"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        content = resp.read().decode("utf-8")
        assert "Sobo HA Exporter" in content

    url_css = "http://127.0.0.1:8099/style.css"
    with urllib.request.urlopen(url_css) as resp:
        assert resp.status == 200
        assert "var(--primary-color)" in resp.read().decode("utf-8")


def test_web_server_api_status_endpoint(test_server):
    url = "http://127.0.0.1:8099/api/status"
    with urllib.request.urlopen(url) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert data["status"] == "success"
        assert data["destination_repository"] == "KeithSobo/sobo-ha-exporter"


def test_web_server_api_setup_endpoint_never_exposes_private_key(test_server):
    url = "http://127.0.0.1:8099/api/setup"
    with urllib.request.urlopen(url) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert "ssh-ed25519 AAAATESTKEY" in data["public_key"]
        # Ensure private key is NOT in data
        raw_json = json.dumps(data)
        assert "PRIVATE_KEY_MATERIAL" not in raw_json


def test_web_server_manual_export_trigger_and_concurrency_lock(test_server):
    _server, _mgr, _data_dir, lock, _mock_export, _test_git = test_server
    url = "http://127.0.0.1:8099/api/run-export"
    req = urllib.request.Request(url, method="POST", data=b"{}")

    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert data["success"] is True

    # Test lock concurrency rejection
    lock.acquire()
    try:
        req2 = urllib.request.Request(url, method="POST", data=b"{}")
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(req2)
        assert exc_info.value.code == 409
    finally:
        lock.release()


def test_web_server_test_git_endpoint(test_server):
    url = "http://127.0.0.1:8099/api/test-git"
    req = urllib.request.Request(url, method="POST", data=b"{}")
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert data["success"] is True
        assert "Connected" in data["message"]


def test_web_server_ingress_prefixed_path_handling(test_server):
    prefix = "/api/hassio_ingress/abc123token"
    url = f"http://127.0.0.1:8099{prefix}/api/status"
    req = urllib.request.Request(url, headers={"X-Ingress-Path": prefix})
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert data["status"] == "success"


def test_web_server_rejects_path_traversal(test_server):
    url = "http://127.0.0.1:8099/../../etc/passwd"
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(url)
    assert exc_info.value.code in [400, 404]
