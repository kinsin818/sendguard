# SG-F1 — Python lane: re-stamp the 27 cells that still carry the previous spec fingerprint

**Race guard first.** Before writing anything, check whether this surface is already owned: does
`results/python.windows.x64/` contain files with an mtime newer than this ticket's dispatch (13:0x +0800 on
2026-10-11), and does `git status --porcelain -uall -- results/python.windows.x64` list anything? If a writer
is already in there, **stop** and report `BLOCKED | reason=tree_already_owned | <the faces you saw>`. Do not
re-run over a colleague's half-finished face, and do not "help" by finishing their files.

## Why this exists

`python ci/spec_drift.py` (added today, `docs/spec-drift.md`) measures which fingerprint each compared cell was
stamped with. Reading at 12:49: **27 of the 264 compared records carry `spec_sha256=b1eb629c…` (the face
committed at 05:05) instead of the current `8650a186…`** - all of them Python's trap, blind and T-API cells.
The same leg proves the delta between those two spec faces touches only `T17`/`T18`, so **nothing you recorded
was asked under different rules**; this is a bookkeeping gap, not a correctness gap. It is also the cheapest
credibility win left in the project: one re-run takes the stale count from 27 to 0, and until then every
outward document has to carry the caveat "237 of 264 records are stamped current".

## Allowed surface (prefixes, smallest set that covers the write)

- `results/python.windows.x64/`
- `evidence/S02/python-selfcheck.md`

Nothing else. **`spec/`, `ci/`, `docs/`, `tool/`, and every other port's `results/` face are out of bounds**;
if you believe one of them must change, write the case in your report instead of editing it. `impl/python/` is
yours to touch **only** to make the harness read the current committed spec face - the recording logic itself
must not change, because a harness that alters answers while claiming to re-stamp is exactly what this project
audits for.

## What to do

Re-emit the same cells under the current committed spec face, so each record's `spec_sha256` equals
`spec/cells-required.json`'s `spec_blob_sha256`. Write **additively** and never wipe the face: this lane lost
74 cells at 07:16 today by rebuilding in place, and the recovery was a documented "they do not exist", not a
restatement. Commit as you go (one commit per group of cells is fine) so nothing sits uncommitted while you
work on the next batch.

## Criteria — every one is a command, and the reading below it is what must appear

1. `python ci/spec_drift.py` → **rc=0** and the line `wrote docs/spec-drift.md … older=0` (today: `older=27`).
2. `python ci/equality.py` → **rc=1, `verdict_disagreements=54`**. The disagreement count must not move: you
   are re-stamping, not re-answering.
3. `python ci/validate_cells.py` → **rc=0, `invalid=0`** (unchanged).
4. `python ci/gap_report.py` → `total_missing=0` for all six ports, and Python's matched count stays 44/44.
5. `git status --porcelain -uall -- results/python.windows.x64` → 0 lines after your last commit (the cells
   must be in history, not only on disk — `evidence/S10/cold-clone-20261011b.md` shows what an uncommitted
   face does to a stranger's reading).

**If criterion 2 moves in either direction, stop and report it as a finding, do not reconcile it.** A re-stamp
that changes a verdict means the two runs disagreed, which is a result about the harness and belongs in
`docs/journey.md`-style disclosure, not in a quiet re-record. If you cannot hold the number steady, the honest
deliverable is the diff plus your explanation, not a matching number.

## Deadline and reporting

Absolute deadline: **2026-10-11 15:00 +0800**. Reply with exactly one line:
`DONE | <absolute path of your self-check file> | 1=rc:N 2=rc:N 3=rc:N 4=rc:N 5=rc:N`
or `BLOCKED | <item, exact command, one next human action>`. `rc=0` with no output is a contradiction, not a
pass — quote the line the command printed.

## Out of scope for this ticket (do not start these)

Applicability of blank verdict fields, a `runtime_executable` field, tightening `spec/schema.json`'s `required`
list. Those are contract round 9 and are written up as a proposal in `docs/NOTICE-rev9-proposal.md` waiting on
the owner's word. A port that "helpfully" edits the spec while re-stamping its cells would turn a
bookkeeping fix into an unauthorised contract change.
