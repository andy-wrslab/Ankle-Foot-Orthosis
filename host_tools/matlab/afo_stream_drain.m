function out = afo_stream_drain()
%AFO_STREAM_DRAIN Incrementally read new samples from the live SDI run.
%   Returns {ok, signals:[{name, w, t:[...], v:[...]}], nkeys, diag}: v is
%   the row-major flattening of numel(t)-by-w data (w>1 = vector signal,
%   expanded into per-element channels by the console). Tracks per-signal
%   read position in AFO_LASTT; if a newer run appears (new recording),
%   switches to it and resets. Never raises into the shared session.
global AFO_RUNID AFO_LASTT
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
        AFO_RUNID = ids(end);       % a new recording run started
        AFO_LASTT = containers.Map('KeyType', 'char', 'ValueType', 'double');
    end
    r = Simulink.sdi.getRun(AFO_RUNID);
    sigs = {};
    diag = {};
    seen = containers.Map('KeyType', 'char', 'ValueType', 'double');
    for i = 1:r.SignalCount
        try
            sg = r.getSignalByIndex(i);
            key = char(sg.Name);
            if isempty(key), key = sprintf('sig_%d', i); end
            if isKey(seen, key)
                seen(key) = seen(key) + 1;
                key = sprintf('%s #%d', key, seen(key));
            else
                seen(key) = 1;
            end
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
            % capped by time (10 s) so slow/decimated signals don't flood
            % the console with minutes of backfill, plus a hard point cap
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
    if isempty(sigs)
        diag{end+1} = 'no new samples in the live SDI run';
    end
    out = jsonencode(struct('ok', true, 'signals', {sigs}, ...
        'nkeys', numel(sigs), 'diag', {diag}));
catch e
    out = jsonencode(struct('ok', false, 'err', e.message));
end
end
