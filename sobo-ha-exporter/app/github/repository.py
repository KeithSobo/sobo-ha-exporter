"""Repository staging manager and marker validation."""

import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

MARKER_FILENAME = ".sobo-ha-exporter"
EXPORTER_MANAGED_DIRS = ["inventory", "summaries", "references", "config", "metadata", "ai"]
SAFE_INITIAL_FILES = {
    "readme.md",
    "license",
    "license.md",
    "license.txt",
    ".gitignore",
    ".sobo-ha-exporter",
}


class RepositoryManagerError(Exception):
    """Raised when repository safety checks fail."""

    pass


class RepositoryManager:
    """Manages cloning, safety checks, and staging copy into target repository."""

    def __init__(self, repo_dir: Path | str):
        self.repo_dir = Path(repo_dir)

    def validate_safe_destination(self) -> bool:
        """Verify repository is empty, marked, or passes safe-initialization check.

        Returns:
            True if safe to modify, False otherwise.
        """
        if not self.repo_dir.exists():
            return True

        files = [f for f in self.repo_dir.iterdir() if f.name != ".git"]
        if not files:
            return True

        marker = self.repo_dir / MARKER_FILENAME
        if marker.exists():
            return True

        for item in files:
            name_lower = item.name.lower()
            if item.is_dir():
                if name_lower not in EXPORTER_MANAGED_DIRS:
                    logger.warning("Target repository contains unmanaged directory: %s", item.name)
                    return False
            else:
                if name_lower not in SAFE_INITIAL_FILES:
                    logger.warning("Target repository contains unmanaged file: %s", item.name)
                    return False

        return True

    def ensure_marker_file(self) -> None:
        """Create marker file in destination repository."""
        self.repo_dir.mkdir(parents=True, exist_ok=True)
        marker = self.repo_dir / MARKER_FILENAME
        if not marker.exists():
            marker.write_text(
                "# Sobo HA Exporter Managed Repository\n"
                "This repository is automatically updated by sobo-ha-exporter.\n",
                encoding="utf-8",
            )

    def sync_staged_content(self, staging_dir: Path | str) -> None:
        """Synchronize exporter-managed content from staging_dir into repository.

        Replaces managed directories that exist in staging, and removes any managed
        directories that are absent in staging (e.g. if an export option is disabled).

        Args:
            staging_dir: Path containing generated export directories.
        """
        staging = Path(staging_dir)
        if not self.validate_safe_destination():
            raise RepositoryManagerError(
                f"Refusing to overwrite repository at {self.repo_dir}: "
                f"missing marker file {MARKER_FILENAME} and failed safe-initialization check"
            )

        self.ensure_marker_file()

        # Synchronize managed directories
        for dname in EXPORTER_MANAGED_DIRS:
            src_sub = staging / dname
            dst_sub = self.repo_dir / dname

            if src_sub.exists() and src_sub.is_dir():
                if dst_sub.exists():
                    shutil.rmtree(dst_sub)
                shutil.copytree(src_sub, dst_sub)
            else:
                # If managed directory is absent in staging, remove stale destination directory
                if dst_sub.exists():
                    shutil.rmtree(dst_sub)

        # Copy README if present in staging
        src_readme = staging / "README.md"
        if src_readme.exists():
            dst_readme = self.repo_dir / "README.md"
            if not dst_readme.exists():
                shutil.copy2(src_readme, dst_readme)
