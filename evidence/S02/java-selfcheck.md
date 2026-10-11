# SENDGUARD S02 - java port self-check record (rev6)

**Current state of this lane's face (SG-F2, 2026-10-11): the counts below are the live ones, and
`ci/acceptance.py` reads them because they are the first `cells_required=` line in this file. The
sections underneath stay as the record of what was true when each was written; none of them is
retouched.**

cells_required=48 cells_produced=86 cells_valid=86 blocked=0 extra=38 controls_pass=true

44/44 required identities matched. 69 cells byte-identical to the pre-ticket face, 5 control cells
carrying only added `control_pass_*` fields, 12 new `java.io` spread cells marked `extra: true`
(`impl/java/tools/verify_sg_f2.py` prints that arithmetic off the disk). Rulers: `selfcheck.py`
rc=0, `selfcheck.py --selftest` 49 arms / 0 problems, `stamp_controls.py --selftest` 8 arms /
0 problems, `verify_sg_f2.py` rc=0.

Supersedes the rev4 text at this path (kept as `impl/java/tools/prev-rev4-record.txt`). The whole
matrix was re-emitted under rev6 in one run, so no cell on disk carries a superseded input or a
superseded field set.

- seat: `seat-qoder` (java port window)
- contract read: `docs/NOTICE-rev6.md`, `spec/cases.yaml` (`control_samples`), `spec/cell-identity.md`
  section 9, `spec/cells-required.json`, `spec/schema.json`, `spec/validate.py`, `spec/canonical.md`,
  `spec/gate.md` at HEAD `f15b399`
- run: 2026-10-11T05:37:27 host-local (UTC+08:00), harness `sg-java-S02-r4-rev6`
- report: `cells_required=44 cells_matched=48 cells_produced=74 cells_valid=74 blocked=0 extra=26
  controls_pass=true` - 44 is the manifest's `required_cells`; the 4 java rows of
  `tapi_cells_per_language` make 48 identities, all present.
- not INSTRUMENT-RED: 5/5 control expectations pass against the sealed baseline, and this window's
  validator passes its own red/green arms (35 arms, 0 problems).

## 1. Action 1 - the five control cells re-run against the pinned bytes

`spec/cases.yaml` now pins `control_samples`: each control's `sample_hex` plus one 28-byte payload
shared by all five. That pin closed a real hole, and this port contributed to it.

| cell | name this port used before rev6 | pinned sample_hex | now |
|---|---|---|---|
| T-CTRL-ASCII | `report-2026.txt` | `7265706f72742d323032362e747874` | unchanged, agreed with the pin |
| T-CTRL-ILLEGAL-CHAR | `a<b.txt` | `613c622e747874` | unchanged, agreed with the pin |
| T-CTRL-PARSE | `sg-parse<U+0000>.txt` - invented here | `6e756c00627974652e747874` | replaced by the pin |
| T-CTRL-NAMETOOLONG | 256 units of this port's PAD alphabet - invented here | 256 `a` units | replaced by the pin |
| T-CTRL-CANON | `ctrl-canon.bin` - invented here | `63616e6f6e2d636865636b2e747874` | replaced by the pin |

Two of the five already matched; **three did not** - this port had invented the sample bytes for
`T-CTRL-PARSE`, `T-CTRL-NAMETOOLONG` and `T-CTRL-CANON`, so that cell asked a different question per
port. Reported as this window's own error, not as a contract gap.

Payload: the port now writes the pinned 28 bytes
`53454e4447554152442d43414e4f4e2d5041594c4f41442d32303236` = `SENDGUARD-CANON-PAYLOAD-2026`,
sha256 `c9fe45b2fee8ea846f0cf4f2cacc2a891e7b082e7719923502d12a9813e21994` - the same digest
`evidence/S00-ctrl-baseline.md` publishes for T-CTRL-ASCII. The driver asserts that equality at
import, so payload drift stops the run instead of shipping a cell with a different digest. The rev4
record's DEFECT-6 ("the baseline gives a hash but not the bytes it hashed") is closed by this pin,
and the agreement is now checked by an arm rather than by prose.

Control results against the sealed expectation sentences (the baseline table is a node observation,
reported, never used as a mandate):

| cell | expectation quoted | java measured | verdict |
|---|---|---|---|
| T-CTRL-NAMETOOLONG | fail on all 3 OS after reaching FS (err_at_syscall, not parse) | err_at_syscall / fs | PASS |
| T-CTRL-ASCII | ok on all languages/OS | ok, 28 written, 28 on disk, read ok, roundtrip true | PASS |
| T-CTRL-ILLEGAL-CHAR | Windows illegal / POSIX creatable, paired with os_legality_verdict | refused, `os_legality_verdict=illegal` | PASS |
| T-CTRL-PARSE | all 6 langs MUST be err-at-parse | err_at_parse / parse | PASS |
| T-CTRL-CANON | identical canonical bytes, else INSTRUMENT-RED | two instruments' digests identical, and equal to the pinned payload digest | PASS |

## 2. Action 2 - blind cells

`blind/B1`..`blind/B5` emitted from `evidence/S00/blind-map.json`, each carrying `blind_id` equal to
the id number (checked by an arm). All five created, wrote 28 bytes, read back 28, verdict `legal`:
B1 `invoice_FINAL_2026.xlsx`, B2 `photo_2_.jpg`, B3 `Copy_of_report.docx`, B4 `data_v2_1_.csv`,
B5 `weekend-report.txt`. The pre-rev6 spelling `blind/BLIND-1..5` stays on disk, marked
`extra: true` with an `extra_reason`, because nothing in this port deletes and the manifest's note
says extras are kept, marked and excluded from the digest. Both spellings carry the same `blind_id`,
which is what section 9.2's fold needs to know which cell is which.

