# Related work

**Read in full** means the paper was fetched and its claims quoted from the
text. **Title-only** means it appeared in a search and has not been read; it
may not be cited, and nothing here may be argued against it. That distinction
is kept explicit because the temptation to cite from an abstract is exactly how
a related-work section becomes wrong.

---

## Read in full

### AbaqusAgent — multi-agent framework for end-to-end FEA
`arxiv.org/abs/2606.00138`

The closest neighbour, and the most useful single finding: **it does not ingest
the documentation at all.** It curates a case library — 104 worked problems, 71
from the Abaqus benchmark manual and 33 textbook-style — indexed along three
structured dimensions (case metadata, problem description, input file), all
embedded with `text-embedding-3-small` into one FAISS store. A query is first
converted into structured fields, then filtered and ranked by weighted
similarity. The retrieval unit is a whole case; the word "chunk" does not
appear. A retrieved case is used as a structural template only, enforced in the
prompt: *"The reference input_file is a template for structure, not physics."*

They say why: *"As a closed-source commercial package, the benchmark
documentation and scripts of Abaqus are not as readily available as those for
open-source FEA codes… The curation of the RAG for AbaqusAgent poses a
significant challenge due to the limited resources."*

Their ablation (20 cases, Opus-4.6, temperature 0):

| Reviewer | RAG | Success | Accuracy | Tokens | Time (s) |
|---|---|---|---|---|---|
| ✓ | ✓ | 90% | 90% | 634,690 | 3,518 |
| ✓ | ✗ | 80% | 80% | 2,203,778 | 7,758 |
| ✗ | ✓ | 45% | 45% | 246,622 | 1,859 |

Two things we take from this. First, **retrieval's measured benefit was 3.5×
fewer tokens and 2.2× less time for +10pp accuracy** — the efficiency effect is
the large, detectable one, and the accuracy delta at n=20 is not significant
(they do not claim it is). That shapes our endpoint choice directly
(`evaluation-design.md`). Second, the same table with GPT-5.2 gives 65%/45%
where Opus-4.6 gives 90%/90%: **model choice moved the result more than the
ablated feature did.** Any ablation must pin the model and say so.

Their evaluation set is 50 cases, but **40 of the 50 are drawn from the 104-case
retrieval library**, leaving 10 external. That is retrieval-set leakage on 80%
of the benchmark and inflates any RAG-on condition. Code is claimed at
`github.com/LIRAM-LIN/AbaqusAgent`; **contents not verified**.

### PDE-Agents — LLM-orchestrated multi-agent FEM with knowledge-graph reasoning
`arxiv.org/html/2606.07850`

Also does not ingest documentation: its graph holds material properties,
failure patterns and run lineage. Three-way ablation on 50 tasks where "KG
Smart" — warm-start injection plus lazy conditional retrieval — reaches 100%
success and 0.933 physics score against 0.853 for KG Off. Headline:
*"integration pattern, rather than knowledge content, [decides] whether
GraphRAG augmentation helps or hinders an LLM agent."*

Their own limitations section asks the question we have to answer too: *"Is
retrieval necessary, or would a better prompt suffice?"* All artifacts
released.

### Is Grep All You Need? How agent harnesses reshape agentic search
`arxiv.org/html/2605.15184`

Grep beat vector retrieval in their Experiment 1, **but the paper's own
conclusion is that retrieval strategy was not the dominant variable**:
*"overall scores still depend strongly on which harness and tool-calling style
is used, even when the underlying conversation data are the same."*

It also states the trade-off precisely: *"Grep is deliberately narrow: it
rewards the model for generating high-precision patterns, but it punishes
vocabulary mismatch — if the agent never guesses a distinctive substring,
nothing is retrieved. Dense retrieval is deliberately broad: it can surface
paraphrases and oblique mentions, but it also elevates semantically 'near'
distractors."*

**Does not transfer directly.** The benchmark is LongMemEval — 116 questions of
conversational memory, where answers are *"often licensed by a small set of
distinctive strings"*. That is the best possible case for lexical matching and
the worst possible analogy for technical documentation.

### A systematic analysis of chunking strategies for reliable question answering
`arxiv.org/abs/2601.14123`

Reports that overlap provides no measurable benefit — **for its configuration**,
which is Natural Questions with SPLADE retrieval and a Mistral-8B generator:
open-domain Wikipedia QA, a sparse-learned retriever, a small generator. Our
corpus is technical documents, our retriever is BM25+dense RRF, and our
consumer is an agent in a loop. The finding is real and does not bear on our
parameters. Recorded here because it was initially over-read in exactly that
way, and the correction is worth keeping.

---

## Where that leaves us

The recurring cross-paper result, from two independent groups, is that
**integration pattern beats index choice**: PDE-Agents says it outright, and
the grep paper finds the harness dominates the retrieval strategy. If that
holds, an ablation of *how* a capability is wired into the loop is more
informative than an ablation of *which* retriever is used — which is the shape
our evaluation already takes.

The unoccupied gap, stated carefully: **both FEA-agent papers route around the
documentation problem by hand-curating a small structured knowledge base, and
both say so.** Nobody in this neighbourhood has made a full documentation
corpus traversable. That is a real opening, with two risks worth naming before
claiming it: it is adjacent to GraphRAG, which PDE-Agents has already applied
in this exact domain, so the difference must be principled (a *derived*
hierarchy from document structure versus a *curated* graph of facts); and given
the integration-beats-index finding, a tree without a traversal policy would
likely underperform its own promise.

## Title-only — not citable yet

The earlier literature sweep surfaced further candidates that were never
fetched. They are deliberately not listed here: a list of unread titles in a
draft is an invitation to cite them. Fetch, read, then add.

## The largest gap

Four papers is enough to position against and nowhere near a survey. Missing
entirely: autonomous-scientist systems outside FEA, the self-verification and
self-consistency literature, work on agent memory and provenance, and anything
on evaluation methodology for agentic systems — which is the literature our
evaluation design should be answerable to.
