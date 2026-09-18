# `paper/` — the draft

The working draft of a paper about adda. **Not** user documentation: `docs/` is
for someone trying to run a study, this is for someone deciding whether to
believe the design. Keeping them apart is deliberate — user docs are organised
by task, a paper by argument, and the two rot at different rates.

## Layout

```
main.tex            venue-agnostic preamble; \pagebudget is the switch
macros.tex          \decision, \measured, \conjecture, \unverified
refs.bib            citations, each marked READ IN FULL or [VERIFY]
sections/*.tex      one file per section
```

Build with any LaTeX toolchain: `latexmk -pdf main.tex`. **Not verified** —
there is no LaTeX in the development container, so this draft has never been
compiled. `tests/test_paper.py` checks what can be checked without one: every
`\input` resolves, every `\cite` key exists, no section is an empty stub, and
the two mechanical house rules below hold.

## Two decisions behind this shape

**Venue-agnostic.** The venue is undecided, so no style file is committed: a
draft that will not compile without a file we do not have is worse than one
that compiles anywhere. Drop the official `.sty` beside `main.tex` and set
`\pagebudget` when the venue is chosen. What changes with the venue is the
thesis sentence, which related work gets weight, and the evaluation's headline.
What does not is the method register, the empirical record, the evaluation
design and the threats — which is what this tree contains.

**The method section is a living register, not prose.** One entry per
mechanism, each owing the reader the same three things: what it does, how it
is done, and why. The `\decision` macro enforces that shape, so
an entry missing its cost is a visible hole rather than a stylistic choice. It
is written to grow past any page limit on purpose and is cut at submission — a
decision recorded and later cut costs nothing; a decision taken and never
recorded is lost.

**Add an entry when you take a decision, not when you write the paper.** That
is the whole point of the register.

## Rules

1. **Every number carries its source.** Use `\measured{value}{file}`. A figure
   we cannot recompute from the repository does not go in.
2. **Separate what we measured from what we believe.** Design rationale is
   argument; run figures are evidence; anything else is `\conjecture{...}` and
   stays out of the claims. The macro renders ugly on purpose.
3. **Negative results stay.** The most defensible content here is the list of
   things that did not work — including several where a feature appeared to be
   on and was not, and one contract test that disabled itself. Those are not an
   embarrassment to be tidied.
4. **No citation without having read the work in full.** `refs.bib` marks each
   entry; `tests/test_paper.py` fails if the related-work section cites one
   that is not marked. Entries whose bibliographic details came from notes
   rather than the source are marked `[VERIFY]` and counted.

## Where the unharvested material is

Most of the raw material is in the repository and has not been drawn on. In
rough order of value: `internal/AUDIT-20260623.md` and `-reruns.md` (real KPI
tables from wet runs); `internal/BACKLOG.md` (numbered defects with root causes
and what each cost); `studies/run_ledger.csv` (76 runs of telemetry, the source
of every variance and dose figure); `internal/FEATURES.md` (the feature
catalogue, organised by implementation where the method register organises by
argument); and **code comments and commit messages**, where most of the
*rationale* actually lives. That last one is the largest asset and the least
harvested.

## Status

| Section | State |
|---|---|
| Method register | ported and extended; owes quantified costs and a worked example |
| Related work | 4 papers read in full; thin, and the largest known gap |
| Evaluation design | fixed and pre-registered; **blocked on runs** |
| Threats | drafted; several are the paper's best content |
| Retrieval evaluation | measured for adda, partial for f3dasm, unscorable for Abaqus |
| Introduction, abstract | deliberately unwritten until the venue is chosen |
| Results | **blocked on the ablation runs** |

This replaces the earlier markdown drafts (`OUTLINE.md`, `method.md`,
`related-work.md`, `evaluation-design.md`, `threats.md`), whose content was
ported into `sections/`. They are in git history.
