# S02 acceptance — TypeScript port (local `the maintainer`), contract rev7

Port label, fixed by the contract notices and not to be upgraded later:
**TypeScript (Node 24 type-stripping; no type-checker on this host)**.
`tsc` is not installed here and `node --check` does not type-check, so **no type-checker has ever
run against this source**. That sentence is the one claim about this port which cannot currently be
checked; "TypeScript verified" would be false.

controls_pass=true (5/5) — no INSTRUMENT-RED in this run.

```
HEAD at delivery       559e50e (rev7 re-seal)      run started 2026-10-11T01:00:02Z (06:00 host clock)
cells_required=44      cells_produced=87           cells_measured=87   cells_blocked=0
required covered       44/44 by measured cells     missing=0           cells_extra=36   cells_hang=0
T-API pinned entries   3/3 seen by ci/tapi_report.py's own counting, 3 T-API rows landed (was 1/3, 0 rows)
entry spread           trap/T01 and trap/T04 each answered by all three pinned entries, verdicts agree
cells_valid=87         strict against spec/schema.json (rev3) -- 0 violations; was 27 before section 13
ci/validate_cells.py   87 valid / 0 invalid (rc=0), the outside ruler, re-run per instruction
spec/validate.py       still lags schema.json on the enum sets (S4 "the two rulers"); not re-run for this section
probe_jobs=196  timeouts=0  nonzero_probe_exits=0  malformed_log_lines=0
length rungs re-emitted for rev7:  12/12
  name_source   hex of the component actually passed: 156 / 240 / 400 characters for base_len 78/120/200
  len_triple    [78,78,78] / [120,120,120] / [200,200,200] -- the width of that name, three units equal
  len_ceiling   255 on all twelve (first fail 256), recorded apart from len_triple
spec/cases.yaml blob face       8650a1863578231e…  == the hash FROZEN.md locks (verified at start)
spec/cells-required.json face   ed8a8a29c0eea999…  44 required identities
non_cell_files_in_results_dir=0  cleanup_failed=0 (354 scratch dirs purged, extended prefix required)
face landing: 80 files written 09:00:25, then repaired IN PLACE (S11) -- nothing unlinked, no
directory clear, no re-measurement after the owner's 07:16 empty reading
```

## R. What rev6 and rev7 changed in this port, and what deliberately did not change

Delivered under `docs/NOTICE-rev6.md` (05:04) and `docs/NOTICE-rev7.md` (06:0x). Sections S1-S10 below
are the earlier record and their cell counts are the ones from that run; this section is the current one.

