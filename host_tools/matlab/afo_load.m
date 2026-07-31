function out = afo_load()
%AFO_LOAD Load the application installed on the target (single-app rig).
%   No local .mldatx needed: the app already lives on the Speedgoat (it is
%   the startup app), so LOAD asks the target for its installed
%   applications and loads the only one. With several installed it falls
%   back to the target's last application if that is among them, otherwise
%   it refuses with the list. Returns JSON {ok, app} / {ok:false, err}.
try
    tg = slrealtime();
    if ~logical(isConnected(tg))
        error('target not connected');
    end
    if logical(isRunning(tg))
        error('model is running - stop it before loading');
    end
    apps = getInstalledApplications(tg);
    apps = cellstr(apps);
    apps = apps(~cellfun(@isempty, apps));
    if isempty(apps)
        error('no application installed on the target');
    end
    if numel(apps) == 1
        name = apps{1};
    else
        name = '';
        try, name = char(getLastApplication(tg)); catch, end
        if isempty(name) || ~any(strcmp(apps, name))
            error('multiple applications installed: %s', strjoin(apps, ', '));
        end
    end
    tg.load(name);
    out = jsonencode(struct('ok', true, 'app', name));
catch e
    out = jsonencode(struct('ok', false, 'err', e.message));
end
end
