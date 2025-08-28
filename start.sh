#!/bin/bash
# Startup script for Whisper API service on macOS (e.g., Mac Studio M3 Ultra).
# Handles system optimization, environment setup, and service launch.

set -euo pipefail

# --- Script configuration -----------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="whisper-api"
LOG_DIR="${SCRIPT_DIR}/logs"
PID_FILE="${LOG_DIR}/${SERVICE_NAME}.pid"

# Colors
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'

# Logging functions
log()   { echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $*${NC}"; }
warn()  { echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING: $*${NC}" >&2; }
error() { echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $*${NC}" >&2; }
info()  { echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')] INFO: $*${NC}"; }

# --- Helper Functions --------------------------------------------------------
create_directories() {
  log "Creating necessary directories..."
  mkdir -p "${LOG_DIR}" "${SCRIPT_DIR}/data" "${SCRIPT_DIR}/cache"
}

check_system_requirements() {
  log "Checking system requirements..."

  if ! command -v python3 &>/dev/null; then
    error "python3 is required but not found."
    exit 1
  fi

  # Prefer python3.12 if available, otherwise use python3
  PY_BIN="python3"
  if command -v python3.12 &>/dev/null; then
    PY_BIN="python3.12"
    info "Using python3.12..."
  else
    info "Using python3..."
  fi
  export PY_BIN

  # Memory info (macOS specific)
  if [[ "$OSTYPE" == "darwin"* ]]; then
    AVAILABLE_MEMORY=$(sysctl -n hw.memsize || echo 0)
    AVAILABLE_GB=$((AVAILABLE_MEMORY / 1024 / 1024 / 1024))
    if [[ $AVAILABLE_GB -lt 32 ]]; then
      warn "Recommended memory is 32GB+, found ${AVAILABLE_GB}GB"
    else
      info "Memory check passed: ${AVAILABLE_GB}GB available"
    fi
  else
    warn "This script is optimized for macOS, detected: $OSTYPE"
  fi
}

optimize_system_for_mac() {
  if [[ "$OSTYPE" != "darwin"* ]]; then
    info "Skipping macOS-specific optimizations for non-Mac system."
    return
  fi

  log "Applying macOS optimizations..."

  if command -v caffeinate &>/dev/null; then
    info "Starting caffeinate to prevent system sleep"
    caffeinate -i &
    echo $! > "${LOG_DIR}/caffeinate.pid"
  else
    warn "caffeinate not available; system may sleep during long runs"
  fi

  export METAL_DEVICE_WRAPPER=1
  export MLX_METAL_DEBUG=0
  export MLX_NUM_THREADS=4
  export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES
  export PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.0

  info "System optimizations applied"
}

# Read PORT from .env file if it exists
load_port_from_env() {
  local env_file="${SCRIPT_DIR}/.env"
  if [[ -f "$env_file" ]]; then
    # Grep for PORT=, take the last one, remove comments, quotes, and spaces.
    local raw_port
    raw_port=$(grep -E '^\s*PORT\s*=' "$env_file" | tail -1 || true)
    if [[ -n "$raw_port" ]]; then
      raw_port="${raw_port%%#*}"
      raw_port="${raw_port#*=}"
      raw_port="${raw_port//\"/}"
      raw_port="${raw_port//\'/}"
      raw_port="${raw_port// /}"
      if [[ -n "$raw_port" ]]; then
        export PORT="$raw_port"
        info "Loaded PORT=${PORT} from .env file"
      fi
    fi
  fi
  # Set default port if not set
  : "${PORT:=8000}"
}

setup_python_environment() {
  log "Setting up Python environment..."
  cd "$SCRIPT_DIR"

  # Prefer existing .venv if present; otherwise use venv/
  VENV_DIR=""
  if [[ -d ".venv" ]]; then
    VENV_DIR=".venv"
  elif [[ -d "venv" ]]; then
    VENV_DIR="venv"
  fi

  if [[ -n "$VENV_DIR" ]]; then
      info "Using existing virtual environment: $VENV_DIR"
      # shellcheck disable=SC1091
      source "$VENV_DIR/bin/activate"
  else
      info "Creating Python virtual environment in 'venv'..."
      "$PY_BIN" -m venv venv
      # shellcheck disable=SC1091
      source "venv/bin/activate"
  fi

  pip install --upgrade pip

  if [[ -f "requirements.txt" ]]; then
    info "Installing Python dependencies..."
    pip install -r requirements.txt
  else
    warn "requirements.txt not found; skipping dependency installation"
  fi
}

health_check() {
  local max_attempts=10
  local attempt=1
  local url="http://localhost:${PORT}/health"

  info "Performing health check on ${url}..."
  while [[ $attempt -le $max_attempts ]]; do
    if curl -s -f "$url" >/dev/null; then
      log "Health check passed (attempt $attempt/$max_attempts)"
      return 0
    fi
    warn "Health check failed (attempt $attempt/$max_attempts); retrying in 5s..."
    sleep 5
    ((attempt++))
  done

  error "Health check failed after ${max_attempts} attempts"
  return 1
}

# --- Service Control Functions -----------------------------------------------
start_service() {
  log "Starting ${SERVICE_NAME}..."

  cd "$SCRIPT_DIR"
  # Ensure virtual environment is active
  if [[ -z "${VIRTUAL_ENV:-}" ]]; then
    if [[ -d ".venv" ]]; then source .venv/bin/activate; fi
    if [[ -d "venv" ]]; then source venv/bin/activate; fi
  fi

  if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    warn "Service already running (PID: $(cat "$PID_FILE"))"
    return 1
  fi

    nohup "${PY_BIN:-python3}" -m uvicorn app.main:app \
    --host 0.0.0.0 \
    --port "${PORT}" \
    --log-level "${LOG_LEVEL:-info}" \
    --access-log \
    --no-use-colors \
    --loop asyncio \
    --http h11 \
    --timeout-keep-alive 3 \
    --backlog 2048 \
    --limit-concurrency 16 \
    > "${LOG_DIR}/service.log" 2>&1 &

  echo $! > "$PID_FILE"
  log "Service started with PID: $(cat "$PID_FILE")"

  sleep 3 # Give the server a moment to start
  if health_check; then
    log "${SERVICE_NAME} is running successfully!"
    info "Logs: ${LOG_DIR}/service.log"
    info "Health endpoint: http://localhost:${PORT}/health"
    info "API docs:       http://localhost:${PORT}/docs"
  else
    error "Service failed to start properly. Check logs for details."
    stop_service
    exit 1
  fi
}

stop_service() {
  log "Stopping ${SERVICE_NAME}..."

  if [[ -f "$PID_FILE" ]]; then
    local pid
    pid="$(cat "$PID_FILE")"
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" || true
      sleep 2
      if kill -0 "$pid" 2>/dev/null; then
        warn "Forcing termination of PID $pid"
        kill -9 "$pid" || true
      fi
    fi
    rm -f "$PID_FILE"
  fi

  if [[ -f "${LOG_DIR}/caffeinate.pid" ]]; then
    local cpid
    cpid="$(cat "${LOG_DIR}/caffeinate.pid")"
    if kill -0 "$cpid" 2>/dev/null; then
      kill "$cpid" 2>/dev/null || true
    fi
    rm -f "${LOG_DIR}/caffeinate.pid"
  fi

  log "Service stopped"
}

restart_service() {
  log "Restarting ${SERVICE_NAME}..."
  stop_service
  sleep 2
  start_service
}

show_status() {
  if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    log "${SERVICE_NAME} is running (PID: $(cat "$PID_FILE"))"
    if [[ -f "${LOG_DIR}/service.log" ]]; then
      echo -e "\n${BLUE}Recent logs:${NC}"
      tail -10 "${LOG_DIR}/service.log"
    fi
    echo -e "\n${BLUE}Health status:${NC}"
    curl -s "http://localhost:${PORT}/health" | python3 -m json.tool 2>/dev/null \
      || echo "Health check failed"
  else
    warn "${SERVICE_NAME} is not running"
    return 1
  fi
}

# --- Main Logic --------------------------------------------------------------

# Trap signals for cleanup. Does NOT trap EXIT on 'start' to allow backgrounding.
# Ensure correct .env is in place (only when ENVIRONMENT is explicitly set)
if [[ -n "${ENVIRONMENT:-}" ]]; then
  ENV_FILE=".env.${ENVIRONMENT}"
  if [[ -f "$SCRIPT_DIR/$ENV_FILE" ]]; then
    cp "$SCRIPT_DIR/$ENV_FILE" "$SCRIPT_DIR/.env"
    info "Using environment: ${ENVIRONMENT} (copied ${ENV_FILE} to .env)"
  else
    error "Requested ENVIRONMENT='${ENVIRONMENT}' but ${ENV_FILE} not found."
    exit 1
  fi
else
  # No ENVIRONMENT provided → keep existing .env without warnings
  [[ -f "$SCRIPT_DIR/.env" ]] && info "Using existing .env (no ENVIRONMENT set)"
fi


load_port_from_env

case "${1:-start}" in
  start)
    create_directories
    check_system_requirements
    optimize_system_for_mac
    setup_python_environment
    start_service
    ;;
  stop)
    stop_service
    ;;
  restart)
    restart_service
    ;;
  status)
    show_status
    ;;
  setup)
    create_directories
    check_system_requirements
    setup_python_environment
    log "Setup completed successfully"
    ;;
  *)
    echo "Usage: $0 {start|stop|restart|status|setup}"
    exit 1
    ;;
esac
