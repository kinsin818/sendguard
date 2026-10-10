# SENDGUARD FROZEN (S01 freeze declaration)

Freeze date: 2026-10-10. Frozen by: main agent (doubao seat) per 军令 S01,
after S00 DoD 10/10 PASS. THIS FILE IS THE LOCK. S01 and later may not add,
remove, or rename cases; additions go to backlog and require a new freeze.

## Locked artifacts (SHA-256, public)

| file | sha256 |
|---|---|
| spec/cases.yaml | 2708ae44f61f448db5ef9abcdb91e1a7a81484626b7edf8b70fca6a77f87b880 |
| spec/gate.md | 5b36eb45e8deed82f2d86400c291aaeded883274453fcf78ae856a7e2c8d793b |
| spec/canonical.md | 64d8addcf36f6e8ead7933fb0089d95ebee0746814281f13050ea180c161d20a |
| spec/attribution-tree.md | 286f81914c73a73986e5de234121ce159fd1bdf39126dc9b22b5560988bde805 |
| spec/validate.py | f19a5d142d737997edf35b2b4ec88b6ab5340b2684c836b52ea89703cd746587 |
| spec/schema.json | f387ec4bc80a4fbff9c9128e1247d2a5297fc473c2551b4d301d1bf3d81af129 |
| evidence/S00/blind-map.json | 289188cfbc6a1efe460e9548380fc3aa4d18901c0bd39c134570e228792d574c |

S03 audit compares HASHES of these files, not "reads the same".

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
