#!/usr/bin/env bash
# Local dev server for the Hugo site.
#
#   ./run.sh            start hugo server (http://localhost:1313)
#   ./run.sh build      production build into public/ (hugo --minify)
#   ./run.sh --port 8080 ...   any hugo server flags are passed through
#
set -euo pipefail
cd "$(dirname "$0")"

# The VS Code extension directory leaks an incompatible libstdc++ into
# LD_LIBRARY_PATH, which makes the hugo binary crash with GLIBCXX errors.
# Start with a clean library path.
unset LD_LIBRARY_PATH
# Never let stray env vars override the configured baseURL.
unset HUGO_BASEURL HUGO_ENV

HUGO=/usr/bin/hugo
if [ ! -x "$HUGO" ]; then
  HUGO="$(command -v hugo)"
fi

if [ "${1:-}" = "build" ]; then
  shift
  exec "$HUGO" --minify --cleanDestinationDir "$@"
fi

# --renderToMemory: the dev server must never clobber public/ with a
# localhost:1313 build (hugo server otherwise writes to the destination).
exec "$HUGO" server --disableFastRender --renderToMemory "$@"
