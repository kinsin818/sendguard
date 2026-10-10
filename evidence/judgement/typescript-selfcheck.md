# S02 acceptance — TypeScript port (seat `qoder`), contract rev3

Port label, fixed by `docs/NOTICE-rev3.md` and not to be upgraded later:
**TypeScript (Node 24 type-stripping; no type-checker on this host)**.
`tsc` is not installed here and `node --check` does not type-check, so **no type-checker has ever
run against this source**. That sentence is the one claim about this port which cannot currently be
checked; "TypeScript verified" would be false.

controls_pass=true (5/5) — no INSTRUMENT-RED in this run.

```
cells_required=33   cells_produced=74   cells_valid=25 (strict, spec/schema.json rev3)
cells_blocked=5     cells_extra=41      cells_measured=69   cells_hang=0
required identities covered = 33/33 by measured cells; uncovered = 0
probe_jobs=151  probe_wall_ms=19742  timeouts=0  nonzero_probe_exits=0  malformed_log_lines=0
non_cell_files_in_results_dir=0  cleanup_failed=0
run face: node v24.15.0, Windows-10-10.0.19041-SP0, AMD64
cells regenerated 2026-10-11 04:5x +0800, after rev3 (commits 7548b9f, 799d69d)
spec/cases.yaml blob face sha256 = a7f9a57df1b4d39a19421a54d175e87793100ce3393e363622ca59816e19148b
spec/cells-required.json face sha256 = 99d6ec085794d3cc… (rev3 regeneration; the 03:4x version is
  withdrawn by name inside the file and was consumed by this port earlier — see S6/G-7)
```

**One number to read carefully:** `cells_valid=25` is *strict against `spec/schema.json` as revised*,
and all 49 failures are the same single cause (gap G-2, `read_result` left `null` where the leg was
never reached — rev3 did not touch that enum). It is **not** 0 any more: gap G-1 (`language` had no
`typescript`) was genuinely closed by rev3 and this port now passes that rule. Separately,
`spec/validate.py` still voids 74/74 because rev3 revised `schema.json` but not the sibling
validator — measured in S4, not argued.

## 1. How the port is executed

**Run, not compiled.** `node src/runner.ts` on `C:\Program Files\nodejs\node.exe` v24.15.0 using
Node's built-in TypeScript type stripping. `evidence/S00/env-facts-windows-local.json` records
`runtimes.tsc = {candidates_found: 0, version_probe: {status: "no-candidate"}}` and
`npx --no-install tsc --version` exits 1. Consequences, declared rather than hidden:

* Source targets `tsconfig.json` (`strict`, `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`,
  `erasableSyntaxOnly`, `verbatimModuleSyntax`), but nothing type-checks it here. A drifted
  positional argument is therefore a live risk and it actually happened (C-5a), which is why the port
  now validates its own output instead of assuming a compiler did.
* Zero third-party dependencies; no `node_modules` in this port. `types/node-builtins.d.ts` declares
  the Node surface used so a seat that installs `typescript` can run `tsc --noEmit` without pulling
  `@types/node`; delete that file if `@types/node` is ever added.
* No cell needed `not-achievable-in-stdlib`: the T16 zip container is hand-built in `src/zip.ts`
  (stored entries, CRC-32 from `node:zlib`).

Reproduce: `cd impl/typescript && node src/runner.ts` (~20 s), then `python selfcheck.py`.

## 2. The three things the notice asked, and where each landed

**(1) Field renames — done, in the port, not in the cells after the fact.**

| rev3 field | value used here | why this value |
|---|---|---|
| `length_unit` | `utf16_code_units` | every length this port reports comes from JS string length = UTF-16 code units; the other two units are published per cell as `len_triple` |
| `name_encoding` | `hex_raw_bytes` | `name_source` is hex of the UTF-8 bytes of the frozen sample, which is how the corpus stores it (N12). Not `hex_utf16le`: the recorded bytes are the frozen table's, not a UTF-16 re-encode |
| `verdict_via` | `win32` (18 cells) / `none` (56 cells) | a verdict is recorded only from the extended-prefix create probe, which asks the **Win32** file API layer through `node:fs`; where the probe was refused (reserved device names) or not defined (length rungs, blocked cells) nothing was asked, so the honest value is `none` rather than a borrowed verdict |

