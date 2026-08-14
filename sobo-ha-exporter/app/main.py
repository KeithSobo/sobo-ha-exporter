"""Main application entrypoint, web server, and export orchestration loop for Sobo HA Exporter."""

import logging
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from datetime import UTC, datetime, timedelta, tzinfo
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app import __version__
from app.analyzers.config_analyzers import analyze_all_configuration
from app.collectors.areas import collect_areas
from app.collectors.automations import collect_automations
from app.collectors.configuration import collect_configuration_files
from app.collectors.dashboards import collect_dashboards
from app.collectors.devices import collect_devices
from app.collectors.entities import collect_entities
from app.collectors.integrations import collect_integrations
from app.collectors.labels import collect_labels
from app.config import AppConfig, ConfigurationError, get_config_dir, load_config
from app.exporters import (
    export_ai_configuration_summary,
    export_ai_reference_layer,
    export_config_yaml,
    export_summaries_markdown,
)
from app.exporters.json_exporter import (
    export_inventory_json,
    export_metadata_json,
    export_references_json,
)
from app.github.deploy_key import ensure_deploy_key, log_deploy_key_banner
from app.github.git_client import GitClient, GitClientError
from app.github.repository import RepositoryManager, RepositoryManagerError
from app.ha_client import HomeAssistantClient
from app.models.dashboard import DashboardModel
from app.models.relationship import RelationshipModel
from app.security.sanitizer import DataSanitizer
from app.security.secret_scanner import SecretScanner
from app.status_manager import StatusManager, sanitize_repo_url
from app.web_server import WebServer

# Setup structured logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s [%(name)s]: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("sobo_ha_exporter")

RUNNING = True
EXPORT_LOCK = threading.Lock()
WEB_SERVER: WebServer | None = None


def handle_signal(sig: int, frame: Any) -> None:
    """Handle graceful shutdown signals."""
    global RUNNING, WEB_SERVER
    logger.info("Received signal %d. Shutting down gracefully...", sig)
    RUNNING = False
    if WEB_SERVER:
        try:
            WEB_SERVER.stop()
        except Exception as e:
            logger.warning("Error stopping web server on signal: %s", e)


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
    """Persist run status via StatusManager."""
    status_mgr = StatusManager(status_dir)
    status_mgr.update_status(
        status_str=status_str,
        last_commit=last_commit if last_commit else None,
        last_error=sanitize_error_message(error_message) if error_message else None,
        counts={
            "entities": entities_count,
            "devices": devices_count,
            "warnings": warnings_count,
        },
    )


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


