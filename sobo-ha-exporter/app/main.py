"""Main application entrypoint and export orchestration loop for Sobo HA Exporter."""

import json
import logging
import os
import re
import shutil
import signal
import sys
import tempfile
import threading
import time
from datetime import UTC, datetime, timedelta, tzinfo
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app import __version__
from app.collectors.areas import collect_areas
from app.collectors.automations import collect_automations
from app.collectors.configuration import collect_configuration_files
from app.collectors.devices import collect_devices
from app.collectors.entities import collect_entities
from app.collectors.integrations import collect_integrations
from app.collectors.labels import collect_labels
from app.config import AppConfig, ConfigurationError, get_config_dir, load_config
from app.exporters import (
    export_ai_reference_layer,
    export_config_yaml,
    export_inventory_json,
    export_metadata_json,
    export_references_json,
    export_summaries_markdown,
)
from app.github.deploy_key import DeployKeyError, ensure_deploy_key, log_deploy_key_banner
from app.github.git_client import GitClient, GitClientError
from app.github.repository import RepositoryManager, RepositoryManagerError
from app.ha_client import HomeAssistantClient
from app.models.relationship import RelationshipModel
from app.security.sanitizer import DataSanitizer
from app.security.secret_scanner import SecretScanner
from app.security.validator import IntegrityValidationError, validate_export_integrity

# Setup structured logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s [%(name)s]: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("sobo_ha_exporter")

RUNNING = True
EXPORT_LOCK = threading.Lock()


def handle_signal(sig: int, frame: Any) -> None:
    """Handle graceful shutdown signals."""
    global RUNNING
    logger.info("Received signal %d. Shutting down gracefully...", sig)
    RUNNING = False


def sanitize_error_message(exc: Exception | str) -> str:
    """Scrub sensitive paths, tokens, passwords, and credentials from exception string."""
    msg = str(exc)
    msg = msg.replace("/data/ssh/id_ed25519", "[PRIVATE_KEY_PATH]")
    msg = re.sub(r"https?://[^:@\s]+:[^:@\s]+@", "https://[REDACTED]@", msg)
    msg = re.sub(
        r"(?i)(bearer\s+[a-zA-Z0-9\._\-]{10,}|eyJ[a-zA-Z0-9\._\-]{10,})",
        "[REDACTED_TOKEN]",
        msg,
    )
    return msg


def update_status(
    status_dir: Path | str,
    status_str: str,
    last_commit: str = "",
    entities_count: int = 0,
    devices_count: int = 0,
    warnings_count: int = 0,
    error_message: str = "",
) -> None:
    """Persist run status to /data/status/status.json."""
    directory = Path(status_dir)
    directory.mkdir(parents=True, exist_ok=True)
    status_file = directory / "status.json"

    data = {
        "status": status_str,
        "last_export": datetime.now(UTC).isoformat(),
        "last_commit": last_commit,
        "entities_exported": entities_count,
        "devices_exported": devices_count,
        "warnings": warnings_count,
        "version": __version__,
    }
    if error_message:
        data["message"] = sanitize_error_message(error_message)

    try:
        status_file.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    except Exception as e:
        logger.error("Failed to write status file: %s", e)


def get_ha_timezone(client: HomeAssistantClient | None = None) -> tuple[tzinfo, str]:
    """Retrieve Home Assistant timezone or fallback to UTC with warning."""
    tz_str = ""
    if client:
        tz_str = client.get_config_timezone()

    if not tz_str:
        tz_str = os.getenv("TZ", "")

    if tz_str and tz_str.upper() != "UTC":
        try:
            return ZoneInfo(tz_str), tz_str
        except ZoneInfoNotFoundError:
            logger.warning("Invalid timezone string '%s'. Falling back to UTC.", tz_str)
        except Exception as e:
            logger.warning("Error loading timezone '%s': %s. Falling back to UTC.", tz_str, e)

    return UTC, "UTC"


def calculate_next_scheduled_run(
    time_str: str,
    tz: tzinfo | None = None,
    now: datetime | None = None,
) -> datetime:
    """Calculate next daily execution datetime based on HH:MM string in specified timezone."""
    target_tz = tz or UTC
    reference = now or datetime.now(target_tz)

    try:
        parts = time_str.strip().split(":")
        target_hour = int(parts[0])
        target_minute = int(parts[1])
    except Exception:
        target_hour = 3
        target_minute = 0

    target = reference.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
    if target <= reference:
        target += timedelta(days=1)

    return target


