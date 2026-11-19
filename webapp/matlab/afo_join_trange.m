function [t_first, t_first_any, t_last] = afo_join_trange(s)
%AFO_JOIN_TRANGE Model-time range of an exported run (struct from load()).
%   t_first     earliest sample over all signals
%   t_first_any same as t_first (kept for the split note)
%   t_last      latest sample over all signals
ts = {};
f = fieldnames(s);
for i = 1:numel(f)
    ts = [ts, collect(s.(f{i}))]; %#ok<AGROW>
end
t_first = inf; t_last = -inf;
for i = 1:numel(ts)
    t = ts{i};
    if ~isempty(t)
        t_first = min(t_first, t(1));
        t_last = max(t_last, t(end));
    end
end
t_first_any = t_first;
end

function out = collect(v)
out = {};
if isa(v, 'Simulink.SimulationData.Dataset')
    for i = 1:v.numElements
        e = v.getElement(i);
        if isa(e, 'Simulink.SimulationData.Dataset')
            out = [out, collect(e)]; %#ok<AGROW>
            continue
        end
        try
            out = [out, collect(e.Values)]; %#ok<AGROW>
        catch
        end
    end
elseif isa(v, 'timeseries')
    out = {v.Time(:)};
elseif isstruct(v)
    f = fieldnames(v);
    for i = 1:numel(f)
        out = [out, collect(v.(f{i}))]; %#ok<AGROW>
    end
elseif istimetable(v)
    out = {seconds(v.Properties.RowTimes)};
end
end
