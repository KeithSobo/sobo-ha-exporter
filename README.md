# Sobo Home Assistant Exporter Add-on

A Home Assistant OS add-on that exports a sanitized, AI-readable reference model of your Home Assistant installation into a private GitHub repository using SSH deploy keys.

## Features & Purpose

- **One-Way Export Only**: Strictly reads Home Assistant configuration (read-only) and API data to generate reference models. Never imports or deploys configuration back into Home Assistant.
- **AI-Readable Structure**: Exports structured JSON inventory, relationship maps, YAML configurations, and Markdown summaries suitable as context for LLMs / AI tools.
- **Strict Data Sanitization**: Redacts sensitive information including coordinates, MAC addresses, IP addresses, user IDs, webhook IDs, credentials in URLs, and secret tokens.
- **Pre-Commit Secret Scanner**: Scans generated artifacts for high-confidence credentials before pushing and aborts if a secret is detected.
- **SSH Deploy Key Authentication**: Uses repo-scoped ED25519 deploy keys stored securely in persistent storage (`/data/ssh/id_ed25519`).
- **Deterministic & Idempotent**: Sorts all entities, devices, areas, and relationships predictably. Only creates a Git commit when content actually changes.

## Architecture Overview

```text
Home Assistant OS (Read-Only /config & API)
          ↓
  sobo-ha-exporter
          ↓ (Sanitizer & Secret Scanner)
Sanitized Reference Model
          ↓ (SSH Deploy Key)
Private GitHub Reference Repository
          ↓
AI Development Tools / LLM Context
```

## Installation & Setup

1. Add this repository URL (`https://github.com/KeithSobo/sobo-ha-exporter`) to your Home Assistant Add-on Store as a custom repository.
2. Install the **Sobo HA Exporter** add-on.
3. In the add-on Configuration tab, set `repository` to your private GitHub SSH repository URL (e.g. `git@github.com:YOUR_USERNAME/ha-reference.git`).
4. Start the add-on and inspect the add-on log output.

## Deploy Key Configuration

On initial startup, the add-on automatically generates an ED25519 SSH key pair at `/data/ssh/id_ed25519` and displays the public key in the add-on logs:

```text
================================================================================
Sobo HA Exporter requires a GitHub deploy key.

Copy the public key below and add it to:
  GitHub repository -> Settings -> Deploy keys -> Add deploy key -> Enable write access

Public deploy key:

ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI... sobo-ha-exporter
================================================================================
```

### Steps on GitHub:

1. Open your destination private GitHub repository.
2. Go to **Settings** -> **Deploy keys** -> **Add deploy key**.
3. Paste the public key displayed in the logs.
4. Check **Allow write access**.
5. Save the key.

On subsequent runs or restarts, the add-on reuses the existing deploy key and fetches/pushes to the destination repository cleanly.

## Configuration Options

```yaml
repository: "git@github.com:USERNAME/ha-reference.git"
branch: "main"

schedule:
  enabled: true
  time: "03:00"

export:
  entities: true
  devices: true
  areas: true
  labels: true
  integrations: true
  relationships: true
  automations: true
  configuration_files: false
  dashboards: false
  custom_components: false
  www: false

sanitization:
  enabled: true
  remove_coordinates: true
  remove_ip_addresses: false
  remove_mac_addresses: true
  remove_user_ids: true
  remove_webhook_ids: true
  remove_tokens: true
  remove_urls_with_credentials: true

git:
  author_name: "Sobo HA Exporter"
  author_email: "sobo-ha-exporter@localhost"
  commit_message: "Update Home Assistant reference export"
```

## Structure of the Generated Reference Repository

```text
ha-reference/
├── README.md
├── ai/
│   ├── README.md
│   ├── overview.md
│   ├── areas.md
│   ├── devices-by-area.md
│   ├── entities-by-domain.md
│   ├── helpers.md
│   ├── automations.md
│   ├── scripts.md
│   ├── integrations.md
│   ├── labels.md
│   ├── dashboards.md
│   ├── orphaned-and-unassigned.md
│   ├── impact-index.json
│   └── search-index.json
├── inventory/
│   ├── entities.json
│   ├── devices.json
│   ├── areas.json
│   ├── labels.json
│   ├── integrations.json
│   └── relationships.json
├── summaries/
│   ├── entity-summary.md
│   ├── device-summary.md
│   ├── integration-summary.md
│   └── area-summary.md
├── references/
│   ├── automation-entity-map.json
│   ├── device-entity-map.json
│   ├── area-device-map.json
│   ├── label-target-map.json
│   └── entity-usage.json
├── config/
│   └── (exported configuration files when enabled)
└── metadata/
    ├── export-info.json
    ├── exporter-version.json
    ├── sanitization-report.json
    └── warnings.json
```

## Security & Privacy Principles

- Home Assistant `/homeassistant` configuration directory is mounted **read-only**.
- `.storage/`, `secrets.yaml`, `.cloud/`, `.auth`, `*.db`, and log files are **never** exported.
- High-entropy secrets and key materials trigger export abortion before `git commit`.
- SSH host key verification is enforced (`known_hosts`).
- Push commands never use `--force`.

## Development & Testing

Please refer to [CONTRIBUTING.md](CONTRIBUTING.md) for developer requirements and setup instructions.

```bash
make check
```

## License

This project is licensed under the [MIT License](LICENSE).
