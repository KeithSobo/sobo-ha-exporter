# Architecture Overview

`sobo-ha-exporter` is designed as a secure, containerized Home Assistant OS Add-on.

## Data Flow Pipeline

```text
+-------------------------------+
|  Home Assistant OS Environment|
| - Supervisor API / WebSocket  |
| - Read-Only /config           |
+---------------+---------------+
                |
                v
+---------------+---------------+
|       Collectors Module       |
| - Entities, Devices, Areas    |
| - Labels, Integrations        |
| - Automations & Config        |
+---------------+---------------+
                |
                v
+---------------+---------------+
|     Security & Sanitizer      |
| - Coordinate Redaction        |
| - MAC / IP / User Redaction   |
| - Secret Pattern Scanner      |
+---------------+---------------+
                |
                v
+---------------+---------------+
|       Exporter Engine         |
| - Deterministic JSON          |
| - Markdown Summaries          |
| - Relationship Mapping        |
+---------------+---------------+
                |
                v
+---------------+---------------+
|    Git & Deploy Key Engine    |
| - ED25519 SSH Auth            |
| - Change Diffing & Idempotency|
| - Commit & Push to GitHub     |
+-------------------------------+
```

## Component Roles

- **`app.config`**: Validates `/data/options.json` schema and establishes conservative defaults.
- **`app.ha_client`**: Connects via WebSocket or REST API using `SUPERVISOR_TOKEN` to retrieve state, registry details, and relationships.
- **`app.collectors`**: Standardizes domain models into decoupled objects (Entity, Device, Area, Label).
- **`app.security.sanitizer`**: Applies sanitization rules iteratively across exported dictionaries and text files.
- **`app.security.secret_scanner`**: Evaluates final staged export files for potential secret patterns prior to commit.
- **`app.exporters`**: Generates stable, deterministic output files.
- **`app.github.deploy_key`**: Manages SSH ED25519 key generation in persistent `/data/ssh/`.
- **`app.github.git_client`**: Handles git clone, fetch, diff, commit, and push operations cleanly.
