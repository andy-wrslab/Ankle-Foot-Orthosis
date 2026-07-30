function out = afo_record_import(outdir)
%AFO_RECORD_IMPORT Import the newest file-log run and export a wide CSV.
%   Imports target file logs into SDI, takes the newest run, synchronizes
%   all signals onto one time grid (union, linear), expands vector signals
%   into columns name_1..name_w, and writes <outdir>/target_<stamp>.csv.
%   Returns JSON {ok, file, rows, nsignals} / {ok:false, err}.
try
    tg = slrealtime();
    before = Simulink.sdi.getAllRunIDs();
    tg.FileLog.import();
    after = Simulink.sdi.getAllRunIDs();
    new = setdiff(after, before);
    if isempty(new)
        % nothing new — fall back to the most recent existing run
        if isempty(after)
            out = jsonencode(struct('ok', false, 'err', 'no file-log runs available'));
            return
        end
        runID = after(end);
    else
        runID = new(end);
    end
    r = Simulink.sdi.getRun(runID);
    TT = [];
    names = {};
    skipped = {};
    for i = 1:r.SignalCount
        try
            s = r.getSignalByIndex(i);
            tm = s.Values.Time(:);
            dat = s.Values.Data;
            if numel(size(dat)) > 2, dat = reshape(dat, size(dat, 1), []); end
            if size(dat, 1) ~= numel(tm), dat = dat.'; end
            w = size(dat, 2);
            base = matlab.lang.makeValidName(char(s.Name));
            cn = cell(1, w);
            if w == 1
                cn{1} = base;
            else
                for k = 1:w, cn{k} = sprintf('%s_%d', base, k); end
            end
            tt = array2timetable(double(dat), 'RowTimes', seconds(tm), ...
                'VariableNames', cn);
            names = [names, cn]; %#ok<AGROW>
            if isempty(TT)
                TT = tt;
            else
                TT = synchronize(TT, tt, 'union', 'linear');
            end
        catch se
            skipped{end+1} = sprintf('%d:%s', i, se.message); %#ok<AGROW>
        end
    end
    if isempty(TT)
        out = jsonencode(struct('ok', false, 'err', 'no exportable signals in run'));
        return
    end
    T = timetable2table(TT);
    T.Properties.VariableNames{1} = 'time_s';
    T.time_s = seconds(T.time_s);
    stamp = char(datetime('now', 'Format', 'yyyyMMdd_HHmmss'));
    f = fullfile(outdir, ['target_' stamp '.csv']);
    writetable(T, f);
    out = jsonencode(struct('ok', true, 'file', f, 'rows', height(T), ...
        'nsignals', numel(names), 'skipped', {skipped}));
catch e
    out = jsonencode(struct('ok', false, 'err', e.message));
end
end
