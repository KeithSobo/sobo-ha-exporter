# Security & Privacy Principles

## Core Security Rules

1. **Read-Only Home Assistant Access**: `/homeassistant` is mounted `read_only: true`. The add-on never modifies Home Assistant configuration files or SQLite databases.
2. **Fail-Closed Secret Scanner**: All staging content is statically scanned before commit. Real secrets, private keys, API tokens, or high-entropy credentials halt export execution immediately.
3. **No Credential Persistence in Status/UI**: The Ingress web interface and `/data/status/` manifests contain safe diagnostic metadata only (`relative_path`, `rule_name`, `line_number`, `size_bytes`). Matched secret strings, file contents, passwords, and private SSH keys are never written to status files or exposed via API.
4. **Deploy Key Scoping**: Auto-generated ED25519 deploy key pair (`/data/ssh/id_ed25519`) is scoped strictly to the target GitHub repository.
5. **Ingress Authentication**: Web UI endpoints are exposed internally on port `8099` behind Home Assistant Supervisor ingress authentication. No unauthenticated external ports are exposed.
