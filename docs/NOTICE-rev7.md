# NOTICE — contract rev7 (2026-10-11 06:0x): the length family was never specified, and it shows

Second completion of an unfilled field, not a change of requirement. rev6 pinned the control-cell samples;
rev7 pins what the two length components are made of. **This is the last contract change tonight.**

## Why: read what the six ports actually recorded for `len/T17` at `base_len=78`

| port | `name_source` decoded | `len_triple` as recorded |
|---|---|---|
| C# | `T-LEN-PATH (length bisection, G1-G4)` | `[48, 48, 48]` — which is the length of that label |
| Go | `aaaaaaaaaaaaaaaa…` | `255/255/255` |
| Java | `0123456789abcdef0123456789abcd…` | `{code_points: 256, …}` |
| Python | `f64c93203nnnnnnnnnnn…` | `{requested: {code_points: 180…}, landed: …}` |
| Rust | `t.bin` | `{code_points: 32739, …}` |
| TypeScript | `61` (the two characters, not their hex) | `[255, 255, 255]` |

Six different questions, and three different quantities called "length". The root cause is in the frozen
spec itself: `sample_hex` for T17 and T18 was written as **prose** — `T-LEN-PATH (length bisection, G1-G4)` —
and one port copied that prose verbatim as the name it "created". Nothing else about the length family was
ever pinned, so the twelve length cells are currently excluded from the comparison as `unpinned_input` and
this project has no comparable length evidence at all.

## The rule, now in `spec/cases.yaml`

```
len_fill:
  unit_hex: "61"            # one code unit: U+0061 LATIN SMALL LETTER A
  rule: "repeat unit_hex until the component is exactly base_len code units, then append nothing"
  applies_to: [T17, T18]
  name_source_rule: "name_source is the hex of the component that was actually passed to the API, not a label"
```

## Three things to record, and where each belongs

1. **`name_source`** = hex of the exact string you handed the API. Not a case label, not a description, not
   the characters `6` and `1` standing for a byte. If your filler is 78 `a`s, `name_source` is
   `6161…61` (156 hex characters).
2. **`len_triple`** = the three widths **of that name** (code points / UTF-16 code units / UTF-8 bytes). For
   the pinned filler all three equal `base_len`, and if they do not, your port is counting something else —
   say so in your self-check rather than filing the other number.
3. **The measured ceiling** is a different quantity and does not belong in `len_triple`. Put it in
   `len_ceiling` (whatever your bisection converged to) and keep your tiers, emoji runs and CJK runs as
   `extra: true` cells exactly as they are — that is where the "按码元判还是按字节判" story lives, and it is
   evidence, just not this comparison.

## What to do

Re-emit the twelve required length cells — `len/T17` and `len/T18` at `base_len` ∈ {78, 120, 200} ×
`path_form` ∈ {plain, extended} — under rules 1-3. Nothing else you landed is invalid: blind, control and
trap cells stay as they are.

Reply one line:

`DONE | <abs path> | len_cells=12/12 name_source_is_the_passed_bytes=yes|no len_triple_is_the_name=yes|no ceiling_field=len_ceiling|absent controls_pass=true|false`

Deadline **07:30** host clock, unchanged. If a rung is unreachable, emit it with `run_status: blocked` plus
the command, its exit code and one attempted fix.

Unchanged: do not read another port's `impl/` or `results/`, no `git push`, no edits to `spec/`, `ci/`,
`docs/`, `harness/`, no deletion logic (M19), never open the **contents** of a reserved device name.