`selfcheck.py` counts these: `length_unit`/`name_encoding`/`verdict_via` present in 74/74 cells, and
`verdict_via ∈ {win32, none}` split 18/56. Note it enforces them because the **notice** demands them:
`spec/schema.json` lists both in `properties` but leaves them out of its `required` array, so the
schema as written is the weaker rule and I did not take the weaker reading.

**(2) Reconciliation against `spec/cells-required.json` (rev3 face).**

| | count | detail |
|---|---|---|
| required identities | 33 | 22 trap cells (members carried in `case_id`: `T09-m1`, `T14-m3`, `T19-m2`), 5 controls, 6 ladder rungs (`T17`/`T18` × base 78/120/200) |
| covered by a measured cell | **33/33** | re-planned to the rev3 identities; nothing required is missing, so no required cell needed `blocked` |
| uncovered and unexplained | 0 | the runner now has a standing path: any required identity it fails to produce is emitted `blocked` with the command it ran to prove absence, that command's exit code, and one attempted fix |
| extra cells, marked `extra: true` | 41 | zip legs (5), frozen G1–G4 grid points (24), base-13 bisections (4), T-API rows (3), blind placeholders (5) |
| T-API identities required of typescript | **0** | the generator derives T-API rows from `cases.yaml`, which has no `typescript` entry list; my 3 rows stay extra and declared (G-6) |

Identity form changes this port made to match the contract: members moved from `sub_identity` into
`case_id` (`trap__T09-m1.json`, member index kept as an in-cell named field, which is what
`cell-identity.md` §1 actually asks for); length rungs are keyed by `base_len` alone, and because the
contract lists **no** per-regime rung identity, both path regimes are measured **inside one cell**
(`last_ok_comp`/`first_fail_comp` for the plain claim, `rung_extended_*` for the prefixed one) rather
than split into two cells colliding on one identity.

Cells withdrawn by the notice's own text were removed rather than left to rot: the 5 identity-less
`blocked` cells (`trap__T09.json`, `T14`, `T17`, `T18`, `T19`) existed only because the 03:4x
required-list demanded an identity-less cell per trap; that version is void per the file itself, and
a cell carrying a claim the current contract no longer makes is worse than deleting it. Also dropped:
the 8 base-78 grid points built on the same withdrawn derivation — their substance now lives in the
required rungs, which measure the whole boundary at base 78 instead of three pre-selected points.

**(3) Self-check re-run** — `python selfcheck.py` exits 0. Sections below.

## 3. Control cells (expectations only from `evidence/S00-ctrl-baseline.md`)

| cell | expected | observed | pass |
|---|---|---|---|
| T-CTRL-NAMETOOLONG | create=err_at_syscall stage=syscall | err_at_syscall / syscall, code ENOENT | true |
| T-CTRL-ASCII | create=ok stage=null | ok, 28 written / 28 on disk, read ok, roundtrip true | true |
| T-CTRL-ILLEGAL-CHAR | create=err_at_syscall stage=syscall | err_at_syscall / syscall, code ENOENT | true |
| T-CTRL-PARSE | create=err_at_parse stage=parse | err_at_parse / parse, code ERR_INVALID_ARG_VALUE | true |
| T-CTRL-CANON | two instruments, same payload, identical sha256 | sha_memory == sha_readback == `347b5c4fb88a4c7e…` | true |

Baseline was taken on node v22.23.2; this run is v24.15.0 and all five still hold.
`error_winerror` is recorded as `not-obtainable-in-stdlib` (M16 asks for the Win32 number verbatim;
`node:fs` does not surface it, so it is declared unavailable rather than invented). `control_pass=true`
is stamped on all 74 cells; `instrument_red=false`, `instrument_conflict=0` everywhere.

## 4. Commands run, with exit codes

| # | command | rc | output that matters |
|---|---|---|---|
| A | `node src/runner.ts` | 0 | `written=74 cells_expected=74 cells_produced=74 cells_measured=69 cells_blocked=5 in_cells_required=33 extra=41 controls_pass=true` |
| B | `node src/runner.ts --selftest-provenance` | 0 | `arms=2 caught=1 PASS` |
| C | `python selfcheck.py --selftest-rules` | 0 | `green_arm_clean=True red_arm_caught=True` |
| D | `python selfcheck.py` | **0** | `cells_required=33 cells_produced=74 … OUTCOME=GREEN … strict_against_schema_json=25` |
| E | `python -m json.tool` × 74 cells | 0 | `json_ok=74 json_bad=0`; 0 BOMs |
| F | `python ci/lint.py --selftest` | 0 | `lint: OK` |
| G | `python ci/lint.py --repo-root .` | 0 | `lint: OK` |
| H | `python spec/validate.py results/typescript.windows.x64` | **1** | `0 valid / 74 void` — see the two-ruler table |
| I | `python ci/equality.py --results-dir results` | **3** | `NOT-COMPARABLE reason=ambiguous_entries cells=47 ports=['csharp','go','java','python','rust']`; typescript is **live and clean** (`instrument_red_or_conflict=0 control_pass_false=0 runtime_crash_text_in_error_message=0 create_ok_without_disk_truth=0`), read as `cells=44 read from 74 cell records` |

