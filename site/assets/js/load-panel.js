/**
 * load-panel.js — Load-Test-Panel unter dem Live-Chart (eigenes Bundle).
 *
 * 1) Auto-Trigger pro menschlichem Visit: getHumanSignals() sammelt ~1.2 s
 *    Telemetrie (webdriver, Plugins, Languages, outer size, WebGL-Renderer,
 *    trusted clicks, mouse moves, time-to-first-input). Bei Human-Score feuert
 *    die Seite automatisch POST /api/load/?source=visitor&duration_s&rate —
 *    einmalig pro Session (sessionStorage-Guard). Läuft schon ein Run, antwortet
 *    der Server 409 (Single-State) und wird ignoriert. Die Signals landen als
 *    Annotation am k6-Job (Nachvollziehbarkeit im Cluster).
 * 2) Manuell: Button startet den vollen Run (Server-Defaults, 5 min).
 * 3) Status-Poll alle 2 s auf /api/load/status: RUNNING -> pulsierende LED,
 *    Status als Klartext, grosser Countdown + schmaler Balken; SUCCEEDED ->
 *    echte k6-Summary (aus dem Job-Log via /status -> last_run.metrics) als
 *    reine Zahlenfolge (Label + Zahl, ohne Boxen, ohne Animation).
 *    Extravagant, aber keine erfundenen Zahlen — alles kommt vom load-Service.
 * 4) Pro Run einmalig das Event "lm-run-start" (Detail: startedAt in ms) auf
 *    window feuern — live-metrics.js zoomt den Chart dann auf den Run-Start
 *    (Anfangsbesuch bei laufendem Run genauso wie neu gestarteter Run).
 *
 * Skalierung der website sieht man als Step in der pods-Linie des Charts oben.
 * API-Daten landen nur via textContent, nie via innerHTML. Alle Tailwind-Klassen
 * sind volle Literale (Source-Scanner), dynamische Werte via Inline-Styles.
 */
