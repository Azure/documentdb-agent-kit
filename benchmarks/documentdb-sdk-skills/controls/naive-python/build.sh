#!/usr/bin/env bash
set -euo pipefail
pip3 install --no-cache-dir --no-index --find-links=/opt/wheels -r /app/requirements.txt
