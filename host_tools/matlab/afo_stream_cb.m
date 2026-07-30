function afo_stream_cb(src, evt)
%AFO_STREAM_CB Instrument callback: pull new samples for every known signal
%   into the global AFO_BUF accumulator ([t data...] rows per signal),
%   drained by afo_stream_drain. Never raises, never prints.
global AFO_BUF AFO_SIGNAMES AFO_EVTINFO
try
    if isempty(AFO_EVTINFO)
        try
            AFO_EVTINFO = sprintf('%s · props: %s', class(evt), strjoin(properties(evt), ','));
        catch
            AFO_EVTINFO = class(evt);
        end
    end
    if isempty(AFO_BUF) || isempty(AFO_SIGNAMES)
        return
    end
    for i = 1:numel(AFO_SIGNAMES)
        s = AFO_SIGNAMES(i);
        try
            [t, d] = getCallbackDataForSignal(src, evt, s.bp, s.pi);
            if isempty(t), continue; end
            t = double(t(:));
            d = double(d);
            if size(d, 1) ~= numel(t), d = d.'; end
            if size(d, 1) ~= numel(t), continue; end
            key = s.nm;
            if isempty(key), key = sprintf('%s:%d', s.bp, s.pi); end
            if isKey(AFO_BUF, key)
                nw = [AFO_BUF(key); [t d]];
            else
                nw = [t d];
            end
            if size(nw, 1) > 20000
                nw = nw(end-20000+1:end, :);
            end
            AFO_BUF(key) = nw;
        catch
        end
    end
catch
end
end
