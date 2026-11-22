# Lokaler Test-Stack (kind)

## Voraussetzungen

docker, kind, helm, kubectl, curl, sha256sum, git, ss (werden in setup.sh geprüft) und einmalig sudo. mkcert wird beim ersten Lauf automatisch nach `.bin/` installiert (gitignored, sha256-geprueft).

## Erster Lauf

```bash
dev/setup.sh
```

Einmalig fragt das Skript nach dem sudo-Passwort: fuer den `/etc/hosts`-Eintrag (`127.0.0.1 metzler.systems`) und um die mkcert-CA im System/Browser zu installieren. Danach im Browser:

- https://metzler.systems/ (website, inkl. Live-Metrics-Konsole auf der Startseite — dort auch der Load-Test-Button)
- https://metzler.systems/api/metrics/health (metric)
- https://metzler.systems/api/metrics/state (Snapshot: Pods/Deployments + metrics.k8s.io, dank lokalem metrics-server)
- https://metzler.systems/api/metrics/stream (SSE-Realtime-Stream, lokal 30 Hz via `METRIC_SAMPLE_HZ=30` in `dev/values/metric.yaml`; `curl -N` zeigt hello/history/sample-Events)
- https://metzler.systems/api/metrics/history?seconds=60 (RAM-Ringbuffer, 30 min Retention)
- https://metzler.systems/api/load/status (load; `POST /api/load/` startet einen 5-min-k6-Run als Kubernetes-Job gegen die website — 409, solange einer läuft)

Load-Test lokal: jeder menschliche Browser-Visit startet automatisch einen k6-Auto-Run (90 s @ 500 rps, source=visitor), der Button in der Live-Metrics-Konsole den vollen 5-min-Run, oder
`python apps/load/scripts/loadtest.py --base-url https://metzler.systems:8443 --cacert dev/certs/rootCA.pem`.
Danach `kubectl get hpa website -n website` beobachten — die Skalierung sieht man als Step in der Pods-Linie des Graphen.

Ist Host-Port 80/443 belegt, laufen die URLs stattdessen auf https://metzler.systems:8443/ (setup.sh gibt die Ports aus).

## Sicherheit: kubectl-Kontext

Alle Skripte schalten den kubectl-Kontext auf `kind-dev` um (`kubectl config use-context kind-dev`) und brechen mit ABBRUCH ab, wenn der aktive Kontext nicht `kind-dev` ist. Prod- oder andere Cluster werden so nie angefasst. `teardown.sh` stellt den vorherigen Kontext wieder her.

Falls der Browser das Zertifikat nicht vertraut: mkcert-CA einmalig importieren (`sudo .bin/mkcert -install` mit `CAROOT=dev/certs`).

### Lokale mkcert-CA im System-Trust-Store (Restrisiko)

`setup.sh` installiert die CA aus `dev/certs/` einmalig in den System-Trust-Store, damit der Browser das Dev-Zertifikat ohne Warnung vertraut. Damit kann diese lokale CA prinzipiell Zertifikate fuer JEDE Domain ausstellen - das ist nur auf dem eigenen Dev-Rechner vertretbar, nie auf fremden oder geteilten Geraeten installieren. Rueckbau mit `sudo env CAROOT=dev/certs .bin/mkcert -uninstall`. Die CA selbst liegt in `dev/certs/` (gitignored) und wird nie committet.

## Dev-Loop

```bash
# App geaendert -> Image neu bauen, in den LAUFENDEN kind-Cluster laden, deployen
# (kein Cluster-Neubau, docker layer cache beschleunigt Rebuilds, Rollout-Restart
# inklusive - gleicher Image-Tag "dev" wuerde den laufenden Pod sonst nicht neu starten)
dev/dev-image.sh metric     # oder: website, load, all

# Chart geaendert -> setup.sh ist idempotent und rollt alles neu aus
dev/setup.sh

# Stack herunterfahren
dev/teardown.sh
```

## Alle Tests einmal laufen lassen

```bash
dev/run-tests.sh            # alle Suiten auf einmal
dev/run-tests.sh load hugo  # nur ausgewaehlte Suiten (shell, load, metric, helm, hugo)
```

Spiegelt die Lint-Jobs der CI, braucht aber keinen laufenden Cluster: `bash -n` ueber alle Shell-Skripte, pro App (load, metric) ruff + vulture + pytest mit Coverage in einem eigenen venv unter `.bin/` (gitignored, wird automatisch angelegt), `helm lint` + `helm template` aller Charts (prod-Defaults und dev-values) und `hugo --minify` fuer die site.

Die Images werden immer lokal gebaut (`docker build`, tag `dev`, `pullPolicy: Never`) und per `kind load docker-image` in den Cluster geladen. ghcr.io wird lokal nicht angefasst - getestet wird der lokale Code-Stand, nicht der prod-Stand.

## Layout

```text
dev/
  kind-config.yaml     # Cluster-Config, mappt Host-Port 80/443 auf Traefik-NodePorts
  values/              # lokale Overrides pro Release (TLS ohne cert-manager, image.tag dev, pullPolicy Never)
  lib.sh               # gemeinsame Konstanten + kind-Kontext-Guard (wird gesourcet)
  setup.sh             # kind create + alle Releases + helm test
  teardown.sh          # kind delete + Kontext restore + /etc/hosts-Eintrag entfernen (nur wenn von setup.sh gesetzt, Marker .hosts-added)
  dev-image.sh         # lokales App-Image bauen + deployen (image.tag=dev, APPS-Tabelle innen)
  run-tests.sh         # alle automatischen Tests einmal laufen lassen, ohne Cluster (pytest/ruff je App, helm, hugo)
  certs/               # mkcert-CA und Certs, gitignored - nie committen
```

## Hinweis: StripPrefix fuer /api/metrics und /api/load

Traefik (Chart 42.4.0, wie prod) strippt bei `pathType: Prefix` den Pfad NICHT automatisch - die Apps erwarten aber `/health` statt `/api/metrics/health` bzw. `/status` statt `/api/load/status` (uvicorn `--root-path` ist nur fuer Logging/URL-Generierung). Die Charts bringen die StripPrefix-Middlewares selbst mit (`templates/middleware.yaml`, referenziert ueber die Ingress-Default-Annotation in `templates/ingress.yaml`) - prod und dev sind damit identisch, keine dev-only-Manifeste mehr noetig. `helm lint` + `helm template` (prod-Defaults und dev-values) laufen als `helm`-Check in `pre-commit.sh`.

## Neue Microservices

1. Chart unter `charts/<name>/` anlegen (prod-Deploy wie gehabt via Flux)
2. `dev/values/<name>.yaml` mit lokalen Overrides (`cert-manager.io/cluster-issuer: null`, TLS-Secret, image.tag dev, pullPolicy Never)
3. In `dev/setup.sh` ein `helm upgrade --install`-Block ergaenzen (und ggf. ein TLS-Secret in der Secret-Schleife)
4. In `dev/dev-image.sh` eine Zeile in die `APPS`-Tabelle aufnehmen (`app|chart|values|build_dir`)
5. Workflow `.github/workflows/<name>.yml` anlegen (Lint + pytest + helm lint/template + Image-Build, siehe `load.yml`)
6. **Ab dem 3. Service**: gemeinsame Teile (Ingress + Middleware, Service, ServiceAccount, securityContext, Probes, test-connection) in ein Library-Chart `charts/common` heben - bis dahin ist Copy-Paste bei 2 Services vertretbar, solange die bewusst verschiedenen Stellen (RBAC, env, app-spezifische Ressourcen) auseinandergehalten werden
