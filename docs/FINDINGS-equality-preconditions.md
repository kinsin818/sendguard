# What must be pinned before "six ports, byte-identical" means anything

Found by building the gate and pointing it at the three ports already in the repo, 2026-10-11 01:31:42 +0800.
No port was blamed below for something a human could have avoided: each item is a missing sentence in the
frozen spec, and the spec was frozen before anyone had to compare two ports.

Gate run: `python ci/equality.py` → `OUTCOME=NOT-COMPARABLE`, rc=3.

## 1. Cross-port cell identity does not exist yet

The first version of the gate keyed cells on `(case_group, case_id, api_entry)` — the identity the order
itself defines (M15: a cell is language × API entry × trap). Measured result: **three ports, intersection of
keys = 0**, because `api_entry` is a language-specific string (`writeFileSync` / `os.Create` / `open_wb`).

So the equality claim cannot use that identity. The gate now keys on `(case_group, case_id)` and treats
`api_entry` as an internal detail — which immediately surfaces item 2.

## 2. A port may answer the same cell several times, and the spec does not say which answer is the port's

26 cells hold several entries; **21 of them disagree with each other** (all in Go, e.g. `trap/T01` via four
entries → two distinct verdicts). T-API exists precisely to expose that, so the disagreement is legitimate
data — but then "what did Go answer for T01" has no single answer, and equality across ports is undefined.

**Needed in the spec:** one `primary_entry` per (port, trap). The pinned entry lists already exist; the
designation does not.

## 3. The length cells collide on a dimension the cell does not carry

48 "same cell, two representations, different bytes" hits, all on `len/T17` and `len/T18`. Cause: the
binary-search rows vary by **root depth**, which is encoded in the filename but not in the cell. Two
different measurements therefore collapse into one identity.

**Needed:** `base_len` (or `root_depth`) as a required cell field, and part of the cell identity.

## 4. Each cell is stored twice, and neither is declared authoritative

Python: 239 cell records → 117 distinct cells. Node: 72 → 36. Go: 153 → 27. The aggregate file and the
per-cell files hold the same cells. That is fine as a convenience, but a claim of reproducibility needs one
authoritative representation and a rule that the other is generated from it — otherwise a future edit can
touch one and not the other, and the digest depends on which file the reader happened to open.

## 5. Non-cell JSON lives inside `results/`

`results/go.windows.go1.23.5/__.json` (a filename built from an empty name), `phantom.json` inside a port
directory, and three `_audit-*.json` / `_pyreader-manifest.json` files under `results/node/windows/`. The
gate reports them as malformed rather than skipping them silently — a loader that quietly ignores
unrecognised files is how a broken run looks clean.

## 6. The three ports did not run the same question set

Distinct cells: **python 117 / node 36 / go 27**. Under the old criterion ("find at least one divergence")
this was harmless — each port could report its own subset and divergences would still be harvested. Under
the equality criterion it is fatal, and it is the reason this gate checks denominators before it compares
anything.

## What happens next

1. Spec patch: `primary_entry` per (port, trap), `base_len` in the cell identity, authoritative-storage rule,
   and a naming rule that keeps non-cell artifacts out of `results/`.
2. Skeleton per port so a window fills only language behaviour and cannot invent its own identity.
3. `ci/selftest.py` with a green arm and a red arm for every gate, including this one — a gate that has only
   ever been seen refusing is not yet proven to work.
4. Then the ports: TypeScript (Node runtime), Java, C#, Rust written fresh; Python and Go re-run against the
   patched spec rather than inherited.
