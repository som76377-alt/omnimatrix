#!/usr/bin/env bash
set -euo pipefail

export PATH="$PWD/.tools/node/bin:$PWD/.tools/cline/bin:$PATH"
exec python -m interfaces.web.server \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --config config/mobile.models.json \
  --workspace-root . \
  --allow-public-chat \
  --allow-free-quota