def test_git_connection(data_dir: Path, repository: str, branch: str = "main") -> dict[str, Any]:
    """Safe Git connection check using git ls-remote (read-only, no modification)."""
    priv_key = data_dir / "ssh" / "id_ed25519"
    if not priv_key.exists():
        return {"success": False, "message": "Deploy key not initialized."}
    if not repository:
        return {"success": False, "message": "No destination repository configured."}

    known_hosts = data_dir / "ssh" / "known_hosts"
    ssh_cmd = f"ssh -i {priv_key} -o StrictHostKeyChecking=accept-new"
    if known_hosts.exists():
        ssh_cmd += f" -o UserKnownHostsFile={known_hosts}"

    env = os.environ.copy()
    env["GIT_SSH_COMMAND"] = ssh_cmd

    try:
        proc = subprocess.run(
            ["git", "ls-remote", repository, f"refs/heads/{branch}"],
            env=env,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if proc.returncode == 0:
            repo_clean = sanitize_repo_url(repository)
            return {
                "success": True,
                "message": f"Successfully connected to {repo_clean} (branch: {branch}).",
            }
        else:
            err = sanitize_error_message(proc.stderr.strip() or proc.stdout.strip())
            return {"success": False, "message": f"Git connection check failed: {err}"}
    except Exception as e:
        return {"success": False, "message": f"Error running Git test: {sanitize_error_message(e)}"}


def run_export(
    config: AppConfig,
    data_dir: Path = Path("/data"),
    config_dir: Path | None = None,
) -> bool:
    """Execute complete export pipeline with clean staging replacement."""
    acquired = EXPORT_LOCK.acquire(blocking=False)
    if not acquired:
        logger.warning("Export requested while another export is in progress. Skipping.")
        return False

    try:
        resolved_config_dir = config_dir if config_dir is not None else get_config_dir()
        return _execute_export_pipeline(
            config=config,
            data_dir=data_dir,
            config_dir=resolved_config_dir,
        )
    finally:
        EXPORT_LOCK.release()


def _execute_export_pipeline(
    config: AppConfig,
    data_dir: Path,
    config_dir: Path,
) -> bool:
    logger.info("Starting Home Assistant export run...")
    status_mgr = StatusManager(data_dir / "status")
    status_mgr.update_status(
        status_str="running",
        destination_repository=config.repository,
        branch=config.branch,
        schedule_enabled=config.schedule.enabled,
        schedule_time=config.schedule.time,
    )

    entities_count = 0
    devices_count = 0
    warnings_count = 0
    warnings: list[str] = []

    ssh_dir = data_dir / "ssh"
    final_staging_dir = data_dir / "generated"
    repo_dir = data_dir / "repo"

    priv_key, _pub_key, _pub_key_text = ensure_deploy_key(ssh_dir=ssh_dir)

    staging_dir = Path(tempfile.mkdtemp(prefix="export_staging_", dir=data_dir))
    try:
        client = HomeAssistantClient()
        client.validate_connection()

        # 1. Collect Core Model Registries
        area_models = collect_areas(client) if config.export.areas else []
        area_name_map = {a.area_id: a.name for a in area_models}
        entity_models = collect_entities(client) if config.export.entities else []
        device_models = (
            collect_devices(
                client=client,
                area_name_map=area_name_map,
                entities=entity_models,
            )
            if config.export.devices
            else []
        )
        label_models = (
            collect_labels(client, required=config.export.labels) if config.export.labels else []
        )

        entities_count = len(entity_models)
        devices_count = len(device_models)

        # 2. Enrich Entity Areas & Derived Models
        if config.export.entities and config.export.devices:
            entity_models = collect_entities(
                client=client,
                device_name_map={d.device_id: d.name for d in device_models},
                area_name_map=area_name_map,
                devices=device_models,
            )
            device_models = collect_devices(
                client=client,
                area_name_map=area_name_map,
                entities=entity_models,
            )

        integrations = (
            collect_integrations(
                client=client,
                entities=entity_models,
                devices=device_models,
            )
            if config.export.integrations
            else []
        )

        auto_entity_map: dict[str, list[str]] = {}
        if config.export.automations:
            auto_entity_map_raw, auto_warnings = collect_automations(config_dir)
            auto_entity_map = {k: list(v) for k, v in auto_entity_map_raw.items()}
            warnings.extend(auto_warnings)

        dashboards: list[DashboardModel] = []
        dash_discovery_error: str | None = None
        if config.export.dashboards:
            dashboards, dash_warns, dash_discovery_error = collect_dashboards(
                client=client,
                config_dir=config_dir,
                entities=entity_models,
                devices=device_models,
                areas=area_models,
                labels=label_models,
            )
            warnings.extend(dash_warns)

        cfg_files: dict[str, str] = {}
        if config.advanced.raw_configuration_export:
            cfg_files = collect_configuration_files(
                config_dir=config_dir,
                allow_custom_components=config.export.custom_components,
                allow_www=config.export.www,
            )

        rel_model = RelationshipModel()
        for d in dashboards:
            d_dict = d.to_dict()
            d_ents = d_dict["relationships"]["entities"]
            rel_model.dashboard_to_entities[d.id] = d_ents
            for ent_id in d_ents:
                rel_model.entity_to_dashboards.setdefault(ent_id, []).append(d.title)

        # 3. Apply Security Sanitizer
        sanitizer = DataSanitizer(config.sanitization)
        entity_models = [sanitizer.sanitize_entity(e) for e in entity_models]
        device_models = [sanitizer.sanitize_device(d) for d in device_models]
        area_models = [sanitizer.sanitize_area(a) for a in area_models]
        label_models = [sanitizer.sanitize_label(lbl) for lbl in label_models]
        cfg_files = sanitizer.sanitize_config_files(cfg_files)

        # 4. Generate Staging Files
        if config.export.entities or config.export.devices or config.export.areas:
            export_inventory_json(
                output_dir=staging_dir,
                entities=entity_models,
                devices=device_models,
                areas=area_models,
                labels=label_models,
                integrations=integrations,
                relationships=rel_model,
                dashboards=dashboards if config.export.dashboards else None,
            )
            export_references_json(output_dir=staging_dir, relationships=rel_model)
            export_summaries_markdown(
                output_dir=staging_dir,
                entities=entity_models,
                devices=device_models,
                areas=area_models,
                integrations=integrations,
            )

        if config.export.configuration_summary:
            analysis_data = analyze_all_configuration(
                config_dir=config_dir,
                entities=entity_models,
                devices=device_models,
                areas=area_models,
                labels=label_models,
            )
            export_ai_configuration_summary(
                output_dir=staging_dir,
                analysis_data=analysis_data,
            )
            if analysis_data.get("warnings"):
                warnings.extend(analysis_data["warnings"])

        if config.advanced.raw_configuration_export and cfg_files:
            export_config_yaml(output_dir=staging_dir, config_files=cfg_files)

        warnings_count = len(warnings) + sanitizer.report.warnings_count
        export_info = {
            "timestamp": datetime.now(UTC).isoformat(),
            "exporter_version": __version__,
            "entities_count": len(entity_models),
            "devices_count": len(device_models),
            "areas_count": len(area_models),
            "labels_count": len(label_models),
            "integrations_count": len(integrations),
            "warnings_count": warnings_count,
        }
        version_info = {
            "version": __version__,
            "python_version": sys.version,
        }

        export_ai_reference_layer(
            output_dir=staging_dir,
            config_dir=config_dir,
            entities=entity_models,
            devices=device_models,
            areas=area_models,
            labels=label_models,
            integrations=integrations,
            relationships=rel_model,
            export_config=config.export,
            export_info=export_info,
            warnings=warnings,
            dashboards=dashboards,
            dash_discovery_error=dash_discovery_error,
        )

        export_metadata_json(
            output_dir=staging_dir,
            export_info=export_info,
            exporter_version=version_info,
            sanitization_report=sanitizer.report.to_dict(),
            warnings=warnings,
        )

        # Generate Safe Export Preview Manifest
        export_config_dict = {
            "ai": True,
            "configuration_summary": config.export.configuration_summary,
            "raw_configuration_export": config.advanced.raw_configuration_export,
            "inventory": config.export.entities,
            "metadata": True,
            "references": config.export.relationships,
            "summaries": config.export.entities,
        }
        status_mgr.write_preview_manifest(staging_dir, export_config_dict, warnings)

        # 5. Secret Scanner Gate on temporary staging directory with Partial Publication
        scanner = SecretScanner()
        scan_res = scanner.scan_directory(staging_dir)
        raw_export_blocked = False

        if scan_res.has_secrets:
            manifest_data = status_mgr.write_failed_manifest(scan_res.detailed_findings)
            raw_dir = staging_dir / "config"

            # Check if findings are isolated to raw config/ export
            all_in_raw = (
                raw_dir.exists()
                and scan_res.detailed_findings
                and all(
                    d.relative_path.startswith("config/") or d.relative_path.startswith("config\\")
                    for d in scan_res.detailed_findings
                )
            )

            if all_in_raw:
                logger.warning(
                    "Secret Scanner detected secrets in raw configuration files. "
                    "Pruning raw config/ output from staging to allow safe summary publication."
                )
                shutil.rmtree(raw_dir, ignore_errors=True)
                rescan_res = scanner.scan_directory(staging_dir)

                if not rescan_res.has_secrets:
                    raw_export_blocked = True
                    msg = (
                        "Raw configuration export blocked by Secret Scanner due to sensitive "
                        "fields. Safe AI configuration summaries and inventory outputs were "
                        "preserved and published."
                    )
                    logger.info(msg)
                else:
                    # Non-raw outputs also failed secret scanner -> fail closed
                    msg = f"Secret Scanner blocked export: {rescan_res.findings[0]}"
                    logger.error(msg)
                    status_mgr.update_status(
                        status_str="blocked",
                        last_error=msg,
                        secret_scan_status="BLOCKED",
                        counts={
                            "entities": entities_count,
                            "devices": devices_count,
                            "warnings": warnings_count,
                        },
                    )
                    shutil.rmtree(staging_dir, ignore_errors=True)
                    return False
            else:
                msg = (
                    f"Secret Scanner blocked export: {scan_res.findings[0]} "
                    f"({manifest_data['total_findings']} total findings). "
                    f"Safe manifest written to {status_mgr.failed_manifest_file}"
                )
                logger.error(msg)
                status_mgr.update_status(
                    status_str="blocked",
                    last_error=msg,
                    secret_scan_status="BLOCKED",
                    counts={
                        "entities": entities_count,
                        "devices": devices_count,
                        "warnings": warnings_count,
                    },
                )
                shutil.rmtree(staging_dir, ignore_errors=True)
                return False

        # 6. Clean replacement of generated staging directory
        if final_staging_dir.exists():
            shutil.rmtree(final_staging_dir)
        shutil.move(str(staging_dir), str(final_staging_dir))

        if not raw_export_blocked:
            status_mgr.clear_failed_manifest()
        status_mgr.write_generated_output_manifest(final_staging_dir)

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
                status_mgr.update_status(
                    status_str="error",
                    last_error=msg,
                    git_connection_status="error",
                )
                return False

        try:
            git_client.fetch_and_update(branch=config.branch)
            repo_mgr.sync_staged_content(final_staging_dir)
            git_client.configure_author(config.git.author_name, config.git.author_email)
        except (GitClientError, RepositoryManagerError) as e:
            msg = f"Error synchronizing repository staging content: {e}"
            logger.error(msg)
            status_mgr.update_status(
                status_str="error",
                last_error=msg,
                git_connection_status="error",
            )
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
            status_mgr.update_status(
                status_str="error",
                last_error=msg,
                git_connection_status="error",
                counts={
                    "entities": entities_count,
                    "devices": devices_count,
                    "warnings": warnings_count,
                },
            )
            return False

        helpers_count = sum(
            1
            for e in entity_models
            if e.domain
            in {
                "input_boolean",
                "input_number",
                "input_text",
                "input_select",
                "counter",
                "timer",
                "schedule",
                "group",
            }
        )
        dash_card_cnt = sum(d.to_dict()["stats"]["card_count"] for d in dashboards)
        dash_view_cnt = sum(d.to_dict()["stats"]["view_count"] for d in dashboards)
        dash_custom_cnt = sum(d.to_dict()["stats"]["custom_card_count"] for d in dashboards)
        dash_pillar_cnt = sum(d.to_dict()["stats"]["pillar_component_count"] for d in dashboards)
        dash_ent_cnt = sum(d.to_dict()["stats"]["entity_count"] for d in dashboards)
        dash_unres_cnt = sum(d.to_dict()["stats"]["unresolved_template_count"] for d in dashboards)

        counts_dict = {
            "entities": len(entity_models),
            "devices": len(device_models),
            "areas": len(area_models),
            "labels": len(label_models),
            "integrations": len(integrations),
            "automations": len(auto_entity_map),
            "helpers": helpers_count,
            "dashboards": len(dashboards),
            "dashboard_views": dash_view_cnt,
            "dashboard_cards": dash_card_cnt,
            "dashboard_custom_cards": dash_custom_cnt,
            "dashboard_pillar_cards": dash_pillar_cnt,
            "dashboard_entities": dash_ent_cnt,
            "dashboard_unresolved": dash_unres_cnt,
            "warnings": warnings_count,
        }

        if pushed:
            logger.info("Export committed and pushed cleanly. Commit: %s", commit_info)
            status_mgr.update_status(
                status_str="success",
                last_commit=commit_info,
                git_connection_status="connected",
                secret_scan_status="BLOCKED" if raw_export_blocked else "PASS",
                counts=counts_dict,
                dashboard_discovery_error=dash_discovery_error,
            )
        else:
            logger.info("No content changes detected. Commit skipped.")
            status_mgr.update_status(
                status_str="no_changes",
                last_commit="no_changes",
                git_connection_status="connected",
                secret_scan_status="BLOCKED" if raw_export_blocked else "PASS",
                counts=counts_dict,
                dashboard_discovery_error=dash_discovery_error,
            )

        return True

    except Exception as exc:
        logger.exception("Unexpected export pipeline failure")
        safe_msg = sanitize_error_message(exc)
        status_mgr.update_status(
            status_str="error",
            last_error=safe_msg,
            counts={
                "entities": entities_count,
                "devices": devices_count,
                "warnings": warnings_count,
            },
        )
        return False

    finally:
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)


