# SG-F8 - the public data contract must carry product identity, not production metadata

Opened 2026-10-12 by the seat that owns `ci/` and the contract, on the owner's ruling of the same morning:
**do not rewrite this repository; fix the interface.** The measured blast radius is what makes that the cheap
option, and it is printed here rather than asserted: 11 non-data faces, 17 lines, **zero** of them in the
judging apparatus.

## The defect, measured

`spec/schema.json:75` declares a property `worker_id`. Six ports write it, and the published values name the
production side rather than the product side:

| value in the public tree | occurrences | what it discloses |
|---|---|---|
| `seat-qoder-rust`, `seat-qoder-python-port`, `seat-qoder/csharp-port`, `seat-qoder-java`, `seat-qoder-typescript`, `seat-qoder` | 691 | session/window identifiers of the studio |
| `W-GO/qianwen` | 161 | which engine staffed one lane |
| `W-PY`, `W-NODE` | 404 | seat codes from the role assignment table |
| `test` | 1 | a fixture value that leaked into a result face |

Total `worker_id` occurrences in the published tree: **1,150**, across 880 result faces and 63 evidence faces, all
generated. A reader can currently reconstruct *who produced which cell* from the deliverable itself, which
answers a question the artifact was never meant to answer. The public tree should answer "is this software
correct?", not "how was the work organised?".

Two additional faces carry the same boundary error in narrative form and are handled by **SG-F9**, not here:
`docs/roles.md` (the seat/persona assignment table) and `spec/FROZEN.md` line 3 (`Frozen by: main agent (doubao
seat) per 军令 S01` - the seal record naming the studio).

## What the field should become

A rename is not the fix; the fix is a policy about what an identity field may contain.

**Keep** (reproducibility metadata, all of it about the artifact): implementation label (`python-port`,
`rust-port`, ...), toolchain/runtime version, harness version, the executable path already recorded by three
ports, spec digest, input digest.

**Remove** (production metadata): session and window identifiers, seat codes, persona or engine names, any
value that ties a cell to a staffing decision, internal project names.

Structural rule for the new field, so this cannot rot again: `implementation_id` must match
`^[a-z][a-z0-9-]{0,15}-port$`. A value containing a path separator, an underscore-prefixed handle, a capitalised
persona name or a model name is rejected at validation time, not by review. The regex is the disclosure scan's
hook, and the scan itself is §4 below.

## Bundling requirement - this does not open a second contract round

Renaming a schema property changes `spec/schema.json`'s digest, which re-seals the contract and stales every
cell's `spec_sha256` until all six ports re-emit. That is exactly the cascade `docs/NOTICE-rev9-proposal.md`
already describes for the blank-legality decision. **Therefore: this change rides in the round-9 seal, one seal,
one re-emit for six ports.** A separate tenth round for a 17-line change would make six ports rebuild twice to
buy nothing. `spec/FROZEN.md`'s digest table is re-pinned in the same seal, and `docs/spec-drift.md` will show
the stale window honestly rather than hide it.

## Allowed surface

- this ticket file only, until the seal: `docs/tickets/SG-F8-public-interface-process-metadata.md`
- at seal time, by the contract owner: `spec/schema.json`, `spec/FROZEN.md`, `docs/NOTICE-rev9-proposal.md`
- by each port, in its own lane: the emit sites listed below
- by the `ci/` owner: `ci/validate_cells.py` (the second ruler - it and `spec/schema.json` must read one closed
  field dictionary, since they were once caught disagreeing), `ci/selftest.py` for the new arms, the new
  disclosure leg, and the generated faces that carry the field name

Ports may not edit `spec/`, `ci/`, or another lane's files.

## What the seal actually costs - and where this ticket's first version was wrong

Measured at the tip after the rename landed: `spec/schema.json` sets `additionalProperties: true`, and a record's
`spec_sha256` is the digest of `spec/cases.yaml`, which this change does not touch. So the claim in the first
version of this ticket - that the rename "stales every cell's `spec_sha256` until all six ports re-emit" - **was
wrong**, and the cost of the change is correspondingly smaller: no fingerprint breaks, no record is invalidated,
and `python ci/equality.py` reads the same `54 / 24/44 / 4 / 121 / 2281` it read before. The six ports' re-emit is
a **purge of a leaking key from the data faces**, not a rebuild under penalty, and that is the honest framing to
send them.

