"""SSH deploy key management."""

import logging
import subprocess
from pathlib import Path

from app.github.host_key import ensure_pinned_known_hosts

logger = logging.getLogger(__name__)


class DeployKeyError(Exception):
    """Raised when SSH deploy key operations fail."""

    pass


def ensure_deploy_key(
    ssh_dir: Path | str = "/data/ssh",
) -> tuple[Path, Path, str]:
    """Ensure an ED25519 SSH deploy key pair and known_hosts exist in persistent storage.

    Directory permissions set to 0700, private key to 0600, public key to 0644.
    If private key exists but public key is missing, reconstructs public key.
    If private key is missing while public key exists, raises DeployKeyError.

    Args:
        ssh_dir: Path to SSH key directory.

    Returns:
        Tuple of (private_key_path, public_key_path, public_key_text).
    """
    directory = Path(ssh_dir)
    directory.mkdir(parents=True, exist_ok=True)
    directory.chmod(0o700)

    priv_key = directory / "id_ed25519"
    pub_key = directory / "id_ed25519.pub"
    known_hosts = directory / "known_hosts"

    # Ensure known_hosts is populated with pinned official GitHub host key
    ensure_pinned_known_hosts(known_hosts)

    # Case A: Neither key exists -> Generate new ED25519 pair
    if not priv_key.exists() and not pub_key.exists():
        logger.info("Generating new ED25519 SSH deploy key pair at %s", priv_key)
        cmd = [
            "ssh-keygen",
            "-t",
            "ed25519",
            "-C",
            "sobo-ha-exporter",
            "-f",
            str(priv_key),
            "-N",
            "",
        ]
        try:
            res = subprocess.run(cmd, check=False, capture_output=True, text=True)
            if res.returncode != 0:
                raise DeployKeyError(f"ssh-keygen failed: {res.stderr}")
            priv_key.chmod(0o600)
            pub_key.chmod(0o644)
        except Exception as e:
            if isinstance(e, DeployKeyError):
                raise
            raise DeployKeyError(f"Failed to generate SSH deploy key: {e}") from e

    # Case B: Private key exists, public key missing -> Reconstruct public key
    elif priv_key.exists() and not pub_key.exists():
        logger.info("Reconstructing missing public key from existing private key %s", priv_key)
        cmd = ["ssh-keygen", "-y", "-f", str(priv_key)]
        try:
            res = subprocess.run(cmd, check=False, capture_output=True, text=True)
            if res.returncode != 0:
                raise DeployKeyError(
                    f"Failed to reconstruct public key from {priv_key}: {res.stderr}. "
                    "Ensure private key is valid or remove /data/ssh to regenerate."
                )
            pub_key_text = res.stdout.strip()
            pub_key.write_text(f"{pub_key_text} sobo-ha-exporter\n", encoding="utf-8")
            pub_key.chmod(0o644)
            priv_key.chmod(0o600)
        except Exception as e:
            if isinstance(e, DeployKeyError):
                raise
            raise DeployKeyError(f"Public key reconstruction failed: {e}") from e

    # Case C: Private key missing, public key exists -> Raise error instructing user to clean up
    elif not priv_key.exists() and pub_key.exists():
        raise DeployKeyError(
            f"Private SSH key is missing at {priv_key} while public key exists at {pub_key}. "
            "Please remove the /data/ssh directory to allow generating a new deploy key pair."
        )

    # Ensure existing file permissions are secure
    if priv_key.exists():
        priv_key.chmod(0o600)
    if pub_key.exists():
        pub_key.chmod(0o644)

    pub_key_text = pub_key.read_text(encoding="utf-8").strip()
    return priv_key, pub_key, pub_key_text


def log_deploy_key_banner(public_key_text: str) -> None:
    """Output formatted deployment banner containing the public key for user setup."""
    banner = f"""
================================================================================
Sobo HA Exporter requires a GitHub deploy key.

Copy the public key below and add it to:

GitHub repository
-> Settings
-> Deploy keys
-> Add deploy key
-> Enable write access

Public deploy key:

{public_key_text}
================================================================================
"""
    logger.info(banner)
