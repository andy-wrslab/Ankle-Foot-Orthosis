function out = afo_record_import(outdir)
%AFO_RECORD_IMPORT Import the newest file-log run and export a wide CSV.
%   If the target is reachable, imports its file logs into SDI first;
%   either way, exports the newest SDI run: all signals synchronized onto
%   one time grid (union, linear), vector signals expanded into columns
%   name_1..name_w, written to <outdir>/target_<stamp>.csv.
%   Returns JSON {ok, file, rows, nsignals, imported, skipped} or
%   {ok:false, err} (err includes the failing file:line).
try
    before = Simulink.sdi.getAllRunIDs();
    imported = false;
    import_err = '';
    try
        tg = slrealtime();
        if isConnected(tg)
            tg.FileLog.import();
            imported = true;
        end
    catch ie
        import_err = ie.message;
    end
    after = Simulink.sdi.getAllRunIDs();
    new = setdiff(after, before);
    if ~isempty(new)
        runID = new(end);
    elseif ~isempty(after)
        runID = after(end);      % fall back to the newest existing run
    else
        out = jsonencode(struct('ok', false, 'err', 'no SDI runs available'));
        return
    end
    r = Simulink.sdi.getRun(runID);
    TT = [];
    names = {};
    skipped = {};
    for i = 1:r.SignalCount
        try
            s = r.getSignalByIndex(i);
            v = s.Values;
            tm = double(v.Time(:));
            N = numel(tm);
            dat = v.Data;
            if ndims(dat) == 3
                dat = reshape(dat, [], N).';
            elseif size(dat, 1) ~= N && size(dat, 2) == N
                dat = dat.';
            end
            if size(dat, 1) ~= N, error('shape %s vs %d pts', mat2str(size(v.Data)), N); end
            w = size(dat, 2);
            base = matlab.lang.makeValidName(char(s.Name));
            cn = cell(1, w);
            if w == 1
                cn{1} = base;
            else
                for k = 1:w, cn{k} = sprintf('%s_%d', base, k); end
            end
            % unique the column names (duplicate signal names exist)
            for k = 1:w
                if any(strcmp(names, cn{k}))
                    cn{k} = matlab.lang.makeUniqueStrings(cn{k}, names);
                end
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
        'nsignals', numel(names), 'imported', imported, ...
        'import_err', import_err, 'skipped', {skipped}));
catch e
    loc = '';
    if ~isempty(e.stack)
        loc = sprintf(' @ %s:%d', e.stack(1).name, e.stack(1).line);
    end
    out = jsonencode(struct('ok', false, 'err', [e.message loc]));
end
end
