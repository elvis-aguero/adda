"""A second, independent labelled query set for the f3dasm API lookup.

WHO IS ASKING, AND WHY A SECOND FILE
    ``tests/f3dasm_query_set.py`` is the first labelled set. This file is a
    disjoint extension of it, written without looking at how any query
    ranks, so that the two sets can disagree — and a disagreement is
    information, not noise: it means one set's phrasing exercises a case the
    other does not.

    The asker imagined behind every query here is one of two people the
    lookup tool actually serves: an engineer setting up a design-of-
    experiments study on their own machine or a SLURM cluster, who half-
    remembers f3dasm's shape but not its exact spelling; or adda's own
    implementer/datagenerator agent, mid-generation, that has either read a
    symbol's name straight out of a traceback or is trying to translate a
    plain-English requirement ("save this to disk", "run this on the
    cluster") into an f3dasm call it has never seen. Neither of those askers
    phrases a question by anticipating what a lexical ranker rewards; both
    of them are simply saying what they want.

THE TIERS
    Same five tiers, same meanings, as ``f3dasm_query_set.py``:

    ``name``       a bare symbol name; the asker wants its signature/doc.
    ``dotted``     a ``Class.method`` path, as an agent writes it down.
    ``traceback``  a PRIVATE ``f3dasm._src....`` path exactly as it would
                   appear in a real stack trace, which must resolve to the
                   public symbol an agent should actually import.
    ``vocab``      a concept in f3dasm's OWN words (sample, store, domain,
                   arm, job, block, step).
    ``synonym``    the same concept in everyday English that deliberately
                   avoids f3dasm's vocabulary. This is the known-weak tier.
                   Every query here was phrased from the CONCEPT, not from
                   the target docstring's wording — the point of the tier is
                   broken the moment a query is checked against the answer
                   and adjusted to share a word with it.

LABELLING RULE, AND THE ONE RULE THAT MATTERS MOST
    ``accept`` is a set of symbol KEYS, exactly as ``build_index()`` names
    them, because a concept usually has more than one right answer. Every
    key below was checked against a live ``build_index("f3dasm")`` at the
    time this file was written — not guessed, not remembered from the other
    query set.

    A label may be REPOINTED later, and only for one reason: f3dasm renamed,
    moved, or removed the symbol, so the key that used to be correct no
    longer resolves or no longer means what the query asks. A label must
    NEVER be edited, added to, or removed because some retriever scored
    badly on it. Curating labels to whatever a ranker currently returns
    turns the measurement into a mirror of the ranker being measured, which
    destroys the entire reason this file is data instead of assertions.

HELD_OUT_IDS
    A stratified third of the indices into ``QUERIES``, listed here as a
    literal, fixed set of integers rather than computed by a hash of the
    query text. The point of listing them literally is that they cannot
    silently drift if the query list is ever reordered or re-hashed by a
    different Python version -- the split is a decision made once, on paper,
    not a property recomputed from the data. The intended use is the usual
    one for a held-out slice: tune ranking heuristics only by looking at the
    complement of this set, then check the held-out indices last, so the
    number reported for them is a genuine test rather than something that
    was, even indirectly, fitted to.
"""
from __future__ import annotations

