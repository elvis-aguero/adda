"""A labelled query set for the f3dasm API lookup, and the metrics over it.

WHY THIS EXISTS AS DATA RATHER THAN AS ASSERTIONS
    ``tests/test_f3dasm_api.py`` carries a 12-query golden set asserted at
    top-5. That guards against a catastrophic ranker change and nothing else:
    it cannot say whether a tweak made retrieval BETTER, only that it did not
    break twelve specific cases. Every ranking change so far has therefore been
    argued from a handful of hand-picked probes — including, in this repo's own
    history, probes chosen by whoever was proposing the change.

    This file separates the labels from the assertions so a change can be
    MEASURED: recall@1/3/5 and MRR, reported per tier, against a recorded
    baseline.

THE TIERS ARE THE POINT
    Aggregate recall hides the only interesting thing. The lookup is near
    perfect when the agent already knows the name and weak when it does not,
    so a single number moves mostly with the tier mix, which is arbitrary.

    ``name``/``dotted``/``traceback``  the agent knows what it wants and is
        checking a signature. Failure here is a catastrophe; these should be
        at or near 1.0 forever.
    ``vocab``  a concept query phrased in f3dasm's OWN words ("sample",
        "store", "domain"). This is what the current lexical ranker is built
        for.
    ``synonym``  the same intent in words f3dasm does not use — "save",
        "supercomputer", "black box". This is the KNOWN-WEAK tier, and it is
        the one that justifies (or refutes) any future embedding work. It is
        recorded honestly rather than curated up.

LABELLING RULE
    ``accept`` is a SET, because a concept usually has several right answers
    and pinning one tunes the ranker toward a worse result. A query counts as
    answered at k if ANY accepted key is in the top k. Keys are checked
    against the live index by ``test_f3dasm_api_retrieval.py``, so a renamed
    f3dasm symbol fails the build instead of silently scoring zero forever.
"""
from __future__ import annotations

