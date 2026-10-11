# Contract round 9 — a proposal, not an applied change

Status: **proposal. `spec/` is untouched by this file.** Nothing here is sealed, nothing has been dispatched
against it, and every leg in `ci/` keeps judging the round-8 contract until the owner says otherwise. It is
written now because three of this morning's findings are the same decision seen from three sides, and the
owner should be able to make it with one word rather than by reading six files.

Authority: the sealed round is the eighth (`spec/FROZEN.md`, `freeze_revision: 2` in `spec/cases.yaml`, and the
manifest pin `spec_blob_sha256=8650a1863578231e…`). Changing `spec/cases.yaml` or `spec/schema.json` re-seals
the contract, which cascades: the manifest is regenerated, `spec/FROZEN.md`'s digest table is re-pinned, and
every cell's `spec_sha256` becomes stale until each port re-emits - which is precisely the state
`docs/spec-drift.md` was built to expose, and it would expose this change too.

## The one decision, in one line

**Say which verdict fields a port must answer for which case group, and give a boolean a way to say
"this answer does not exist here".** Everything else below is bookkeeping that follows from it.

## What is measured today (12:49 readings, all reproducible)

| fact | reading | source |
|---|---|---|
| fields the gate scores as a verdict | 10 | `ci/equality.py` `VERDICT_FIELDS` |
| of those, **required** by `spec/schema.json` | **1** (`os_legality_verdict`) | `python ci/validate_cells.py` → `verdict_fields_not_required=9` |
| of those, not even documented in the schema | 4 (`phantom`, `name_mutated`, `len_triple`, `name_landed_as`) | same, `verdict_fields_undocumented=4` |
| compared records with a blank verdict field, one port | 121 of 264×10 field-cells | `python ci/equality.py` → `verdict_not_recorded_pairs=121` |
| compared field-cells blank in **all six** ports | 10 | `docs/coverage.md` |
| cells where all six answered all ten fields, and matched | **4** | `docs/STATUS.md` |
| ports that record *which executable* answered | 3 of 6, in 3 field names and 3 shapes (`java` 74/74 `toolchain`+`jvm_self_report`, `rust` 174/174 string, `python` 123/125 path) | `docs/FINDINGS-rev6.md` M7 |
| ports that record nothing about it | 3 of 6 (`typescript` 0/87, `go` 0/203, `csharp` 0/50) | same |
| control cells stamped with a calibration result | 5/5 in five ports, **1/5 in `java`** | `docs/acceptance-S02.md` |

The precedent that makes this cheap rather than exotic: `read_result` already carries a fifth value
`not_applicable`, added for exactly this problem (nothing landed, so there was no read to perform). The
booleans have no such escape, which is why a port that legitimately could not round-trip a name either omits
the field (a blank) or writes `false` (a claim that it tried and failed).

## Option A — name the applicability, keep the schema permissive (recommended)

Add to `spec/cell-identity.md` a table: for each case group (`trap`, `ctrl`, `blind`, `len`, `tapi`), which of
the ten verdict fields must be answered, which may be `not_applicable`, and what a blank then means. Add
`runtime_executable` (one object: `path`, `version`, `resolved_how`) to `spec/schema.json` as a documented
property for every port. Do **not** add the nine fields to `required` yet.

- Cost: one spec edit + manifest regeneration; **no port re-runs** (nothing that exists becomes invalid, and
  blanks that the table blesses stay blessed).
- Instrument work I would do alongside, each with red and green arms: `ci/coverage_report.py` gains
  "blanks that the applicability table does not bless" as its own counted row; `ci/validate_cells.py` stops
  reporting `verdict_fields_not_required=9` and reports the per-group duty instead; a new arm proves that a
  blessed blank does not block `OUTCOME=PASS` while an unblessed one still does.
- What it buys: the four fully-recorded cells stop being an accident of which ports felt like filling fields,
  and the headline can then be widened deliberately, group by group.

## Option B — tighten `required` to all ten verdict fields

- Cost: every port re-emits every cell (six faces, 557 records today), the manifest and `FROZEN.md` re-pin,
  and `docs/spec-drift.md` will read `older=264` until they do. Cells where the answer genuinely does not
  exist become **failures** unless Option A's applicability table exists first.
- This is the wrong order: it makes ports invent values to satisfy a field list, which is the exact behaviour
  this project spends its whole morning trying to make visible.

## Option C — do nothing

- Cost: the product sentence keeps needing the caveat it has today ("24 cells with no conflict, of which 4
  fully recorded"), and the runtime-identity finding (`docs/FINDINGS-rev6.md` M7) stays an anecdote rather
  than a checked field. Acceptable for a portfolio piece; not acceptable if the claim is "pre-flight checking
  you can trust".

## What the owner actually needs to say

1. `A` / `B` / `C`;
2. if `A`: whether `runtime_executable` should be *required* (my recommendation: documented now, required next
   round after the three silent ports add it - requiring it immediately would invalidate 237 of 264 records at
   a stroke, which is true but not useful in the same breath as shipping);
3. nothing else in this file needs a decision: the two owed re-runs (`docs/tickets/`) and the java control-cell
   stamps are already dispatched work, not questions.

Until one of those three words arrives, `spec/` stays at round 8, the legs keep printing the blanks, and the
outward documents keep the pair-of-numbers rule (`cells_fully_recorded_and_identical` quoted beside
`cells_with_no_verdict_disagreement`) so nobody can quote the flattering half.
