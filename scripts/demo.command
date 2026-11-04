#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
exec .venv/bin/workthread --workspace .runtime/demo demo --open
