"""Unit tests for app.github.deploy_key module."""

import logging

import pytest

from app.github.deploy_key import DeployKeyError, ensure_deploy_key, log_deploy_key_banner


def test_deploy_key_generation_and_reuse(tmp_path):
    ssh_dir = tmp_path / "ssh"
    priv, pub, text = ensure_deploy_key(ssh_dir=ssh_dir)

    assert priv.exists()
    assert pub.exists()
    assert text.startswith("ssh-ed25519")

    # Call again to verify key reuse (should not regenerate or fail)
    priv2, _pub2, text2 = ensure_deploy_key(ssh_dir=ssh_dir)
    assert priv == priv2
    assert text == text2


def test_deploy_key_reconstruct_missing_public_key(tmp_path):
    ssh_dir = tmp_path / "ssh"
    _priv, pub, _orig_text = ensure_deploy_key(ssh_dir=ssh_dir)

    # Delete public key file
    pub.unlink()
    assert not pub.exists()

    # ensure_deploy_key should reconstruct missing public key from existing private key
    _priv2, pub2, recon_text = ensure_deploy_key(ssh_dir=ssh_dir)
    assert pub2.exists()
    assert recon_text.startswith("ssh-ed25519")


def test_deploy_key_missing_private_key_raises_actionable_error(tmp_path):
    ssh_dir = tmp_path / "ssh"
    priv, pub, _ = ensure_deploy_key(ssh_dir=ssh_dir)

    # Delete private key file while public key exists
    priv.unlink()
    assert not priv.exists()
    assert pub.exists()

    with pytest.raises(DeployKeyError, match="Private SSH key is missing"):
        ensure_deploy_key(ssh_dir=ssh_dir)


def test_log_deploy_key_banner(caplog):
    caplog.set_level(logging.INFO)
    log_deploy_key_banner("ssh-ed25519 AAAATESTKEY test@user")
    assert "Sobo HA Exporter requires a GitHub deploy key" in caplog.text
    assert "ssh-ed25519 AAAATESTKEY test@user" in caplog.text
