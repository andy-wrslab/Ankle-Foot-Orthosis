function afo_stream_cb(src, evt)
%AFO_STREAM_CB Instrument callback: append pushed samples per signal key.
%   The target pushes observer batches over XCP into the Target object,
%   which dispatches them to the long-lived instrument (create-once — see
%   afo_stream_setup), which fires this callback. Each enumerated signal
%   is pulled out of the event with getCallbackDataForSignal and appended
%   as [t data] rows into the AFO_BUF accumulator, which afo_stream_drain
%   consumes ~1x/s. Signals are delivered in groups sharing a sample time,
%   so any one event may carry data for only a subset — absent signals
%   return empty and are skipped. Never raises, never prints: output here
%   would spam the user's shared desktop session.
global AFO_BUF AFO_SIGNAMES AFO_EVTINFO
CAP = 12000;   % rows kept per signal (~12 s of 1 kHz backlog; the server
               % watchdog fires long before a healthy drain falls this far)
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
            if isKey(AFO_BUF, s.key)
                nw = [AFO_BUF(s.key); [t d]];
            else
                nw = [t d];
            end
            if size(nw, 1) > CAP
                nw = nw(end-CAP+1:end, :);
            end
            AFO_BUF(s.key) = nw;
        catch
        end
    end
catch
end
end
