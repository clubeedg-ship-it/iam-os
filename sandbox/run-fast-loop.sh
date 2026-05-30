#!/bin/bash
# Bring up the IAM-OS stack on the host with synthetic touches.
#
# This is the "fast loop" sandbox from specs.md §9: no hardware, no VM.
# Runs lidar-service in simulation mode, the touch-bridge, and the
# web-server with the launcher SPA, all wired through /tmp paths so the
# script can run on macOS and Linux without sudo. The launcher opens at
# the printed URL.
#
# Ctrl-C tears everything down through the trap below.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

RUN_DIR="${IAM_OS_RUN_DIR:-/tmp/iam-os}"
LIDAR_SOCKET="$RUN_DIR/lidar.sock"
STATUS_FILE="$RUN_DIR/lidar-status.json"
CAL_DIR="$RUN_DIR/calibration"
CAL_POINTER="$CAL_DIR/active.json"
LAUNCHER_DIST="$REPO_ROOT/launcher/dist"
GAMES_DIR="$REPO_ROOT/games"

BRIDGE_PORT="${IAM_OS_BRIDGE_PORT:-8765}"
WEB_PORT="${IAM_OS_WEB_PORT:-8080}"
LOG_DIR="${IAM_OS_LOG_DIR:-$RUN_DIR/logs}"

note() { printf '[fast-loop] %s\n' "$*"; }
fail() { printf '[fast-loop] error: %s\n' "$*" >&2; exit 1; }

ensure_venv() {
    local svc="$1" pkg="$2"
    local svc_dir="$REPO_ROOT/services/$svc"
    if [ ! -x "$svc_dir/.venv/bin/python" ]; then
        note "creating venv for $svc"
        python3 -m venv "$svc_dir/.venv"
        "$svc_dir/.venv/bin/pip" install --quiet --upgrade pip
        "$svc_dir/.venv/bin/pip" install --quiet -e "$svc_dir"
    fi
    if ! "$svc_dir/.venv/bin/python" -c "import $pkg" 2>/dev/null; then
        note "installing $svc package into venv"
        "$svc_dir/.venv/bin/pip" install --quiet -e "$svc_dir"
    fi
}

ensure_launcher_dist() {
    if [ ! -f "$LAUNCHER_DIST/index.html" ]; then
        note "building launcher SPA"
        (cd "$REPO_ROOT/launcher" && npm --silent install && npm --silent run build)
    fi
}

write_web_config() {
    cat >"$RUN_DIR/web-server.toml" <<EOF
[server]
host = "127.0.0.1"
port = $WEB_PORT

[paths]
launcher_dist = "$LAUNCHER_DIST"
games_dir = "$GAMES_DIR"

[lidar]
socket_path = "$LIDAR_SOCKET"
status_file = "$STATUS_FILE"
reconnect_initial_s = 0.5
reconnect_max_s = 5.0

[calibration]
presets_dir = "$CAL_DIR"
active_pointer_path = "$CAL_POINTER"

[logging]
level = "INFO"
EOF
}

PIDS=()
cleanup() {
    note "stopping ${#PIDS[@]} service(s)"
    for pid in "${PIDS[@]}"; do
        kill -TERM "$pid" 2>/dev/null || true
    done
    for pid in "${PIDS[@]}"; do
        wait "$pid" 2>/dev/null || true
    done
}
trap cleanup EXIT INT TERM

mkdir -p "$RUN_DIR" "$CAL_DIR" "$LOG_DIR"
rm -f "$LIDAR_SOCKET" "$STATUS_FILE"

[ -x "$(command -v python3)" ] || fail "python3 not found on PATH"
[ -x "$(command -v npm)" ] || fail "npm not found on PATH"

ensure_venv lidar-service iam_lidar
ensure_venv touch-bridge iam_bridge
ensure_venv web-server iam_webserver
ensure_launcher_dist
write_web_config

note "lidar-service starting (--simulate, socket=$LIDAR_SOCKET)"
( cd "$REPO_ROOT/services/lidar-service" && \
  PYTHONPATH=. \
  IAM_LIDAR_OUTPUT_SOCKET_PATH="$LIDAR_SOCKET" \
  IAM_LIDAR_STATUS_FILE_PATH="$STATUS_FILE" \
  IAM_LIDAR_CALIBRATION_PRESETS_DIR="$CAL_DIR" \
  IAM_LIDAR_CALIBRATION_ACTIVE_POINTER_PATH="$CAL_POINTER" \
  .venv/bin/python -m iam_lidar --simulate \
  >"$LOG_DIR/lidar.log" 2>&1 ) &
PIDS+=($!)

# Wait for the socket to appear before starting the bridge, so the bridge
# does not hammer reconnects against a not-yet-bound upstream.
for _ in $(seq 1 50); do
    [ -S "$LIDAR_SOCKET" ] && break
    sleep 0.1
done

note "touch-bridge starting (port=$BRIDGE_PORT)"
( cd "$REPO_ROOT/services/touch-bridge" && \
  PYTHONPATH=. .venv/bin/python -m iam_bridge \
    --socket "$LIDAR_SOCKET" --port "$BRIDGE_PORT" \
  >"$LOG_DIR/bridge.log" 2>&1 ) &
PIDS+=($!)

note "web-server starting (port=$WEB_PORT)"
( cd "$REPO_ROOT/services/web-server" && \
  .venv/bin/python -m iam_webserver --config "$RUN_DIR/web-server.toml" \
  >"$LOG_DIR/web-server.log" 2>&1 ) &
PIDS+=($!)

sleep 1
note "launcher: http://127.0.0.1:$WEB_PORT/"
note "touch contract: ws://127.0.0.1:$BRIDGE_PORT"
note "logs:  $LOG_DIR/{lidar,bridge,web-server}.log"
note "press Ctrl-C to stop"

# Wait until every service is gone (or the user signals).
wait
