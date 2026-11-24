/* Dock one-shot buttons: Zero, Calibrate IMU, Calibrate FSR, Reset SV (Andy 15:06).
 * - Labels never change (no busy verb, no countdown); state is colour only:
 *   greyed = locked (aria-disabled); never lit.
 * - All four are momentary (Andy 15:22 / 16:15): dark only while held (CSS :active). Zero /
 *   Calibrate FSR / Reset SV = one ~200 ms 5431 pulse, Calibrate IMU = the 5434 counter + 1.
 *   No latched state, no completion feedback.
 * - The `disabled` property is ALWAYS false here: only the dock freeze / view-only paths
 *   (renderDock) set it, and they return before this runs. That was the 15:05 bug: a press
 *   set disabled = true and the render only reset aria-disabled, so Zero stayed grey.
 * Pure ES3 (also runs in the JScript unit harness test/js/dock_actions_harness.js). */
(function (root) {
    var PRESS_MS = 250;
    var LABELS = {zero: 'Encoder', imu: 'IMU', cal: 'FSR', reset: 'SV'};   // Calibration section (Andy Nov 24 16:16)
    var KEYS = ['zero', 'imu', 'cal', 'reset'];

    function cls(el, c, on) {
        if (!el.classList) { return; }
        if (on) { el.classList.add(c); } else { el.classList.remove(c); }
    }

    function view(st) {
        var cmd = st.commands || {}, lat = cmd.latched || {}, T = cmd.toggles || {}, ic = st.imu_cal || {};
        var assist = (T.assist || {}).value;
        var zLit = false, cLit = false;              // momentary: never lit (lat kept for old servers)
        if (lat) { /* ignored */ }
        var zLock = !zLit && assist !== 0;      // Zero ON needs Assist off; OFF always works
        return {
            zero: {lit: zLit, locked: zLock,
                   title: zLock ? 'Zero: switch Assist off first (hold the ankle still in neutral)' :
                       'Zero: sets the current ankle angle and motor encoder position as zero (hold the ankle still in neutral, Assist off)'},
            imu: {hidden: !ic.visible, lit: false, locked: !ic.enabled,
                  title: ic.enabled ? 'Resets the IMU front end; the wearer holds still for 5 s' : (ic.reason || '')},
            cal: {lit: cLit, locked: false,
                  title: '30 s FSR (insole pressure) calibration: walk normally until it finishes'},
            reset: {lit: false, locked: false, title: 'Clears the stride-velocity buffers'}
        };
    }

    function render(btns, st, now) {
        var v = view(st);
        for (var i = 0; i < KEYS.length; i++) {
            var k = KEYS[i], b = btns[k], s = v[k];
            if (!b) { continue; }
            if (k === 'imu') { b.hidden = !!s.hidden; }
            b.disabled = false;
            b.setAttribute('aria-disabled', s.locked ? 'true' : 'false');
            cls(b, 'busy', false);
            cls(b, 'lit', s.lit);
            cls(b, 'pressed', !!(b._pressedUntil && now < b._pressedUntil));
            if (b.title !== s.title) { b.title = s.title; }
            if (b.textContent !== LABELS[k]) { b.textContent = LABELS[k]; }
        }
        return v;
    }

    // click feedback only: never disables, never changes the label
    function press(btn, now) {
        btn._pressedUntil = now + PRESS_MS;
        cls(btn, 'pressed', true);
        if (typeof setTimeout !== 'undefined') {
            setTimeout(function () { if (Date.now() >= btn._pressedUntil) { cls(btn, 'pressed', false); } }, PRESS_MS + 20);
        }
    }

    root.AFODockActions = {view: view, render: render, press: press, PRESS_MS: PRESS_MS, LABELS: LABELS};
})(this);
