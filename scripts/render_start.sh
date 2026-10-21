#!/usr/bin/env bash
set -euo pipefail

export PATH="$PWD/.tools/node/bin:$PWD/.tools/cline/bin:$PATH"
exec python scripts/render_supervisor.py
