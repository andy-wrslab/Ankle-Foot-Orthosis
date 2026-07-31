function afo_stream_cb(src, evt) %#ok<INUSL>
%AFO_STREAM_CB Instrument callback: map-driven extraction of pushed samples.
%   Each AcquireGroupDataEvent carries data for ONE acquire group:
%   evt.AcquireGroupData is a struct array (one element per group) with
%   Time [n x 1] and Data {1 x nsig}; evt.Map is a containers.Map from
%   'blockpath:port' to int32 [groupIndex dataIndex]. We walk the map
%   once, keep entries whose group has samples this event and whose key
%   is one of ours (AFO_KEYMAP, built by afo_stream_setup), and append
%   [t data] rows into the AFO_BUF accumulator that afo_stream_drain
%   consumes. This replaces getCallbackDataForSignal, which returned
%   empty for signals outside the event's group and proved unreliable
%   for per-signal queries (live finding 2026-07-31). Never raises,
%   never prints — output here would spam the MATLAB session.
global AFO_BUF AFO_KEYMAP AFO_EVTINFO
CAP = 12000;   % rows kept per signal (~12 s of 1 kHz backlog; the server
               % watchdog fires long before a healthy drain falls this far)
try
    if isempty(AFO_EVTINFO)
        try
            AFO_EVTINFO = class(evt);
        catch
        end
    end
    % NOTE: isempty() on a containers.Map means "zero entries", so an
    % empty-but-valid buffer would bail out here forever — this exact gate
    % (isempty(AFO_BUF)) is why the 2026-07-30 instrument callback never
    % accumulated anything. Check the class, not emptiness.
    if ~isa(AFO_BUF, 'containers.Map') || ~isa(AFO_KEYMAP, 'containers.Map')
        return
    end
    m = evt.Map;
    gAll = evt.AcquireGroupData;
    ks = keys(m);
    for i = 1:numel(ks)
        try
            k = ks{i};
            if ~isKey(AFO_KEYMAP, k), continue; end
            gi = m(k);                      % int32 [group, dataIdx]
            g = gAll(double(gi(1)));
            t = double(g.Time(:));
            if isempty(t), continue; end    % this event served another group
            d = double(g.Data{double(gi(2))});
            if size(d, 1) ~= numel(t), d = d.'; end
            if size(d, 1) ~= numel(t), continue; end
            key = AFO_KEYMAP(k);
            if isKey(AFO_BUF, key)
                nw = [AFO_BUF(key); [t d]];
            else
                nw = [t d];
            end
            if size(nw, 1) > CAP
                nw = nw(end-CAP+1:end, :);
            end
            AFO_BUF(key) = nw;
        catch
        end
    end
catch
end
end
