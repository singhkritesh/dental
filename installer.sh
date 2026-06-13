#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

print_info() {
  printf "[installer] %s\n" "$1"
}

print_warn() {
  printf "[installer][warn] %s\n" "$1"
}

print_error() {
  printf "[installer][error] %s\n" "$1" >&2
}

usage() {
  cat <<'EOF'
Usage: ./installer.sh [options]

Installs missing host dependencies when possible, prepares environment files,
checks fixed ports, verifies Ollama, builds/starts the Docker stack, and runs
basic health checks.

Options:
  --check-only        Validate dependencies, ports, env, and Ollama without starting containers.
  --no-start         Install/prepare/check everything but do not start Docker Compose.
  --yes              Non-interactive mode. Approve supported dependency installs automatically.
  -h, --help         Show this help.

Important:
  This script does NOT install or pull Ollama models. If MODEL_NAME is missing,
  it prints the exact ollama pull command for the operator to run manually.
EOF
}

CHECK_ONLY=false
NO_START=false
ASSUME_YES=false

for arg in "$@"; do
  case "$arg" in
    --check-only)
      CHECK_ONLY=true
      NO_START=true
      ;;
    --no-start)
      NO_START=true
      ;;
    --yes|-y)
      ASSUME_YES=true
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      print_error "Unknown option: $arg"
      usage
      exit 2
      ;;
  esac
done

confirm() {
  local prompt="$1"
  if [[ "$ASSUME_YES" == "true" ]]; then
    return 0
  fi

  local reply
  read -r -p "$prompt [y/N] " reply
  case "$reply" in
    y|Y|yes|YES)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

detect_os() {
  case "$(uname -s)" in
    Darwin)
      printf "macos"
      ;;
    Linux)
      printf "linux"
      ;;
    *)
      printf "unknown"
      ;;
  esac
}

has_command() {
  command -v "$1" >/dev/null 2>&1
}

install_with_brew() {
  local package="$1"
  local label="$2"

  if ! has_command brew; then
    print_error "$label is missing and Homebrew is not installed. Install $label manually, then rerun this script."
    return 1
  fi

  if confirm "$label is missing. Install '$package' with Homebrew now?"; then
    brew install "$package"
  else
    print_error "$label is required."
    return 1
  fi
}

install_with_apt() {
  local package="$1"
  local label="$2"

  if ! has_command apt-get; then
    print_error "$label is missing and apt-get is not available. Install $label manually, then rerun this script."
    return 1
  fi

  if confirm "$label is missing. Install '$package' with apt-get now?"; then
    sudo apt-get update
    sudo apt-get install -y "$package"
  else
    print_error "$label is required."
    return 1
  fi
}

ensure_curl() {
  if has_command curl; then
    print_info "curl found: $(command -v curl)"
    return 0
  fi

  case "$(detect_os)" in
    macos)
      install_with_brew curl "curl"
      ;;
    linux)
      install_with_apt curl "curl"
      ;;
    *)
      print_error "curl is missing. Install curl manually, then rerun this script."
      return 1
      ;;
  esac
}

ensure_ollama() {
  if has_command ollama; then
    print_info "Ollama CLI found: $(command -v ollama)"
    return 0
  fi

  case "$(detect_os)" in
    macos)
      install_with_brew ollama "Ollama"
      ;;
    linux)
      print_warn "Ollama is missing. The official Linux installer requires a network download."
      if confirm "Install Ollama using the official installer from ollama.com now?"; then
        curl -fsSL https://ollama.com/install.sh | sh
      else
        print_error "Ollama is required. Install it manually, then rerun this script."
        return 1
      fi
      ;;
    *)
      print_error "Ollama is missing. Install Ollama manually, then rerun this script."
      return 1
      ;;
  esac
}

ensure_docker() {
  if has_command docker; then
    print_info "Docker CLI found: $(command -v docker)"
  else
    case "$(detect_os)" in
      macos)
        if has_command brew; then
          if confirm "Docker is missing. Install Docker Desktop with Homebrew Cask now?"; then
            brew install --cask docker
            print_warn "Docker Desktop may need to be opened once manually before the daemon is available."
          else
            print_error "Docker is required."
            return 1
          fi
        else
          print_error "Docker is missing. Install Docker Desktop manually, then rerun this script."
          return 1
        fi
        ;;
      linux)
        if has_command apt-get; then
          if confirm "Docker is missing. Install docker.io and docker-compose-plugin with apt-get now?"; then
            sudo apt-get update
            sudo apt-get install -y docker.io docker-compose-plugin
            print_warn "You may need to add your user to the docker group or use sudo for Docker commands."
          else
            print_error "Docker is required."
            return 1
          fi
        else
          print_error "Docker is missing. Install Docker manually, then rerun this script."
          return 1
        fi
        ;;
      *)
        print_error "Docker is missing. Install Docker manually, then rerun this script."
        return 1
        ;;
    esac
  fi

  if ! docker compose version >/dev/null 2>&1; then
    print_error "Docker Compose plugin is not available. Install Docker Compose plugin, then rerun this script."
    return 1
  fi
  print_info "Docker Compose plugin is available."
}

ensure_docker_daemon() {
  if docker info >/dev/null 2>&1; then
    print_info "Docker daemon is running."
    return 0
  fi

  print_error "Docker daemon is not running or not reachable."
  case "$(detect_os)" in
    macos)
      print_error "Open Docker Desktop, wait until it is running, then rerun this script."
      ;;
    linux)
      print_error "Start Docker with: sudo systemctl start docker"
      ;;
  esac
  return 1
}

