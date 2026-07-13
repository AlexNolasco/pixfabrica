#!/usr/bin/env bash
# Preflight checks for local Pixfabrica development.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if [[ -f "$ROOT/web/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/web/.env"
  set +a
fi
# shellcheck source=scripts/dev-ports.sh
source "$ROOT/scripts/dev-ports.sh"

FAIL=0
PORTS_IN_USE=0

port_available() {
  local port=$1
  if command -v ss >/dev/null 2>&1; then
    ! ss -tln 2>/dev/null | grep -q ":${port} "
  elif command -v netstat >/dev/null 2>&1; then
    ! netstat -an 2>/dev/null | grep -q ":${port}.*LISTEN"
  else
    return 0
  fi
}

echo "Pixfabrica doctor"
echo "================="
echo ""

# --- hard requirements ---

if command -v uv >/dev/null 2>&1; then
  echo "✓ uv              $(uv --version 2>/dev/null | head -1)"
else
  echo "✗ uv              not found — https://docs.astral.sh/uv/getting-started/installation/"
  FAIL=1
fi

if uv python find 3.12 >/dev/null 2>&1 || command -v python3.12 >/dev/null 2>&1; then
  if command -v python3.12 >/dev/null 2>&1; then
    echo "✓ Python 3.12     $(python3.12 --version 2>/dev/null)"
  else
    echo "✓ Python 3.12     available via uv"
  fi
else
  echo "✗ Python 3.12     not found — run: uv python install 3.12"
  FAIL=1
fi

if command -v pnpm >/dev/null 2>&1; then
  echo "✓ pnpm            $(pnpm --version)"
else
  echo "✗ pnpm            not found — https://pnpm.io/installation"
  FAIL=1
fi

echo ""

# --- warnings (optional for editor) ---

if command -v ffmpeg >/dev/null 2>&1 && command -v ffprobe >/dev/null 2>&1; then
  echo "✓ ffmpeg          on PATH"
else
  echo "⚠ ffmpeg          not on PATH — editor works; renders will fail"
fi

if uv run python -c "from pixfabrica_renderer.gl_probe import gl_available; raise SystemExit(0 if gl_available() else 1)" >/dev/null 2>&1; then
  echo "✓ opengl          context available"
else
  echo "⚠ opengl          not available — GL tracks and GPU effects disabled"
fi

if curl -sf --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  echo "✓ ollama          reachable at http://127.0.0.1:11434"
else
  echo "⚠ ollama          not reachable — compose agent disabled"
fi

echo ""

# --- info ---

if port_available "$PIXFABRICA_WEB_PORT"; then
  echo "✓ port ${PIXFABRICA_WEB_PORT} (web)  available"
else
  echo "⚠ port ${PIXFABRICA_WEB_PORT} (web)  in use — close the other dev server"
  PORTS_IN_USE=1
fi

if port_available "$PIXFABRICA_API_PORT"; then
  echo "✓ port ${PIXFABRICA_API_PORT} (api)  available"
else
  echo "⚠ port ${PIXFABRICA_API_PORT} (api)  in use — close the other dev server"
  PORTS_IN_USE=1
fi

if [[ "$PORTS_IN_USE" -ne 0 ]]; then
  echo ""
  echo "Ports busy? Usually a previous run-all / pnpm dev:all is still running."
  echo "Or pick different ports (same values for doctor, setup, and run-all):"
  echo "  export PIXFABRICA_WEB_PORT=5174"
  echo "  export PIXFABRICA_API_PORT=8001"
  echo "  ./run-all.sh"
  echo "Or copy web/.env.example to web/.env and edit the port numbers there."
fi

echo ""

if [[ "$FAIL" -ne 0 ]]; then
  echo "Doctor failed — fix the items marked ✗ above."
  exit 1
fi

echo "Doctor passed — run ./setup.sh next (or ./run-all.sh if already set up)."
exit 0
