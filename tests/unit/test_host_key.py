"""Unit tests for GitHub host key verification."""

from app.github.host_key import PINNED_GITHUB_HOST_KEY, ensure_pinned_known_hosts


def test_ensure_pinned_known_hosts_creates_file(tmp_path):
    known_hosts = tmp_path / "known_hosts"
    assert not known_hosts.exists()

    ensure_pinned_known_hosts(known_hosts)
    assert known_hosts.exists()
    content = known_hosts.read_text(encoding="utf-8")
    assert PINNED_GITHUB_HOST_KEY in content


def test_ensure_pinned_known_hosts_restores_corrupted_file(tmp_path):
    known_hosts = tmp_path / "known_hosts"
    known_hosts.write_text("invalid_untrusted_host_key", encoding="utf-8")

    ensure_pinned_known_hosts(known_hosts)
    content = known_hosts.read_text(encoding="utf-8")
    assert PINNED_GITHUB_HOST_KEY in content
    assert "invalid_untrusted" not in content
