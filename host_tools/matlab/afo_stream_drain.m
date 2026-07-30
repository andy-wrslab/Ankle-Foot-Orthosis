function out = afo_stream_drain()
%AFO_STREAM_DRAIN Read the instrument buffer and return it as JSON.
%   Returns {ok, signals:[{name, w, t:[...], v:[...]}], nkeys, diag} where
%   v is the row-major flattening of an numel(t)-by-w matrix (w>1 for
%   vector signals). The buffer is cumulative (AxesTimeSpan-bounded); the
%   console dedups by timestamp, so overlapping windows are fine. Any
%   buffer entry whose shape is not recognized is described in diag so the
%   console event log shows exactly what arrived.
global AFO_INST
try
    if isempty(AFO_INST) || ~isvalid(AFO_INST)
        out = jsonencode(struct('ok', false, 'err', 'stream not set up'));
        return
    end
    m = AFO_INST.getBufferedData();
    sigs = {}; diag = {};
    ks = keys(m);
    for i = 1:numel(ks)
        v = m(ks{i});
        [t, dat] = i_extract(v);
        if isempty(t) || isempty(dat)
            if numel(diag) < 4
                diag{end+1} = sprintf('%s -> %s %s', ks{i}, class(v), mat2str(size(v))); %#ok<AGROW>
            end
            continue
        end
        if size(dat, 1) ~= numel(t), dat = dat.'; end
        if size(dat, 1) ~= numel(t), continue; end
        sigs{end+1} = struct('name', ks{i}, 'w', size(dat, 2), ...
            't', t(:).', 'v', reshape(dat.', 1, [])); %#ok<AGROW>
    end
    out = jsonencode(struct('ok', true, 'signals', {sigs}, ...
        'nkeys', numel(ks), 'diag', {diag}));
catch e
    out = jsonencode(struct('ok', false, 'err', e.message));
end
end

function [t, dat] = i_extract(v)
%I_EXTRACT Pull (time, data) out of whatever shape the buffer holds.
t = []; dat = [];
try
    if isstruct(v)
        if numel(v) == 1
            fn = fieldnames(v);
            tf = fn(strcmpi(fn, 'time')); df = fn(strcmpi(fn, 'data'));
            if ~isempty(tf), t = double(v.(tf{1})(:)); end
            if ~isempty(df), dat = double(v.(df{1})); end
        else
            fn = fieldnames(v);
            tf = fn(strcmpi(fn, 'time')); df = fn(strcmpi(fn, 'data'));
            if ~isempty(tf) && ~isempty(df)
                t = arrayfun(@(x) double(x.(tf{1})(1)), v(:));
                dat = cell2mat(arrayfun(@(x) double(x.(df{1})(:)).', v(:), ...
                    'UniformOutput', false));
            end
        end
    elseif isa(v, 'timetable')
        t = seconds(v.Properties.RowTimes); t = t(:);
        dat = double(v{:, :});
    elseif isa(v, 'timeseries')
        t = double(v.Time(:));
        dat = double(v.Data);
        if numel(size(dat)) > 2, dat = reshape(dat, size(dat, 1), []); end
    elseif isnumeric(v) && size(v, 2) >= 2
        t = double(v(:, 1));
        dat = double(v(:, 2:end));
    end
catch
    t = []; dat = [];
end
end
