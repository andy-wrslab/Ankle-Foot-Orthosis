% load_model_simulink  Loads the ensemble GP models and scaling parameters
% from the subject MAT-file in THIS folder, wraps the ensemble, converts it
% to a codegen-compatible model, and assigns everything to the base
% workspace for use by the Simulink model.
%
% This is the manual version of what the console runs automatically on
% every CONNECT (host_tools/matlab/afo_load_gp.m, subject selected by the
% server --gp-mat argument). Both load from the git folder, so no shared
% desktop MATLAB setup is required.
%
% The MAT-file must contain:
%   ensembleModels - cell array of 10 CompactRegressionGP objects.
%   mu_X           - input feature means.
%   sigma_X        - input feature standard deviations.
%   mu_y           - output mean.
%   sigma_y        - output standard deviation.

here = fileparts(mfilename('fullpath'));

modelFilename = fullfile(here, 'best_gp_Haoran_synced_.mat');
% modelFilename = fullfile(here, 'best_gp_Andy_synced_.mat');
% modelFilename = fullfile(here, 'best_gp_Yibo_synced_.mat');

% Load the ensemble models and scaling parameters from the MAT-file.
load(modelFilename, 'ensembleModels', 'mu_X', 'sigma_X', 'mu_y', 'sigma_y');

% Convert into a codegen-compatible model using saveLearnerForCoder.
saveLearnerForCoder(ensembleModels{1}, fullfile(here, 'ensembleModels'));

disp(['finalGP model loaded successfully from ', modelFilename]);