# (query, accepted keys, tier)
QUERIES: list[tuple[str, set[str], str]] = [
    # --- the agent knows the name -----------------------------------------
    ("ExperimentData", {"f3dasm.ExperimentData"}, "name"),
    ("create_sampler", {"f3dasm.create_sampler"}, "name"),
    ("create_optimizer", {"f3dasm.create_optimizer"}, "name"),
    ("create_datagenerator", {"f3dasm.create_datagenerator"}, "name"),
    ("Domain", {"f3dasm.design.Domain"}, "name"),
    ("DataGenerator", {"f3dasm.DataGenerator"}, "name"),
    ("Pipeline", {"f3dasm.Pipeline"}, "name"),
    ("SlurmCluster", {"f3dasm.SlurmCluster"}, "name"),
    ("datagenerator decorator", {"f3dasm.datagenerator"}, "name"),
    ("make_nd_continuous_domain",
     {"f3dasm.design.make_nd_continuous_domain"}, "name"),

    # --- Class.method -------------------------------------------------------
    ("ExperimentData.store", {"f3dasm.ExperimentData.store"}, "dotted"),
    ("ExperimentData.to_numpy", {"f3dasm.ExperimentData.to_numpy"}, "dotted"),
    ("Domain.add_float", {"f3dasm.design.Domain.add_float"}, "dotted"),
    ("Domain.get_bounds", {"f3dasm.design.Domain.get_bounds"}, "dotted"),
    ("Pipeline.run", {"f3dasm.Pipeline.run"}, "dotted"),
    ("Block.loop", {"f3dasm.Block.loop"}, "dotted"),
    ("ExperimentData.get_n_best_output",
     {"f3dasm.ExperimentData.get_n_best_output"}, "dotted"),

    # --- a name as it appears in a traceback or an operator -----------------
    ("f3dasm._src.experimentdata.ExperimentData",
     {"f3dasm.ExperimentData"}, "traceback"),
    ("f3dasm._src.design.domain.Domain", {"f3dasm.design.Domain"}, "traceback"),
    ("Block.__rshift__", {"f3dasm.Block.__rshift__"}, "traceback"),
    ("ExperimentData.__add__", {"f3dasm.ExperimentData.__add__"}, "traceback"),

    # --- concept, in f3dasm's own vocabulary --------------------------------
    ("sampler", {"f3dasm.create_sampler"}, "vocab"),
    ("how do I sample the design space",
     {"f3dasm.create_sampler", "f3dasm.design.grid", "f3dasm.design.sobol",
      "f3dasm.design.latin", "f3dasm.design.random"}, "vocab"),
    ("latin hypercube sampling",
     {"f3dasm.design.latin", "f3dasm.create_sampler"}, "vocab"),
    ("store data to disk",
     {"f3dasm.ExperimentData.store", "f3dasm.design.Domain.store",
      "f3dasm.ExperimentSample.store"}, "vocab"),
    ("define input parameters",
     {"f3dasm.design.Domain", "f3dasm.design.Domain.add_parameter",
      "f3dasm.design.Domain.add_float", "f3dasm.design.Domain.add"}, "vocab"),
    ("add a categorical parameter to the domain",
     {"f3dasm.design.Domain.add_category"}, "vocab"),
    ("add an output parameter",
     {"f3dasm.design.Domain.add_output"}, "vocab"),
    ("bounds of the continuous parameters",
     {"f3dasm.design.Domain.get_bounds"}, "vocab"),
    ("run a pipeline on slurm",
     {"f3dasm.SlurmCluster", "f3dasm.SlurmResources", "f3dasm.Pipeline",
      "f3dasm.Pipeline.run"}, "vocab"),
    ("the n best output samples",
     {"f3dasm.ExperimentData.get_n_best_output"}, "vocab"),
    ("mark a job status",
     {"f3dasm.ExperimentData.mark", "f3dasm.ExperimentSample.mark",
      "f3dasm.ExperimentData.mark_all"}, "vocab"),
    ("join two ExperimentData objects",
     {"f3dasm.ExperimentData.join", "f3dasm.ExperimentData.__add__"}, "vocab"),
    ("convert to pandas dataframe",
     {"f3dasm.ExperimentData.to_pandas",
      "f3dasm.ExperimentData.to_multiindex"}, "vocab"),
    ("nelder mead optimizer",
     {"f3dasm.optimization.nelder_mead", "f3dasm.create_optimizer"}, "vocab"),
    ("rosenbrock benchmark function",
     {"f3dasm.datageneration.functions.rosenbrock"}, "vocab"),
    ("chain blocks in sequence",
     {"f3dasm.ChainedBlock", "f3dasm.Block.__rshift__",
      "f3dasm.ChainedBlock.call"}, "vocab"),
    ("repeat a block n iterations",
     {"f3dasm.LoopBlock", "f3dasm.Block.loop", "f3dasm.Loop"}, "vocab"),
    ("replace NaN values",
     {"f3dasm.ExperimentData.replace_nan",
      "f3dasm.ExperimentSample.replace_nan"}, "vocab"),

    # --- concept, in words f3dasm does NOT use (the known-weak tier) --------
    ("how do I save my results to a file",
     {"f3dasm.ExperimentData.store", "f3dasm.ExperimentSample.store"},
     "synonym"),
    ("read an experiment back from disk",
     {"f3dasm.ExperimentData.from_file"}, "synonym"),
    ("get the best design found so far",
     {"f3dasm.ExperimentData.get_n_best_output"}, "synonym"),
    ("combine two datasets",
     {"f3dasm.ExperimentData.join", "f3dasm.ExperimentData.__add__",
      "f3dasm.ExperimentData.add_experiments"}, "synonym"),
    ("run jobs on a supercomputer",
     {"f3dasm.SlurmCluster", "f3dasm.SlurmResources",
      "f3dasm.Pipeline.generate_scripts"}, "synonym"),
    ("wrap a black box simulation",
     {"f3dasm.DataGenerator", "f3dasm.datagenerator",
      "f3dasm.create_datagenerator"}, "synonym"),
    ("pick points to try next",
     {"f3dasm.create_optimizer", "f3dasm.optimization.nelder_mead",
      "f3dasm.optimization.lbfgsb", "f3dasm.optimization.cg"}, "synonym"),
    ("check which runs already finished",
     {"f3dasm.ExperimentData.is_all_finished",
      "f3dasm.ExperimentSample.is_status",
      "f3dasm.ExperimentData.select_with_status"}, "synonym"),
    ("turn the table into arrays for scikit-learn",
     {"f3dasm.ExperimentData.to_numpy"}, "synonym"),
    ("how many experiments do I have",
     {"f3dasm.ExperimentData.__len__"}, "synonym"),
    ("throw away the last few rows",
     {"f3dasm.ExperimentData.remove_rows_bottom"}, "synonym"),
    ("a test function to benchmark against",
     {"f3dasm.datageneration.functions.rosenbrock",
      "f3dasm.datageneration.functions.ackley",
      "f3dasm.datageneration.functions.sphere",
      "f3dasm.create_datagenerator"}, "synonym"),
    ("quasi random low discrepancy points",
     {"f3dasm.design.sobol", "f3dasm.design.latin"}, "synonym"),
    ("where does the project folder live",
     {"f3dasm.ExperimentData.set_project_dir"}, "synonym"),
    ("pull out one experiment by index",
     {"f3dasm.ExperimentData.get_experiment_sample",
      "f3dasm.ExperimentData.__getitem__",
      "f3dasm.ExperimentData.select"}, "synonym"),
    ("gradient based local search",
     {"f3dasm.optimization.lbfgsb", "f3dasm.optimization.cg",
      "f3dasm.create_optimizer"}, "synonym"),
    ("tidy up the numbers to three decimals",
     {"f3dasm.ExperimentData.round", "f3dasm.ExperimentSample.round"},
     "synonym"),
]

