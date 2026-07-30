function out = afo_stream_drain()
%AFO_STREAM_DRAIN Consume the AFO_BUF accumulator and return it as JSON.
%   Returns {ok, signals:[{name, w, t:[...], v:[...]}], nkeys, diag} where
%   v is the row-major flattening of an numel(t)-by-w matrix (w>1 for
%   vector signals, which the console expands into per-element channels).
%   Entries are removed as they are read (the callback keeps appending).
%   When nothing has accumulated, diag explains why (callback not fired /
%   event info) so the console event log shows the state.
global AFO_INST AFO_BUF AFO_EVTINFO
try
    if isempty(AFO_INST) || ~isvalid(AFO_INST)
        out = jsonencode(struct('ok', false, 'err', 'stream not set up'));
        return
    end
    sigs = {};
    diag = {};
    if ~isempty(AFO_BUF)
        ks = keys(AFO_BUF);
        for i = 1:numel(ks)
            v = AFO_BUF(ks{i});
            remove(AFO_BUF, ks{i});
            if isempty(v) || size(v, 2) < 2, continue; end
            t = v(:, 1);
            dat = v(:, 2:end);
            sigs{end+1} = struct('name', ks{i}, 'w', size(dat, 2), ...
                't', t(:).', 'v', reshape(dat.', 1, [])); %#ok<AGROW>
        end
    end
    if isempty(sigs)
        if isempty(AFO_EVTINFO)
            diag{end+1} = 'instrument callback has not fired yet';
        else
            diag{end+1} = ['callback fired but no signal data matched · evt ' AFO_EVTINFO];
        end
    end
    out = jsonencode(struct('ok', true, 'signals', {sigs}, ...
        'nkeys', numel(sigs), 'diag', {diag}));
catch e
    out = jsonencode(struct('ok', false, 'err', e.message));
end
end