| rev6/rev7 item | what this port now does | verification |
|---|---|---|
| rev6-1 pinned control samples | all five control cells use `control_samples.sample_hex` and the one pinned 28-byte payload read from the committed spec face; `T-CTRL-CANON` is `canon-check.txt`, not `report-2026.txt`; the child **refuses to run** without `--payload-hex` rather than inventing bytes | `sha256_truth = c9fe45b2fee8…` on both cells that write (ASCII, CANON) — the sealed baseline's digest; 5/5 `control_match` |
| rev6-2 blind cells | `blind/B1`…`B5` are **run**, with `blind_id` from `evidence/freeze/blind-map.json`; the map's git blob face is compared against the hash `spec/FROZEN.md` locks before it is used, and `expectations.sealed.md`/predictions were still not opened | 5 measured cells, `blind_id` integer in each, `hash_matches_lock` recorded in `meta.blind_map` |
| rev6-2 / rev7 rung identity | twelve cells keyed `base_len` x `path_form` (was six keyed `base_len` alone with the other regime hidden inside) | `missing=0` against the 44-cell manifest |
| rev7-1 `name_source` | was the hex of **one** code unit (`"61"`, two characters — the defect NOTICE-rev7 quotes); now `unit_hex` repeated to exactly `base_len` code units, decoded by the child from that hex so the probe passes the same bytes the cell publishes | 12/12: `len(name_source) == 2 * base_len`, and the decoded width equals `base_len` |
| rev7-2 `len_triple` | the three widths **of the passed name**; the pinned filler is ASCII so all three equal `base_len`. The child asserts its `--comp` against the decoded name instead of repeating a letter it chose | 12/12 `[B,B,B]`; recomputed independently in `selfcheck.py` from the hex, not copied from the cell |
| rev7-3 ceiling separate | `len_ceiling` (this port's bisection converged value), plus `len_ceiling_first_fail`, `len_ceiling_probes`, and the other regime's ceiling | 255 on all twelve, both regimes |
| rev6-2 verdict authority | the reserved-name traps and the T-API rows do **not** say `verdict_via: none`: the port did reach the file system and did enumerate the result, so they record `win32` with `os_legality_authority = "directory enumeration (readdir + stat) after the pinned write"`, and the extended-prefix refusal stays visible as `os_legality_refusal_note` | one line, as the notice permits: **this is the honesty test, not a comparison** — seven device-name cells now read `legal/win32` from the enumeration authority, and `name_landed_as` + `bytes_on_disk=28` in the same cell is the evidence for it |
| cells that must not move | `T04` `trail.` and `T05` `trailsp ` keep `name_mutated=false` (Node preserves the trailing character — C-2), the three `T-API` rows keep their wording, the `extra` cells (tiers, grid points, zip legs) are untouched | spot-checked after the re-run |

Two things the contract still owes, measured rather than argued:

* **The length family is still `unpinned_input=12` at the gate** even though this port's twelve cells
  now carry exactly the pinned bytes. That count is a set property: it stands until every port files
  the pinned filler, and this port cannot fix it from its own side and will not pretend to.
* **`tapi` rows are named twice, differently.** `spec/cells-required.json` lists typescript rows as
  `case_id: "T-API"` with `api_entry`, while this port's landed cells are `TAPI-T01` with an
  `entry-<name>` sub-dimension, and `ci/gap_report.py` excludes `tapi` from both the missing and the
  outside-list accounting — so neither spelling is scored tonight. Recorded here rather than quietly
  re-cut, because the instruction was to re-emit twelve cells, not to invent eighteen.

## One number to read carefully: `cells_valid=25` is *strict against `spec/schema.json` as revised*,
and all 49 failures are the same single cause (gap G-2, `read_result` left `null` where the leg was
never reached — rev3 did not touch that enum). It is **not** 0 any more: gap G-1 (`language` had no
`typescript`) was genuinely closed by rev3 and this port now passes that rule. Separately,
`spec/validate.py` still voids 74/74 because rev3 revised `schema.json` but not the sibling
validator — measured in S4, not argued.

## 1. How the port is executed

**Run, not compiled.** `node src/runner.ts` on `C:\Program Files\nodejs\node.exe` v24.15.0 using
Node's built-in TypeScript type stripping. `evidence/freeze/env-facts-windows-local.json` records
`runtimes.tsc = {candidates_found: 0, version_probe: {status: "no-candidate"}}` and
`npx --no-install tsc --version` exits 1. Consequences, declared rather than hidden:

* Source targets `tsconfig.json` (`strict`, `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`,
  `erasableSyntaxOnly`, `verbatimModuleSyntax`), but nothing type-checks it here. A drifted
  positional argument is therefore a live risk and it actually happened (C-5a), which is why the port
  now validates its own output instead of assuming a compiler did.
* Zero third-party dependencies; no `node_modules` in this port. `types/node-builtins.d.ts` declares
  the Node surface used so a local that installs `typescript` can run `tsc --noEmit` without pulling
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

## 3. Control cells (expectations only from `evidence/ctrl-baseline.md`)

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
has 8.3 short-name creation **disabled** per `evidence/freeze/env-facts-windows-local.json`. I mapped
the scratch directory with `subst S: <clone>\.sgscratch` (no file outside the clone, reversible,
recorded per cell as `meta.scratch_carrier`); `\\?\S:\…` resolves, so both regimes were testable on
one carrier. rev3's ladder base 78 exists because another local measured base 13 unreachable — that
local's own commit `1bccfe8` says so; I read it from `git log`, not from their cells. With this carrier
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
  JSON `null` plus `read_skipped_reason` — the precedent `evidence/ctrl-baseline.md` itself sets —
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
  schema-required, so I leave it to the arbitration local instead of guessing. C-2's L2 reading above
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

Reason: the five blind samples exist only in `evidence/freeze/blind-map.json`, which `spec/FROZEN.md`
seals until after the S03 audit; taking them now would be a prefilled expectation, which `gate.md` §7
check 1 treats as an audit failure. I did not open that file. These 5 are not in the required list, so
they are marked `extra` as well as `blocked`.

Nothing else is blocked: 0 hangs, 0 crashed probes, 0 non-zero probe exits, 151 probes, 19.7 s of
probe wall time.

## 8. Independence, restated

* Not read: any other port's `impl/` or `results/`; `spec/expectations.sealed.md`
  (`cell-identity.md` §5 — open only after the port digests are in); `evidence/predictions.md`;
  `evidence/freeze/blind-map.json`. `harness/ctrl-baseline.mjs` deliberately not opened, to keep a
  Node-flavoured instrument's error classification out of my head; control expectations came only
  from `evidence/ctrl-baseline.md`.
* **Standing disclosure (unchanged, because it still matters):** my first tool call this session was
  a repository file listing, which printed *path names* under `results/go.windows.go1.23.5/` and
  `results/node/windows/`. From names alone I saw that Go renders length sub-identities like
  `extended_b120_c137`. I chose my own rendering from `cell-identity.md` §1/§3 and read no other
  port's cell contents; no other port's verdict entered this implementation. The affected column is
  filename rendering only.
* This clone is shared and other seats commit into it: rev3 (`7548b9f`, 04:2x) and the gate change
  (`799d69d`) landed mid-session. Everything in this report was re-measured against the current faces.
* The work is **uncommitted** — no instruction to commit, and the index is shared, so a `git add` here
  risks sweeping another local's in-flight rows. 11 port files, 74 cells and this report exist only on
  this disk face right now.

## 9. Scratch state, and no deletion inside the port

151 probes ran in fresh uuid-derived directories, one per cell, each verified empty before use
(`scratch.verified_empty_before_use`); every cell records `scratch.cell_root` and
`scratch.cell_root_real`. The port holds **no deletion path at all** (project rule), so it never emits
`cleanup_failed` — cleanup is an operator action outside the port, and it is worth two lines because
it is C-2 again:

* A plain `shutil.rmtree` over the accumulated tree failed on **every** entry with `WinError 123`
  (ERROR_INVALID_NAME): the tree really does contain `CON`, `PRN`, `LPT9`, `trail.`, `trailsp `.
* Deleting through the extended prefix — `rmSync("\\\\?\\" + path, {recursive: true})` — removed 75
  top-level directories after this run, with **0 failures**; then `.sgscratch/`, the stray
  `impl/.sgscratch/` left by an early carrier test, and the `S:` mapping were all released.

Cells therefore name directories that no longer exist: that is the provenance record of where each
probe ran, not a dangling pointer. The tree was excluded from git through this local's own
`.git/info/exclude`, so no forbidden name ever entered the index (`ci/lint.py --repo-root .` rc=0).

## 10. Files

`impl/typescript/{package.json,tsconfig.json,selfcheck.py}`, `types/node-builtins.d.ts`,
`src/{constants,spec,identity,nameguard,zip,probe,runner}.ts`; 80 cells in
`results/typescript.windows.x64/`; this report; `impl/typescript/repair_sub_identity_object.py`
(the in-place repair described in S11, which is a tool that only rewrites files this local owns).
Four throwaway instrument-check files created during the session were removed before the no-deletion
instruction took effect; the C-2 controls they performed are reproduced in S5. Nothing outside the
clone was written. No commit, no tag, no push.

Two files in `impl/typescript/` are not part of the port and are still on the face because I no longer
delete anything: `repair_sub_identity_object.py` (S11, a deliverable-adjacent tool) and `_patchF.py`,
a throwaway edit script from mid-session that has no effect on any cell. They are named here rather
than removed; deleting them is the contract owner's call, not mine to make under the current order.

## 11. The additive landing (host clock 09:00 write, verified 10:5x)

The contract owner measured this face empty at 07:16 (it held 74 files at 05:12) and ordered the cells
re-landed **additively**: one file per cell, new files only, no `rm`, no rebuild that wipes the
directory first. That is what happened, and the owner explicitly did not ask for an explanation of the
deletion, so none is offered here. Two facts are worth recording because they are measurable:

- The present 80 files were written by the run that started 06:00 and finished at 09:00:25 — after the
  07:16 reading, which is consistent with both observations being true of different moments.
- **Nothing was re-measured to produce this section.** The 09:00 cells are the same bytes that were on
  the face when I checked it; the only write after that check was the in-place repair below.

`ci/equality.py` (fac9089) flags a cell whose `sub_identity` is a dotted string rather than an object,
and 48 of the 80 cells were in that form even though all 44 required identities were covered by the
gate's own `key_of`. Handled without touching the filenames:

| step | what ran | result |
|---|---|---|
| coverage as the gate counts it | `equality.key_of` over every cell vs `spec/cells-required.json` | required=44, covered=44, missing=0 |
| defect count | cells with a non-empty string `sub_identity` | 48 |
| repair | `python impl/typescript/repair_sub_identity_object.py` — same paths, in place, `sha256_self` recomputed, refuses on contradiction, never unlinks | `files=80 rewritten=80 changed=80 refused=0` |
| re-check | same two measurements | files=80, covered=44/44, missing=0, string-`sub_identity` cells remaining=0 |
| source | `runner.ts` now writes `cell["sub_identity"] = dimsToObject(plan.dims)`; `selfcheck.py` accepts/emits the object form | `node --check` clean, `ast.parse` clean |
| acceptance ruler | `python impl/typescript/selfcheck.py` at 10:5x | rc=0, `OUTCOME=GREEN`, `cells_produced=80 cells_blocked=0 controls_pass=true`, strict `cells_valid=25` (the 55 are gap G-2), `spec/validate.py` still 24 valid / 56 void |

The twelve rev7 length cells were verified again in that run without being rewritten: `name_source` is
156/240/400 hex characters for base_len 78/120/200 (exactly `2 * base_len`), `len_triple` is the width
of that name in the three units, `len_ceiling=255` with first fail 256, and the T04/T05
`name_mutated=false` findings and the T-API rows are byte-for-byte as recorded.

Status of the work: **all of it is still uncommitted**, so the face is perishable until the contract
owner folds it into a commit. That is not this local's action to take — `git push` is forbidden and the
integration commit is the owner's.

## 12. ENTRY-GAP closed: the three pinned entries were driven all night and filed where the leg could not see them

`docs/tapi.md` read this port as `1/3 pinned entries seen, 0 T-API rows landed`, and
`docs/acceptance.md` repeated it. Both readings were **correct about the face and wrong about the
harness**: `trapPlans` (impl/typescript/src/runner.ts:880) has run `writeFileSync`,
`createWriteStream` and `appendFileSync` as three separate child processes for *every* trap since the
first run, and `tapiPlans` had run all three against T01. Two filing decisions of mine hid that:

| cause | mechanism | evidence |
|---|---|---|
| `extra: true` on every cell whose filename was not one of the 44 required stems | `ci/equality.py:255` drops `extra` cells inside `discover()`, so a pinned T-API row marked extra is not "not compared", it is **invisible** — which `docs/tapi.md` then reports as an entry that was never run | the three rows existed at 09:00 and read 0 rows at 11:31 |
| `case_id: "TAPI-T01"` | the manifest pins `case_group=tapi, case_id=T-API` (`tapi_cells_per_language`); a row under a spelling the leg does not pin matches nothing | `spec/cells-required.json`, 26 pinned rows, 3 of them typescript |

Fixed in the port, not in the ruler: `tapiPlans` now takes the identity **from the manifest**
(`loadRequiredSet().tapiRows`, runner.ts:1132) and refuses to start if the manifest pins an entry this
port has no driver for; `extra` now means "outside every list the manifest pins", with the two pinned
exceptions (`tapi_cells_per_language`, and a non-primary entry leg of a required identity) each
required to **cite** the list that pins it (`tapi_pinned_in_manifest`, `published_as_leg_of`) — the rule
is `classify_extra_claims()` in `selfcheck.py`, with a green and a red arm in `--selftest-rules`
(`green_passes=True, red_caught=True`, rc=0).

Seven cells landed additively at 11:4x–11:5x host clock. **Nothing was removed and nothing pre-existing
was modified**, checked by hashing all 80 files before the run and diffing after:
`pre=80 now=87 removed=0 added=7 pre-existing files modified=0`.

```
tapi__T-API__entry-writeFileSync.json      create ok, 28 bytes on disk, enumerated CON.txt, legal
tapi__T-API__entry-createWriteStream.json  same
tapi__T-API__entry-appendFileSync.json     same
trap__T01__entry-createWriteStream.json    verdict fields identical to trap__T01.json
trap__T01__entry-appendFileSync.json       identical
trap__T04__entry-createWriteStream.json    identical
trap__T04__entry-appendFileSync.json       identical
```

The five control cells were **re-run** as the ruler for this subset (gate.md §8: controls verify the
ruler; a selection containing no control cell must not reach `controls_pass=true` having tested
nothing), and deliberately **not written** — `CTRL … ran as ruler only; not written (subset run)`. The
missing-required reconciliation is skipped on a subset run and says so
(`RECONCILE skipped: subset run …the required identities not in this selection are left exactly as the
face holds them`); before this guard, `--only` would have emitted 44 blocked cells straight over the
measured ones. That guard is the difference between an additive landing and the 07:16 accident.

**What I expected the answer to be, and why:** agreement. All three pinned entries reach the same
`CreateFile`/`open` — `writeFileSync` and `appendFileSync` differ only in the access mode, and
`createWriteStream` adds an asynchronous `finish`/`close` event after the same call. Name legality is
decided by the parse layer *before* any of that, so on a port whose layer-2 finding (C-2) is that
`node:fs` skips Win32 name parsing altogether, three entries agreeing is the expected shape, not a
suspicious one. `spec/gate.md` §2 as corrected says exactly that, and names the TypeScript observation
as the reason the old wording was withdrawn — so `verdict_via=win32` on all three, identical verdict
fields, published as **entry-invariance**. Two of the three traps' legs were measured twice: the first
`trap__T04__entry-*` write carried `os_legality_verdict=unknown` because my spread plan gave its leg
no extended leg, which is an artefact of *my plan's shape* rather than the entry's behaviour, and
publishing that as an entry divergence would have been a manufactured finding. The second write added
the `osprobe` job with the leg's own entry and produced `legal`, matching its sibling.

Read back through the gate's own code (in memory — `ci/tapi_report.py` and `ci/acceptance.py` write
into `docs/`, which this local may not touch, so neither was run):

