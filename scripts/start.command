#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
exec .venv/bin/workthread serve --open
