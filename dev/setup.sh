#!/usr/bin/env bash
#
# setup.sh — lokaler Test-Stack im kind-Cluster (siehe dev/README.md).
#
# Legt den kind-Cluster "dev" an und installiert Traefik, metrics-server,
# Kyverno + Policies sowie die Charts website, metric und load (Images lokal
# gebaut, siehe dev/dev-image.sh). Danach im Browser:
#   https://metzler.systems/                    (website)
#   https://metzler.systems/api/metrics/health  (metric)
#   https://metzler.systems/api/load/status     (load)
#
# Sicherheit: Alle kubectl/helm-Aufrufe laufen ausschliesslich im Kontext
# "kind-dev" — das Skript schaltet um und bricht ab, wenn der Kontext nicht
# kind-dev ist. Prod-Kontexte werden nie angefasst.
#
# Einmalig noetig: sudo (fuer /etc/hosts und die mkcert-CA im System).
# Ist Host-Port 80/443 belegt, faellt das Skript auf 8080/8443 zurueck.
set -euo pipefail

# shellcheck source=dev/lib.sh
source "$(git rev-parse --show-toplevel)/dev/lib.sh"

LOCAL_BIN="$DEV_REPO_ROOT/.bin"
MKCERT_VERSION="1.4.4"
export CAROOT="$DEV_DIR/certs"

log() { printf '\n==> %s\n' "$*"; }

for t in docker kind helm kubectl curl sha256sum git ss; do dev_need "$t"; done

# --- mkcert nach .bin/ installieren (sha256 gepinnt, siehe pre-commit.sh-Muster)
mkcert_bin() {
  if command -v mkcert >/dev/null 2>&1; then
    command -v mkcert
  elif [[ -x "$LOCAL_BIN/mkcert" ]]; then
    echo "$LOCAL_BIN/mkcert"
  else
    return 1
  fi
}

install_mkcert() {
  local arch expected base tarball tmp
  # mkcert publiziert keine Checksums-Datei im Release — Hashes sind gepinnt.
  case "$(uname -m)" in
    x86_64)  arch=amd64; expected="6d31c65b03972c6dc4a14ab429f2928300518b26503f58723e532d1b0a3bbb52" ;;
    aarch64) arch=arm64; expected="b98f2cc69fd9147fe4d405d859c57504571adec0d3611c3eefd04107c7ac00d0" ;;
    *) echo "    nicht unterstuetzte Architektur: $(uname -m)" >&2; return 1 ;;
  esac
  base="https://github.com/FiloSottile/mkcert/releases/download/v${MKCERT_VERSION}"
  tarball="mkcert-v${MKCERT_VERSION}-linux-${arch}"
  tmp="$(mktemp -d)"
  if ! curl -fsSL "$base/$tarball" -o "$tmp/$tarball"; then
    echo "    Download von mkcert v${MKCERT_VERSION} fehlgeschlagen" >&2
    rm -rf "$tmp"
    return 1
  fi
  if [[ "$(sha256sum "$tmp/$tarball" | cut -d' ' -f1)" != "$expected" ]]; then
    echo "    sha256 passt nicht fuer $tarball (erwartet $expected)" >&2
    rm -rf "$tmp"
    return 1
  fi
  mkdir -p "$LOCAL_BIN"
  install -m755 "$tmp/$tarball" "$LOCAL_BIN/mkcert"
  rm -rf "$tmp"
  echo "    installiert: $LOCAL_BIN/mkcert (v${MKCERT_VERSION}, sha256-geprueft)"
}

if ! MKCERT="$(mkcert_bin)"; then
  log "mkcert v${MKCERT_VERSION} wird nach .bin/ installiert"
  install_mkcert
  MKCERT="$LOCAL_BIN/mkcert"
fi

# --- /etc/hosts: Hostname lokal aufloesen -----------------------------------
log "/etc/hosts-Eintrag fuer $DEV_HOST"
if grep -Eq "^[[:space:]]*127\.0\.0\.1[[:space:]].*\b${DEV_HOST}\b" /etc/hosts; then
  echo "    bereits vorhanden"
elif echo "127.0.0.1 $DEV_HOST" | sudo tee -a /etc/hosts >/dev/null 2>&1; then
  echo "    hinzugefuegt: 127.0.0.1 $DEV_HOST"
  # Marker fuer teardown.sh: Eintrag stammt von uns und darf wieder entfernt
  # werden (ein bereits vorhandener Eintrag wird dagegen nie angefasst)
  touch "$DEV_DIR/.hosts-added"
else
  echo "    WARNUNG: /etc/hosts nicht beschreibbar (sudo fehlgeschlagen)" >&2
  echo "    -> Eintrag manuell setzen fuer Browser-URLs, Smoke-Test unten nutzt --resolve" >&2
fi

