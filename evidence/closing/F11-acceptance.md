# SG-F11 acceptance - the blank sentence now carries its arithmetic

Accepted by the seat that owns `ci/`, 2026-10-12, against `docs/tickets/SG-F11-blank-count-sentence.md`.
Every number below is from this run's captured output, not from prose.

## Commands and readings (before / after)

| # | command | rc | reading |
|---|---|---|---|
| 1 | the reading HEAD published before this ticket, read with `git show HEAD:docs/evidence.md` (rc=0 for the read; the `1` below is the gate's own rc recorded in that face) | 1 | `OUTCOME=RED verdict_disagreements=54 verdict_identical_cells=24/44 cells_fully_recorded_and_identical=4 verdict_not_recorded_pairs=121 verdict_pairs_recorded=2281/2640 probe_cells_differing=29 unpinned_input=0 cells_excluded=0 channel_abstentions=13 truncated_values=2 required_cells_missing=0` |
| 2 | `python ci/equality.py` after the wording work | 1 | all twelve `key=value` pairs equal to row 1 - compared programmatically, not by eye: `fields_new=12 fields_head=12 equal_keys=True differing={} pairs_equal=True` (the face line in `docs/evidence.md` carries markdown emphasis marks around it, which is the only textual difference). The four readings criterion 4 names did not move; only what is said about them changed |
| 3 | `python ci/coverage_report.py --selftest` | 0 | `arms=9 passed=9` |
| 4 | `python ci/coverage_report.py` | 0 | `wrote docs/coverage.md bytes=6123 fields=10 ports=6 cells_compared=44 recorded=2281/2640 fully_recorded=4 clean_and_fully_recorded=4 blanks_by_everybody=10` |
| 5 | `python ci/claim_digest.py --selftest` | 0 | `arms=13 passed=13` (was 6; the printed literal `SELFTEST_ARMS = 6` is gone, the count is collected from the arm labels and A13 refuses a gap) |
| 6 | `python ci/claim_digest.py --scratch-root ../sg-claims-judge` | 0 | `OUTCOME=CLEAN stale_claims=0 unpaired_claims=0 pairing_scope=policed-only(blind_bare_blocks=1,unpoliced_faces_with_bare=1 - SG-F13 owns the widening) coverage=full` |
| 7 | `python ci/link_check.py` | 0 | `OUTCOME=CLEAN markdown_faces=84 links_checked=25 resolved=25 external=0 broken=0 unreadable=0` |
| 8 | `python ci/selftest.py --scratch-root ../sg-selftest` | 0 | `arms=21 passed=21 failed=0` |

## The one-pass measurement behind the sentence

Read from `evidence/S02/equality-verdict.json` in the same pass that writes the face, never from a remembered
number: `blank_pairs=121`, `disagree_with_abstention=23`, `disagree_all_six_recorded=31`,
`union=144`, pair universe `440` = cells x verdict fields, field-cell universe `2640` = pairs x ports, and
`verdict_pairs_recorded=2281` is counted on the second one. Auditor-1's packet figure of `154 of 440` did not
reproduce and is refused, not copied (`evidence/audit-in/ADJUDICATION.md`).

`docs/coverage.md` line 60 now prints it: *"The gate publishes `121` (cell, field) rows; a row may charge more
than one port, so they expand to `258` (cell, field, port) blanks below ... `121 + 23 = 144` pairs, out of `440`
(cell, field) pairs in the grid; of the `2640` field-cells possible, `2281` were answered at all."* The assurance
that "nothing is left unplaced" is replaced by the partition it actually describes (`docs/coverage.md:70`): the
bucket column sums to `258`, which is the expanded count of the `121` published rows, and the face says in words
that this is the whole of the claim the table makes. Two unit labels were also corrected at the source, because
they were the same conflation: `(cell, field) pairs` where the face said `field-cells` for `121`, and
`(cell, field) pairs ... a pair here is a blank for each port in the grid` for the 10 nobody answered.

`docs/claim-boundary.md`'s Verdict-fields row no longer calls the 121 rows field-cells, and refuses to restate
the expanded count in prose at all - it points at the generated face instead, because a number copied out of a
generated face is a number that can go stale. Its claim anchor moved with the sentence
(`boundary-blank-rows` -> `(\d+) \(cell, field\) pairs blank in at least one port`), so a hand-rollback of the
wording is a `stale|` finding, not a silent pass.

## Criterion 3, proven on the real tree

A rule that only fires in a fixture is the decorative-gate defect this project has caught in itself before, so
the pairing rule was probed against the production run by planting text in a policed face and restoring it
byte-for-byte. The probe script is deliberately **not** a tracked face (a face that plants a defect in a policed
face would be scanned by the leg it is testing): it lives one directory outside the tree at
`../f11_red_probe.py` and is run from there:

```
baseline| rc=0 OUTCOME=CLEAN stale_claims=0 unpaired_claims=0 pairing_scope=policed-only(blind_bare_blocks=1,unpoliced_faces_with_bare=1 - SG-F13 owns the widening) coverage=full
planted-bare| rc=1 OUTCOME=RED stale_claims=0 unpaired_claims=1
planted-bare| unpaired| docs/claim-boundary.md block 7/7: `verdict_identical_cells` is published without `cells_fully_recorded_and_identical` - it counts cells where an abstention made a contradiction impossible, so alone it is not a correctness number (SG-F11)
planted-paired| rc=0 OUTCOME=CLEAN stale_claims=0 unpaired_claims=0 pairing_scope=policed-only(blind_bare_blocks=1,unpoliced_faces_with_bare=1 - SG-F13 owns the widening) coverage=full
restore| md5_before=c3e74d2cac93 md5_after=c3e74d2cac93 equal=True
restore| git_status rc=0/0 before='M docs/claim-boundary.md' after='M docs/claim-boundary.md' unchanged_by_probe=True
PROBE| OK
```

The `M docs/claim-boundary.md` on both sides of the restore line is this ticket's own wording edit, still
uncommitted at probe time - which is why the arm compares the status *before and after* the probe rather than
demanding a clean tree.

The green half matters as much as the red half: `ci/claim_digest.py` has 13 arms now. A8 plants a bare number in
a face and requires `RED`; A9 requires the paired form to pass; A10 requires a qualifier parked in a *different*
paragraph to stay RED (a reader meets the two apart); A11 requires the excluded classes to be counted rather than
dropped; A7 asserts both excluded directories exist and every face they match is readable, because an exclusion
matching nothing is a rule nobody tested; A12 asserts the population is a disjoint partition of the tracked
markdown index; A13 refuses a gap in the label sequence, so the printed arm count cannot drift from the checks
behind it (the old printed literal `SELFTEST_ARMS = 6` is gone).

Production run lines, with their denominators:

```
pairing| rules=1 faces_scanned=14 unpaired=0 | excluded_named=evidence,docs/tickets on_disk=52 tracked=51
blocks_with_bare_pair=2 faces=2 dirs_missing=0 disk_only=1 | tracked_md=86 policed=14 unpoliced=21
unpoliced_bare_blocks=1 unpoliced_faces_with_bare=1
OUTCOME=CLEAN stale_claims=0 unpaired_claims=0 pairing_scope=policed-only(blind_bare_blocks=1,
unpoliced_faces_with_bare=1 - SG-F13 owns the widening) coverage=full
```

Two notes on reading that line, both of which this project has had to learn the hard way. The counts move with
the index: the same command run before the two new faces were staged read `tracked_md=84, tracked=49`, and run
after it reads `86, 51` - a captured line is a capture of one moment, and the moment is the face it belongs to.
The `blocks_with_bare_pair=2` inside the excluded class are `docs/tickets/SG-F11-blank-count-sentence.md` and
`docs/tickets/SG-F13-pairing-rule-scope.md`: the ticket that names the defect, and the ticket that widens the
rule, both quote the bare number in order to explain why it must not be published bare.

## The leak leg, and one number this row refuses to attribute

`python ci/process_leak_scan.py --repo-root . --quiet` before the two new faces were staged and after:

```
before  files_scanned=1195 unreadable=0 FATAL=2305 MENTIONED=145 counted_not_fatal=9108
        fatal_by_class=HOSTROOT:13,IDENTITY:1134,LOGIN:15,RETIRED:1143  mentioned_by_class=...,TOOLPATH:131
after   files_scanned=1197 unreadable=0 FATAL=2305 MENTIONED=148 counted_not_fatal=9113
        fatal_by_class=HOSTROOT:13,IDENTITY:1134,LOGIN:15,RETIRED:1143  mentioned_by_class=...,TOOLPATH:134
```

No fatal class moved, which is the only thing this ticket is obliged to prove about the leak leg. The +3 is
**not attributed here**, and the reason it is not is worth more than the number: an attempt to attribute it with
an ad-hoc "looks like a path" regex produced +13 across the staged faces, disagreeing with the leg's +3, because
the leg routes hits by face class (`rule` faces go to `mentioned`, `TOOLPATH` is counted-not-fatal by design)
while my regex counted every match everywhere. Asking the leg's own `scan_face()` reproduced the +13-vs-+3 gap
for the same reason, so neither of my two recount attempts is the leg's ruler and neither is printed as if it
were. That is this project's oldest defect - two rulers, one number - caught while trying to be careful about it,
and it is why the row above prints the leg's line verbatim instead of a derived claim.

Reading `ANY_PATH` itself explains the shape of it: it is
`[A-Za-z]:[\\ /]{1,2}(?![\\/]) | /[A-Za-z0-9_.-]+/`, so its second branch fires on any `/word/` fragment, which
includes ordinary repo-relative references such as `docs/tickets/` and `evidence/S11/`. The leg's docstring calls
that class "any other **absolute** path"; the rule is looser than the word. That is harmless for a counted-not-
fatal metric and load-bearing for nothing here, but it is a rule named by one thing and measuring another, so it
gets its own ticket rather than being absorbed into this acceptance row:
`docs/tickets/SG-F14-leak-leg-toolpath-rule-shape.md`.

Two properties of that line are the reason it can be quoted at all. The `CLEAN` carries its own scope, because
"no face has the defect" and "the faces I read have no defect" are different claims - the rule this ticket adds
to other faces is applied to the leg itself. And the population is a verified partition, asserted by arm A12:
tracked markdown 86 = policed 14 + named-excluded 51 + unpoliced 21.

The `blocks_with_bare_pair=2` inside the excluded class are the SG-F11 ticket and the SG-F13 ticket: the first
quotes the bare number to explain why it is bare, the second quotes it to widen the rule that forbids it. Both
are reported and left alone, not silenced and not "fixed", and that is why the excluded class prints a count
rather than being skipped. The one offender in the *unpoliced* 21 is `docs/journey.md:53`, a faithful capture of a
round whose gate did not yet emit the qualifier; it prints as `blind-not-fatal|`, it is not this ticket's surface,
and `docs/tickets/SG-F13-pairing-rule-scope.md` now owns the widening with that face and its block number named.

## What this ticket did not do

No bucket changed in the gate; no verdict-adjacent number moved; no generated face was hand-edited (the corrected
sentences are authored in `ci/coverage_report.py`); nothing was deleted; `spec/` was not touched.

## Erratum on the before/after leak table above

The two rows were captured with needles that could not match an escaped Windows path, so the column headed `LOGIN`
read 15 in both rows and the claim "no fatal class moved" was measured with a blind ruler. Re-measured after
`_escaped_forms()` went into `ci/process_leak_scan.py`: `LOGIN 15 -> 1111`, `HOSTROOT 13 -> 338+` on the same
content. What this ticket actually proved still stands - the four *verdict* readings did not move, and they are
re-read by the gate itself, not by this face. See `docs/FINDINGS-rev6.md` M12(a).
