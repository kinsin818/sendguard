# F11 - the published sentence about blanks counts one bucket, and the reader hears the whole hole

Opened 2026-10-12 by the local that owns `ci/`, from two audit packets that reached it by different routes
(auditor-1 F-1 and auditor-4 F-2, the latter also carried into F-3 of `docs/coverage.md`'s own wording row).

## The defect, measured

`docs/coverage.md` and the outward prose publish:

> `verdict_not_recorded_pairs=121` - field-cells blank in at least one port

and, in the "What a blank is" section, the assurance that nothing is left unplaced. The gate's buckets are:

| bucket | what it holds | count in the current reading |
|---|---|---|
| `not_recorded_pairs` | a port abstained on a field **where the recording ports did not contradict each other** | 121 |
| disagreements | facts where two ports differ - **including the 23 field-cells where a port also abstained** | 54 facts over 20 cells |

So the literal number of (cell, field) pairs with at least one abstaining port is **144 of 440**, not 121: the 23
abstentions that sit on already-contradicted facts are charged to the disagreement bucket first. Both reviewers
identified the right defect; **auditor-1's own arithmetic did not reproduce**, and this is the part of the batch
that shows the intake rule working rather than flattering anyone:

```
python ci/equality.py                      # the gate, re-read not remembered
python - <<PY                              # one pass over the gate's own artifact
  ...disagreements rows split by whether a port is absent from the row...
PY
blank_pairs= 121
disagree_with_abstention= 23   disagree_all_six_recorded= 31
union (any port abstained on that pair)= 144
```

`121 + 23 = 144`. The packet states `154 of 440 (35%)`. The claim survives, the number does not: a reviewer's
figure is treated exactly like a published one - reproduced or refused, never copied. Two denominators also need
naming in the sentence, because they are different objects: **440** = cells x verdict fields (a pair), **2,640** =
pairs x ports (a field-cell per port), and `verdict_pairs_recorded=2281` is counted on the second one.

The same sentence family is behind auditor-1 F-3: `verdict_identical_cells=24/44` counts a cell where an
abstention made a contradiction impossible, and the number survives publication only because it is welded to
`cells_fully_recorded_and_identical=4`. A claim that survives only while paired with its qualifier must say so in
the sentence, not rely on the reader carrying the pairing rule in their head.

**The instrument is not wrong.** Bucketing disagreement first and abstention second is deliberate and printed;
this project's rule is that a fix belongs wherever the defect actually lives, and here it lives in three
sentences.

## Acceptance criteria

1. `docs/coverage.md` names both buckets and both denominators in one sentence, in the generator, so the corrected
   wording cannot be restored by hand-editing the face: 121 where nobody contradicted and someone abstained, plus
   23 abstentions on facts that also disagree, against `verdict_pairs_possible`;
2. the sentence "nothing is left unplaced" is replaced by the arithmetic that makes it true or deleted - whichever
   the numbers support at the run, chosen by the generator, not by this ticket;
3. `verdict_identical_cells` is never emitted anywhere without its qualifier in the same paragraph; the check is
   mechanical - extend `ci/claim_digest.py` so an occurrence of that number with no `cells_fully_recorded_and_identical`
   within the same face block is `RED`, with a red arm (bare number planted) and a green arm (the pair present);
4. both readings printed before/after in the acceptance row: `python ci/equality.py` must keep
   `verdict_disagreements=54`, `verdict_identical_cells=24/44`, `cells_fully_recorded_and_identical=4` and
   `verdict_not_recorded_pairs=121` exactly - the numbers do not move in this ticket, only what is said about them;
5. `python ci/coverage_report.py && python ci/claim_digest.py --scratch-root ../<dir> && python ci/link_check.py`
   all green at the new tip, and `python ci/selftest.py --scratch-root ../<dir>` still `arms=21 passed=21`.

## Do not

- Do not re-bucket in the gate to make the sentence cleaner; a bucket change would move verdict-adjacent numbers
  and turn a wording fix into a re-measurement, which is precisely the confusion `docs/FINDINGS-rev6.md` M8 cost
  this project.
- Do not hand-edit a generated face; the corrected sentence is authored in `ci/coverage_report.py`.
- No deletion logic (project rule), no touching `spec/`, no history rewriting.

## Allowed surface

`ci/coverage_report.py`, the generated `docs/coverage.md`, `docs/claim-boundary.md`'s Verdict-fields row,
`ci/claim_digest.py` (one new claim plus its arms), and an appended errata line in `docs/FINDINGS-rev6.md`.
