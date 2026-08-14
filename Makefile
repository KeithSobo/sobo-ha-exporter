.PHONY: install-dev format format-check lint type-check unit-test integration-test test coverage build check

install-dev:
	pip install -r sobo-ha-exporter/requirements.txt
	pip install pytest pytest-cov ruff mypy types-PyYAML types-requests pre-commit
	npm install

format:
	ruff format .
	npm run format

format-check:
	ruff format --check .
	npm run format:check

lint:
	ruff check .
	@which yamllint > /dev/null 2>&1 && yamllint . || echo "yamllint not installed, skipping"
	@which markdownlint > /dev/null 2>&1 && markdownlint "**/*.md" || echo "markdownlint not installed, skipping"
	@which shellcheck > /dev/null 2>&1 && shellcheck sobo-ha-exporter/*.sh || echo "shellcheck not installed, skipping"

type-check:
	mypy sobo-ha-exporter/app

unit-test:
	pytest tests/unit

integration-test:
	pytest tests/integration

test:
	pytest

coverage:
	pytest --cov=sobo_ha_exporter.app --cov-report=term-missing --cov-fail-under=80

build:
	docker build -t sobo-ha-exporter:local ./sobo-ha-exporter

check: format-check lint type-check test coverage
