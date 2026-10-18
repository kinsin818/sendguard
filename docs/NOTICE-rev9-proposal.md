# Contract round 9 — a proposal, not an applied change

Status: **proposal. `spec/` is untouched by this file.** Nothing here is sealed, nothing has been issued
against it, and every leg in `ci/` keeps judging the round-8 contract until the maintainer says otherwise. It is
written now because three of this morning's findings are the same decision seen from three sides, and the
maintainer should be able to make it with one word rather than by reading six files.

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
| control cells stamped with a calibration result | 5/5 in five ports, **1/5 in `java`** | `docs/acceptance.md` |
| ports that declare whether a Windows-shaped trap even applies on this OS | **1 of 6** (reading 13:26, work tree: `java` 81 records `true`, 5 `false`; the other five write the field nowhere) | `python ci/validate_cells.py` → "Who declares whether a question applies on this OS" |

The last row is the one that makes the applicability question answerable rather than rhetorical: the field
`spec_applicable_on_windows` exists in the schema and in the records, **is read by no leg**, and is written by
one port as a habit. A convention kept by one port is not a contract - either round 9 gives it a rule (who must
write it, on which case groups, and what a `false` licenses to be blank) or the field should be deleted rather
than left as a private dialect that flatters itself into being evidence.

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

## What the maintainer actually needs to say

1. `A` / `B` / `C`;
2. if `A`: whether `runtime_executable` should be *required* (my recommendation: documented now, required next
   round after the three silent ports add it - requiring it immediately would invalidate 237 of 264 records at
   a stroke, which is true but not useful in the same breath as shipping);
3. **Whether a control cell's stamp has to say where it came from.** Measured at 13:34 by
   `python ci/validate_cells.py`: 30 control cells across six ports carry `control_pass=true` and **zero** carry
   any pointer to the command that produced it, because no contract round asks for one (`control_pass_evidence`
   is not a field anywhere except in a ticket this machine wrote and then retracted - see
   `docs/tickets/F2-*.md`'s amendment). Either the contract names it and every port re-stamps with a source,
   or the calibration marks stay assertions a reader cannot re-check, and the whitepaper should stop implying
   they are measurements.
4. Nothing else in this file needs a decision: the two re-runs that were owed have both landed
   (`evidence/closing/F1-acceptance.md`, `evidence/closing/F2-acceptance.md`), and the OS-portability work is
   written up but unscheduled (`docs/tickets/F3-os-portability.md`), waiting on 1-3 above and on your
   priority.

Until one of those three words arrives, `spec/` stays at round 8, the legs keep printing the blanks, and the
outward documents keep the pair-of-numbers rule (`cells_fully_recorded_and_identical` quoted beside
`cells_with_no_verdict_disagreement`) so nobody can quote the flattering half.


## Added 2026-10-12: a fourth item rides this same seal, and no round opens for it alone

The maintainer ruled this morning that this repository is **not** rewritten. The measured blast radius of the disclosure
fix is 11 non-data faces and 17 lines (1 in `spec/schema.json`, 16 across the six ports' emit sites), and nothing
in the judging apparatus reads the field - `ci/`, `tool/` and the generated `docs/` faces score 0 hits. See
`docs/tickets/F8-public-interface-process-metadata.md` for the change and
`docs/tickets/F9-narrative-faces-production-metadata.md` for its narrative half.

Why it belongs in this round rather than a tenth: renaming a schema property changes `spec/schema.json`'s digest,
which re-seals the contract and stales every record's `spec_sha256` until all six ports re-emit. Two seals would
make six ports rebuild twice for what one rebuild delivers, and `ci/spec_drift.py` would show two stale windows
where one is the honest count.

What the seal must carry in one act:

1. `worker_id` removed from `spec/schema.json`; `implementation_id` added with value shape
   `^[a-z][a-z0-9-]{0,15}-port$`, enforced by `ci/validate_cells.py` in both directions - a planted pass value
   refused, `python-port` accepted;
2. `spec/FROZEN.md`'s seal line re-worded in product-side terms, its digest table re-pinned in the same commit;
3. the two rulers (`spec/schema.json` and `ci/validate_cells.py`) reading one closed field dictionary, since they
   were once caught disagreeing;
4. `docs/claim-boundary.md` gaining a row that separates **product provenance** - runtime, toolchain, harness
   version, kept because verdicts demonstrably flip with the executable - from **production metadata**, which
   port was staffed by whom, not part of any cell's correctness and not published from here on.

What a seal cannot undo, stated rather than implied: the field and its values are already in the published
history - 1,150 occurrences over 880 result faces and 63 evidence faces - plus the narrative faces. History is not
rewritten on the maintainer's rule, so the forward correction is paired with an errata row naming what was public,
and no face may read as though it always was clean. `python ci/process_leak_scan.py --repo-root .` is the standing
leg; at the time of writing it reports
`OUTCOME=RED ... fatal_by_class=HOSTROOT:14,IDENTITY:1134,LOGIN:17,RETIRED:1141` against this tree and
`OUTCOME=CLEAN files_scanned=5 FATAL=0` against a sibling repository, so a future `CLEAN` is a reachable state and
not a hope.

## Erratum (2026-10-12)

The reading quoted above (`HOSTROOT:14, IDENTITY:1134, LOGIN:17, RETIRED:1141`) was measured with needles that could
not match an escaped Windows path, so the profile-path and tree-path counts it prints are lower bounds of the wrong
kind - not conservative, simply blind. Corrected counts and the reason are in `docs/FINDINGS-rev6.md` M12. Any
proposal text that relies on those numbers must re-read them, not reuse them.
