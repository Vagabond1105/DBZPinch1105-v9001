#!/usr/bin/env bash
# Launch the Z-pinch GUI (or pass --headless ... for batch runs).
# PYTHONPATH is cleared so unrelated packages (e.g. ROS) cannot shadow the venv.
cd "$(dirname "$0")"
PYTHONPATH= exec .venv/bin/python main.py "$@"
