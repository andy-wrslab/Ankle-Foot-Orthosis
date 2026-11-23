// Live plots on uPlot (Nov 23, Andy: "it feels like a low refresh rate"; torque plot stalls).
//
// * Canvas 2D (no WebGL): the page had 17 Plotly scattergl plots in one DOM, over Chrome's
//   ~16 WebGL-context limit, and a Plotly redraw costs ~6 ms per plot (axes re-laid out on
//   every extendTraces). uPlot redraws a 1000-point plot in about 1 ms.
// * One shared model-time clock drives EVERY visible plot's x range on EVERY animation frame
//   (~60 fps), whether or not that plot got new points: no plot can stop its time axis
//   because its values did not change. The clock follows the newest sample ~0.08 s behind
//   (smoothed against wall time, so scrolling is even although data arrives 20x / s) and
//   never runs past the newest sample.
// * Data: the page's own 100 Hz buffer (SSE: first message full, then deltas), fed directly
//   by assets/sse.js (window._afoLiveMsg), no Dash cycle per message.
// * Gait: Torque, Stride velocity. Sensors: FSR (8 named) and Linear acceleration. Training:
//   Assistance, Uc from /api/live/training (1 Hz, min/max binned, up to 5 min).
// * Hidden browser tabs, other pages and other sub-tabs: nothing drawn.
// * No hold (Andy 14:34: "no need for hold in any of the pages"): plots always follow the
//   shared clock; hovering only shows the cursor readout (time + every trace's value).
// * Every plot has the same y-axis gutter and right padding, so the time ticks of stacked
//   plots line up vertically.
// * Test hook: window._afoPlots.state() (ranges, last x, sizes, fps).
(function () {
    'use strict';
    var E = window._afoPlots = window._afoPlots || {};
    E.plots = {};          // id -> {u, host, spec, ...}
    E.frames = 0; E.drawn = 0; E.fpsLog = [];
    var LAG = 0.08, Y_GUTTER = 52, Y_LABEL = 24, X_AXIS_H = 30;   // Y_LABEL: band for the 16 px y label (Andy 15:21)
    E.X_AXIS_H = X_AXIS_H;
    var HOLD = {on: false};                             // kept for the state() hook: always false
    var SERIES_KEYS = ['ankle', 'torque', 'demand_torque', 'gait', 'sv_target', 'uc', 'assistance_level', 'ankle_vel', 'heel_strike'];

    function spec() {
        if (E.spec) { return E.spec; }
        var el = document.getElementById('liveSpec');
        if (!el) { return null; }
        try { E.spec = JSON.parse(el.getAttribute('data-spec')); } catch (e) { return null; }
        return E.spec;
    }
    function lowerT(arr, x) { var lo = 0, hi = arr.length; while (lo < hi) { var m = (lo + hi) >> 1; if (arr[m] < x) { lo = m + 1; } else { hi = m; } } return lo; }

    // ------------------------------------------------------------ buffer (100 Hz)
    var B = null;
    function ingest(p) {
        var t = Array.isArray(p.t) ? p.t : [];
        var sess = (p.meta || {}).session;
        // a new run / restart: another stream session, or the model time back by more than 1 s
        // (Andy 16:08: after the Speedgoat reboot the old run's plots stayed until a reload)
        var restart = !!B && ((sess !== undefined && sess !== B.session && B.t.length > 0) ||
            (t.length > 0 && B.t.length > 0 && t[t.length - 1] < B.t[B.t.length - 1] - 1));
        var reset = !B || p.kind === 'full' || restart;
        var i0 = 0;
        if (reset) {
            B = {t: [], s: {}, press: [], imu: [], gen: (B ? B.gen + 1 : 1), session: sess, ver: 0};
            SERIES_KEYS.forEach(function (n) { B.s[n] = []; });
            E.clock = null;
            if (restart) { clearAll(); }
        } else if (B.t.length) {
            var last = B.t[B.t.length - 1];
            while (i0 < t.length && t[i0] <= last) { i0++; }
        }
        if (i0 < t.length) {
            var nOld = B.t.length, add = t.length - i0;
            Array.prototype.push.apply(B.t, t.slice(i0));
            SERIES_KEYS.forEach(function (n) {
                var a = p[n], dst = B.s[n];
                if (Array.isArray(a)) { Array.prototype.push.apply(dst, a.slice(i0)); } else { for (var j = 0; j < add; j++) { dst.push(null); } }
            });
            ['press', 'imu'].forEach(function (g) {
                var src = Array.isArray(p[g]) ? p[g] : [];
                for (var j = 0; j < src.length; j++) {
                    if (!B[g][j]) { B[g][j] = new Array(nOld).fill(null); }
                    Array.prototype.push.apply(B[g][j], (src[j] || []).slice(i0));
                }
            });
            var keep = 10 * 100 + 300;
            if (B.t.length > keep + 300) {
                var cut = B.t.length - keep;
                B.t.splice(0, cut);
                SERIES_KEYS.forEach(function (n) { B.s[n].splice(0, cut); });
                ['press', 'imu'].forEach(function (g) { B[g].forEach(function (a) { a.splice(0, cut); }); });
            }
            B.ver++;
            B.arrivedAt = performance.now();
        }
        if (p.latest) { B.latest = p.latest; }
        B.statusword = p.statusword;
    }
    E.buffer = function () { return B; };

    // on a restart: every plot (Gait, Sensors, Training) emptied at once, the shared clock and the
    // Training buffer dropped (refetched now), so no point of the old run is drawn again
    function clearAll() {
        E.resets = (E.resets || 0) + 1;
        E.shown = null;
        Object.keys(E.plots).forEach(function (id) {
            var P = E.plots[id];
            if (!P || !P.u) { return; }
            var empty = [[]];
            P.spec.series.forEach(function () { empty.push([]); });
            try { P.u.setData(empty, false); } catch (e) { /* plot gone */ }
            P.ver = -1; P.gen = -1; P.lastX = null;
        });
        if (typeof TR !== 'undefined' && TR) { TR.data = null; TR.at = 0; TR.ver = (TR.ver || 0) + 1; }
    }

    var linkSession = null;
    window._afoLiveMsg = function (raw) {
        try {
            var p = raw ? (window._afoParse ? window._afoParse(raw) : JSON.parse(raw)) : null;
            if (!p) { return; }
            window._afoLastSnapshot = p; window._afoLastPacketAt = Date.now();
            ingest(p);
            var meta = p.meta || {};
            if (meta.session !== undefined && meta.session !== linkSession) {
                linkSession = meta.session;
                try { window.dash_clientside.set_props('link-session', {data: meta.session}); } catch (e) { /* not mounted */ }
            }
            if (window._afoOnSnapshot) { try { window._afoOnSnapshot(p); } catch (e) { console.error('[AFO] snapshot hook', e); } }
        } catch (err) { console.error('[AFO] live update failed; message skipped', err); }
    };

    // ------------------------------------------------------------ shared model-time clock
    var lastFrame = null;
    function tick(now) {
        if (!B || !B.t.length) { return null; }
        var tl = B.t[B.t.length - 1], target = tl - LAG;
        var c = E.clock;
        if (c == null || Math.abs(c - target) > 0.5) { c = target; }
        else {
            c += Math.max(0, (now - (lastFrame || now)) / 1000);
            c += (target - c) * 0.08;               // pull gently toward the newest sample
        }
        if (c > tl) { c = tl; }
        E.clock = c;
        return c;
    }

    // ------------------------------------------------------------ uPlot instances
    function cssFont() { return '13px Inter, "Segoe UI", system-ui, sans-serif'; }      // Andy 14:34: one step larger
    function fmtTick(v, step) { var d = step < 1 ? 1 : 0; return v.toFixed(d) + ' s'; }

    function zeroLinePlugin(color) {
        return {hooks: {drawAxes: [function (u) {
            var s = u.scales.y; if (!(s.min < 0 && s.max > 0)) { return; }
            var y = Math.round(u.valToPos(0, 'y', true)) + 0.5, ctx = u.ctx;
            ctx.save(); ctx.strokeStyle = color; ctx.lineWidth = 1 * devicePixelRatio;
            ctx.beginPath(); ctx.moveTo(u.bbox.left, y); ctx.lineTo(u.bbox.left + u.bbox.width, y); ctx.stroke(); ctx.restore();
        }]}};
    }

    function tooltipPlugin(ps) {
        var tip;
        return {hooks: {
            init: [function (u) {
                tip = document.createElement('div'); tip.className = 'u-tip'; tip.hidden = true;
                u.over.appendChild(tip);
            }],
            setCursor: [function (u) {
                var i = u.cursor.idx;
                if (i == null || u.cursor.left < 0) { tip.hidden = true; return; }
                var x = u.data[0][i]; if (x == null) { tip.hidden = true; return; }
                var html = '<div class="u-tip-t">' + x.toFixed(3) + ' s</div>';
                ps.series.forEach(function (s, k) {
                    if (!u.series[k + 1].show) { return; }
                    var v = u.data[k + 1][i];
                    html += '<div><i style="background:' + s.color + '"></i>' + s.label + '  <b>' +
                        (typeof v === 'number' ? v.toFixed(s.dec) : '–') + '</b>' + (s.unit ? ' ' + s.unit : '') + '</div>';
                });
                tip.innerHTML = html; tip.hidden = false;
                var left = u.cursor.left + 12, w = tip.offsetWidth;
                if (left + w > u.over.clientWidth) { left = u.cursor.left - w - 12; }
                tip.style.left = Math.max(0, left) + 'px'; tip.style.top = '4px';
            }]
        }};
    }

    function make(id, ps, host) {
        var S = spec(), st = S.style;
        var w = host.clientWidth, h = host.clientHeight;
        if (w < 20 || h < 20) { return null; }
        var opts = {
            width: w, height: h,
            legend: {show: false},
            padding: [8, 16, 0, 0],
            cursor: {y: false, points: {show: false}, drag: {x: false, y: false, setScale: false}},
            scales: {x: {time: false, auto: false}, y: {auto: false, range: function () { return ps.y; }}},
            axes: [
                // x tick labels only on the bottom plot of the tab (Andy 14:55); every plot keeps the
                // vertical grid lines at the same ticks. EVERY plot reserves the same x-axis band
                // (empty on the top plots), so all drawing areas = card height - X_AXIS_H, equal
                {stroke: st.text, font: cssFont(), grid: {show: true, stroke: st.grid, width: 1},
                 ticks: {stroke: st.grid, width: 1, size: ps.xlabels ? 4 : 0},
                 border: {show: true, stroke: st.grid, width: 1},
                 incrs: [0.5, 1, 2, 5, 10, 15, 20, 30, 60], space: 64, size: X_AXIS_H,
                 values: function (u, vals, ax, sp, incr) { return vals.map(function (v) { return ps.xlabels ? fmtTick(v, incr) : ''; }); }},
                // rotated y label next to the axis; the same gutter on every plot so the areas line up
                {stroke: st.text, font: cssFont(), grid: {stroke: st.grid, width: 1}, ticks: {show: false}, size: Y_GUTTER, space: 32,
                 label: ps.ylabel || '', labelSize: Y_LABEL, labelGap: 2, labelFont: '500 16px Inter, "Segoe UI", system-ui, sans-serif'}
            ],
            series: [{}].concat(ps.series.map(function (s) {
                return {label: s.label, stroke: s.color, width: s.width, dash: s.dash || undefined,
                        spanGaps: false, points: {show: false}};
            })),
            plugins: [zeroLinePlugin(st.zero), tooltipPlugin(ps)]
        };
        var data = [[]].concat(ps.series.map(function () { return []; }));
        var u = new window.uPlot(opts, data, host);
        var P = {id: id, u: u, host: host, spec: ps, ver: -1, gen: -1, w: w, h: h, shown: {}, gutter: Y_GUTTER, padding: opts.padding};
        if (window.ResizeObserver) {
            P.ro = new ResizeObserver(function () {
                var W = host.clientWidth, H = host.clientHeight;
                if (W >= 20 && H >= 20 && (W !== P.w || H !== P.h)) { P.w = W; P.h = H; u.setSize({width: W, height: H}); }
            });
            P.ro.observe(host);
        }
        return P;
    }
    function destroy(P) {
        try { if (P.ro) { P.ro.disconnect(); } } catch (e) { /* ignore */ }
        try { P.u.destroy(); } catch (e) { /* ignore */ }
        E.destroyed = (E.destroyed || 0) + 1;
    }
    function card(P, on) { var c = P.host.closest('.plot-card'); if (c) { c.classList.toggle('holding', on); } }


    function srcArray(src) {
        var a = src[0], k = src[1];
        if (a === 'press' || a === 'imu') { return B[a][k] || []; }
        return B.s[a] || [];
    }
    function hiddenOf(id) { return (window._afoHidden || {})[id] || {}; }

    // ------------------------------------------------------------ Training data (1 Hz)
    var TR = {data: null, busy: false, at: 0, win: null};
    function trainingPoll(now) {
        var win = window._afoTrWin || 120;
        if (TR.busy || (now - TR.at < 1000 && TR.win === win)) { return; }
        TR.busy = true; TR.at = now; TR.win = win;
        fetch('/api/live/training?w=' + win).then(function (r) { return r.json(); })
            .then(function (d) { TR.data = d; TR.ver = (TR.ver || 0) + 1; })
            .catch(function () { /* offline: keep the last */ })
            .then(function () { TR.busy = false; });
    }
    function trainingRange(t, w) { return [Math.max(0, t - w), Math.max(w, t)]; }

    // ------------------------------------------------------------ frame loop
    function visibleIds(sub) {
        var S = spec(); if (!S) { return []; }
        return Object.keys(S.plots).filter(function (id) { return S.plots[id].group === sub; });
    }
    function drawLive(P, xmin, xmax, now) {
        var u = P.u, ps = P.spec;
        if (B.ver !== P.ver || B.gen !== P.gen) {
            var i0 = lowerT(B.t, xmin - 0.05);
            var d = [B.t.slice(i0)];
            ps.series.forEach(function (s) { d.push(srcArray(s.src).slice(i0)); });
            P.ver = B.ver; P.gen = B.gen;
            u.batch(function () { u.setData(d, false); u.setScale('x', {min: xmin, max: xmax}); });
        } else {
            u.setScale('x', {min: xmin, max: xmax});
        }
        P.xmin = xmin; P.xmax = xmax;
        P.lastX = B.t[B.t.length - 1];
    }
    function drawTraining(P, now) {
        var d = TR.data, u = P.u, ps = P.spec;
        var win = window._afoTrWin || 120;
        var tl = (E.shown != null) ? E.shown : (d && typeof d.t_latest === 'number' ? d.t_latest : null);
        if (tl == null) { return; }
        var r = trainingRange(tl, win);
        if (d && d.t_latest != null && TR.ver !== P.ver) {
            var col = ps.series[0].src[1], s = (d.series || {})[col] || {t: [], v: []};
            var xs = s.t.map(function (v) { return v + d.t_latest; });
            P.ver = TR.ver;
            u.batch(function () { u.setData([xs, s.v], false); u.setScale('x', {min: r[0], max: r[1]}); });
            P.lastX = xs.length ? xs[xs.length - 1] : null;
        } else {
            u.setScale('x', {min: r[0], max: r[1]});
        }
        P.xmin = r[0]; P.xmax = r[1];
    }
    function updateChips() {
        var S = spec(); if (!S || !B || !B.latest) { return; }
        var L = B.latest;
        document.querySelectorAll('.lg[data-g]').forEach(function (chip) {
            var ps = S.plots[chip.getAttribute('data-g')]; if (!ps) { return; }
            var s = ps.series[Number(chip.getAttribute('data-k'))]; if (!s) { return; }
            var a = s.src[0], k = s.src[1];
            var v = (a === 'press' || a === 'imu') ? (Array.isArray(L[a]) ? L[a][k] : null) : L[a];
            var txt = (typeof v === 'number' && isFinite(v)) ? v.toFixed(s.dec) : '–';
            var b = chip.querySelector('.lg-v'); if (b && b.textContent !== txt) { b.textContent = txt; }
        });
    }

    var chipsAt = 0;
    function frame(now) {
        window.requestAnimationFrame(frame);
        E.frames++;
        if (document.hidden || !window.uPlot) { lastFrame = now; return; }
        if (window._afoPage && window._afoPage !== 'live') { lastFrame = now; return; }
        var S = spec(); if (!S) { lastFrame = now; return; }
        var sub = window._afoLiveSub || 'gait';
        var live = tick(now);
        lastFrame = now;
        var t = live;                                   // ONE clock for every plot of the tab, always
        E.shown = t;
        var win = window._afoWinSec || S.window_default;
        var drew = 0;
        visibleIds(sub).forEach(function (id) {
            var host = document.getElementById(id);
            if (!host || host.offsetParent === null) { return; }
            var P = E.plots[id];
            if (!P || P.host !== host) {
                if (P) { destroy(P); E.plots[id] = null; }      // host re-rendered: free the old plot first
                try { P = E.plots[id] = make(id, S.plots[id], host); } catch (e) { console.error('[AFO] ' + id + ' create failed', e); return; }
                if (!P) { return; }
            }
            var hid = hiddenOf(id);
            S.plots[id].series.forEach(function (s, k) {
                var show = !hid[k];
                if (P.shown[k] !== show) { P.shown[k] = show; P.u.setSeries(k + 1, {show: show}); }
            });
            try {
                // every group (Gait, Sensors, Training: Andy 14:34, same 2 s / 10 s range, 100 Hz)
                if (t != null) { drawLive(P, Math.max(0, t - win), Math.max(win, t), now); }   // never negative
                drew++;
            } catch (e) { console.error('[AFO] ' + id + ' draw failed', e); }
        });
        if (drew) { E.drawn++; }
        if (sub === 'sensors' && now - chipsAt > 200) { chipsAt = now; updateChips(); }
    }
    window.requestAnimationFrame(frame);

    // ------------------------------------------------------------ test / debug hook
    E.state = function () {
        var out = {clock: E.clock, shown: E.shown, held: HOLD.on, frames: E.frames, drawn: E.drawn, t_latest: B && B.t.length ? B.t[B.t.length - 1] : null,
                   buffer_len: B ? B.t.length : 0, created: Object.keys(E.plots).length, destroyed: E.destroyed || 0, plots: {}};
        Object.keys(E.plots).forEach(function (id) {
            var P = E.plots[id]; if (!P) { return; }
            out.plots[id] = {xmin: P.xmin, xmax: P.xmax, lastX: P.lastX, w: P.w, h: P.h, gutter: P.gutter,
                             area_h: P.u.bbox ? Math.round(P.u.bbox.height / (window.devicePixelRatio || 1)) : null,
                             area_w: P.u.bbox ? Math.round(P.u.bbox.width / (window.devicePixelRatio || 1)) : null,
                             visible: P.host.offsetParent !== null, held: HOLD.on,
                             shown: P.u.series.slice(1).map(function (s) { return s.show; })};
        });
        return out;
    };
    E.release = function () { /* no hold any more */ };
    // kept names used by afo_console.js
    window._afoRequestRender = function () { /* every frame draws anyway */ };
})();
