#!/usr/bin/env bash
# Launch the OpenBOR underpass playable test stage.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENGINE="$ROOT/openbor_engine/OpenBOR.AppImage"
DATA_DIR="$ROOT/openbor"
if [[ ! -x "$ENGINE" ]]; then
  echo "Missing OpenBOR engine at $ENGINE" >&2
  exit 1
fi
if [[ ! -d "$DATA_DIR/data" ]]; then
  echo "Missing OpenBOR data pack at $DATA_DIR/data" >&2
  exit 1
fi
cd "$DATA_DIR"
# Some builds read Saves/ next to engine; keep cwd = openbor (parent of data/)
exec "$ENGINE"
