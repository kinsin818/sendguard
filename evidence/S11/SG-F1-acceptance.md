# Acceptance record — SG-F1 (Python lane, spec-fingerprint re-stamp)

Seat: delivery (`d9242392`). Host clock 2026-10-11 13:20 +0800.
Ticket: `docs/tickets/SG-F1-python-restamp.md`, dispatched 13:05. Worker return: committed its own work as
`e0d80a8` ("SG-F1: re-stamp the python cells to the current spec fingerprint, no answer moved") and reported
in `evidence/S02/python-selfcheck.md`.

## Verdict: ACCEPTED on all five criteria, read by this seat's own instruments, not by the worker's summary

| # | criterion (from the ticket) | expected | read at 13:20, work tree = HEAD `e0d80a8` | rc |
|---|---|---|---|---|
| 1 | `python ci/spec_drift.py` | `older=0` | `compared=264 current=264 older=0 unstamped=0 older_unresolvable=0 affected_by_delta=0` → `OUTCOME=CLEAN` | 0 |
| 2 | `python ci/equality.py` — the disagreement count must not move | 54 | `verdict_disagreements=54 verdict_identical_cells=24/44 cells_fully_recorded_and_identical=4 verdict_not_recorded_pairs=121 required_cells_missing=0` | 1 (RED = the measurement) |
| 3 | `python ci/validate_cells.py` | `invalid=0` | `invalid=0 missing_faces=0 verdict_fields_not_required=9 cells_omitting_a_compared_field=371` | 0 |
| 4 | `python ci/gap_report.py` | every port 44/44 | `ports=6 total_missing=0` | 0 |
| 5 | no faces left uncommitted in the lane's own directory | 0 lines | `git status --porcelain -uall -- results/python.windows.x64` → 0 | 0 |

Criterion 2 held, so this was a re-stamp and not a silent re-answer: the 27 records that had been produced
under the 05:05 face now carry `8650a186…`, and no verdict moved. The gate's artifact and every derived
document were regenerated after it (`python ci/refresh_all.py` → `OUTCOME=CLEAN refusals=1
tool_failures=0`, the single refusal being criterion 2's RED).

## What the ticket got wrong, which is my defect and not the lane's

The Allowed-surface list named `results/python.windows.x64/` and
`evidence/S02/python-selfcheck.md`, but the lane's own instrument dumps (`sg_run_summary.json`, the
self-check logs) belong under `evidence/` per `spec/cell-identity.md` §3. The worker therefore had to choose
between two of its rules and wrote: *"Instrument dumps sit under `impl/` because the only evidence path this
seat may write is this single file, while cell-identity section 3 says dumps belong in `evidence/` — noted,
not resolved by me."*

That is the correct behaviour by a worker (report, don't silently pick) and the correct lesson for a
dispatcher: **an Allowed-surface list must cover the paths the project's own rules require the deliverable to
touch, or the ticket hands the worker a rule conflict and gets whichever resolution is convenient.** SG-F1 is
amended in place with that line; SG-F2 and the F3 shape were written with the evidence directory included.

## Not accepted, deliberately left open

- The 121 blank verdict field-cells and `cells_fully_recorded_and_identical=4` are unchanged by this ticket -
  they are the round-9 contract question (`docs/NOTICE-rev9-proposal.md`), not a lane's sloppiness.
- The recording choice that keeps `name_landed_as` blank - "the component is already published as
  `name_source`, so stamping it twice is a recording decision, not missing evidence" - was raised by the
  **TypeScript** lane at 12:02 about its own cells (`evidence/S02/typescript-selfcheck.md`), not by this one.
  It belongs to the same round-9 question, and both lanes declined to answer it for the owner, which is right.
- This ticket says nothing about Python's 33 extra cells or the 27 that were stamped `b1eb629c`: the latter is
  now 0, and `extra` publishing is by design (`docs/GAP.md` reads `total_missing=0`, and extra cells are
  published, never compared).
