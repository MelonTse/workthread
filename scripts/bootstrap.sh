#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
if [ ! -x .tools/bootstrap/bin/uv ]; then python3 -m pip install --target .tools/bootstrap uv; fi
export UV_PYTHON_INSTALL_DIR="$PWD/.tools/python"
export UV_CACHE_DIR="$PWD/.tools/cache"
.tools/bootstrap/bin/uv python install 3.13 --no-bin
.tools/bootstrap/bin/uv sync --frozen --python 3.13
