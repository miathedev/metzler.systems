# Metzler.systems Webseite

Infrastructure as Code meiner Website: https://metzler.systems

[![website-image](https://github.com/miathedev/metzler.systems/actions/workflows/website.yml/badge.svg)](https://github.com/miathedev/metzler.systems/actions/workflows/website.yml)
[![metric-image](https://github.com/miathedev/metzler.systems/actions/workflows/metric.yml/badge.svg)](https://github.com/miathedev/metzler.systems/actions/workflows/metric.yml)
[![load-image](https://github.com/miathedev/metzler.systems/actions/workflows/load.yml/badge.svg)](https://github.com/miathedev/metzler.systems/actions/workflows/load.yml)

## Was in diesem Repo lebt

- `site/`: statische Hugo-Website (HugoBlox Developer Portfolio) mit Live-Metrics-Konsole auf der Startseite (SSE-Stream eigener Kubernetes-Metriken, gerendert mit ECharts)
- `apps/metric/`: Metrics-API (FastAPI). Sampled metrics.k8s.io, haelt einen RAM-Ringbuffer und pusht live per SSE an die Konsole
- `apps/load/`: Load-Service (FastAPI). Startet k6 als batch/v1-Job gegen die Website, damit der HPA-Skalierungsschritt als Stufe im Live-Graphen sichtbar wird
- `charts/`: Helm-Charts fuer website, metric und load
- `flux/cluster/infomaniak/`: GitOps-Deploy (Flux) auf die Infomaniak Public Cloud in der Schweiz
- `dev/`: lokaler kind-Stack, testet dieselben Charts ohne prod anzufassen (siehe `dev/README.md`)

`apps/load/` und `apps/metric/` teilen sich absichtlich das Code-Skelett (config.py, k8s.py, ruff.toml, Dockerfile): zwei unabhaengige Deployables mit getrennter CI und getrennten Images, ganz ohne gemeinsames Paket. Wie bei den Helm-Charts (Copy-Paste-Hinweis in `dev/README.md`) wird die Dopplung bewusst in Kauf genommen, solange die Apps klein bleiben.

## Architektur

```text
Browser
  -> Traefik (Ingress + TLS via cert-manager, letsencrypt-prod)
       -> website   /               nginx, statische Hugo-Site
       -> metric    /api/metrics   FastAPI, read-only metrics.k8s.io + SSE-Stream
       -> load      /api/load      FastAPI, k6-Run als batch/v1-Job (Single-State, 409 bei aktivem Run)
Flux deployt deklarativ aus diesem Repo, CI baut die Images und pusht sie nach ghcr.io
lokal: dev/setup.sh (kind), gleiche Charts, gleiche Ingress-Pfade
```

## Quickstart: lokaler Test-Stack

Voraussetzungen: docker, kind, helm, kubectl, curl, sha256sum, git, ss (prüft setup.sh selbst) und einmalig sudo

`dev/run-tests.sh` braucht zusätzlich python3 (Suiten load/metric), hugo + `site/node_modules` via pnpm (Suite hugo) und helm (Suite helm). Fehlende Tools lassen die jeweilige Suite weich ausfallen (uebersprungen), siehe dev/README.md

```sh
dev/setup.sh              # kind-Cluster + alle Releases (fragt einmalig nach sudo fuer /etc/hosts + mkcert-CA)
dev/dev-image.sh metric   # nach App-Aenderung: Image lokal bauen, in kind laden, deployen
dev/run-tests.sh          # alle automatischen Tests lokal laufen lassen, ohne Cluster (siehe dev/README.md)
dev/teardown.sh           # Cluster herunterfahren, kubectl-Kontext wiederherstellen
```

Danach im Browser: https://metzler.systems/ (Live-Metrics-Konsole), https://metzler.systems/api/metrics/state, https://metzler.systems/api/load/status. Ist Host-Port 80/443 belegt, laufen die URLs stattdessen auf Port 8443 (gibt setup.sh aus).

## Quellen:
* Hugo Template: https://github.com/HugoBlox/hugo-theme-developer-portfolio

## Pre-Commit-Hooks

Einmalig pro Clone aktivieren:

```sh
git config core.hooksPath .githooks
```

Die Hooks in `.githooks/` rufen `pre-commit.sh` im Repo-Root auf. Dort laufen
alle lokalen Checks. Neue Checks in `pre-commit.sh` als `check_<name>()`
definieren und in der `CHECKS`-Liste registrieren. Einzelne Checks
ueberspringen: `SKIP=gitleaks git commit ...`

Aktuelle Checks:
* `pre-commit`: gitleaks-Scan der gestageten Aenderungen (wird beim ersten
  Lauf automatisch als gepinnte Version nach `.bin/` installiert)
* `typography`: Text-Inhalte (`site/content/`, `site/data/`, `site/config/`,
  READMEs) enthalten keine Semikola und keine Nicht-ASCII-Zeichen, ausser
  Buchstaben mit Diakritika und `§` in Gesetzeszitaten. Code-Fences in
  Markdown sind ausgenommen (dort sind z.B. Shell-Semikola legitim).
  Auslassen mit `SKIP=typography git commit ...`
* `helm`: lint + template aller lokalen Charts (prod-Defaults und dev-values,
  falls vorhanden), braucht helm im PATH. Auslassen mit `SKIP=helm git commit ...`
* `commit-msg`: Commit-Style (siehe unten)

## Commit-Style

`<Topic>: <beschreibung>`, z.B. `Fix: kyverno admission ...` oder
`chore(website): image auf <sha> [skip ci]`. Topic ist ein Wort aus Buchstaben
und Ziffern, optional mit Scope in Klammern. Merge-, `fixup!`- und
`squash!`-Commits sind ausgenommen. Erzwungen durch `.githooks/commit-msg`
(Pattern: `COMMIT_MSG_PATTERN` in `pre-commit.sh`).

## VSCode

Geteilte Workspace-Dateien liegen in `.vscode/`: Extension-Empfehlungen, Settings, Tasks und Debug-Konfigs fuer die FastAPI-Apps. Alles andere unter `.vscode/` bleibt lokal und ist gitignored. Nuetzliche Tasks: alle Tests (`dev/run-tests.sh`), kind-Stack starten/stoppen, App-Image neu bauen und deployen. Das integrierte Terminal startet ohne `LD_LIBRARY_PATH`, damit hugo dort nicht crasht.
