# F13 - the pairing rule reads 14 faces; 21 more are published prose and nobody has looked at them

Opened 2026-10-12 by the local that owns `ci/`, arising from F11 criterion 3. Not a defect in `claim_digest.py`
- the leg now prints its own blind spot on purpose (`pairing| ... unpoliced=21 unpoliced_bare_blocks=1
unpoliced_faces_with_bare=1`) and its verdict line says `pairing_scope=policed-only(...)`. This ticket is the
widening.

## Measured, this run

```
python ci/claim_digest.py --scratch-root ../sg-claims-judge
tracked_md=84  policed=14  excluded_named(evidence,docs/tickets)=49  unpoliced=21
unpoliced_bare_blocks=1  unpoliced_faces_with_bare=1
```

Partition verified by arm A12 (`three == set(all_md)`, disjoint, every policed face in the index) - it is the
same arithmetic the F11 sentence had to learn to name.

The one offender found in the unpoliced set:

```
blind-not-fatal| docs/journey.md block 14/102: `verdict_identical_cells` is published without
                 `cells_fully_recorded_and_identical` - ... (F11)
```

`docs/journey.md` line 53 records an older round's stdout:
`OUTCOME=RED verdict_disagreements=42 verdict_identical_cells=18/30 unpinned_input=12 incomparable=2`. That gate
did not yet emit the qualifier, so the number is not *wrong* - it is a faithful capture of a weaker measurement,
and it reads as a correctness claim to anyone who does not know the round it came from.

## Acceptance criteria

1. `PAIR_RULES` is enforced fatally over the whole tracked markdown population minus the two named excluded
   classes, i.e. `unpoliced=21` becomes `0` and `policed=14` becomes `35` (or the current number, re-measured at
   the run);
2. `docs/journey.md`'s block is resolved by **prose that says which round it came from and that the qualifier
   did not exist then** - the qualifier token must appear in the same paragraph, and the paragraph must not
   claim the old run measured what it could not. Do **not** add `cells_fully_recorded_and_identical=0`: that
   would be inventing a reading. If no honest sentence exists, the alternative is to declare a
   `historical-quote` exemption bound to `(rule, face)` pairs with its own printed count, exactly as kind
   `history` already does for numeric claims - and the ticket must say which of the two it shipped;
3. every one of the remaining 20 unpoliced faces is read by the new scope and the run prints
   `unpoliced_bare_blocks=0`;
4. the arms cover the widened scope both ways: the offender above, when planted in a *policed* face, is `RED`,
   and after the fix the whole leg is `CLEAN` with `pairing_scope=tracked_md_covered=<N>` - the `policed-only`
   form must become unreachable except when the index cannot be read;
5. `python ci/claim_digest.py --selftest`, `python ci/claim_digest.py --scratch-root ../<dir>`,
   `python ci/link_check.py` and `python ci/selftest.py --scratch-root ../<dir>` all green at the new tip, and
   the four gate readings (`verdict_disagreements=54`, `verdict_identical_cells=24/44`,
   `cells_fully_recorded_and_identical=4`, `verdict_not_recorded_pairs=121`) unchanged.

## Do not

- Do not touch `evidence/**`: captured runs are their own face class, they are counted and reported, and this
  local does not re-word someone else's capture.
- Do not re-word `docs/tickets/F11-blank-count-sentence.md` to make the count go to zero. That face quotes
  the bare number **to explain why the bare number is wrong**; it is a ticket, and a ticket about a defect is
  allowed to describe it. If the widening has to reach `docs/tickets/**` at all, the answer is the named
  exemption in criterion 2, printed with its denominator - not an edit.
- No bucket change in the gate, no deletion (project rule), no `spec/`, no history rewriting.

## Allowed surface

`ci/claim_digest.py` (the policed set, `PAIR_RULES`, its arms), `docs/journey.md` (one block, criterion 2 only),
and the acceptance row in `evidence/closing/`.

## Clock

24 h from dispatch. Queue position: behind F8's six-lane re-emit and behind the CI-read leg; this ticket
blocks nothing else.