## 3. Action 3 - the length rungs, both path forms

12 required cells: `len/T17` and `len/T18` at `base_len` in {78, 120, 200} x `path_form` in {plain,
extended}, each declaring `sub_identity = {"base_len": .., "path_form": ..}` and carrying
`len_triple` plus the bisection bracket. Every rung cell runs six name-length points: the linear
model's `259 - base_len - 1` at -1/0/+1, and 254/255/256 at the component wall.

| base_len | linear model's last ok name length | measured last ok total | first refused total | last ok component |
|---|---|---|---|---|
| 78 | 180 (total 259) | 334 | 335 | 255 |
| 120 | 138 (total 259) | 376 | 377 | 255 |
| 200 | 58 (total 259) | 456 | 457 | 255 |

The three columns after the model apply to both forms: in the six extended cells the `Files.write` column is empty by measurement (`run_status` ok, every point `err_at_parse`), so their `measured_plain_wall` is null and the numbers above are the OS-leg column (`points[].extended`, `measured_extended_wall`); in the six plain cells both columns agree.

Both forms give the same wall, because the extended form is answered twice over: the pinned entry
`Files.write` **refuses the extended string at parse** (`err_at_parse`, `InvalidPathException:
Illegal character [?] in path at index 2`) so it yields no bracket of its own, while the same cell's
OS leg - `java.io` handing that string to `CreateFileW` - reaches the wall at the identical place.
Each extended cell therefore says `create_result=err_at_parse`, `longpath_mechanism=prefix_rewrite`
(the requested form *is* the prefix) and publishes the bracket through `points[].extended` /
`measured_extended_wall`; the plain cells carry `longpath_mechanism=unknown` for the reason in
section 5.

Nothing needed `run_status: blocked` - all 12 rungs were reachable, so no cell is absent and none is
blocked. The blocked path is armed and tested: an arm asserts a blocked cell must carry the command,
its exit code and one attempted fix, and that `run_status` agrees with `blocked`. It fired twice
during bring-up - once on an embedded U+0000 before the probe learned to classify a parse refusal,
once when a leaked loop variable sent `--path-form extended` to a tier cell and the probe crashed on
a null handle. Both were fixed in the instrument, not worked around in the data.

## 4. Inventory

| group | required manifest | matched here | extra (kept, marked, excluded) |
|---|---|---|---|
| trap | 22 | 22 | 3 (whole-case T09/T14/T19) |
| ctrl | 5 | 5 | 0 |
| blind | 5 | 5 | 5 (pre-rev6 `BLIND-n` spelling) |
| len | 12 | 12 | 14 (8 FROZEN tier cells + 6 rev5 rung ids without `path_form`) |
| tapi (separate list) | 4 | 4 | 4 (pre-rev3 `T-API-n` ids) |
| | **44 (+4)** | **48** | **26** |

74 cell files, 0 absent, 0 blocked, 0 non-cell files in `results/java.windows.x64/`. 191 child
processes, 5 s external limit, 0 timeouts, no `hang`, per-cell wall time 122-433 ms, 180
`entry_spread` records.

Distributions: `create_result` ok 41 / err_at_syscall 22 / err_at_parse 11; `read_result` ok 35 /
not_applicable 37 / eof 2; `os_legality_verdict` legal 47 / illegal 27; `attribution_layer` L1 58 /
L3 11 / L2 5; `path_form` plain 68 / extended 6; `verdict_via` win32 in all 74.

## 5. What the matrix says

- **A successful write that stores nothing.** `NUL.tar.gz` (T02), `COM1.log` (T11), `AUX.log`
  (T14-m2): `create_result=ok`, `bytes_written=28`, nothing at that name in the fresh directory,
  `phantom=true`, `bytes_on_disk=null`, and the observation honestly `not_applicable` with a
  `read_skipped_reason`. A sender-side checker cannot see this from the return value.
- **Doors that answer ok to nothing.** `Files.createFile` returns success for `CON.txt` and `CON`
  where `Files.write`, `Files.newOutputStream`, `Files.move`, `File.createNewFile`,
  `FileOutputStream.write` and `File.renameTo` refuse at the filesystem - five cells `L2`, because
  switching the entry removes it.
- **java refuses whole classes of name before the OS** (`a<b.txt`, U+0001, U+0000, trailing space),
  every pinned entry agreeing: those 11 cells are `L3`. A trailing **dot** is not refused - it
  reaches the OS and comes back renamed: `trail.` lands as `trail`, `name_mutated=true`, 28 bytes on
  a name nobody asked for.
- **NFC and NFD coexist** (T09-m1/m2): two separate entries, `norm_variant_hits=2` on the second
  member while `same_name_hits=1`. T07/T08/T09-m1/T09-m2 are required for every port, so they run on
  Windows and carry `spec_applicable_on_windows: false` (cases.yaml marks them `[macos, ubuntu]`).
- **The wall is the 255-unit component, in both path forms and at every rung** - never
  `259 - base_len - 1`, whose own point passes at all three bases. Under rev4/rev6 gate.md 5 the
  regime is keyed by `longpath_mechanism`: the plain cells report `unresolved` (mechanism unknown),
  the extended cells report the prefix-rewrite model with a 255 ceiling. Only the length group
  carries that field; a trap cell that never varied a length makes no regime claim.
