"""Unit tests for GitHub SSH repository URL and branch validation."""

import pytest

from app.config import AppConfig, ConfigurationError, parse_config_dict


def test_valid_github_ssh_urls():
    valid_urls = [
        "git@github.com:KeithSobo/sobo-ha-exporter.git",
        "git@github.com:my-org/my-repo",
        "ssh://git@github.com/KeithSobo/sobo-ha-exporter.git",
        "ssh://git@github.com/my-org/my-repo",
    ]
    for url in valid_urls:
        cfg = AppConfig(repository=url, branch="main")
        cfg.validate()  # Should not raise


def test_invalid_repository_urls():
    invalid_urls = [
        "git://github.com/KeithSobo/sobo-ha-exporter.git",
        "https://github.com/KeithSobo/sobo-ha-exporter.git",
        "http://github.com/KeithSobo/sobo-ha-exporter.git",
        "git@gitlab.com:KeithSobo/sobo-ha-exporter.git",
        "git@bitbucket.org:KeithSobo/sobo-ha-exporter.git",
        "git@github.com:",
        "git@github.com:/repo.git",
        "git@github.com:owner/",
        "ssh://git@github.com/",
        "",
    ]
    for url in invalid_urls:
        cfg = AppConfig(repository=url, branch="main")
        with pytest.raises(ConfigurationError):
            cfg.validate()


def test_unsafe_branch_names():
    unsafe_branches = [
        "main; rm -rf /",
        "main && echo hack",
        "../main",
        "main space",
        "main\nnewline",
        "",
    ]
    for branch in unsafe_branches:
        data = {
            "repository": "git@github.com:KeithSobo/sobo-ha-exporter.git",
            "branch": branch,
        }
        with pytest.raises(ConfigurationError):
            parse_config_dict(data)
