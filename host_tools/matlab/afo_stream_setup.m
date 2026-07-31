function out = afo_stream_setup()
%AFO_STREAM_SETUP Establish the live data plane: instrument push first,
%   SDI-run polling as automatic fallback.
%
%   INSTRUMENT DISCIPLINE (hard-won — do not relax): create at most ONE
%   slrealtime.Instrument per MATLAB session and NEVER remove or delete
%   it. Repeated create/remove cycles leave stale references in the
%   Target object's registry and wedge XCP streaming for the whole
%   session (recovery: afo_recover, which detaches everything — after
%   that the old handle is simply orphaned and a fresh instrument is
%   created). A create-once instrument is the supported streaming
%   client: R2024b defaults are StreamingOnly=1, BufferData=0,
%   RemoveOnStop=0, MLObsDropIfBusy=1 — pure push delivery via
%   connectCallback, no UI buffering, surviving model stops. Instruments
%   share the XCP acquire list with recording by reference count, so the
%   push plane coexists with startRecording and with run rotation.
%
%   Both planes are initialized here: signal keys are enumerated from the
%   live SDI run that startRecording creates (stable "name #N" uniquing,
%   identical keys in both modes), so the console's channel set does not
%   change when the mode falls back. Returns JSON
%   {ok, mode:'instrument'|'run', app, nsignames, notes} / {ok:false, err}.
global AFO_MODE AFO_INST AFO_BUF AFO_SIGNAMES AFO_EVTINFO
global AFO_RUNID AFO_LASTT AFO_KEYS AFO_RR
try
    % ---- enumerate signal names from the live SDI run (needed by both
    % planes: run mode reads it, instrument mode maps bp/port -> key) ----
    ids = Simulink.sdi.getAllRunIDs;
    if isempty(ids)
        error('no SDI run yet - recording must be active first');
    end
    runid = ids(end);
    r = Simulink.sdi.getRun(runid);
    n = r.SignalCount;
    if n == 0
        error('live SDI run has no signals yet');
    end
    keys_ = cell(1, n);
    signames = struct('bp', {}, 'pi', {}, 'key', {});
    seen = containers.Map('KeyType', 'char', 'ValueType', 'double');
    for i = 1:n
        nm = ''; bp = ''; pidx = 1;
        try
            sg = r.getSignalByIndex(i);
            nm = char(sg.Name);
            bp = char(sg.BlockPath);
            pidx = double(sg.PortIndex);
        catch
        end
        if isempty(nm), nm = sprintf('sig_%d', i); end
        if isKey(seen, nm)
            seen(nm) = seen(nm) + 1;
            key = sprintf('%s #%d', nm, seen(nm));
        else
            seen(nm) = 1;
            key = nm;
        end
        keys_{i} = key;
        if ~isempty(bp)
            signames(end+1) = struct('bp', bp, 'pi', pidx, 'key', key); %#ok<AGROW>
        end
    end

    % ---- run-polling plane: always primed (it is also the fallback) ----
    AFO_RUNID = runid;
    AFO_KEYS = keys_;
    AFO_LASTT = containers.Map('KeyType', 'char', 'ValueType', 'double');
    AFO_RR = 0;

    % ---- instrument plane: create once, reuse forever ----
    notes = '';
    mode = 'run';
    try
        tg = slrealtime();
        appname = '';
        try, appname = char(getLastApplication(tg)); catch, end
        if isempty(appname)
            error('no application on the target');
        end
        attached = false;
        if ~isempty(AFO_INST) && isvalid(AFO_INST)
            try
                hh = tg.getAllInstruments();
                for k = 1:numel(hh)
                    if hh(k) == AFO_INST, attached = true; break; end
                end
            catch
            end
        end
        if ~attached
            % any previous handle is orphaned, never deleted: delete() is
            % what poisons the target registry
            inst = slrealtime.Instrument(appname);
            % capture instrumentation warnings (e.g. fixed-point skips)
            % instead of printing them into the shared session
            notes = evalc('inst.addInstrumentedSignals();');
            inst.connectCallback(@afo_stream_cb);
            tg.addInstrument(inst);
            AFO_INST = inst;
        end
        if isempty(AFO_BUF)
            AFO_BUF = containers.Map('KeyType', 'char', 'ValueType', 'any');
        end
        AFO_SIGNAMES = signames;
        AFO_EVTINFO = '';
        mode = 'instrument';
    catch instErr
        notes = ['instrument plane unavailable - polling the SDI run instead: ' ...
                 instErr.message];
    end
    AFO_MODE = mode;
    out = jsonencode(struct('ok', true, 'mode', mode, 'app', char(r.Name), ...
        'nsignames', n, 'notes', strtrim(notes)));
catch e
    out = jsonencode(struct('ok', false, 'err', e.message));
end
end
