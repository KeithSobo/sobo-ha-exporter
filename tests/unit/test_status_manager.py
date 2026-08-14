"""Unit tests for StatusManager and safe metadata persistence."""

from app.status_manager import StatusManager, sanitize_repo_url


def test_sanitize_repo_url():
    assert (
        sanitize_repo_url("git@github.com:KeithSobo/sobo-ha-exporter.git")
        == "KeithSobo/sobo-ha-exporter"
    )
    assert (
        sanitize_repo_url("https://github.com/KeithSobo/sobo-ha-exporter.git")
        == "KeithSobo/sobo-ha-exporter"
    )
    assert sanitize_repo_url("") == ""


def test_status_manager_updates_status(tmp_path):
    mgr = StatusManager(tmp_path / "status")
    mgr.update_status(
        status_str="success",
        last_commit="abc1234",
        destination_repository="git@github.com:KeithSobo/sobo-ha-exporter.git",
        counts={"entities": 10, "devices": 5},
    )

    data = mgr.get_status()
    assert data["status"] == "success"
    assert data["last_commit"] == "abc1234"
    assert data["destination_repository"] == "KeithSobo/sobo-ha-exporter"
    assert data["counts"]["entities"] == 10


def test_status_manager_write_preview_manifest(tmp_path):
    mgr = StatusManager(tmp_path / "status")
    staging_dir = tmp_path / "staging"
    (staging_dir / "inventory").mkdir(parents=True)
    (staging_dir / "inventory" / "entities.json").write_text("[]", encoding="utf-8")

    prev = mgr.write_preview_manifest(staging_dir, {"inventory": True}, ["warning 1"])
    assert prev["total_files"] == 1
    assert "inventory" in prev["categories"]
    assert mgr.preview_file.exists()


def test_status_manager_failed_manifest_and_clear(tmp_path):
    mgr = StatusManager(tmp_path / "status")
    scan_details = [
        type(
            "Detail",
            (),
            {
                "relative_path": "config/packages/network.yaml",
                "extension": ".yaml",
                "size_bytes": 120,
                "rule_name": "Hardcoded Password Field",
                "line_number": 18,
            },
        )()
    ]

    failed = mgr.write_failed_manifest(scan_details)
    assert failed["total_findings"] == 1
    assert mgr.failed_manifest_file.exists()

    mgr.clear_failed_manifest()
    assert not mgr.failed_manifest_file.exists()