**The two rulers, over the same cells (D prints this itself, so it is not my prose):**

```
spec/schema.json (rev3)     : 25 of 74 valid; violations by field -> read_result=49   (gap G-2)
spec/validate.py (unrevved) : 0 of 74 valid; rejects
      language       in 74 cells   <- rev3 added typescript to schema.json, not to validate.py CLOSED_SETS L24
      name_encoding  in 74 cells   <- rev3 re-defined it to hex_raw_bytes/hex_utf16le; validate.py L26 still
                                       lists utf16_code_units/code_points/utf8_bytes (the values it moved to length_unit)
      read_result    in 54 cells   <- G-2 (null legs, incl. the 5 blocked cells)
      roundtrip_ok   in 54 cells   <- boolean column, same not-reached family
      enum_to_stat_agrees in 45 cells
      create_result  in  5 cells   <- the 5 blocked cells
      error_stage    in  5 cells   <- the 5 blocked cells
RULER_DIVERGENCE fields=['language','name_encoding']
```

A cell cannot satisfy both rulers at once, because the two files now define `name_encoding`
differently. I follow the revised `schema.json` (rev3 is the later act, and it is what the notice
told me to conform to) and print the divergence rather than smoothing it. The repair is two lines in
`spec/validate.py`'s `CLOSED_SETS` — which is a frozen file this port may not touch.

## 5. Findings

