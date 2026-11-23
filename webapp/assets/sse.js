// Live snapshot stream: ONE EventSource per tab, opened once and kept open.
// Each message goes into the dcc.Store "es" (data = the raw JSON text), which
// drives the Live plot clientside callback. Replaces the dash_extensions
// EventSource, which re-created its connection on every render (one /events
// request per message, ~21 per second per tab, and 503s past MAX_CLIENTS).
// The browser's own retry handles dropped connections; a refused one (e.g. 503,
// readyState CLOSED) is reopened here with backoff 1 s, 2 s, 4 s ... 15 s.
// Closed on page unload so the server frees the slot at once.
(function () {
    var URL = '/events', MAX_BACKOFF_MS = 15000;
    var es = null, backoff = 1000, timer = null, pending = null, stopped = false;
    window._afoSse = {opens: 0, messages: 0, errors: 0, dropped_unmounted: 0};

    function push(data) {
        // (a dcc.Store has no DOM node, so readiness = Dash's set_props existing)
        var dc = window.dash_clientside;
        if (!dc || !dc.set_props) {
            pending = data;                    // Dash not ready yet: keep only the newest
            window._afoSse.dropped_unmounted += 1;
            return;
        }
        try { dc.set_props('es', {data: data}); } catch (e) { pending = data; }
    }

    function flushPending() {
        if (pending !== null && window.dash_clientside && window.dash_clientside.set_props) {
            var d = pending; pending = null; push(d);
        }
    }

    function schedule() {
        if (stopped || timer) { return; }
        timer = setTimeout(function () { timer = null; open(); }, backoff);
        backoff = Math.min(MAX_BACKOFF_MS, backoff * 2);
    }

    function open() {
        if (stopped || (es && es.readyState !== 2)) { return; }   // 2 = CLOSED
        try { es = new EventSource(URL); } catch (e) { schedule(); return; }
        window._afoSse.opens += 1;
        es.onopen = function () { backoff = 1000; };
        es.onmessage = function (ev) { window._afoSse.messages += 1; push(ev.data); };
        es.onerror = function () {
            window._afoSse.errors += 1;
            if (es && es.readyState === 2) { es = null; schedule(); }   // refused: reopen with backoff
        };
    }

    function close() {
        stopped = true;
        if (timer) { clearTimeout(timer); timer = null; }
        if (es) { try { es.close(); } catch (e) { /* ignore */ } es = null; }
    }

    window.addEventListener('pagehide', close);
    window.addEventListener('beforeunload', close);
    window.addEventListener('pageshow', function (ev) { if (ev.persisted) { stopped = false; open(); } });
    setInterval(flushPending, 250);
    open();
})();
