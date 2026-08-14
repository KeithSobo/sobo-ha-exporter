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


def test_secret_scanner_ignores_ui_translation_labels(tmp_path):
    trans_file = tmp_path / "en.json"
    trans_file.write_text(
        '{"password": "Password", "api_key": "API Key", "secret": "Client Secret"}',
        encoding="utf-8",
    )
    scanner = SecretScanner()
    res = scanner.scan_directory(tmp_path)
    assert res.has_secrets is False


def test_secret_scanner_detects_real_hardcoded_password(tmp_path):
    user_yaml = tmp_path / "configuration.yaml"
    user_yaml.write_text('mqtt:\n  password: "MySecretPass123!"\n', encoding="utf-8")
    scanner = SecretScanner()
    res = scanner.scan_directory(tmp_path)
    assert res.has_secrets is True
    assert any("Hardcoded Password Field" in f for f in res.findings)


def test_secret_scanner_no_secret_values_in_detailed_findings(tmp_path):
    user_yaml = tmp_path / "configuration.yaml"
    secret_val = "SuperSecret_Value_998877"
    user_yaml.write_text(f'mqtt:\n  password: "{secret_val}"\n', encoding="utf-8")
    scanner = SecretScanner()
    res = scanner.scan_directory(tmp_path)
    assert res.has_secrets is True
    assert len(res.detailed_findings) > 0
    detail = res.detailed_findings[0]
    assert detail.rule_name == "Hardcoded Password Field"
    assert detail.relative_path == "configuration.yaml"
    # Ensure secret_val does not appear in detail fields
    assert secret_val not in detail.relative_path
    assert secret_val not in detail.rule_name
    assert secret_val not in detail.extension
