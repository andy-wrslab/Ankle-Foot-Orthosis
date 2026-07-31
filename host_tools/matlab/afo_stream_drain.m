function out = afo_stream_drain()
%AFO_STREAM_DRAIN Return new live samples as JSON {ok, signals, nkeys, diag}.
%   signals: [{name, w, t:[...], v:[row-major flatten of numel(t)-by-w]}].
%   Two planes (chosen by afo_stream_setup):
%     instrument — consume the AFO_BUF push accumulator at the FULL push
%       rate (~1 kHz; the browser decimates for drawing, the host CSV
%       records everything). Signals the instrument cannot stream (not in
%       the event map — e.g. fixed-point skips) are polled from the live
%       SDI run on a slow stride so no channel ever goes stale. O(new
%       samples) for pushed signals regardless of run length.
%     run — incremental sg.Values polling of the live SDI run (fallback;
%       cost grows with run length on trial-aligned runs).
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
%Consume the push accumulator; poll only what push cannot deliver.
global AFO_MODE AFO_INST AFO_BUF AFO_EVTINFO AFO_RUNID AFO_KEYS
global AFO_PUSHSEEN AFO_MISSTICK
if isempty(AFO_INST) || ~isvalid(AFO_INST)
    % instrument vanished (afo_recover detaches everything) - fall back
    % and make the server re-run setup, which builds a fresh one
    AFO_MODE = 'run';
    out = jsonencode(struct('ok', false, 'err', 'instrument gone - re-setup'));
    return
end
% a new run means a new trial (or recovery): re-pin so the missing-signal
% polling and key map follow it. Push rows survive in AFO_BUF meanwhile.
ids = Simulink.sdi.getAllRunIDs;
if ~isempty(ids) && ~isempty(AFO_RUNID) && ids(end) ~= AFO_RUNID
    AFO_RUNID = [];
    out = jsonencode(struct('ok', false, 'err', 'run changed - re-setup'));
    return
end
if ~isa(AFO_PUSHSEEN, 'containers.Map')
    AFO_PUSHSEEN = containers.Map('KeyType', 'char', 'ValueType', 'logical');
end
sigs = {};
if isa(AFO_BUF, 'containers.Map') && AFO_BUF.Count > 0
    ks = keys(AFO_BUF);
    for i = 1:numel(ks)
        v = AFO_BUF(ks{i});
        remove(AFO_BUF, ks{i});
        if isempty(v) || size(v, 2) < 2, continue; end
        AFO_PUSHSEEN(ks{i}) = true;
        sigs{end+1} = pack_sig(ks{i}, v(:, 1), v(:, 2:end)); %#ok<AGROW>
    end
end
% every 5th drain, poll signals push has never delivered (slow stride:
% their Values cost grows with run length on trial-aligned runs)
if isempty(AFO_MISSTICK), AFO_MISSTICK = 0; end
AFO_MISSTICK = AFO_MISSTICK + 1;
if ~isempty(sigs) && mod(AFO_MISSTICK, 5) == 0 && ~isempty(AFO_RUNID)
    try
        r = Simulink.sdi.getRun(AFO_RUNID);
        n = min(r.SignalCount, numel(AFO_KEYS));
        for i = 1:n
            key = AFO_KEYS{i};
            if isKey(AFO_PUSHSEEN, key), continue; end
            s = pull_run_signal(r, i, key, 10);
            if ~isempty(s), sigs{end+1} = s; end %#ok<AGROW>
        end
    catch
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
    s = pull_run_signal(r, i, AFO_KEYS{i}, 10);
    if ~isempty(s), sigs{end+1} = s; end %#ok<AGROW>
end
AFO_RR = mod(AFO_RR + take, n);
if isempty(sigs)
    diag{end+1} = 'no new samples in the live SDI run';
end
out = jsonencode(struct('ok', true, 'signals', {sigs}, ...
    'nkeys', numel(sigs), 'diag', {diag}));
end

function s = pull_run_signal(r, i, key, DEC)
%Extract new samples for run-signal index i (shared by both planes).
%   Incremental past AFO_LASTT(key); 10 s time cap on fresh attach;
%   decimation by DEC for the live view; newest sample always delivered.
global AFO_LASTT
s = [];
try
    sg = r.getSignalByIndex(i);
    v = sg.Values;
    if isempty(v), return; end
    t = double(v.Time(:));
    Npt = numel(t);
    if Npt == 0, return; end
    last = -inf;
    if isKey(AFO_LASTT, key), last = AFO_LASTT(key); end
    idx = find(t > last);
    if isempty(idx), return; end
    tcap = t(idx(end)) - 10;
    idx = idx(t(idx) >= tcap);
    lastIdx = idx(end);
    idx = idx(1:DEC:end);
    if idx(end) ~= lastIdx
        idx(end+1) = lastIdx; %#ok<AGROW>
    end
    if numel(idx) > 2000
        idx = idx(end-1999:end);
    end
    d = v.Data;
    if ndims(d) == 3
        d = reshape(d, [], Npt);             % [w x N] view, cheap
        d2 = d(:, idx).';
    elseif size(d, 1) == Npt
        d2 = d(idx, :);
    elseif size(d, 2) == Npt
        d2 = d(:, idx).';
    else
        return
    end
    t2 = t(idx);
    AFO_LASTT(key) = t2(end);
    s = pack_sig(key, t2, double(d2));
catch
    s = [];
end
end

function s = pack_sig(name, t, d)
%Binary-packed signal: t as float64, values as float32 (row-major
%[numel(t) x w] flattening), both base64 inside the JSON envelope —
%roughly 3x smaller and an order of magnitude cheaper to parse than
%JSON numeric arrays at the full 1 kHz rate.
s = struct('name', name, 'w', size(d, 2), 'n', numel(t), ...
    'tb', matlab.net.base64encode(typecast(double(t(:).'), 'uint8')), ...
    'vb', matlab.net.base64encode(typecast(single(reshape(d.', 1, [])), 'uint8')));
end
