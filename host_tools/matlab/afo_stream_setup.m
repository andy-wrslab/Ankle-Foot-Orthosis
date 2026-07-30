function out = afo_stream_setup()
%AFO_STREAM_SETUP Attach an instrument that streams every instrumented signal.
%   Creates an slrealtime.Instrument, adds all SDI-instrumented (badge)
%   signals, attaches it to the target, and keeps it in a global for
%   afo_stream_drain. Returns JSON {ok} / {ok:false, err}.
global AFO_INST
try
    tg = slrealtime();
    if ~isempty(AFO_INST)
        try, tg.removeInstrument(AFO_INST); catch, end
        try, delete(AFO_INST); catch, end
        AFO_INST = [];
    end
    inst = slrealtime.Instrument();
    inst.AxesTimeSpan = 5;              % keep the host-side buffer bounded
    inst.addInstrumentedSignals();
    tg.addInstrument(inst);
    AFO_INST = inst;
    out = jsonencode(struct('ok', true));
catch e
    out = jsonencode(struct('ok', false, 'err', e.message));
end
end
