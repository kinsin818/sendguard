# Cell identity and storage authority (contract patch 1)

Status: adds sentences the frozen spec never had. It does **not** edit `spec/cases.yaml`, `spec/gate.md` or
`spec/canonical.md`; those are re-sealed in one deliberate revision once the sealed expectation table is
filed, because a lock must move once, not while someone is reading it.

Why this file exists: `ci/equality.py` was pointed at the three ports already in the repo and returned
`NOT-COMPARABLE`. Measured reasons, all of them missing sentences rather than bad ports:

| measured | meaning |
|---|---|
| cross-port key intersection = **0** | the cell identity in use (language × entry × trap) cannot be compared across ports, because `api_entry` is a language-specific string |
| **21** cells hold several entries that disagree with each other | "what did Go answer for T01" currently has no single answer |
| **48** length cells collide on an unrecorded dimension | the root depth lives in the filename and not in the cell |
| python 117 / node 36 / go 27 distinct cells | the three ports did not run the same question set |
| 5 non-cell JSON files inside `results/` | a loader that skips unrecognised files makes a broken run look clean |

## 1. The equality key

A cell's identity for cross-port comparison is:

```
(case_group, case_id, sub_identity)
```

- `api_entry` is **not** part of it. It stays in the record as data — the T-API sub-cells exist precisely to
  show that one language does not agree with itself, and that is a finding, not a comparison key.
- `sub_identity` is an ordered, named set of extra dimensions, and it is **required** whenever a case is run
  more than once per port. Declared values:
  - `len` group: `base_len` (integer, the length of the directory path with no trailing separator)
  - cross-reader work: `builder`, `reader`
  - zip round-trip: `packer`, `extractor`
- A dimension that varies must appear as a named field inside the cell. Encoding it only in the filename is
  not identity — that is what produced the 48 collisions above.

## 2. Primary entry per (port, trap)

The equality digest uses the **primary** entry. Every other entry for the same cell is kept, published, and
reported as `entry_spread`, but it does not enter the digest.

| port | primary entry | why |
|---|---|---|
| python | `open_wb` | create-and-write with content is what a deliverer actually does |
| node | `writeFileSync` | same |
| typescript | `writeFileSync` | same runtime; the port is written in TypeScript, evidence says `TypeScript (Node runtime)` |
| go | `os.Create` | same |
| java | `Files.write` | one-step NIO write; `File` variants are kept as `entry_spread` |
| csharp | `File.WriteAllBytes` | one-step write |
| rust | `File::create` + write | same |

A port that cannot run its primary entry records `blocked` for that cell with the command and its exit code.
It may not silently substitute another entry, and it may not mark the cell passed.

## 3. Storage authority

- Authoritative: one file per cell, `results/<lang>.<os>.<arch>/<case_group>__<case_id>[__<sub>].json`.
- Derived: the aggregate `results/<lang>.<os>.<runtime_version>.json` is **generated** by
  `ci/export_aggregate.py` from the per-cell files. Nobody hand-writes it, and `ci/equality.py` re-derives it
  and refuses if the stored aggregate disagrees with the cells it claims to summarise.
- `results/` may contain nothing but cell files. Instrument dumps, manifests, phantom exports and audit
  captures move to `evidence/`. A file in `results/` that is not a cell is a defect the gate reports, not
  one it skips.

## 4. Denominator rule

The gate compares question sets before it compares answers. Two ports with different cell sets produce
`NOT-COMPARABLE` naming both directions of difference; it never compares the intersection and reports the
result as agreement. This is the specific way the old criterion let the project look finished while three
ports had answered three different questionnaires.

## 5. What this patch does not decide

- The `expectation: null` policy in the shipped spec stays (the divergence appendix needs it unpolluted).
  The independent expectation lives in `spec/expectations.sealed.md`, hashed at seal time, opened only after
  the port digests are in.
- Whether a given machine's answer depends on hardware (a reserved name with a device behind it) or on
  policy (`LongPathsEnabled`) is an environment fact, recorded per run, never folded into a verdict.
