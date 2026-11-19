function out = afo_rc(action, varargin)
%AFO_RC Run-control helper for the AFO web app. Every call returns JSON.
%   afo_rc('status')                 connection, app, run state, TET, EtherCAT, file log
%   afo_rc('connect') / ('disconnect')
%   afo_rc('start') / ('stop')       stop/start verify the new state by polling
%   afo_rc('load', appNameOrMldatx)  only when the app is stopped
%   afo_rc('save', outFile)          import the target file log, export newest run to outFile
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
            % fall back to all runs of the app if this release has no list API
            scope = 'newest';
            try
                L = list(tg.FileLog);
                if istable(L) && height(L) > 0
                    import(tg.FileLog, L(end, :));
                else
                    error('empty list');
                end
            catch
                scope = 'all runs (list API unavailable)';
                tg.FileLog.import(appName);
            end
            after = Simulink.sdi.getAllRunIDs();
            new = setdiff(after, before);
            if isempty(new), error('file log import produced no new SDI run'); end
            runID = new(end);
            Simulink.sdi.exportRun(runID, 'to', 'file', 'filename', outFile);
            d = dir(outFile);
            out = jsonencode(struct('ok', true, 'file', outFile, 'bytes', d.bytes, 'runID', runID, 'scope', scope));
        otherwise
            error('unknown action %s', action);
    end
catch e
    loc = '';
    if ~isempty(e.stack), loc = sprintf(' @ %s:%d', e.stack(1).name, e.stack(1).line); end
    out = jsonencode(struct('ok', false, 'err', [e.message loc]));
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
