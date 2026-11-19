function [joined, info] = afo_join_runs(parts)
%AFO_JOIN_RUNS Join consecutive file-log runs of ONE app session in time.
%   parts: cell array of exported runs, oldest first. Each is the struct that
%   load() returns for a Simulink.sdi.exportRun file (usually one Dataset
%   variable, possibly with nested Datasets). Leaf signals are matched by
%   name + block path + port wherever they sit in the nesting (group names
%   differ between runs) and concatenated in time; the first part's
%   structure is kept and signals only present in later parts are appended.
%   info.split_t: model time where each later part starts (one per split).
%   Which runs belong together is decided by afo_rc('save') from model time.
joined = parts{1};
info = struct('n_parts', numel(parts), 'split_t', [], 'vars', {fieldnames(joined)'}, 'unmatched', 0);
for k = 2:numel(parts)
    [~, t0] = afo_join_trange(parts{k});
    info.split_t(end+1) = t0;
    vars = fieldnames(parts{k});
    for v = 1:numel(vars)
        name = vars{v};
        if isfield(joined, name)
            [joined.(name), n] = join_value(joined.(name), parts{k}.(name));
            info.unmatched = info.unmatched + n;
        else
            joined.(name) = parts{k}.(name);
        end
    end
end
end

function [a, nUnmatched] = join_value(a, b)
nUnmatched = 0;
if isa(a, 'Simulink.SimulationData.Dataset') && isa(b, 'Simulink.SimulationData.Dataset')
    leaves = containers.Map();
    order = {};
    [leaves, order] = flatten(b, leaves, order);
    used = containers.Map();
    a = walk(a, leaves, used);
    for i = 1:numel(order)              % signals that only exist in the later part
        if ~isKey(used, order{i})
            a = a.addElement(leaves(order{i}));
            nUnmatched = nUnmatched + 1;
        end
    end
elseif isa(a, 'timeseries') && isa(b, 'timeseries')
    a = join_ts(a, b);
elseif isstruct(a) && isstruct(b)
    f = fieldnames(b);
    for i = 1:numel(f)
        if isfield(a, f{i})
            a.(f{i}) = join_value(a.(f{i}), b.(f{i}));
        else
            a.(f{i}) = b.(f{i});
        end
    end
elseif istimetable(a) && istimetable(b)
    a = [a; b];
end
% anything else (scalars, metadata): keep the first part's value
end

function [leaves, order] = flatten(ds, leaves, order)
for i = 1:ds.numElements
    e = ds.getElement(i);
    if isa(e, 'Simulink.SimulationData.Dataset')
        [leaves, order] = flatten(e, leaves, order);
    else
        k = leaf_key(e);
        if ~isKey(leaves, k)
            leaves(k) = e;
            order{end+1} = k; %#ok<AGROW>
        end
    end
end
end

function ds = walk(ds, leaves, used)
for i = 1:ds.numElements
    e = ds.getElement(i);
    if isa(e, 'Simulink.SimulationData.Dataset')
        ds = ds.setElement(i, walk(e, leaves, used));
    else
        k = leaf_key(e);
        if isKey(leaves, k) && ~isKey(used, k)
            eb = leaves(k);
            try
                e.Values = join_value(e.Values, eb.Values);
                ds = ds.setElement(i, e);
                used(k) = true; %#ok<NASGU> (handle object)
            catch
            end
        end
    end
end
end

function k = leaf_key(e)
nm = ''; bp = ''; port = '';
try, nm = char(e.Name); catch, end
try, bp = strjoin(cellstr(e.BlockPath.convertToCell()), '/'); catch, end
try, port = num2str(e.PortIndex); catch, end
k = [nm '|' bp '|' port];
end

function c = join_ts(a, b)
ta = a.Time(:); tb = b.Time(:);
da = a.Data; db = b.Data;
if a.IsTimeFirst
    d = cat(1, da, db);
else
    d = cat(ndims(da), da, db);
end
t = [ta; tb];
[t, order] = sort(t);            % stable; keeps a monotonic time vector
idx = repmat({':'}, 1, ndims(d));
if a.IsTimeFirst, idx{1} = order; else, idx{end} = order; end
d = d(idx{:});
c = timeseries(d, t, 'Name', a.Name);
c.DataInfo = a.DataInfo;
try, c.TimeInfo.Units = a.TimeInfo.Units; catch, end
end
