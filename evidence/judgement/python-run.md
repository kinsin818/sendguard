# S02 — Python local run report (windows, local) — freeze revision 2

- date: 2026-10-10
- worker: W-PY
- freeze: **revision 2** (`spec/cases.yaml` sha256 `a7f9a57d…48b`, per `spec/FROZEN.md`)
- harness: `impl/python/sg_python.py` v0.2.0-s02 (stdlib only, deps_direct=0)
- interpreter: `C:\Python314\python.exe` — Python 3.14.7
- OS: Microsoft Windows 10.0.19041 (AMD64), NTFS, max_component=255, LongPathsEnabled=0
- instrument: `harness/audit.exe` v0.1.0-s00 (independent Go enumerator) + self enumeration
- scratch: `%TEMP%\sendguard-run\` (OUTSIDE the repo, N12); harness deletes nothing (project rule)

## 1. Coverage (full, rev2)

| group | cells | note |
|---|---|---|
| trap (T01–T20) | **22** | 20 case ids; T09×2, T14×3 members |
| ctrl (5 control cells) | 5 | all `control_pass = true` |
| len (T17/T18) | 2 | extended + plain component-boundary bisection |
| tapi (T-API sweep) | **88** | 22 traps × 4 pinned python entries |

Schema validation: `results/python/windows` **29 valid / 0 void**;
`results/python/api` **88 valid / 0 void**. Dual instrument: **0 conflicts**
(`sha256_self == sha256_truth` on all 29 cells).

## 2. Freeze defect resolution

Rev1 of the freeze had 9 corrupted sample hex values; W-PY found and reported
them (`defects/sample-corruption.md`). Rev2 replaced all 9 with correct UTF-8
hex; `--check-samples` now reports **DEFECT samples: 0**. All rows below are
first measured on the corrected freeze.

## 3. Measured results (windows / python, entry `open_wb` unless noted)

### 3.1 Unicode / encoding rows (now valid) — all land intact on NTFS
`T06 emoji-U+1F600` ok (28 B) · `T07 NFD cafe+U+0301` ok (28 B) ·
`T08 NFC café` ok (28 B) · `T09a NFD resume-e+U+0301` ok (28 B) ·
`T09b NFC resume-é` ok (28 B) · `T12 bidi+U+202E` ok (28 B) ·
`T13 zero-width U+200B` ok (28 B) · `T19a fullwidth ABC` ok (28 B) ·
`T19b Hangul jamo` ok (28 B). NTFS preserves all three normal forms distinctly
(T09a and T09b coexist as two entries).

- `T15 control char U+0001` -> `err_at_syscall` (OSError): control chars 0x00-0x1F
  are rejected at name parse on Windows.

### 3.2 Reserved device names — NOT uniform
- phantom write (create=ok, absent from enumeration): `T01 CON.txt`,
  `T02 NUL.tar.gz`, `T10 CON`, `T11 COM1.log`, `T14b AUX.log`.
- `T01/T10/T11/T14b` additionally **hang on read-back** (5 s -> `hang`); `T02` reads EOF.
- `T14a PRN`, `T14c LPT9` -> `err_at_syscall` (FileNotFoundError), i.e. hard error,
  not a phantom.

### 3.3 Path-preprocessing (mutation, NOT phantom)
- `T04 "trail."` lands as `trail` (trailing dot stripped).
- `T05 "trailsp "` lands as `trailsp` (trailing space stripped).
  Reader still resolves the asked name, so read_result = ok; enumeration proves
  the name changed. `name_mutated=true`, `name_landed_as=<hex>`.

### 3.4 Illegal char / benign
- `T03 a<b.txt` -> `err_at_syscall`. `T16 zip-roundtrip.zip`, `T20 --force.txt`
  -> ok, 28 B. `T08 café.txt` -> ok.

### 3.5 T-API — intra-language entry divergence (real L2 data)
5 of 22 traps give **different create_result across python's own pinned entries**:

| trap | open_wb | pathlib_write_bytes | os.mkdir | os.rename |
|---|---|---|---|---|
| T01 | ok | ok | err_at_syscall | err_at_syscall |
| T02 | ok | ok | ok | err_at_syscall |
| T10 | ok | ok | err_at_syscall | err_at_syscall |
| T11 | ok | ok | err_at_syscall | err_at_syscall |
| T14b | ok | ok | err_at_syscall | err_at_syscall |

Same trap name -> different verdict depending on API entry. This is exactly the
"same language, different entry" axis; it cannot be explained by the OS alone.

### 3.6 Length (T18)
- extended path (`\\?\`, prefix_rewrite): component boundary = **255** (base_len 69).
- plain path: component boundary = **177** (base 71 -> full path 259 = 260-1).

### 3.7 Controls (expectations from `evidence/ctrl-baseline.md`)
`T-CTRL-ASCII=ok`, `T-CTRL-PARSE=err_at_parse(ValueError)`,
`T-CTRL-ILLEGAL-CHAR=err_at_syscall`, `T-CTRL-NAMETOOLONG=err_at_syscall`,
`T-CTRL-CANON` python sha == node sha `c9fe45b2…21994` -> all pass.

## 4. acceptance status

- full 22-trap coverage on rev2; schema-valid; 0 conflicts.
- existence from **directory enumeration** (audit + scandir), `path_view` + `dir_view`
  both recorded (M2). `exists()/stat()` never used as sole truth (they lie — see S02 defect notes).
- errors verbatim (`winerror:` / exception name) (M16); 5 s timeout -> `hang` (M9);
  no delete anywhere (project rule); English only (M21).
- **Rev1 was blocked on the freeze defect; rev2 is unblocked.**

## 5. Artifacts

- `impl/python/sg_python.py` (v0.2.0-s02)
- `results/python/windows/*.json` (29), `results/python/api/*.json` (88),
  `results/python.windows.3.14.7.json`, `results/python/phantom.windows.json`,
  `results/python/api-entry.windows.json`
- `results/python/_superseded_rev1/` (4 stale T14 api cells from rev1, kept not deleted)
- `evidence/judgement/defects/sample-corruption.{md,json}`, `evidence/judgement/conflicts/` (empty)

## 6. Instrument caveat

`os_legality_verdict` comes from an independent PowerShell/.NET `File.WriteAllBytes`
probe (different runtime than CPython) and is best-effort: a reserved device name can
probe "legal" while `mechanism_class = reserved_device_name` carries the real story.
Always pair with the enumeration truth.

## 7. Next

1. Propagate the same harness to the Node/Go seats and the CI columns (macOS/ubuntu).
2. Deferred sub-items for this local: T16 zip round-trip body, T17 full-path bisection
   (G1–G4), cross-language read-back (S04).
