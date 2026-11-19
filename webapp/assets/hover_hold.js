// Hover hold (design v18): while the pointer is on a plot, that plot is not
// redrawn so the unified hover label (time + every trace) stays readable; its
// card gets class "holding" (a small "Held" tag in the head). Data keeps
// buffering and the plot catches up when the pointer leaves. Tablet: a tap
// shows the label and holds; a tap outside releases. Safety: 20 s without
// pointer movement releases too. Each graph <id> has a dcc.Store "hold-<id>".
(function () {
    var HELD = ['torque', 'gait', 'press', 'imu', 'tr-assist', 'tr-uc',
                'sig-g0', 'sig-g1', 'sig-g2', 'sig-g3', 'sig-g4', 'sig-g5'];
    var MAX_HOLD_MS = 20000;
    window._afoHold = window._afoHold || {};
    var timers = {};

    function setHold(id, on) {
        var el = document.getElementById(id);
        var card = el && el.closest('.plot-card');
        if (card) { card.classList.toggle('holding', on); }
        if (on) { arm(id); } else if (timers[id]) { clearTimeout(timers[id]); timers[id] = null; }
        if (!!window._afoHold[id] === on) { return; }
        window._afoHold[id] = on;
        try {
            if (window.dash_clientside && window.dash_clientside.set_props) {
                window.dash_clientside.set_props('hold-' + id, {data: on});
            }
        } catch (e) { /* store not in this layout */ }
    }

    function arm(id) {
        if (timers[id]) { clearTimeout(timers[id]); }
        timers[id] = setTimeout(function () { setHold(id, false); }, MAX_HOLD_MS);
    }

    function wire() {
        HELD.forEach(function (id) {
            var el = document.getElementById(id);
            if (!el || el._afoHoldWired) { return; }
            el._afoHoldWired = true;
            el.addEventListener('mouseenter', function () { setHold(id, true); });
            el.addEventListener('mousemove', function () { if (window._afoHold[id]) { arm(id); } });
            el.addEventListener('mouseleave', function () { setHold(id, false); });
            el.addEventListener('touchstart', function () { setHold(id, true); }, {passive: true});
        });
    }

    document.addEventListener('touchstart', function (ev) {
        HELD.forEach(function (id) {
            var el = document.getElementById(id);
            if (window._afoHold[id] && el && !el.contains(ev.target)) { setHold(id, false); }
        });
    }, {passive: true});

    window._afoReleaseAllHolds = function () { HELD.forEach(function (id) { if (window._afoHold[id]) { setHold(id, false); } }); };
    setInterval(wire, 1000);
})();