TIERS = ("name", "dotted", "traceback", "vocab", "synonym")


def evaluate(rank, ks=(1, 3, 5)) -> dict:
    """Score a ranking function over the query set.

    ``rank(query, limit) -> list[str]`` of keys, best first. Returns
    ``{tier_or_"all": {"n": int, "r@1": float, ..., "mrr": float}}``.

    MRR is reported alongside recall because recall@5 is blind to WHERE in the
    five a hit landed, and an answer at rank 5 is one an agent scrolls past.
    """
    top = max(ks)
    buckets: dict[str, list[float]] = {t: [] for t in TIERS}
    buckets["all"] = []
    hits: dict[str, list[list[bool]]] = {t: [] for t in TIERS}
    hits["all"] = []
    for query, accept, tier in QUERIES:
        got = list(rank(query, top))
        pos = next((i for i, k in enumerate(got) if k in accept), None)
        rr = 0.0 if pos is None else 1.0 / (pos + 1)
        at = [pos is not None and pos < k for k in ks]
        for b in (tier, "all"):
            buckets[b].append(rr)
            hits[b].append(at)
    out = {}
    for b, rrs in buckets.items():
        if not rrs:
            continue
        rows = hits[b]
        out[b] = {"n": len(rrs), "mrr": sum(rrs) / len(rrs)}
        for i, k in enumerate(ks):
            out[b][f"r@{k}"] = sum(r[i] for r in rows) / len(rows)
    return out


def format_report(scores: dict) -> str:
    """A table, so a regression is readable in the pytest output."""
    head = f"{'tier':<10}{'n':>4}{'r@1':>8}{'r@3':>8}{'r@5':>8}{'MRR':>8}"
    lines = [head, "-" * len(head)]
    for tier in (*TIERS, "all"):
        s = scores.get(tier)
        if not s:
            continue
        lines.append(
            f"{tier:<10}{s['n']:>4}{s['r@1']:>8.2f}{s['r@3']:>8.2f}"
            f"{s['r@5']:>8.2f}{s['mrr']:>8.2f}")
    return "\n".join(lines)