**C-1 — the carrier had to change to reach the frozen grid.** The order says write only inside the
clone; its shortest directory is 30 characters, while the frozen grid needs `base_len` 13, and `D:\`
has 8.3 short-name creation **disabled** per `evidence/S00/env-facts-windows-local.json`. I mapped
the scratch directory with `subst S: <clone>\.sgscratch` (no file outside the clone, reversible,
recorded per cell as `meta.scratch_carrier`); `\\?\S:\…` resolves, so both regimes were testable on
one carrier. rev3's ladder base 78 exists because another seat measured base 13 unreachable — that
seat's own commit `1bccfe8` says so; I read it from `git log`, not from their cells. With this carrier
base 13 **is** reachable, so the frozen base-13 points are still delivered (marked extra) alongside
the required 78/120/200 rungs.

**C-2 — `node:fs` does not apply the Win32 name-parsing layer, measured with same-directory
controls.** Plain absolute paths from this port created **real NTFS entries** named `CON.txt`, `CON`,
`NUL.tar.gz`, `COM1.log`, `PRN`, `AUX.log`, `LPT9` (10 cells, `create_result=ok`, 28 bytes on disk)
and kept trailing dots/spaces (`trail.`, `trailsp `). Controls in the same directory on the same
volume: `cmd.exe` sent `CON.txt` to the device (nothing listed), wrote `trail.` as `trail`, and
refused a 309-character path (rc=1, ERROR_PATH_NOT_FOUND); python 3.14 also refused (rc=1). A .NET
directory listing independently confirmed node's `CON.txt` is a 28-byte entry, not a device alias.
Per cell, `meta.instrument_c2`. Under the attribution tree this is L2 (stdlib/toolchain policy): the
seven device-name cells and the two trailing-dot/space cells share one root cause and must dedup to
one finding, not nine.

**C-3 — T-API produced zero intra-runtime hits, and `spec/gate.md` §2 still reads that as
`instrument_failure`.** The three pinned entries agree in all 22 trap cells and all 3 T-API cells.
Read literally, §2 voids and re-runs this batch; a re-run reproduces it, because all three entries
reach the same libuv open. I did not manufacture a hit and I do not waive §2. **Ruling still
requested** (unchanged from the previous report).

**C-4 — reconfirmed on rev3's own ladder: for this runtime there is no total-path wall at all, so
T17's linear model has nothing to hit.** All 6 required rungs, plain **and** extended, at all three
ladder bases, land on the same boundary: last ok component **255**, first fail **256** — i.e. the
*component* wall, at total path lengths 334, 376 and 456, which are each far past 259. The two
regimes agree exactly (`rung_extended_last_ok_comp` equals the plain value in 6/6). So
`spec/gate.md` §5's basis ("domain B four base tiers each hit `259 - base - 1` EXACTLY, zero
tolerance") is unsatisfiable through this port at any base, and any cross-port equality written as
"bisection must equal `259 - base - 1`" is a statement about runtimes that obey the legacy cap.
`longpath_mechanism` is `prefix_rewrite` where a plain create cleared 259 characters, with the
elimination recorded in-cell (`manifest` is excluded: python's executable carries the
`longPathAware` token and still refused 309 characters under `LongPathsEnabled=0`).

**C-5 — defects my own rulers caught, all fixed in code (unchanged from the previous report, restated
because they are why the current numbers are trustworthy).** (a) 62 cells were written with `env` and
`meta` transposed by a positional argument that drifted — invisible with no type-checker; now
`provenanceProblem()` refuses to label such a cell measured, with both arms tested (row B).
(b) `create_result=ok` with `bytes_written=null` broke the definition of the word in
`canonical.md` §3; bisection legs now re-create their boundary before claiming `ok`, and that
definition is a checked rule with a red and a green arm (row C). (c) dimensions carried only in
filenames; now mirrored in-cell and checked.

**C-6 — new in this pass: the identity form the contract wants is not the identity form the gate can
see.** `ci/equality.py` builds sub_identity from five named fields (`base_len, builder, reader,
packer, extractor`), so `path_form`, `comp_len`, `member` and `entry_source` are invisible to it, and
it has **no handling for `extra` at all** even though the notice states extras are excluded from the
digest. Measured consequence: it reads my 74 files as **44 keys**, keeping one record per key by
filename order. I mitigated what I can without touching `ci/`: the 6 required rungs are keyed by
`base_len` alone and their filenames sort before every extra cell sharing that key
(`len__T17__base_len-78.json` before `len__T17__path_form-…`), so the record the gate keeps for a
required identity is the required cell, deterministically. What remains is a defect in the gate, not
in these cells.

## 6. Contract gaps

* **G-1 — CLOSED by rev3.** `language` now includes `typescript` and `format_version` accepts both
  integer and string, so the truthful value no longer voids my cells. `spec/validate.py` was not
  revised and still voids on it (S4).
* **G-2 — STILL OPEN.** `read_result` is required and `canonical.md` §5 still offers only
  `ok/eof/err6/hang`, every one of which presupposes an attempted read. When a create does not land
  there is nothing to read; when the name is reserved this port refuses to open it at all. I record
  JSON `null` plus `read_skipped_reason` — the precedent `evidence/S00-ctrl-baseline.md` itself sets —
  and `ci/equality.py` tolerates `None`. Writing `eof` would paraphrase a verdict. 49 cells under
  `schema.json`, 54 under `validate.py` (the blocked cells add 5). The clean fix is a fifth word,
  e.g. `not_reached`, in `canonical.md` §5 — a frozen-file change I may not make.
* **G-7 — withdrawn derivation consumed, now corrected.** The 03:4x `cells-required.json` this port
  reconciled against is void per its own file text; the cells it forced (5 identity-less traps, 8
  base-78 points) were deleted, and the set was re-derived from the rev3 face. Recorded here because
  "discard it and re-derive" should be visible in the acceptance, not implied.
* **G-8 — rev3 revised `schema.json` without `spec/validate.py`.** Two shipped rulers now disagree on
  `language` and on the *definition* of `name_encoding`, so no cell can be valid under both and
  "passes strict validation" is ambiguous until one of the two is amended.
* **G-6 — no `typescript` entry list or T-API count exists.** `spec/FROZEN.md` pins six languages;
  `cell-identity.md` §2 assigns typescript node's primary entry, and rev3's
  `primary_entry_per_port` confirms `typescript: writeFileSync`. But the T-API rows the generator
  emits are derived from `cases.yaml`, which has no `typescript` key, so **0 T-API identities are
  required of this port** while its 3 pinned entries are inherited by inference. Declared, not
  silently assumed.
* **G-4 — `blocked` / `not-achievable-in-stdlib` / `cleanup_failed` are not canonical words.** They
  live in the extra `status` field and `blocked_*`, never in a closed-set field.
* **G-5 (blind cells)** — the frozen table assigns no `case_id` to the 5 blind samples, so no two
  ports can name the same blind cell. Mine are declared placeholders `T-BLIND-1..5`.
* **`attribution_layer` is not emitted.** Deciding L1/L2/L3 needs cross-port and cross-OS data
  (`attribution-tree.md` §1–2), which a single port on a single OS does not have; the field is not
  schema-required, so I leave it to the arbitration seat instead of guessing. C-2's L2 reading above
  is offered as the tree's own reasoning, in prose, not welded into cells.

## 7. Blocked cells (5 — the blind group only)

`blind__T-BLIND-1..5.json`, `status: blocked`, `blocked_exit_code: 9`, each carrying:

```
blocked_command: "C:\Program Files\nodejs\node.exe" "…\impl\typescript\src\probe.ts"
                 --mode cell --dir <fresh uuid dir> --entry writeFileSync --form plain --name-hex ""
