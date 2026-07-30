function out = afo_stream_setup()
%AFO_STREAM_SETUP Attach an instrument that streams every instrumented signal.
%   Binds an slrealtime.Instrument to the application on the target (the
%   instrument must know its application to resolve the instrumented
%   signal set), adds all SDI-badge signals, attaches it, and keeps it in
%   a global for afo_stream_drain. Returns JSON {ok, app} / {ok:false, err}.
global AFO_INST
try
    tg = slrealtime();
    appname = '';
    try, appname = char(getLastApplication(tg)); catch, end
    if isempty(appname)
        error('no application on the target - load/start it first');
    end
    if ~isempty(AFO_INST)
        try, tg.removeInstrument(AFO_INST); catch, end
        try, delete(AFO_INST); catch, end
        AFO_INST = [];
    end
    inst = slrealtime.Instrument(appname);
    inst.AxesTimeSpan = 5;              % keep the host-side buffer bounded
    inst.addInstrumentedSignals();
    % Streaming only delivers data when a callback is connected (signals are
    % streamed "to be available in callback") — register a no-op so the
    % buffer that getBufferedData reads actually fills.
    inst.connectCallback(@(varargin) []);
    tg.addInstrument(inst);
    AFO_INST = inst;
    out = jsonencode(struct('ok', true, 'app', appname));
catch e
    out = jsonencode(struct('ok', false, 'err', e.message));
end
end
