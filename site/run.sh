#!/usr/bin/env bash
# run.sh: lokaler Dev-Server fuer die Hugo-Site.
#
#   ./run.sh            startet hugo server (http://localhost:1313)
#   ./run.sh build      Produktions-Build nach public/ (hugo --minify)
#   ./run.sh --port 8080 ...   alle hugo-server-Flags werden durchgereicht
#
set -euo pipefail
cd "$(dirname "$0")"

# Das VS-Code-Extension-Verzeichnis leakt ein inkompatibles libstdc++ in
# LD_LIBRARY_PATH, dadurch crasht das hugo-Binary mit GLIBCXX-Fehlern.
# Deshalb mit sauberem Library-Pfad starten.
unset LD_LIBRARY_PATH
# Niemals zulassen, dass fremde Env-Vars die konfigurierte baseURL ueberschreiben.
unset HUGO_BASEURL HUGO_ENV

HUGO=/usr/bin/hugo
if [ ! -x "$HUGO" ]; then
  HUGO="$(command -v hugo)"
fi

if [ "${1:-}" = "build" ]; then
  shift
  exec "$HUGO" --minify --cleanDestinationDir "$@"
fi

# --renderToMemory: der Dev-Server darf public/ nie mit einem
# localhost:1313-Build ueberschreiben (hugo server schreibt sonst ins Ziel).
exec "$HUGO" server --disableFastRender --renderToMemory "$@"
