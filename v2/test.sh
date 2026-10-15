#!/usr/bin/env bash
# Run the physics validation suite (~1 min).
cd "$(dirname "$0")"
PYTHONPATH= PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 exec .venv/bin/python -m pytest "$@"
