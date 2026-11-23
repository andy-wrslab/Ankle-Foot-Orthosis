// JScript (Windows Script Host) harness for assets/live_uplot.js: runs the real engine with
// stubbed window / document / uPlot / requestAnimationFrame, no browser. Run by
// test/test_live_uplot_unit.py:  cscript //nologo //E:jscript live_uplot_harness.js <live_uplot.js> <case>
// Prints one JSON-ish result line per check: "ok name" / "FAIL name: detail".
var fso = new ActiveXObject("Scripting.FileSystemObject");
var SRC = WScript.Arguments(0), CASE = WScript.Arguments.length > 1 ? WScript.Arguments(1) : "stall";

// ---- ES5 polyfills (JScript is ES3)
if (!Array.prototype.forEach) { Array.prototype.forEach = function (f, t) { for (var i = 0; i < this.length; i++) { if (i in this) { f.call(t, this[i], i, this); } } }; }
if (!Array.prototype.map) { Array.prototype.map = function (f, t) { var o = []; for (var i = 0; i < this.length; i++) { o.push(f.call(t, this[i], i, this)); } return o; }; }
if (!Array.prototype.filter) { Array.prototype.filter = function (f, t) { var o = []; for (var i = 0; i < this.length; i++) { if (f.call(t, this[i], i, this)) { o.push(this[i]); } } return o; }; }
if (!Array.prototype.fill) { Array.prototype.fill = function (v) { for (var i = 0; i < this.length; i++) { this[i] = v; } return this; }; }
if (!Array.isArray) { Array.isArray = function (a) { return Object.prototype.toString.call(a) === "[object Array]"; }; }
if (!Object.keys) { Object.keys = function (o) { var k = []; for (var p in o) { if (Object.prototype.hasOwnProperty.call(o, p)) { k.push(p); } } return k; }; }
var JSON = {parse: function (s) { return eval("(" + s + ")"); }};
function isFinite2(v) { return typeof v === "number" && v === v && v !== Infinity && v !== -Infinity; }

// ---- stubs
var now = 1000, rafQ = [];
var console = {errors: [], error: function () { var a = []; for (var i = 0; i < arguments.length; i++) { a.push(String(arguments[i])); } console.errors.push(a.join(" ")); }, log: function () {}};
var performance = {now: function () { return now; }};
var calls = {};     // id -> [{op, min, max, n}]
function FakeUPlot(opts, data, host) {
    this.series = [{}]; for (var i = 1; i < opts.series.length; i++) { this.series.push({show: true}); }
    this.id = host.id; calls[this.id] = [];
}
FakeUPlot.prototype.batch = function (f) { f(); };
FakeUPlot.prototype.setData = function (d) { calls[this.id].push({op: "data", n: d[0].length, last: d[0][d[0].length - 1]}); };
FakeUPlot.prototype.setScale = function (k, r) { calls[this.id].push({op: "x", min: r.min, max: r.max}); };
FakeUPlot.prototype.setSeries = function (i, o) { this.series[i].show = o.show; };
FakeUPlot.prototype.setSize = function () {};
function Host(id) {
    this.id = id; this.offsetParent = {}; this.clientWidth = 800; this.clientHeight = 300;
    this.addEventListener = function () {}; this.closest = function () { return null; };
}
var spec = {window_default: 10, style: {text: "#777", grid: "#eee", zero: "#ccc"}, plots: {
    torque: {group: "gait", y: [-6.6, 16.6], series: [{label: "Measured", src: ["torque", null], color: "#000", width: 1.5, dec: 2, unit: "N·m"},
                                                     {label: "Command", src: ["demand_torque", null], color: "#1F6F78", width: 1.5, dash: [5, 4], dec: 2, unit: "N·m"}]},
    gait: {group: "gait", y: [-0.16, 2.16], series: [{label: "Current", src: ["gait", null], color: "#000", width: 1.5, dec: 2, unit: "m/s"},
                                                    {label: "Target", src: ["sv_target", null], color: "#1F6F78", width: 1.5, dec: 2, unit: "m/s"}]},
    press: {group: "sensors", y: [-80, 1080], series: [{label: "Hallux (FSR1)", src: ["press", 0], color: "#000", width: 1.25, dec: 0, unit: "counts"}]},
    imu: {group: "sensors", y: [-3.48, 3.48], series: [{label: "x", src: ["imu", 0], color: "#000", width: 1.25, dec: 2, unit: "g"}]}}};
