function out = afo_stream_setup()
%AFO_STREAM_SETUP SDI-run-based streaming (no instrument, no XCP).
%   startRecording streams every instrumented signal into a live SDI run
%   in this MATLAB session; the console reads that run incrementally.
%   This setup verifies the run exists, pins its ID, and resets the
%   per-signal read positions. Returns JSON {ok, app, nsignames}.
global AFO_RUNID AFO_LASTT
try
    ids = Simulink.sdi.getAllRunIDs;
    if isempty(ids)
        error('no SDI run yet - recording must be active first');
    end
    AFO_RUNID = ids(end);
    r = Simulink.sdi.getRun(AFO_RUNID);
    if r.SignalCount == 0
        error('live SDI run has no signals yet');
    end
    AFO_LASTT = containers.Map('KeyType', 'char', 'ValueType', 'double');
    out = jsonencode(struct('ok', true, 'app', char(r.Name), ...
        'nsignames', r.SignalCount));
catch e
    out = jsonencode(struct('ok', false, 'err', e.message));
end
end
