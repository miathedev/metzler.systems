// k6-Load-Script fuer die website — wird als ConfigMap (templates/
// k6-script-configmap.yaml) in den Run-Job gemountet und von der load-App
// via Env konfiguriert (K6_* kommen aus charts/load values.k6/env).
import http from "k6/http";
import { check } from "k6";

export const options = {
  scenarios: {
    website: {
      // constant-arrival-rate: konstante Request-Rate — skaliert die website
      // am HPA (cpu) vorbei ins Limit, weil die Last nicht von VUs abhaengt.
      executor: "constant-arrival-rate",
      rate: Number(__ENV.K6_RATE || "1000"),
      timeUnit: "1s",
      duration: __ENV.K6_DURATION || "5m",
      preAllocatedVUs: Number(__ENV.K6_VUS || "100"),
      maxVUs: Number(__ENV.K6_MAX_VUS || "600"),
      gracefulStop: "30s",
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.05"], // <5% Fehler gilt als bestanden
  },
};

export default function () {
  const res = http.get(__ENV.K6_TARGET_URL || "http://website:8080/", {
    // Cache-Buster: eindeutiger Query-Param pro Request, damit weder
    // Traefik noch nginx etwas aus einem Cache bedienen kann.
    params: { _: `${__VU}-${__ITER}-${Date.now()}` },
  });
  check(res, { "status is 2xx": (r) => r.status >= 200 && r.status < 300 });
}
