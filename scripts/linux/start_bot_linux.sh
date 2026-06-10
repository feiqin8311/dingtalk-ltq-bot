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

if [[ -z "${LOCAL_CDP_BROWSER_BIN:-}" && -n "${CHROME_BIN:-}" && -x "${CHROME_BIN}" ]]; then
  export LOCAL_CDP_BROWSER_BIN="$CHROME_BIN"
fi

exec "$PYTHON_EXE" "$PROJECT_DIR/main.py"
