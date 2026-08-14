"""Unit tests for GitClient and branch validation."""

import subprocess
from unittest.mock import patch

import pytest

from app.github.git_client import GitClient, GitClientError, validate_branch_name


def test_validate_branch_name_valid_and_invalid():
    valid_branches = [
        "main",
        "develop",
        "feature/new-card",
        "release/v1.0.0",
    ]
    for b in valid_branches:
        assert validate_branch_name(b) is True

    invalid_branches = [
        "../main",
        "feature..bad",
        "/foo",
        "foo/",
        "foo.lock",
        "foo bar",
        "foo~bar",
        "foo^bar",
        "foo:bar",
        "foo?bar",
        "foo*bar",
        "foo[bar",
    ]
    for b in invalid_branches:
        assert validate_branch_name(b) is False


def test_git_client_init_and_env(tmp_path):
    priv_key = tmp_path / "id_ed25519"
    priv_key.write_text("private", encoding="utf-8")
    known_hosts = tmp_path / "known_hosts"
    known_hosts.write_text("github.com ssh-ed25519 AAAAKEY", encoding="utf-8")

    client = GitClient(
        repo_dir=tmp_path / "repo",
        private_key_path=priv_key,
        known_hosts_path=known_hosts,
    )

    env = client._get_env()
    assert "GIT_SSH_COMMAND" in env
    assert str(priv_key) in env["GIT_SSH_COMMAND"]
    assert str(known_hosts) in env["GIT_SSH_COMMAND"]


def test_git_client_timestamp_only_restoration(tmp_path):
    priv_key = tmp_path / "id_ed25519"
    priv_key.write_text("private", encoding="utf-8")
    client = GitClient(repo_dir=tmp_path, private_key_path=priv_key)

    with (
        patch.object(client, "get_porcelain_status") as mock_status,
        patch.object(client, "restore_file") as mock_restore,
    ):
        mock_status.side_effect = [
            ["M metadata/export-info.json"],
            [],  # Clean after restoration
        ]

        pushed, commit_hash = client.commit_and_push("msg")
        assert pushed is False
        assert commit_hash == "no_changes"
        mock_restore.assert_called_once_with("metadata/export-info.json")


def test_git_client_restore_file_and_test_connection(tmp_path):
    priv_key = tmp_path / "id_ed25519"
    priv_key.write_text("private", encoding="utf-8")
    client = GitClient(repo_dir=tmp_path, private_key_path=priv_key)

    with (
        patch.object(client, "run_git") as mock_run,
        patch.object(client, "run_git_checked") as mock_checked,
    ):
        # restore fails, triggers fallback checkout & reset
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="error"
        )
        client.restore_file("metadata/export-info.json")
        mock_checked.assert_any_call(["checkout", "HEAD", "--", "metadata/export-info.json"])
        mock_checked.assert_any_call(["reset", "HEAD", "metadata/export-info.json"])

    with patch.object(client, "run_git") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )
        assert client.test_connection("git@github.com: KeithSobo/repo.git") is True


def test_commit_and_push_failures_raise_git_client_error(tmp_path):
    priv_key = tmp_path / "id_ed25519"
    priv_key.write_text("private", encoding="utf-8")
    client = GitClient(repo_dir=tmp_path, private_key_path=priv_key)

    with (
        patch.object(client, "get_porcelain_status", return_value=["M inventory/entities.json"]),
        patch.object(client, "run_git_checked") as mock_checked,
    ):
        with patch.object(client, "run_git") as mock_run:
            # diff --cached returns 1 (staged changes exist)
            mock_run.side_effect = [
                subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr=""),
                subprocess.CompletedProcess(args=[], returncode=1, stderr="push rejected"),
                subprocess.CompletedProcess(args=[], returncode=1, stderr="push -u rejected"),
            ]
            mock_checked.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="abc1234"
            )

            with pytest.raises(GitClientError, match="Push to origin/main failed"):
                client.commit_and_push("msg")