- **Why the plain mechanism stays `unknown`, measured three ways.** Leg 1: a dot-suffixed directory
  is still reached by a 305-unit plain path (`name-parsing-still-applies-at-long-length`), so the
  string did not go out as an extended form. Leg 2: a real directory named `COM1` (created through
  `java.io` with the prefix, listed only) is traversed normally at both 31 and 266 units, so a
  device name in a middle component cannot test the prefix at all. Leg 3, the decisive one: the same
  **final** name `CON.txt` is refused at total 28 and at total 430, landing nothing either time
  (`not-rewritten`). Yet a plain path of 456 units still created a file, while `LongPathsEnabled`
  reads 0 through two independent instruments and the S00 raw-byte scan found no `longPathAware`
  token in any of the three java binaries. None of `manifest` / `prefix_rewrite` / `none` fits, and
  picking one would be the exact error rev6 exists to stop.
- **T-API publishes java disagreeing with itself**: `Files.createFile` answers `ok` for `CON.txt`
  where the other three pinned entries answer `err_at_syscall`, and on the ASCII name it writes 0
  bytes and reads back `eof`. Under rev6 that spread is the matrix, not a failure either way.
- **Zip bit-11 round-trips inside the JDK** (T16): a 170-byte archive whose entry name
  `636166c3a92de298832e747874` reopened byte-identical.

## 6. Validator state (my own script, stdlib only)

- Denominator derived from `spec/cells-required.json` **read from the committed blob face**; the
  manifest's own citation of `spec/cases.yaml` is re-verified against `git cat-file blob
  HEAD:spec/cases.yaml` before anything runs. Blob and checkout agree this round
  (`required_cells_sha256 = 3742747dd412e8a9d799e6c7f215f561f4c14774466759de515335b76ee90ff6, identical on the committed blob face and on this checkout`).
- **Pinned-input arm**: a control cell whose `name_source` is not the pinned `sample_hex`, or whose
  payload digest is not the pinned one, is VOID with `UNPINNED_INPUT` - tested both directions (the
  red arm must be caught, and the pinned value must pass).
- **Two-ruler agreement**: every closed set is compared across `canonical.md`, `schema.json` and
  `validate.py`, and the run refuses to judge cells until the three agree. They do, on 12 fields.
- **Lock faces**: all 8 rows of `spec/FROZEN.md` re-hashed against the committed blob - 8 checked,
  0 mismatches.
- Word extraction takes a table's first column only, so `read_skipped_reason` (a field rev4 mentions
  in prose) is not mistaken for a verdict; and unlike `ci/equality.py`'s extractor it reads
  `attribution_layer`'s mixed case, so that field is actually checked rather than silently skipped.
- rev4's `not_applicable` pairings are enforced both ways; `run_status` must agree with `blocked`;
  `verdict_via=none` may not sit beside a claimed verdict; a filename with two sub slots must agree
  with the cell's `sub_identity`; an unmarked extra, and a required cell marking itself extra, are
  both VOID. 35 arms, 0 problems.

## 7. Reported to the contract owner (nothing here patched by this window)

1. `spec/schema.json`'s `required` array still lists 17 fields while rev3/rev6 declare
   `verdict_via` required. This port follows the stricter reading - all 74 cells carry it.
2. The 4 java rows of `tapi_cells_per_language` still carry `sub_identity: {}` and differ only by
   `api_entry`, which section 9.2's fold does not consume. The cells are emitted exactly as the
   manifest spells them; if the digest leg must address them separately, that dimension has to be
   declared in the manifest, not invented by a port.
3. `ci/export_aggregate.py` is still cited by `spec/cell-identity.md` 3 and still does not exist, so
   no aggregate was generated or hand-written.
4. Java exposes no numeric Win32 error (`NoSuchMethodException: FileSystemException.getWinError()`),
   so `winerror` is null with that probe text and the OS's localized message is kept verbatim;
   `java.io.File` failures are bare booleans with no error at all. The console here is cp936 and the
   JVM self-reports `file.encoding=GBK`, so every cell file is written as ASCII bytes with `\uXXXX`
   escapes and the validator rejects any non-ASCII byte in a cell face.
5. `spec/cases.yaml` marks T07/T08/T09 `[macos, ubuntu]` while the required list names them for every
   port. One sentence would make "run them and record applicability as a field" the rule instead of
   this port's inference.
6. Directory-view hygiene, disclosed rather than hidden: the OS-legality leg creates, so an entry can
   be present that the pinned entry never produced. 24 cells set
   `dir_view_contains_probe_created_files` with `dir_view_note`, and the probe now also flags
   `hit_came_from_earlier_leg` where a name exists but that member's own create was refused - the
   same combination that crashed the instrument before it was guarded.

## 8. Unchanged rules, and how each was met

Primary entry `Files.write` on every non-`T-API` cell (enforced by an arm); the `java.io.File`
variants inside the same cell file as `entry_spread`, so `results/` holds only cells. One child
process per cell x entry (191), external 5 s timeout owned by the driver, `hang` never needed.
Reserved device names: created and listed only - never opened, never read, never stat'd
(`stat_status: "skipped-reserved-name (list only; no open)"`); the pinned create-and-write entries do
hand the 28 payload bytes to a device, which is what the pinned entry *is*, disclosed instead of
dodged by substituting another entry. No deletion logic anywhere (M19): every cell carries
`cleanup_failed=true`, and the honest side effect is 3711 retained fresh scratch directories plus
their child result documents under `D:\s\` (accumulated across this session's runs) and 629
directories left at `D:\j*` by runs made before that root was fixed. Fresh uuid directory per run,
verified empty before use and recounted after; `base_len` is the directory path length with no
trailing separator and `base_len_actual` is re-read inside the JVM (78/120/200 confirmed). Zero
third-party dependencies: one `.java` compiled by `javac`; driver and validator on the Python
standard library. Writes limited to `impl/java/`, `results/java.windows.x64/` and this file; nothing
under `spec/`, `ci/`, `harness/`, `docs/` was modified, and the one `ci/__pycache__` byproduct of
calling the gate's own function was removed; `D:\sendguard` was never opened; no commit, no push, no
tag. No other port's `impl/` or `results/` was read in this round, and no tool that enumerates them
was run.

## 9. Disclosure against audit check 1 (`spec/gate.md` 7)

Before any measurement this window ran one recursive text search over `spec/` for the frozen length
grid, and three lines of `spec/expectations.sealed.md` (the T17/T18 rows) appeared in that output.
The file was never opened and those lines were never used as a criterion - the rung result in section
3 contradicts the quoted `<= 259` expectation, which is the evidence that it was not fitted.

## 10. Reproduce

```
"C:\Program Files\Eclipse Adoptium\jdk-17.0.17.10-hotspot\bin\javac.exe" -nowarn ^
    -d impl\java\build impl\java\src\CellProbe.java
