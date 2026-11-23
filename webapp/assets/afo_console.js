// AFO console (design v18). Builds the top bar, popovers, side banner, dock and
// the Trials page from the approved mock markup, and drives them from
// /api/console/state (polled twice a second). Nothing here sends a command or
// a setting by itself: every POST below is behind an operator click or a
// committed field (Enter / leaving the field). Plots are Dash graphs.
(function () {
    'use strict';
    var S = {state: null, page: null, liveSub: 'gait', runs: null, selRun: null,
             sigNames: [], lastPacketAt: 0, editing: {}, exportJob: null, lastSid: null};
    var POLL_MS = 500;
    var $ = function (id) { return document.getElementById(id); };
    function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
        return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]; }); }
    function post(url, body) {
        return fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json'},
                           body: JSON.stringify(body || {})})
            .then(function (r) { return r.json().catch(function () { return {}; })
                .then(function (j) { j._status = r.status; return j; }); })
            .catch(function (e) { return {ok: false, msg: String(e), _status: 0}; });
    }
    function getJSON(url) { return fetch(url).then(function (r) { return r.json(); }); }
    function setProps(id, props) {
        try { window.dash_clientside.set_props(id, props); } catch (e) { /* not mounted yet */ }
    }
    function local() { var a = $('app'); return a && a.getAttribute('data-local') === '1'; }

    // ---------------------------------------------------------- two-step confirm
    // every action button shows its busy state in the click handler itself (< 100 ms),
    // before the server call; a state poll does not undo it until the server reports
    function busyNow(btn, text, ms) {
        if (!btn) { return; }
        btn.classList.add('busy'); btn.disabled = true; btn.textContent = text;
        btn._busyUntil = Date.now() + (ms || 3000);
    }
    function busyHeld(btn) { return !!(btn && btn._busyUntil && Date.now() < btn._busyUntil); }
    function mmss(sec) { sec = Math.max(0, Math.floor(sec)); return Math.floor(sec / 60) + ':' + ('0' + (sec % 60)).slice(-2); }
    function confirmable(btn, label, confirmText, action) {
        var tm = null;
        btn.addEventListener('click', function () {
            if (btn.disabled || btn.getAttribute('aria-disabled') === 'true') { return; }
            if (!btn.classList.contains('confirming')) {
                btn.classList.add('confirming');
                btn.textContent = typeof confirmText === 'function' ? confirmText() : confirmText;
                tm = setTimeout(function () { btn.classList.remove('confirming'); btn.textContent = label(); }, 3000);
                return;
            }
            clearTimeout(tm);
            btn.classList.remove('confirming');
            btn.textContent = label();
            action();
        });
    }
    function flash(el, ok, tip) {
        if (!el) { return; }
        el.classList.remove('sent-flash', 'send-error');
        if (ok) {
            el.classList.add('sent-flash'); el.title = '';
            setTimeout(function () { el.classList.remove('sent-flash'); }, 700);
        } else {
            el.classList.add('send-error'); el.title = tip || 'Not sent';
        }
    }

    // ---------------------------------------------------------- markup (from the mock)
    var ADV = [
        ['Walking-speed target', 'RL mode only', [
            ['sv_target_min', 'Min target speed', 'm/s', 'Healthy participants 0.8, patients 0.5 m/s'],
            ['sv_target_max', 'Max target speed', 'm/s'],
            ['target_step_up', 'Target step up', 'm/s'],
            ['target_step_down', 'Target step down', 'm/s']], true],
        ['When the target steps', 'RL mode only', [
            ['window_up', 'Step-up window', 'strides', 'Target goes up when at least 90 % of the last N strides had Uc = 1'],
            ['window_down', 'Step-down window', 'strides', 'Target can go down when at least 90 % of the last N strides had Uc not 1'],
            ['assist_threshold', 'High-assist level', 'of 10', 'A step down needs RL assistance above this level ...'],
            ['min_cycles', 'High-assist strides', 'strides', '... for this many strides in a row']]],
        ['Torque controller', '', [
            ['p_gain', 'Torque P gain', ''], ['i_gain', 'Torque I gain', '']]],
        ['Safety', '', [
            ['threshold_pressure', 'Standing-still cutoff', 'counts', 'Torque is cut to 0 when the insole pressure sum varies by less than this over the last 0.7 s (standing still)']]]
    ];

    function chromeHTML() {
        var adv = ADV.map(function (sec) {
            var rows = sec[2].map(function (f) {
                return '<label' + (f[3] ? ' title="' + esc(f[3]) + '"' : '') + '>' + esc(f[1]) + '<span><input class="input mono adv-in" data-k="' +
                    f[0] + '"' + (f[4] ? ' readonly' : '') + '>' + (f[2] ? ' ' + esc(f[2]) : '') + '</span></label>';
            }).join('');
            if (sec[3]) {
                rows += '<div class="adv-nc" id="advNc" title="UDP 5430 parameters: no block in this model reads them. Wiring them waits for a later round.">' +
                    '<div class="nc-head">Not connected in this model · UDP 5430</div>' +
                    ['epsilon up', 'epsilon down', 'step up', 'step down', 'v min'].map(function (n) {
                        return '<label>' + n + '<span><input class="input mono" value="–" disabled></span></label>'; }).join('') + '</div>';
            }

            return '<fieldset class="adv-sec"><legend' + (sec[1] ? ' title="' + esc(sec[1]) + '"' : '') + '>' + esc(sec[0]) +
                '</legend>' + rows + '</fieldset>';
        }).join('');
        return '' +
        '<header class="topbar" id="topbar">' +
          '<span class="appname">AFO</span>' +
          '<nav class="nav" id="nav"><a href="/live" data-nav="live">Live</a><a href="/trials" data-nav="trials">Trials</a>' +
          '<a href="/daq" data-nav="daq">DAQ</a></nav>' +
          '<span class="spacer"></span>' +
          '<div class="session-bar" id="sessionBar">' +
            '<label class="tb-field" title="Participant ID (used in export file names)"><span>ID</span><input class="input" id="sPart" autocomplete="off"></label>' +
            '<label class="tb-field" title="Body mass (kg). AFO_r1: also sets the Bi-LSTM mass (BIF_mass_kg). More than 20 kg."><span>Mass</span><input class="input mono" id="sMass" autocomplete="off" aria-label="Body mass (kg)"><span>kg</span>' +
              '<span class="tb-state" id="sMassState" hidden></span></label>' +

            '<button class="side-chip" id="sideChip" aria-haspopup="dialog" aria-expanded="false" title="Foot side on the target">–</button>' +
            '<span class="vr sb-sep" aria-hidden="true"></span>' +
            '<button class="btn sm" id="advBtn" aria-haspopup="dialog" aria-expanded="false">Advanced</button>' +
          '</div>' +
          '<span class="vr"></span>' +
          '<div class="meta">' +
            '<button class="status-btn" id="statusBtn" aria-haspopup="dialog" aria-expanded="false" title="Connection, data streams and the settings the target reports back"><span class="sb-mark" aria-hidden="true"></span><span class="sb-txt" id="statusTxt">…</span></button>' +
          '</div>' +
        '</header>' +
        '<div class="popover" id="statusPop" role="dialog" aria-label="Rig status" hidden>' +
          '<div class="pop-head"><span class="card-title">Settings on the target</span><span class="spacer"></span><span class="hint" id="echoTime"></span></div>' +
          '<table class="echo-table" id="echoTable"><thead><tr><th>Setting</th><th class="r">Entered</th><th class="r">Target uses</th></tr></thead><tbody></tbody></table>' +
          '<div class="pop-head sub"><span class="card-title">Open items</span></div>' +
          '<ul class="open-items" id="openItems"></ul>' +
          '<div class="pop-head sub" id="afterStartHead" hidden><span class="card-title">After Start</span><span class="spacer"></span><span class="hint" id="bifLine"></span></div>' +
          '<ul class="pop-checklist" id="afterStart" hidden></ul>' +
          '<div class="pop-head sub"><span class="card-title">Rig status</span><span class="spacer"></span><span class="hint" id="rigTime"></span></div>' +
          '<dl class="kv" id="rigKv"></dl>' +
        '</div>' +
        '<div class="popover adv-pop top" id="advPop" role="dialog" aria-label="Advanced parameters" hidden>' +
          '<div class="pop-head" title="Rarely changed · sent on Enter"><span class="card-title">Advanced</span></div>' +
          '<div class="adv-groups">' + adv + '</div>' +
        '</div>' +
        '<div class="popover side-pop" id="sidePop" role="dialog" aria-label="Foot side" hidden>' +
          '<div class="pop-head"><span class="card-title">Foot side</span></div>' +
          '<div class="side-pick" id="sidePick"><button class="side-opt" data-side="LEFT" aria-pressed="false">Left</button>' +
          '<button class="side-opt" data-side="RIGHT" aria-pressed="false">Right</button></div>' +
          '<div class="side-confirm" id="sideConfirm" hidden><p><b id="scTitle"></b><br><span class="hint">This reverses the actuation direction. Only switch when the AFO is on that leg.</span></p>' +
          '<div class="side-act"><button class="btn" id="scCancel">Cancel</button><button class="btn primary" id="scOk"></button></div></div>' +
        '</div>' +
        '';
    }

    function dockHTML() {
        return '' +
        '<div class="controls">' +
          '<button class="btn btn-toggle btn-motor" id="bMotor" data-drive="unknown">Motor <span class="pill unknown">?</span></button>' +
          '<button class="btn btn-toggle" id="bAssist">Assist <span class="pill unknown">?</span></button>' +
          '<button class="btn btn-toggle" id="bK" title="Enables RL adaptation updates on heel strike (model K signal)">K <span class="pill unknown">?</span></button>' +
          '<div class="mode" id="modeBox" title="The model latches a new mode at the next heel strike">' +
            '<span class="lbl">Mode</span>' +
            '<div class="seg" id="modeSel" role="group" aria-label="Assistance mode"><button data-m="1" aria-pressed="false">RL</button><button data-m="3" aria-pressed="false">Fixed K</button></div>' +
            '<span class="k-field off" id="kField" title="Percent of the torque profile. Applies at the next heel strike."><input class="input mono" id="kPct" aria-label="Fixed K percentage"><span>%</span></span>' +
            '<button class="btn sm" id="kConfirm" hidden></button>' +
          '</div>' +
        '</div>' +
        '<span class="hint" id="dockMsg"></span>' +
        '<button class="btn sm" id="unknownOff" hidden>Set unknown to OFF</button>' +
        '<span class="spacer"></span>' +
        '<div class="actions">' +
          '<button class="btn act" id="bZero" title="Zero: sets the current ankle angle and motor encoder position as zero (hold the ankle still in neutral, Assist off)">Zero</button>' +
          '<button class="btn act momentary" id="bImuCal" hidden title="Resets the IMU front end; the wearer holds still for 5 s">Calibrate IMU</button>' +
          '<button class="btn act" id="bCal" title="30 s FSR (insole pressure) calibration: walk normally until it finishes">Calibrate FSR</button>' +
          '<button class="btn act momentary" id="bResetSV" title="Clears the stride-velocity buffers">Reset SV</button>' +
        '</div>';
    }

    function trialsHTML() {
        return '' +
        // Andy 14:48: Connect lives here (run 14: everything else is UDP); Andy 15:23: Start / Stop
        // too (off the top bar), same confirms, auto-connect and busy states
        '<div class="ml-link" id="mlLink"><span class="field-label">MATLAB link</span>' +
        '<span class="ml-state" id="mlState">Not connected</span>' +
        '<button class="btn sm" id="tConnect" title="Start, Stop, Export and Load connect by themselves">Connect</button>' +
        '<span class="vr" aria-hidden="true"></span>' +
        '<div class="target"><div class="btn-group">' +
          '<button class="btn sm" id="tStart">Start</button>' +
          '<button class="btn sm danger" id="tStop">Stop</button>' +
        '</div></div></div>' +
        '<div class="toolbar"><h1 class="page-title">Trials</h1></div>' +
        // Refresh in the runs card's own header, like "Fetch latest" on DAQ (Andy 15:23)
        '<section class="card flush">' +
          '<div class="card-head"><span class="card-title">Runs</span><span class="spacer"></span>' +
            '<span class="hint" id="runsHint"></span>' +
            '<button class="btn sm" id="runsRefresh">Refresh</button></div>' +
          '<div class="runs-limit" id="runsLimit" hidden></div>' +
          '<table class="table runs" id="runTable"><thead><tr><th>Run</th><th>Started</th><th class="r">Duration</th><th class="r">Size</th><th>Participant</th><th>Status</th></tr></thead><tbody></tbody></table>' +
          '<div class="export-bar">' +
            '<label class="field-label" for="expName">Export file name</label>' +
            '<input class="input mono" id="expName" autocomplete="off" title="Participant ID, date, start time and trial number; saved to afo_mat with a settings .json beside the .mat">' +
            '<span class="sent" id="expState"></span><span class="spacer"></span>' +
            '<button class="btn primary" id="expBtn">Export</button>' +
          '</div>' +
        '</section>';
    }

    // ---------------------------------------------------------- router
    var PAGES = ['live', 'trials', 'daq'];
    var LEGACY = {signals: 'live', teensy: 'daq'};       // removed / renamed pages (Andy 14:36)
    function go(page, push) {
        if (LEGACY[page]) { page = LEGACY[page]; push = true; }
        if (PAGES.indexOf(page) < 0) { page = 'live'; }
        S.page = page; window._afoPage = page;
        PAGES.forEach(function (p) { var el = $('page-' + p); if (el) { el.hidden = p !== page; } });
        resizeSoon($('page-' + page));
        var dock = $('dock'); if (dock) { dock.hidden = page !== 'live'; }
        document.querySelectorAll('#nav a').forEach(function (a) {
            if (a.getAttribute('data-nav') === page) { a.setAttribute('aria-current', 'page'); } else { a.removeAttribute('aria-current'); }
        });
        if (push !== false && location.pathname !== '/' + page) {
            history.pushState({}, '', '/' + page);
            window.dispatchEvent(new PopStateEvent('popstate'));
        }
        if (window._afoReleaseAllHolds) { window._afoReleaseAllHolds(); }
        if (window._afoPlots && window._afoPlots.release) { window._afoPlots.release(); }
        setTimeout(function () { window.dispatchEvent(new Event('resize')); }, 60);
        if (page === 'trials') { loadRuns(); }
        if (S.state) { renderSide(S.state); }
    }
    window.addEventListener('popstate', function () {
        var p = (location.pathname || '/').replace(/^\/+|\/+$/g, '') || 'live';
        if (p !== S.page) { go(p, false); }
    });

    // ---------------------------------------------------------- Live toolbar
    // Plotly graphs (Signals, Trials) drawn while hidden get a default width; size them to
    // their card in the same frame they become visible (no half-width flash), and once more
    // next frame. The live plots (uPlot) size themselves (ResizeObserver, live_uplot.js).
    function resizePlots(root) {
        if (!root || !window.Plotly || !window.Plotly.Plots) { return; }
        var gds = root.querySelectorAll('.js-plotly-plot');
        for (var i = 0; i < gds.length; i++) {
            if (gds[i].offsetParent === null) { continue; }
            // relayout(autosize) sizes from the card at once; Plots.resize waits ~100 ms
            try { if (gds[i]._fullLayout) { window.Plotly.relayout(gds[i], {autosize: true}); } } catch (e) { /* not drawn yet */ }
        }
    }
    function resizeSoon(root) {
        resizePlots(root);
        if (window.requestAnimationFrame) { window.requestAnimationFrame(function () { resizePlots(root); }); }
    }
    window._afoResizePlots = resizeSoon;
    // legend chips (Sensors): a click hides / shows that trace; drawn on the next frame
    document.addEventListener('click', function (e) {
        var b = e.target && e.target.closest ? e.target.closest('.lg[data-g]') : null;
        if (!b) { return; }
        var g = b.getAttribute('data-g'), k = b.getAttribute('data-k');
        var H = window._afoHidden = window._afoHidden || {};
        H[g] = H[g] || {};
        H[g][k] = !H[g][k];
        b.setAttribute('aria-pressed', H[g][k] ? 'false' : 'true');
        b.classList.toggle('off', !!H[g][k]);
        var V = window._afoVisDirty = window._afoVisDirty || {};
        V[g] = true;
        if (window._afoRequestRender) { window._afoRequestRender(); }
    });
    function setLiveSub(sub) {
        S.liveSub = sub; window._afoLiveSub = sub;
        [['pgGait', 'gait'], ['pgSensors', 'sensors'], ['pgTraining', 'training']].forEach(function (x) {
            var b = $(x[0]); if (b) { b.setAttribute('aria-pressed', x[1] === sub ? 'true' : 'false'); }
        });
        document.querySelectorAll('#page-live [data-live]').forEach(function (c) { c.hidden = c.getAttribute('data-live') !== sub; });
        resizeSoon($('page-live'));
        if (window._afoRequestRender) { window._afoRequestRender(); }
        // one 2 s / 10 s window for Gait, Sensors and Training (Andy 14:34 / 14:58): the selector shows
        // the current window on every switch; the plots use it on their first frame
        if ($('liveWin')) { $('liveWin').hidden = false; showWin(); }
        if ($('trWin')) { $('trWin').hidden = true; }
        setProps('live-sub', {data: sub});
        if (window._afoReleaseAllHolds) { window._afoReleaseAllHolds(); }
        if (window._afoPlots && window._afoPlots.release) { window._afoPlots.release(); }
        setTimeout(function () { window.dispatchEvent(new Event('resize')); }, 30);
    }
    function showWin() {
        var w = window._afoWinSec === 2 ? 2 : 10, b = $(w === 2 ? 'w2' : 'w10');
        if (b && $('liveWin')) { segPress($('liveWin'), b); }
    }
    function segPress(group, btn) {
        group.querySelectorAll('button').forEach(function (b) { b.setAttribute('aria-pressed', b === btn ? 'true' : 'false'); });
    }
    document.addEventListener('click', function (e) {
        var t = e.target.closest ? e.target.closest('button, a') : null;
        if (!t) { return; }
        if (t.matches('#nav a')) { e.preventDefault(); go(t.getAttribute('data-nav')); return; }
        if (t.id === 'pgGait') { setLiveSub('gait'); }
        else if (t.id === 'pgSensors') { setLiveSub('sensors'); }
        else if (t.id === 'pgTraining') { setLiveSub('training'); }
        else if (t.id === 'w2' || t.id === 'w10') { segPress($('liveWin'), t); window._afoWinSec = t.id === 'w2' ? 2 : 10;
            setProps('window-sec', {data: window._afoWinSec});
            try { window.localStorage.setItem('afo.win', String(window._afoWinSec)); } catch (e) { /* no storage */ } }
        else if (t.parentElement && t.parentElement.id === 'trWin') { segPress($('trWin'), t); window._afoTrWin = Number(t.getAttribute('data-w'));
            setProps('tr-window', {data: window._afoTrWin}); }
    });

    // ---------------------------------------------------------- snapshot hook (SSE)
    function driveOf(sw) {
        // CiA-402 state from the statusword mask; bit 10 (target reached) and the other
        // manufacturer bits are ignored (0x0660 is "switch-on disabled", like 0x0260)
        if (typeof sw !== 'number' || !isFinite(sw)) { return null; }
        sw = sw >>> 0;
        if (sw & 0x0008) { return 'fault'; }
        var s = sw & 0x006F;
        if (s === 0x0027) { return 'on'; }                      // operation enabled
        if (s === 0x0021 || s === 0x0023) { return 'ready'; }   // ready to switch on / switched on
        if ((sw & 0x004F) === 0x0040) { return 'disabled'; }    // switch-on disabled
        return 'other';
    }
    window._afoOnSnapshot = function (p) {
        S.lastPacketAt = Date.now();
        var mt = $('mtime');
        if (mt && typeof p.t_latest === 'number') { var txt = p.t_latest.toFixed(3) + ' s'; if (mt.textContent !== txt) { mt.textContent = txt; } }
        var m = $('bMotor');
        if (m && typeof p.statusword === 'number') {
            var d = driveOf(p.statusword), hex = '0x' + ('0000' + (p.statusword >>> 0).toString(16).toUpperCase()).slice(-4);
            if (d && d !== 'other') { m.setAttribute('data-drive', d); }
            m.setAttribute('data-sw', hex);
            S.drive = d === 'other' ? (S.drive || 'unknown') : d;
        }
    };
    setInterval(function () {      // stale rule: no 5431 packet for > 0.5 s
        var stale = !S.lastPacketAt || Date.now() - S.lastPacketAt > 500;
        document.querySelectorAll('#page-live .plot-body').forEach(function (b) { b.classList.toggle('stale', stale); });
        var m = $('bMotor');
        if (m && stale) { m.setAttribute('data-drive', 'unknown'); S.drive = 'unknown'; }
    }, 250);

    // ---------------------------------------------------------- render from state
    function render(st) {
        S.state = st;
        renderStatus(st); renderTarget(st); renderSession(st); renderSide(st); renderBif(st); renderDock(st);
    }

    function renderStatus(st) {
        var b = $('statusBtn'), txt = $('statusTxt');
        if (!b) { return; }
        var s = st.status, cls = {green: 'ok', neutral: 'ok', red: 'alarm', amber: 'caution', busy: 'busy'}[s.level] || '';
        b.className = 'status-btn ' + cls;
        var m = /^No data ([0-9.]+) s$/.exec(s.text || '');
        var html = m ? 'No data <span class="secs">' + esc(m[1]) + ' s</span>' : esc(s.text);
        if (txt.innerHTML !== html) { txt.innerHTML = html; }
        b.title = (s.issues || []).map(function (i) { return i.text + (i.detail ? ': ' + i.detail : ''); }).join('\n') ||
            'Connection, data streams and the settings the target reports back';
        // popover: every open item (most important first) with what to do
        var oi = $('openItems');
        if (oi) {
            var items = (s.issues || []), oh = items.length ? items.map(function (i) {
                return '<li class="' + esc(i.level) + '"><b>' + esc(i.text) + '</b>' +
                    (i.todo ? '<span class="todo">' + esc(i.todo) + '</span>' : '') +
                    (i.detail ? '<span class="todo hint">' + esc(i.detail) + '</span>' : '') + '</li>';
            }).join('') : '<li class="none">Nothing open</li>';
            oh += (s.notes || []).map(function (n) { return '<li class="note">' + esc(n) + '</li>'; }).join('');
            if (oi.innerHTML !== oh) { oi.innerHTML = oh; }
        }
        // popover: settings table + rig status
        var rows = st.settings.rows.map(function (r) {
            return '<tr class="' + r.state + '" data-k="' + r.key + '"' + (r.differs && r.differs.length ? ' title="Differs: ' + esc(r.differs.join(', ')) + '"' :
                r.title ? ' title="' + esc(r.title) + '"' : '') +
                '><td>' + esc(r.label) + '</td><td class="r mono">' + esc(r.entered) + '</td><td class="r mono">' + esc(r.target) + '</td></tr>';
        }).join('');
        var tb = document.querySelector('#echoTable tbody'); if (tb && tb.innerHTML !== rows) { tb.innerHTML = rows; }
        var et = $('echoTime');
        if (et) { et.textContent = st.settings.read_back_at ? 'Read back ' + st.settings.read_back_at : 'Not read back yet'; }
        var R = st.rig;
        var kv = [['Target', esc(R.target)], ['Application', esc(R.application)], ['TET', '<span class="mono">' + esc(R.tet) + '</span>'],
                  ['EtherCAT', esc(R.ethercat)], ['File log', esc(R.file_log)],
                  ['Main UDP', '<span class="mono">' + R.main_udp.rate + '</span>&nbsp;packets/s · ' + R.main_udp.bad + ' bad' +
                      ' · ' + (R.main_udp.lost || 0) + ' lost'],
                  ['Console UDP', R.console_udp.enabled ? '<span class="mono">' + R.console_udp.rate + '</span>&nbsp;packets/s · ' + R.console_udp.lost + ' lost' +
                      (R.console_udp.rejected ? ' · ' + R.console_udp.rejected + ' rejected' : '') : 'off'],
                  ['Drive statusword', '<span class="mono">' + esc(R.statusword) + '</span>'], ['IMU', esc(R.imu)]];
        if (st.model) { kv.splice(1, 0, ['Model profile', esc(st.model.label) +
            (st.model.source === 'last connect' ? ' <span class="muted">· last connected</span>' : '')]); }
        if (st.bif && st.bif.phase !== 'unknown') { kv.push(['Bi-LSTM', esc(st.bif.text.replace(/^Bi-LSTM: /, '')) + (st.bif.state_text ? ' · ' + esc(st.bif.state_text) : '') +
            (st.bif.source ? ' <span class="hint">(' + esc(st.bif.source) + ')</span>' : '')]); }
        var kvh = kv.map(function (x) { return '<dt>' + x[0] + '</dt><dd>' + x[1] + '</dd>'; }).join('');
        var k = $('rigKv'); if (k && k.innerHTML !== kvh) { k.innerHTML = kvh; }
        if ($('rigTime')) { $('rigTime').textContent = 'Updated ' + R.updated; }
    }

    function renderTarget(st) {
        var c = $('tConnect'), s = $('tStart'), p = $('tStop');
        if (!c || !s || !p) { return; }
        // MATLAB link row (Trials): Connected · app RUNNING / Not connected / Connecting… m:ss / Busy / Offline
        var mls = $('mlState');
        if (mls) {
            var bz = st.busy, keys = ((st.status || {}).issues || []).map(function (i) { return i.key; }), T0 = st.target || {};
            var txt = (bz && bz.stage === 'Connecting…') ? 'Connecting… ' + (bz.started ? mmss(Date.now() / 1000 - bz.started) : '') :
                T0.connected ? 'Connected' + (T0.app ? ' · ' + T0.app + (T0.running ? ' RUNNING' : ' stopped') : '') :
                keys.indexOf('speedgoat-busy') >= 0 ? 'Busy (another MATLAB session)' :
                keys.indexOf('speedgoat-offline') >= 0 ? 'Offline' : 'Not connected';
            if (mls.textContent !== txt) { mls.textContent = txt; }
        }
        var busy = st.busy, T = st.target, tablet = !st.local;
        // a button pressed less than its hold time ago keeps the busy text the click handler
        // gave it (until the server's busy state takes over); the others show their label
        [c, s, p].forEach(function (b) { if (!busyHeld(b)) { b.classList.remove('busy'); } });
        if (!b_conf(s) && !busyHeld(s)) { s.textContent = 'Start'; }
        if (!b_conf(p) && !busyHeld(p)) { p.textContent = 'Stop'; }
        if (!busyHeld(c)) { c.textContent = T.connected ? 'Disconnect' : 'Connect'; }
        c.title = T.connected ? 'Connected to ' + T.address : 'Connect to ' + T.address;
        if (tablet) {
            [c, s, p].forEach(function (b) { b.disabled = true; b.setAttribute('aria-disabled', 'true'); b.title = 'Start and stop from the OMEN'; });
            return;
        }
        if (st.view_only) {
            [s, p].forEach(function (b) { b.disabled = true; b.title = 'View-only console: Start and Stop are disabled'; });
        }
        if (busy) {
            var acting = {connect: c, disconnect: c, start: s, stop: p}[busy.action];
            [c, s, p].forEach(function (b) { b.disabled = true; b._busyUntil = 0; });
            if (acting) {
                acting.classList.add('busy');
                var el = busy.started ? ' ' + mmss(Date.now() / 1000 - busy.started) : '';
                acting.textContent = (busy.stage || busy.verb) + el; acting.title = busy.msg;
            }
            return;
        }
        if (busyHeld(c) || busyHeld(s) || busyHeld(p)) { return; }   // pressed: wait for the server's busy state
        c.disabled = false;
        if (st.view_only) { return; }
        // Start is never locked by the foot side: Start reloads the build defaults, and the
        // confirmed side and mass are sent right after it; Motor/Assist wait for the readback
        // Start / Stop connect by themselves when needed (Andy 14:48)
        s.disabled = !!T.running;
        s.title = T.running ? 'Running' : (T.connected ? '' : 'Connects first, then ') +
            'Reload the app and start; the confirmed foot side and mass are sent right after Start';
        p.disabled = !T.running;
        p.title = !T.running ? 'Stopped' : (T.connected ? '' : 'Connects first, then: ') + 'Stop the app (the file log stays on the target; export it from Trials)';
    }
    function b_conf(b) { return b.classList.contains('confirming'); }

    function renderSession(st) {
        var sv = st.session, part = $('sPart'), mass = $('sMass');
        checkConfirm(sv);
        if (part && document.activeElement !== part && !S.editing.sPart) { var v = sv.sid || ''; if (part.value !== v) { part.value = v; } }
        if (mass && document.activeElement !== mass && !S.editing.sMass) {
            var w = sv.values.weight; var t = w == null ? '' : String(+w); if (mass.value !== t) { mass.value = t; }
        }
        // Mass: visible state right after Enter (pending / sending / set / not set)
        var ms = $('sMassState');
        if (ms) {
            var mst = sv.status.weight, mmsg = sv.status_msg.weight || '', rbw = sv.readback ? sv.readback.weight : null;
            if (mass && !S.editing.sMass) {
                var held = mst === 'pending' || mst === 'sending';
                mass.classList.toggle('send-pending', held);
                if (held) { mass.classList.remove('send-error'); }
                mass.title = mst === 'pending' ? mmsg.replace(/^pending: /, 'Saved; ') : mst === 'sending' ? 'Sending…' : '';
            }
            var mt = '', mc = '';
            if (mst === 'pending') { mt = /Mass not set/.test(mmsg) ? 'not set' : /Not set on device/.test(mmsg) ? 'not on device' :
                /after Start/.test(mmsg) ? 'after Start' :
                /disabled/.test(mmsg) ? 'not sent' : 'when connected'; mc = 'pending'; }
            else if (mst === 'sending') { mt = 'sending…'; mc = 'pending'; }
            else if (mst === 'error') { mt = 'refused'; mc = 'err';
                var rmsg = /App started elsewhere/.test(mmsg) ? 'Target refused: app started by another MATLAB, press Stop → Start' :
                    'Target refused: ' + (mmsg || 'not set');
                if (S.massRefusedShown !== rmsg) { S.massRefusedShown = rmsg; dockMsg(rmsg, true); }
                mmsg = rmsg; }
            // design rule v17: no check marks, colour only; a confirmed mass is the normal field,
            // "Confirmed by device" in its tooltip
            var massOk = sv.values.weight != null && rbw != null && Math.abs(+rbw - +sv.values.weight) < 1e-3 && !mt;
            if (ms.textContent !== mt) { ms.textContent = mt; }
            ms.className = 'tb-state ' + mc; ms.hidden = !mt;
            if (mst !== 'error') { S.massRefusedShown = null; }
            ms.title = mst === 'pending' ? mmsg.replace(/^pending: /, 'Saved; ') : mst === 'error' ? (mmsg || 'Not set') : '';
            if (mass && !S.editing.sMass && massOk) { mass.title = 'Confirmed by device (5433 echo)'; }
        }
        var gw = $('sGearWrap'), gear = $('sGear'), isBif = !!(st.model && st.model.bif);
        var nc = $('advNc'); if (nc && nc.hidden !== isBif) { nc.hidden = isBif; }      // AFO_r1 does not use UDP 5430
        if (gw && gw.hidden === isBif) { gw.hidden = !isBif; setTimeout(topbarHeight, 0); }
        if (gear && isBif && document.activeElement !== gear && !S.editing.sGear) {
            var g = sv.values.bif_mass; var gt = g == null ? '' : String(+g); if (gear.value !== gt) { gear.value = gt; }
            var gs = sv.status.bif_mass, rb = sv.readback ? sv.readback.bif_mass : null;
            var low = rb != null && +rb <= 20;
            // pending (held, not sent yet) is amber; send error / too low for the Bi-LSTM is red
            gear.classList.toggle('send-error', gs === 'error' || low);
            gear.classList.toggle('send-pending', gs === 'pending' && !low);
            gear.title = (gs === 'pending' || gs === 'error') ? (sv.status_msg.bif_mass || 'Not sent') :
                low ? 'Target has ' + (+rb) + ' kg: the Bi-LSTM gives no assist until this is more than 20 kg' : '';
        }
        // run 15 (31-float echo): the values in use come from the echo (no MATLAB connection
        // needed); read-only (disabled, no hint) until the 5435 sender is there
        var av = sv.adv || {}, advUdp = !!av.udp;
        var advOn = advUdp || !!(st.target && st.target.connected);
        document.querySelectorAll('.adv-in').forEach(function (inp) {
            if (document.activeElement === inp || S.editing['adv-' + inp.getAttribute('data-k')]) { return; }
            var k = inp.getAttribute('data-k'), v = sv.values[k];
            if (advUdp) {
                var sending = sv.status[k] === 'sending' && v != null;
                v = sending ? v : (sv.readback || {})[k];
                var ro = !av.send || !!av.frozen;
                inp.disabled = ro; inp.readOnly = ro || inp.hasAttribute('readonly');
                inp.classList.remove('adv-stale');
                var tu = v == null ? '' : String(+v); if (inp.value !== tu) { inp.value = tu; }
                var su = sv.status[k];
                inp.classList.toggle('send-error', su === 'error' && !ro);
                inp.classList.toggle('send-pending', su === 'sending' && !ro);
                inp.title = av.frozen ? (av.msg || '') : (su === 'error' && !ro) ? (sv.status_msg[k] || 'Not sent') : '';
                return;
            }
            if (inp.disabled) { inp.disabled = false; }
            var last = (sv.adv_last || {})[k];
            if (!advOn) {
                // not connected: the last values read, greyed; "–" if never read (Connect is on Trials)
                var lt = last == null ? '–' : String(+last);
                if (inp.value !== lt) { inp.value = lt; }
                inp.classList.add('adv-stale'); inp.readOnly = true;
                inp.title = 'Connect on Trials to read' + (last == null ? '' : ' (last value read)');
                return;
            }
            inp.classList.remove('adv-stale'); inp.readOnly = inp.hasAttribute('readonly');
            if (v == null && last != null) { v = last; }
            var t = v == null ? '' : String(+v); if (inp.value !== t) { inp.value = t; }
            var stt = sv.status[k];
            inp.classList.toggle('send-error', stt === 'error');
            inp.classList.toggle('send-pending', stt === 'pending' || stt === 'sending');
            inp.title = stt === 'error' ? (sv.status_msg[k] || 'Not sent') :
                stt === 'pending' ? (sv.status_msg[k] || 'pending').replace(/^pending: /, 'Saved; ') : stt === 'sending' ? 'Sending…' : '';
        });
    }

    function renderSide(st) {
        var chip = $('sideChip'), ban = $('sideBanner');
        if (!chip) { return; }
        var sd = st.side, motorOn = st.commands.toggles.motor.value === 1, onLive = S.page === 'live';
        chip.textContent = sd.chip;
        // the attention style of "? CONFIRM FOOT" only on Live and connected; else the chip stays quiet
        chip.className = 'side-chip' + (sd.state === 'confirm' && onLive && sd.connected ? ' unset' :
            (sd.state === 'mismatch' || sd.state === 'refused') ? ' mismatch' : sd.state === 'pending' ? ' pending' : '');
        // the target refused the side: say so at once in the dock (once per refusal), no silent wait
        if (sd.state === 'refused' && sd.msg && S.sideRefusedShown !== sd.msg) {
            S.sideRefusedShown = sd.msg; dockMsg(sd.msg, true); if (typeof toast === 'function') { toast(sd.msg, true); }
        } else if (sd.state !== 'refused') { S.sideRefusedShown = null; }
        chip.disabled = motorOn;
        // full text in the title: the chip ellipsizes when the top bar is tight
        chip.title = sd.chip + ' · ' + (motorOn ? 'Locked while Motor is on' : sd.state === 'ok' ? 'Confirmed by device (5433 echo)' : 'Foot side on the target');
        if (!ban) {
            document.querySelectorAll('.side-opt').forEach(function (o) { o.setAttribute('aria-pressed', o.getAttribute('data-side') === sd.app ? 'true' : 'false'); });
            return;
        }
        var sid = esc(st.session.sid || 'this participant'), html = '', cls = '';
        if (sd.state !== 'mismatch' && !onLive) {
            // Trials / DAQ: no foot-side banner (the quiet chip stays in the top bar)
        } else if (!st.session.sid) {
            cls = 'caution'; html = '<span><b>Set the participant ID</b> in the top bar, then confirm the foot side.</span>';
        } else if (sd.state === 'pending') {
            cls = 'info';
            html = '<span><b>' + esc((sd.app || '').charAt(0) + (sd.app || '').slice(1).toLowerCase()) + ' foot saved for ' + sid + '.</b> ' +
                (/disabled/.test(sd.msg || '') ? 'Target writes are off, so it is not sent.' :
                 /after Start/.test(sd.msg || '') ? 'The app is stopped: it is sent right after Start and then read back.' :
                 'Not connected: it is sent when connected (at once if the app is running, else right after Start) and then read back.') +
                '</span><span class="spacer"></span><span class="lock-note">Motor and Assist stay locked until the target reports this side.</span>';
        } else if (sd.state === 'confirm') {
            cls = 'caution';
            html = '<span>' + (sd.after_start ? 'Start reset the target to its build defaults. <b>Confirm the foot side for ' + sid +
                '</b> to send the session values again.' : '<b>Confirm the foot side for ' + sid + '.</b> The AFO direction depends on it.') +
                '</span><span class="spacer"></span><button class="btn" data-pick="LEFT">Left foot</button><button class="btn" data-pick="RIGHT">Right foot</button>' +
                '<span class="lock-note">Motor and Assist stay locked until the target reports this side.</span>';
        } else if (sd.state === 'mismatch') {
            cls = 'alarm';
            html = '<span><b>Foot side differs.</b> This app has ' + esc(sd.app) + ', the target reports ' + esc(sd.target) +
                '. A flipped side reverses the actuation, so Motor and Assist are off.</span><span class="spacer"></span>' +
                '<button class="btn" data-pick="' + esc(sd.app) + '">Send ' + esc(sd.app) + ' to target</button>' +
                '<button class="btn" data-pick="' + esc(sd.target) + '">Use target\'s ' + esc(sd.target) + '</button>';
        }
        var key = cls + '|' + html;
        if (ban.getAttribute('data-key') !== key) {
            ban.setAttribute('data-key', key);
            ban.className = 'sys-banner' + (cls ? ' ' + cls : '');
            ban.innerHTML = html; ban.hidden = !html;
            ban.querySelectorAll('[data-pick]').forEach(function (x) {
                x.addEventListener('click', function () { sendSide(x.getAttribute('data-pick')); });
            });
            setTimeout(function () { window.dispatchEvent(new Event('resize')); }, 30);
        }
        document.querySelectorAll('.side-opt').forEach(function (o) { o.setAttribute('aria-pressed', o.getAttribute('data-side') === sd.app ? 'true' : 'false'); });
    }

    function renderBif(st) {
        var list = $('afterStart'), head = $('afterStartHead'), line = $('bifLine');
        if (list && head) {
            var chk2 = st.checklist, bif2 = st.bif, h2 = '';
            if (chk2) {
                h2 = chk2.items.map(function (i) {
                    var mark = '';
                    return '<li class="' + (i.done === true ? 'done' : i.done === false ? 'todo' : 'unknown') + '">' + mark + '' +
                        esc(i.text) + (i.detail ? ' <span class="hint">' + esc(i.detail) + '</span>' : '') + '</li>';
                }).join('');
            }
            if (list.innerHTML !== h2) { list.innerHTML = h2; }
            list.hidden = !h2; head.hidden = !h2;
            if (line) { var lt = bif2 && bif2.phase !== 'unknown' ? bif2.text : ''; if (line.textContent !== lt) { line.textContent = lt; } }
        }
        var ban = $('bifBanner'); if (!ban) { return; }
        var html = '', chk = st.checklist, bif = st.bif;
        if (chk && !chk.all_done) {
            html = '<span><b>After Start</b></span><ol class="checklist">' + chk.items.map(function (i) {
                var mark = '';
                return '<li class="' + (i.done === true ? 'done' : i.done === false ? 'todo' : 'unknown') + '">' + mark + '' +
                    esc(i.text) + (i.detail ? ' <span class="hint">' + esc(i.detail) + '</span>' : '') + '</li>';
            }).join('') + '</ol><span class="spacer"></span>' + (bif ? '<span class="bif-txt">' + esc(bif.text) + '</span>' : '');
        } else if (bif && st.target.running && bif.phase !== 'valid' && bif.phase !== 'unknown') {
            html = '<span class="bif-txt">' + esc(bif.text) + '</span>';
        }
        var key = html;
        if (ban.getAttribute('data-key') !== key) {
            ban.setAttribute('data-key', key); ban.innerHTML = html; ban.hidden = !html;
            setTimeout(function () { window.dispatchEvent(new Event('resize')); }, 30);
        }
    }

    function setPill(btn, value, pending, mismatch) {
        var p = btn.querySelector('.pill'), st = value === 1 ? 'on' : value === 0 ? 'off' : 'unknown';
        if (!p.classList.contains(st)) { p.className = 'pill ' + st; p.textContent = st === 'on' ? 'On' : st === 'off' ? 'Off' : '?'; }
        btn.classList.toggle('pending', !!pending);
        btn.classList.toggle('mismatch', !!mismatch);
    }

    function renderDock(st) {
        var T = st.commands.toggles, sideOk = st.side.state === 'ok';
        var mb = $('bMotor'), ab = $('bAssist'), kb = $('bK');
        if (!mb) { return; }
        // run 14: the 5433 echo stalled -> every control frozen, nothing sent, the device keeps
        // its settings; when the echo returns the page re-adopts the device state and unfreezes
        var lk = st.link || {};
        if (lk.frozen) {
            setPill(mb, T.motor.value, false, false); setPill(ab, T.assist.value, false, false); setPill(kb, T.k.value, false, false);
            document.querySelectorAll('#dock button, #dock input, #sideChip, #sMass').forEach(function (el) {
                el.disabled = true; el.title = lk.msg;
            });
            var fdm = $('dockMsg'); if (fdm && fdm.textContent !== lk.msg) { fdm.textContent = lk.msg; fdm.style.color = 'var(--caution)'; }
            S.wasFrozen = true;
            return;
        }
        if (S.wasFrozen) {
            S.wasFrozen = false;
            document.querySelectorAll('#dock button, #dock input, #sideChip, #sMass').forEach(function (el) { el.disabled = false; el.title = ''; });
            var udm = $('dockMsg'); if (udm) { udm.textContent = ''; udm.style.color = ''; }
        }
        if (st.view_only) {
            setPill(mb, T.motor.value, false, T.motor.mismatch); setPill(ab, T.assist.value, false, T.assist.mismatch);
            setPill(kb, T.k.value, false, T.k.mismatch);
            document.querySelectorAll('#dock button, #dock input').forEach(function (el) {
                el.disabled = true; el.title = 'View-only console: commands are not sent from this app';
            });
            var dm = $('dockMsg'); if (dm && dm.textContent !== 'View-only: commands disabled') { dm.textContent = 'View-only: commands disabled'; }
            return;
        }
        setPill(mb, T.motor.value, T.motor.pending, T.motor.mismatch);
        setPill(ab, T.assist.value, T.assist.pending, T.assist.mismatch);
        setPill(kb, T.k.value, T.k.pending, T.k.mismatch);
        S.lastT = T;
        var fault = S.drive === 'fault';
        var sw = mb.getAttribute('data-sw');
        // AFO_r1: the statusword cannot tell "STO engaged" from "fault latched after STO was
        // released" (both 0x0628). Motor OFF -> ON makes the model's Drive Enable Logic send
        // the fault-reset pulses, so Motor stays clickable (neutral grey) with Assist off and
        // the side confirmed; it was disabled before, which made the fault impossible to clear.
        var isR1 = !!(st.model && st.model.bif);
        var faultReset = fault && isR1 && T.motor.value !== 1 && T.assist.value !== 1 && sideOk;
        // locked Motor: aria-disabled (not disabled), so its title shows on hover and a press can
        // say why in the dock; it keeps the drive colour (red while the fault is latched)
        var locked = (fault && T.motor.value !== 1 && !faultReset) || (!sideOk && T.motor.value !== 1);
        mb.disabled = false;
        mb.setAttribute('aria-disabled', locked ? 'true' : 'false');
        var lockWhy = '';
        if (!sideOk && T.motor.value !== 1) {
            var sdv = st.side || {}, elsewhere = ((st.status || {}).issues || []).some(function (i) { return i.key === 'app-elsewhere'; });
            var why = sdv.target === 'UNSET' ? 'foot side not set on the target' :
                sdv.state === 'mismatch' ? 'foot side on the target differs' :
                sdv.state === 'refused' ? 'foot side refused by the target' :
                sdv.state === 'pending' ? 'foot side not on the target yet' : 'confirm the foot side first';
            lockWhy = 'Motor locked: ' + why + (elsewhere || sdv.state === 'refused' && /another MATLAB/.test(sdv.msg || '') ?
                ' (app started by another MATLAB: press Stop → Start)' : '') + (fault ? '; drive fault latched' + (sw ? ' (' + sw + ')' : '') : '');
        } else if (locked && fault) {
            lockWhy = 'Motor locked: drive fault' + (sw ? ' (' + sw + ')' : '') + ': clear STO first';
        }
        S.motorLockWhy = locked ? lockWhy : '';
        // stays RED (fault colour from data-drive) but clickable; after a press that did not clear
        // the fault within 2 s, say so (STO is probably still engaged)
        // Independent of the Motor value: with STO engaged the model still echoes cmd_motor = 1
        // after the press (run 12), so this must not depend on faultReset. Kept until the fault
        // clears or Motor goes OFF again (1 -> 0 after the press).
        if (!fault) { S.motorFaultPressAt = null; S.motorFaultOnSeen = false; }
        if (S.motorFaultPressAt) {
            if (T.motor.value === 1) { S.motorFaultOnSeen = true; }
            else if (S.motorFaultOnSeen && T.motor.value === 0) { S.motorFaultPressAt = null; S.motorFaultOnSeen = false; }
        }
        var NC_MSG = 'Fault not cleared: is STO released?';
        var notCleared = !!(fault && S.motorFaultPressAt && Date.now() - S.motorFaultPressAt > 2000);
        if (notCleared && !S.motorFaultNoted) { S.motorFaultNoted = true;
            if (typeof toast === 'function') { toast(NC_MSG, true); } }
        var dmEl = $('dockMsg');
        if (dmEl) {
            if (notCleared && dmEl.textContent !== NC_MSG) { clearTimeout(S.msgT); dmEl.textContent = NC_MSG; dmEl.style.color = 'var(--alarm)'; }
            else if (!notCleared && dmEl.textContent === NC_MSG) { dmEl.textContent = ''; dmEl.style.color = ''; }
        }
        mb.title = (S.motorLockWhy && !sideOk) ? S.motorLockWhy :
            notCleared ? 'Fault not cleared: is STO released? Release STO, then press Motor again' + (sw ? ' (' + sw + ')' : '') :
            faultReset ? 'Drive fault' + (sw ? ' (' + sw + ')' : '') + ': release STO, then press Motor to clear it' :
            (fault && isR1 && T.assist.value === 1 && T.motor.value !== 1) ? 'Drive fault: switch Assist off, then press Motor to clear it' :
            S.motorLockWhy ? S.motorLockWhy :
            fault ? 'Drive fault: clear STO first' + (sw ? ' (' + sw + ')' : '') :
            (sw ? 'Drive statusword ' + sw : 'No drive data');
        ab.disabled = !sideOk && T.assist.value !== 1;
        ab.title = ab.disabled ? 'Confirm the foot side first' : '';
        var unknown = ['motor', 'assist', 'k'].some(function (t) { return T[t].value == null; });
        $('unknownOff').hidden = !unknown;
        // mode: the model's echo drives the selected segment
        var sv = st.session, rb = sv.readback || {};
        var mode = rb.mode != null ? Math.round(+rb.mode) : (sv.values.mode != null ? Math.round(+sv.values.mode) : null);
        document.querySelectorAll('#modeSel button').forEach(function (b) {
            if (!b.classList.contains('confirming')) { b.setAttribute('aria-pressed', String(+b.getAttribute('data-m') === mode)); }
        });
        var modeRow = st.settings.rows.filter(function (r) { return r.key === 'mode'; })[0];
        $('modeBox').classList.toggle('mismatch', !!(modeRow && modeRow.state === 'differs'));
        var kf = $('kField'); kf.classList.toggle('off', mode !== 3);
        var kp = $('kPct');
        if (document.activeElement !== kp && !S.editing.kPct) {
            var kv = sv.values.k_percent != null ? sv.values.k_percent : rb.k_percent;
            var t = kv == null ? '' : (+kv).toFixed(1); if (kp.value !== t) { kp.value = t; }
        }
        // one-shot actions (assets/afo_dock_actions.js): fixed labels, lit / greyed / pressed by colour,
        // `disabled` always cleared (Zero stayed grey after one press, 15:05)
        if (window.AFODockActions) {
            AFODockActions.render({zero: $('bZero'), imu: $('bImuCal'), cal: $('bCal'), reset: $('bResetSV')}, st, Date.now());
        }
    }

    function dockMsg(t, isErr) {
        var m = $('dockMsg'); if (!m) { return; }
        m.textContent = t || ''; m.style.color = isErr ? 'var(--alarm)' : '';
        clearTimeout(S.msgT); if (t) { S.msgT = setTimeout(function () { m.textContent = ''; }, 6000); }
    }

    // ---------------------------------------------------------- actions
    // a press of side / mass / mode / K: toast "sending…", fast polling until the device echo
    // confirms (then "… saved" for 1.5 s) or 3 s pass
    function expectConfirm(key, label) { S.expect = {key: key, label: label, at: Date.now()}; S.fastUntil = Date.now() + 3000; }
    function checkConfirm(sv) {
        var e = S.expect; if (!e) { return; }
        var st = (sv.status || {})[e.key];
        if (st === 'confirmed') { S.expect = null; S.fastUntil = 0; toast(e.label + ' saved', false); clearTimeout(S.toastT);
            S.toastT = setTimeout(function () { var el = $('afoToast'); if (el) { el.hidden = true; } }, 1500); }
        else if (st === 'error' || Date.now() - e.at > 3000) { S.expect = null; S.fastUntil = 0; }
    }
    function toast(t, isErr) {
        var el = $('afoToast');
        if (!el) { el = document.createElement('div'); el.id = 'afoToast'; el.className = 'toast'; el.setAttribute('role', 'status');
                   el.setAttribute('aria-live', 'polite'); document.body.appendChild(el); }
        el.textContent = t || ''; el.className = 'toast' + (isErr ? ' err' : ''); el.hidden = !t;
        clearTimeout(S.toastT); if (t) { S.toastT = setTimeout(function () { el.hidden = true; }, 6000); }
    }
    function sendSide(side) {
        var name = side.charAt(0) + side.slice(1).toLowerCase();
        toast(name + ' foot: sending…', false);
        // the chip shows the pick at once (pending) instead of after the next state poll
        var chip = $('sideChip');
        if (chip) { chip.textContent = name + ' · sending…'; chip.className = 'side-chip pending'; }
        expectConfirm('side', name + ' foot');
        post('/api/console/side', {side: side}).then(function (r) {
            closeSidePop();
            var err = !r.ok || r._status >= 400;
            var m = (r.msg || '');
            var when = /not sent|writes are disabled|writes off/i.test(m) ? 'not sent (target writes off)' :
                /after Start/i.test(m) ? 'sent after Start' : /when connected|on Connect/i.test(m) ? 'sent when connected' : '';
            var t = err ? (m || 'Foot side not accepted') :
                r.state === 'pending' ? name + ' foot saved; ' + (when || 'sent later') :
                (name + ' foot: sending…');
            toast(t, err); dockMsg(err ? m : '', err); poll();
        }).catch(function () { toast('App not reachable: foot side not sent', true); });
    }
    function commitField(el, key, url, body) {
        S.editing[key] = true;
        var ck = (body && (body.key || body.name)) || ({sMass: 'weight', kPct: 'k_percent'})[key] || key;
        expectConfirm(ck, ck === 'weight' ? 'Body mass' : ck === 'k_percent' ? 'K' : ck === 'mode' ? 'Mode' : ck);
        post(url, body).then(function (r) {
            S.editing[key] = false;
            var ok = r.ok && (r.state === 'sending' || r.state === 'confirmed' || r.state === undefined);
            var held = r.ok && r.state === 'pending';     // saved, sent later: amber, not the red send error
            if (held) {
                el.classList.remove('sent-flash', 'send-error'); el.classList.add('send-pending');
                el.title = (r.msg || '').replace(/^pending: /, 'Saved; ');
            } else {
                el.classList.remove('send-pending');
                flash(el, ok, r.needs_confirm || r.msg || 'Not sent');
            }
            if (typeof toast === 'function') { toast(r.needs_confirm || r.msg || (ok ? 'Saved' : 'Not sent'), !ok && !held); }
            poll();
        });
    }
    function bindChrome() {
        // session fields: sent on Enter or when leaving the field
        function onCommit(el, fn) {
            var start = null;
            el.addEventListener('focus', function () { start = el.value; });
            el.addEventListener('keydown', function (e) { if (e.key === 'Enter') { el.blur(); } if (e.key === 'Escape') { el.value = start; el.blur(); } });
            el.addEventListener('blur', function () { if (el.value !== start && el.value.trim() !== '') { fn(el.value.trim()); } });
        }
        onCommit($('sPart'), function (v) { commitField($('sPart'), 'sPart', '/api/console/sid', {sid: v}); });
        onCommit($('sMass'), function (v) { commitField($('sMass'), 'sMass', '/api/console/value', {key: 'weight', value: v}); });

        document.querySelectorAll('.adv-in').forEach(function (inp) {
            if (inp.readOnly) { return; }
            var k = inp.getAttribute('data-k');
            onCommit(inp, function (v) { commitField(inp, 'adv-' + k, '/api/console/value', {key: k, value: v}); });
        });
        // popovers
        var sb = $('statusBtn'), sp = $('statusPop'), ab = $('advBtn'), ap = $('advPop'), chip = $('sideChip');
        function toggle(btn, pop) { var open = pop.hidden; closeAll(); pop.hidden = !open; btn.setAttribute('aria-expanded', String(open)); }
        sb.addEventListener('click', function (e) { e.stopPropagation(); toggle(sb, sp); });
        ab.addEventListener('click', function (e) { e.stopPropagation(); toggle(ab, ap); });
        chip.addEventListener('click', function (e) {
            e.stopPropagation(); if (chip.disabled) { return; }
            var r = chip.getBoundingClientRect(), pop = $('sidePop');
            $('sideConfirm').hidden = true; S.pendingSide = null;
            pop.style.top = (r.bottom + 6) + 'px'; pop.style.left = Math.max(16, Math.min(r.left, window.innerWidth - 296)) + 'px'; pop.style.right = 'auto';
            toggle(chip, pop);
        });
        [sp, ap, $('sidePop')].forEach(function (p) { p.addEventListener('click', function (e) { e.stopPropagation(); }); });
        document.addEventListener('click', closeAll);
        document.addEventListener('keydown', function (e) { if (e.key === 'Escape') { closeAll(); } });
        document.querySelectorAll('.side-opt').forEach(function (o) {
            o.addEventListener('click', function () {
                var side = o.getAttribute('data-side'), sd = (S.state || {}).side || {};
                if (side === sd.app && sd.state === 'ok') { closeSidePop(); return; }
                S.pendingSide = side;
                var nm = side === 'LEFT' ? 'Left' : 'Right';
                $('scTitle').textContent = (sd.app && side !== sd.app ? 'Switch to ' : 'Use ') + nm + ' foot?';
                $('scOk').textContent = (sd.app && side !== sd.app ? 'Switch to ' : 'Use ') + nm;
                $('sideConfirm').hidden = false;
            });
        });
        $('scCancel').addEventListener('click', function () { S.pendingSide = null; $('sideConfirm').hidden = true; });
        $('scOk').addEventListener('click', function () { if (S.pendingSide) { sendSide(S.pendingSide); } });
        // target controls (OMEN only): Connect | Start (two-step) | Stop (two-step)
        $('tConnect').addEventListener('click', function () {
            var T = (S.state || {}).target || {};
            busyNow($('tConnect'), T.connected ? 'Disconnecting…' : 'Connecting…');
            post('/api/run/' + (T.connected ? 'disconnect' : 'connect')).then(function (r) { if (r.err) { dockMsg(r.err, true); $('tConnect')._busyUntil = 0; } poll(); });
        });
        confirmable($('tStart'), function () { return 'Start'; }, function () {
            var app = ((S.state || {}).side || {}).app; return 'Start · ' + (app || '?') + ' foot?';
        }, function () { busyNow($('tStart'), 'Starting…');
            post('/api/run/start').then(function (r) { if (r.err) { dockMsg(r.err, true); $('tStart')._busyUntil = 0; } poll(); }); });
        confirmable($('tStop'), function () { return 'Stop'; }, 'Confirm stop?', function () {
            busyNow($('tStop'), 'Stopping…');
            post('/api/run/stop').then(function (r) { if (r.err) { dockMsg(r.err, true); $('tStop')._busyUntil = 0; } poll(); });
        });
    }
    function closeSidePop() { var p = $('sidePop'); if (p) { p.hidden = true; } var c = $('sideChip'); if (c) { c.setAttribute('aria-expanded', 'false'); } }
    function closeAll() {
        ['statusPop', 'advPop', 'sidePop'].forEach(function (id) { var p = $(id); if (p) { p.hidden = true; } });
        ['statusBtn', 'advBtn', 'sideChip'].forEach(function (id) { var b = $(id); if (b) { b.setAttribute('aria-expanded', 'false'); } });
    }

    function bindDock() {
        [['bMotor', 'motor'], ['bAssist', 'assist'], ['bK', 'k']].forEach(function (x) {
            if (x[1] === 'motor') {
                // a locked Motor says why once in the dock when hovered (title has it too)
                $(x[0]).addEventListener('mouseenter', function () {
                    if (S.motorLockWhy && S.motorLockShown !== S.motorLockWhy) { S.motorLockShown = S.motorLockWhy; dockMsg(S.motorLockWhy, true); }
                });
            }
            $(x[0]).addEventListener('click', function () {
                if (x[1] === 'motor' && $(x[0]).getAttribute('aria-disabled') === 'true') {
                    dockMsg(S.motorLockWhy || 'Motor locked', true);       // pressed while locked: say why, send nothing
                    return;
                }
                if (x[1] === 'motor') {
                    // an ON press with the fault bit set is a fault-reset attempt; an OFF press ends it
                    var on = S.lastT && S.lastT.motor && S.lastT.motor.value === 1;
                    if (on) { S.motorFaultPressAt = null; S.motorFaultOnSeen = false; }
                    else if (S.drive === 'fault') { S.motorFaultPressAt = Date.now(); S.motorFaultNoted = false; S.motorFaultOnSeen = false; }
                }
                post('/api/console/toggle', {name: x[1]}).then(function (r) {
                    dockMsg(r.ok ? '' : r.msg, !r.ok);
                    if (!r.ok && /unknown/i.test(r.msg || '')) { $('unknownOff').hidden = false; }
                    poll();
                });
            });
        });
        confirmable($('unknownOff'), function () { return 'Set unknown to OFF'; }, 'Send with unknown = OFF?', function () {
            post('/api/console/unknown-off').then(function (r) { dockMsg(r.msg, !r.ok); poll(); });
        });
        // mode: RL | Fixed K. If Assist is ON, switching uses the two-step confirm.
        document.querySelectorAll('#modeSel button').forEach(function (b) {
            var tm = null;
            b.addEventListener('click', function () {
                var m = +b.getAttribute('data-m');
                if (b.getAttribute('aria-pressed') === 'true') { return; }
                var assistOn = (((S.state || {}).commands || {}).toggles || {}).assist && S.state.commands.toggles.assist.value === 1;
                if (assistOn && !b.classList.contains('confirming')) {
                    b.classList.add('confirming'); b.textContent = 'Switch to ' + (m === 1 ? 'RL' : 'Fixed K') + '?';
                    tm = setTimeout(function () { b.classList.remove('confirming'); b.textContent = m === 1 ? 'RL' : 'Fixed K'; }, 3000);
                    return;
                }
                clearTimeout(tm); b.classList.remove('confirming'); b.textContent = m === 1 ? 'RL' : 'Fixed K';
                post('/api/console/value', {key: 'mode', value: m, confirmed: true}).then(function (r) {
                    dockMsg(r.state === 'pending' ? r.msg : (r.ok ? '' : r.msg), !r.ok || r.state === 'pending'); poll();
                });
            });
        });
        // K %: one decimal, sent on Enter/blur; a change over 2 % with Motor ON asks once more
        var kp = $('kPct'), kc = $('kConfirm'), start = null;
        kp.addEventListener('focus', function () { start = kp.value; });
        kp.addEventListener('keydown', function (e) { if (e.key === 'Enter') { kp.blur(); } if (e.key === 'Escape') { kp.value = start; kp.blur(); } });
        function sendK(v, confirmed) {
            S.editing.kPct = true;
            post('/api/console/value', {key: 'k_percent', value: v, confirmed: !!confirmed}).then(function (r) {
                S.editing.kPct = false;
                if (r._status === 409 && r.needs_confirm) {
                    kc.hidden = false; kc.className = 'btn sm confirming'; kc.textContent = 'Confirm ' + (+v).toFixed(1) + ' %?'; kc.title = r.needs_confirm;
                    kc.onclick = function () { kc.hidden = true; sendK(v, true); };
                    clearTimeout(S.kT); S.kT = setTimeout(function () { kc.hidden = true; poll(); }, 3000);
                    return;
                }
                flash(kp, r.ok && r.state !== 'pending', r.msg); poll();
            });
        }
        kp.addEventListener('blur', function () { if (kp.value !== start && kp.value.trim() !== '') { sendK(kp.value.trim(), false); } });
        // Zero / Calibrate FSR: toggles; Reset SV: 200 ms pulse; Calibrate IMU: counter + 1.
        // No text change and no toast on success, only a message on an error or refusal.
        function dockAct(id, url, body) {
            var b = $(id);
            if (!b || b.disabled) { return; }
            if (b.getAttribute('aria-disabled') === 'true') { dockMsg(b.title, true); return; }
            // toggles: a brief pressed tint; IMU / Reset SV: dark only while held (CSS :active)
            if (window.AFODockActions && !b.classList.contains('momentary')) { AFODockActions.press(b, Date.now()); }
            post(url, body).then(function (r) {
                if (!r.ok) { dockMsg(r.msg, true); }
                else if (r.state === 0 || r.state === 1) { b.classList.toggle('lit', r.state === 1); }
                poll();
            });
        }
        $('bZero').addEventListener('click', function () { dockAct('bZero', '/api/console/pulse', {name: 'zero'}); });
        $('bCal').addEventListener('click', function () { dockAct('bCal', '/api/console/pulse', {name: 'calibrate'}); });
        $('bResetSV').addEventListener('click', function () { dockAct('bResetSV', '/api/console/pulse', {name: 'reset'}); });
        $('bImuCal').addEventListener('click', function () { dockAct('bImuCal', '/api/console/imucal', {}); });
    }

    // ---------------------------------------------------------- Trials
    function fmtStart(s) {
        if (!s) { return '–'; }
        var d = new Date(String(s).replace(' ', 'T'));
        if (isNaN(d)) { return esc(s); }
        return d.toLocaleString('en-US', {month: 'short', day: 'numeric'}) + ', ' + ('0' + d.getHours()).slice(-2) + ':' + ('0' + d.getMinutes()).slice(-2);
    }
    function fmtDur(s) { if (s == null) { return '–'; } s = Math.round(+s); return Math.floor(s / 60) + ':' + ('0' + (s % 60)).slice(-2); }
    function fmtSize(b) { if (b == null || b === '') { return '–'; } b = +b; return b >= 1e9 ? (b / 1e9).toFixed(1) + ' GB' : Math.round(b / 1e6) + ' MB'; }
    function loadRuns() {
        getJSON('/api/trials/runs').then(function (d) { S.runs = d; renderRuns(); }).catch(function () {});
    }
    function selectedRun() { var rs = (S.runs || {}).runs || []; return rs.filter(function (r) { return r.id === S.selRun; })[0]; }
    function renderRuns() {
        var tb = document.querySelector('#runTable tbody'); if (!tb) { return; }
        var d = S.runs || {runs: []}, rs = d.runs || [];
        var lim = $('runsLimit');
        if (lim) {
            var lh = '';
            if (rs.length && d.max_runs) {
                lh = '<span>' + d.n_runs + '/' + d.max_runs + ' runs on target · the oldest is deleted at ' + d.max_runs + '</span>';
                if (d.near_limit) {
                    lh += '<span class="warn">Export before the next run: the oldest unexported run will be deleted (' +
                        d.unexported + ' not exported)</span>';
                }
            }
            if (lim.innerHTML !== lh) { lim.innerHTML = lh; }
            lim.hidden = !lh; lim.classList.toggle('near', !!d.near_limit);
        }
        if (!rs.length) {
            tb.innerHTML = '<tr><td colspan="6" class="hint">' + (d.connected ? 'No runs in the file log yet. Press Refresh after Stop.' :
                'Not connected: the run list is read from the Speedgoat. Connect in the top bar, then Refresh.') +
                (d.err ? ' (' + esc(d.err) + ')' : '') + '</td></tr>';
        } else {
            if (!selectedRun()) { var first = rs.filter(function (r) { return !r.recording; })[0]; S.selRun = first ? first.id : null; }
            tb.innerHTML = rs.map(function (r) {
                var st = r.recording ? '<span class="exp-st rec">Recording · exportable after Stop</span>' :
                    r.exported ? '<span class="exp-st done">Exported</span>' : '<span class="exp-st">Not exported</span>';
                if (r.split_of && !r.recording) { st += '<span class="hint"> · continues the previous run, joined on export</span>'; }
                return '<tr' + (r.recording ? ' class="rec"' : ' tabindex="0" aria-selected="' + (r.id === S.selRun) + '"') + ' data-id="' + esc(r.id) + '">' +
                    '<td class="num l">' + esc(r.row) + '</td><td>' + fmtStart(r.start) + '</td><td class="num">' + fmtDur(r.duration_s) + '</td>' +
                    '<td class="num">' + fmtSize(r.size) + '</td><td>' + (r.participant ? esc(r.participant) : '<span class="hint">none set</span>') + '</td><td>' + st + '</td></tr>';
            }).join('');
            tb.querySelectorAll('tr[data-id]:not(.rec)').forEach(function (tr) {
                function sel() { S.selRun = tr.getAttribute('data-id'); S.expEdited = false; renderRuns(); }
                tr.addEventListener('click', sel);
                tr.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); sel(); } });
            });
        }
        var r = selectedRun(), name = $('expName'), stt = $('expState'), btn = $('expBtn');
        if (r && !S.expEdited && document.activeElement !== name) {
            var base = r.exported && r.export ? r.export.mat.split(/[\\/]/).pop() : (r.default_name ? r.default_name + '.mat' : '');
            if (name.value !== base) { name.value = base; }
        }
        if (!S.exportBusy) {
            stt.textContent = r ? 'Run ' + r.row + ' · ' + fmtDur(r.duration_s) + ' · ' + fmtSize(r.size) : '';
            if (!b_conf(btn)) { btn.textContent = r && r.exported ? 'Export again' : 'Export'; }
        }
        btn.disabled = !r || !local() || !!S.exportBusy;
        btn.title = !local() ? 'Export from the OMEN' : '';
        $('runsRefresh').hidden = !local();
    }
    function bindTrials() {
        $('expName').addEventListener('input', function () { S.expEdited = true; });
        $('runsRefresh').addEventListener('click', function () {
            $('runsHint').textContent = 'Reading the file log…';
            post('/api/trials/runs/refresh').then(function (r) {
                $('runsHint').textContent = r.ok ? 'Reading the file log…' : (r.msg || 'Refresh failed');
                setTimeout(loadRuns, 1500); setTimeout(loadRuns, 5000);
            });
        });
        var btn = $('expBtn');
        confirmable(btn, function () { var r = selectedRun(); return r && r.exported ? 'Export again' : 'Export'; },
            'Replace file?', function () { doExport(true); });
        // a first click on a NOT exported run exports at once (no confirm)
        btn.addEventListener('click', function (e) {
            var r = selectedRun();
            if (r && !r.exported && btn.classList.contains('confirming')) {
                btn.classList.remove('confirming'); btn.textContent = 'Export'; doExport(false);
            }
        }, true);
    }
    function doExport(replace) {
        var r = selectedRun(); if (!r) { return; }
        var nm = $('expName').value.trim().replace(/\.mat$/i, '');
        S.exportBusy = true; var btn = $('expBtn'), stt = $('expState');
        btn.classList.add('busy'); btn.textContent = 'Exporting…'; btn.disabled = true;
        post('/api/trials/runs/export', {id: r.id, name: nm, replace: !!replace, join: true}).then(function (res) {
            if (!res.ok) { S.exportBusy = false; btn.classList.remove('busy'); stt.textContent = res.msg || 'Export failed'; renderRuns(); return; }
            var t0 = Date.now();
            (function wait() {
                getJSON('/api/run/status').then(function (s) {
                    var j = s.job;
                    if (j && j.state === 'running' && Date.now() - t0 < 900000) { setTimeout(wait, 1000); return; }
                    S.exportBusy = false; btn.classList.remove('busy');
                    stt.textContent = j && j.state === 'done' ? 'Saved ' + nm + '.mat' : 'Export failed: see the log';
                    loadRuns();
                });
            })();
        });
    }

    // ---------------------------------------------------------- polling + boot
    function poll() {
        return getJSON('/api/console/state').then(render).catch(function () {
            var b = $('statusBtn'); if (b) { b.className = 'status-btn alarm'; $('statusTxt').textContent = 'App not reachable'; }
        });
    }
    function topbarHeight() {
        var tb = $('topbar'); if (tb) { document.documentElement.style.setProperty('--topbar-real', tb.getBoundingClientRect().height + 'px'); }
    }
    function boot() {
        var top = $('chrome-top'), dock = $('dock'), tr = $('trials-root');
        if (!top || !dock || !tr || !$('page-live')) { setTimeout(boot, 50); return; }
        top.innerHTML = chromeHTML(); dock.innerHTML = dockHTML(); tr.innerHTML = trialsHTML();
        bindChrome(); bindDock(); bindTrials();
        window._afoLiveSub = 'gait';
        go((location.pathname || '/').replace(/^\/+|\/+$/g, '') || 'live', false);
        if (location.pathname === '/' ) { history.replaceState({}, '', '/live'); window.dispatchEvent(new PopStateEvent('popstate')); }
        topbarHeight(); window.addEventListener('resize', topbarHeight);
        // the shared 2 s / 10 s window survives a reload
        try { var sw = Number(window.localStorage.getItem('afo.win')); if (sw === 2 || sw === 10) { window._afoWinSec = sw;
            setProps('window-sec', {data: sw}); } } catch (e) { /* no storage */ }
        showWin();
        poll(); setInterval(poll, POLL_MS);
        // while a value is being sent, poll every 100 ms so its confirmation shows at once
        setInterval(function () { if (S.fastUntil && Date.now() < S.fastUntil) { poll(); } }, 100);
        setInterval(function () { if (S.page === 'trials' && !S.exportBusy) { loadRuns(); } }, 3000);
    }
    if (document.readyState === 'loading') { document.addEventListener('DOMContentLoaded', boot); } else { boot(); }
    window._afoConsole = S;
})();
