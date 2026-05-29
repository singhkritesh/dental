#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

print_info() {
  printf "[stop] %s\n" "$1"
}

print_error() {
  printf "[stop][error] %s\n" "$1" >&2
}

command -v docker >/dev/null 2>&1 || {
  print_error "docker is required but not installed."
  exit 1
}

docker compose version >/dev/null 2>&1 || {
  print_error "docker compose plugin is required but not available."
  exit 1
}

print_info "Stopping Docker stack (frontend + api + db)..."
(
  cd "$ROOT_DIR"
  docker compose down --remove-orphans "$@"
)

print_info "Offloading any loaded Ollama models..."
"$ROOT_DIR/scripts/offload_ollama_models.sh"

print_info "Shutdown complete."
