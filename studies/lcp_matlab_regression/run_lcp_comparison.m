% Script to run LCP model comparison against baseline
addpath('workspace');

% Define the 5 test cases
test_cases = struct();
test_cases(1).name = 'case_1_high_we_low_bo';
test_cases(1).We = 50;
test_cases(1).Bo = 0.01;
test_cases(1).Oh = 0.005;

test_cases(2).name = 'case_2_mid_we_mid_bo';
test_cases(2).We = 10;
test_cases(2).Bo = 0.1;
test_cases(2).Oh = 0.01;

test_cases(3).name = 'case_3_low_we_high_bo';
test_cases(3).We = 2;
test_cases(3).Bo = 1;
test_cases(3).Oh = 0.002;

test_cases(4).name = 'case_4_viscous_regime';
test_cases(4).We = 5;
test_cases(4).Bo = 0.1;
test_cases(4).Oh = 0.1;

test_cases(5).name = 'case_5_edge_case_contact';
test_cases(5).We = 20;
test_cases(5).Bo = 0.05;
test_cases(5).Oh = 0.005;

% Run LCP model on all test cases
results_lcp = struct();

for i = 1:length(test_cases)
    case_name = test_cases(i).name;
    fprintf('Running LCP model for %s...\n', case_name);

    params = struct();
    params.We = test_cases(i).We;
    params.Bo = test_cases(i).Bo;
    params.Oh = test_cases(i).Oh;
    params.L = 20;
    params.n_steps = 100;

    try
        result = lcp_model(params);
        results_lcp.(case_name) = result;
        fprintf('  OK - contact_radius=%.6f\n', result.contact_radius);
    catch ME
        fprintf('  ERROR: %s\n', ME.message);
        results_lcp.(case_name) = [];
    end
end

% Save results
save('workspace/lcp_results.mat', 'results_lcp');
fprintf('LCP results saved to workspace/lcp_results.mat\n');

% Compare with baseline
baseline = jsondecode(fileread('workspace/baseline_results.json'));

fprintf('\n=== COMPARISON RESULTS ===\n\n');

comparison_table = table();

for i = 1:length(test_cases)
    case_name = test_cases(i).name;
    fprintf('Case %d: %s\n', i, case_name);

    if ~isempty(results_lcp.(case_name))
        lcp_result = results_lcp.(case_name);
        baseline_result = baseline.(case_name);

        % Contact radius error (absolute)
        r_lcp = lcp_result.contact_radius;
        r_base = baseline_result.contact_radius;
        r_err_abs = abs(r_lcp - r_base);
        r_err_rel = r_err_abs / abs(r_base) * 100;  % percent

        % h trajectory final value
        h_lcp_final = lcp_result.h(end);
        h_base_final = baseline_result.h(end);
        h_err_rel = abs(h_lcp_final - h_base_final) / abs(h_base_final) * 100;  % percent

        % v trajectory final value
        v_lcp_final = lcp_result.v(end);
        v_base_final = baseline_result.v(end);
        v_err_rel = abs(v_lcp_final - v_base_final) / abs(v_base_final) * 100;  % percent

        fprintf('  contact_radius: LCP=%.6f, baseline=%.6f, abs_err=%.6e, rel_err=%.4f%%\n', ...
                r_lcp, r_base, r_err_abs, r_err_rel);
        fprintf('  h(final):       LCP=%.6f, baseline=%.6f, rel_err=%.4f%%\n', ...
                h_lcp_final, h_base_final, h_err_rel);
        fprintf('  v(final):       LCP=%.6f, baseline=%.6f, rel_err=%.4f%%\n', ...
                v_lcp_final, v_base_final, v_err_rel);

        % Pass/fail
        r_tol = 0.0001;  % 0.01% relative tolerance for radius
        h_tol = 1.0;     % 1% relative tolerance for h
        v_tol = 1.0;     % 1% relative tolerance for v

        pass_r = r_err_rel < r_tol;
        pass_h = h_err_rel < h_tol;
        pass_v = v_err_rel < v_tol;
        pass_all = pass_r && pass_h && pass_v;

        fprintf('  PASS/FAIL: r=%d h=%d v=%d | OVERALL=%d\n\n', pass_r, pass_h, pass_v, pass_all);

        % Add to table
        new_row = table(i, test_cases(i).We, test_cases(i).Bo, test_cases(i).Oh, ...
                        r_err_abs, r_err_rel, h_err_rel, v_err_rel, ...
                        pass_r, pass_h, pass_v, pass_all, ...
                        'VariableNames', {'Case', 'We', 'Bo', 'Oh', ...
                                         'radius_err_abs', 'radius_err_pct', ...
                                         'h_err_pct', 'v_err_pct', ...
                                         'pass_r', 'pass_h', 'pass_v', 'pass_all'});
        if i == 1
            comparison_table = new_row;
        else
            comparison_table = [comparison_table; new_row];
        end
    else
        fprintf('  FAILED - no result\n\n');
    end
end

% Save comparison table
save('workspace/comparison_table.mat', 'comparison_table');
writetable(comparison_table, 'workspace/comparison_results.csv');
fprintf('\nComparison results saved to workspace/comparison_results.csv\n');

% Print final summary
fprintf('\n=== SUMMARY ===\n');
disp(comparison_table);
