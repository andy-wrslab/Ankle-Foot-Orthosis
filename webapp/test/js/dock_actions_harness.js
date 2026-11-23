// JScript (Windows Script Host) harness for assets/afo_dock_actions.js: the real file runs
// with fake buttons, no browser. Run by test/test_dock_buttons.py:
//   cscript //nologo //E:jscript dock_actions_harness.js <afo_dock_actions.js>
// Prints one line per check: "ok name" / "FAIL name: detail".
var fso = new ActiveXObject("Scripting.FileSystemObject");
var SRC = WScript.Arguments(0);
var f = fso.OpenTextFile(SRC, 1, false, 0);     // ASCII read: the code itself is ASCII
var code = f.ReadAll();
f.Close();
var root = this;
eval(code);
var A = root.AFODockActions;

function Btn(label) {
    var self = this, cl = {};
    this.textContent = label; this.title = ""; this.hidden = false; this.disabled = false; this.attrs = {};
    this.classList = {
        add: function (c) { cl[c] = true; }, remove: function (c) { delete cl[c]; },
        contains: function (c) { return !!cl[c]; }
    };
    this.setAttribute = function (k, v) { self.attrs[k] = String(v); };
    this.getAttribute = function (k) { return self.attrs.hasOwnProperty(k) ? self.attrs[k] : null; };
}
function check(name, cond, got) { WScript.Echo((cond ? "ok   " : "FAIL ") + name + (cond ? "" : ": " + got)); }
function st(o) {
    return {commands: {latched: {zero: o.zero || 0, calibrate: o.cal || 0}, toggles: {assist: {value: o.assist}}},
            imu_cal: {visible: o.imuVis !== false, enabled: o.imuEn !== false, state: o.imu || "idle", text: o.imuText || ""}};
}
var b = {zero: new Btn("Zero"), imu: new Btn("Calibrate IMU"), cal: new Btn("Calibrate FSR"), reset: new Btn("Reset SV")};
var t = 100000;

// 1. the 15:05 bug: a press must never leave `disabled` set once the hold time is over
var keys = ["zero", "imu", "cal", "reset"];
for (var i = 0; i < keys.length; i++) {
    var k = keys[i], x = b[k];
    x.disabled = true;                    // what busyNow used to leave behind
    A.press(x, t);
    A.render(b, st({assist: 0}), t + 50);
    check(k + ": pressed style right after the press", x.classList.contains("pressed"), "no pressed class");
    A.render(b, st({assist: 0}), t + A.PRESS_MS + 10);
    check(k + ": disabled is false after a press + the hold time", x.disabled === false, x.disabled);
    check(k + ": pressed style gone after the hold time", !x.classList.contains("pressed"), "still pressed");
    check(k + ": label unchanged", x.textContent === A.LABELS[k], x.textContent);
}
// 2. Zero toggle: lit from commands.latched, ON locked with Assist on, OFF always allowed
A.render(b, st({assist: 0, zero: 1}), t);
check("zero: lit when latched on", b.zero.classList.contains("lit") && b.zero.getAttribute("aria-disabled") === "false", b.zero.attrs["aria-disabled"]);
A.render(b, st({assist: 1, zero: 1}), t);
check("zero: lit + Assist on -> still pressable (switch off)", b.zero.getAttribute("aria-disabled") === "false", b.zero.attrs["aria-disabled"]);
A.render(b, st({assist: 1, zero: 0}), t);
check("zero: off + Assist on -> greyed (aria-disabled), not disabled",
      b.zero.getAttribute("aria-disabled") === "true" && b.zero.disabled === false && !b.zero.classList.contains("lit"), b.zero.attrs["aria-disabled"]);
check("zero: label 'Zero' in every state", b.zero.textContent === "Zero", b.zero.textContent);
// 3. Calibrate FSR toggle: lit from the latched (echo-adopted) state, never locked
A.render(b, st({assist: 1, cal: 1}), t);
check("cal: lit when latched on, never locked", b.cal.classList.contains("lit") && b.cal.getAttribute("aria-disabled") === "false", b.cal.attrs["aria-disabled"]);
A.render(b, st({assist: 1, cal: 0}), t);
check("cal: unlit when off", !b.cal.classList.contains("lit"), "lit");
check("cal: label 'Calibrate FSR', no countdown", b.cal.textContent === "Calibrate FSR", b.cal.textContent);
// 4. Calibrate IMU: lit while running (bias_ready 0), label fixed, not greyed
A.render(b, st({assist: 0, imu: "busy", imuText: "Hold still 3 s…"}), t);
check("imu: lit while running, not greyed", b.imu.classList.contains("lit") && b.imu.getAttribute("aria-disabled") === "false" && b.imu.disabled === false,
      b.imu.attrs["aria-disabled"]);
check("imu: label 'Calibrate IMU' while running (no 'Hold still' / countdown)", b.imu.textContent === "Calibrate IMU", b.imu.textContent);
A.render(b, st({assist: 0, imu: "done", imuText: "IMU ready"}), t);
check("imu: unlit once IMU ready, label unchanged", !b.imu.classList.contains("lit") && b.imu.textContent === "Calibrate IMU", b.imu.textContent);
A.render(b, st({assist: 1, imuEn: false}), t);
check("imu: greyed when not enabled", b.imu.getAttribute("aria-disabled") === "true" && b.imu.disabled === false, b.imu.attrs["aria-disabled"]);
A.render(b, st({assist: 0, imuVis: false}), t);
check("imu: hidden when not visible", b.imu.hidden === true, b.imu.hidden);
// 5. Reset SV: never lit, never locked, label fixed
A.render(b, st({assist: 1}), t);
check("reset: never lit or locked, label 'Reset SV'", !b.reset.classList.contains("lit") && b.reset.getAttribute("aria-disabled") === "false"
      && b.reset.textContent === "Reset SV", b.reset.textContent);
// 6. a stale busy label from an old page version is put back
b.cal.textContent = "Calibrating… 30 s"; b.cal.classList.add("busy");
A.render(b, st({assist: 0}), t);
check("cal: stale busy text and busy class cleared", b.cal.textContent === "Calibrate FSR" && !b.cal.classList.contains("busy"), b.cal.textContent);
WScript.Echo("done");