rc 9; event log: {"ev":"probe_crash","message":"sample is not lowercase even-length UTF-8 hex: \"\""}
attempted_fix: probed with an empty --name-hex to confirm the sample really is unavailable; it is.
               Not resolved by opening the sealed map.
```

Reason: the five blind samples exist only in `evidence/S00/blind-map.json`, which `spec/FROZEN.md`
seals until after the S03 audit; taking them now would be a prefilled expectation, which `gate.md` §7
check 1 treats as an audit failure. I did not open that file. These 5 are not in the required list, so
they are marked `extra` as well as `blocked`.

Nothing else is blocked: 0 hangs, 0 crashed probes, 0 non-zero probe exits, 151 probes, 19.7 s of
probe wall time.

## 8. Independence, restated

* Not read: any other port's `impl/` or `results/`; `spec/expectations.sealed.md`
  (`cell-identity.md` §5 — open only after the port digests are in); `evidence/S00-predictions.md`;
  `evidence/S00/blind-map.json`. `harness/ctrl-baseline.mjs` deliberately not opened, to keep a
  Node-flavoured instrument's error classification out of my head; control expectations came only
  from `evidence/S00-ctrl-baseline.md`.
* **Standing disclosure (unchanged, because it still matters):** my first tool call this session was
  a repository file listing, which printed *path names* under `results/go.windows.go1.23.5/` and
  `results/node/windows/`. From names alone I saw that Go renders length sub-identities like
  `extended_b120_c137`. I chose my own rendering from `cell-identity.md` §1/§3 and read no other
  port's cell contents; no other port's verdict entered this implementation. The affected column is
  filename rendering only.
* This clone is shared and other seats commit into it: rev3 (`7548b9f`, 04:2x) and the gate change
  (`799d69d`) landed mid-session. Everything in this report was re-measured against the current faces.
* The work is **uncommitted** — no instruction to commit, and the index is shared, so a `git add` here
  risks sweeping another seat's in-flight rows. 11 port files, 74 cells and this report exist only on
  this disk face right now.

## 9. Scratch state, and no deletion inside the port

151 probes ran in fresh uuid-derived directories, one per cell, each verified empty before use
(`scratch.verified_empty_before_use`); every cell records `scratch.cell_root` and
`scratch.cell_root_real`. The port holds **no deletion path at all** (M19), so it never emits
`cleanup_failed` — cleanup is an operator action outside the port, and it is worth two lines because
it is C-2 again:

* A plain `shutil.rmtree` over the accumulated tree failed on **every** entry with `WinError 123`
  (ERROR_INVALID_NAME): the tree really does contain `CON`, `PRN`, `LPT9`, `trail.`, `trailsp `.
* Deleting through the extended prefix — `rmSync("\\\\?\\" + path, {recursive: true})` — removed 75
  top-level directories after this run, with **0 failures**; then `.sgscratch/`, the stray
  `impl/.sgscratch/` left by an early carrier test, and the `S:` mapping were all released.

Cells therefore name directories that no longer exist: that is the provenance record of where each
probe ran, not a dangling pointer. The tree was excluded from git through this seat's own
`.git/info/exclude`, so no forbidden name ever entered the index (`ci/lint.py --repo-root .` rc=0).

## 10. Files

`impl/typescript/{package.json,tsconfig.json,selfcheck.py}`, `types/node-builtins.d.ts`,
`src/{constants,spec,identity,nameguard,zip,probe,runner}.ts`; 74 cells in
`results/typescript.windows.x64/`; this report. Four throwaway instrument-check files created during
the session were removed; the C-2 controls they performed are reproduced in S5. Nothing outside the
clone was written. No commit, no tag, no push.
