#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_DIR"

load_env_file() {
  local env_file="$1"
  [[ -f "$env_file" ]] || return 0
  while IFS= read -r raw_line || [[ -n "$raw_line" ]]; do
    local line="${raw_line#"${raw_line%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"
    [[ -z "$line" || "${line:0:1}" == "#" ]] && continue
    [[ "$line" != *"="* ]] && continue
    local key="${line%%=*}"
    local value="${line#*=}"
    key="${key%"${key##*[![:space:]]}"}"
    value="${value#${value%%[![:space:]]*}}"
    value="${value%\"}"
    value="${value#\"}"
    value="${value%\'}"
    value="${value#\'}"
    export "$key=$value"
  done < "$env_file"
}

load_env_file "$PROJECT_DIR/.env"
load_env_file "$PROJECT_DIR/.env.linux"

PYTHON_EXE="${PYTHON_EXE:-python3}"
if [[ -x "$PROJECT_DIR/.venv/bin/python" ]]; then
  PYTHON_EXE="$PROJECT_DIR/.venv/bin/python"
fi

resolve_playwright_chromium() {
  "$PYTHON_EXE" - <<'PY'
import sys
try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        path = str(getattr(p.chromium, "executable_path", "") or "").strip()
        if path:
            sys.stdout.write(path)
except Exception:
    pass
PY
}

if [[ -z "${LOCAL_CDP_BROWSER_BIN:-}" ]]; then
  RESOLVED_CDP_BROWSER="$(resolve_playwright_chromium || true)"
  if [[ -n "${RESOLVED_CDP_BROWSER}" && -x "${RESOLVED_CDP_BROWSER}" ]]; then
    export LOCAL_CDP_BROWSER_BIN="$RESOLVED_CDP_BROWSER"
  elif [[ -n "${CHROME_BIN:-}" && -x "${CHROME_BIN}" ]]; then
    export LOCAL_CDP_BROWSER_BIN="$CHROME_BIN"
  fi
fi

if [[ -n "${CONDA_PREFIX:-}" && -d "${CONDA_PREFIX}/lib" ]]; then
  if [[ -n "${LD_LIBRARY_PATH:-}" ]]; then
    export LD_LIBRARY_PATH="${CONDA_PREFIX}/lib:${LD_LIBRARY_PATH}"
  else
    export LD_LIBRARY_PATH="${CONDA_PREFIX}/lib"
  fi
fi

API_HOST="${API_HOST:-0.0.0.0}"
API_PORT="${API_PORT:-18081}"

exec "$PYTHON_EXE" -m uvicorn api_server:app --host "$API_HOST" --port "$API_PORT"
