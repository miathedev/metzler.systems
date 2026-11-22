/**
 * live-metrics.js - "Live from the cluster" Konsole auf der Startseite.
 *
 * Verbindet sich mit dem SSE-Endpunkt der metrics API (/api/metrics/stream, bis
 * 30 Samples/s) und rendert jede Station (Deployment) als kompakten Inline-Chip
 * in EINER Zeile (Grafana-"Stat"-Stil: Status-LED + Name in Stationsfarbe +
 * Pod-Anzahl) - keine eigene Zeile/Flaeche pro Station. Darunter ein grosses
 * ECharts-Trendpanel (CPU/MEM/Pods) ueber das GESAMTE RAM-Cache-Fenster des
 * Servers (30 min): per dataZoom-Slider/inside-Zoom beliebig rein- und rauszoomen.
 *
 * Achsen/Legende: cpu = durchgezogene Linie (linke Y-Achse, m), mem =
 * gestrichelte Linie (rechte Y-Achse, Mi), pods = gepunktete Step-Linie
 * (zweite rechte Y-Achse) - am Step sieht man exakt, wann skaliert wurde.
 * Die Legende ist handgebautes HTML mit echten Strich-Swatches, damit klar
 * ist, welcher Strich was bedeutet. Die Serie traegt Namen + Einheit
 * ("website cpu (m)"). Jedes Sample-Event traegt "b" (Buffer-Fuellstand),
 * damit die RAM-cache-Anzeige live aktualiert.
 *
 * Run-Zoom: load-panel.js feuert bei aktivem k6-Run einmalig das window-Event
 * "lm-run-start" (Detail: startedAt in ms). Dann wird der dataZoom so gesetzt,
 * dass das Fenster am Run-Start beginnt; die rechte Kante bleibt bei 100 %
 * (live). So sieht man beim Seitenaufruf direkt den laufenden Run ab seinem
 * Start — und ebenso automatisch bei jedem neu gestarteten Run.
 *
 * Design (verbindlicher Hausstil des Projekts): Site-Card als Panel, der Chart als
 * schwarzes Inset darin, Haarlinien dazwischen. Keine Pills, keine " · "
 * Separatoren, Status als LED + Klartext. Akzent fuehrt LED-Amber (Site-Primary),
 * Teal nur als zweite Hue, weitere Stationen in ruhigen Ink-Neutralschritten.
 * Einzige Bewegung: die pulsende Live-LED.
 *
 * Bundled mit Hugo js.Build (echarts/core, tree-shaken). Alle Tailwind-Klassen
 * sind volle Literale, damit der Source-Scanner sie findet; dynamische Werte
 * laufen ueber Inline-Styles / ECharts-Optionen, nie ueber generierte
 * Klassennamen. API-Daten landen nur via textContent, nie via innerHTML.
 */
