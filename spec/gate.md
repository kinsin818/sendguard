# SENDGUARD Gate Discipline (locked at S01 freeze)

Every rule in this file is frozen BEFORE any worker spawns. Nobody (including
the main agent) may reinterpret it mid-run; changes require a FROZEN.md update.

## 1. Judgment gate (S03) - Go / No-Go only, no "pending"

- Go looks ONLY at type II + type IV':
  - II  - bytes_written vs bytes_on_disk (disk truth after a "success").
  - IV' - same language, same api_entry: `len(request name)` vs
          `len(enumerated on-disk name)` (normalization drift / stripping).
- I (block or not), III (dep count), cross-language unit difference are DATA
  COLUMNS, not gate criteria.
- Zero hits on II+IV' -> judge `spec_or_isolation_failure` first (check
  expectation prefill / worker cross-visibility / copied baseline), rework the
  whole batch, re-run; only rework-then-still-zero -> No-Go.
- `instrument_conflict` -> INSTRUMENT-RED + rework; it is NOT a Go hit source.

## 2. T-API instrument self-check gate

- T-API cells enter the matrix as data cells and become whitepaper page-3
  selling points; they do NOT gate Go/No-Go.
- T-API hit count == 0 -> `instrument_failure`: harness rework, S02 batch
  voided and re-run. Neither Go nor No-Go may be issued on void data.

## 3. Four-type divergence counting (locked pre-run)

| type | counts |
|---|---|
| I  | ok / err_at_parse / err_at_syscall / hang |
| II | bytes_written vs bytes_on_disk |
| III| deps_direct / deps_total (per cell x entry) |
| IV | length counting unit triple (cp / utf16 / bytes) |

IV' (above) is the gate form; IV (cross-language unit) is a data column.

## 4. Verification-cell vs bisection deviation triage (Qoder 3-5)

| |verification - bisection| | verdict |
|---|---|---|
| <= 1 code unit | consistent; cell enters the formal matrix |
| > 1 unit, other cells of domain normal | unresolved (evidence only, not whitepaper, instrument NOT guilty) |
| > 1 unit, systematic domain shift (>= 2 cells same direction) | INSTRUMENT-RED: domain re-run |

## 5. Bisection override procedure (Qoder 3-3)

Only the arbitration seat may sign a bisection downgrade. Basis: domain B four
base tiers each hit `259 - base - 1` EXACTLY (zero tolerance), boundary code 3.
Flow: (1) S03 gate verifies domain B four tiers + G1/G2 six points -> record
`linear-model-confirmed`; (2) arbitration seat signs downgrade;
(3) taking-data seat re-checks domain A four tiers all == 255 and domain C ==
NAME_MAX; any failure keeps the bisection leg. Tolerance: the linear model is
a zero-tolerance equality; +/- 1 code unit applies only to verification-vs-
bisection deviation, never mixed.

## 6. Attribution discipline (see attribution-tree.md)

- attribution_layer in {L1, L2, L3, L3_interaction} via 2x2 + third question.
- Main L3 count EXCLUDES interaction cells; external divergence counts are
  deduped by mechanism_class.
- L3 == 0 -> whitepaper MUST state "six-language necessity is not proven by
  this matrix"; project demotes to a cross-platform delivery cost study.

## 7. Audit 5 checks (fresh independent external model, M17)

1. expectation was ever prefilled (incl. predictions archive)
2. hit criteria changed after the fact (docs commit time vs result time)
3. instrument_conflict cells mixed into the formal matrix
4. T11 actually run on pinned entry; unresolved really lands on T11
5. failures printed as-is (no evidence deletion)

## 8. Instrument rules

- Control cells: any mismatch -> INSTRUMENT-RED, re-run 3x to verify
  instrument; control cells are for verifying the ruler, not producing data.
- CANON control: both instruments same payload -> identical sha256, else
  INSTRUMENT-RED.
- Judgment numbers parse from result JSON only; worker report text is never
  parsed for gate decisions.
- "own created list" minus directory enumeration: every extra entry must be
  claimed by some language; unclaimed -> INSTRUMENT-RED.

## 9. Anti self-deception

- The gate exists for the six-fresh-rewrite scenario (M10): if brand-new
  implementations in the first three languages run zero divergence, we must
  have the courage to stop. Skipping the gate because "we measured before" is
  an M17 violation.

## 10. Data-integrity side rails

- Every probe action: 5s timeout -> `hang`.
- path_view AND dir_view both recorded per cell (M2); bytes_on_disk authority
  is dir_view; view_divergence is itself a headline column.
- errno / winerror stored verbatim (M16).
- Batch result cells: `control_pass: true` required; zero "conflict-but-not-
  archived" cells (all conflicts -> evidence/S02/conflicts/).
