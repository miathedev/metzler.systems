#!/usr/bin/env bash
#
# pre-commit.sh — alle lokalen Git-Hook-Checks des Repos.
#
# Wird von den Git-Hooks in .githooks/ ausgefuehrt. Einmalig pro Clone
# aktivieren mit:
#
#   git config core.hooksPath .githooks
#
# Modi:
#   pre-commit.sh                      — pre-commit-Hook (.githooks/pre-commit)
#   pre-commit.sh commit-msg <file>    — commit-msg-Hook (.githooks/commit-msg)
#
# Neuen Check hinzufuegen:
#   1. Funktion check_<name>() unten definieren (Rueckgabe 0 = bestanden)
#   2. Funktionsnamen in CHECKS eintragen (bzw. Mode-spezifisch umschalten)
#
# Einzelne Checks ueberspringen (z.B. im Notfall):
#   SKIP=gitleaks git commit ...

set -uo pipefail

# Modus: "pre-commit" (Standard) oder "commit-msg <datei>" (Message-Check).
MODE="${1:-pre-commit}"
MSG_FILE=""
if [[ "$MODE" == "commit-msg" ]]; then
  MSG_FILE="${2:-}"
  # Relativen Pfad absolut machen, bevor wir ins Repo-Root wechseln.
  case "$MSG_FILE" in
    /*) ;;
    "") ;;
    *) MSG_FILE="$PWD/$MSG_FILE" ;;
  esac
fi

if ! REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"; then
  echo "pre-commit.sh: laeuft nur innerhalb eines Git-Repos" >&2
  exit 1
fi
cd "$REPO_ROOT"

# Gepinnte Version fuer den Auto-Install von gitleaks (siehe install_gitleaks).
GITLEAKS_VERSION="8.30.1"
# Erlaubter Commit-Style: "<Topic>: <beschreibung>", z.B. "Fix: kyverno ..."
# oder "chore(website): image auf <sha>". Topic: Wort aus Buchstaben/Ziffern,
# optional mit Scope in Klammern. Merge-/fixup-/squash!-Commits siehe
# check_commit_msg.
COMMIT_MSG_PATTERN='^[A-Za-z][A-Za-z0-9_-]*(\([A-Za-z0-9_./-]+\))?: .+'
# Verboten in Text-Inhalten (siehe check_typography): ";" (ausser als Teil
# eines HTML-Entities wie &amp;), jedes Nicht-ASCII-Zeichen ausser Buchstaben
# mit Diakritika (ae/oe/ue/ss/...) und dem Paragraph-Zeichen, sowie Entities,
# die auf solche Zeichen rendern (&mdash; usw.).
TYPO_PATTERN='(?<!&[A-Za-z0-9#]{1,10});|[^\x00-\x7F\x{00A7}\x{00C0}-\x{00D6}\x{00D8}-\x{00F6}\x{00F8}-\x{00FF}]|&(?i:mdash|ndash|rarr|hellip|lsquo|rsquo|ldquo|rdquo|nbsp);'
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

check_commit_msg() {
  if [[ -z "$MSG_FILE" || ! -f "$MSG_FILE" ]]; then
    echo "  kein Commit-Message-File uebergeben (Aufruf: pre-commit.sh commit-msg <file>)" >&2
    return 1
  fi
  local first
  first="$(head -n1 "$MSG_FILE" | tr -d '\r')"
  # Merge-, fixup!- und squash!-Commits (z.B. rebase --autosquash) ausnehmen
  case "$first" in
    "Merge "*|"fixup! "*|"squash! "*)
      echo "  ausgenommen: $first"
      return 0
      ;;
  esac
  if [[ -z "${first//[[:space:]]/}" ]]; then
    echo "  leere Commit-Message" >&2
    return 1
  fi
  if [[ "$first" =~ $COMMIT_MSG_PATTERN ]]; then
    return 0
  fi
  {
    echo "  Commit-Message verstosst gegen den Style:"
    echo "    '$first'"
    echo "  erwartet: '<Topic>: <beschreibung>', z.B. 'Fix: kyverno admission in system namespaces'"
  } >&2
  return 1
}

# ---------------------------------------------------------------------------
# typography — Text-Inhalte duerfen weder Semikola noch Nicht-ASCII-Zeichen
# enthalten (ausser Buchstaben mit Diakritika und Paragraph-Zeichen).
# Scannt die gestageten Versionen von site/content/, site/data/,
# site/config/ und den READMEs; Code-Fences in Markdown (``` / ~~~) werden
# ausgelassen, weil dort z.B. Shell-Semikola legitim sind.
# ---------------------------------------------------------------------------

check_typography() {
  local files f out hits=0
  if git diff --cached --quiet; then
    echo "  keine gestageten Aenderungen, Scan uebersprungen"
    return 0
  fi
  files="$(git diff --cached --name-only --diff-filter=ACM \
           | grep -E '^(README\.md|site/README\.md|site/content/.*\.md|site/data/.*\.yaml|site/config/.*\.yaml)$' \
           || true)"
  if [[ -z "$files" ]]; then
    echo "  keine Text-Dateien unter den gestageten Aenderungen"
    return 0
  fi
  while IFS= read -r f; do
    if [[ "$f" == *.md ]]; then
      out="$(git show ":$f" | LC_ALL=C.UTF-8 awk '
               /^[[:space:]]*(```|~~~)/ { fence = !fence; next }
               !fence
             ' | LC_ALL=C.UTF-8 grep -nP "$TYPO_PATTERN" | sed "s|^|$f:|")"
    else
      out="$(git show ":$f" | LC_ALL=C.UTF-8 grep -nP "$TYPO_PATTERN" | sed "s|^|$f:|")"
    fi
    if [[ -n "$out" ]]; then
      echo "$out"
      hits=1
    fi
  done <<< "$files"
  if ((hits)); then
    {
      echo "  verboten in Text-Inhalten: Semikolon und Nicht-ASCII-Zeichen."
      echo "  erlaubt: ASCII, Buchstaben mit Diakritika (ae/oe/ue/ss/...) und das Paragraph-Zeichen"
    } >&2
    return 1
  fi
  return 0
}

# ---------------------------------------------------------------------------
# Check-Registry — hier landen kuenftig weitere Checks
# ---------------------------------------------------------------------------

CHECKS=(
  check_gitleaks
  check_typography
)

# Der pre-commit-Hook sieht die Commit-Message nicht — die prueft der
# commit-msg-Hook in seinem eigenen Modus.
if [[ "$MODE" == "commit-msg" ]]; then
  CHECKS=(check_commit_msg)
fi

# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

is_skipped() {
  case ",${SKIP:-}," in *",$1,"*) return 0 ;; esac
  return 1
}

if [[ "$MODE" == "commit-msg" ]]; then
  echo "commit-msg: pruefe Commit-Message ($MSG_FILE)"
else
  echo "pre-commit: Checks laufen in $REPO_ROOT"
fi
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
  echo "$MODE: ${#FAILED_CHECKS[@]} Check(s) fehlgeschlagen: ${FAILED_CHECKS[*]} — Commit abgebrochen."
  exit 1
fi
echo "$MODE: alle Checks bestanden."
