# SENDGUARD S02 — Go port self-check (session-token), contract rev7 run

Round verdict: **controls 5/5 PASS against the sealed baseline and against the pinned control samples.
No INSTRUMENT-RED.** This local's checker says `OUTCOME=PASS` with 0 void cells, and `ci/gap_report.py`
reads this port as `matched 44/44, missing 0, outside-list 0, extra-flagged 1`.

- local `session-token`, language face `go`; repo `D:\work\session-token`, HEAD at the time of writing
  `177ecc6`; no commit, no tag, no push by this local
- landed face `results/go.windows.x64/` — 49 cell files: 22 trap + 5 ctrl + 12 len + 5 blind + 4 T-API,
  plus 1 `extra: true` zip cell. Nothing else is in that directory; `results/go.windows.go1.23.5` was left
  exactly where it is.
- builder `C:\Program Files\Go\bin\go.exe`, `go version go1.23.5 windows/amd64`; runner
  `impl/go/rederive/bin/sg.exe`, sha256 pinned before and after the run and equal (`exe_face_stable=true`),
  `harness_version = sg-go-rederive-1.0.0+<exe-sha-12>`
- `spec/cases.yaml` at the committed blob face: `git cat-file blob HEAD:spec/cases.yaml` =
  `8650a1863578231e…`, which is what every cell records in `provenance.spec_sha256`, and it equals the
  worktree face and the value `spec/FROZEN.md` declares. `freeze_revision` read from the file: `2`.
- Locked-artifact check this local ran (8 files): `spec/cases.yaml`, `gate.md`, `canonical.md`,
  `attribution-tree.md`, `validate.py`, `schema.json`, `cell-identity.md`, `cells-required.json` — all
  eight measured shas equal the values declared in `spec/FROZEN.md`.
- `spec/cells-required.json`: measured sha256 equals the FROZEN declaration, and the file still carries its
  own `withdraws` sentence for the 03:4x version. This port re-derived from the current file, after rev7
  re-sealed it.
- host face per cell: `LongPathsEnabled = 0` (status `present`), `max_component = 255`
  (`GetVolumeInformationW`, NTFS), `CurrentBuild 19041`, console code page 936, independent read-back arm
  `C:\Python314\python.exe`.
