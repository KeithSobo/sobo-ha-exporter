# Changelog

All notable changes to the Sobo Home Assistant Exporter add-on will be documented in this file.

## [0.3.2] - 2026-08-14

### Fixed

- Resolved line length formatting in `ha_client.py` error message outputs.

## [0.3.1] - 2026-08-14

### Added

- Native support for UI-managed (storage mode) Lovelace dashboards using the supported Home Assistant WebSocket API (`lovelace/dashboards/list` and `lovelace/config`).
- Normalized `DashboardModel`, `ViewModel`, and `CardModel` representations supporting default dashboard, additional dashboards, and admin dashboards.
- Recursive card parser with support for sections, badges, chips, nested cards (`vertical-stack`, `horizontal-stack`, `grid`, `conditional`), custom cards (`custom:*`), and Pillar cards (`pillar-*`).
- Automated Pillar component detector (`pillar-main-group-card`, `pillar-group-card`, `pillar-sub-button-*`, `pillar-chips`).
- `inventory/dashboards.json` output for complete inventory tracking.
- Replaced single `ai/dashboards.md` file with multi-file directory `ai/dashboards/` containing `overview.md` and per-dashboard Markdown analysis files (e.g. `ai/dashboards/Home.md`, `ai/dashboards/Network.md`).
- Multi-directional dashboard relationship mapping across entities, devices, areas, labels, automations, and scripts.
- Search index (`search-index.json`) and reverse impact index (`impact-index.json`) integration for dashboard entity usage.
- Ingress UI metrics for Dashboard Count, View Count, Card Count, Custom Cards, Pillar Cards, Entity References, Unresolved Templates, and explicit failure diagnostic banners.
- Partial export failure handling ensuring non-dashboard categories publish cleanly even if dashboard discovery fails.

## [0.3.0] - 2026-08-14

### Added

- Product separation of safe AI Configuration Summary (`export.configuration_summary`, default `true`) and Advanced Raw Configuration Export (`advanced.raw_configuration_export`, default `false`).
- Safe PyYAML parser (`SafeYamlParser`) with custom tag handling (`!secret`, `!include`, `!env_var`, `!input`), path traversal prevention, and depth/size limits.
- Generates 14 safe structural Markdown summaries under `ai/configuration/`.
