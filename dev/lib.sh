#!/usr/bin/env bash
# lib.sh — gemeinsame Konstanten und Helfer fuer dev/*.sh.
# Wird gesourcet, nicht ausgefuehrt.

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  echo "lib.sh wird gesourcet, nicht direkt ausgefuehrt" >&2
  exit 1
fi

DEV_REPO_ROOT="$(git rev-parse --show-toplevel)"
# DEV_DIR/DEV_NS/DEV_HOST werden von den sourcenden Skripten gelesen, in lib.sh
# selbst aber nie benutzt — deshalb pro Variable die SC2034-Disable.
# shellcheck disable=SC2034
DEV_DIR="$DEV_REPO_ROOT/dev"
DEV_CLUSTER="dev"
DEV_CONTEXT="kind-$DEV_CLUSTER"
# shellcheck disable=SC2034
DEV_NS="website"
# shellcheck disable=SC2034
DEV_HOST="metzler.systems"

dev_need() {
  command -v "$1" >/dev/null 2>&1 || { echo "fehlt: $1" >&2; exit 1; }
}

# Bricht ab, wenn der aktive kubectl-Kontext nicht der kind-Cluster ist.
dev_require_kind_context() {
  local current_ctx
  current_ctx="$(kubectl config current-context 2>/dev/null || true)"
  if [[ "$current_ctx" != "$DEV_CONTEXT" ]]; then
    echo "ABBRUCH: kubectl-Kontext ist '${current_ctx:-<leer>}', erwartet '$DEV_CONTEXT' - kein Prod-Cluster anlangen" >&2
    exit 1
  fi
}

# Schaltet auf den kind-Kontext um und prueft ihn danach (Sicherheit).
dev_use_kind_context() {
  if ! kubectl config use-context "$DEV_CONTEXT" 2>/dev/null; then
    echo "Kontext $DEV_CONTEXT fehlt - erst dev/setup.sh ausfuehren" >&2
    exit 1
  fi
  dev_require_kind_context
}
