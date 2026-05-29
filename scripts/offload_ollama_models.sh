#!/usr/bin/env bash
set -euo pipefail

print_info() {
  printf "[offload] %s\n" "$1"
}

print_warn() {
  printf "[offload][warn] %s\n" "$1"
}

if ! command -v ollama >/dev/null 2>&1; then
  print_warn "ollama CLI is not installed; skipping model offload."
  exit 0
fi

ps_output="$(ollama ps 2>/dev/null || true)"
loaded_models=()
while IFS= read -r model; do
  if [[ -n "$model" ]]; then
    loaded_models+=("$model")
  fi
done < <(printf "%s\n" "$ps_output" | awk 'NR > 1 && $1 != "NAME" {print $1}')

if [[ "${#loaded_models[@]}" -eq 0 ]]; then
  print_info "No loaded Ollama models to offload."
  exit 0
fi

for model in "${loaded_models[@]}"; do
  if ollama stop "$model" >/dev/null 2>&1; then
    print_info "Offloaded model: $model"
  else
    print_warn "Failed to offload model: $model"
  fi
done
