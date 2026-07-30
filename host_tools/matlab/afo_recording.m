function out = afo_recording(action)
%AFO_RECORDING Start/stop target SDI + File Log recording, tolerantly.
%   afo_recording('start') / afo_recording('stop'). Already-started /
%   already-stopped states count as success (state:'already') and no
%   error is ever printed into the shared MATLAB session.
try
    tg = slrealtime();
    if strcmp(action, 'start')
        try
            startRecording(tg);
            out = jsonencode(struct('ok', true, 'state', 'started'));
        catch e
            if contains(e.message, 'Recording is started')
                out = jsonencode(struct('ok', true, 'state', 'already'));
            else
                out = jsonencode(struct('ok', false, 'err', e.message));
            end
        end
    else
        try
            stopRecording(tg);
            out = jsonencode(struct('ok', true, 'state', 'stopped'));
        catch e
            if contains(e.message, 'Recording is stopped') || contains(e.message, 'not started')
                out = jsonencode(struct('ok', true, 'state', 'already'));
            else
                out = jsonencode(struct('ok', false, 'err', e.message));
            end
        end
    end
catch e
    out = jsonencode(struct('ok', false, 'err', e.message));
end
end