copy_env_if_missing() {
  local source_file="$1"
  local target_file="$2"

  if [[ -f "$target_file" ]]; then
    print_info "$(basename "$target_file") already exists."
    return 0
  fi

  if [[ ! -f "$source_file" ]]; then
    print_error "Missing template env file: $source_file"
    return 1
  fi

  cp "$source_file" "$target_file"
  print_info "Created $target_file from $source_file"
}

load_env() {
  set -a
  # shellcheck disable=SC1091
  source "$ROOT_DIR/.env"
  set +a
}

port_in_use() {
  local port="$1"

  if has_command lsof; then
    lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
    return $?
  fi

  if has_command nc; then
    nc -z localhost "$port" >/dev/null 2>&1
    return $?
  fi

  if has_command ss; then
    ss -ltn | awk '{print $4}' | grep -Eq "[:.]${port}$"
    return $?
  fi

  print_warn "No lsof, nc, or ss command found; cannot verify port $port."
  return 1
}

compose_service_owns_port() {
  local port="$1"

  (
    cd "$ROOT_DIR"
    docker compose ps --format json 2>/dev/null || true
  ) | grep -q "0.0.0.0:${port}->"
}

check_required_port() {
  local label="$1"
  local port="$2"
  local allow_compose_owner="${3:-false}"

  if ! port_in_use "$port"; then
    print_info "$label port $port is available."
    return 0
  fi

  if [[ "$allow_compose_owner" == "true" ]] && compose_service_owns_port "$port"; then
    print_info "$label port $port is already owned by this Compose stack."
    return 0
  fi

  print_error "$label port $port is already in use. Free this port before continuing."
  return 1
}

wait_for_http() {
  local name="$1"
  local url="$2"
  local retries="${3:-30}"
  local sleep_seconds="${4:-1}"

  local i
  for ((i = 1; i <= retries; i++)); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      print_info "$name is reachable at $url"
      return 0
    fi
    sleep "$sleep_seconds"
  done

  print_error "$name did not become reachable in time: $url"
  return 1
}

wait_for_command() {
  local name="$1"
  local retries="${2:-40}"
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

  print_error "$name did not become ready in time."
  return 1
}

ensure_ollama_server() {
  if curl -fsS "http://localhost:11434/api/tags" >/dev/null 2>&1; then
    print_info "Host Ollama server is reachable."
    return 0
  fi

  print_warn "Host Ollama server is not reachable."
  if [[ "$(detect_os)" == "macos" ]] && has_command open; then
    if confirm "Try opening the Ollama app now?"; then
      open -a Ollama || true
      wait_for_http "Host Ollama" "http://localhost:11434/api/tags" 30 1
      return $?
    fi
  fi

  print_error "Start Ollama manually, then rerun this script. Suggested command: ollama serve"
  return 1
}

verify_model_present() {
  local model_name="$1"

  if ollama list | awk 'NR > 1 {print $1}' | grep -Fxq "$model_name"; then
    print_info "Configured model is installed locally: $model_name"
    return 0
  fi

  print_error "Configured model is not installed locally: $model_name"
  print_error "This installer will not pull models automatically. Run manually: ollama pull $model_name"
  return 1
}

warn_on_default_secrets() {
  if [[ "${POSTGRES_PASSWORD:-}" == "siligent" ]]; then
    print_warn "POSTGRES_PASSWORD is still the default value. Change it before production use."
  fi

  if [[ "${API_KEY:-}" == "" ]]; then
    print_warn "API_KEY is blank. Browser auth still applies, but the extra API-key gate is disabled."
  fi
}

print_info "Preparing Siligent Dental AI Assistant installer checks..."

ensure_curl
ensure_docker
ensure_ollama

copy_env_if_missing "$ROOT_DIR/.env.example" "$ROOT_DIR/.env"
copy_env_if_missing "$ROOT_DIR/frontend/.env.example" "$ROOT_DIR/frontend/.env"
load_env

POSTGRES_DB="${POSTGRES_DB:-siligent}"
POSTGRES_USER="${POSTGRES_USER:-siligent}"
POSTGRES_PORT="${POSTGRES_PORT:-5434}"
MODEL_NAME="${MODEL_NAME:-qwen3.5:4b}"

warn_on_default_secrets

ensure_docker_daemon
ensure_ollama_server
verify_model_present "$MODEL_NAME"

check_required_port "Frontend" "3000" true
check_required_port "API" "8000" true
check_required_port "Postgres" "$POSTGRES_PORT" true
check_required_port "Ollama" "11434" false

if [[ "$CHECK_ONLY" == "true" ]]; then
  print_info "Check-only mode complete. No containers were started."
  exit 0
fi

if [[ "$NO_START" == "true" ]]; then
  print_info "Installer preparation complete. Skipping container startup because --no-start was provided."
  exit 0
fi

print_info "Building and starting Docker stack..."
(
  cd "$ROOT_DIR"
  docker compose up -d --build
)

wait_for_command "Postgres" 40 1 \
  bash -lc "cd '$ROOT_DIR' && docker compose exec -T db pg_isready -U '$POSTGRES_USER' -d '$POSTGRES_DB'"
wait_for_http "API" "http://localhost:8000/" 45 1
wait_for_http "Frontend" "http://localhost:3000" 45 1

print_info "Installer complete."
print_info "Frontend: http://localhost:3000"
print_info "API docs: http://localhost:8000/docs"
print_info "Host Ollama: http://localhost:11434"
print_info "Postgres: localhost:$POSTGRES_PORT (database: $POSTGRES_DB)"
print_info "Compose status:"
(
  cd "$ROOT_DIR"
  docker compose ps
)