def run_export(
    config: AppConfig,
    data_dir: Path = Path("/data"),
    config_dir: Path | None = None,
) -> bool:
    """Execute complete export pipeline with clean staging replacement."""
    if not EXPORT_LOCK.acquire(blocking=False):
        logger.warning("An export process is already running. Skipping concurrent run.")
        return False

    resolved_config_dir = config_dir if config_dir is not None else get_config_dir()

    try:
        return _execute_export_pipeline(config, data_dir, resolved_config_dir)
    finally:
        EXPORT_LOCK.release()


def _execute_export_pipeline(
    config: AppConfig,
    data_dir: Path,
    config_dir: Path,
) -> bool:
    logger.info("Starting Home Assistant export run...")

    entities_count = 0
    devices_count = 0
    warnings_count = 0
    warnings: list[str] = []

    ssh_dir = data_dir / "ssh"
    status_dir = data_dir / "status"
    final_staging_dir = data_dir / "generated"
    repo_dir = data_dir / "repository"

    update_status(status_dir, "running")

    temp_staging_base = tempfile.mkdtemp(prefix="staging_", dir=data_dir)
    staging_dir = Path(temp_staging_base)

    try:
        # 1. SSH Deploy Key verification
        try:
            priv_key, _pub_key, _pub_key_text = ensure_deploy_key(ssh_dir=ssh_dir)
        except DeployKeyError as e:
            msg = f"SSH deploy key error: {e}"
            logger.error(msg)
            update_status(status_dir, "error", error_message=msg)
            return False

        # 2. Setup HA API Client & Validate Connection
        ha_client = HomeAssistantClient()
        ha_client.validate_connection()

        areas = collect_areas(ha_client) if config.export.areas else []
        area_map = {a.area_id: a.name for a in areas}

        devices = (
            collect_devices(ha_client, area_name_map=area_map) if config.export.devices else []
        )
        dev_map = {d.device_id: d.name for d in devices}

        entities = (
            collect_entities(
                ha_client,
                device_name_map=dev_map,
                area_name_map=area_map,
                devices=devices,
            )
            if config.export.entities
            else []
        )
        entities_count = len(entities)

        # Re-run device collection with entities to populate integration_domains
        if config.export.devices:
            devices = collect_devices(ha_client, area_name_map=area_map, entities=entities)
        devices_count = len(devices)

        labels = collect_labels(ha_client, required=True) if config.export.labels else []

        # Validate relationship integrity before export
        try:
            validate_export_integrity(
                entities=entities,
                devices=devices,
                areas=areas,
                labels=labels if config.export.labels else None,
            )
        except IntegrityValidationError as e:
            msg = f"Export integrity validation failed: {e}"
            logger.error(msg)
            update_status(
                status_dir,
                "error",
                entities_count=entities_count,
                devices_count=devices_count,
                warnings_count=warnings_count,
                error_message=msg,
            )
            return False

        integrations = (
            collect_integrations(ha_client, entities=entities, devices=devices)
            if config.export.integrations
            else []
        )

        auto_map: dict[str, list[str]] = {}
        if config.export.automations:
            auto_map, auto_warnings = collect_automations(config_dir=config_dir)
            warnings.extend(auto_warnings)
            warnings_count = len(warnings)

        rel_model = RelationshipModel()
        if config.export.relationships:
            for ent in entities:
                if ent.device_id:
                    rel_model.device_to_entities.setdefault(ent.device_id, []).append(ent.entity_id)
                    rel_model.entity_to_device[ent.entity_id] = ent.device_id
                for lbl in ent.labels:
                    rel_model.label_to_entities.setdefault(lbl, []).append(ent.entity_id)

            for dev in devices:
                if dev.area_id:
                    rel_model.device_to_area[dev.device_id] = dev.area_id
                    rel_model.area_to_devices.setdefault(dev.area_id, []).append(dev.device_id)
                if dev.integration:
                    rel_model.integration_to_devices.setdefault(dev.integration, []).append(
                        dev.device_id
                    )
                for lbl in dev.labels:
                    rel_model.label_to_devices.setdefault(lbl, []).append(dev.device_id)

            for ent in entities:
                if ent.platform:
                    rel_model.integration_to_entities.setdefault(ent.platform, []).append(
                        ent.entity_id
                    )

            for auto_name, ent_list in auto_map.items():
                rel_model.automation_to_entities[auto_name] = ent_list
                for ent_id in ent_list:
                    rel_model.entity_to_automations.setdefault(ent_id, []).append(auto_name)

        # 3. Apply Sanitization to collected objects
        sanitizer = DataSanitizer(config.sanitization)

        entities = [sanitizer.sanitize_entity(e) for e in entities]
        devices = [sanitizer.sanitize_device(d) for d in devices]
        areas = [sanitizer.sanitize_area(a) for a in areas]
        labels = [sanitizer.sanitize_label(lbl) for lbl in labels]
        integrations = sanitizer.sanitize_value(integrations)
        auto_map = sanitizer.sanitize_value(auto_map)
        rel_model_dict = sanitizer.sanitize_value(rel_model.to_dict())

        rel_model.device_to_entities = rel_model_dict.get("device_to_entities", {})
        rel_model.entity_to_device = rel_model_dict.get("entity_to_device", {})
        rel_model.device_to_area = rel_model_dict.get("device_to_area", {})
        rel_model.area_to_devices = rel_model_dict.get("area_to_devices", {})
        rel_model.label_to_entities = rel_model_dict.get("label_to_entities", {})
        rel_model.label_to_devices = rel_model_dict.get("label_to_devices", {})
        rel_model.integration_to_devices = rel_model_dict.get("integration_to_devices", {})
        rel_model.integration_to_entities = rel_model_dict.get("integration_to_entities", {})
        rel_model.automation_to_entities = rel_model_dict.get("automation_to_entities", {})
        rel_model.entity_to_automations = rel_model_dict.get("entity_to_automations", {})

        sanitizer_report = sanitizer.get_report()

        # 4. Generate outputs into temporary staging directory
        if (
            config.export.entities
            or config.export.devices
            or config.export.areas
            or config.export.labels
            or config.export.integrations
            or config.export.relationships
        ):
            export_inventory_json(
                output_dir=staging_dir,
                entities=entities,
                devices=devices,
                areas=areas,
                labels=labels,
                integrations=integrations,
                relationships=rel_model,
            )

        if config.export.relationships or config.export.automations:
            export_references_json(output_dir=staging_dir, relationships=rel_model)

        export_summaries_markdown(
            output_dir=staging_dir,
            entities=entities,
            devices=devices,
            areas=areas,
            integrations=integrations,
        )

        if config.export.configuration_files:
            cfg_files = collect_configuration_files(config_dir=config_dir)
            cfg_files = sanitizer.sanitize_value(cfg_files)
            export_config_yaml(output_dir=staging_dir, config_files=cfg_files)

        export_info = {
            "timestamp": datetime.now(UTC).isoformat(),
            "entities_count": len(entities),
            "devices_count": len(devices),
            "areas_count": len(areas),
            "labels_count": len(labels),
            "integrations_count": len(integrations),
            "warnings_count": len(warnings),
        }
        version_info = {
            "version": __version__,
            "python_version": sys.version,
        }

        export_ai_reference_layer(
            output_dir=staging_dir,
            config_dir=config_dir,
            entities=entities,
            devices=devices,
            areas=areas,
            labels=labels,
            integrations=integrations,
            relationships=rel_model,
            export_config=config.export,
            export_info=export_info,
            warnings=warnings,
        )

        export_metadata_json(
            output_dir=staging_dir,
            export_info=export_info,
            exporter_version=version_info,
            sanitization_report=sanitizer_report,
            warnings=warnings,
        )

        # 5. Secret Scanner Gate on temporary staging directory
        scanner = SecretScanner()
        scan_res = scanner.scan_directory(staging_dir)
        if scan_res.has_secrets:
            msg = f"Secret Scanner aborted export due to findings: {scan_res.findings}"
            logger.error(msg)
            update_status(
                status_dir,
                "error",
                entities_count=entities_count,
                devices_count=devices_count,
                warnings_count=warnings_count,
                error_message=msg,
            )
            return False

        # 6. Clean replacement of generated staging directory
        if final_staging_dir.exists():
            shutil.rmtree(final_staging_dir)
        shutil.move(str(staging_dir), str(final_staging_dir))

        # 7. Git repository operations
        git_client = GitClient(repo_dir=repo_dir, private_key_path=priv_key)
        repo_mgr = RepositoryManager(repo_dir=repo_dir)

        if not repo_dir.exists() or not (repo_dir / ".git").exists():
            logger.info("Cloning destination repository %s...", config.repository)
            try:
                git_client.clone_repository(config.repository, branch=config.branch)
            except GitClientError as e:
                msg = (
                    f"Failed to clone repository: {e}. "
                    "Ensure public key has been added to GitHub with write access."
                )
                logger.error(msg)
                update_status(status_dir, "error", error_message=msg)
                return False

        try:
            git_client.fetch_and_update(branch=config.branch)
            repo_mgr.sync_staged_content(final_staging_dir)
            git_client.configure_author(config.git.author_name, config.git.author_email)
        except (GitClientError, RepositoryManagerError) as e:
            msg = f"Error synchronizing repository staging content: {e}"
            logger.error(msg)
            update_status(status_dir, "error", error_message=msg)
            return False

        # Execute commit and push
        try:
            pushed, commit_info = git_client.commit_and_push(
                message=config.git.commit_message,
                branch=config.branch,
            )
        except GitClientError as e:
            msg = f"Git operation failed: {e}"
            logger.error(msg)
            update_status(
                status_dir=status_dir,
                status_str="error",
                entities_count=entities_count,
                devices_count=devices_count,
                warnings_count=warnings_count,
                error_message=msg,
            )
            return False

        if pushed:
            logger.info("Export committed and pushed cleanly. Commit: %s", commit_info)
            update_status(
                status_dir=status_dir,
                status_str="success",
                last_commit=commit_info,
                entities_count=entities_count,
                devices_count=devices_count,
                warnings_count=warnings_count,
            )
        else:
            logger.info("No content changes detected. Commit skipped.")
            update_status(
                status_dir=status_dir,
                status_str="no_changes",
                last_commit="no_changes",
                entities_count=entities_count,
                devices_count=devices_count,
                warnings_count=warnings_count,
            )

        return True

    except Exception as exc:
        logger.exception("Unexpected export pipeline failure")
        safe_msg = sanitize_error_message(exc)
        update_status(
            status_dir=status_dir,
            status_str="error",
            entities_count=entities_count,
            devices_count=devices_count,
            warnings_count=warnings_count,
            error_message=safe_msg,
        )
        return False

    finally:
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)