import * as echarts from "echarts/core";
import { LineChart } from "echarts/charts";
import { DataZoomComponent, GridComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";

// kein TooltipComponent: die Konsole zeigt Achsen + Legende, keine Hover-Box
echarts.use([LineChart, GridComponent, DataZoomComponent, CanvasRenderer]);

(function () {
  "use strict";

  var root = document.getElementById("lm-root");
  if (!root || !window.fetch) return;

  var endpoint = root.getAttribute("data-endpoint") || "/api/metrics/state";
  var streamAttr = root.getAttribute("data-stream");
  var streamUrl = streamAttr || endpoint.replace(/\/state$/, "/stream");
  var pollSeconds = parseInt(root.getAttribute("data-poll") || "3", 10) || 3;
  // window = wie viel des Server-RAM-Caches geladen/angezeigt wird (30 min =
  // komplettes Fenster, per dataZoom beliebig zoombar)
  var windowSeconds = parseInt(root.getAttribute("data-window") || "60", 10) || 60;
  var windowMs = windowSeconds * 1000;

  var stationsEl = document.getElementById("lm-stations");
  var legendEl = document.getElementById("lm-legend");
  var emptyEl = document.getElementById("lm-empty");
  var statusDot = document.getElementById("lm-status-dot");
  var statusText = document.getElementById("lm-status-text");
  var clockEl = document.getElementById("lm-clock");
  var sourceEl = document.getElementById("lm-source");
  var chartEl = document.getElementById("lm-chart");

  // Theme-Pack "serverroom": amber LED accent, teal only as second hue when a
  // second station must be told apart, then quiet ink neutrals.
  var STATION_COLORS = ["#fbbf24", "#2dd4bf", "#94a3b8", "#64748b", "#8b93a3", "#565e6d"];
  var INK = "#7a8296"; // muted text on ink surface
  var AXIS_LINE = "rgba(255,255,255,0.14)";
  var GRID_LINE = "rgba(255,255,255,0.05)";
  var MONO = "monospace";

  var rows = {}; // station name -> row refs
  var order = []; // insertion order, stable colors per station
  var chartData = {}; // name -> { cpu: [[t,m]], mem: [[t,Mi]], pods: [[t,n]] }
  var chart = null;
  var chartPending = false;
  var runStartMs = 0; // letzter gemeldeter k6-Run-Start (0 = keiner)
  var es = null;
  var pollTimer = null;
  var reconnectTimer = null;
  var lastT = 0;
  var helloCfg = null; // hello-Event, fuer RAM-cache-Anzeige
  var lastBuffered = -1;
  var legendKey = "";

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  function fmtTime(ms) {
    if (!ms) return "--:--:-- UTC";
    return new Date(ms).toISOString().substr(11, 8) + " UTC";
  }

  function ledClass(state) {
    if (state === "running") return "bg-amber-400 lm-led-live";
    if (state === "zero") return "bg-gray-600";
    return "bg-red-500";
  }

  // Station als kompakte Inline-Gruppe in einer gemeinsamen Zeile (Stat-Stil):
  // LED = Zustand, Name in Stationsfarbe (die Farbe der Chart-Serie/Legende),
  // dann die Pod-Anzahl. children-Reihenfolge: [led, name, pods].
  function buildChip(st) {
    var color = STATION_COLORS[order.length % STATION_COLORS.length];
    var chip = el(
      "div",
      "lm-station inline-flex items-center gap-2 font-mono text-xs"
    );
    var led = el("span", "lm-led inline-block h-2 w-2 rounded-full bg-gray-600");
    var name = el("span", "font-medium", st.n || "?");
    name.style.color = color; // koppelt Chip an Serie + Legenden-Swatch
    var pods = el("span", "tabular-nums text-gray-400", "-");
    chip.appendChild(led);
    chip.appendChild(name);
    chip.appendChild(pods);
    var refs = { el: chip, led: led, pods: pods };
    refs._color = color;
    return refs;
  }

  // ---- hand-built HTML legend (real line-style swatches, incl. dashed/dotted) ----
  // Pro Eintrag: Swatch + Stationsname in Serienfarbe + Metrik in gedämpft,
  // ohne Trennzeichen dazwischen ("website cpu (m)")

  function legendItem(color, swClass, name, metric) {
    var item = el("span", "inline-flex items-center");
    var sw = el("span", "lm-sw " + swClass);
    sw.style.borderTopColor = color;
    var label = el("span", null, name);
    label.style.color = color;
    var meta = el("span", "text-gray-500", " " + metric);
    item.appendChild(sw);
    item.appendChild(label);
    item.appendChild(meta);
    return item;
  }

  function rebuildLegend() {
    var key = order.join("|");
    if (!legendEl || key === legendKey) return;
    legendKey = key;
    legendEl.textContent = "";
    order.forEach(function (name) {
      var row = rows[name];
      if (!row) return;
      legendEl.appendChild(legendItem(row._color, "lm-sw-solid", name, "cpu (m)"));
      legendEl.appendChild(legendItem(row._color, "lm-sw-dash", name, "mem (Mi)"));
      legendEl.appendChild(legendItem(row._color, "lm-sw-dot", name, "pods"));
    });
  }

  // ---- ECharts trend panel (whole RAM-cache window, zoomable) ----

  function baseOption() {
    return {
      backgroundColor: "transparent",
      animation: false, // updates arrive at sample rate, no extra tweening
      // bottom 64: Platz fuer Achsenlabels + Achsenname ueber dem Zoom-Slider
      grid: { left: 44, right: 88, top: 30, bottom: 64 },
      // Achsenbeschriftung: Name = Einheit/Bedeutung, dezent in INK-Mono
      xAxis: {
        type: "time",
        name: "time (UTC)",
        nameLocation: "middle",
        nameGap: 26,
        nameTextStyle: { color: INK, fontFamily: MONO, fontSize: 10 },
        axisLine: { lineStyle: { color: AXIS_LINE } },
        axisLabel: { color: INK, fontFamily: MONO, fontSize: 10, formatter: "{HH}:{mm}:{ss}" },
        splitLine: { show: true, lineStyle: { color: GRID_LINE } },
      },
      yAxis: [
        { // cpu, linke Achse
          type: "value",
          name: "cpu (m)",
          nameLocation: "end",
          nameGap: 6,
          nameTextStyle: { color: INK, fontFamily: MONO, fontSize: 10 },
          axisLine: { lineStyle: { color: AXIS_LINE } },
          axisLabel: { color: INK, fontFamily: MONO, fontSize: 10 },
          splitLine: { lineStyle: { color: GRID_LINE } },
        },
        { // mem, rechte Achse (innen versetzt)
          type: "value",
          name: "mem (Mi)",
          nameLocation: "end",
          nameGap: 6,
          nameTextStyle: { color: INK, fontFamily: MONO, fontSize: 10 },
          position: "right",
          offset: 44,
          axisLine: { lineStyle: { color: AXIS_LINE } },
          axisTick: { show: false },
          axisLabel: { color: INK, fontFamily: MONO, fontSize: 10 },
          splitLine: { show: false },
        },
        { // pods, rechte Achse (aussen) - Skalierung als Step sichtbar
          type: "value",
          name: "pods",
          nameLocation: "end",
          nameGap: 6,
          nameTextStyle: { color: INK, fontFamily: MONO, fontSize: 10 },
          position: "right",
          offset: 0,
          min: 0,
          interval: 1,
          axisLine: { lineStyle: { color: AXIS_LINE } },
          axisTick: { show: false },
          axisLabel: { color: INK, fontFamily: MONO, fontSize: 10, formatter: "{value}" },
          splitLine: { show: false },
        },
      ],
      // innen zoomen (Mausrad/Trackpad), Slider unten = komplettes Fenster
      dataZoom: [
        { type: "inside" },
        {
          type: "slider",
          bottom: 4,
          height: 16,
          start: 0,
          end: 100,
          borderColor: "rgba(255,255,255,0.12)",
          backgroundColor: "rgba(255,255,255,0.03)",
          fillerColor: "rgba(251,191,36,0.15)",
          handleStyle: { color: "#fbbf24", borderColor: "#fbbf24" },
          moveHandleStyle: { color: "#fbbf24" },
          dataBackground: {
            lineStyle: { color: "rgba(255,255,255,0.25)" },
            areaStyle: { color: "rgba(255,255,255,0.06)" },
          },
          textStyle: { color: INK, fontFamily: MONO, fontSize: 9 },
        },
      ],
      series: [],
    };
  }

  // Pro Station drei Serien; der Serienname traegt Metrik + Einheit ohne
  // Trenner ("website cpu (m)"). cpu solid (y0), mem dashed (y1), pods dotted
  // + step (y2). Erste Station fuehrt mit Akzent + Area-Fill. lttb-Sampling
  // haelt das Rendering bei 30 min x 30 Hz billig.
  function seriesList() {
    var series = [];
    order.forEach(function (name) {
      var row = rows[name];
      if (!row) return;
      var color = row._color;
      var d = chartData[name] || { cpu: [], mem: [], pods: [] };
      var lead = series.length === 0;
      series.push({
        name: name + " cpu (m)",
        type: "line",
        showSymbol: false,
        yAxisIndex: 0,
        z: 3,
        sampling: "lttb",
        data: d.cpu,
        lineStyle: { width: 1.8, color: color },
        itemStyle: { color: color },
        areaStyle: lead ? { color: color + "14" } : undefined,
      });
      series.push({
        name: name + " mem (Mi)",
        type: "line",
        showSymbol: false,
        yAxisIndex: 1,
        z: 2,
        sampling: "lttb",
        data: d.mem,
        lineStyle: { width: 1.2, type: "dashed", color: color },
        itemStyle: { color: color },
        opacity: 0.75,
      });
      series.push({
        name: name + " pods",
        type: "line",
        step: "end",
        showSymbol: false,
        yAxisIndex: 2,
        z: 4,
        sampling: "lttb",
        data: d.pods,
        lineStyle: { width: 1.4, type: "dotted", color: color },
        itemStyle: { color: color },
      });
    });
    return series;
  }

  function ensureChart() {
    if (chart || !chartEl) return;
    chart = echarts.init(chartEl);
    chart.setOption(baseOption());
    applyRunZoom(); // Event kam evtl. vor der Chart-Init
  }

  // dataZoom linke Kante auf den Run-Start setzen (5 s Puffer), rechte Kante
  // bleibt end:100 -> Fenster folgt weiter live. Nur startValue angeben, der
  // Rest des Zooms bleibt unberuehrt.
  function applyRunZoom() {
    if (!chart || !runStartMs) return;
    chart.dispatchAction({
      type: "dataZoom",
      startValue: Math.max(0, runStartMs - 5000),
    });
  }

  // load-panel.js meldet jeden neuen/laufenden k6-Run genau einmal
  window.addEventListener("lm-run-start", function (ev) {
    var t0 = ev && ev.detail && ev.detail.startedAt;
    if (!t0) return;
    runStartMs = t0;
    applyRunZoom();
  });

  function renderChart() {
    if (!chart || !chartEl.clientWidth) return; // section hidden
    chart.setOption({ series: seriesList() });
  }

  function scheduleChart() {
    ensureChart();
    if (chartPending) return;
    chartPending = true;
    // throttle to ~8 fps: samples may arrive at 30 Hz, text updates per sample
    setTimeout(function () {
      chartPending = false;
      renderChart();
    }, 120);
  }

  window.addEventListener("resize", function () {
    if (chart) chart.resize();
  });

  // ---- data ingestion ----

  function trim(arr, cutoff) {
    var i = 0;
    while (i < arr.length && arr[i][0] < cutoff) i++;
    if (i > 0) arr.splice(0, i);
  }

  function updateSource(buffered) {
    if (!sourceEl || !helloCfg || buffered == null || buffered === lastBuffered) return;
    lastBuffered = buffered;
    // nur die nötigste Angabe: Fuellstand des RAM-Cache als live Sample-Count
    sourceEl.textContent =
      "RAM cache " + helloCfg.retention_minutes + " min (" +
      buffered + "/" + helloCfg.max_samples + " samples)";
  }

  function feedSample(sample) {
    if (!sample || !sample.s) return;
    var t = sample.t;
    // Monotonie-Guard: ECharts zeichnet in Datenreihenfolge, ein Sample mit
    // t <= lastT wuerde die Linie rueckwaerts malen (Zickzack). Tritt auf bei
    // SSE-Reconnect (history wird komplett neu gefuettert) und im Poll-Mix
    // (gecachter /state-Zeitstempel kann hinter dem letzten Stream-Sample liegen).
    if (t <= lastT) return;
    lastT = t;
    if (clockEl) clockEl.textContent = fmtTime(t);
    if (emptyEl) emptyEl.style.display = "none";
    updateSource(sample.b);

    var seen = {};
    sample.s.forEach(function (st) {
      seen[st.n] = true;
      var row = rows[st.n];
      if (!row) {
        row = buildChip(st);
        rows[st.n] = row;
        order.push(st.n);
        stationsEl.appendChild(row.el);
      }
      row.led.className = "lm-led inline-block h-2 w-2 rounded-full " + ledClass(st.st);
      row.pods.textContent = st.p + (st.p === 1 ? " pod" : " pods");
      if (!chartData[st.n]) chartData[st.n] = { cpu: [], mem: [], pods: [] };
      chartData[st.n].cpu.push([t, st.c / 1e6]);
      chartData[st.n].mem.push([t, st.m / 1048576]);
      chartData[st.n].pods.push([t, st.p]);
    });

    var cutoff = t - windowMs;
    Object.keys(chartData).forEach(function (name) {
      trim(chartData[name].cpu, cutoff);
      trim(chartData[name].mem, cutoff);
      trim(chartData[name].pods, cutoff);
    });
    order.slice().forEach(function (name) {
      if (!seen[name]) {
        var row = rows[name];
        if (row) row.el.remove();
        delete rows[name];
        delete chartData[name];
        order.splice(order.indexOf(name), 1);
      }
    });
    rebuildLegend();
    scheduleChart();
  }

  // /state (poll fallback) -> slim sample shape
  function slimFromState(state) {
    var t = Date.parse(state.time) || Date.now();
    var s = (state.stations || []).map(function (st) {
      var cpu = 0;
      var mem = 0;
      var pods = 0;
      var states = {};
      (st.tracks || []).forEach(function (tr) {
        var p = tr.pod;
        if (p) {
          pods++;
          cpu += p.cpu_nano || 0;
          mem += p.mem_bytes || 0;
          states[p.state] = true;
        }
      });
      var keys = Object.keys(states);
      var sstate = keys.length === 0 ? "zero" : keys.length === 1 && keys[0] === "running" ? "running" : keys.sort().join("+");
      return { n: st.name, c: cpu, m: mem, p: pods, st: sstate };
    });
    return { t: t, s: s };
  }

  function setStatus(ok) {
    if (statusDot) {
      statusDot.className = "h-2 w-2 rounded-full " + (ok ? "bg-amber-400 lm-led-live" : "bg-red-500");
    }
    root.classList.toggle("lm-offline", !ok);
  }

  // ---- transport: SSE stream with polling fallback ----

  function startPolling() {
    if (pollTimer) return;
    if (statusText) statusText.textContent = "online";
    var tick = function () {
      fetch(endpoint, { headers: { Accept: "application/json" } })
        .then(function (r) {
          if (!r.ok) throw new Error("HTTP " + r.status);
          return r.json();
        })
        .then(function (state) {
          setStatus(true);
          feedSample(slimFromState(state));
        })
        .catch(function () {
          setStatus(false);
        });
    };
    tick();
    pollTimer = setInterval(tick, pollSeconds * 1000);
  }

  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  function startStream() {
    if (!window.EventSource) {
      startPolling();
      return;
    }
    if (es) {
      es.close();
      es = null;
    }
    // komplettes RAM-Cache-Fenster anfordern (max_points hoch genug fuer
    // 30 min x 30 Hz ohne Striding), Zoomen passiert clientseitig im Chart
    var url = streamUrl + "?window_seconds=" + windowSeconds + "&max_points=60000";
    es = new EventSource(url);
    es.addEventListener("hello", function (ev) {
      var h = JSON.parse(ev.data);
      helloCfg = h;
      stopPolling();
      setStatus(true);
      if (statusText) statusText.textContent = "online";
      updateSource(h.buffered);
    });
    es.addEventListener("history", function (ev) {
      var samples = (JSON.parse(ev.data).samples) || [];
      // History-Burst in Chunks fuettern: bis zu 54k Samples (30 min x 30 Hz)
      // synchron per forEach wuerden den Main Thread kurz blockieren
      var i = 0;
      function chunk() {
        var end = Math.min(i + 2000, samples.length);
        for (; i < end; i++) feedSample(samples[i]);
        if (i < samples.length) setTimeout(chunk, 0);
      }
      chunk();
    });
    es.addEventListener("sample", function (ev) {
      feedSample(JSON.parse(ev.data));
    });
    es.onopen = function () {
      // Verbindung steht (wieder): Polling-Fallback aus, Status auf online
      setStatus(true);
      stopPolling();
      if (statusText) statusText.textContent = "online";
    };
    es.onerror = function () {
      if (!es) return;
      // CONNECTING wie CLOSED behandeln: Polling-Fallback an, damit die Konsole
      // nie dunkel bleibt. Nur bei CLOSED (endgueltig geschlossen, z. B. Proxy-
      // Timeout) zusaetzlich einen Reconnect planen.
      setStatus(false);
      startPolling();
      if (es.readyState === 2) {
        clearTimeout(reconnectTimer);
        reconnectTimer = setTimeout(startStream, 15000);
      }
    };
  }

  // Lazy start: das echarts-Bundle (~520 kB) und der SSE-Stream laufen erst an,
  // wenn das Panel im Viewport ist. Ohne IntersectionObserver sofort starten.
  if ("IntersectionObserver" in window) {
    var started = false;
    var io = new IntersectionObserver(function (entries) {
      if (started) return;
      entries.forEach(function (en) {
        if (en.isIntersecting) {
          started = true;
          io.disconnect();
          startStream();
        }
      });
    });
    io.observe(root);
  } else {
    startStream();
  }
})();