python impl\java\tools\run_cells.py            # rc0: 48 identities, 26 extras, 0 blocked, 0 absent
python impl\java\tools\selfcheck.py --selftest # 35 arms, 0 problems
python impl\java\tools\selfcheck.py            # rc0, controls_pass=true
```

Toolchain re-proved every run: three `java` binaries on PATH (jdk-17.0.17 first, jdk-21.0.6, then
the Oracle `javapath` shim reporting 1.8.0_31); `JAVA_HOME` points at jdk-21 and is **not** used;
compile and run both pin `...jdk-17.0.17.10-hotspot\bin`, and every cell carries
`jvm_self_report.java_home` / `java_version` so the answer names the JVM that produced it. Raw
captures beside the scripts: `run-facts.json`, `run-output.txt`, `selfcheck-output.txt`,
`selftest-output.txt`.

Close: 44 manifest cells plus this port's 4 T-API rows, all present, none blocked, 26 extras kept
and marked. Worth buying: the write that reports success and stores nothing (three names), the door
that says ok where three say no, the wall sitting at 255 units per component in both path forms and
at every rung, and the fact that no `longpath_mechanism` word in the contract describes what this
machine does to a long plain path from java.nio.

## Addendum - rev7 arrived after this text was written (run 2026-10-11T07:22:42, HEAD 559e50e)

`docs/NOTICE-rev7.md` re-sealed `spec/cases.yaml` (blob face now
`8650a1863578231ef75af28f22322ac8375aed7fdfc62a3b09f01cd496453261`) and the manifest
(`ed8a8a29c0eea9992565...`), pinning the length filler to one code unit U+0061 repeated `base_len`
times, and separating three quantities that were all called "length". It named this port: my length
cells passed a cycled `0123456789abcdef` filler and put the converged ceiling (256) into
`len_triple`. Re-emitted under the pin:

- 12 rung cells, `name_source` = hex of the exact component handed to the API (`61` x base_len: 78,
  120, 200 code units), `len_triple` = that name's three widths (all equal `base_len`, which is the
  check rev7 asks for), and the converged ceiling moved to `len_ceiling`
  (`through_the_pinned_entry` 255 in the plain form, null in the extended form where every point is
  `err_at_parse`; `through_the_os_leg` 255 in both). The 7-point bracket per cell is kept as
  evidence inside `points`, and the 8 FROZEN tier cells plus 6 rev5 rung ids stay as `extra: true`.
- Because the spec face moved, my own arm (a cell must cite the committed `spec_sha256`) would have
  voided all 62 non-length cells over a hash they could not have known. So the whole matrix was
  re-emitted in one run, and every non-length cell was then compared field-by-field against the
  pre-re-emit snapshot at `impl/java/tools/rev6-cell-face.json`: **zero differences**. Nothing but
  the length family changed.
- Gates after the re-emit: `run_cells.py` rc=0 (48 identities, 26 extras, 0 blocked, 0 absent),
  `selfcheck.py --selftest` 39 arms 0 problems (three new rev7 arms: a label instead of bytes, a
  ceiling mixed into the triple, and a missing ceiling - each must be caught, and the pinned rung
  must pass), `selfcheck.py` rc=0 with `controls_pass=true`.
- Disclosed against my own rule of naming my errors: `harness_version` still reads
  `sg-java-S02-r4-rev6` on all 74 cells after this re-emit. The field set did change (rev7 added
  `len_ceiling`, `headline_rule`, `pinned_component_units`), so the label is one revision stale; the
  deadline came before another full run, and a mislabelled provenance string is reported here rather
  than quietly corrected in some cells and not others.

---

## rev7 follow-up: why the six extended rungs say `err_at_parse` (answered 2026-10-11 10:5x host clock, no matrix re-run)

Question put to this window: `len/T17` and `len/T18` at `base_len` 78/120/200 with `path_form=extended`
all record `create_result=err_at_parse`, `error_stage=parse`, while four other ports reach the
filesystem on the same rungs. Is that Java refusing the name, or my harness refusing its own argument?

Delivered late: the deadline on this question was 08:40 and the first answer reached the dispatcher at
10:5x. The delay was this window working rev7 rule 4 (the `java.io` spread cells) instead of the
question; that work is still unfinished and none of it is in the recorded cells.

Artifacts written for this answer, all under `impl/java/`, all read-only w.r.t. the filesystem:

- `impl/java/src/ExtPathOfRepro.java` - the minimal reproduction class;
- `impl/java/tools/ext-path-of-repro.txt` - its compile and run capture (13,610 B, `javac_rc=0`,
  `run_rc=0`, the printing JDK identified inside the file);
- `impl/java/tools/ext-probe-source-compile-check.txt` - which probe source builds (3,091 B).

### 1. Which call raised, verbatim

The raising call is `java.nio.file.Paths.get(String)` - the JDK's own Windows path parser. It is
literally this window's line `target = Paths.get(requested);` at `impl/java/src/CellProbe.java:144`
(face `79b2c71`, the face that produced the recorded cells), and nothing between the cell's requested
string and that call inspects or vetoes the string.

Exception type and message as recorded in
`results/java.windows.x64/len__T17__base_len-78__extended.json` (`error_class` / `error_message`):

```
java.nio.file.InvalidPathException
Illegal character [?] in path at index 2: \\?\D:\s\9431b6\<48 hex>\a x78
reason=Illegal character [?] in path
index=2
```

Frames printed by the reproduction (same JDK, same message):

```
at java.base/sun.nio.fs.WindowsPathParser.nextSlash(WindowsPathParser.java:212)
at java.base/sun.nio.fs.WindowsPathParser.parse(WindowsPathParser.java:111)
at java.base/sun.nio.fs.WindowsPathParser.parse(WindowsPathParser.java:77)
at java.base/sun.nio.fs.WindowsPath.parse(WindowsPath.java:92)
at java.base/sun.nio.fs.WindowsFileSystem.getPath(WindowsFileSystem.java:232)
```

Every frame is in `java.base`. There is no `CellProbe` frame between the parser and the throw, so the
rejection is not this window's argument check. One command, on this host, no filesystem mutation
(`Path.of`, `Paths.get` and `new File(String)` do no I/O; the program creates, opens and lists nothing):

```
"C:/Program Files/Eclipse Adoptium/jdk-17.0.17.10-hotspot/bin/javac" -encoding US-ASCII \
    -d impl/java/build-repro impl/java/src/ExtPathOfRepro.java        # javac_rc=0