## The 11 faces and their line counts (measured, 18 lines - not 32)


`spec/schema.json` 1 - `impl/python/sg_python.py` 5 - `impl/rust/run_cells.py` 3 - `impl/typescript/src/runner.ts` 2 -
`impl/csharp/run_csharp.py` 1 - `impl/go/main.go` 1 - `impl/go/rederive/celljson.go` 1 - `impl/java/tools/run_cells.py` 1 -
`impl/python/sg_run.py` 1 - `impl/python/sg_selfcheck.py` 1 - `impl/rust/src/probe.rs` 1.

## Value mapping each port must apply (measured occurrences at the tip)

| value published today | occurrences | becomes |
|---|---|---|
| `W-PY` | 241 | `python-port` |
| `seat-qoder-rust` | 174 | `rust-port` |
| `W-NODE` | 73 | `node-port` |
| `W-GO/qianwen` | 154 | `go-port` |
| `seat-qoder-python-port` | 123 | `python-port` |
| `seat-qoder-typescript` | 87 | `typescript-port` |
| `seat-qoder-java` | 86 | `java-port` |
| `seat-qoder/csharp-port` | 50 | `csharp-port` |
| `seat-qoder` | 49 | the port that wrote it, named as a lane |
| `test` | 1 | a fixture value that reached a result face; that port must say whether the cell is a real record |

Total `worker_id` occurrences: **1,150**. A port re-emitting with any value outside
`^[a-z][a-z0-9-]{0,15}-port$` is refused by `ci/validate_cells.py`, whose arms A25-A29 cover both the schema
pattern and the fact that old records are not invalidated by the rename.

## Acceptance criteria

1. the sealed schema declares `implementation_id` with the value regex above and **no** `worker_id`;
   `ci/validate_cells.py` rejects a value outside the regex, with a red arm (a planted `seat-qoder-x` value is
   refused) and a green arm (`python-port` passes) - a validator that has only been seen refusing is the
   decoration this project has caught itself building three times already;
2. each port re-emits its canonical face; the re-emit is by the port's own author, and the port's report names
   the commit it re-ran at;
3. `python ci/spec_drift.py` reaches CLEAN for the new round: zero records on a stale digest, and the
   stale-window between seal and re-emit is visible on `docs/spec-drift.md` rather than edited out;
4. equality readings are unchanged by this ticket - **the numbers before and after must be identical**
   (`verdict_disagreements`, `verdict_identical_cells`, `cells_fully_recorded_and_identical`,
   `verdict_not_recorded_pairs`), because a metadata rename that moves a verdict means it was not a metadata
   rename. The before/after pair is printed in the acceptance row, from the same batch;
5. no `worker_id` remains in any *generated public* face at the new tip, asserted by a scan over `git ls-files`
   at the tip rather than over the work tree; the same scan prints its denominator
   (`files_scanned=`, and `hits_by_class=` for the four classes: session id / seat code / persona-engine name /
   internal project name);
6. the disclosure leg is standing, not one-off: it runs in `ci/refresh_all.py`, exits 3 on an unreadable tree
   (an instrument failure is never a measurement), and refuses to run without naming the root it scanned;
7. history is not rewritten. `git log` still contains every old value, and the errata is append-only: a dated
   line in `docs/claim-boundary.md` and one in each affected narrative face stating that the field was public,
   is public in history, was renamed forward, and why. No commit claims it "never" appeared.

## Do not

- Do not delete the field to make the scan pass. It carries reproducibility information the project needs; the
  fix is what the value may say.
- Do not open a second contract round for this. See the bundling requirement.
- Do not touch `D:\sendguard` (read-only evidence) or rewrite any pushed commit.
- No deletion logic anywhere (rule M19): the 880 stale result faces are superseded by re-emits, not removed.
