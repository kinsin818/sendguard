# SENDGUARD FROZEN

Freeze date: 2026-10-10, sealed under the project's closing criteria
(10/10 PASS). THIS FILE IS THE LOCK. Later revisions may not add,
remove, or rename cases; additions go to backlog and require a new freeze.

**FREEZE REVISION 3 (contract-only; the 20 traps and their hex are unchanged) (2026-10-10, defect fix)**:
`spec/cases.yaml` was amended per `evidence/judgement/defects/sample-corruption.md`
(found by the python port): 9 corrupted sample hex values (T06/T07/T09a/T09b/T12/T13/
T15/T19a/T19b) replaced with the correct UTF-8 hex. No trap id / category /
locale / applicability changed; `freeze_revision: 2` + `rev2_note` added to the
yaml. Old sha256 of cases.yaml: `2708ae44f61f448db5ef9abcdb91e1a7a81484626b7edf8b70fca6a77f87b880`
(declared defective and superseded). All other locked artifacts unchanged.
Affected cells must be re-run with the new hex (never hand-typed names).

**FREEZE REVISION 4 (contract-only; the 20 traps, their hex and `spec/cases.yaml` are unchanged) (2026-10-12)**:
`spec/schema.json` renamed the producer field to `implementation_id` and gave it the value
pattern `^[a-z][a-z0-9-]{0,15}-port$`. Reason: the published values named sessions, producer codes and tool names
(1,150 occurrences across 880 result faces), which is production metadata about who staffed a lane, not a property
of any cell. Old sha256 of schema.json:
`52abbc86c8899f41e1889e71d35cdf73bd363204274e862bf6bcb2ab9f761435` (superseded, still in the published history).

What did **not** change, and why that is the whole cost of this revision: the per-record fingerprint
`spec_sha256` is the digest of `spec/cases.yaml`, which this revision does not touch - measured, not asserted:
`sha256(HEAD:spec/cases.yaml)` = `4ffeadca18318c92...` before and after. And `additionalProperties` is true
by design, so no record already written becomes invalid: a port that recorded extra fields is not punished for
it. The six ports therefore re-emit to **purge a leaking key from the data faces**, not to re-answer anything;
`python ci/equality.py` reads `54 / 24/44 / 4 / 121 / 2281` on the old faces and will read the same numbers on
the re-emitted ones. If those readings ever move because of this rename, it is not the rename that moved them.

The seal line above used to name a persona and an internal order word for the act of sealing. That wording is
itself published, so it is corrected forward rather than erased: the authority for a seal is
the contract-owner role, and who personally held it is in the history and is not a fact about the contract.

## Locked artifacts (SHA-256, public)

| file | sha256 |
|---|---|
| spec/cases.yaml | 4ffeadca18318c92feb16d6556a80804f89d80920147d0df60db40936d9516df |
| spec/gate.md | f3749d4311206c7e567bcf02661e332e28b75b892ff2fb0275504c701f8ed424 |
| spec/canonical.md | f3fe3122c131649d5df81d6c5331d0224dc270065f8ff46dd328d465324e6e69 |
| spec/attribution-tree.md | 286f81914c73a73986e5de234121ce159fd1bdf39126dc9b22b5560988bde805 |
| spec/validate.py | 66f8c0035981bf7c518378b96206309860057e215c08cad2f533dde26d87dfbe |
| spec/schema.json | 736ace2951a9520d6a9f627bbbc2503055805bef10c38eddfeb025514e28881d |
| spec/cell-identity.md | 9e2345e6d5346e3e5844ec06239d48b0eb4abe5e4c7471cec41969e45155dfa8 |
| spec/cells-required.json | e1e7e57f17eaeb7919723f5a8a34446b16a739609595821a85050880baed2c34 |

## 20 frozen traps (ids only; samples are hex-only per N12)

T01 T02 T03 T04 T05 T06 T07 T08 T09 T10 T11 T12 T13 T14 T15 T16 T17 T18 T19 T20
(count = 20; T09 and T14 carry multiple members; T17/T18 are T-LEN bisection
cells with G1-G4 verification grid: G1 base13 x(244,245,246), G2 base120
x(137,138,139), G3 base13 x(254,255,256), G4 base200 x(254,255,256);
G3 == G4 (255) is the domain-A internal self-check.)

## Pinned api_entry per language (implementations may not self-select)

node:   writeFileSync, createWriteStream, appendFileSync
python: open_wb, os.mkdir, pathlib.write_bytes, os.rename
go:     os.Create, os.WriteFile, os.OpenFile, os.Mkdir
java:   Files.write, Files.createFile, Files.newOutputStream, Files.move
csharp: File.WriteAllBytes, File.Create, FileStream, File.Move
rust:   std::fs::write, std::fs::File::create, std::fs::OpenOptions, std::fs::rename

T-API sub-cells (instrument self-check, not counted in the 20): python 4,
go 4, node 3 (the pinned lists above).

## Control cells (5, not counted in the 20)

T-CTRL-NAMETOOLONG, T-CTRL-ASCII, T-CTRL-ILLEGAL-CHAR, T-CTRL-PARSE,
T-CTRL-CANON. Expectations come ONLY from evidence/ctrl-baseline.md.

## Blind samples

- seed: 7f3c1a9e5b2d8f40c6e1a7b3d9f2e5c8a1b6d4f0e9c2a7b5d3f8e6c1a9b4d7f0
  (recorded at the initial freeze; unsealed after the first audit via blind-map.json)
- sealed map: evidence/freeze/blind-map.json (sha256 above)
- 5 real-world-shaped, nobody-picked names; reported separately from the 20
  construction traps.

## Freeze consequences

1. expectation column is 20/20 null; filling ANY expectation before
   measurement is a sealing violation.
2. No new trap/case/entry after this file; additions -> backlog.
3. api_entry pinned; an implementation picking any other entry -> blocked recorded,
   never "just pick one".
4. gate.md and attribution-tree.md are the only valid judgment procedures.
5. Samples are synthetic (no real usernames/emails/companies), hex-only
   (N12).

## rev3 changelog (2026-10-11 04:20:59 +0800, the maintainer)

Schema defects fixed, no trap was touched: `format_version` demanded the string "1" while every port writes integer 1 (this alone made every cell VOID under strict validation); `language` had no `typescript`; `name_encoding` carried two different meanings between schema.json and canonical.md, so the length field is now `length_unit` and `name_encoding` matches canonical. `verdict_via` became a required field: a legality verdict must name the tool asked. `spec/cell-identity.md` and `spec/cells-required.json` joined the locked set; the first, wrong `cells-required.json` is withdrawn by name in that file.

## rev4 changelog (2026-10-11 04:42:29 +0800, the maintainer)

Prompted by the TypeScript port's report. Closed sets were inconsistent between the two rulers: `spec/schema.json` was updated by rev3 and `spec/validate.py` was not, so no cell could satisfy both. Also: a fifth `read_result` word (`not_applicable`) so a cell whose create failed is not forced to claim it read something; the T-API clause no longer treats agreement as an instrument failure; the bisection regime is keyed by `longpath_mechanism` because a prefix-rewriting runtime shows the component ceiling on both path forms; `typescript` aliased to node's pinned entries; `extra` cells and cell-declared `sub_identity` honoured by the gate.
