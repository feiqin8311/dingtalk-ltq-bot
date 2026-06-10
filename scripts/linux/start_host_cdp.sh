#!/usr/bin/env bash
set -euo pipefail

PORT="${1:-19444}"
MODE="${2:-visible}"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CHROME_BIN="${CHROME_BIN:-/usr/bin/google-chrome}"

if ! command -v "$CHROME_BIN" >/dev/null 2>&1; then
  echo "Chrome not found: $CHROME_BIN" >&2
  exit 1
fi

if ss -ltn "( sport = :$PORT )" | grep -q LISTEN; then
  echo "CDP port already in use: $PORT" >&2
  exit 1
fi

case "$MODE" in
  visible)
    PROFILE_DIR="$PROJECT_DIR/data/chrome-cdp-visible"
    EXTRA_ARGS=(
      --window-size=1440,900
      --new-window
      about:blank
    )
    export DISPLAY="${DISPLAY:-:1}"
    ;;
  headless)
    PROFILE_DIR="$PROJECT_DIR/data/chrome-cdp-headless-host"
    EXTRA_ARGS=(
      --headless=new
      about:blank
    )
    ;;
  *)
    echo "Usage: $0 [port] [visible|headless]" >&2
    exit 1
    ;;
esac

mkdir -p "$PROFILE_DIR"
LOG_FILE="/tmp/dingtalk-ltq-cdp-${PORT}.log"
PID_FILE="/tmp/dingtalk-ltq-cdp-${PORT}.pid"

setsid "$CHROME_BIN" \
  --user-data-dir="$PROFILE_DIR" \
  --remote-debugging-host=127.0.0.1 \
  --remote-debugging-port="$PORT" \
  --no-first-run \
  --no-default-browser-check \
  --disable-dev-shm-usage \
  --no-sandbox \
  "${EXTRA_ARGS[@]}" \
  >"$LOG_FILE" 2>&1 < /dev/null &

echo $! >"$PID_FILE"
echo "Started Chrome CDP on 127.0.0.1:$PORT"
echo "PID: $(cat "$PID_FILE")"
echo "Profile: $PROFILE_DIR"
echo "Log: $LOG_FILE"
