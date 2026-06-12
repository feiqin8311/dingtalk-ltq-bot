#!/usr/bin/env bash
set -euo pipefail

SERVER_HOST="${SERVER_HOST:-121.41.4.126}"
SERVER_USER="${SERVER_USER:-root}"
REMOTE_BIND_PORT="${REMOTE_BIND_PORT:-18781}"
LOCAL_API_PORT="${LOCAL_API_PORT:-18081}"
SERVER_SSH_PORT="${SERVER_SSH_PORT:-22}"

exec ssh \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -N \
  -p "${SERVER_SSH_PORT}" \
  -R "127.0.0.1:${REMOTE_BIND_PORT}:127.0.0.1:${LOCAL_API_PORT}" \
  "${SERVER_USER}@${SERVER_HOST}"
