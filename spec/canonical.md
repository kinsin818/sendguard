# SENDGUARD Canonical Status Words (Closed Set)

Status words are a closed set. A measurement cell whose status word is not in this file MUST be judged `VOID`; no window may invent its own word. Any addition requires a FROZEN.md change (S01 gate discipline).

## 1. Cell verdict (outer level)

| word | meaning |
|---|---|
| `valid` | Cell passed schema + status-word checks and is eligible for the matrix. |
| `void` | Cell has an unknown status word, missing required field, or failed schema; excluded from all tables. |
| `instrument_red` | The instrumentation itself failed (control mismatch, hash conflict, instrument conflict); the whole round is re-run, not patched. |

## 2. case_group

| word | meaning |
|---|---|
| `trap` | One of the 20 frozen traps (T01-T20). |
| `ctrl` | One of the 5 control cells (T-CTRL-*), not counted in the 20. |
| `tapi` | T-API instrument self-check cell, not counted in the 20. |
| `blind` | Blind sample (5), not counted in the 20. |
| `len` | T-LEN path/component length binary-search cell (T17/T18), not counted in the 20. |

## 3. create_result (creation side)

| word | meaning |
|---|---|
| `ok` | Create succeeded (bytes_written recorded). |
| `err_at_parse` | Language rejected before syscall (parse-time). |
| `err_at_syscall` | OS rejected at syscall. |
| `hang` | 5-second hard timeout; process hung. |

## 4. error_stage (five values, unchanged from vFinal)

`parse` / `syscall` / `fs` / `tool` / `null` (no error).

## 5. read_result (observation side, 4 values - 2nd-round verdict 4)

| word | meaning |
|---|---|
| `ok` | Read succeeded, bytes returned. |
| `eof` | Read returned EOF / zero bytes. |
| `err6` | WinError 6 (invalid handle) path. |
| `hang` | Read hung (timeout). |

Hang conflicts are NOT adjudicated: both recipes run in the same job, both readings are printed as-is.

## 6. os_legality_verdict (ask the OS directly, separate from language self-report)

| word | meaning |
|---|---|
| `legal` | OS says the name is legal (can exist). |
| `illegal` | OS says the name is illegal. |
| `unknown` | OS answer not obtainable in this cell. |

## 7. path_form

`plain` / `extended` (`\\?\` prefix or manifest long-path path).

## 8. longpath_mechanism

`manifest` / `prefix_rewrite` / `none` / `unknown`.

## 9. attribution_layer

`L1` (OS/environment) / `L2` (stdlib-policy) / `L3` (language-semantics) / `L3_interaction` (interaction cells, reported separately, not merged into main L3 count).

## 10. mechanism_class (dedup key for external divergence counts)

Closed at S01 freeze; known entries as of S00:

| class | example |
|---|---|
| `reserved_device_name` | CON.txt / NUL.tar.gz / COM1.log / CONIN$ |
| `path_preprocessing_policy` | trailing dot/space stripping, `\\?\` auto-prefix (T01 & T-DOTSP share this) |
| `illegal_char_filter` | `<` `>` `:` `"` `\|` `?` `*` |
| `component_length_limit` | T-LEN component / path limits |
| `unicode_normalization` | NFC / NFD coexistence |
| `case_folding` | case-insensitive filesystems |
| `control_char_handling` | U+0000-1F |
| `bidi_handling` | U+202E |
| `zero_width_handling` | U+200B |
| `zip_roundtrip` | zip bit-11 roundtrip |
| `os_legality` | OS verdict differs from language self-report |
| `unknown` | not yet classified (must be resolved before whitepaper) |
