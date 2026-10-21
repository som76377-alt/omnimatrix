#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ECC_COMMIT="90606c8315ee09cafc303515c5f33024db6b9882"
DEST="$ROOT/.tools/ecc"
mkdir -p "$ROOT/.tools"
if [[ ! -d "$DEST/.git" ]]; then
  mkdir -p "$DEST"
  git -C "$DEST" init
  git -C "$DEST" remote add origin https://github.com/affaan-m/ECC.git
fi
git -C "$DEST" fetch --depth 1 origin "$ECC_COMMIT"
git -C "$DEST" checkout --force --detach FETCH_HEAD
ACTUAL_COMMIT="$(git -C "$DEST" rev-parse HEAD)"
if [[ "$ACTUAL_COMMIT" != "$ECC_COMMIT" ]]; then
  echo "ECC source pin mismatch; refusing to install the reference catalogue." >&2
  exit 1
fi
if [[ ! -f "$DEST/LICENSE" || ! -d "$DEST/skills" ]]; then
  echo "Pinned ECC source is missing its license or skills directory." >&2
  exit 1
fi
echo "ECC reference catalogue installed at the pinned commit; hooks and plugin code were not installed or executed."