# (query, accepted keys, tier)
QUERIES: list[tuple[str, set[str], str]] = [
    # --- 0..13: the agent knows the name ------------------------------------
    ("ExperimentSample", {"f3dasm.ExperimentSample"}, "name"),
    ("ChainedBlock", {"f3dasm.ChainedBlock"}, "name"),
    ("LoopBlock", {"f3dasm.LoopBlock"}, "name"),
    ("Loop", {"f3dasm.Loop"}, "name"),
    ("Step", {"f3dasm.Step"}, "name"),
    ("SlurmResources", {"f3dasm.SlurmResources"}, "name"),
    ("CollectArrayResults", {"f3dasm.CollectArrayResults"}, "name"),
    ("Block", {"f3dasm.Block"}, "name"),
    ("nelder_mead", {"f3dasm.optimization.nelder_mead"}, "name"),
    ("lbfgsb", {"f3dasm.optimization.lbfgsb"}, "name"),
    ("update_config_with_experiment_sample",
     {"f3dasm.hydra_tools.update_config_with_experiment_sample"}, "name"),
    ("try_import", {"f3dasm.optimization.try_import"}, "name"),
    ("count_open", {"f3dasm.pipeline.count_open.main"}, "name"),
    ("run_step", {"f3dasm.pipeline.run_step.main"}, "name"),

    # --- 14..23: Class.method ------------------------------------------------
    ("ExperimentSample.get", {"f3dasm.ExperimentSample.get"}, "dotted"),
    ("ExperimentSample.mark", {"f3dasm.ExperimentSample.mark"}, "dotted"),
    ("Domain.add_int", {"f3dasm.design.Domain.add_int"}, "dotted"),
    ("Domain.add_array", {"f3dasm.design.Domain.add_array"}, "dotted"),
    ("Pipeline.generate_scripts",
     {"f3dasm.Pipeline.generate_scripts"}, "dotted"),
    ("Pipeline.from_step", {"f3dasm.Pipeline.from_step"}, "dotted"),
    ("SlurmCluster.from_yaml", {"f3dasm.SlurmCluster.from_yaml"}, "dotted"),
    ("DataGenerator.execute", {"f3dasm.DataGenerator.execute"}, "dotted"),
    ("ChainedBlock.call", {"f3dasm.ChainedBlock.call"}, "dotted"),
    ("ExperimentData.to_xarray", {"f3dasm.ExperimentData.to_xarray"}, "dotted"),

    # --- 24..33: a name as it appears in a traceback ------------------------
    ("f3dasm._src.pipeline.pipeline.Pipeline", {"f3dasm.Pipeline"},
     "traceback"),
    ("f3dasm._src.pipeline.resources.SlurmCluster", {"f3dasm.SlurmCluster"},
     "traceback"),
    ("f3dasm._src.experimentsample.ExperimentSample",
     {"f3dasm.ExperimentSample"}, "traceback"),
    ("f3dasm._src.core.DataGenerator", {"f3dasm.DataGenerator"}, "traceback"),
    ("f3dasm._src.core.ChainedBlock", {"f3dasm.ChainedBlock"}, "traceback"),
    ("f3dasm._src.core.LoopBlock", {"f3dasm.LoopBlock"}, "traceback"),
    ("f3dasm._src.pipeline.loop.Loop", {"f3dasm.Loop"}, "traceback"),
    ("f3dasm._src.samplers.create_sampler", {"f3dasm.create_sampler"},
     "traceback"),
    ("f3dasm._src.optimization.optimizer_factory.create_optimizer",
     {"f3dasm.create_optimizer"}, "traceback"),
    ("ExperimentSample.__add__", {"f3dasm.ExperimentSample.__add__"},
     "traceback"),

    # --- 34..53: concept, in f3dasm's own vocabulary ------------------------
    ("arm a block before running it",
     {"f3dasm.Block.arm", "f3dasm.DataGenerator.arm"}, "vocab"),
    ("mark all experiments as open",
     {"f3dasm.ExperimentData.mark_all"}, "vocab"),
    ("get the next open job",
     {"f3dasm.ExperimentData.get_open_job"}, "vocab"),
    ("move a parameter from output to input",
     {"f3dasm.ExperimentData.move_to_input"}, "vocab"),
    ("move a parameter from input to output",
     {"f3dasm.ExperimentData.move_to_output"}, "vocab"),
    ("select experiments by status",
     {"f3dasm.ExperimentData.select_with_status"}, "vocab"),
    ("add a constant parameter to the domain",
     {"f3dasm.design.Domain.add_constant"}, "vocab"),
    ("add an array parameter to the domain",
     {"f3dasm.design.Domain.add_array"}, "vocab"),
    ("get a value from an experiment sample",
     {"f3dasm.ExperimentSample.get"}, "vocab"),
    ("create an experiment sample from a numpy array",
     {"f3dasm.ExperimentSample.from_numpy"}, "vocab"),
    ("wrap a block in a Loop",
     {"f3dasm.Loop", "f3dasm.LoopBlock"}, "vocab"),
    ("define a pipeline step",
     {"f3dasm.Step"}, "vocab"),
    ("set slurm resources for a step",
     {"f3dasm.SlurmResources"}, "vocab"),
    ("generate slurm scripts without submitting",
     {"f3dasm.Pipeline.generate_scripts"}, "vocab"),
    ("start the pipeline from a given step",
     {"f3dasm.Pipeline.from_step"}, "vocab"),
    ("create a datagenerator from a function",
     {"f3dasm.create_datagenerator"}, "vocab"),
    ("create an optimizer block",
     {"f3dasm.create_optimizer"}, "vocab"),
    ("evaluate a datagenerator with mpi",
     {"f3dasm._src.datagenerator.evaluate_mpi"}, "vocab"),
    ("the job status enum",
     {"f3dasm._src.experimentsample.JobStatus"}, "vocab"),
    ("load a domain from a yaml config",
     {"f3dasm.design.Domain.from_yaml"}, "vocab"),

    # --- 54..69: concept, in words f3dasm does NOT use (known-weak tier) ----
    ("spread points evenly across every combination of settings",
     {"f3dasm.design.grid", "f3dasm._src.samplers.Grid"}, "synonym"),
    ("load a saved project back into memory",
     {"f3dasm.ExperimentData.from_file"}, "synonym"),
    ("renumber everything starting from zero",
     {"f3dasm.ExperimentData.reset_index"}, "synonym"),
    ("put the rows in a particular order",
     {"f3dasm.ExperimentData.sort"}, "synonym"),
    ("grab just one variable's column",
     {"f3dasm.ExperimentData.select_parameter"}, "synonym"),
    ("is everything done running yet",
     {"f3dasm.ExperimentData.is_all_finished"}, "synonym"),
    ("hand off my simulation code so it runs automatically",
     {"f3dasm.create_datagenerator", "f3dasm.DataGenerator",
      "f3dasm.datagenerator"}, "synonym"),
    ("spread the workload across many cpu cores on one machine",
     {"f3dasm._src.datagenerator.evaluate_multiprocessing"}, "synonym"),
    ("make sure two workers don't grab the same piece of work at once",
     {"f3dasm._src.mpi_utils.mpi_get_open_job",
      "f3dasm._src.mpi_utils.mpi_lock_manager"}, "synonym"),
    ("give up after trying too many times",
     {"f3dasm._src.errors.ReachMaximumTriesError"}, "synonym"),
    ("the file was there but had nothing in it",
     {"f3dasm._src.errors.EmptyFileError"}, "synonym"),
    ("the picture I saved during the run won't open",
     {"f3dasm._src._io.figure_load"}, "synonym"),
    ("a step failed because a dependency package is missing",
     {"f3dasm.optimization.try_import",
      "f3dasm._src.optimization.errors.faulty_optimizer"}, "synonym"),
    ("hook my config file up to the values of one run",
     {"f3dasm.hydra_tools.update_config_with_experiment_sample"}, "synonym"),
    ("flip a continuous variable into buckets",
     {"f3dasm._src.design.parameter.ContinuousParameter.to_discrete"},
     "synonym"),
    ("let a component get ready before the real run starts",
     {"f3dasm.Block.arm", "f3dasm.DataGenerator.arm"}, "synonym"),
]

#: Same five tier names, same order, as ``f3dasm_query_set.py`` -- kept
#: identical rather than re-derived so the two files can be scored together
#: by that module's own ``evaluate``/``format_report`` without translation.
TIERS = ("name", "dotted", "traceback", "vocab", "synonym")

#: One third of ``QUERIES`` (23 of 70), stratified across tiers in
#: proportion to each tier's size, and written down as literal indices
#: rather than computed -- see the module docstring for why. Indices are
#: 0-based positions into ``QUERIES`` above, and line up with the numbered
#: comments in that list.
HELD_OUT_IDS: frozenset[int] = frozenset({
    # name (5 of 14)
    1, 4, 7, 10, 13,
    # dotted (3 of 10)
    15, 18, 21,
    # traceback (3 of 10)
    25, 28, 31,
    # vocab (7 of 20)
    34, 37, 40, 43, 46, 49, 52,
    # synonym (5 of 16)
    55, 58, 61, 64, 67,
})
