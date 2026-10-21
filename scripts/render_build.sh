#!/usr/bin/env bash
set -euo pipefail

python -m pip install -r requirements.txt
mkdir -p .tools/node .tools/cline
curl -fsSL https://nodejs.org/dist/v22.18.0/node-v22.18.0-linux-x64.tar.xz \
  | tar -xJ --strip-components=1 -C .tools/node
PATH="$PWD/.tools/node/bin:$PATH" npm install --global --prefix "$PWD/.tools/cline" cline
PATH="$PWD/.tools/node/bin:$PWD/.tools/cline/bin:$PATH" cline --version
