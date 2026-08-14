# Troubleshooting Guide

## Opening the Ingress UI

Navigate to **Home Assistant Sidebar &rarr; Sobo HA Exporter** or open the add-on page and click **Open Web UI**.

## Status State Meanings

- **`setup_required`**: SSH deploy key is not yet added to GitHub or destination repository URL is not configured.
- **`idle`**: Exporter is configured and waiting for next scheduled run.
- **`running`**: Export pipeline is currently executing.
- **`success`**: Reference export completed and pushed cleanly to GitHub.
- **`no_changes`**: Export completed successfully; no content changes were detected since last commit.
- **`blocked`**: Secret scanner detected potential hardcoded credentials. The export was halted, no content was pushed to GitHub, and safe diagnostic findings are available under the **Diagnostics** tab.
- **`error`**: Network, API, or system error occurred. Check logs or the Overview tab for sanitized error messages.

## Resolving Blocked Exports

1. Open the Ingress UI and click the **Diagnostics** tab.
2. Inspect the safe findings list (shows file path, rule name, and line number).
3. Open the flagged configuration file in Home Assistant and remove hardcoded secrets or use `secrets.yaml` / environment variables.
4. Click **Run Export Now** to re-run validation and resume exports.
