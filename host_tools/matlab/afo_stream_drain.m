function out = afo_stream_drain()
%AFO_STREAM_DRAIN Incrementally read new samples from the live SDI run.
%   Round-robin: reads a slice of ~16 signals per call (sg.Values has a
%   fixed ~20 ms cost per signal, so a full sweep in one call would take
%   seconds); each signal is refreshed every few drains while the stream
%   as a whole never pauses. Returns {ok, signals:[{name,w,t,v}], nkeys,
%   diag}. If a newer run appears (new recording), switches and resets.
global AFO_RUNID AFO_LASTT AFO_KEYS AFO_RR
SLICE = 16;
try
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
catch e
    out = jsonencode(struct('ok', false, 'err', e.message));
end
end
