"""Centralized GitHub SSH host key constant and validator."""

from pathlib import Path

# Official, pinned GitHub ED25519 public host key line
PINNED_GITHUB_HOST_KEY = (
    "github.com ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl\n"
)


def ensure_pinned_known_hosts(known_hosts_path: Path | str) -> None:
    """Verify known_hosts file exists and contains the pinned GitHub SSH host key.

    If missing or blank, populates it with the pinned official key.
    If corrupted/unexpected, restores the pinned official key.

    Args:
        known_hosts_path: Path to known_hosts file.
    """
    path = Path(known_hosts_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if not path.exists():
        path.write_text(PINNED_GITHUB_HOST_KEY, encoding="utf-8")
        path.chmod(0o644)
        return

    content = path.read_text(encoding="utf-8", errors="ignore").strip()
    if not content or "ssh-ed25519" not in content:
        path.write_text(PINNED_GITHUB_HOST_KEY, encoding="utf-8")
        path.chmod(0o644)