```
pinned=3 seen=3 covered=[appendFileSync, createWriteStream, writeFileSync] missing=[] rows_landed=3
cells_with_multiple_entries (this port) = 3 keys: tapi/T-API, trap/T01, trap/T04  -- 1 distinct
                                          verdict tuple each
ci/equality.py run with SG_VERDICT_OUT pointed outside the repo:
  cells_with_multiple_entries=2  of_which_spread_disagrees=0  cells_missing_primary=0
  excluded as extra: typescript=36   (the 3 old TAPI-T01 rows are inside that count)
  OUTCOME=RED verdict_disagreements=54   (unchanged from the state the acceptance sheet already held;
                                          only each port's PRIMARY entry enters the cross-port digest,
                                          so the new legs cannot move that number)
```

Two things the contract owner should know they will not get from the face:

1. **`docs/tapi.md`'s "Does an entry change the answer?" paragraph cannot see this data.** It builds
   its cell groups with `by_cell.setdefault(equality.fmt(k), []).append(lst[0])`
   (`ci/tapi_report.py:74`) — one record *per identity key*, so a key holding three entries is appended
   once and `len(rows) > 1` is only ever true when two distinct keys render to the same string. Every
   port will keep reading "answered once" whether or not it published entry legs; the count that does
   see it is `cells_with_multiple_entries` inside `ci/equality.py` (now 2, disagrees 0). I did not
   touch `ci/`; this is reported as an instrument observation, with the line named.
