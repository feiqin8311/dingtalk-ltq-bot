#!/usr/bin/env bash
set -euo pipefail

PORT="${1:-9444}"
PID_FILE="/tmp/dingtalk-ltq-cdp-${PORT}.pid"

if [[ -f "$PID_FILE" ]]; then
  PID="$(cat "$PID_FILE")"
  if kill "$PID" >/dev/null 2>&1; then
    echo "Stopped Chrome CDP PID $PID"
  else
    echo "Process already exited: $PID"
  fi
  rm -f "$PID_FILE"
  exit 0
fi

if pgrep -f "remote-debugging-port=$PORT" >/dev/null 2>&1; then
  pkill -f "remote-debugging-port=$PORT"
  echo "Stopped Chrome CDP on port $PORT"
  exit 0
fi

echo "No Chrome CDP process found for port $PORT"
