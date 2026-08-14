#!/usr/bin/env bash
set -e

echo "Starting Sobo HA Exporter add-on..."
exec python3 -m app.main
