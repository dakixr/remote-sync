#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -f "${ROOT_DIR}/.env" ]]; then
  set -a
  source "${ROOT_DIR}/.env"
  set +a
fi
PORT="${PORT:-8000}"
HOST="${HOST:-127.0.0.1}"
LOCAL_URL="http://${HOST}:${PORT}"
TUNNEL_NAME="${TUNNEL_NAME:-remote-sync}"
TUNNEL_HOSTNAME="${TUNNEL_HOSTNAME:-rsync.antoniapavel.com}"
REMOTE_SYNC_TOKEN="${REMOTE_SYNC_TOKEN:-}"
SERVER_LOG="$(mktemp -t remote-sync-server.XXXXXX.log)"
TUNNEL_LOG="$(mktemp -t remote-sync-tunnel.XXXXXX.log)"
SERVER_PID=""
TUNNEL_PID=""

cleanup() {
  local exit_code=$?
  trap - EXIT INT TERM

  if [[ -n "${TUNNEL_PID}" ]] && kill -0 "${TUNNEL_PID}" 2>/dev/null; then
    kill "${TUNNEL_PID}" 2>/dev/null || true
    wait "${TUNNEL_PID}" 2>/dev/null || true
  fi

  if [[ -n "${SERVER_PID}" ]] && kill -0 "${SERVER_PID}" 2>/dev/null; then
    kill "${SERVER_PID}" 2>/dev/null || true
    wait "${SERVER_PID}" 2>/dev/null || true
  fi

  rm -f "${SERVER_LOG}" "${TUNNEL_LOG}"
  exit "${exit_code}"
}

trap cleanup EXIT INT TERM

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "missing required command: $1" >&2
    exit 1
  }
}

wait_for_http() {
  local url="$1"
  local retries="${2:-60}"
  local delay="${3:-0.5}"
  local i
  for ((i = 0; i < retries; i++)); do
    if curl -fsS "${url}/health" >/dev/null 2>&1; then
      return 0
    fi
    sleep "${delay}"
  done
  return 1
}

require_cmd uv
require_cmd cloudflared
require_cmd curl

cd "${ROOT_DIR}"

if lsof -nP -iTCP:"${PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "port ${PORT} is already in use; stop the existing listener or run with PORT=<free-port>" >&2
  exit 1
fi

if [[ -z "${REMOTE_SYNC_TOKEN}" ]]; then
  echo "WARNING: REMOTE_SYNC_TOKEN is not set — server has no authentication!" >&2
fi

echo "Starting server on ${LOCAL_URL}..."
REMOTE_SYNC_TOKEN="${REMOTE_SYNC_TOKEN}" uv run remote-sync server --host "${HOST}" --port "${PORT}" >"${SERVER_LOG}" 2>&1 &
SERVER_PID=$!

if ! wait_for_http "${LOCAL_URL}"; then
  echo "server did not start successfully" >&2
  cat "${SERVER_LOG}" >&2
  exit 1
fi

if [[ -z "${TUNNEL_NAME}" || -z "${TUNNEL_HOSTNAME}" ]]; then
  echo "TUNNEL_NAME and TUNNEL_HOSTNAME are required" >&2
  exit 1
fi

echo "Starting named tunnel ${TUNNEL_NAME} for https://${TUNNEL_HOSTNAME}..."
TUNNEL_TOKEN="$(cloudflared tunnel token "${TUNNEL_NAME}" 2>/dev/null || true)"
if [[ -z "${TUNNEL_TOKEN}" ]]; then
  echo "failed to fetch token for named tunnel ${TUNNEL_NAME}" >&2
  exit 1
fi
cloudflared tunnel --url "${LOCAL_URL}" --logfile "${TUNNEL_LOG}" run --token "${TUNNEL_TOKEN}" &
TUNNEL_PID=$!
PUBLIC_URL="https://${TUNNEL_HOSTNAME}"
sleep 2
if ! kill -0 "${TUNNEL_PID}" 2>/dev/null; then
  echo "named tunnel failed to start" >&2
  cat "${TUNNEL_LOG}" >&2
  exit 1
fi

echo
echo "Local:  ${LOCAL_URL}"
echo "Public: ${PUBLIC_URL}"
echo
echo "Press Control-C to stop both the server and the tunnel."

while true; do
  if ! kill -0 "${SERVER_PID}" 2>/dev/null; then
    echo "server exited unexpectedly" >&2
    cat "${SERVER_LOG}" >&2
    exit 1
  fi
  if ! kill -0 "${TUNNEL_PID}" 2>/dev/null; then
    echo "tunnel exited unexpectedly" >&2
    cat "${TUNNEL_LOG}" >&2
    exit 1
  fi
  sleep 1
done
