"""Canonical, CI-verified f3dasm data idioms — the single source of truth.

``F3DASM_CORE_IDIOMS`` is the ONE place these snippets live. The implementer and
datagenerator system prompts compose it in (DRY — no hand-copied API examples to
drift), and ``tests/test_f3dasm_idioms.py`` EXECUTES it against the
installed f3dasm on every CI run. If an f3dasm API moves, that test fails at
build time — agents never receive a broken example, and no runtime introspection
is needed.

Every call here was verified against the installed f3dasm. Do NOT edit by hand
without re-running the test — that is the whole point of this file.
"""

# The runnable core. Lines that need a registered evaluator (get_evaluator) are
# shown as comments — they are correct but cannot execute outside a live run;
# everything else executes in the CI exec-test.
F3DASM_CORE_IDIOMS = '''\
VERIFIED f3dasm DATA IDIOMS (CI-checked against the installed f3dasm —
trust these over any remembered signature):

    from f3dasm import ExperimentData, ExperimentSample, create_sampler
    from f3dasm.design import Domain
    import numpy as np

    # Domain: one add_float per continuous input, one add_output per output.
    domain = Domain()
    for name in ("x1", "x2"):
        domain.add_float(name, -5.0, 5.0)
    domain.add_output("y")

    # Space-filling sample: create_sampler() returns a Block; call it ON an
    # ExperimentData. There is NO data.sample(...) method.
    data = ExperimentData(domain=domain)
    sampler = create_sampler("latin_sampler", seed=0)   # or "random_sampler"
    data = sampler.call(data=data, n_samples=8)

    # Read arrays: to_numpy() takes NO argument and returns (X, y) as a tuple.
    # NOT data.to_numpy("input"). Use X, y = ... (or _, y = ... to discard X).
    X, y = data.to_numpy()
    # to_pandas() returns a (input_df, output_df) TUPLE — NOT a single frame.
    # Unpack it: df_in, df_out = data.to_pandas(). The output_df carries METADATA
    # columns (_delegation_id, _source, _ts, _wall_ms) alongside the outputs, so
    # df_out[col].astype(float) FAILS on those. For analysis / surrogate fitting,
    # always use data.to_numpy() — it strips metadata and returns clean float
    # arrays. Never use df_out[col].astype(float).

    # Wrap proposed candidate points (e.g. from an acquisition function) into
    # evaluatable ExperimentData. There is NO ExperimentData.from_numpy; build
    # ExperimentSamples (kwarg is _input_data, NOT input) then from_data:
    candidates = np.array([[1.0, 2.0], [3.0, -1.0]])
    samples = {
        i: ExperimentSample(
            _input_data={n: float(candidates[i, j])
                         for j, n in enumerate(domain.input_names)})
        for i in range(len(candidates))
    }
    cand_data = ExperimentData.from_data(data=samples, domain=domain)

    # COMPOSITION — how f3dasm runs a MULTI-STAGE experiment. Blocks chain with
    # the >> operator (producing a ChainedBlock) and repeat with .loop(n) (a
    # LoopBlock). A chain is itself a Block, so it composes further, and kwargs
    # given to .call() reach every block in the chain.
    explore = create_sampler("latin_sampler", seed=0)
    refine = create_sampler("random_sampler", seed=1)
    chained = explore >> refine                  # ChainedBlock
    chain_data = chained.call(ExperimentData(domain=domain), n_samples=4)
    repeated = refine.loop(3)                    # LoopBlock — runs it 3 times

    # Pipeline/Step/Loop is the DECLARATIVE form of the same composition. Step
    # wraps one Block with its kwargs; Loop repeats a list of Steps.
    from f3dasm import Loop, Pipeline, Step
    pipeline = Pipeline(name="optimise", steps=[
        Step(block=explore, name="explore", kwargs={"n_samples": 8}),
        Loop(n_iterations=3, steps=[Step(block=repeated, name="refine")]),
    ])
    # pipeline.run() RETURNS A JOB ID (str), NOT data. Read the result back from
    # rootdir/job_id. Defaults: mode="local", rootdir=cwd, project_job=<epoch>.
    #   from pathlib import Path
    #   job_id = pipeline.run(mode="local", project_job="run_001",
    #                         rootdir="{delegation_id}")
    #   result = ExperimentData.from_file(
    #       project_dir=Path("{delegation_id}") / job_id)

    # Evaluate ground truth ONLY through get_evaluator (ledgered w/ provenance):
    #   from adda import get_evaluator
    #   gen = get_evaluator()
    #   data = gen.call(data, mode="sequential")   # or mode="parallel"
    #   gen.flush()
    # After outputs exist, best-N by an output column:
    #   best = data.get_n_best_output(5, "y")   # (n_samples, output_name)

    # sklearn GaussianProcessRegressor: does NOT accept n_jobs (parallelism kwarg).
    # Correct signature — only these kwargs are valid:
    #   from sklearn.gaussian_process import GaussianProcessRegressor
    #   from sklearn.gaussian_process.kernels import Matern
    #   gpr = GaussianProcessRegressor(
    #       kernel=Matern(nu=2.5), n_restarts_optimizer=5, alpha=1e-6,
    #       normalize_y=True, random_state=0,
    #   )
    # WRONG: GaussianProcessRegressor(..., n_jobs=4)  → TypeError

    # @datagenerator: return SCALARS, not dicts.
    # output_names=['y'] already maps name→value; return the value directly.
    #   CORRECT:   @datagenerator(output_names=['y'])
    #              def my_oracle(x): return x**2        # scalar
    #   WRONG:     def my_oracle(x): return {'y': x**2} # stores dict-as-string
    # Multiple outputs: return a tuple in the same order as output_names.
    #   @datagenerator(output_names=['y1', 'y2'])
    #   def f(x): return x, x**2   # positional tuple, NOT a dict
'''
