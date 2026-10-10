# SENDGUARD S02 — Go port self-check (seat-qoder), contract rev6 run

Round verdict: **controls 5/5 PASS against the sealed baseline; no INSTRUMENT-RED.**
`ci/gap_report.py` reads this port as `matched 44/44, missing 0, outside-list 0, extra-flagged 1`, and
this seat's own checker reports `OUTCOME=PASS` with 0 void cells.

- seat: `seat-qoder`, worker_id `seat-qoder`, language face `go`
- repo `D:\sendguard-work\seat-qoder`, HEAD `f15b399`; no commit, no tag, no push by this seat
- landed cell set: `results/go.windows.x64/` — 49 files, 48 of them rows of `spec/cells-required.json`,
  1 marked `extra: true`
- builder: `C:\Program Files\Go\bin\go.exe`, `go version go1.23.5 windows/amd64`
- runner: `impl/go/rederive/bin/sg.exe`, sha256 pinned before and after the run and equal
  (`exe_face_stable=true`); `harness_version = sg-go-rederive-1.0.0+<exe-sha-12>`
- `spec/cases.yaml` blob face (committed): `git cat-file blob HEAD:spec/cases.yaml` =
  `a7f9a57df1b4d39a19421a54d175e87793100ce3393e363622ca59816e19148b`
- `spec/cells-required.json` face: measured sha256 `3742747dd412e8a9…` **equals** the value
  `spec/FROZEN.md` declares, and the file still carries its own `withdraws` line for the 03:4x version —
  this port re-derived from the current file, as instructed
- host face, recorded per cell: `LongPathsEnabled = 0` (status `present`),
  `GetVolumeInformationW(D:) max_component = 255`, NTFS, `CurrentBuild 19041`, console code page 936
- **runner manifest scan (new, because it turned out to decide a claim):** byte scan of `sg.exe`
  (4,591,616 bytes) for the token `longPathAware` → **0 hits**. Same method and same disclaimer as
  `evidence/S00/env-facts-windows-local.json`: a byte scan, not a PE manifest parse.
- `deps_direct = 0`, `deps_total = 0` everywhere; `golang.org/x/text` is not used and is not in this
  machine's module cache; normalisation cells say `not-achievable-in-stdlib` in words, never a silent 0.

## 1. Counters

```
cells_required=48          (44 generic rows + 4 go T-API rows)
cells_produced=49
cells_valid=49
cells_blocked=0
extra=1
required_matched=48  required_missing=0
identity_collisions=0
unclaimed_dir_view_entries=0
controls_found=5 controls_failed=0
OUTCOME=PASS
```

Cross-checked with three rulers this seat may run but not edit, all rc=0:
`ci/lint.py --selftest`, `ci/lint.py --repo-root`, and the frozen `spec/validate.py` over
`results/go.windows.x64` → **49 valid / 0 void**. (Before the last fix that file said 36 valid / 13 void;
see §5.)

This seat's checker also runs its own green/red arms: `selftest_arms=18 selftest_failed=0`, including red
arms for an unknown status word, for `verdict_via` absent, for a `len` cell without an integer `base_len`,
for a control cell whose name is not the pinned sample, and for `roundtrip_ok` published as `null`.

## 2. Item 1 — which layer my legality verdict asks, and in which path form

**The `legal` on `trap/T03` and `ctrl/T-CTRL-ILLEGAL-CHAR` was a wrong answer, and the reason was my
probe, not the file system.** The verdict used to be taken from `FindFirstFileW`. That is a query API:
for `a<b.txt` it answers `ERROR_FILE_NOT_FOUND (2)`, and this port's mapping read "2 = the OS accepted the
name and reported it absent" → `legal`. A query does not validate a name, so "absent" and "illegal" are
the same answer to it, and five other ports were right where I was wrong.

The verdict is now taken from a probe that can answer the question:

| field | value in every cell that has a verdict |
|---|---|
| `verdict_via` | `win32` |
| `verdict_via_probe` | `kernel32!CreateFileW(CREATE_NEW) + directory listing` |
| `verdict_via_path_form` | the cell's own `path_form` (see below) |

