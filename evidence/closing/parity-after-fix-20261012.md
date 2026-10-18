# The parity reading that `722c334` promised, taken after it landed

Command, run from this repository at the commit named below:

```
python ci/clone_parity.py --scratch-root ../sg-parity-verify
```

Output, verbatim:

```
OUTCOME=CLEAN faces_compared=13 identical=11 declared=1 differing=0 missing=0
host_bound=1(docs/host-stamp.md) clone=<scratch clone dir>
source=this repository
rc=0
```

Commit under test: `722c334` (`git rev-parse HEAD` at the time of the run; the clone adopted
`<scratch clone dir>`, created rather than reused, `status_before=0`).

## What this reading does and does not prove

**It proves:** every generated face in a `--no-local` clone of the published-shaped tree is byte-identical to the
blob that clone checks out, with the two self-referential lines declared in advance (`docs/evidence.md` naming the
HEAD it was generated under) absorbed by the narrow exception rather than by a widening of it, and one face
(`docs/host-stamp.md`) excluded by name because it holds machine facts.

**It does not prove:** cross-machine reproducibility. The clone is on the same host, same drive, same interpreter
(3.14.7). That limit is published in `docs/claim-boundary.md` and is the reason `F3` exists.

## The sequence, including the reading that was red

This file exists because a claim was made one commit too early and then checked:

| commit | what it claimed about parity | what the leg said |
|---|---|---|
| `6d15c6c` | quoted a pre-commit reading, and said the post-commit one was "the next thing done" | `OUTCOME=RED ... differing=1 declared=0 rc=1` - the committed `docs/evidence.md` carried a line the clone's generator could not produce, because `ci/evidence_table.py` had fallen out of that commit's staged set |
| `722c334` | names that defect, asserts each required face by name rather than by a count of staged paths | `OUTCOME=CLEAN ... differing=0 rc=0`, this file |

The line-count check is what caught it: `if rx and not extra` refuses to excuse a difference when the two faces do
not even have the same number of lines, so a declared line-shape exception cannot swallow a whole missing line.
That guard existed before this episode and was not written for it, which is the argument for arming instruments
rather than trusting care: the leg found a defect in a commit whose own message claimed the leg was green.

Numbers quoted here are not hand-copied: `python ci/refresh_all.py --check` regenerates the faces, and
`python ci/claim_digest.py --scratch-root ../<dir>` re-measures every number that appears in prose, so a future
divergence between this page and the leg's output is a red run, not a typo to be noticed by someone's memory.
