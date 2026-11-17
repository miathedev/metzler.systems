#!/usr/bin/env bash
#
# pre-commit.sh — alle lokalen Pre-Commit-Checks des Repos.
#
# Wird vom Git-Hook .githooks/pre-commit ausgefuehrt. Einmalig pro Clone
# aktivieren mit:
#
#   git config core.hooksPath .githooks
#
# Neuen Check hinzufuegen:
#   1. Funktion check_<name>() unten definieren (Rueckgabe 0 = bestanden)
#   2. Funktionsnamen in CHECKS eintragen
#
# Einzelne Checks ueberspringen (z.B. im Notfall):
#   SKIP=gitleaks git commit ...

set -uo pipefail

if ! REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"; then
  echo "pre-commit.sh: laeuft nur innerhalb eines Git-Repos" >&2
  exit 1
fi
cd "$REPO_ROOT"

# Gepinnte Version fuer den Auto-Install von gitleaks (siehe install_gitleaks).
GITLEAKS_VERSION="8.30.1"
# Repo-lokales Verzeichnis fuer auto-installierte Tools (gitignored via .bin/).
LOCAL_BIN="$REPO_ROOT/.bin"

FAILED_CHECKS=()

# ---------------------------------------------------------------------------
# gitleaks — scannt die gestageten Aenderungen auf Secrets
# ---------------------------------------------------------------------------

gitleaks_bin() {
  if [[ -n "${GITLEAKS_BIN:-}" ]]; then
    [[ -x "$GITLEAKS_BIN" ]] || return 1
    echo "$GITLEAKS_BIN"
  elif command -v gitleaks >/dev/null 2>&1; then
    command -v gitleaks
  elif [[ -x "$LOCAL_BIN/gitleaks" ]]; then
    echo "$LOCAL_BIN/gitleaks"
  else
    return 1
  fi
}

install_gitleaks() {
  local os arch base tarball sumfile tmp
  os="linux"
  case "$(uname -m)" in
    x86_64)  arch="x64" ;;
    aarch64) arch="arm64" ;;
    *) echo "    nicht unterstuetzte Architektur: $(uname -m)" >&2; return 1 ;;
  esac
  base="https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}"
  tarball="gitleaks_${GITLEAKS_VERSION}_${os}_${arch}.tar.gz"
  sumfile="gitleaks_${GITLEAKS_VERSION}_checksums.txt"
  tmp="$(mktemp -d)"

  if ! curl -fsSL "$base/$tarball" -o "$tmp/$tarball" \
     || ! curl -fsSL "$base/$sumfile" -o "$tmp/$sumfile"; then
    echo "    Download von gitleaks v${GITLEAKS_VERSION} fehlgeschlagen" >&2
    rm -rf "$tmp"
    return 1
  fi

  if ! (cd "$tmp" && awk -v f="$tarball" '$2 == f' "$sumfile" | sha256sum -c - >/dev/null); then
    echo "    sha256-Checksum passt nicht fuer $tarball" >&2
    rm -rf "$tmp"
    return 1
  fi

  mkdir -p "$LOCAL_BIN"
  if ! tar -xzf "$tmp/$tarball" -C "$LOCAL_BIN" gitleaks; then
    rm -rf "$tmp"
    return 1
  fi
  chmod +x "$LOCAL_BIN/gitleaks"
  rm -rf "$tmp"
  echo "    installiert: $LOCAL_BIN/gitleaks (v${GITLEAKS_VERSION}, sha256-geprueft)"
}

check_gitleaks() {
  local bin
  if ! bin="$(gitleaks_bin)"; then
    echo "  gitleaks nicht gefunden — Auto-Install nach .bin/ ..."
    install_gitleaks || return 1
    bin="$LOCAL_BIN/gitleaks"
  fi
  if git diff --cached --quiet; then
    echo "  keine gestageten Aenderungen — Scan uebersprungen"
    return 0
  fi
  # --staged: nur das gestagete Diff wird gescannt; --redact: Secrets werden
  # in der Ausgabe nicht im Klartext ausgegeben; --verbose: Fundstelle (Rule,
  # Datei, Zeile) wird angezeigt.
  "$bin" protect --staged --redact --no-banner --verbose
}

# ---------------------------------------------------------------------------
# Check-Registry — hier landen kuenftig weitere Checks
# ---------------------------------------------------------------------------

CHECKS=(
  check_gitleaks
)

# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

is_skipped() {
  case ",${SKIP:-}," in *",$1,"*) return 0 ;; esac
  return 1
}

echo "pre-commit: Checks laufen in $REPO_ROOT"
for check in "${CHECKS[@]}"; do
  name="${check#check_}"
  if is_skipped "$name"; then
    echo "==> $name: uebersprungen (SKIP=${SKIP:-})"
    continue
  fi
  echo "==> $name"
  if "$check"; then
    echo "    ok"
  else
    echo "    FEHLGESCHLAGEN"
    FAILED_CHECKS+=("$name")
  fi
done

if ((${#FAILED_CHECKS[@]} > 0)); then
  echo
  echo "pre-commit: ${#FAILED_CHECKS[@]} Check(s) fehlgeschlagen: ${FAILED_CHECKS[*]} — Commit abgebrochen."
  exit 1
fi
echo "pre-commit: alle Checks bestanden."
