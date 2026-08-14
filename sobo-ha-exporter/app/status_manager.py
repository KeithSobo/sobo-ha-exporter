"""Status and safe metadata persistence manager for Sobo HA Exporter."""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app import __version__

logger = logging.getLogger(__name__)


def atomic_write_json(target_path: Path, data: Any) -> None:
    """Safely write data to a target JSON path using atomic file replacement."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target_path.with_suffix(".tmp")

    content = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    temp_path.write_text(content, encoding="utf-8")
    temp_path.replace(target_path)


def sanitize_repo_url(url: str) -> str:
    """Format repository URL cleanly showing owner/repo without credentials."""
    if not url:
        return ""
    # Strip SSH or HTTPS auth
    clean = url.strip()
    if clean.startswith("git@github.com:"):
        clean = clean[len("git@github.com:") :]
    elif "github.com/" in clean:
        clean = clean.split("github.com/")[-1]

    if clean.endswith(".git"):
        clean = clean[:-4]
    return clean


class StatusManager:
    """Manages reading and updating safe status and metadata files under /data/status."""

    def __init__(self, status_dir: Path | str):
        self.status_dir = Path(status_dir)
        self.status_dir.mkdir(parents=True, exist_ok=True)

    @property
    def status_file(self) -> Path:
        return self.status_dir / "status.json"

    @property
    def preview_file(self) -> Path:
        return self.status_dir / "export-preview.json"

    @property
    def failed_manifest_file(self) -> Path:
        return self.status_dir / "failed-export-manifest.json"

    @property
    def output_file(self) -> Path:
        return self.status_dir / "generated-output.json"

    def get_status(self) -> dict[str, Any]:
        """Read status.json safely."""
        if not self.status_file.exists():
            return {
                "status": "idle",
                "exporter_version": __version__,
                "last_attempt_at": None,
                "last_success_at": None,
                "last_commit": None,
                "last_error": None,
                "next_run": None,
                "git_connection_status": "untested",
                "secret_scan_status": "NOT_RUN",
                "destination_repository": "",
                "branch": "main",
                "schedule_enabled": True,
                "schedule_time": "03:00",
                "schedule_timezone": "UTC",
                "counts": {},
            }
        try:
            res: dict[str, Any] = json.loads(self.status_file.read_text(encoding="utf-8"))
            return res
        except Exception as e:
            logger.warning("Error reading status.json: %s", e)
            return {"status": "error", "last_error": str(e), "exporter_version": __version__}

    def update_status(
        self,
        status_str: str,
        last_commit: str | None = None,
        last_error: str | None = None,
        next_run: str | None = None,
        git_connection_status: str | None = None,
        secret_scan_status: str | None = None,
        destination_repository: str | None = None,
        branch: str | None = None,
        schedule_enabled: bool | None = None,
        schedule_time: str | None = None,
        schedule_timezone: str | None = None,
        counts: dict[str, int] | None = None,
    ) -> None:
        """Update status.json atomically."""
        current = self.get_status()
        now_iso = datetime.now(UTC).isoformat()

        current["status"] = status_str
        current["exporter_version"] = __version__
        current["last_attempt_at"] = now_iso

        if status_str in ["success", "no_changes"]:
            current["last_success_at"] = now_iso
            current["last_error"] = None

        if last_commit is not None:
            current["last_commit"] = last_commit
        if last_error is not None:
            current["last_error"] = last_error
            current["message"] = last_error
        if next_run is not None:
            current["next_run"] = next_run
        if git_connection_status is not None:
            current["git_connection_status"] = git_connection_status
        if secret_scan_status is not None:
            current["secret_scan_status"] = secret_scan_status
        if destination_repository is not None:
            current["destination_repository"] = sanitize_repo_url(destination_repository)
        if branch is not None:
            current["branch"] = branch
        if schedule_enabled is not None:
            current["schedule_enabled"] = schedule_enabled
        if schedule_time is not None:
            current["schedule_time"] = schedule_time
        if schedule_timezone is not None:
            current["schedule_timezone"] = schedule_timezone
        if counts is not None:
            current["counts"] = counts
            current["entities_exported"] = counts.get("entities", 0)
            current["devices_exported"] = counts.get("devices", 0)
            current["warnings"] = counts.get("warnings", 0)

        atomic_write_json(self.status_file, current)

    def write_preview_manifest(
        self, staging_dir: Path, export_config_data: dict[str, bool], warnings: list[str]
    ) -> dict[str, Any]:
        """Generate and save export-preview.json metadata manifest."""
        staged_files = [f for f in sorted(staging_dir.rglob("*")) if f.is_file()]
        total_count = len(staged_files)
        total_bytes = sum(f.stat().st_size for f in staged_files)

        category_stats: dict[str, dict[str, Any]] = {}
        extension_stats: dict[str, int] = {}
        rel_files: list[str] = []

        for f in staged_files:
            rel = f.relative_to(staging_dir)
            rel_str = str(rel).replace("\\", "/")
            rel_files.append(rel_str)

            top_cat = rel.parts[0] if len(rel.parts) > 1 else "root"
            cat_entry = category_stats.setdefault(
                top_cat, {"file_count": 0, "size_bytes": 0, "enabled": True}
            )
            cat_entry["file_count"] += 1
            cat_entry["size_bytes"] += f.stat().st_size

            ext = f.suffix.lower() or "no_extension"
            extension_stats[ext] = extension_stats.get(ext, 0) + 1

        for cat, key_name in [
            ("ai", "configuration_summary"),
            ("config", "raw_configuration_export"),
            ("inventory", "inventory"),
            ("metadata", "metadata"),
            ("references", "references"),
            ("summaries", "summaries"),
        ]:
            if cat not in category_stats:
                is_enabled = export_config_data.get(key_name, export_config_data.get(cat, True))
                category_stats[cat] = {
                    "file_count": 0,
                    "size_bytes": 0,
                    "enabled": is_enabled,
                }

        preview_data = {
            "timestamp": datetime.now(UTC).isoformat(),
            "total_files": total_count,
            "total_bytes": total_bytes,
            "categories": category_stats,
            "extensions": extension_stats,
            "warnings": warnings,
            "files": rel_files,
        }

        atomic_write_json(self.preview_file, preview_data)
        return preview_data

    def write_failed_manifest(self, scan_details: list[Any]) -> dict[str, Any]:
        """Save failed-export-manifest.json with safe diagnostic findings."""
        findings = [
            {
                "relative_path": getattr(d, "relative_path", str(d)),
                "extension": getattr(d, "extension", ""),
                "size_bytes": getattr(d, "size_bytes", 0),
                "rule_name": getattr(d, "rule_name", "Secret Pattern"),
                "line_number": getattr(d, "line_number", None),
            }
            for d in scan_details
        ]

        manifest_data = {
            "timestamp": datetime.now(UTC).isoformat(),
            "exporter_version": __version__,
            "total_findings": len(findings),
            "findings": findings,
        }

        atomic_write_json(self.failed_manifest_file, manifest_data)
        return manifest_data

    def clear_failed_manifest(self) -> None:
        """Remove failed-export-manifest.json on successful export."""
        if self.failed_manifest_file.exists():
            try:
                self.failed_manifest_file.unlink()
            except Exception as e:
                logger.warning("Could not delete failed export manifest: %s", e)

    def write_generated_output_manifest(self, staging_dir: Path) -> dict[str, Any]:
        """Generate and save generated-output.json manifest from staging dir."""
        staged_files = [f for f in sorted(staging_dir.rglob("*")) if f.is_file()]
        now_iso = datetime.now(UTC).isoformat()

        dir_stats: dict[str, dict[str, Any]] = {}
        rel_files: list[str] = []

        for f in staged_files:
            rel = f.relative_to(staging_dir)
            rel_str = str(rel).replace("\\", "/")
            rel_files.append(rel_str)

            top_dir = rel.parts[0] if len(rel.parts) > 1 else "root"
            entry = dir_stats.setdefault(
                top_dir,
                {"file_count": 0, "size_bytes": 0, "last_generated_at": now_iso},
            )
            entry["file_count"] += 1
            entry["size_bytes"] += f.stat().st_size

        output_data = {
            "last_generated_at": now_iso,
            "total_files": len(staged_files),
            "total_bytes": sum(f.stat().st_size for f in staged_files),
            "directories": dir_stats,
            "file_list": rel_files,
        }

        atomic_write_json(self.output_file, output_data)
        return output_data
