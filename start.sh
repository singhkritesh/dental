#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

print_info() {
  printf "[start] %s\n" "$1"
}

print_warn() {
  printf "[start][warn] %s\n" "$1"
}

print_error() {
  printf "[start][error] %s\n" "$1" >&2
}

wait_for_http() {
  local name="$1"
  local url="$2"
  local retries="${3:-20}"
  local sleep_seconds="${4:-1}"

  local i
  for ((i = 1; i <= retries; i++)); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      print_info "$name is reachable at $url"
      return 0
    fi
    sleep "$sleep_seconds"
  done

  print_warn "$name did not become reachable in time: $url"
  return 1
}

wait_for_command() {
  local name="$1"
  local retries="${2:-20}"
  local sleep_seconds="${3:-1}"
  shift 3

  local i
  for ((i = 1; i <= retries; i++)); do
    if "$@" >/dev/null 2>&1; then
      print_info "$name is ready"
      return 0
    fi
    sleep "$sleep_seconds"
  done

  print_warn "$name did not become ready in time"
  return 1
}

command -v docker >/dev/null 2>&1 || {
  print_error "docker is required but not installed."
  exit 1
}

docker compose version >/dev/null 2>&1 || {
  print_error "docker compose plugin is required but not available."
  exit 1
}

command -v curl >/dev/null 2>&1 || {
  print_error "curl is required but not installed."
  exit 1
}

if [[ ! -f "$ROOT_DIR/.env" ]]; then
  print_warn ".env not found. Copying from .env.example."
  cp "$ROOT_DIR/.env.example" "$ROOT_DIR/.env"
fi

if [[ ! -f "$ROOT_DIR/frontend/.env" ]]; then
  print_warn "frontend/.env not found. Copying from frontend/.env.example."
  cp "$ROOT_DIR/frontend/.env.example" "$ROOT_DIR/frontend/.env"
fi

# shellcheck disable=SC1091
source "$ROOT_DIR/.env"

POSTGRES_DB="${POSTGRES_DB:-siligent}"
POSTGRES_USER="${POSTGRES_USER:-siligent}"
POSTGRES_PORT="${POSTGRES_PORT:-5434}"

print_info "Checking host Ollama at http://localhost:11434..."
wait_for_http "Host Ollama" "http://localhost:11434/api/tags" 10 1 || {
  print_warn "Host Ollama is not reachable. Start it with: ollama serve"
}

print_info "Starting Docker stack (frontend + api + db)..."
(
  cd "$ROOT_DIR"
  docker compose up -d --build "$@"
)

wait_for_command "Postgres" 40 1 \
  bash -lc "cd '$ROOT_DIR' && docker compose exec -T db pg_isready -U '$POSTGRES_USER' -d '$POSTGRES_DB'"
wait_for_http "API" "http://localhost:8000/" 45 1 || true
wait_for_http "Frontend" "http://localhost:3000" 45 1 || true

print_info "Startup complete."
print_info "Frontend: http://localhost:3000"
print_info "API docs: http://localhost:8000/docs"
print_info "Host Ollama: http://localhost:11434"
print_info "Postgres: localhost:$POSTGRES_PORT (database: $POSTGRES_DB)"
print_info "Compose status:"
(
  cd "$ROOT_DIR"
  docker compose ps
)
