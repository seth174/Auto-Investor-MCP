#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"
source .venv/bin/activate
pip3 install -r requirements.txt

set -a
# shellcheck disable=SC1091
source .env
set +a

echo "Starting Auto Investor MCP on ${HOST:-127.0.0.1}:${PORT:-8001}"
python3 src/server.py
