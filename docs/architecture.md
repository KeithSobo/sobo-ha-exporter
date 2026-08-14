# Architecture Specification

## Overview

`sobo-ha-exporter` operates as a read-only one-way export add-on for Home Assistant OS. It collects entity, device, area, label, integration, automation, script, and helper configurations, normalizes and sanitizes the data, runs static secret scanning, and pushes the generated reference repository to a user-configured private GitHub SSH repository.

```text
Home Assistant OS (Read-Only /homeassistant & API)
          ↓
  sobo-ha-exporter
          ├─► Status Manager & Ingress UI (Port 8099)
          ├─► Data Sanitizer & Secret Scanner
          └─► SSH Deploy Key Authentication
          ↓
Private GitHub Reference Repository
```

## Runtime & Web Server Architecture

- **Main Application**: Daemon loop managing daily export execution and scheduling (`app/main.py`).
- **Ingress Web Server**: Multi-threaded Python HTTP server running on internal port `8099` (`app/web_server.py`).
- **Status Persistence**: Atomic JSON metadata writing under `/data/status/` (`status.json`, `export-preview.json`, `failed-export-manifest.json`, `generated-output.json`).
- **Security Scoping**: Mounted `/homeassistant` directory is strictly read-only. Ingress endpoints expose pre-sanitized metadata only.
