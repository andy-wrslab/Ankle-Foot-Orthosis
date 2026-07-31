function out = afo_stream_setup()
%AFO_STREAM_SETUP SDI-run-based streaming (no instrument objects — ever).
%   startRecording streams every instrumented signal into a live SDI run;
%   the console reads that run incrementally. Instrument attach/remove
%   operations have been observed to wedge the app's XCP streaming, so
%   this data plane never creates one. Pins the newest run, precomputes
%   stable unique keys per signal index, and resets read positions.
%   Returns JSON {ok, app, nsignames}.
global AFO_RUNID AFO_LASTT AFO_KEYS AFO_RR
try
    ids = Simulink.sdi.getAllRunIDs;
    if isempty(ids)
        error('no SDI run yet - recording must be active first');
    end
    AFO_RUNID = ids(end);
    r = Simulink.sdi.getRun(AFO_RUNID);
    n = r.SignalCount;
    if n == 0
        error('live SDI run has no signals yet');
    end
    % precompute stable unique display keys (duplicate names exist)
    AFO_KEYS = cell(1, n);
    seen = containers.Map('KeyType', 'char', 'ValueType', 'double');
    for i = 1:n
        key = '';
        try
            sg = r.getSignalByIndex(i);
            key = char(sg.Name);
        catch
        end
        if isempty(key), key = sprintf('sig_%d', i); end
        if isKey(seen, key)
            seen(key) = seen(key) + 1;
            key = sprintf('%s #%d', key, seen(key));
        else
            seen(key) = 1;
        end
        AFO_KEYS{i} = key;
    end
    AFO_LASTT = containers.Map('KeyType', 'char', 'ValueType', 'double');
    AFO_RR = 0;
    out = jsonencode(struct('ok', true, 'app', char(r.Name), 'nsignames', n));
catch e
    out = jsonencode(struct('ok', false, 'err', e.message));
end
end
