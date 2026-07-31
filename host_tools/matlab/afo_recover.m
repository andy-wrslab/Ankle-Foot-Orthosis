function out = afo_recover(targetname)
%AFO_RECOVER Recover a wedged live stream without touching the Speedgoat.
%   Proven sequence (2026-07-31 rig session): stale slrealtime.Instrument
%   references poison the Target object's internal registry, which breaks
%   XCP live streaming and even stopRecording/disconnect. Fix: fresh
%   target handle, flush all instruments, cycle the target connection,
%   restart recording. Replaces the base-workspace tg with the healthy
%   handle. Returns JSON {ok} / {ok:false, err}.
try
    tg2 = slrealtime(targetname);
    try, tg2.removeAllInstruments; catch, end
    try, tg2.disconnect; catch, end
    pause(3);
    tg2.connect;
    ok = logical(isConnected(tg2));
    assignin('base', 'tg', tg2);
    try, startRecording(tg2); catch, end    % tolerate already-recording
    out = jsonencode(struct('ok', ok));
catch e
    out = jsonencode(struct('ok', false, 'err', e.message));
end
end
