#!/usr/bin/env python3
"""Loadtest-CLI: startet einen Load-Run ueber die oeffentliche API und pollt
den Status, bis der Run abgelaufen ist.

Nur stdlib (urllib), damit das Skript ueberall laeuft — lokal gegen kind:

    python apps/load/scripts/loadtest.py \
        --base-url https://metzler.systems:8443 --cacert dev/certs/rootCA.pem

Prod:

    python apps/load/scripts/loadtest.py --base-url https://metzler.systems

Zweiter Start waehrend eines laufenden Runs antwortet die API mit 409 —
das Skript meldet das und pollt weiter (Single-State, siehe app/k8s.py).
Waerend des Runs: kubectl get hpa website -n website bzw. die Pods-Serie im
Live-Graphen auf metzler.systems beobachten (Skalierung als Step sichtbar).
"""

import argparse
import json
import ssl
import sys
import time
import urllib.error
import urllib.request


def _req(ctx, method, url):
    r = urllib.request.Request(url, method=method,
                               headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(r, context=ctx, timeout=15) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        try:
            return e.code, json.loads(body)
        except ValueError:
            return e.code, {"detail": body}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base-url", default="https://metzler.systems",
                    help="Basis-URL ohne Pfad (default: prod)")
    ap.add_argument("--cacert", default=None,
                    help="CA fuer selbstsigniertes Cert (kind: dev/certs/rootCA.pem)")
    ap.add_argument("--insecure", action="store_true",
                    help="TLS-Verifikation abschalten (nur lokaler Test)")
    ap.add_argument("--poll", type=float, default=2.0, help="Poll-Intervall in s")
    args = ap.parse_args()

    if args.insecure:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    elif args.cacert:
        ctx = ssl.create_default_context(cafile=args.cacert)
    else:
        ctx = ssl.create_default_context()

    base = args.base_url.rstrip("/") + "/api/load"
    code, body = _req(ctx, "POST", base + "/")
    if code == 409:
        print("409: load already running — pollt weiter bis idle", flush=True)
    elif code != 200:
        print(f"POST {base}/ -> HTTP {code}: {body}", file=sys.stderr)
        return 1
    else:
        print(f"POST {base}/ -> 200: run gestartet "
              f"({body.get('rate')} rps, {body['duration_s']}s, "
              f"VUs {body.get('vus')}/{body.get('max_vus')})", flush=True)

    while True:
        time.sleep(args.poll)
        code, st = _req(ctx, "GET", base + "/status")
        if code != 200:
            print(f"GET status -> HTTP {code}: {st}", file=sys.stderr)
            return 1
        if st.get("state") == "running":
            print(f"running: job {st.get('job')} ({st.get('job_state')}), "
                  f"{st['remaining_s']:.0f}s verbleibend, "
                  f"Ziel-Rate {st.get('rate')} rps",
                  flush=True)
        else:
            print(f"idle: letzter Run job {st.get('job')} -> {st.get('job_state')} "
                  f"(k6-Summary siehe `kubectl logs -n website job/<name>`)",
                  flush=True)
            return 0


if __name__ == "__main__":
    sys.exit(main())
