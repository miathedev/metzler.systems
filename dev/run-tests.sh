#!/usr/bin/env bash
#
# run-tests.sh — alle automatischen Tests des Repos einmal lokal laufen lassen.
#
# usage: dev/run-tests.sh [suite ...]
#   ohne Argumente laufen alle Suiten, sonst nur die genannten.
#   Suiten: shell, load, metric, helm, hugo
#
# Die Suiten spiegeln die Lint-Jobs der CI (.github/workflows/*.yml), brauchen
# aber keinen kind-Cluster:
#   shell   — bash -n ueber alle Shell-Skripte des Repos; shellcheck zusaetzlich,
#             falls lokal installiert (in der CI laeuft shellcheck immer, website.yml)
#   load    — apps/load: ruff + vulture + pytest --cov in eigenem venv (.bin/)
#   metric  — apps/metric: dasselbe
#   helm    — helm lint + helm template fuer alle Charts (prod UND dev-values)
#   hugo    — site/ baut fehlerfrei mit hugo --minify
#
# Die Python-Test-Venvs liegen unter .bin/venv-<app>/ (gitignored wie ganz .bin/)
# und werden bei Bedarf angelegt und mit requirements-dev.txt befuellt.
# Kein -e: der Runner sammelt den rc pro Suite manuell (FAILED/SKIPPED) —
# ein -e wuerde beim ersten Fehlschlag abbrechen. Die Setup-Schritte sind
# deshalb explizit abgesichert.
set -uo pipefail

# shellcheck source=dev/lib.sh
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" \
  || { echo "run-tests.sh: kein git-Repository gefunden" >&2; exit 1; }
source "$REPO_ROOT/dev/lib.sh"

ALL_SUITES=(shell load metric helm hugo)

# ---------------------------------------------------------------------------
# Suiten — Rueckgabe 0 = bestanden, 2 = uebersprungen (Tool fehlt), sonst fail
# ---------------------------------------------------------------------------

suite_shell() {
  local f failed=0
  local -a scripts=()
  while IFS= read -r f; do
    scripts+=("$f")
  done < <(find "$DEV_REPO_ROOT" -type f -name '*.sh' \
             -not -path '*/.git/*' -not -path '*/node_modules/*' \
             -not -path '*/.bin/*' -not -path '*/public/*' | sort)
  if (( ${#scripts[@]} == 0 )); then
    echo "  keine .sh-Dateien gefunden" >&2
    return 1
  fi
  for f in "${scripts[@]}"; do
    if ! bash -n "$f"; then
      echo "  Syntaxfehler in $f" >&2
      failed=1
    fi
  done
  # In der CI laeuft shellcheck immer (website.yml, Job shell) — lokal nur,
  # wenn installiert, damit die lokale Suite nicht staerker prueft als noetig.
  if command -v shellcheck >/dev/null 2>&1; then
    shellcheck "${scripts[@]}" || failed=1
  else
    echo "  shellcheck nicht installiert — nur bash -n (CI prueft mit shellcheck)"
  fi
  return "$failed"
}

# Gemeinsamer Ablauf fuer die Python-Apps (load, metric): eigenes venv, dann
# ruff, vulture und pytest — exakt die Schritte des CI-Lint-Jobs. fail_under
# ist das Coverage-Floor pro App (gleich wie --cov-fail-under in der CI).
suite_app() {
  local app="$1" fail_under="$2"
  local dir="$DEV_REPO_ROOT/apps/$app"
  local venv="$DEV_REPO_ROOT/.bin/venv-$app"
  # Fehlende Tools ueberspringen die Suite weich (wie check_helm in
  # pre-commit.sh), damit die restlichen Suiten trotzdem laufen.
  command -v python3 >/dev/null 2>&1 || { echo "  python3 fehlt — Suite uebersprungen"; return 2; }
  if [[ ! -x "$venv/bin/python" ]]; then
    echo "  lege venv an: $venv"
    python3 -m venv "$venv" || return 1
  fi
  "$venv/bin/pip" install -q -r "$dir/requirements-dev.txt" || return 1
  (
    cd "$dir" &&
    "$venv/bin/ruff" check . &&
    "$venv/bin/vulture" app whitelist_vulture.py &&
    "$venv/bin/python" -m pytest tests -q --cov=app --cov-report=term-missing \
      --cov-fail-under="$fail_under"
  )
}

suite_load()   { suite_app load 80;   }
suite_metric() { suite_app metric 70; }

suite_helm() {
  command -v helm >/dev/null 2>&1 || { echo "  helm nicht installiert — Suite uebersprungen"; return 2; }
  local c failed=0
  for c in "$DEV_REPO_ROOT"/charts/*/; do
    c="$(basename "$c")"
    [[ -f "$DEV_REPO_ROOT/charts/$c/Chart.yaml" ]] || continue
    if ! helm lint "$DEV_REPO_ROOT/charts/$c" >/dev/null; then
      echo "  helm lint charts/$c fehlgeschlagen" >&2
      failed=1
    fi
    if ! helm template "$c" "$DEV_REPO_ROOT/charts/$c" -n website >/dev/null; then
      echo "  helm template charts/$c (prod-Defaults) fehlgeschlagen" >&2
      failed=1
    fi
    if [[ -f "$DEV_REPO_ROOT/dev/values/$c.yaml" ]]; then
      if ! helm template "$c" "$DEV_REPO_ROOT/charts/$c" -n website \
           -f "$DEV_REPO_ROOT/dev/values/$c.yaml" >/dev/null; then
        echo "  helm template charts/$c (dev-values) fehlgeschlagen" >&2
        failed=1
      fi
    fi
  done
  return "$failed"
}

suite_hugo() {
  if ! command -v hugo >/dev/null 2>&1 || [[ ! -d "$DEV_REPO_ROOT/site/node_modules" ]]; then
    echo "  hugo oder site/node_modules fehlt — Suite uebersprungen"
    return 2
  fi
  # LD_LIBRARY_PATH wird entfernt, weil die VSCode-Extension darueber eigene
  # Libs injiziert, mit denen hugo sofort crasht; node_modules/.bin liefert
  # die Tailwind-CLI fuer den Build.
  (
    cd "$DEV_REPO_ROOT/site" &&
    env -u LD_LIBRARY_PATH PATH="$PWD/node_modules/.bin:$PATH" hugo --minify >/dev/null
  )
}

# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if (( $# > 0 )); then
  SUITES=("$@")
else
  SUITES=("${ALL_SUITES[@]}")
fi
for s in "${SUITES[@]}"; do
  case " ${ALL_SUITES[*]} " in
    *" $s "*) ;;
    *) echo "unbekannte Suite: $s (erlaubt: ${ALL_SUITES[*]})" >&2; exit 2 ;;
  esac
done

FAILED=()
SKIPPED=()
for s in "${SUITES[@]}"; do
  echo "==> $s"
  "suite_$s"
  rc=$?
  case $rc in
    0) echo "    ok" ;;
    2) echo "    uebersprungen"; SKIPPED+=("$s") ;;
    *) echo "    FEHLGESCHLAGEN"; FAILED+=("$s") ;;
  esac
done

echo
if ((${#FAILED[@]} > 0)); then
  echo "run-tests.sh: FEHLGESCHLAGEN: ${FAILED[*]}" >&2
  ((${#SKIPPED[@]} > 0)) && echo "uebersprungen: ${SKIPPED[*]}" >&2
  exit 1
fi
echo "run-tests.sh: alle Tests bestanden${SKIPPED:+ (uebersprungen: ${SKIPPED[*]})}"
