#!/usr/bin/env bash
# Resolve dev server ports — source from doctor.sh, run-all.sh, etc.
: "${PIXFABRICA_WEB_PORT:=5173}"
: "${PIXFABRICA_API_PORT:=8000}"
export PIXFABRICA_WEB_PORT PIXFABRICA_API_PORT