# --- TLS-Cert fuer $DEV_HOST via mkcert ---------------------------------------
log "TLS-Cert fuer $DEV_HOST (mkcert, CA liegt in dev/certs/)"
mkdir -p "$CAROOT"
# Private Keys liegen unverschluesselt in dev/certs — Ordner auf 700 ziehen.
chmod 700 "$CAROOT"
# Cert UND Key pruefen: nur das Cert zu sehen hiesse spaeter beim
# Secret-Anlegen (unten) abgebrochen zu werden.
if [[ ! -f "$CAROOT/$DEV_HOST.pem" || ! -f "$CAROOT/$DEV_HOST-key.pem" ]]; then
  (cd "$CAROOT" && "$MKCERT" -cert-file "$DEV_HOST.pem" -key-file "$DEV_HOST-key.pem" "$DEV_HOST")
  echo "    Cert erzeugt: $CAROOT/$DEV_HOST.pem"
fi
if [[ ! -f "$CAROOT/.ca-installed" ]]; then
  # CA einmalig ins System/Browser installieren (interaktives sudo)
  if sudo env CAROOT="$CAROOT" "$MKCERT" -install >/dev/null 2>&1; then
    touch "$CAROOT/.ca-installed"
    echo "    mkcert-CA im System installiert"
  else
    echo "    WARNUNG: mkcert-CA nicht installiert (sudo fehlgeschlagen)" >&2
    echo "    -> Browser zeigt evtl. Zertifikatswarnung, siehe dev/README.md" >&2
  fi
fi

# --- Host-Ports: 80/443 oder Fallback 8080/8443 -------------------------------
# Der Fallback gilt nur beim NEUANLEGEN des Clusters: existiert er bereits,
# wurden die Host-Ports bei seiner Erstellung festgelegt und bleiben — der
# damalige Marker .https-port sagt, welcher Port beschrieben ist.
HTTP_PORT="${HOST_HTTP_PORT:-80}"
HTTPS_PORT="${HOST_HTTPS_PORT:-443}"
host_port_free() {
  ! ss -tlnH 2>/dev/null | awk '{print $4}' | grep -qE "[:.]$1$"
}
KIND_CONFIG="$DEV_DIR/kind-config.yaml"
CLUSTER_EXISTS=0
if kind get clusters 2>/dev/null | grep -qx "$DEV_CLUSTER"; then
  CLUSTER_EXISTS=1
fi
if (( CLUSTER_EXISTS )); then
  # Marker von der Erstellung lesen (Default 443 = Mapping aus kind-config.yaml)
  if [[ -f "$DEV_DIR/.https-port" ]]; then
    HTTPS_PORT="$(cat "$DEV_DIR/.https-port")"
  fi
  echo "Cluster existiert bereits — Host-Ports bleiben wie bei der Erstellung (https: $HTTPS_PORT)"
else
  if ! host_port_free "$HTTP_PORT" || ! host_port_free "$HTTPS_PORT"; then
    HTTP_PORT=8080
    HTTPS_PORT=8443
    KIND_CONFIG="$(mktemp /tmp/kind-config-dev-XXXXXX.yaml)"
    sed -e "s/hostPort: 80/hostPort: $HTTP_PORT/" -e "s/hostPort: 443/hostPort: $HTTPS_PORT/" \
      "$DEV_DIR/kind-config.yaml" > "$KIND_CONFIG"
    echo "Host-Port 80/443 belegt — Fallback auf $HTTP_PORT/$HTTPS_PORT (Browser-URLs mit :$HTTPS_PORT)"
  fi
  # Marker fuer dev-image.sh: dort steht der beschriebene Port in der
  # Abschlussmeldung (gitignored, siehe .gitignore).
  echo "$HTTPS_PORT" > "$DEV_DIR/.https-port"
fi
PORT_SUFFIX=""
[[ "$HTTPS_PORT" != "443" ]] && PORT_SUFFIX=":$HTTPS_PORT"

# --- kind-Cluster -------------------------------------------------------------
# Vorherigen Kontext VOR kind create merken — kind setzt current-context auf
# kind-dev, danach waere die Restore-Information in teardown.sh falsch.
PREV_CONTEXT="$(kubectl config current-context 2>/dev/null || true)"
log "kind-Cluster $DEV_CLUSTER"
if (( CLUSTER_EXISTS )); then
  echo "    Cluster existiert bereits"
else
  kind create cluster --name "$DEV_CLUSTER" --config "$KIND_CONFIG" --wait 180s
fi
# mktemp-Config vom Port-Fallback liegt sonst dauerhaft in /tmp
if [[ "$KIND_CONFIG" == /tmp/kind-config-dev-* ]]; then
  rm -f "$KIND_CONFIG"
fi

# --- Kontext-Umschaltung auf kind-dev (alle weiteren Aufrufe nur dort) --------
kubectl config use-context "$DEV_CONTEXT"
# .prev-context nur merken, wenn sie vom kind-Kontext verschieden ist — ein
# Re-Run von setup.sh wuerde sonst "kind-dev" als Vorgaenger speichern und
# teardown.sh koennte nach `kind delete` den Kontext nicht mehr restore'n.
if [[ -n "$PREV_CONTEXT" && "$PREV_CONTEXT" != "$DEV_CONTEXT" ]]; then
  echo "$PREV_CONTEXT" > "$DEV_DIR/.prev-context"
fi
dev_require_kind_context
echo "    kubectl-Kontext: $DEV_CONTEXT (zuvor: ${PREV_CONTEXT:-<leer>})"

