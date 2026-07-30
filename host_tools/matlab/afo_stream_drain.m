function out = afo_stream_drain()
%AFO_STREAM_DRAIN Read the instrument buffer and return it as JSON.
%   Returns {ok, signals:[{name, w, t:[...], v:[...]}]} where v is the
%   row-major flattening of an numel(t)-by-w matrix (w>1 for vector
%   signals, which the console expands into per-element channels).
%   The buffer is cumulative (AxesTimeSpan-bounded); the console dedups
%   by timestamp, so returning overlapping windows is fine.
global AFO_INST
try
    if isempty(AFO_INST) || ~isvalid(AFO_INST)
        out = jsonencode(struct('ok', false, 'err', 'stream not set up'));
        return
    end
    m = AFO_INST.getBufferedData();
    sigs = {};
    ks = keys(m);
    for i = 1:numel(ks)
        d = m(ks{i});
        t = []; v = [];
        if isstruct(d)
            if isfield(d, 'time'), t = d.time(:); end
            if isfield(d, 'data'), v = d.data; end
        elseif isnumeric(d) && size(d, 2) >= 2
            t = d(:, 1); v = d(:, 2:end);
        end
        if isempty(t) || isempty(v), continue; end
        if size(v, 1) ~= numel(t), v = v.'; end
        if size(v, 1) ~= numel(t), continue; end
        sigs{end+1} = struct('name', ks{i}, 'w', size(v, 2), ...
            't', t(:).', 'v', reshape(v.', 1, [])); %#ok<AGROW>
    end
    out = jsonencode(struct('ok', true, 'signals', {sigs}));
catch e
    out = jsonencode(struct('ok', false, 'err', e.message));
end
end
