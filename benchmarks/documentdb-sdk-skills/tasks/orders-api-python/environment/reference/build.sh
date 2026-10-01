#!/usr/bin/env bash
set -euo pipefail
# Installs from the wheels baked into the image: the task runs with no internet.
pip3 install --no-cache-dir --no-index --find-links=/opt/wheels -r /app/requirements.txt