2. **Three superseded files are still on the face and I did not delete them**:
   `tapi__TAPI-T01__entry-{writeFileSync,createWriteStream,appendFileSync}.json`. They stay `extra: true`
   and therefore invisible to the gate, they contradict nothing, and `selfcheck.py` now prints
   `superseded_cells_left_on_face=3` with a pointer from each to the pinned row that replaces it
   (`present=True`). Removing them is the owner's call, not mine, under project rule and the additive-landing
   order. `denominator_disagree` compares `produced - superseded` to the recomputed expectation
   (87 − 3 = 84), so leaving them there cannot silently inflate a count.

## 13. The three load-bearing fields: 61 non-conforming cells → 0 (host clock 11:45–12:0x)

`ci/validate_cells.py` read this face as **24 conform of 80** (61 cells invalid at 87 files) while my
own ruler said `cells_valid=27`. The outside ruler was right and the disagreement was mine: 60 cells
carried `"read_result": null` and 60/14 carried null `roundtrip_ok` / `enum_to_stat_agrees`. A null on
`read_result` is not caution — it is a **missing required field**, and `spec/canonical.md` section 5 has
carried the honest word for that situation since rev4: `not_applicable`, "nothing was read because
nothing landed: creation failed, or the name is a device this project refuses to open", requiring
`read_skipped_reason`. My cells already recorded the reason; they just refused to name the field.