# --- Helm-Repos ---------------------------------------------------------------
helm repo add traefik https://traefik.github.io/charts >/dev/null 2>&1 || true
helm repo add kyverno https://kyverno.github.io/helm-charts >/dev/null 2>&1 || true
helm repo add metrics-server https://kubernetes-sigs.github.io/metrics-server/ >/dev/null 2>&1 || true
helm repo update >/dev/null

wait_ns() {
  kubectl wait --for=condition=ready pod -n "$1" --all --timeout=300s
}

# --- Kyverno zuerst (wie prod), dann warten bis der Webhook steht -------------
log "Kyverno installieren (Version wie prod)"
helm upgrade --install kyverno kyverno/kyverno -n kyverno --create-namespace \
  --version 3.10.0 -f "$DEV_DIR/values/kyverno.yaml"
wait_ns kyverno

# --- Traefik + metrics-server (vor den Policies, damit die ValidatingPolicy
# --- die Infra-Charts nicht blockieren kann) ----------------------------------
log "Traefik installieren (Version wie prod)"
helm upgrade --install traefik traefik/traefik -n traefik --create-namespace \
  --version 42.4.0 -f "$DEV_DIR/values/traefik.yaml"
wait_ns traefik

log "metrics-server installieren (Version wie prod)"
helm upgrade --install metrics-server metrics-server/metrics-server -n kube-system \
  --version 3.14.0 -f "$DEV_DIR/values/metrics-server.yaml"
kubectl wait -n kube-system --for=condition=ready pod \
  -l app.kubernetes.io/name=metrics-server --timeout=300s

# --- Kyverno-Policies aus dem Repo --------------------------------------------
log "Kyverno-Policies installieren (charts/kyverno-policies)"
helm upgrade --install kyverno-policies "$DEV_REPO_ROOT/charts/kyverno-policies" -n kyverno

# --- TLS-Secrets aus dem mkcert-Cert ------------------------------------------
log "TLS-Secrets website-tls / metric-tls / load-tls im Namespace $DEV_NS"
kubectl create namespace "$DEV_NS" --dry-run=client -o yaml | kubectl apply -f -
# StripPrefix-Middlewares kommen aus den Charts selbst (templates/middleware.yaml)
for s in website-tls metric-tls load-tls; do
  kubectl -n "$DEV_NS" create secret tls "$s" \
    --cert="$CAROOT/$DEV_HOST.pem" --key="$CAROOT/$DEV_HOST-key.pem" \
    --dry-run=client -o yaml | kubectl apply -f -
done

# --- website + metric + load: Images lokal bauen, in kind laden, deployen ----
# Kein ghcr-Pull: die Images entstehen aus dem lokalen Code (tag dev,
# pullPolicy Never in den dev/values). dev-image.sh all baut alle und
# deployt per helm upgrade --install.
log "Images lokal bauen + website/metric/load deployen (dev/dev-image.sh all)"
"$DEV_DIR/dev-image.sh" all
wait_ns "$DEV_NS"

# --- Helm-Tests (test-connection-Hooks) ---------------------------------------
log "helm test"
helm test website -n "$DEV_NS" --logs
helm test metric -n "$DEV_NS" --logs
helm test load -n "$DEV_NS" --logs

# --- Smoke-Test durch den Ingress (curl --resolve, braucht keinen /etc/hosts-Eintrag)
log "Smoke-Test durch den Ingress"
curl -fsS --resolve "$DEV_HOST:$HTTPS_PORT:127.0.0.1" --cacert "$CAROOT/rootCA.pem" \
  "https://$DEV_HOST$PORT_SUFFIX/api/metrics/health" && echo
curl -fsS --resolve "$DEV_HOST:$HTTPS_PORT:127.0.0.1" --cacert "$CAROOT/rootCA.pem" \
  "https://$DEV_HOST$PORT_SUFFIX/api/load/status" && echo
curl -fsS --resolve "$DEV_HOST:$HTTPS_PORT:127.0.0.1" --cacert "$CAROOT/rootCA.pem" \
  -o /dev/null -w "website: HTTP %{http_code}\n" "https://$DEV_HOST$PORT_SUFFIX/"

log "Fertig — lokaler Stack laeuft"
cat <<EOF

Browser:
  https://$DEV_HOST$PORT_SUFFIX/                      (website)
  https://$DEV_HOST$PORT_SUFFIX/api/metrics/health     (metric, liveness/readiness)
  https://$DEV_HOST$PORT_SUFFIX/api/metrics/state      (braucht metrics-server, lokal installiert)
  https://$DEV_HOST$PORT_SUFFIX/api/load/status        (load, POST /api/load/ startet 5-min-Run)

Ohne /etc/hosts-Schreibrecht zum Testen:
  curl --resolve $DEV_HOST:$HTTPS_PORT:127.0.0.1 --cacert "$CAROOT/rootCA.pem" https://$DEV_HOST$PORT_SUFFIX/api/metrics/health

App lokal neu bauen und deployen:  dev/dev-image.sh metric   (oder: website, load, all)
Stack herunterfahren:               dev/teardown.sh
EOF