"C:/Program Files/Eclipse Adoptium/jdk-17.0.17.10-hotspot/bin/java" -cp impl/java/build-repro \
    ExtPathOfRepro                                                    # run_rc=0
```

### 2. General rejection, not the harness's path shape

`Paths.get` and `Path.of` gave the same answer for every input (`toString match=true`, or both threw).

| input passed to the same call | chars | JDK 17.0.17 | what JDK 21.0.6 does with the same string |
|---|---|---|---|
| `D:\Qoder` | 8 | OK | OK |
| the plain rung string, `base_len=78` | 141 | OK | OK |
| the plain rung string, `base_len=200` (total 263 > 259) | 263 | OK | OK |
| `\\?\D:\Qoder` | 12 | **InvalidPathException, index 2** | OK, prefix stripped -> `D:\Qoder` |
| `\\?\C:\` | 7 | **index 2** | OK -> `C:\` |
| the extended rung string, `base_len=78` | 145 | **index 2** | OK, prefix stripped |
| the extended rung string, `base_len=200` | 267 | **index 2** | OK, prefix stripped |
| `\\?\UNC\server\share\x.txt` | 26 | **index 2** | OK -> `\\server\share\x.txt` |
| `//?/D:/Qoder` | 12 | index 2 | index 2 |
| `\?\D:\Qoder` | 11 | `Illegal char <?> at index 1` | same |
| `\\.\PhysicalDrive0` | 18 | OK | OK |

