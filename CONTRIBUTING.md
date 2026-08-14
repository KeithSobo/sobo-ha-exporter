# Contributing to Sobo Home Assistant Exporter

Thank you for your interest in contributing!

## Code Structure

```text
sobo-ha-exporter/
├── repository.yaml         # HA repository manifest
├── docs/                   # Architecture, security, and format docs
├── tests/                  # Unit and integration test suites
└── sobo-ha-exporter/       # Add-on root directory
    ├── config.yaml         # HA add-on manifest & configuration options
    ├── build.yaml          # Build specs
    ├── Dockerfile          # Add-on container image definition
    ├── run.sh              # Container startup script
    └── app/                # Python application code
```

## Local Development Setup

1. **Install Python dependencies:**
   ```bash
   pip install -r sobo-ha-exporter/requirements.txt
   pip install pytest pytest-cov ruff mypy types-PyYAML types-requests pre-commit
   ```

2. **Install Node.js dependencies (for Prettier formatting):**
   ```bash
   npm install
   ```

3. **Install Pre-commit hooks:**
   ```bash
   pre-commit install
   ```

## Developer Commands

We provide standard `make` targets for quality checks and testing:

* `make install-dev`: Install local python and node development tools.
* `make format`: Format code with Ruff and Prettier.
* `make format-check`: Verify formatting without making changes.
* `make lint`: Run Ruff, yamllint, markdownlint, and shellcheck.
* `make type-check`: Run Mypy type checker.
* `make unit-test`: Execute unit tests.
* `make integration-test`: Execute local integration tests.
* `make test`: Run all tests.
* `make coverage`: Run test suite with coverage enforcement (minimum 80%).
* `make build`: Build local Docker image.
* `make check`: Aggregate check command expected before committing.

## Guidelines

- All Python application code must be type-annotated.
- Tests must maintain at least 80% coverage across `sobo-ha-exporter/app`.
- Do not commit secrets, SSH private keys, or credentials.
- Ensure `make check` passes before submitting pull requests.