(function () {
  "use strict";

  var root = document.getElementById("lp-root");
  if (!root || !window.fetch) return;

  var loadUrl = root.getAttribute("data-load") || "/api/load/";
  var autoDuration = parseInt(root.getAttribute("data-auto-duration") || "90", 10) || 90;
  var autoRate = parseInt(root.getAttribute("data-auto-rate") || "500", 10) || 500;

  var btn = document.getElementById("lp-btn");
  var led = document.getElementById("lp-led");
  var stateEl = document.getElementById("lp-state");
  var liveEl = document.getElementById("lp-live");
  var countEl = document.getElementById("lp-count");
  var barEl = document.getElementById("lp-bar");
  var metricsEl = document.getElementById("lp-metrics");

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  // ---- human signals (Bot-Erkennung) ----

  function getHumanSignals() {
    var signals = {
      webdriver: !!navigator.webdriver,
      noPlugins: !navigator.plugins || navigator.plugins.length === 0,
      zeroOuterSize: window.outerWidth === 0 || window.outerHeight === 0,
      noLanguages: !navigator.languages || navigator.languages.length === 0,
      trustedClicks: 0,
      mouseMoves: 0,
      timeToFirstInput: null,
      renderer: "",
    };
    var start = performance.now();
    try {
      var canvas = document.createElement("canvas");
      var gl = canvas.getContext && canvas.getContext("webgl");
      var debugInfo = gl && gl.getExtension ? gl.getExtension("WEBGL_debug_renderer_info") : null;
      if (debugInfo) {
        signals.renderer = String(gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL));
      }
    } catch (e) {
      // WebGL nicht verfuegbar — Signal bleibt leer
    }
    var recordFirstInput = function () {
      if (signals.timeToFirstInput == null) {
        signals.timeToFirstInput = Math.round(performance.now() - start);
      }
    };
    window.addEventListener("mousemove", function () {
      signals.mouseMoves++;
      recordFirstInput();
    }, { passive: true });
    window.addEventListener("click", function (e) {
      if (e.isTrusted) signals.trustedClicks++;
      recordFirstInput();
    }, { passive: true });
    // kurz warten, damit Telemetrie einsickert, bevor entschieden wird
    return new Promise(function (resolve) {
      setTimeout(function () { resolve(signals); }, 1200);
    });
  }

  function isHuman(s) {
    if (s.webdriver) return false; // automatisierter Browser
    if (/swiftshader|llvmpipe|software/i.test(s.renderer)) return false; // headless GPU
    var interacted = s.trustedClicks > 0 || s.mouseMoves > 10 ||
      (s.timeToFirstInput != null && s.timeToFirstInput < 20000);
    var botish = s.noPlugins && s.noLanguages && s.zeroOuterSize;
    return interacted && !botish;
  }

  // ---- formatting ----

  function fmtRemain(s) {
    s = Math.max(0, Math.floor(s || 0));
    return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0");
  }

  function fmtInt(n) {
    return isFinite(n) ? Math.round(n).toLocaleString("de-DE") : "-";
  }

  function fmtBytes(b) {
    if (b == null || !isFinite(b)) return "-";
    var u = ["B", "kB", "MB", "GB", "TB"];
    var i = 0;
    while (b >= 1000 && i < u.length - 1) { b /= 1000; i++; }
    return b.toLocaleString("de-DE", { maximumFractionDigits: i ? 1 : 0 }) + " " + u[i];
  }

  // ---- paint ----

  // Eine Kennzahl als Label + Zahl, ohne Box, ohne Animation (Hausstil:
  // keine Cards-in-Cards, einzige Bewegung bleibt die Live-LED)
  function metricCell(label, value, fmt) {
    var cell = el("div");
    cell.appendChild(el("div", "font-mono text-xs text-gray-500", label));
    cell.appendChild(el("div", "mt-1 font-mono text-2xl font-medium tabular-nums text-gray-900 dark:text-gray-100", fmt(value)));
    return cell;
  }

  function paintMetrics(m) {
    metricsEl.textContent = "";
    if (!m) {
      metricsEl.classList.add("hidden");
      return;
    }
    metricsEl.classList.remove("hidden");
    metricsEl.appendChild(metricCell("requests", m.http_reqs, fmtInt));
    metricsEl.appendChild(metricCell("avg rps", m.rps, fmtInt));
    metricsEl.appendChild(metricCell("p95", m.p95_ms, function (v) { return v == null ? "-" : v.toFixed(1) + " ms"; }));
    metricsEl.appendChild(metricCell("failed", m.failed_pct, function (v) { return v == null ? "-" : v.toFixed(2) + " %"; }));
    metricsEl.appendChild(metricCell("data", m.data_received_bytes, fmtBytes));
    metricsEl.appendChild(metricCell("vus", m.vus, fmtInt));
  }

  var lastMetricsKey = "";
  var announcedRun = ""; // Run, dessen Start schon an den Chart gemeldet wurde

  // Chart-Fenster auf den Start des aktiven Runs zoomen (einmalig pro Run,
  // damit manuelles Zoomen des Users nicht alle 2 s zurueckgesetzt wird)
  function announceRunStart(st) {
    if (!st || !st.job || !st.started_at) return;
    var key = st.job + "|" + st.started_at;
    if (key === announcedRun) return;
    var ms = Date.parse(st.started_at);
    if (!ms) return;
    announcedRun = key;
    window.dispatchEvent(new CustomEvent("lm-run-start", { detail: { startedAt: ms } }));
  }

  function paint(st) {
    var running = !!(st && st.state === "running");
    var js = (st && st.job_state) || "idle";
    if (running) announceRunStart(st);
    if (led) {
      led.className = "lm-led inline-block h-2 w-2 rounded-full " +
        (running ? "bg-amber-400 lm-led-live"
          : js === "Failed" ? "bg-red-500"
          : js === "Succeeded" ? "bg-emerald-400" : "bg-gray-600");
    }
    if (stateEl) {
      // Status als Klartext neben der LED, nie als Pill
      stateEl.textContent = running ? "running" : js.toLowerCase();
      stateEl.className = "font-mono text-xs " +
        (running ? "text-amber-600 dark:text-amber-300"
          : js === "Failed" ? "text-red-500 dark:text-red-400"
          : js === "Succeeded" ? "text-emerald-600 dark:text-emerald-400"
          : "text-gray-400");
    }
    if (btn) {
      btn.disabled = running;
      btn.textContent = running ? "running" : "start k6 run (5 min)";
    }
    if (liveEl) {
      liveEl.classList.toggle("hidden", !running);
      if (running) {
        if (countEl) countEl.textContent = fmtRemain(st.remaining_s);
        if (barEl && st.duration_s) {
          var pct = Math.min(100, Math.max(0, (1 - st.remaining_s / st.duration_s) * 100));
          barEl.style.width = pct.toFixed(1) + "%";
        }
      }
    }
    var lr = st && st.last_run;
    var key = lr ? lr.job + "|" + lr.job_state : "";
    if (lr && lr.job_state === "Succeeded" && lr.metrics && key !== lastMetricsKey) {
      lastMetricsKey = key;
      paintMetrics(lr.metrics);
    } else if (!lr) {
      lastMetricsKey = "";
      if (metricsEl) {
        metricsEl.classList.add("hidden");
        metricsEl.textContent = "";
      }
    }
  }

  function poll() {
    return fetch(loadUrl + "status", { headers: { Accept: "application/json" } })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(paint)
      .catch(function () {
        // load-Service nicht erreichbar: Panel unveraendert lassen
      });
  }

  if (btn) {
    btn.addEventListener("click", function () {
      btn.disabled = true;
      btn.textContent = "starting";
      fetch(loadUrl + "?source=button", { method: "POST" })
        .then(function (r) {
          if (r.status === 409) { poll(); return; } // Single-State
          if (!r.ok) throw new Error("HTTP " + r.status);
          poll();
        })
        .catch(function (e) {
          btn.disabled = false;
          // HTTP-Status mitzeigen, sonst sieht man nicht, woran es lag (403/429/...)
          btn.textContent = "error " + (e && e.message ? e.message : "retry");
        });
    });
  }

  poll();
  setInterval(poll, 2000);

  // ---- auto-trigger fuer menschliche Besuche ----

  getHumanSignals().then(function (signals) {
    if (!isHuman(signals)) return;
    var guard = null;
    try {
      guard = window.sessionStorage && window.sessionStorage.getItem("lp-auto");
    } catch (e) {
      // sessionStorage nicht verfuegbar — Guard wirkungslos, Run trotzdem ok
    }
    if (guard) return;
    fetch(loadUrl + "status", { headers: { Accept: "application/json" } })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (st) {
        if (st && st.state === "running") return; // laeuft schon -> 409 sparen
        try { window.sessionStorage && window.sessionStorage.setItem("lp-auto", "1"); } catch (e) {}
        return fetch(loadUrl + "?source=visitor&duration_s=" + autoDuration + "&rate=" + autoRate, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ signals: signals }),
        }).then(function (r) {
          if (r.ok || r.status === 409) poll();
        });
      })
      .catch(function () {});
  });
})();