I separated two different things before stamping anything, because the fix is not the same for both:

**36 cells had a leg that was never run, not a leg that could not be run.** The length and bisection
modes wrote a 28-byte file into the scratch directory, enumerated it, and then declined to read it back
because "the question is whether it lands". That was my cell's question, not a fact about Windows, and
it left three verdict fields unrecorded on cells whose answers were sitting on disk. So the instrument
was widened instead of the label changed: `modeLen` and `modeBisect` now run the same read-back leg the
trap cells run — guarded the same way (reserved device names are still never opened; if nothing landed,
the leg says so) — and `modeCanon` now emits the enumeration event it had been omitting. Forty length
cells and one control cell were re-measured in place.

The diff against a snapshot taken before those runs is the part worth reading:

```
cells_changed_vs_snapshot= 36
fields_that_moved= {'read_result': 36, 'roundtrip_ok': 36, 'enum_to_stat_agrees': 4, 'name_mutated': 4}
name_source moved= 0   len_triple moved= 0   (the 12 rungs still read len_ceiling=255 first_fail=256)
```

Every movement is a field that was `null` and is now a measured value. No recorded verdict changed, no
input changed, and the twelve rev7 rungs still report the same ceiling. `name_mutated` went from absent
to `false` on the four standalone bisection cells because they now enumerate the confirming file — that
is a new observation, not a re-labelling. The two `roundtrip_ok=True` cells among them read the pinned
payload back and compared it: `c9fe45b2…` is unchanged on the CANON control cell after its re-run, and
`canon_instruments.agree` is still true, so the control leg still verifies the ruler.

