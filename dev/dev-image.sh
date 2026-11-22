#!/usr/bin/env bash
#
# dev-image.sh — App-Image(s) lokal bauen, in den kind-Cluster laden und deployen.
#
# usage: dev/dev-image.sh <metric|website|load|all>
#
# Baut das Image mit dem Tag "dev" (docker layer cache macht Rebuilds ohne
# Aenderungen schnell), laedt es per `kind load docker-image` in den LAUFENDEN
# Cluster (kein Neubau noetig) und deployt per helm upgrade --install plus
# rollout restart (gleicher Tag + pullPolicy=Never aendert den Pod-Spec nicht,
# der laufende Pod wuerde das neue Image sonst nicht uebernehmen).
# image.tag=dev und pullPolicy=Never kommen aus den dev/values-Dateien.
#
# Sicherheit: schaltet auf den Kontext kind-dev um und bricht ab, wenn der
# Kontext nicht kind-dev ist — Prod-Cluster werden nie angefasst.
set -euo pipefail

# shellcheck source=dev/lib.sh
source "$(git rev-parse --show-toplevel)/dev/lib.sh"

for t in docker kind helm kubectl; do dev_need "$t"; done

dev_use_kind_context

# Image-Repository aus den Chart-Values lesen, damit der Name exakt zu
# image.repository:tag im Deployment passt (sonst ErrImageNeverPull).
img_repo() {
  sed -n 's/^[[:space:]]*repository:[[:space:]]*//p' "$DEV_REPO_ROOT/$1/values.yaml" | head -1 | tr -d '"'
}

build_load() {
  local img="$1" build_dir="$2"
  echo "==> Image bauen: $img (Build-Kontext: $build_dir)"
  docker build -t "$img" "$DEV_REPO_ROOT/$build_dir"
  echo "==> Image in kind-Cluster $DEV_CLUSTER laden"
  kind load docker-image "$img" --name "$DEV_CLUSTER"
}

deploy() {
  local app="$1" chart="$2" values="$3"
  echo "==> Helm-Release $app aktualisieren (Kontext $DEV_CONTEXT)"
  helm upgrade --install "$app" "$DEV_REPO_ROOT/$chart" -n "$DEV_NS" -f "$DEV_REPO_ROOT/$values"
  echo "==> Rollout neu starten: deployment/$app (nimmt das geladene Image auf)"
  kubectl rollout restart "deployment/$app" -n "$DEV_NS"
  kubectl rollout status "deployment/$app" -n "$DEV_NS" --timeout=180s
}

# App-Tabelle: app|chart|values|build_dir — neue Microservices hier ergaenzen.
APPS=(
  "website|charts/website|dev/values/website.yaml|site"
  "metric|charts/metric|dev/values/metric.yaml|apps/metric"
  "load|charts/load|dev/values/load.yaml|apps/load"
)

sel="${1:-}"
matched=0
for entry in "${APPS[@]}"; do
  IFS='|' read -r app chart values build_dir <<< "$entry"
  if [[ "$sel" == "all" || "$sel" == "$app" ]]; then
    matched=1
    build_load "$(img_repo "$chart"):dev" "$build_dir"
    deploy "$app" "$chart" "$values"
  fi
done

if (( ! matched )); then
  echo "usage: dev/dev-image.sh <metric|website|load|all>" >&2
  exit 1
fi

# Abschluss-URLs mit Port-Suffix, falls setup.sh auf den Fallback :8443
# ausgewichen ist (Marker dev/.https-port, siehe dev/setup.sh).
PORT_SUFFIX=""
if [[ -f "$DEV_DIR/.https-port" ]]; then
  _p="$(cat "$DEV_DIR/.https-port")"
  [[ -n "$_p" && "$_p" != "443" ]] && PORT_SUFFIX=":$_p"
fi
echo "Fertig. Browser neu laden: https://metzler.systems$PORT_SUFFIX/ bzw. https://metzler.systems$PORT_SUFFIX/api/metrics/health bzw. https://metzler.systems$PORT_SUFFIX/api/load/status"