- `deps_direct = 0`, `deps_total = 0` on every cell; no external module (`golang.org/x/text` is unused and
  absent from this machine's module cache); the normalisation cells carry
  `normalization_dependency = "not-achievable-in-stdlib: …"` in words, never a silent 0.

## 1. Counters (this local's own checker)

```
cells_required=48        (44 rows of spec/cells-required.json + the 4 go T-API rows)
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

Other rulers, run not edited, all rc=0: `ci/lint.py --selftest`, `ci/lint.py --repo-root`, and the frozen
`spec/validate.py` over the landed face → **49 valid / 0 void**. The checker's own arms:
`selftest_arms=23 selftest_failed=0`, green and red, including red arms for a status word outside
`canonical.md`, for `verdict_via` absent, for a control cell whose name is not the pinned sample, for
`roundtrip_ok` published as `null`, and for `len_triple` carrying either a label's length or a measured
ceiling (both failure modes rev7 names in its table).

Reproducibility: the grid was run again into a directory outside the repo and compared field by field over
the ten `VERDICT_FIELDS` — **0 differences in 49 cells**. 137 child processes per run, one per cell, each
under an externally enforced 5 s ceiling: `timed_out=0`, `create_result=hang` count 0.

## 2. rev6 item 1 — which layer my legality verdict asks, and in which path form

**A wrong answer of mine, corrected.** Until rev6 this port took `os_legality_verdict` from
`FindFirstFileW`, a *query* API: for `a<b.txt` it answers `ERROR_FILE_NOT_FOUND (2)`, and my mapping read
"2 = the OS accepted the name and reported it absent" → `legal`. A query does not validate a name, so
"absent" and "illegal" are one answer to it; five other ports were right where I was wrong.

The verdict now comes from a probe that can answer the question — `verdict_via = win32`,
`verdict_via_probe = kernel32!CreateFileW(CREATE_NEW) + directory listing`. `rawCreateFileW` reaches
kernel32 through `LoadDLL`/`FindProc` with a UTF-16 pointer this port builds itself, deliberately **not**
Go's `syscall.CreateFile` wrapper, which belongs to the layer under test. It creates in a dedicated sibling
directory the parent verified empty, writes no payload, reads no contents, then lists that directory and
compares the entry the file system stored with the name that was asked. `FindFirstFileW` is still run and
published, renamed `legality_probe_second_face_findfirstfile`, so the face that lies stays visible.

Machine-checked over the 49 landed cells:
- cells whose probe path form differs from the recorded `path_form`: **0**. The 43 plain cells are asked on
  the plain absolute path; the 6 extended len cells are asked through `\\?\` and record
  `path_form: extended`, so the record and the ask agree in both directions and nothing had to be fixed in
  the record;
- `verdict_via`: `win32` × 48, `none` × 1 (`T-CTRL-PARSE`, whose embedded NUL this runtime refused before
  any call — the OS has no answer, so `unknown` is the only lawful verdict there);
- answers that moved against the previous run: `T03`, `T-CTRL-ILLEGAL-CHAR` and `T-CTRL-NAMETOOLONG`
  `legal → illegal`; `trap/T01` stays `illegal` for the right reason (the create is refused **and** the
  probe directory stays empty).
- the two probes are corroborated rather than merged: when CREATE_NEW answers 2 and the same cell's create
  attempt was refused by the name itself (123/161/206/87), the verdict is `illegal` and the note names both
  codes. Where there is no name-level refusal beside it, this port keeps `unknown`.

**Open item, named not hidden:** `trap/T14-m1` (`PRN`) and `trap/T14-m3` (`LPT9`) are `unknown` in this
face because the OS answered `winerror 2 (ERROR_FILE_NOT_FOUND)` to *both* the cell's create attempt and
the legality probe — the recorded answer is "no such file", not "invalid name". `T14-m2` (`AUX.log`) is
`illegal`. Any port that reports `illegal` for PRN/LPT9 got there from the reserved-name list rather than
from what the create call answered on this machine; S03 should treat those two cells as a
comparability item, which is what rev6 §9.4 is for. This local did not upgrade the code to fit the list.

## 3. rev6 item 2 — the five control cells on the pinned samples

Names and payloads are read out of `spec/cases.yaml control_samples` at run time; no control cell carries a
name this port chose. All five pinned `payload_hex` values are cross-checked for agreement when the spec is
loaded, and the write payload is the pinned one.

| cell | pinned hex | name | create | verdict |
|---|---|---|---|---|
| T-CTRL-ASCII | `7265706f72742d323032362e747874` | `report-2026.txt` | ok, 28 written / 28 on disk, read ok | legal |
| T-CTRL-ILLEGAL-CHAR | `613c622e747874` | `a<b.txt` | err_at_syscall 123 | illegal |
| T-CTRL-PARSE | `6e756c00627974652e747874` | `nul\x00byte.txt` | err_at_parse | unknown |
| T-CTRL-NAMETOOLONG | 256 × `61` | `aaa…` | err_at_syscall 123 | illegal |
| T-CTRL-CANON | `63616e6f6e2d636865636b2e747874` | **`canon-check.txt`** | ok | legal |

`T-CTRL-CANON` is the one this local had invented: the previous run used `canon-go-arm.txt`, exactly the
drift rev6 §6 names. Both CANON arms now hash the pinned 28 bytes
(`SENDGUARD-CANON-PAYLOAD-2026`): `sha256_self` (what this port wrote) equals `sha256_truth`
(`C:\Python314\python.exe` hashing the bytes the **directory enumerated**, never the requested path) equals
the baseline `c9fe45b2fee8ea84…`.

## 4. rev7 — the twelve length cells, re-emitted under the pinned filler

`name_source` is the hex of the component actually handed to the API: `spec/cases.yaml len_fill.unit_hex`
(`61`, U+0061) repeated until the component is exactly `base_len` code units, nothing appended. So
`len/T17[base_len=78,path_form=plain]` carries 78 `61` pairs and `len_triple = 78/78/78`; the 200-rung
cells carry 200 and read `200/200/200`. `base_len` is a name width, not a directory depth, so the padded
directory chain this port used in the rev6 run is gone and every cell now measures in the ordinary
sandbox directory.

The ceiling is a separate field, `len_ceiling`, holding the authoritative face, the converged
`ceiling_code_units`, the bracket `[1, 260]` (260 = measured `max_component 255 + 5`), the probe count, and
the boundary of each of the three faces walked at one identical depth: `os.Create(plain)`,
`kernel32!CreateFileW(raw)`, and `explicit(\\?\)` — 12 probes each, 36 per cell, every attempt published in
`bisection.faces[].attempts` with its name hex, which is what keeps the listings claim-covered.

| rung | form | name width | `len_triple` | ceiling (all three faces) | create | probes |
|---|---|---|---|---|---|---|
| 78 | plain, extended | 78 | 78/78/78 | 255 | ok | 12 per face |
| 120 | plain, extended | 120 | 120/120/120 | 255 | ok | 12 per face |
| 200 | plain, extended | 200 | 200/200/200 | 255 | ok | 12 per face |

Twelve of twelve ran, so `run_status: blocked` was not needed and no rung is absent. What the ladder shows
on this machine: the component ceiling is 255 code units at every rung and in both forms, and the two
forms agree, because `kernel32!CreateFileW` accepted a plain path of 255 + a 256-unit directory at every
rung — no 259-unit wall appeared. Two claims of mine are withdrawn on that evidence: the earlier
`longpath_mechanism = prefix_rewrite` inference (the raw OS entry says yes too, so nothing was rewritten;
the value is `none` on all twelve cells) and the rev6 statement that a rung at 512 units was only reachable
via a rewrite. Corollary for the manifest: the scanning instrument was itself broken and is fixed —
the first version searched for a plain string that is compiled into `sg.exe`, so it reported 0 hits on one
build and 1 on the next with no manifest change. The needle is now assembled at run time from an obfuscated
copy and a green arm was added: the same scan finds 2 hits in `C:\Python314\python.exe` (which is what
`evidence/freeze/env-facts-windows-local.json` records) and **0** in this runner. Byte scan, not a PE
manifest parse, with the same disclaimer the S00 file carries.

## 5. What the rest of the face says (data, not judgment)

Blind, all five, first time this port ran them, primary entry, plain form: `invoice_FINAL_2026.xlsx`,
`photo_2_.jpg`, `Copy_of_report.docx`, `data_v2_1_.csv`, `weekend-report.txt` — every one created ok, 28
written / 28 on disk, read ok, name enumerated unchanged, `os_legality_verdict=legal`,
`mechanism_class=unknown` with `blind_id` an integer: the frozen corpus never classified these shapes, so
this port did not pick a class.

Totals: `create_result` ok 40 / err_at_syscall 8 / err_at_parse 1; verdict legal 29 / illegal 17 /
unknown 3; 36 of 49 cells executed a read; 41 recorded `enum_to_stat_agrees`.
`roundtrip_ok` and `enum_to_stat_agrees` are **absent** where the leg did not run rather than `null` —
they are not nullable in `spec/schema.json`, the frozen `validate.py` voids a non-boolean one (that was
13 VOID cells before this fix), and rev6 §9.1 says an unrecorded answer is a completeness finding, never an
answer. The reason sits beside them in `roundtrip_ok_basis` / `enum_to_stat_agrees_basis`, and
`read_leg_executed` / `roundtrip_leg_executed` say which legs ran.

Reserved-device names, primary entry (`!` = create said yes and the directory stored nothing):
`NUL.tar.gz`, `COM1.log`, `AUX.log` → `ok!`; `CON.txt`, `CON` → `err_at_syscall 87`; `PRN`, `LPT9` →
`err_at_syscall 2`. `entry_spread` carries the other entries per member — on `CON.txt`,
`os.OpenFile` says `ok!` where `os.Create` says `err_at_syscall`; on `NUL.tar.gz` three entries say `ok!`.
The T-API rows roll up per entry: `os.Mkdir` answers differently from the primary on 20 of 22 members, and
`os.WriteFile` on exactly the seven reserved names, where it is recorded **blocked** inside the spread
(it is one indivisible open+write; running it as pinned would push 28 bytes into a device — `PRN` would
queue a print job, `COM1` would drive a serial port, and the local order allows those names to be created
and listed only). Those seven are this port's only unmeasured legs; none of them is a published cell, so
none is a silent pass.

`T04`/`T05` land stripped (`trail.`, `trailsp `), `name_mutated=true` on all four entries, and
`enum_to_stat_agrees=false` is the IV' drift a port that only stats would not see. Multi-member cases share
one directory per `(case × entry)` on purpose; `coexistence` publishes both the cell's own listing and the
parent's post-group listing (`members_in_dir_after_group`), because the frozen question is coexistence in
ONE directory. The `extra` cell is the zip round trip with `packer`/`extractor` = `go.archive/zip+go1.23.5`:
the ASCII frozen name is written with bit 11 clear, the two non-ASCII frozen names with bit 11 set, and all
three names read back byte-equal.

## 6. State, and what this document does not prove

- 119 superseded pre-rev6 cell files were **moved, not deleted**, to
  `D:\work-run\_superseded-go-pre-rev6\`; `git status` shows 0 tracked deletions, so nothing committed
  was removed. The previous version of this self-check document was untracked and has been rewritten: its
  two claims that this round contradicts (the `prefix_rewrite` inference and the `FindFirstFileW` legality
  rule) are restated and withdrawn in §2 and §4 rather than left standing.
- Sandbox directories accumulate under `D:\work-run\<uuid>\` (49 per run, plus earlier runs and the
  out-of-repo verification trees): measured dir plus same-depth siblings for the extended probe, the
  legality probe and the three bisection faces. No delete call exists in this port; the checker counts it
  (`deletion_calls_found=0` over `files_scanned=13`). `docs/cleanup-notice.md` gives the operator the
  `\\?\` recipe; this local did not run it.
- No aggregate file is written: `ci/export_aggregate.py` still does not exist and hand-writing one is what
  `spec/cell-identity.md` §3 forbids. Instrument output is `evidence/judgement/go-run-manifest.json`, never
  `results/`.
- Independence, as discipline not measurement: no file under another port's `impl/` or `results/` was
  opened, and `impl/go/main.go`, `impl/go/run_log.txt`, `evidence/judgement/ctrl-go-json/`,
  `evidence/judgement/conflicts/` and the other ports' `*-selfcheck.md` were not read. Two name-level queries were
  made (`ls impl`, `git ls-files results/`), and `ci/gap_report.py` was run with `--out` redirected outside
  `docs/` — its default target is `docs/GAP.md`, which this local may not write — and only the go block of
  that scratch copy was read.
- Not proven here: cross-port equality (S03's, and `ci/equality.py` was never run by this local because its
  output would show other ports' answers), any `attribution_layer` (`spec/attribution-tree.md` §1's first
  pass needs the other five ports), and whether the 255-everywhere ceiling result holds on a host where the
  259-unit wall is enforced. The `PRN`/`LPT9` unknowns in §2 are the one place this face knowingly differs
  from a verdict another port can reach from the reserved-name list.

## 7. Contract items left open by this round

1. `verdict_via` is required by the NOTICE but is absent from `spec/schema.json`'s `required` array, and
   `spec/cell-identity.md` §6 lists four values while `schema.json` allows a fifth (`none`). This port
   enforces the NOTICE in its own checker; the two files still disagree about what "required" means.
2. `len_triple` is a `VERDICT_FIELD`, and rev7 resolved exactly the hazard I raised: the triple now
   describes the pinned name, so it is comparable, while the ceiling moved to `len_ceiling` where a
   per-port environment answer belongs. Nothing further is asked, but note that `len_ceiling` is not in any
   field class, so a reader could still mistake it for a verdict.
3. `base_len` in `spec/cells-required.json` is a name width under rev7, but `spec/gate.md` §5 still
   describes domain B as four base tiers each hitting `259 - base - 1` and `spec/FROZEN.md` still prints the
   G1-G4 grid with tiers 13/120/200. Those two sentences are from the directory-depth reading and now
   disagree with the pinned rule; this port followed `len_fill`.
4. `spec/cells-required.json` has no `generated_at` key (the checker prints `None`), so its withdrawal of the
   03:4x version rests on the `withdraws` sentence alone.

## 8. Files this local wrote

`impl/go/rederive/` (13 `.go` files, `selfcheck.py`, `go.mod`, `bin/sg.exe` gitignored),
`results/go.windows.x64/` (49 cells), `evidence/judgement/go-selfcheck.md` (this file),
`evidence/judgement/go-run-manifest.json`. Nothing under `spec/`, `ci/`, `harness/`, `docs/` or `D:\local-dir`
was written by this local, and no other port's face was touched.


---

## Addendum, 2026-10-11 08:3x host clock - one false verdict of mine, found and re-landed (rev7 re-send)

Re-checking the twelve length cells against this repo's own recorded environment fact ("ordinary paths
reach 259 units in total, only a prefixed form shows 255") contradicted what my cells said, so the ceiling
was re-measured outside the repo with three faces over a directory of known length: plain
`kernel32!CreateFileW` accepted a 255-unit component at a 285-unit total path and the entries really
landed (the listing showed components of 10, 100 and 255 units), and 256 was refused with
`ERROR_INVALID_NAME 123`. `len_ceiling = 255` is therefore this host's answer for this binary and stands,
consistent with the manifest scan finding no `longPathAware` token in the runner.

That re-measurement found a defect of mine instead. `legalityCreateProbe` built its extended-form path with
a three-character prefix, one backslash short, so the six cells recording `path_form: extended` were asked

    backslash  question  backslash  D : ...

the OS answered 123, and my mapping published `os_legality_verdict = illegal`. **Six landed cells carried a
false verdict.** A cell whose record says extended must be *asked* extended: the record was right and the
ask was wrong, which is the mirror image of what rev6 item 1 warned about.

Fixed and re-landed. The prefix is now the four bytes `\\?\`, and the probe publishes
`asked_path_head_hex` - the head of the exact path handed to `CreateFileW` - so the claim can be checked
from the record instead of from my source. `selfcheck.py` gained a leg for it (an extended cell must show
head `5c5c3f5c`, a plain cell `443a5c`) plus one green and one red arm, the red arm being this exact typo:
`selftest_arms=25 selftest_failed=0`.

| the six `path_form: extended` len cells | verdict |
|---|---|
| before the fix (asked with a three-character prefix, winerror 123, nothing created) | `illegal` - false |
| after the fix (asked with `\\?\`, created, the entry enumerated under the name asked) | `legal` |

Verdict totals over the 49 cells moved from legal 29 / illegal 17 / unknown 3 to
**legal 35 / illegal 11 / unknown 3**.

Rev7 invariants re-checked on the re-landed face and unchanged: `name_source` is `61` repeated `base_len`
times (156 / 240 / 400 hex characters), `len_triple` is that name's width (`78/78/78`, `120/120/120`,
`200/200/200`), the ceiling is its own field `len_ceiling` (255 on all three faces at all three rungs,
12 probes per face), all twelve `run_status: ran`, and the twelve identities are exactly `len/T17` and
`len/T18` at `base_len` in {78, 120, 200} times `path_form` in {plain, extended}. Rulers after the
re-land: this checker `OUTCOME=PASS`, 49 valid / 0 void under the frozen `spec/validate.py`,
`ci/gap_report.py` `matched 44/44, missing 0, outside-list 0, extra-flagged 1`, controls 5/5.

Still open, named not hidden: `trap/T14-m1` (`PRN`) and `trap/T14-m3` (`LPT9`) stay `unknown`, because the
OS answered `winerror 2` to both the create attempt and the legality probe in those cells; `T14-m2`
(`AUX.log`) is `illegal`.

Clock, stated plainly: the rev7 re-send asked for 07:30 and this correction landed at 08:3x. The six
wrongly-judged cells were on disk between the two runs, so anyone who read that face in the interval read
six false verdicts. §2 and §4 above are the earlier record; this addendum supersedes them on those six
cells and on nothing else.
