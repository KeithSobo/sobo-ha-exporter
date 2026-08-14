"""Unit tests for app.security.secret_scanner."""

from app.security.secret_scanner import SecretScanner


def test_secret_scanner_clean_directory(tmp_path):
    (tmp_path / "entities.json").write_text('{"name": "Light"}', encoding="utf-8")
    scanner = SecretScanner()
    res = scanner.scan_directory(tmp_path)
    assert res.has_secrets is False
    assert len(res.findings) == 0


def test_secret_scanner_detects_ssh_key(tmp_path):
    key_file = tmp_path / "leaked_key.txt"
    key_file.write_text("-----BEGIN RSA PRIVATE KEY-----\nMIIEogIBAAKCAQEA...\n", encoding="utf-8")
    scanner = SecretScanner()
    res = scanner.scan_directory(tmp_path)
    assert res.has_secrets is True
    assert any("SSH Private Key" in f for f in res.findings)


def test_secret_scanner_detects_github_pat(tmp_path):
    token_file = tmp_path / "config.json"
    token_file.write_text('{"token": "ghp_1234567890abcdefghijklmnopqrstuvwxyz"}', encoding="utf-8")
    scanner = SecretScanner()
    res = scanner.scan_directory(tmp_path)
    assert res.has_secrets is True
    assert any("GitHub Personal Access Token" in f for f in res.findings)


def test_secret_scanner_ignores_redacted_placeholders(tmp_path):
    clean_file = tmp_path / "report.json"
    clean_file.write_text(
        '{"token": "[REDACTED_TOKEN]", "example": "EXAMPLE_KEY"}', encoding="utf-8"
    )
    scanner = SecretScanner()
    res = scanner.scan_directory(tmp_path)
    assert res.has_secrets is False
