function out = afo_load_gp(matpath)
%AFO_LOAD_GP Load the subject GP ensemble the Simulink model requires.
%   The model expects ensembleModels plus the scaling parameters mu_X,
%   sigma_X, mu_y, sigma_y in the base workspace, and a codegen-compatible
%   learner file 'ensembleModels.mat' (saveLearnerForCoder of
%   ensembleModels{1}) written next to the source MAT-file. The console
%   runs this on every CONNECT, before touching the target, so any model
%   load or parameter path finds them. Subject is selected by the MAT-file
%   path (server --gp-mat). Idempotent, quiet. Returns JSON
%   {ok, file} / {ok:false, err}.
try
    if nargin < 1 || isempty(matpath)
        error('no GP mat file configured');
    end
    if ~exist(matpath, 'file')
        error('GP mat file not found: %s', matpath);
    end
    S = load(matpath, 'ensembleModels', 'mu_X', 'sigma_X', 'mu_y', 'sigma_y');
    req = {'ensembleModels', 'mu_X', 'sigma_X', 'mu_y', 'sigma_y'};
    for i = 1:numel(req)
        if ~isfield(S, req{i})
            error('%s missing from %s', req{i}, matpath);
        end
        assignin('base', req{i}, S.(req{i}));
    end
    % codegen-compatible learner next to the source file (matches the
    % manual load_model_simulink workflow run from that folder)
    d = fileparts(matpath);
    saveLearnerForCoder(S.ensembleModels{1}, fullfile(d, 'ensembleModels'));
    out = jsonencode(struct('ok', true, 'file', matpath));
catch e
    out = jsonencode(struct('ok', false, 'err', e.message));
end
end
