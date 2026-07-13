#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

echo "Running doctor..."
"$ROOT/doctor.sh"

echo ""
echo "Installing Python packages..."
uv sync --all-packages

echo ""
echo "Installing web packages..."
(cd web && pnpm install)

echo ""
echo "Setup complete. Run ./run-all.sh to start the editor."
