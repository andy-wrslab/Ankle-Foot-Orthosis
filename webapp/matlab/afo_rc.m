function out = afo_rc(action, varargin)
%AFO_RC Run-control helper for the AFO web app. Every call returns JSON.
%   afo_rc('status')                 connection, app, run state, TET, EtherCAT, file log
%   afo_rc('connect') / ('disconnect')
%   afo_rc('start') / ('stop')       stop/start verify the new state by polling
%   afo_rc('load', appNameOrMldatx)  only when the app is stopped
%   afo_rc('list')                   every run in the target file log (all columns as text/numbers)
%   afo_rc('save', outFile [, app, keyCol, keyVal, join])
%                                    import ONE file-log run (the newest, or the row whose keyCol
%                                    reads keyVal as listed by 'list'; keyCol '#row' = row number)
%                                    and export it to outFile; with join (default true) earlier runs
%                                    of the same app session (model time continues) are joined
%   No torque/assist/motor control lives here.
try
    tg = slrealtime();
    switch lower(action)
        case 'status'
            out = jsonencode(rc_status(tg));
        case 'connect'
            if ~logical(isConnected(tg)), connect(tg); end
            s = rc_status(tg); s.ok = s.connected;
            out = jsonencode(s);
        case 'disconnect'
            if logical(isConnected(tg)), disconnect(tg); end
            out = jsonencode(struct('ok', ~logical(isConnected(tg)), 'connected', logical(isConnected(tg))));
        case 'stop'
            need_connected(tg);
            if ~logical(isRunning(tg))
                out = jsonencode(struct('ok', true, 'state', 'already stopped')); return
            end
            stop(tg);
            ok = wait_for(@() ~logical(isRunning(tg)), 20);
            s = rc_status(tg); s.ok = ok;
            if ~ok, s.err = 'failed to stop: target still reports running after 20 s'; end
            out = jsonencode(s);
        case 'start'
            need_connected(tg);
            if logical(isRunning(tg))
                out = jsonencode(struct('ok', true, 'state', 'already running')); return
            end
            if ~logical(isLoaded(tg))
                % stop() unloads the app on this target: reload the SAME
                % application (the target's last/only installed app) first
                name = '';
                try, name = char(getLastApplication(tg)); catch, end
                if isempty(name)
                    apps = cellstr(getInstalledApplications(tg));
                    apps = apps(~cellfun(@isempty, apps));
                    if numel(apps) == 1, name = apps{1}; end
                end
                if isempty(name), error('no application loaded and no unique last application to reload'); end
                load(tg, name);
            end
            start(tg);
            ok = wait_for(@() logical(isRunning(tg)), 20);
            s = rc_status(tg); s.ok = ok;
            if ~ok, s.err = 'start requested but target does not report running after 20 s'; end
            out = jsonencode(s);
        case 'load'
            need_connected(tg);
            if logical(isRunning(tg)), error('model is running - stop it before loading'); end
            app = varargin{1};
            load(tg, app);
            s = rc_status(tg); s.ok = logical(isLoaded(tg));
            out = jsonencode(s);
        case 'list'
            need_connected(tg);
            L = list(tg.FileLog);
            rows = {};
            cols = {};
            if istable(L)
                cols = L.Properties.VariableNames;
                for i = 1:height(L)
                    r = struct('row', i);
                    for c = 1:numel(cols)
                        r.(matlab.lang.makeValidName(cols{c})) = cellval(L.(cols{c})(i));
                    end
                    rows{end+1} = r; %#ok<AGROW>
                end
            end
            out = jsonencode(struct('ok', true, 'columns', {cols}, 'rows', {rows}, 'n', numel(rows)));
        case 'save'
            outFile = varargin{1};
            if exist(outFile, 'file'), error('refusing to overwrite %s', outFile); end
            before = Simulink.sdi.getAllRunIDs();
            need_connected(tg);
            appName = '';
            if numel(varargin) >= 2, appName = varargin{2}; end
            if isempty(appName)
                try, appName = char(tg.ModelStatus.Application); catch, end
            end
            if isempty(appName)
                try, appName = char(getLastApplication(tg)); catch, end
            end
            if isempty(appName), error('cannot tell which application''s file log to import'); end
            % import only the newest run (a trial), not every log on the target;
            % fall back to all runs of the app if this release has no list API.
            % If a recording restart split this app session into several
            % file-log runs, the earlier runs of the SAME session are joined:
            % a run belongs to the session when model time continues (it
            % ends before the next run starts, within 60 s, and the next run
            % does not start at t = 0, which a new Start would).
            scope = 'newest';
            L = [];
            try
                L = list(tg.FileLog);
                if ~istable(L) || height(L) == 0, error('empty list'); end
            catch
                L = [];
            end
            splits = struct('t_model', {}, 'run_row', {});
            if isempty(L)
                scope = 'all runs (list API unavailable)';
                tg.FileLog.import(appName);
                after = Simulink.sdi.getAllRunIDs();
                new = setdiff(after, before);
                if isempty(new), error('file log import produced no new SDI run'); end
                runIDs = new(end);
                Simulink.sdi.exportRun(runIDs, 'to', 'file', 'filename', outFile);
            else
                appcol = '';
                for c = {'Application', 'ApplicationName', 'App'}
                    if any(strcmp(L.Properties.VariableNames, c{1})), appcol = c{1}; break; end
                end
                sel = height(L);
                if numel(varargin) >= 4 && ~isempty(varargin{3})
                    keyCol = varargin{3}; keyVal = varargin{4};
                    if strcmp(keyCol, '#row')
                        sel = double(keyVal);
                    else
                        sel = [];
                        for i = 1:height(L)
                            if strcmp(string(cellval(L.(keyCol)(i))), string(keyVal)), sel = i; break; end
                        end
                    end
                    if isempty(sel) || sel < 1 || sel > height(L)
                        error('run %s = %s not found in the file log', keyCol, string(keyVal));
                    end
                end
                doJoin = true;
                if numel(varargin) >= 5, doJoin = logical(varargin{5}); end
                [runIDs, parts, rows] = import_rows(tg, L, sel);
                k = sel - 1;
                if ~doJoin, k = 0; end
                while k >= 1 && numel(parts) < 20
                    if ~isempty(appcol) && ~strcmp(string(L.(appcol)(k)), string(L.(appcol)(sel))), break; end
                    [rid, p] = import_rows(tg, L, k);
                    [t0new, ~, ~] = afo_join_trange(parts{1});
                    [~, ~, t1old] = afo_join_trange(p{1});
                    if t0new > 1 && t1old <= t0new && (t0new - t1old) < 60
                        runIDs = [rid, runIDs]; parts = [p, parts]; rows = [k, rows]; %#ok<AGROW>
                        splits(end+1) = struct('t_model', t0new, 'run_row', rows(2)); %#ok<AGROW>
                        k = k - 1;
                    else
                        try, Simulink.sdi.deleteRun(rid); catch, end
                        break
                    end
                end
                if numel(parts) == 1
                    Simulink.sdi.exportRun(runIDs, 'to', 'file', 'filename', outFile);
                else
                    scope = sprintf('newest app session: %d file-log runs joined', numel(parts));
                    [joined, ~] = afo_join_runs(parts);
                    save(outFile, '-struct', 'joined', '-v7.3');
                    splits = fliplr(splits);   % oldest split first
                end
            end
            d = dir(outFile);
            out = jsonencode(struct('ok', true, 'file', outFile, 'bytes', d.bytes, 'runID', runIDs(end), ...
                'runIDs', runIDs, 'n_runs', numel(runIDs), 'splits', splits, 'scope', scope));
        otherwise
            error('unknown action %s', action);
    end
catch e
    loc = '';
    if ~isempty(e.stack), loc = sprintf(' @ %s:%d', e.stack(1).name, e.stack(1).line); end
    out = jsonencode(struct('ok', false, 'err', [e.message loc]));
end
end

function [runIDs, parts, rows] = import_rows(tg, L, k)
% import file-log row k into SDI, export it to a temp file and load it back
before = Simulink.sdi.getAllRunIDs();
import(tg.FileLog, L(k, :));
new = setdiff(Simulink.sdi.getAllRunIDs(), before);
if isempty(new), error('file log import of row %d produced no new SDI run', k); end
runIDs = new(end);
tmp = [tempname '.mat'];
Simulink.sdi.exportRun(runIDs, 'to', 'file', 'filename', tmp);
parts = {load(tmp)};
rows = k;
delete(tmp);
end

function v = cellval(x)
% one table cell as JSON-friendly text/number (same text in 'list' and 'save')
if iscell(x), x = x{1}; end
if isdatetime(x)
    x.Format = 'yyyy-MM-dd HH:mm:ss';
    v = char(x);
elseif isduration(x)
    v = seconds(x);
elseif isnumeric(x) || islogical(x)
    v = double(x);
elseif isstring(x) || ischar(x) || iscategorical(x)
    v = char(string(x));
else
    try, v = char(string(x)); catch, v = class(x); end
end
end

function need_connected(tg)
if ~logical(isConnected(tg)), error('target not connected'); end
end

function ok = wait_for(cond, timeout_s)
t0 = tic; ok = false;
while toc(t0) < timeout_s
    try
        if cond(), ok = true; return; end
    catch
    end
    pause(0.5);
end
end

function s = rc_status(tg)
s = struct('ok', true, 'connected', logical(isConnected(tg)), 'loaded', false, 'running', false, ...
    'app', '', 'state', '', 'exec_time', [], 'tet_avg_us', [], 'tet_max_us', [], ...
    'ethercat_state', [], 'filelog', '', 'target', tg.TargetSettings.address);
if ~s.connected, return; end
try, s.loaded = logical(isLoaded(tg)); catch, end
try, s.running = logical(isRunning(tg)); catch, end
try
    ms = tg.ModelStatus;
    s.app = char(ms.Application);
    s.state = char(ms.State);
    s.exec_time = double(ms.ExecTime);
    if ~isempty(ms.TETInfo)
        s.tet_avg_us = 1e6 * double(ms.TETInfo(1).TETAvg);
        s.tet_max_us = 1e6 * double(ms.TETInfo(1).TETMax);
    end
catch
end
try, s.filelog = char(string(tg.FileLog.LoggingService)); catch, end
if s.running
    try
        s.ethercat_state = double(getsignal(tg, 'AFO/EtherCAT Initialization/EtherCAT Get State', 1));
    catch
    end
end
end
