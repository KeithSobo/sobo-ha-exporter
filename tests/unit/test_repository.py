"""Unit tests for RepositoryManager."""

import pytest

from app.github.repository import RepositoryManager, RepositoryManagerError


def test_repository_manager_validation(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()

    mgr = RepositoryManager(repo_dir)
    assert mgr.validate_safe_destination() is True

    (repo_dir / "my_unmanaged_file.py").write_text("hello", encoding="utf-8")
    assert mgr.validate_safe_destination() is False

    mgr.ensure_marker_file()
    assert mgr.validate_safe_destination() is True


def test_repository_manager_sync_and_removes_stale_directories(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    mgr = RepositoryManager(repo_dir)
    mgr.ensure_marker_file()

    # Pre-populate repository with stale config/ and summaries/ directories
    (repo_dir / "config").mkdir()
    (repo_dir / "config" / "old.yaml").write_text("old", encoding="utf-8")
    (repo_dir / "summaries").mkdir()
    (repo_dir / "summaries" / "old.md").write_text("old", encoding="utf-8")
    (repo_dir / "unmanaged_custom_dir").mkdir()

    # Staging has inventory/ but NOT config/ or summaries/
    staging = tmp_path / "staging"
    inv_dir = staging / "inventory"
    inv_dir.mkdir(parents=True)
    (inv_dir / "entities.json").write_text("[]", encoding="utf-8")

    mgr.sync_staged_content(staging)

    # inventory/ must exist in repo
    assert (repo_dir / "inventory" / "entities.json").exists()
    # Stale config/ and summaries/ must be removed
    assert not (repo_dir / "config").exists()
    assert not (repo_dir / "summaries").exists()
    # Unmanaged directory must be untouched (since marker is present)
    assert (repo_dir / "unmanaged_custom_dir").exists()


def test_repository_manager_refuses_unsafe_overwrite(tmp_path):
    repo_dir = tmp_path / "unsafe_repo"
    repo_dir.mkdir()
    (repo_dir / "my_secret_code.py").write_text("print('hello')", encoding="utf-8")

    staging = tmp_path / "staging"
    staging.mkdir()

    mgr = RepositoryManager(repo_dir)
    with pytest.raises(RepositoryManagerError, match="Refusing to overwrite"):
        mgr.sync_staged_content(staging)
