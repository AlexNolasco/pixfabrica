#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -f "$ROOT/web/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/web/.env"
  set +a
fi
if [[ -f "$ROOT/api/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/api/.env"
  set +a
fi
# shellcheck source=scripts/dev-ports.sh
source "$ROOT/scripts/dev-ports.sh"

open_browser() {
  sleep 2
  local url="http://localhost:${PIXFABRICA_WEB_PORT}"
  if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$url" >/dev/null 2>&1 || true
  elif command -v open >/dev/null 2>&1; then
    open "$url" >/dev/null 2>&1 || true
  elif command -v cmd.exe >/dev/null 2>&1; then
    cmd.exe /c start "" "$url" >/dev/null 2>&1 || true
  fi
}

echo "Starting Pixfabrica (Vite + API)..."
echo "Editor:   http://localhost:${PIXFABRICA_WEB_PORT}"
echo "API docs: http://localhost:${PIXFABRICA_API_PORT}/docs"
echo ""

open_browser &
cd "$ROOT/web"
exec pnpm dev:all
