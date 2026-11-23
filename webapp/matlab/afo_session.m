function out = afo_session(action, varargin)
%AFO_SESSION Read / set session parameters of the loaded AFO app. JSON out.
%   afo_session('read', paths)            paths: cellstr of 'block|param'
%   afo_session('set', block, param, val) setparam, then getparam readback
%   Session parameters are tunable block parameters; every Start reloads the
%   app and resets them to the compiled defaults, so the web app re-applies.
persistent tg   % one Target object for the life of the warm MATLAB worker (not one per call)
try
    if isempty(tg) || ~isvalid(tg)
        tg = slrealtime();
    end
    if ~logical(isConnected(tg)), error('target not connected'); end
    switch lower(action)
        case 'read'
            paths = varargin{1};
            if ischar(paths), paths = {paths}; end
            vals = struct('path', {}, 'value', {}, 'err', {});
            for i = 1:numel(paths)
                parts = strsplit(paths{i}, '|');
                try
                    v = double(getparam(tg, parts{1}, parts{2}));
                    vals(end+1) = struct('path', paths{i}, 'value', v, 'err', ''); %#ok<AGROW>
                catch e
                    vals(end+1) = struct('path', paths{i}, 'value', [], 'err', e.message); %#ok<AGROW>
                end
            end
            out = jsonencode(struct('ok', true, 'values', vals));
        case 'set'
            blk = varargin{1}; prm = varargin{2}; val = double(varargin{3});
            setparam(tg, blk, prm, val);
            rb = double(getparam(tg, blk, prm));
            out = jsonencode(struct('ok', isequal(rb, val), 'readback', rb, 'requested', val));
        otherwise
            error('unknown action %s', action);
    end
catch e
    out = jsonencode(struct('ok', false, 'err', e.message));
end
end
