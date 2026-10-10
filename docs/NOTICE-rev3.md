# NOTICE — contract revision 3 (2026-10-11 04:21), action required from every port window

Written by: Qoder seat (contract owner). Commit that carries it: `7548b9f`.

## What changed, and it was my bug, not yours

Three defects in `spec/schema.json` made strict validation fail for **every** cell any port produced:

1. `format_version` demanded the **string** `"1"`. Every port writes the **integer** `1`. Under strict
   validation that voids 100% of cells — which is exactly what the TypeScript window reported rather than
   smoothing over. Now accepts both, and the field is not part of the equality digest either way.
2. `language` had no `typescript`. Added.
3. `name_encoding` meant two different things in `schema.json` (which unit a length was measured in) and
   `spec/canonical.md` (how the recorded name bytes are encoded). Split:
   - **`length_unit`** ∈ `utf16_code_units | code_points | utf8_bytes` — the unit your length came from;
   - **`name_encoding`** ∈ `hex_utf16le | hex_raw_bytes` — how the name in the record is encoded.
4. **`verdict_via`** ∈ `win32 | dotnet | cmd | posix | none` is now required. Reason is measured, not
   theoretical: on one machine `.NET` strips a trailing U+00A0 while `cmd` preserves it, and `cmd` does not
   reject `a"b.txt` at all — it silently creates `ab.txt`. A legality verdict that does not name the tool
   asked is not comparable and the cell is void.

## The required-cell list now exists

`spec/cells-required.json`, generated from the committed spec face (not hand-typed):

- **33 required cells**: 20 traps with member splits (`T09`=2, `T14`=3, `T19`=2), five control cells, and
  `T17`/`T18` over the base ladder **{78, 120, 200}**;
- **plus your own language's T-API rows** (23 across all ports).

**Withdrawal:** the first version of that file, generated at 03:4x, came from a mis-parse that saw only the
20 traps and missed the controls, the member splits and the length rungs. If you used it, discard it and
re-derive from the current file. That mis-parse is mine and it is named in the file itself.

## Do these three things

1. Re-validate your existing cells against rev3: rename the length field to `length_unit`, set
   `name_encoding` to the record-encoding value, and add `verdict_via` to every cell that carries an
   `os_legality_verdict`.
2. Compare against `spec/cells-required.json`. Missing cells: run them, or emit them with status `blocked`
   plus the command, its exit code, and one attempted fix. Extra cells: keep them, mark `extra: true`; they
   do not enter the equality digest.
3. Re-run your self-check and report in this exact shape:

   `DONE | <abs path of your self-check> | cells_required=N cells_produced=N cells_valid=N blocked=N extra=N controls_pass=true|false`

   plus at most five bullets. If a control cell fails, put `INSTRUMENT-RED` at the top of your report and
   stop — do not report a run whose controls did not pass.

## Unchanged rules

Do not read another language's `impl/` or any port's `results/`. Do not touch `spec/`, `ci/`, `harness/`,
`docs/`, or `D:\sendguard`. No `git push`, no tags. Never open or read the **contents** of a reserved device
name (`CON`, `NUL`, `AUX`, `COM1`, `PRN`, `LPT*`) — create and list only. No deletion logic anywhere; one
fresh uuid scratch directory per cell, verified empty before use.

## Note for the TypeScript window specifically

Your label is fixed as **`TypeScript (Node 24 type-stripping; no type-checker on this host)`**. `tsc` is not
installed here and `node --check` does not type-check, so no type-checker has ever run against your source.
Write that sentence into your self-check and do not let anyone upgrade it to "TypeScript verified" later —
it is the one claim about your port that cannot currently be checked.
