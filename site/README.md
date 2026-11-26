# site/, HugoBlox Developer Portfolio

Statischer Source der Website `metzler.systems`. Hugo rendert daraus einmalig
statische Dateien nach `public/` (gitignored), im Cluster serviert sie ein
rootless nginx.

## Voraussetzungen

- hugo (ab v0.170.0 genügt das normale Binary, `extended` ist als Alias entfallen, bei älteren Versionen braucht es `+extended`). Der Docker-Build pinnt HUGO_VERSION=0.170.1, siehe site/Dockerfile
- Go (für Hugo Modules, `go.mod`/`go.sum`)
- node + pnpm (`pnpm install` installiert `tailwindcss` CLI + `preact` -
  beides braucht der Build und liegt in `node_modules/.bin`)

## Lokal entwickeln

```bash
cd site
pnpm install                 # einmalig: node_modules
pnpm dev                     # = hugo server --disableFastRender -> http://localhost:1313
```

Falls `hugo` direkt aufgerufen wird, muss `node_modules/.bin` im PATH sein
(damit `tailwindcss` gefunden wird):

```bash
PATH="$PWD/node_modules/.bin:$PATH" hugo server
```

## Produktions-Build

```bash
pnpm run build   # hugo --minify + pagefind (Such-Index), Ergebnis: site/public/
```

## Wo was liegt

| Pfad | Zweck |
|---|---|
| `content/` | Deine Inhalte als Markdown ( `_index.md` = Startseite, `projects/`, `authors/`) |
| `config/_default/hugo.yaml` | Hugo-Basics: `title`, `baseURL`, Ausgabeformate |
| `config/_default/params.yaml` | HugoBlox-Config: Name, Tagline, Farben, Theme, Features |
| `config/_default/menus.yaml` | Navigation |
| `data/authors/me.yaml` | Autorenprofil (wird auf der Startseite angezeigt) |
| `layouts/` | Eigene Template-Overrides (gewinnen gegen Theme-Layouts), z. B. Fix in `_partials/functions/build_links.html` und der Block `_partials/hbx/blocks/live-metrics/` |
| `assets/js/live-metrics.js` | Live-Metrics-Block auf der Startseite: SSE-Stream (`/api/metrics/stream`, prod 10 Samples/s via `METRIC_SAMPLE_HZ=10` im Chart, lokal im kind 30 Hz via `dev/values/metric.yaml`, komplettes 30-min-RAM-Cache-Fenster via `window_seconds=1800&max_points=60000`) via EventSource mit Poll-Fallback auf `/api/metrics/state`. Pro Station ein kompakter Inline-Chip in einer gemeinsamen Zeile (LED, Name in Serienfarbe, Pod-Anzahl als Gauge), darunter der ECharts-Trend-Chart (`echarts/core`, per `js.Build` gebundelt) ueber das ganze Fenster (dataZoom-Slider + inside-Zoom, lttb-Sampling), drei Y-Achsen (cpu m / mem Mi / pods als gepunktete Step-Linie, Skalierung als Stufe sichtbar), HTML-Legende mit echten Strich-Swatches, RAM-Cache-Anzeige aktualiert live via `"b"` in jedem Sample-Event |
| `assets/js/load-panel.js` | Load-Test-Panel unter dem Chart (eigenes Bundle): Human-Signals (~1.2 s: webdriver/Plugins/Languages/WebGL-Renderer/trusted clicks/mouse moves/time-to-first-input), bei Human-Score automatischer `POST /api/load/?source=visitor&duration_s=90&rate=500` (once per Session, 409 wenn aktiv). Button = voller 5-min-Run. Status-Poll malt RUNNING (LED, grosser Countdown + Balken) bzw. nach Succeeded die echten k6-Metriken aus `/api/load/status` (`last_run.metrics`) als 6er-Grid (requests/rps/p95/failed/data/VUs) |
| `static/` | Statische Dateien, die 1:1 übernommen werden (uploads/) |
| `go.mod` / `go.sum` | Gepinnte Theme-Abhängigkeiten (HugoBlox kit Module) |

## Theme aktualisieren

```bash
hugo mod get github.com/HugoBlox/kit/modules/blox@latest
hugo mod tidy
```

Danach `hugo --minify` testen, Layout-Overrides in `layouts/` bleiben erhalten.