def main() -> None:
    """Main application execution, Ingress web server, and scheduling loop."""
    global WEB_SERVER
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    logger.info("Starting Sobo Home Assistant Exporter v%s", __version__)

    data_dir = Path(os.getenv("DATA_DIR", "/data"))
    config_dir = get_config_dir()
    ssh_dir = data_dir / "ssh"
    status_dir = data_dir / "status"
    options_file = data_dir / "options.json"

    status_mgr = StatusManager(status_dir)

    try:
        _priv, _pub, pub_key_text = ensure_deploy_key(ssh_dir=ssh_dir)
        log_deploy_key_banner(pub_key_text)
    except Exception as e:
        msg = f"Failed to initialize SSH deploy key: {e}"
        logger.error(msg)
        status_mgr.update_status(status_str="error", last_error=msg)
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
        status_mgr.update_status(
            status_str="setup_required",
            last_error=(
                "Configure the destination GitHub SSH repository and add the displayed deploy key."
            ),
        )
    except Exception as e:
        last_setup_error = str(e)
        last_log_time = time.time()
        logger.error("Unexpected options error: %s", e)
        status_mgr.update_status(status_str="error", last_error=str(e))

    # Helper function for manual export trigger from Ingress UI
    def _manual_export_trigger() -> bool:
        if not app_config:
            try:
                cfg = load_config(options_file)
                return run_export(cfg, data_dir=data_dir, config_dir=config_dir)
            except Exception as exc:
                logger.error("Manual export failed due to config error: %s", exc)
                return False
        return run_export(app_config, data_dir=data_dir, config_dir=config_dir)

    # Helper function for Git connection check from Ingress UI
    def _test_git_trigger() -> dict[str, Any]:
        repo_url = app_config.repository if app_config else ""
        branch_name = app_config.branch if app_config else "main"
        res = test_git_connection(data_dir=data_dir, repository=repo_url, branch=branch_name)
        status_mgr.update_status(
            status_str=status_mgr.get_status().get("status", "idle"),
            git_connection_status="connected" if res.get("success") else "error",
        )
        return res

    # Start Ingress HTTP Web Server on port 8099
    ingress_port = int(os.getenv("INGRESS_PORT", "8099"))
    WEB_SERVER = WebServer(
        host="0.0.0.0",
        port=ingress_port,
        status_mgr=status_mgr,
        data_dir=data_dir,
        export_lock=EXPORT_LOCK,
        run_export_fn=_manual_export_trigger,
        test_git_fn=_test_git_trigger,
    )
    WEB_SERVER.start()

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
        status_mgr.update_status(
            status_str=status_mgr.get_status().get("status", "idle"),
            next_run=next_run.isoformat(),
        )
        logger.info(
            "Next scheduled export: %s (Timezone: %s)",
            next_run.isoformat(),
            tz_name,
        )
    else:
        logger.info("Scheduled exports are disabled or setup is required. Add-on will idle.")

    try:
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
                        next_run = calculate_next_scheduled_run(
                            app_config.schedule.time, tz=tz_info
                        )
                        status_mgr.update_status(
                            status_str=status_mgr.get_status().get("status", "idle"),
                            next_run=next_run.isoformat(),
                        )
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
                    status_mgr.update_status(
                        status_str=status_mgr.get_status().get("status", "idle"),
                        next_run=next_run.isoformat(),
                    )
                    logger.info(
                        "Next scheduled export: %s (Timezone: %s)",
                        next_run.isoformat(),
                        tz_name,
                    )
    finally:
        if WEB_SERVER:
            WEB_SERVER.stop()


if __name__ == "__main__":
    main()
