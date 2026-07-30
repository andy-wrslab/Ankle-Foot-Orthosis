function out = afo_stream_setup()
%AFO_STREAM_SETUP Attach an instrument that streams every instrumented signal.
%   Binds an slrealtime.Instrument to the application on the target, adds
%   all SDI-badge signals, connects afo_stream_cb (which accumulates data
%   into global AFO_BUF), and enumerates the signal set (block path, port,
%   name) from the live SDI recording run. Returns JSON
%   {ok, app, nsignames, notes} / {ok:false, err}.
global AFO_INST AFO_BUF AFO_SIGNAMES AFO_EVTINFO
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
    AFO_BUF = containers.Map('KeyType', 'char', 'ValueType', 'any');
    AFO_SIGNAMES = struct('bp', {}, 'pi', {}, 'nm', {});
    AFO_EVTINFO = '';

    inst = slrealtime.Instrument(appname);
    inst.AxesTimeSpan = 5;
    % capture instrumentation warnings (e.g. fixed-point skips) instead of
    % printing them into the shared MATLAB session
    wtxt = evalc('inst.addInstrumentedSignals();');
    inst.connectCallback(@afo_stream_cb);
    tg.addInstrument(inst);
    AFO_INST = inst;

    % enumerate the instrumented signals (block path + port + display name)
    % from the live SDI run created by startRecording
    try
        ids = Simulink.sdi.getAllRunIDs;
        if ~isempty(ids)
            r = Simulink.sdi.getRun(ids(end));
            for i = 1:r.SignalCount
                try
                    sg = r.getSignalByIndex(i);
                    AFO_SIGNAMES(end+1) = struct( ...
                        'bp', char(sg.BlockPath), ...
                        'pi', double(sg.PortIndex), ...
                        'nm', char(sg.Name)); %#ok<AGROW>
                catch
                end
            end
        end
    catch
    end

    out = jsonencode(struct('ok', true, 'app', appname, ...
        'nsignames', numel(AFO_SIGNAMES), 'notes', strtrim(wtxt)));
catch e
    out = jsonencode(struct('ok', false, 'err', e.message));
end
end