`rawCreateFileW` calls kernel32!CreateFileW through `LoadDLL`/`FindProc` with a UTF-16 pointer this port
built itself — **not** Go's `syscall.CreateFile` wrapper, which is part of the layer under test. It creates
in a dedicated sibling directory (`<sandbox>\l\<same-depth chain>`) that the parent verified empty, never
writes a payload, never reads contents, and then lists that directory and compares the entry the file
system actually stored with the name that was asked. `FindFirstFileW` is still run and published, renamed
to `legality_probe_second_face_findfirstfile`, precisely so a reader can see the face that lies.

Machine-checked, across all 49 landed cells:

- cells whose probe path form differs from the recorded `path_form`: **0**. The `plain` cells (43) are
  asked on the plain absolute path; the six `extended` len cells are asked through `\\?\`, and they record
  `path_form: extended` — the record and the ask agree in both directions, so there is nothing to fix in
  the record.
- `verdict_via`/probe pairs present: `(win32, CreateFileW+listing)` and `(none, none)`. The `none` pair is
  exactly one cell, `T-CTRL-PARSE`: its name carries an embedded NUL, this runtime refused it before any
  call, so the OS has no answer and the verdict is `unknown`. That cell is the reason `schema.json` needs
  `none` in the `verdict_via` enum; `spec/cell-identity.md` §6 lists only four values and omits it.
- answers that changed against the previous run: `T03` and `T-CTRL-ILLEGAL-CHAR` `legal → illegal`;
  `T-CTRL-NAMETOOLONG` `legal → illegal` (CREATE_NEW refuses the 256-unit component with
  `ERROR_INVALID_NAME 123`). `trap/T01` stays `illegal` — and stays illegal for the right reason now:
  the create is refused and the listing of the probe directory is empty.

## 3. Item 2 — the five control cells on the pinned samples

Names and payloads now come from `spec/cases.yaml control_samples`, decoded at run time; this port no
longer supplies a name of its own to any control cell.

| cell | pinned `sample_hex` | run name | create | verdict | pass |
|---|---|---|---|---|---|
| T-CTRL-ASCII | `7265706f72742d323032362e747874` | `report-2026.txt` | ok, 28 written / 28 on disk, read ok | legal | yes |
| T-CTRL-ILLEGAL-CHAR | `613c622e747874` | `a<b.txt` | err_at_syscall 123 | illegal | yes |
| T-CTRL-PARSE | `6e756c00627974652e747874` | `nul\x00byte.txt` | err_at_parse | unknown (`verdict_via=none`) | yes |
| T-CTRL-NAMETOOLONG | 256 × `a` | `aaa…` | err_at_syscall 123 | illegal | yes |
| T-CTRL-CANON | `63616e6f6e2d636865636b2e747874` | **`canon-check.txt`** | ok | legal | yes |

`T-CTRL-CANON` is the one this seat had invented: the previous run used `canon-go-arm.txt`, which is
exactly the drift rev6 §6 names (`canon-csharp.txt` / `canon-go-arm.txt` / `canon-python.txt` /
`report-2026.txt` under one cell id). Both payload hashes are the pinned 28 bytes
`SENDGUARD-CANON-PAYLOAD-2026`: `sha256_self` (this port's own hash of what it wrote) equals
`sha256_truth` (the independent `C:\Python314\python.exe` read-back arm hashing what the **directory
enumerated**, never the requested path) equals `c9fe45b2fee8ea84…`. The checker's red arm proves it
would notice if a cell carried a name other than the pinned hex.

## 4. Item 3 — the twelve length cells, and what they measured

All twelve rungs ran: `T17`/`T18` × `base_len ∈ {78, 120, 200}` × `path_form ∈ {plain, extended}`.
`run_status: ran` on all twelve; **no cell needed `blocked`**, so none was emitted as absent either.

Each cell is a bisection of the name length over the bracket `[1, 260]` — 260 = measured
`max_component 255 + 5`, above every candidate ceiling — 12 probes per face, three faces walked per cell in
three sibling directories at an *identical absolute depth* (the parent refuses to run if the depths
differ), plus verification points at `boundary-1` and `boundary+1`. The cell's own record is the boundary
name of its authoritative face: `os.Create(plain)` for the plain cells, `explicit(\\?\)` for the extended
ones. All attempt records, including every rejected probe's name hex, are published in `bisection.faces[].attempts`,
which is what makes the directory listings of those probe directories claim-covered
(`unclaimed_dir_view_entries=0`).

| case | rung | form | abs dir length | boundary | abs total at boundary | create |
|---|---|---|---|---|---|---|
| T17 / T18 | 78 | plain and extended | 134 | 255 | 390 | ok |
| T17 / T18 | 120 | plain and extended | 176 | 255 | 432 | ok |
| T17 / T18 | 200 | plain and extended | 256 | 255 | 512 | ok |

Every one of the twelve boundaries is 255, and the three faces agree at every rung — including
`kernel32!CreateFileW(raw)` on a **plain** path of 512 units at rung 200. The 259-unit ceiling the ladder
is built around was never observed on this host by this binary:

| rung | `259 - abs_dir - 1` (the model's prediction) | observed plain boundary |
|---|---|---|
| 78 | 124 | 255 |
| 120 | 82 | 255 |
| 200 | 2 | 255 |

Consequences, stated rather than smoothed: (a) `longpath_mechanism` is `none` on all twelve cells, and the
`prefix_rewrite` claim in my earlier self-check is **withdrawn** — it was inferred from one layer's answer
("a long plain path worked while `LongPathsEnabled=0`"), and the three-face ladder shows the raw entry says
yes too, so nothing had to be rewritten. The runner carries no `longPathAware` token, so this is not a
manifest effect either. (b) Because `len_triple` is now a `VERDICT_FIELD` and a len cell's `len_triple`
describes the boundary name its own layer accepted, two ports can differ there for an *environment* reason
and be called a verdict disagreement. See §7.

## 5. Fields rev6 forced me to move, and one I had to stop publishing

- `length_unit = utf16_code_units` (the unit a length came from) and `name_encoding = hex_raw_bytes`
  (how the name in the record is encoded: lowercase hex of the name's raw UTF-8 bytes, the face
  `spec/cases.yaml` pins; the UTF-16LE and code-point faces of every enumerated name are published beside
  it in `dir_view`). The split is the port's; the collision was the contract's.
- `sub_identity` is now an **object** (`{"base_len": 78, "path_form": "plain"}`), with numbers as numbers
  so it renders identically to the manifest row it must match; the ordered list is kept beside it as
  `sub_identity_declared`. The previous array form is what `ci/equality.py` logs as a contract defect.
- `run_status` on every cell (`ran` here; `blocked` plus command, exit code and one attempted fix is what
  an unrunnable rung would have carried).
- **`roundtrip_ok` and `enum_to_stat_agrees` are no longer published as `null`.** They are
  `VERDICT_FIELDS`, not nullable in `spec/schema.json`, and the frozen `spec/validate.py:67-71` voids a
  present-but-non-boolean one — which is how 13 of my 49 cells came out VOID under the ruler that ships.
  rev6 §9.1 says an answer a port did not record stays `NOT-RECORDED`, a completeness finding and never an
  answer, so where the leg did not run the field is now absent and the reason sits beside it in
  `roundtrip_ok_basis` / `enum_to_stat_agrees_basis`. `read_leg_executed` and `roundtrip_leg_executed`
  still say which legs ran: 25 of 49 cells executed a read.
- `blind_id` is an integer on the five blind cells.

## 6. What the cells say (data, not judgment)

Five blind samples, all run for the first time in this port, all on the pinned entry `os.Create`, plain
form: `invoice_FINAL_2026.xlsx`, `photo_2_.jpg`, `Copy_of_report.docx`, `data_v2_1_.csv`,
`weekend-report.txt` — every one created ok, 28/28 bytes, read ok, name enumerated unchanged
(`name_mutated=false`), `os_legality_verdict=legal`, `mechanism_class=unknown` with
`case_category_frozen` absent: the frozen corpus never classified these shapes, so I did not pick a class.

Reserved device names, primary entry (`!` = create reported success and the directory stored nothing):
`CON.txt` / `CON` / `PRN` / `LPT9` → `err_at_syscall 87`; `NUL.tar.gz` → `ok!`; `COM1.log` → `ok!`;
`AUX.log` → `ok!`. `entry_spread` carries the other three entries per member: on `CON.txt`,
`os.OpenFile` says `ok!` where `os.Create` says `err_at_syscall`; on `NUL.tar.gz` three entries say `ok!`.
`os.WriteFile` against the seven reserved names is recorded inside those spreads as `blocked` (it is one
indivisible open+write; running it as pinned would push 28 bytes into a device — `PRN` would queue a print
job, `COM1` would drive a serial port), which is why the published T-API row for `os.WriteFile` is the only
place that entry is judged, and it disagrees with the primary entry on exactly those seven members
(`tapi_spread.disagreements`: T01, T02, T10, T11, T14-m1, T14-m2, T14-m3). `os.Mkdir` disagrees on 20 of 22
members, and the trap cells that ran it (`os.Mkdir` is not the primary entry) keep that in `entry_spread`
rather than as separate files — four cells at one `(case_group, case_id, sub_identity)` is the gate's
`ambiguous_entries` refusal, and `spec/cell-identity.md` §2 asks for the spread instead.

`T04` `trail.` lands as `trail`, `T05` `trailsp ` lands as `trailsp`, on all four entries:
`name_mutated=true`, `name_landed_as` carries the enumerated hex, `enum_to_stat_agrees=false`.
`T09-m1`/`T09-m2`, `T14-m1..m3`, `T19-m1`/`T19-m2` share one directory per `(case × entry)` by design —
coexistence in **one** directory is the frozen question — and the parent's post-group listing shows both or
all three members present together (`members_in_dir_after_group`), while a member's own dir_view legitimately
predates a sibling that ran after it (`same_name_hits` distinguishes the two readings; both are published).

The `extra` cell is the zip round trip with `packer` and `extractor` as declared dimensions
(`go.archive/zip+go1.23.5`): the ASCII frozen name is written with bit 11 clear, the two non-ASCII frozen
names with bit 11 set, and all three entry names read back byte-equal.

## 7. Contract defects found in rev6, with the run kept going on the pinned bytes

1. **`len_triple` is a `VERDICT_FIELD` but its value comes from a probe-dependent boundary.** For a length
   cell the recorded name *is* the boundary its own layer accepted, so a port whose runtime enforces the
   259-unit ceiling would publish `124/124/124` at rung 78 where this port publishes `255/255/255`, and the
   gate would call that a verdict disagreement when it is an environment difference — the thing §9.3 was
   written to avoid. Either move `len_triple` for the `len` group into `PROBE_FIELDS`, or have the len cells
   pin `len_triple` to the ladder's bracket name rather than to its result. This port kept the pinned-byte
   reading and says so here.
2. **The ladder's premise is not true on this host.** `259 - base_len - 1` predicts 124 / 82 / 2; the raw
   `kernel32!CreateFileW` accepted 255-unit names at all three rungs (absolute totals 390, 432, 512) with
   `LongPathsEnabled=0` and no `longPathAware` token in the measuring binary. If the rungs are meant to
   straddle something, that something is not present here, and cells that answer 255 everywhere are the
   honest output of the pinned procedure.
3. **`verdict_via` is required by the NOTICE but not by `spec/schema.json`'s `required` array** (it is only
   in `properties`), and `spec/cell-identity.md` §6 lists four values while `schema.json` allows a fifth,
   `none`. This port enforces the NOTICE in its own checker, uses `none` for the single cell where no tool
   was asked, and reports both gaps instead of patching either file.
4. **`spec/validate.py` still knows only the pre-rev3 `name_encoding` enum.** It is frozen at sha
   `f19a5d14…` and listed in `FROZEN.md`, so the two frozen rulers disagree with each other about a rev3+
   cell: `schema.json` accepts `hex_raw_bytes`, `validate.py` would call it an unknown status word. The 49
   cells pass both today only because `validate.py` checks `name_encoding` against its own set — measured:
   it reports 49 valid, so its set evidently no longer bites, and I record that as luck rather than design.
5. `generated_at` is absent from the current `spec/cells-required.json` (the checker prints `None`), so the
   withdrawal of the 03:4x version can only be read from the `withdraws` string, not from a timestamp.
6. Nothing else in rev6 was wrong in a way this port had to work around: the folding of `T09a → T09-m1`,
   the `\\?\` identity for `len`, and §9.5's canonical-face rule all removed problems I had reported in
   earlier rounds.

## 8. Reproducibility, retained state, and what this document does not prove

- The grid was run twice more into directories outside the repo and compared field by field over the ten
  `VERDICT_FIELDS`: **0 differences in 49 cells**, verdict-digest equal
  (`ef8119c139efaae7…` on both faces). 137 child processes per run, one per cell, each under an externally
  enforced 5 s ceiling: `timed_out=0`, `create_result=hang` count 0; a timeout would have been recorded as
  `hang` with the child's last phase as the stage and the parent's own post-mortem listing printed beside it.
- **119 superseded pre-rev6 cell files** (the 139-cell round's residue after the first 49 landed) were
  **moved, not deleted**, to `D:\sendguard-run\_superseded-go-pre-rev6\`; they are the previous contract
  revision's records and this face must not mix two revisions. The earlier version of this self-check
  document was untracked in git and was rewritten rather than preserved, so its prose survives only where
  §2 and §4 restate the two claims it made that this round contradicts (the `prefix_rewrite` claim is
  withdrawn there; the earlier `FindFirstFileW` legality rule is named there).
- Sandbox directories accumulate under `D:\sendguard-run\<uuid>\` — the measured dir plus same-depth
  siblings for the extended probe, the legality probe and the three bisection faces. This port contains no
  delete call anywhere; the checker counts it: `deletion_calls_found=0` over `files_scanned=13`.
  `cleanup-notice.md` gives the operator the `\\?\` removal recipe; this seat did not run it.
- No aggregate file is written: `ci/export_aggregate.py` still does not exist, and hand-writing an
  aggregate is what `spec/cell-identity.md` §3 forbids. Instrument output is in
  `evidence/S02/go-run-manifest.json`, not in `results/`.
- Independence, as a discipline statement: this seat opened no file under any other port's `impl/` or
  `results/`, and did not open `impl/go/main.go`, `impl/go/run_log.txt`,
  `evidence/S02/ctrl-go-json/`, `evidence/S02/conflicts/` or any other port's `*-selfcheck.md`. Two
  name-level queries were made (`ls impl`, `git ls-files results/`); no bytes of another port's records were
  read. `ci/gap_report.py` was run with `--out` redirected **outside** `docs/`, because its default target
  is `docs/GAP.md` and this seat may not write there; the go block was read from that scratch copy, and
  only the go block.
- Not proven here: any cross-port equality verdict (that is `ci/equality.py`'s and S03's), any
  `attribution_layer` (the first pass of `spec/attribution-tree.md` §1 needs the other five ports' answers,
  and Q3 alone would let one port pre-decide an L2/L3 call), and whether the 255-everywhere result holds on
  a host where the ceiling is enforced — this run states one machine's answers and names its environment
  facts.

## 9. Files this seat wrote

`impl/go/rederive/` (13 `.go` files + `selfcheck.py` + `go.mod`, `bin/sg.exe` gitignored),
`results/go.windows.x64/` (49 cell files), `evidence/S02/go-selfcheck.md` (this file),
`evidence/S02/go-run-manifest.json`. Nothing under `spec/`, `ci/`, `harness/`, `docs/` or `D:\sendguard`
was written, and `results/go.windows.go1.23.5` was left where it is.