var specEl = {getAttribute: function () { return "__SPEC__"; }};
var hosts = {torque: new Host("torque"), gait: new Host("gait"), press: new Host("press"), imu: new Host("imu")};
var document = {hidden: false,
    getElementById: function (id) { return id === "liveSpec" ? specEl : (hosts[id] || null); },
    querySelectorAll: function () { return []; }, createElement: function () { return {}; }};
var window = {uPlot: FakeUPlot, _afoPage: "live", _afoLiveSub: "gait",
    requestAnimationFrame: function (f) { rafQ.push(f); return rafQ.length; }};
window.window = window;
var rawSpec = null;
specEl.getAttribute = function () { return rawSpec; };
function stringify(v) {      // tiny JSON writer for the spec / messages
    if (v === null || v === undefined) { return "null"; }
    if (typeof v === "number") { return isFinite2(v) ? String(v) : "null"; }
    if (typeof v === "string") { return '"' + v.replace(/\\/g, "\\\\").replace(/"/g, '\\"') + '"'; }
    if (typeof v === "boolean") { return v ? "true" : "false"; }
    if (Array.isArray(v)) { var a = []; for (var i = 0; i < v.length; i++) { a.push(stringify(v[i])); } return "[" + a.join(",") + "]"; }
    var o = []; for (var k in v) { if (Object.prototype.hasOwnProperty.call(v, k)) { o.push(stringify(k) + ":" + stringify(v[k])); } } return "{" + o.join(",") + "}";
}
rawSpec = stringify(spec);

// ---- load the real engine
var f = fso.OpenTextFile(SRC, 1); var code = f.ReadAll(); f.Close();
code = code.replace(/\.catch\(/g, "['catch'](").replace(/'use strict';/, "");
eval(code);
var E = window._afoPlots;

// ---- feed: 100 Hz samples in 50 ms messages (20 / s), like the server
var t0 = CASE === "early" ? 1.0 : 20.0, n = 0;
function message(kind, k0, k1, torqueOf) {
    var m = {kind: kind, t: [], torque: [], demand_torque: [], gait: [], sv_target: [], press: [[]], imu: [[]], meta: {session: 1}};
    for (var k = k0; k < k1; k++) {
        var t = Math.round((t0 + k * 0.01) * 1000) / 1000;
        m.t.push(t); m.torque.push(torqueOf(k)); m.demand_torque.push(torqueOf(k));
        m.gait.push(1.0 + 0.2 * Math.sin(k / 50)); m.sv_target.push(1.2);
        m.press[0].push(100); m.imu[0].push(0);
    }
    m.t_latest = m.t[m.t.length - 1]; m.latest = {torque: 0, press: [100], imu: [0]};
    return stringify(m);
}
function runFrames(count) { for (var i = 0; i < count; i++) { now += 16.7; var q = rafQ; rafQ = []; for (var j = 0; j < q.length; j++) { q[j](now); } } }
function lastX(id) { var c = calls[id] || []; for (var i = c.length - 1; i >= 0; i--) { if (c[i].op === "x") { return c[i]; } } return null; }
function countX(id) { var c = calls[id] || [], m = 0; for (var i = 0; i < c.length; i++) { if (c[i].op === "x") { m++; } } return m; }
var results = [];
function check(name, cond, detail) { results.push((cond ? "ok   " : "FAIL ") + name + (cond ? "" : ": " + detail)); }

if (CASE === "early") {
    window._afoLiveMsg(message("full", 0, 100, function () { return 0; }));     // t 1.0 .. 1.99
    n = 100; var neg = 0, okShape = true;
    for (var e = 0; e < 20 * 12; e++) {                                         // 12 s
        window._afoLiveMsg(message("delta", n, n + 5, function () { return 0; })); n += 5; runFrames(3);
        var g1 = lastX("torque"), g2 = lastX("gait");
        if (!g1 || !g2) { continue; }
        if (g1.min < 0 || g2.min < 0) { neg++; }
        var tt = E.clock;
        if (Math.abs(g1.min - Math.max(0, tt - 10)) > 1e-9 || Math.abs(g1.max - Math.max(10, tt)) > 1e-9) { okShape = false; }
    }
    check("early: Gait x range never negative (t from 1 s)", neg === 0, neg + " negative frames");
    check("early: range = [max(0, t - w), max(w, t)]", okShape, stringify(lastX("torque")));
    for (var r0 = 0; r0 < results.length; r0++) { WScript.Echo(results[r0]); }
    WScript.Quit(0);
}
var torqueOf = CASE === "real" ? function (k) { return 5 * Math.sin(k / 30); } : function (k) { return 0.0; };   // STO: exactly 0.0
window._afoLiveMsg(message("full", 0, 1000, torqueOf));
n = 1000;
var maxLag = 0, frames = 0, sameEvery = true, advanced = 0, prevT = null, prevG = null, maxStep = 0;
for (var s = 0; s < 20 * 180; s++) {           // 3 minutes of 20 Hz messages
    window._afoLiveMsg(message("delta", n, n + 5, torqueOf)); n += 5;
    var before = countX("torque");
    runFrames(3);                              // ~50 ms of frames per message
    frames += 3;
    var a = lastX("torque"), b = lastX("gait");
    if (!a || !b) { continue; }
    if (a.min !== b.min || a.max !== b.max) { sameEvery = false; }
    var lag = Math.abs(a.max - b.max); if (lag > maxLag) { maxLag = lag; }
    if (prevT !== null && a.max > prevT) { advanced++; }
    if (prevT !== null) { maxStep = Math.max(maxStep, a.max - prevT); }
    prevT = a.max; prevG = b.max;
}
var tl = t0 + (n - 1) * 0.01;
check(CASE + ": torque x range set on every frame", countX("torque") >= frames, countX("torque") + " of " + frames);
check(CASE + ": gait x range set on every frame", countX("gait") >= frames, countX("gait") + " of " + frames);
check(CASE + ": torque and SV ranges identical every frame", sameEvery, "max lag " + maxLag);
check(CASE + ": torque range kept advancing (no stall > 0.5 s)", advanced >= 20 * 180 - 2 && maxLag <= 0.5, advanced + " advances, lag " + maxLag);
check(CASE + ": torque range ends near the newest sample (< 0.3 s)", Math.abs(lastX("torque").max - tl) < 0.3, lastX("torque").max + " vs " + tl);
check(CASE + ": scrolling is smooth (no jump > 0.2 s per message)", maxStep < 0.2, "max step " + maxStep);
check(CASE + ": 10 s window", Math.abs(lastX("torque").max - lastX("torque").min - 10) < 1e-6, lastX("torque").min + ".." + lastX("torque").max);
check(CASE + ": no console errors", console.errors.length === 0, console.errors.slice(0, 3).join(" | "));
// sub-tab not shown: nothing drawn for its plots
check(CASE + ": Sensors plots not drawn while Gait is shown", !calls.press && !calls.imu, "press drawn");
// hidden browser tab: no drawing
var cBefore = countX("torque"); document.hidden = true; runFrames(10); document.hidden = false;
check(CASE + ": hidden browser tab draws nothing", countX("torque") === cBefore, (countX("torque") - cBefore) + " draws");
// stream stops: the clock never runs past the newest sample
runFrames(120);
check(CASE + ": stream stopped: range stops at the newest sample", lastX("torque").max <= tl + 1e-9, lastX("torque").max + " > " + tl);
// Sensors sub-tab: both plots get the same range each frame
window._afoLiveSub = "sensors";
window._afoLiveMsg(message("delta", n, n + 5, torqueOf)); n += 5; runFrames(5);
var p = lastX("press"), q = lastX("imu");
check(CASE + ": Sensors plots drawn with the same range", p && q && p.min === q.min && p.max === q.max, stringify(p) + " " + stringify(q));
for (var r = 0; r < results.length; r++) { WScript.Echo(results[r]); }