def main() -> None:
    """Main application execution and scheduling loop."""
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    logger.info("Starting Sobo Home Assistant Exporter v%s", __version__)

    data_dir = Path(os.getenv("DATA_DIR", "/data"))
    config_dir = get_config_dir()
    ssh_dir = data_dir / "ssh"
    status_dir = data_dir / "status"
    options_file = data_dir / "options.json"

    try:
        _priv, _pub, pub_key_text = ensure_deploy_key(ssh_dir=ssh_dir)
        log_deploy_key_banner(pub_key_text)
    except Exception as e:
        msg = f"Failed to initialize SSH deploy key: {e}"
        logger.error(msg)
        update_status(status_dir, "error", error_message=msg)
        sys.exit(1)

    app_config: AppConfig | None = None
    last_setup_error = ""
    last_log_time = 0.0

    try:
        app_config = load_config(options_file)
    except ConfigurationError as e:
        last_setup_error = str(e)
        last_log_time = time.time()
        logger.warning("Configuration required: %s", e)
        update_status(
            status_dir,
            "setup_required",
            error_message=(
                "Configure the destination GitHub SSH repository and add the displayed deploy key."
            ),
        )
    except Exception as e:
        last_setup_error = str(e)
        last_log_time = time.time()
        logger.error("Unexpected options error: %s", e)
        update_status(status_dir, "error", error_message=str(e))

    if app_config:
        try:
            run_export(app_config, data_dir=data_dir, config_dir=config_dir)
        except Exception as e:
            logger.error("Unhandled error during startup export: %s", e)

    ha_client = HomeAssistantClient()
    tz_info, tz_name = get_ha_timezone(ha_client)

    next_run: datetime | None = None
    if app_config and app_config.schedule.enabled:
        next_run = calculate_next_scheduled_run(app_config.schedule.time, tz=tz_info)
        logger.info(
            "Next scheduled export: %s (Timezone: %s)",
            next_run.isoformat(),
            tz_name,
        )
    else:
        logger.info("Scheduled exports are disabled or setup is required. Add-on will idle.")

    while RUNNING:
        time.sleep(15)
        if not RUNNING:
            break

        if not app_config:
            try:
                app_config = load_config(options_file)
                logger.info("Valid options detected. Proceeding with initial export...")
                run_export(app_config, data_dir=data_dir, config_dir=config_dir)
                if app_config.schedule.enabled:
                    next_run = calculate_next_scheduled_run(app_config.schedule.time, tz=tz_info)
                    logger.info(
                        "Next scheduled export: %s (Timezone: %s)",
                        next_run.isoformat(),
                        tz_name,
                    )
            except Exception as exc:
                err_str = str(exc)
                now_sec = time.time()
                if err_str != last_setup_error or (now_sec - last_log_time >= 300):
                    logger.warning("Waiting for configuration: %s", sanitize_error_message(exc))
                    last_setup_error = err_str
                    last_log_time = now_sec

        elif app_config.schedule.enabled and next_run:
            now = datetime.now(tz_info)
            if now >= next_run:
                logger.info(
                    "Triggering scheduled export for target time %s (%s)",
                    next_run.isoformat(),
                    tz_name,
                )
                try:
                    run_export(app_config, data_dir=data_dir, config_dir=config_dir)
                except Exception as e:
                    logger.error("Error during scheduled export: %s", e)

                next_run = calculate_next_scheduled_run(app_config.schedule.time, tz=tz_info)
                logger.info(
                    "Next scheduled export: %s (Timezone: %s)",
                    next_run.isoformat(),
                    tz_name,
                )


if __name__ == "__main__":
    main()