**24 cells genuinely have nothing to record.** Fifteen are reserved device names this port will not open
(the ticket's standing rule), nine refused at create. For those the honest value of `read_result` is the
closed set's own word, so `--conform-face` (a new mode of the runner, not a separate script — it runs
the same function a fresh cell passes through and re-serialises through `serialiseCell`, so a repaired
file and a measured one cannot drift) stamped `not_applicable` on all 24 and kept each
`read_skipped_reason` beside it: `files=87 changed=24 refused=0`, no file created, none removed.

For `roundtrip_ok` and `enum_to_stat_agrees` on those 24 there is no honest value at all, and that one is
the contract's, not mine: `spec/schema.json` types both `{"type": "boolean"}` — no null branch, no
`not_applicable` word — and neither is in its `required` list. Stamping `false` would claim a comparison
that was never made; stamping `true` would claim bytes came back. So the key is **absent and the cell
says why**: `roundtrip_ok_not_observable_reason` / `enum_to_stat_agrees_not_observable_reason`, naming the
leg that would have produced the value. 24 cells carry the first, 9 carry the second. My own ruler accepts
an absence only when it is explained, and still calls an unexplained one a violation — both arms are in
`--selftest-rules` (`red_unexplained_absence_caught=True, green_explained_absence_allowed=True`).

