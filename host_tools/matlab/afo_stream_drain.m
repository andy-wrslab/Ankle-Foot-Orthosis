function out = afo_stream_drain()
%AFO_STREAM_DRAIN Return new live samples as JSON {ok, signals, nkeys, diag}.
%   signals: [{name, w, t:[...], v:[row-major flatten of numel(t)-by-w]}].
%   Two planes (chosen by afo_stream_setup):
%     instrument — consume the AFO_BUF push accumulator filled by
%       afo_stream_cb at the full ~1 kHz push rate, decimated here to
%       ~100 Hz for the live view (the full-rate record is the target
%       File Log). O(new samples): cost does not grow with run length.
%     run — incremental sg.Values reads of the live SDI run (fallback;
%       cost grows with run length, bounded by run rotation).
global AFO_MODE
try
    if strcmp(AFO_MODE, 'instrument')
        out = drain_inst();
    else
        out = drain_run();
    end
catch e
    out = jsonencode(struct('ok', false, 'err', e.message));
end
end

function out = drain_inst()
%Consume the push accumulator. Entries are removed as they are read;
%the callback keeps appending concurrently (MATLAB event dispatch is
%serialized with engine evals, so map access never races).
%   HYBRID GUARANTEE: whenever the push buffer yields nothing this call,
%   fall through to the run-polling extraction. A valid-but-silent
%   instrument (callback firing yet extracting nothing — seen live
%   2026-07-31 after hot-deploying v4) must never cost data the SDI run
%   already has. Push simply wins whenever it actually delivers.
global AFO_MODE AFO_INST AFO_BUF AFO_EVTINFO
DECIM = 10;   % ~1 kHz push -> ~100 Hz live view, newest sample always kept
if isempty(AFO_INST) || ~isvalid(AFO_INST)
    % instrument vanished (afo_recover detaches everything) - fall back
    % and make the server re-run setup, which builds a fresh one
    AFO_MODE = 'run';
    out = jsonencode(struct('ok', false, 'err', 'instrument gone - re-setup'));
    return
end
sigs = {};
if ~isempty(AFO_BUF)
    ks = keys(AFO_BUF);
    for i = 1:numel(ks)
        v = AFO_BUF(ks{i});
        remove(AFO_BUF, ks{i});
        if isempty(v) || size(v, 2) < 2, continue; end
        idx = 1:DECIM:size(v, 1);
        if idx(end) ~= size(v, 1)
            idx(end+1) = size(v, 1); %#ok<AGROW>
        end
        t = v(idx, 1);
        d = v(idx, 2:end);
        sigs{end+1} = struct('name', ks{i}, 'w', size(d, 2), ...
            't', t(:).', 'v', reshape(d.', 1, [])); %#ok<AGROW>
    end
end
if isempty(sigs)
    % nothing pushed this cycle - poll the live SDI run instead
    if isempty(AFO_EVTINFO)
        why = 'push idle (callback has not fired yet)';
    else
        why = 'push idle (callback fired, nothing extracted)';
    end
    out = drain_run();
    % annotate only empty results: re-encoding data-carrying JSON would
    % turn 1-point arrays into scalars and break the server's parsing
    try
        o = jsondecode(out);
        if isfield(o, 'ok') && o.ok && (~isfield(o, 'nkeys') || o.nkeys == 0)
            o.signals = {};
            o.diag = {[why ' - falling back to run polling']};
            out = jsonencode(o);
        end
    catch
    end
    return
end
out = jsonencode(struct('ok', true, 'signals', {sigs}, ...
    'nkeys', numel(sigs), 'diag', {{}}));
end

function out = drain_run()
%Incrementally read new samples from the live SDI run (fallback plane).
%   Round-robin: reads a slice of ~22 signals per call (sg.Values has a
%   per-signal cost proportional to run length, so a full sweep in one
%   call would take seconds); each signal is refreshed every few drains
%   while the stream as a whole never pauses. If a newer run appears
%   (new recording), asks the server to re-run setup.
global AFO_RUNID AFO_LASTT AFO_KEYS AFO_RR
SLICE = 22;
if isempty(AFO_RUNID)
    out = jsonencode(struct('ok', false, 'err', 'stream not set up'));
    return
end
ids = Simulink.sdi.getAllRunIDs;
if isempty(ids)
    out = jsonencode(struct('ok', true, 'signals', {{}}, 'nkeys', 0, ...
        'diag', {{'no SDI runs'}}));
    return
end
if ids(end) ~= AFO_RUNID
    % a new recording run started - re-pin via setup (keys may differ)
    out = jsonencode(struct('ok', false, 'err', 'run changed - re-setup'));
    AFO_RUNID = [];
    return
end
r = Simulink.sdi.getRun(AFO_RUNID);
n = min(r.SignalCount, numel(AFO_KEYS));
sigs = {};
diag = {};
take = min(SLICE, n);
for k = 0:take-1
    i = mod(AFO_RR + k, n) + 1;
    try
        sg = r.getSignalByIndex(i);
        key = AFO_KEYS{i};
        v = sg.Values;
        if isempty(v), continue; end
        t = double(v.Time(:));
        N = numel(t);
        if N == 0, continue; end
        last = -inf;
        if isKey(AFO_LASTT, key), last = AFO_LASTT(key); end
        idx = find(t > last);
        if isempty(idx), continue; end
        % fresh attach to a long run: stream only the recent tail —
        % capped by time (10 s) plus a hard point cap
        tcap = t(idx(end)) - 10;
        idx = idx(t(idx) >= tcap);
        % decimate to ~100 Hz for the live view (the full-rate record is
        % the target file log). Keeps drains small so the sweep stays
        % fast and nothing is ever truncated mid-window.
        lastIdx = idx(end);
        idx = idx(1:10:end);
        if idx(end) ~= lastIdx
            idx(end+1) = lastIdx;      %#ok<AGROW> always deliver the newest sample
        end
        if numel(idx) > 2000
            idx = idx(end-1999:end);
        end
        d = v.Data;
        if ndims(d) == 3
            d = reshape(d, [], N);           % [w x N] view, cheap
            d2 = d(:, idx).';
        elseif size(d, 1) == N
            d2 = d(idx, :);
        elseif size(d, 2) == N
            d2 = d(:, idx).';
        else
            continue
        end
        t2 = t(idx);
        AFO_LASTT(key) = t2(end);
        sigs{end+1} = struct('name', key, 'w', size(d2, 2), ...
            't', t2(:).', 'v', reshape(double(d2).', 1, [])); %#ok<AGROW>
    catch
    end
end
AFO_RR = mod(AFO_RR + take, n);
if isempty(sigs)
    diag{end+1} = 'no new samples in the live SDI run';
end
out = jsonencode(struct('ok', true, 'signals', {sigs}, ...
    'nkeys', numel(sigs), 'diag', {diag}));
end
