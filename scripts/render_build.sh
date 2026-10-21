#!/usr/bin/env bash
set -euo pipefail

ROOT="$(pwd)"
python -m pip install -r requirements.txt
mkdir -p .tools/node .tools/cline
curl -fsSL https://nodejs.org/dist/v22.18.0/node-v22.18.0-linux-x64.tar.xz \
  | tar -xJ --strip-components=1 -C .tools/node
PATH="$ROOT/.tools/node/bin:$PATH" npm install --global --prefix "$ROOT/.tools/cline" cline
PATH="$ROOT/.tools/node/bin:$ROOT/.tools/cline/bin:$PATH" cline --version

# FreeLLMAPI is built from an exact upstream commit and runs only as a
# loopback sidecar. Do not bind its port to Render's public interface.
FREELLMAPI_COMMIT="19eb7e1c3bd5e7421ee72c3878a099f511ea4275"
mkdir -p .tools/freellmapi
if [[ ! -d .tools/freellmapi/.git ]]; then
  git -C .tools/freellmapi init
  git -C .tools/freellmapi remote add origin https://github.com/tashfeenahmed/freellmapi.git
fi
git -C .tools/freellmapi fetch --depth 1 origin "$FREELLMAPI_COMMIT"
git -C .tools/freellmapi checkout --force --detach FETCH_HEAD
ACTUAL_COMMIT="$(git -C .tools/freellmapi rev-parse HEAD)"
if [[ "$ACTUAL_COMMIT" != "$FREELLMAPI_COMMIT" ]]; then
  echo "FreeLLMAPI source pin mismatch; refusing to build." >&2
  exit 1
fi

PATH="$ROOT/.tools/node/bin:$PATH" npm ci --prefix "$ROOT/.tools/freellmapi"
PATH="$ROOT/.tools/node/bin:$PATH" npm run build --prefix "$ROOT/.tools/freellmapi"
PATH="$ROOT/.tools/node/bin:$PATH" npm prune --omit=dev --prefix "$ROOT/.tools/freellmapi"
