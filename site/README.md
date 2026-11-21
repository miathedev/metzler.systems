# site/, HugoBlox Developer Portfolio

Statischer Source der Website `metzler.systems`. Hugo rendert daraus einmalig
statische Dateien nach `public/` (gitignored), im Cluster serviert sie ein
rootless nginx.

## Voraussetzungen

- hugo **extended** (v0.162.0): `hugo version` muss `+extended` zeigen
- Go (für Hugo Modules, `go.mod`/`go.sum`)
- node + pnpm (`pnpm install` installiert `tailwindcss` CLI + `preact` -
  beides braucht der Build und liegt in `node_modules/.bin`)

## Lokal entwickeln

```bash
cd site
pnpm install                 # einmalig: node_modules
pnpm dev                     # = hugo server --disableFastRender → http://localhost:1313
```

Falls `hugo` direkt aufgerufen wird, muss `node_modules/.bin` im PATH sein
(damit `tailwindcss` gefunden wird):

```bash
PATH="$PWD/node_modules/.bin:$PATH" hugo server
```

## Produktions-Build

```bash
PATH="$PWD/node_modules/.bin:$PATH" hugo --minify
# Ergebnis: site/public/
```

## Wo was liegt

| Pfad | Zweck |
|---|---|
| `content/` | Deine Inhalte als Markdown ( `_index.md` = Startseite, `projects/`, `blog/`, `authors/`) |
| `config/_default/hugo.yaml` | Hugo-Basics: `title`, `baseURL`, Ausgabeformate |
| `config/_default/params.yaml` | HugoBlox-Config: Name, Tagline, Farben, Theme, Features |
| `config/_default/menus.yaml` | Navigation |
| `data/authors/me.yaml` | Autorenprofil (wird auf der Startseite angezeigt) |
| `layouts/` | Eigene Template-Overrides (gewinnen gegen Theme-Layouts), z. B. Fix in `_partials/functions/build_links.html` |
| `static/` | Statische Dateien, die 1:1 übernommen werden (uploads/) |
| `go.mod` / `go.sum` | Gepinnte Theme-Abhängigkeiten (HugoBlox kit Module) |

## Theme aktualisieren

```bash
hugo mod get github.com/HugoBlox/kit/modules/blox@latest
hugo mod tidy
```

Danach `hugo --minify` testen, Layout-Overrides in `layouts/` bleiben erhalten.
