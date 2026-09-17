"""Held-out collision queries. Written from the symbols' SUMMARIES, before any
ranking was run, and never edited afterwards.

Two kinds, because they falsify different things:

DISAMBIGUATED — the query names the owner. Centrality must NOT override an
explicit signal; if one of these regresses, the tiebreak is overreaching.

AMBIGUOUS — the query does not say which class. Gold is my judgement of what a
user most plausibly means, made from the docstrings before measuring.
"""
DISAMBIGUATED = [
    ("build a domain from a hydra yaml config", "f3dasm.design.Domain.from_yaml"),
    ("create experiment data from a yaml configuration", "f3dasm.ExperimentData.from_yaml"),
    ("make a slurm cluster from a yaml config", "f3dasm.SlurmCluster.from_yaml"),
    ("create a block from a yaml configuration", "f3dasm.Block.from_yaml"),
    ("initialise a domain from input and output data", "f3dasm.design.Domain.from_data"),
    ("create an experimentdata object from existing data", "f3dasm.ExperimentData.from_data"),
    ("prepare the data generator before execution", "f3dasm.DataGenerator.arm"),
    ("arm all the chained blocks", "f3dasm.ChainedBlock.arm"),
    ("arm the inner block before the loop starts", "f3dasm.LoopBlock.arm"),
    ("convert the experiment sample to a dictionary", "f3dasm.ExperimentSample.to_dict"),
    ("create an experiment sample from a json file", "f3dasm.ExperimentSample.from_json"),
    ("interface that handles execution of the data generator", "f3dasm.DataGenerator.execute"),
    ("print the count of open experiments", "f3dasm.pipeline.count_open.main"),
    ("parse arguments and execute a single pipeline step", "f3dasm.pipeline.run_step.main"),
]
AMBIGUOUS = [
    # "from a yaml config" with no class named -- the object a user most often
    # builds from a config is the experiment data itself.
    ("load it from a yaml config file", "f3dasm.ExperimentData.from_yaml"),
    # "from data I already have" -- likewise.
    ("build one from data I already have", "f3dasm.ExperimentData.from_data"),
    # "prepare before running" -- Block.arm is the base-class contract every
    # other arm implements.
    ("prepare it before running", "f3dasm.Block.arm"),
    # a bare constructor query
    ("construct the main object that stores a design of experiments",
     "f3dasm.ExperimentData.__init__"),
]