So on 17.0.17 the answer is unconditional: every string whose third character is `?` in the server
position is refused at index 2, whether it is 7 characters or 267, whether it is a drive root, an
ordinary directory or this harness's rung. Length is irrelevant - the plain 263-character path parses
fine. The parser reads `\\?\` as a UNC path and then finds `?` illegal as a server name; `\\.\` (a
legal server name) passes, which is the shape of the same rule.

New fact this reproduction produced, not previously recorded anywhere in this port: **on the other JDK
installed on this host (Temurin 21.0.6, `java.class.version=65.0`) `Paths.get` ACCEPTS the `\\?\`
prefix and returns the path with the prefix removed.** The recorded cells ran on 17.0.17 - the first
`java` on PATH, which is the toolchain `run-facts.json` names - so their readings describe 17.0.17,
and on that JDK the refusal is real. The same question asked of the same machine one JDK version later
has a different answer, which belongs to the matrix as a JDK-version fact, not as a port defect.
The Oracle launcher on PATH (`C:\ProgramData\Oracle\Java\javapath\java.exe`, 1.8.0_31) was not asked:
the reproduction class calls `Path.of`, a JDK 11 API, so running it on 1.8 would measure the launcher,
not the parser.

`new File(String)` accepted all eleven strings, including every `\\?\` form, which is why this port's
second leg could ask the OS at all.

### 3. Which label this is, and what I am not changing

**(a) an API-policy finding, and the recorded verdicts stay exactly as they are.** Neither word in
`create_result` nor `error_stage` nor `os_legality_verdict` moves. The reasoning: the throw comes from
`java.base`, it is unconditional on the prefix, and the extended rung's question is precisely "does
this language express the Win32 extended form". `java.nio` on 17.0.17 answers no. The ports said to reach the filesystem on these rungs - csharp, go,
python, rust - are named from the dispatcher's message; this window has not read another port's cells
or source, and does not claim to know how they pass the string. The difference as stated is the
finding; the mechanism on their side is theirs to record.

The note the `(b)` reading would have required is already in the cells, so nothing needs adding for
that half either: `error_stage=parse` is the word that says the OS was not asked *by that call*, and
the cell separately records the OS's answer through a named second instrument -

- `os_legality_probe.instrument` = `java.io.FileOutputStream(java.io.File(String)) with \\?\ prefix`
- `os_legality_probe.create_result` = `ok`, `landed_by_enumeration` = `true`
- `os_legality_verdict` = `legal`, `os_legality_basis` = "the OS created and enumerated the name once
  the language path parser was bypassed"
- `verdict_via` = `win32`, with `verdict_via_evidence` naming the bypass
- `extended_leg_note` = "the second leg is java.io with the extended-prefix string (java.nio throws
  InvalidPathException on that string); it isolates the component wall from the path wall"

So the cell does not claim Windows refused the name. It claims `java.nio` refused the string, and that
the OS accepted the name - both measured, both attributable to a named call.

### 4. Two defects this reproduction exposed, reported and not patched

1. **HEAD does not build.** `git show HEAD:impl/java/src/CellProbe.java` (commit `e7a4d7f`, stamped
   2026-10-11 09:17:41) calls `createViaString` at its line 183 and `readViaIoString` at line 283, and
   that blob contains no definition of either (definition count in the blob: `createViaString` 0, in
   the worktree 1). Compiling that blob with the port's own JDK: `javac_rc=1`, 2 errors, both
   `cannot find symbol`, captured in `impl/java/tools/ext-probe-source-compile-check.txt` step A. The
   09:17 land swept this window's in-flight rev7-rule-4 edit at the moment the call sites existed and
   the methods did not; the worktree now has the definitions and compiles (`javac_rc=0`, step C). A
   cold checkout of HEAD cannot rebuild the java port until either my remaining 54 uncommitted lines
   land or the file is reverted to `79b2c71`. I have not committed or reverted anything - both are
   your call.
2. **Six cells' attribution basis overclaims.** Each of the six extended rungs records
   `attribution_layer=L3` with the sentence "java.nio rejected the path string before any syscall and
   every entry of this port agrees" while its `entry_spread` array holds **0** entries: only
   `Files.write` was run as an entry on those rows, and the one other instrument the cell did ask
   (`java.io`) answered `ok` - i.e. the data inside the cell contradicts the precondition of the word
   it uses. Under the locked tree's R1 ("switching a stdlib entry of the same language removes the
   divergence -> L2") these six are L2 evidence. This is a driver defect, not a reinterpretation: the
   tuple set in `impl/java/tools/run_cells.py:attribute()` never sees the second leg. I am not editing
   the cells and I am not re-running the matrix on my own initiative, because the attribution tree is
   frozen and re-labelling is your word, not mine. Say the word and the fix is one tuple plus a
   re-emit of the six.

## SG-F2 (dispatched 13:0x): the twelve `java.io` legs and the five stamped controls

Written 2026-10-11 13:30:00 +0800 host clock, before the 15:30 +0800 deadline. HEAD at the time of the run: `6f6757f`.

### Part 1 - the twelve java.io legs, published as extra cells

One fresh child per rung (`13` children in this run, 12 cell files, blocked=0, timeouts none, 5 s external limit unchanged). The entry is `FileOutputStream.write` called with the requested **String**, which is the instrument `impl/java/tools/ext-path-of-repro.txt` showed accepting `\\?\` while `Paths.get` throws; the dimension that separates these cells from the required ones is `builder`, which `spec/cell-identity.md` section 1 already declares, and `impl/java/tools/selfcheck.py` now refuses any cell where the filename slot, `sub_identity.builder` and `api_entry` disagree.

| case | base_len | path_form | this cell (java.io) | read back | bytes on disk | component ceiling | attribution | paired required cell (Files.write) answered |
|---|---|---|---|---|---|---|---|---|
| `T17` | 120 | extended | `ok` | `ok` | 28/28 | 255 | L2 | `err_at_parse / parse` |
| `T17` | 120 | plain | `ok` | `ok` | 28/28 | 255 | L1 | `ok / null` |
| `T17` | 200 | extended | `ok` | `ok` | 28/28 | 255 | L2 | `err_at_parse / parse` |
| `T17` | 200 | plain | `ok` | `ok` | 28/28 | 255 | L1 | `ok / null` |
| `T17` | 78 | extended | `ok` | `ok` | 28/28 | 255 | L2 | `err_at_parse / parse` |
| `T17` | 78 | plain | `ok` | `ok` | 28/28 | 255 | L1 | `ok / null` |
| `T18` | 120 | extended | `ok` | `ok` | 28/28 | 255 | L2 | `err_at_parse / parse` |
| `T18` | 120 | plain | `ok` | `ok` | 28/28 | 255 | L1 | `ok / null` |
| `T18` | 200 | extended | `ok` | `ok` | 28/28 | 255 | L2 | `err_at_parse / parse` |
| `T18` | 200 | plain | `ok` | `ok` | 28/28 | 255 | L1 | `ok / null` |
| `T18` | 78 | extended | `ok` | `ok` | 28/28 | 255 | L2 | `err_at_parse / parse` |
| `T18` | 78 | plain | `ok` | `ok` | 28/28 | 255 | L1 | `ok / null` |

Every one of the twelve carries `name_source` = the pinned filler repeated `base_len` times (unit_hex `61`, nothing appended), `len_triple` = the three widths of *that name* (all equal to `base_len`; the set on disk is [78, 120, 200]), the converged ceiling in `len_ceiling` alone, `jvm_self_report.java_version` = `17.0.17` and `toolchain.java` = `C:\Program Files\Eclipse Adoptium\jdk-17.0.17.10-hotspot\bin\java.exe`, and `extra: true` with the reason naming the paired cell.

The reading, in one sentence: through `java.io` **every** pinned rung creates and reads back its 28 bytes in **both** path forms, and the wall is the same 255-unit component in both columns - so the extended-form refusal belongs to `java.nio`'s path parser, not to Windows, and this port now says so with two cells per rung instead of one cell and a footnote.

### Part 2 - five of five controls stamped, from the readings already on the disk

`impl/java/tools/stamp_controls.py` reads each control cell, applies the criterion table quoted from `evidence/S00-ctrl-baseline.md` **through `impl/java/tools/selfcheck.py`** (no second copy of the criteria), and writes `control_pass` plus `control_pass_rule`, `control_pass_observed`, `control_pass_command`, `control_pass_tool`, `control_pass_basis`, `control_pass_stamped_at` and where relevant `control_pass_partial`. No child process was started for the stamps and no measurement was re-taken; the tool refuses (exit 3) rather than stamping when the cell cites a spec face that is not the committed one, when the face is not the driver's own serialisation, when `name_source` is not the rev6 pinned sample, when the cell is not a control cell, and when a recorded field would move.

| control | criterion (quoted) | observed in the cell | stamped |
|---|---|---|---|
| `T-CTRL-ASCII` | ok on all languages/OS | `create_result='ok'` | `control_pass=True` |
| `T-CTRL-PARSE` | may reject before syscall, but all 6 langs MUST be err-at-parse | `create_result='err_at_parse' error_stage='parse'` | `control_pass=True` |
| `T-CTRL-ILLEGAL-CHAR` | Windows illegal (winerror=123) / POSIX creatable, paired with os_legality_verd | `create_result='err_at_parse' os_legality_verdict='illegal'` | `control_pass=True` |
| `T-CTRL-NAMETOOLONG` | fail on all 3 OS after reaching FS (err_at_syscall, not parse) | `create_result='err_at_syscall' error_stage='fs'` | `control_pass=True` |
| `T-CTRL-CANON` | identical canonical bytes; else INSTRUMENT-RED | `sha256_primary=c9fe45b2fee8... second_instrument=c9fe45b2fee8... payload=c9fe45b2fee8... instrum` | `control_pass=True` |

Two things about those stamps that are not flattering and are therefore in the record:

- `T-CTRL-CANON`'s criterion in the self-check table reads `control_pass`, the field being stamped - circular. The stamper re-derives it instead from the three sha strings the cell recorded: primary, second instrument and payload are all `c9fe45b2fee8ea846f0cf4f2cacc2a891e7b082e7719923502d12a9813e21994`, identical to each other and to the sealed S00 baseline, and a fixture with one of those shas changed is refused (selftest red side).
- `T-CTRL-ILLEGAL-CHAR`'s expectation names `winerror=123`, which this port cannot surface at all (`impl/java/src/CellProbe.java:711` `winErrorOf()` measures the absence: `NoSuchMethodException: FileSystemException.getWinError()`). The stamp is true for the halves the criterion tests, and `control_pass_partial` says which half is unobservable instead of counting it. The same caveat is recorded for `T-CTRL-PARSE` (its cross-port half is the gate's comparison, not this window's claim) and `T-CTRL-NAMETOOLONG` (`error_stage=fs` where the S00 table layer said `syscall`).

### The five criteria, as commands, with the reading each produced

Taken from the transcript `impl/java/tools/sg-f2-criteria.txt` (one command per block, rc printed immediately after it); the numbers below are read out of that file, not retyped:

1. `python ci/validate_cells.py` -> wrote docs/cell-validation.md bytes=2647 invalid=0 missing_faces=0 verdict_fields_not_required=9 verdict_fields_undocumented=4 cells_omitting_a_compared_field=371
2. `python ci/acceptance.py` -> the java row on the generated face: `| java | 86 | 44/44 | 0 | 0 | 38 | 4/4 | pass (5/5 stamped) | 0 | 74 | OK | `cells_required=44 cells_matched=48 cells_produced=74 cells_valid=74 bl` (evidence/S02/java-selfcheck.md) |`
3. `python ci/equality.py` -> rc=1, `OUTCOME=RED verdict_disagreements=54 verdict_identical_cells=24/44 cells_fully_recorded_and_identical=4 verdict_not_recorded_pairs=121 verdict_pairs_recorded=2281/2640 probe_cells_differing=29 unpinned_input=0 cells_excluded=0 channel_abstentions=13 truncated_values=2 required_cells_missing=0`
3b. its comparison line: `cells_compared=44 fields=10 fact_cells=430 agree=255 disagree=54 not_recorded=121 truncated_value=2 channel_abstentions=13 name_cross_form_agreements=12`
4. `python ci/length_report.py` -> wrote docs/length-family.md bytes=7455 rows=84, and the java rows of the split still read: `| T17 | 78 | extended | java | err_at_parse | bytes(78 units) | 78/78/78 |` (extended still `err_at_parse`, plain still `ok`, triples unchanged)
5. `git status --porcelain -uall -- results/java.windows.x64` -> **17 lines** at the moment this section is generated (5 modified control cells + 12 uncommitted spread cells), git rc=0. The criterion asks for 0 *after this lane's commit*, so this line is the before-reading; the after-reading is printed by the same command in the reply, and `verify_sg_f2.py` flips to `mode=post-commit` at the same moment, which is the check that the commit carried exactly these 17 files and nothing else.

This window's own gates after the change: `selfcheck.py` rc=0, `selfcheck.py --selftest` rc=0 (49 arms, 0 problems - 39 before SG-F2, ten of them about the spread cells and the entry-substitution rule), `stamp_controls.py --selftest` rc=1 (8 arms, 0 problems), `verify_sg_f2.py` rc=0, and that verifier's own arithmetic line, printed from its stdout rather than retyped here:

    NOTE cells_on_disk=86 spread_cells=12
    NOTE mode=pre-commit spread_committed=0/12
    NOTE cells=86 identical_to_HEAD=69 stamped_ctrl=5 spread_new=12 rewritten=[] uncommitted_extra=0 moved=0
    NOTE arms=4 red_caught=3 (one arm is the green side, which must stay clean)

### Four things this window is not going to smooth over

1. **`harness_version` is now split across the face.** The 74 cells from the 07:22 full run read `sg-java-S02-r4-rev6`; the 12 new cells read `sg-java-S02-r5-SG-F2`. That is the cost of an append-only ticket: a re-run would have re-measured the 44 compared records, which SG-F2 forbids. The split is in every cell's own field, and `spread_pair.paired_cell_harness_version` names the older value on the twin, so a reader cannot mistake the two for one run.
2. **The six required extended rungs still read `attribution_layer=L3`** with the sentence "java.nio rejected the path string before any syscall and every entry of this port agrees", while the twin this ticket ordered for the same rung answered `ok` - the disagreement is now *published as a cell*, so the overclaim in that basis sentence is contradicted by its own pair on the same disk. `run_cells.py:attribute()` never saw the second leg, and the new cells go through `paired_rung_claim()` which names both files. Re-labelling the six needs your word, because the attribution tree is frozen and the ticket says not to re-answer them; the six are untouched.
3. **The three `docs/` faces moved, and it was the gate tools that moved them.** `ci/validate_cells.py`, `ci/acceptance.py` and `ci/length_report.py` each write their own repository face (`docs/cell-validation.md`, `docs/acceptance-S02.md`, `docs/length-family.md`). This window edited no file under `docs/`, `spec/`, `ci/` or `harness/`; it ran the commands the criteria name, and those commands write.
4. **The scratch pile is the price of M19, and the counter is shared.** The io run's facts record `scratch_parent=D:\s`, `scratch_dirs_retained=4122`, `child_result_files_retained=4117`. Those two counts are every entry of the parent directory, which all six ports scratch into - this window cannot attribute them to itself and does not claim it can (reading another port's faces is out of bounds). What IS this lane's own doing: 13 children in this run, each with a fresh uuid directory, and none of them deleted, because there is no deletion logic anywhere here. The disk cost of the rule is being paid and nobody has named who cleans it up at the end.

### Files this ticket added to the java lane

- `impl/java/tools/stamp_controls.py` (16774 B, sha256 cb63478fa163)
- `impl/java/tools/verify_sg_f2.py` (10047 B, sha256 0a176ab9d2ec)
- `impl/java/tools/gen_sg_f2_appendix.py` (14487 B, sha256 89367331b1fa)
- `impl/java/tools/sg-f2-criteria.txt` (3434 B, sha256 89862acb3826)
- `impl/java/tools/run-facts-io-spread.json` (12497 B, sha256 16ad239c1e44)
- `impl/java/tools/run-output-io-spread.txt` (2676 B, sha256 e2fd8b5f1bfd)
- `impl/java/tools/run-output-io-spread-2.txt` (2676 B, sha256 e2fd8b5f1bfd)
- `impl/java/tools/selfcheck-output.txt` (7497 B, sha256 dd5fd808204a)
- `impl/java/tools/selftest-output.txt` (337 B, sha256 63bfe84a283d)
- `impl/java/tools/verify-sg-f2-output.txt` (252 B, sha256 44d38ff3e930)

Sizes and digests are of those files as they stand at the moment this section is generated; `impl/java/tools/record-appendix-sg-f2.txt` is deliberately not listed, because this section is being written into it and its digest would be a self-reference.


### SG-F2 addendum - the stamper's own arms went false, and one number above is now stale

The section above prints `stamp_controls.py --selftest` as **8 arms / 0 problems**. That was the true
reading of a real run when it was captured. It then went false on its own ticket, for a reason worth
recording: two of those eight arms built their fixtures out of the live control cells, and part 2 of
this ticket **stamps those cells**. Once a live cell carried `control_pass`, tampering with the
fixture's data made the tool answer `STAMP_CONTRADICTS_RECORDING` or `FIELD_MOVED` (exit 3) where the
arm expected `rc=1` - the tool behaving correctly and the arm measuring the wrong thing. Fixed in the
tool, not in the number:

- `red-canon-sha-mismatch-pre-stamp` and `red-failing-criterion-pre-stamp` rebuild the pre-ticket
  state first, by dropping the whole `control_pass*` family, so what they test is "a failing criterion
  cannot buy a true stamp";
- two arms were added for the state the ticket created: `red-stamped-cell-whose-data-moved` (a
  already-stamped cell whose underlying shas are changed must be refused, never silently rewritten)
  and `red-stamp-contradicts-recording`;
- `green-stamp-unstamped` keeps the pass path tested now that no live cell on the face is unstamped.

Reading after that fix, in the same capture as this addendum:
`python impl/java/tools/stamp_controls.py --selftest` -> `arms_checked=10 problems=0`, rc=0.
`python impl/java/tools/selfcheck.py --selftest` -> `arms_checked=49 problems=0`, rc=0.
`python impl/java/tools/verify_sg_f2.py` -> `mode=post-commit spread_committed=12/12
cells=86 identical_to_HEAD=86 stamped_ctrl=0 rewritten=[] moved=0`, rc=0 - which is the commit-level
proof that `b56e9c4` carried exactly this lane: after the commit every cell on the disk equals its
own committed face.

The generator was changed for the same reason: it now reads its own arm counts and rc's out of the
runs it starts (`arms_checked=(/d+)` parsed from the child's stdout) instead of carrying them as
prose, so a stale count cannot be landed by that tool a second time.

Why this is appended rather than edited in place: the paragraph above was a true reading at its own
clock, and the rule this project runs on is that a record is repaired by adding the later reading,
not by rewriting the earlier one so it matches the clock.
