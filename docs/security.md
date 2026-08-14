# Security Principles & Guidelines

`sobo-ha-exporter` adheres to zero-trust design for exported Home Assistant metadata.

## Core Safeguards

1. **Read-Only Configuration Mount**: Home Assistant configuration is mounted into the container as `read_only`. The add-on cannot alter live HA files under any circumstances.
2. **Exclusion Rules**:
   - `secrets.yaml` is hard-blocked and strictly excluded from collection.
   - `.storage/`, `.cloud/`, `.auth`, `*.db`, `*.log`, `backups/` and temporary runtime files are strictly excluded.
3. **Redaction & Sanitization**:
   - High-precision regex pattern matchers redact GPS coordinates, MAC addresses, webhook IDs, credentials in URLs, and user IDs.
   - Live entity state attribute values (such as exact sensor values) are stripped by default, retaining schema and metadata.
4. **Secret Scanner Pre-Commit Gate**:
   - Prior to staging and committing files to Git, the application performs a static secret scan over all output files.
   - If an API key, private key, token, or high-entropy string is detected with high confidence, the commit process is aborted and logged to `/data/status/status.json`.
5. **SSH Deploy Key Scope**:
   - Authentication is strictly limited to an ED25519 repository deploy key pair generated in `/data/ssh/id_ed25519`.
   - Host key verification is mandatorily enforced against GitHub's known host keys (`known_hosts`). Strict host key checking is never disabled.
   - Private keys are never output to logs or exported.
