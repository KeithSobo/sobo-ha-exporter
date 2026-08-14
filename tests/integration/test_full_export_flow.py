"""Local integration tests using a local bare Git repository."""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.config import AppConfig
from app.ha_client import HomeAssistantClientError
from app.main import run_export


def create_local_bare_repo(tmp_path: Path) -> tuple[Path, Path]:
    """Create a local bare Git repository and a clone working dir for testing."""
    bare_repo = tmp_path / "remote.git"
    bare_repo.mkdir()
    subprocess.run(["git", "init", "--bare", str(bare_repo)], check=True, capture_output=True)

    work_tree = tmp_path / "work_tree"
    work_tree.mkdir()
    subprocess.run(["git", "init"], cwd=work_tree, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.name", "Test"], cwd=work_tree, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=work_tree,
        check=True,
        capture_output=True,
    )

    (work_tree / "README.md").write_text("# Reference Export", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=work_tree, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"], cwd=work_tree, check=True, capture_output=True
    )

    subprocess.run(
        ["git", "remote", "add", "origin", str(bare_repo)],
        cwd=work_tree,
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "branch", "-M", "main"], cwd=work_tree, check=True, capture_output=True)
    subprocess.run(
        ["git", "push", "-u", "origin", "main"], cwd=work_tree, check=True, capture_output=True
    )

    return bare_repo, work_tree


def test_full_export_flow_local_area_inheritance_and_relationships(tmp_path):
    bare_repo, _ = create_local_bare_repo(tmp_path)

    data_dir = tmp_path / "data"
    config_dir = tmp_path / "config"
    data_dir.mkdir()
    config_dir.mkdir()

    config = AppConfig(
        repository=str(bare_repo),
        branch="main",
        export=MagicMock(
            entities=True,
            devices=True,
            areas=True,
            labels=True,
            integrations=True,
            relationships=True,
            automations=False,
            configuration_summary=True,
        ),
    )

    mock_ha_client = MagicMock()
    mock_ha_client.get_area_registry.return_value = [
        {"area_id": "garage_area", "name": "Garage"},
        {"area_id": "kitchen_area", "name": "Kitchen"},
    ]
    mock_ha_client.get_device_registry.return_value = [
        {
            "id": "garage_device",
            "name": "Garage Hub",
            "area_id": "garage_area",
            "identifiers": [["zha", "hub1"]],
        }
    ]
    mock_ha_client.get_states.return_value = [
        {"entity_id": "sensor.garage_temp", "attributes": {"friendly_name": "Garage Temp"}},
        {"entity_id": "switch.garage_door", "attributes": {"friendly_name": "Garage Door"}},
        {"entity_id": "light.kitchen_strip", "attributes": {"friendly_name": "Kitchen Strip"}},
    ]
    mock_ha_client.get_entity_registry.return_value = [
        {
            "entity_id": "sensor.garage_temp",
            "device_id": "garage_device",
            "area_id": None,
            "platform": "zha",
        },
        {
            "entity_id": "switch.garage_door",
            "device_id": "garage_device",
            "area_id": None,
            "platform": "zha",
        },
        {
            "entity_id": "light.kitchen_strip",
            "device_id": "garage_device",
            "area_id": "kitchen_area",
            "platform": "zha",
        },
    ]
    mock_ha_client.get_label_registry.return_value = []

    with patch("app.main.HomeAssistantClient", return_value=mock_ha_client):
        success = run_export(config, data_dir=data_dir, config_dir=config_dir)
        assert success is True

        gen_dir = data_dir / "generated" / "inventory"
        assert (gen_dir / "entities.json").exists()
        assert (gen_dir / "devices.json").exists()

        entities_json = json.loads((gen_dir / "entities.json").read_text(encoding="utf-8"))
        ent_by_id = {e["entity_id"]: e for e in entities_json}

        # Verify 2 entities inherited Garage area, 1 entity overridden to Kitchen
        assert ent_by_id["sensor.garage_temp"]["effective_area_id"] == "garage_area"
        assert ent_by_id["sensor.garage_temp"]["area_source"] == "device"

        assert ent_by_id["switch.garage_door"]["effective_area_id"] == "garage_area"
        assert ent_by_id["switch.garage_door"]["area_source"] == "device"

        assert ent_by_id["light.kitchen_strip"]["effective_area_id"] == "kitchen_area"
        assert ent_by_id["light.kitchen_strip"]["area_source"] == "entity"

        devices_json = json.loads((gen_dir / "devices.json").read_text(encoding="utf-8"))
        assert len(devices_json) == 1
        assert "zha" in devices_json[0]["integration_domains"]


def test_api_failure_aborts_export_leaving_repository_untouched(tmp_path):
    bare_repo, _ = create_local_bare_repo(tmp_path)

    data_dir = tmp_path / "data"
    config_dir = tmp_path / "config"
    data_dir.mkdir()
    config_dir.mkdir()

    config = AppConfig(
        repository=str(bare_repo),
        branch="main",
    )

    mock_ha_client = MagicMock()
    mock_ha_client.validate_connection.side_effect = HomeAssistantClientError(
        "HTTP 401 Unauthorized"
    )

    with (
        patch("app.main.HomeAssistantClient", return_value=mock_ha_client),
        patch("app.github.git_client.GitClient.commit_and_push") as mock_push,
    ):
        success = run_export(config, data_dir=data_dir, config_dir=config_dir)
        assert success is False
        assert mock_push.call_count == 0

        status_file = data_dir / "status" / "status.json"
        status_data = json.loads(status_file.read_text(encoding="utf-8"))
        assert status_data["status"] == "error"
        assert "HTTP 401 Unauthorized" in status_data["message"]