Numbers after the pass, all three rulers, same 87 files:

```
ci/validate_cells.py   | typescript | 87 cells read | 87 valid | 0 invalid |  self-reported 87 |  rc=0
                       invalid cells across the six faces: 0     (my row's SELF-REPORT-DISAGREES is gone)
impl/typescript/selfcheck.py  OUTCOME=GREEN cells_valid=87 cells_invalid_on_rules_other_than_the_two_gaps=0
                       cells_with_not_reached_null_gap_G2=0 (was 55)  cells_required=44/44 cells_blocked=0
                       cells_with_an_unobservable_digest_field_explained=24  UNEXPLAINED_absent=0
face integrity         files=87  non_cell_files_in_results_dir=0  probe_jobs=196 timeouts=0 nonzero_rc=0
```

Three things the owner should decide on rather than inherit:

1. **G-2 has a second shape and it is not fixable by any port.** rev4/rev5 gave `read_result` a fifth
   word and left the two derived booleans with none, so a cell whose read leg legitimately did not run
   is conformant on one field and unrepresentable on two. The gate scores those as NOT-RECORDED, which
   is why `verdict_not_recorded_pairs` is still 121 across the tree — and the rows name other ports too
   (`roundtrip_ok` on the illegal-char control is missing for go, python, rust **and** typescript), so
   this is a schema gap, not a TypeScript habit. A `not_applicable` branch on those two fields — or a
   stated convention that absence *is* the not-applicable answer, which is what the gate already does
   with it — would close it for everyone.
2. **`name_landed_as` is deliberately null on my length cells** (40 of them; it is 45 of 87 across the
   face counting the refused creates). The value exists — the enumeration matched the requested
   component exactly — but the cell already publishes that component as `name_source`, and repeating a
   255-character name in a second field was a recording choice, not an omission of evidence. Consequence
   stated plainly: those cells score NOT-RECORDED for a verdict field, and if the owner wants them in the
   digest, say so and I will stamp the enumerated name (it will then be compared against the other
   ports' landed names, which is a real cross-port question I have not been asked to answer tonight).
3. **`ci/equality.py` does not parse on the working tree right now.** `git status --porcelain` shows it
   modified and uncommitted by another lane, and `python ci/equality.py` exits with `SyntaxError:
   unmatched ')'` at line 944 (the OUTCOME=RED format string takes 13 arguments for 11 placeholders).
   It ran cleanly for me minutes earlier, so the edit is in flight, not abandoned. I did not touch `ci/`.
   The gate readings quoted in this section are from the runs that completed before it broke, plus one
   count recomputed from `git show HEAD:ci/equality.py`'s committed `VERDICT_FIELDS` so the numbers above
   do not depend on the in-flight file.
