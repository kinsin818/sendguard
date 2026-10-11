# SENDGUARD FROZEN (S01 freeze declaration)

Freeze date: 2026-10-10. Frozen by: main agent (doubao seat) per 军令 S01,
after S00 DoD 10/10 PASS. THIS FILE IS THE LOCK. S01 and later may not add,
remove, or rename cases; additions go to backlog and require a new freeze.

**FREEZE REVISION 3 (contract-only; the 20 traps and their hex are unchanged) (2026-10-10, P0 defect fix)**:
`spec/cases.yaml` was amended per `evidence/S02/defects/sample-corruption.md`
(found by W-PY): 9 corrupted sample hex values (T06/T07/T09a/T09b/T12/T13/
T15/T19a/T19b) replaced with the correct UTF-8 hex. No trap id / category /
locale / applicability changed; `freeze_revision: 2` + `rev2_note` added to the
yaml. Old sha256 of cases.yaml: `2708ae44f61f448db5ef9abcdb91e1a7a81484626b7edf8b70fca6a77f87b880`
(declared defective and superseded). All other locked artifacts unchanged.
All seats must read the new freeze; affected cells must be re-run with the new
hex (never hand-typed names).

## Locked artifacts (SHA-256, public)

| file | sha256 |
|---|---|
| spec/cases.yaml | 8650a1863578231ef75af28f22322ac8375aed7fdfc62a3b09f01cd496453261 |
| spec/gate.md | 6a3894573214b49889965104ea44c863d73dc09b386b8d838362c5b19ac46a50 |
| spec/canonical.md | f3fe3122c131649d5df81d6c5331d0224dc270065f8ff46dd328d465324e6e69 |
| spec/attribution-tree.md | 286f81914c73a73986e5de234121ce159fd1bdf39126dc9b22b5560988bde805 |
| spec/validate.py | 66f8c0035981bf7c518378b96206309860057e215c08cad2f533dde26d87dfbe |
| spec/schema.json | 52abbc86c8899f41e1889e71d35cdf73bd363204274e862bf6bcb2ab9f761435 |
| spec/cell-identity.md | 5c87c7c66cfe828ea304a6aa16d28d492cf36bf77d520bde293ba213955b10b7 |
| spec/cells-required.json | ed8a8a29c0eea99925659f6d0f2f63b94469654e1f793ab027b6e55a4a1a8cb8 |

## 20 frozen traps (ids only; samples are hex-only per N12)

T01 T02 T03 T04 T05 T06 T07 T08 T09 T10 T11 T12 T13 T14 T15 T16 T17 T18 T19 T20
(count = 20; T09 and T14 carry multiple members; T17/T18 are T-LEN bisection
cells with G1-G4 verification grid: G1 base13 x(244,245,246), G2 base120
x(137,138,139), G3 base13 x(254,255,256), G4 base200 x(254,255,256);
G3 == G4 (255) is the domain-A internal self-check.)

## Pinned api_entry per language (workers may not self-select)

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
T-CTRL-CANON. Expectations come ONLY from evidence/S00-ctrl-baseline.md.

## Blind samples

- seed: 7f3c1a9e5b2d8f40c6e1a7b3d9f2e5c8a1b6d4f0e9c2a7b5d3f8e6c1a9b4d7f0
  (recorded at S01 freeze; unsealed after S03 audit via blind-map.json)
- sealed map: evidence/S00/blind-map.json (sha256 above)
- 5 real-world-shaped, nobody-picked names; reported separately from the 20
  construction traps.

## Freeze consequences

1. expectation column is 20/20 null; filling ANY expectation before
   measurement is an M17 violation.
2. No new trap/case/entry after this file; additions -> backlog.
3. api_entry pinned; a worker picking any other entry -> blocked recorded,
   never "just pick one".
4. gate.md and attribution-tree.md are the only valid judgment procedures.
5. Samples are synthetic (no real usernames/emails/companies), hex-only
   (N12).


## rev3 changelog (2026-10-11 04:20:59 +0800, Qoder seat)

Schema defects fixed, no trap was touched: `format_version` demanded the string "1" while every port writes integer 1 (this alone made every cell VOID under strict validation); `language` had no `typescript`; `name_encoding` carried two different meanings between schema.json and canonical.md, so the length field is now `length_unit` and `name_encoding` matches canonical. `verdict_via` became a required field: a legality verdict must name the tool asked. `spec/cell-identity.md` and `spec/cells-required.json` joined the locked set; the first, wrong `cells-required.json` is withdrawn by name in that file.


## rev4 changelog (2026-10-11 04:42:29 +0800, Qoder seat)

Prompted by the TypeScript port's report. Closed sets were inconsistent between the two rulers: `spec/schema.json` was updated by rev3 and `spec/validate.py` was not, so no cell could satisfy both. Also: a fifth `read_result` word (`not_applicable`) so a cell whose create failed is not forced to claim it read something; the T-API clause no longer treats agreement as an instrument failure; the bisection regime is keyed by `longpath_mechanism` because a prefix-rewriting runtime shows the component ceiling on both path forms; `typescript` aliased to node's pinned entries; `extra` cells and cell-declared `sub_identity` honoured by the gate.
