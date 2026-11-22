#!/usr/bin/env bash
#
# teardown.sh — kind-Cluster "dev" loeschen, /etc/hosts-Eintrag entfernen und
# den zuvor aktiven kubectl-Kontext wiederherstellen.
#
# GNU sed vorausgesetzt (-i ohne Backup-Suffix, \b-Wortgrenzen) — wie setup.sh
# mit ss ist der dev-Stack ohnehin Linux-only.
set -euo pipefail

# shellcheck source=dev/lib.sh
source "$(git rev-parse --show-toplevel)/dev/lib.sh"

dev_need kind
dev_need kubectl

if kind get clusters 2>/dev/null | grep -qx "$DEV_CLUSTER"; then
  echo "==> kind-Cluster $DEV_CLUSTER loeschen"
  kind delete cluster --name "$DEV_CLUSTER"
else
  echo "==> kein kind-Cluster $DEV_CLUSTER vorhanden"
fi

# Idempotenz: nur entfernen, wenn setup.sh den Eintrag selbst gesetzt hat
# (Marker dev/.hosts-added). Ein schon vorher vorhandener Eintrag bleibt stehen.
if [[ -f "$DEV_DIR/.hosts-added" ]]; then
  rm -f "$DEV_DIR/.hosts-added"
  if grep -Eq "^[[:space:]]*127\.0\.0\.1[[:space:]].*\b${DEV_HOST}\b" /etc/hosts; then
    echo "==> /etc/hosts-Eintrag fuer $DEV_HOST entfernen (von setup.sh gesetzt, sudo)"
    # Delimiter "/" mit -E: die |-Delimiter-Form ist GNU-spezifisch (\| ist
    # dort Alternation) und bricht auf BSD sed mit "Unbekannter Befehl".
    if sudo sed -i -E "/^[[:space:]]*127\.0\.0\.1[[:space:]].*\b${DEV_HOST}\b/d" /etc/hosts 2>/dev/null; then
      echo "    entfernt"
    else
      echo "    WARNUNG: konnte /etc/hosts nicht bearbeiten (sudo fehlgeschlagen)" >&2
    fi
  else
    echo "==> kein /etc/hosts-Eintrag fuer $DEV_HOST (Marker entfernt)"
  fi
elif grep -Eq "^[[:space:]]*127\.0\.0\.1[[:space:]].*\b${DEV_HOST}\b" /etc/hosts; then
  echo "==> /etc/hosts-Eintrag fuer $DEV_HOST bleibt bestehen (nicht von setup.sh gesetzt)"
else
  echo "==> kein /etc/hosts-Eintrag fuer $DEV_HOST"
fi

if [[ -f "$DEV_DIR/.prev-context" ]]; then
  prev="$(cat "$DEV_DIR/.prev-context")"
  rm -f "$DEV_DIR/.prev-context"
  if [[ -n "$prev" ]] && kubectl config get-contexts "$prev" >/dev/null 2>&1; then
    kubectl config use-context "$prev"
    echo "==> kubectl-Kontext zurueck auf '$prev'"
  fi
fi

echo "Fertig. Lokale Zertifikate bleiben in $DEV_REPO_ROOT/dev/certs/ (gitignored)."
