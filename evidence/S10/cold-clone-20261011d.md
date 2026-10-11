# S10 - cold clone rehearsal of `2c9b89c` (2026-10-11)

Run by the delivery seat at 13:58-13:59 +0800. Method: `git clone --no-local` of the seat repository into
`D:\sendguard-work\cold-5`, then every judging leg and every generator re-run inside that clone, then each
regenerated face compared against the blob the clone checked out (`git show HEAD:<path>`), with only the
timestamp patterns normalised. Nothing in the seat tree was touched by this run, and nothing in the clone was
deleted.

One honest disclosure about the carrier: the first attempt at this runner died on its own line 75 (an
`AttributeError` unpacking a helper's return value) *after* the clone had completed and before any leg ran. The
second attempt reused `cold-5` instead of deleting it, and the capture below shows that reuse being re-verified
- HEAD equal to the seat's HEAD, status empty - before anything was measured. An aborted clone that was then
verified clean is the same starting condition as a fresh one; that is the claim, and the two lines that prove it
are in the raw block.

## Pre-conditions, from the capture

```
host| git version 2.53.0.windows.2
seat HEAD| 2c9b89c674e3332c03ef17e5fb857c161461282c
seat status rc=0 lines=1
   seat dirty| ?? impl/python/sg_restamp_note.txt
NOTE: D:\sendguard-work\cold-5 already exists - reusing it instead of deleting anything. It is re-verified below (HEAD must equal the seat's HEAD and status must be empty) or this run means nothing.
clone HEAD| 2c9b89c674e3332c03ef17e5fb857c161461282c  equals seat HEAD: True
clone status rc=0 lines=0 (a cold clone must start clean)
clone tracked paths| 1166 (git ls-files rc=0)
```

The single dirty face in the seat belongs to the Python lane and is not this seat's work; it is left alone.
`1166` is the denominator the delivery leg needs to agree with.

## Judging legs, run inside the clone

```
LEG| selftest                 rc=0  OUTCOME=PASS
LEG| lint                     rc=0  lint: OK  arms=24 passed=24  workflows=1 runner_labels_checked=7 tracked=1166,untracked=0 names_checked=1166 json_scanned=969
LEG| validate_cells           rc=0  arms=24 passed=24
LEG| spec_drift               rc=0  arms=15 passed=15
LEG| delivery_form            rc=0  arms=14 passed=14
LEG| equality                 rc=1  OUTCOME=RED verdict_disagreements=54 verdict_identical_cells=24/44 cells_fully_recorded_and_identical=4 verdict_not_recorded_pairs=121 verdict_pairs_recorded=2281/2640 probe_cells_differing=29 unpinned_input=0 cells_excluded=0 channel_abstentions=13 truncated_values=2 required_cells_missing=0
LEG| triangle                 rc=0  OUTCOME=CLEAN
```

Every number matches the seat's own run at the same commit: the arms (21 self-test arms reported through
`evidence_table`, 24 lint, 24 validate_cells, 15 spec_drift, 14 delivery_form) and the verdict, which is RED by
design - 54 disagreements, 24 of 44 cells identical, 4 fully recorded, 121 blanks. A clone that reproduced a
*quiet* verdict would be the alarming result.

## Parity of the derived faces

```
SAME| docs/GAP.md                      1354 bytes regenerated identically modulo timestamps
SAME| docs/matrix.md                   11921 bytes regenerated identically modulo timestamps
SAME| docs/expected-summary.md         14521 bytes regenerated identically modulo timestamps
SAME| docs/cell-validation.md          3882 bytes regenerated identically modulo timestamps
SAME| docs/tapi.md                     2326 bytes regenerated identically modulo timestamps
SAME| docs/acceptance-S02.md           5394 bytes regenerated identically modulo timestamps
SAME| docs/STATUS.md                   4455 bytes regenerated identically modulo timestamps
SAME| docs/coverage.md                 3846 bytes regenerated identically modulo timestamps
SAME| docs/spec-drift.md               1761 bytes regenerated identically modulo timestamps
DIFF| docs/delivery-form.md            head=32 lines disk=32 lines differing=2
   L13   HEAD | | rust | 174 | 1 / 2 (n=174) | 1 / 1 / 1733 (n=174) | 0 | - | 0 | - | - | 2 |
   L13   DISK | | rust | 174 | 1 / 2 (n=174) | 1 / 1 / 1733 (n=174) | 0 | - | 0 | - | - | 0 |
   L17   HEAD | A customer who clones this tree gets their source and a toolchain command, not an artifact; the `14` files this column ignored are build output that exists on some workin
   L17   DISK | A customer who clones this tree gets their source and a toolchain command, not an artifact; the `12` files this column ignored are build output that exists on some workin
DIFF| docs/evidence.md                 head=24 lines disk=24 lines differing=1
   L5    HEAD | - repository commit: `56d66cadd48e` (working tree carries 14 uncommitted faces at generation time). That is the HEAD this file was generated **under**, not the commit tha
   L5    DISK | - repository commit: `2c9b89c674e3` (working tree carries 11 uncommitted faces at generation time). That is the HEAD this file was generated **under**, not the commit tha
SAME| evidence/S02/equality-verdict.json 59200 bytes regenerated identically modulo timestamps
parity| faces identical=10 differing=2 of 12
```

The comparison is blob-to-disk: `git show HEAD:<path>` against the file the clone's own generator wrote. Both
sides are LF here because every generator opens with `newline="\n"`, so no `autocrlf` smudge sits between the
two faces being compared. The runner prints at most 170 characters of a differing line, which is why two of the
quoted lines stop mid-sentence - the comparison itself was over the whole bytes.

## What the second difference means, and what was done about it

The fixed leg had removed the *bytes* of untracked build output from the published table, and that part worked:
all six artifact columns read identically in the clone. What it had left in the table was the column counting
what the filter dropped, and a drop can only be counted from files that are present. The seat's disk holds rust's
two release executables and the java lane's four `.class` files; a clone of the same commit holds none of them,
so the same honest code reads `2` in the seat's rust row and `0` in the clone's, and the total sentence reads 14
against 12.

That is not drift in the repository; it is a machine fact wearing a repository column. The delivery form is the
face a buyer reads, so the disk-dependent count was taken out of it and kept in the run line, where it is still
published and still per-port - this is the seat's own run at 14:02, after the change:

```
wrote docs/delivery-form.md bytes=4734 ports=6 cells_total=569 installers_found=0 not_measured_cells=3
instrument_problems=0 untracked_ignored=14 installers_untracked=0 tracked_paths=1166
drops=csharp:0,go:0,java:4,python:1,rust:2,typescript:7
```

`docs/evidence.md` differs for a different, already-disclosed reason and is left as it is: that line names the
HEAD the file was generated *under* and the number of uncommitted faces at that instant, which in the clone is 11
because this run itself regenerated 11 tracked faces. It states its own basis, so it is a truthful difference
rather than an irreproducible claim.

## Arms added because of this run

`ci/delivery_form.py` went from no self-test at all to 15 arms, and the shape arm is the one this clone run
bought:

```
SELFTEST-FAIL: selftest A15 red: the published table must be the nine tracked columns and nothing
               disk-dependent, got column counts [10] over 7 rows
SELFTEST-FAIL: selftest A15 red: a count of ignored files needs the files to be present, so it may not be
               published in a face a clone is expected to reproduce byte for byte
arms=15 passed=13        <- against the face as it stood before this change
arms=15 passed=15        <- after regenerating the face
```

Both sides are asserted: the arm refused the ten-column face and accepted the nine-column one, so it is not a
description of the current file.

## What this run does not prove

- It does not rebuild any port harness. The six faces are read exactly as committed; compiling all six from
  source on a clean machine is a different act with its own gap, recorded in `docs/STATUS.md` and
  `docs/acceptance-S02.md`.
- It does not put a macOS or Linux row on the board. No port harness runs on those systems here, and the
  instrument job in `.github/workflows/matrix.yml` has never executed, because nothing has been pushed.
- It normalises timestamps and says so. Everything else is compared byte-wise.
- The seat's work tree still carries one face that is not this seat's (`impl/python/sg_restamp_note.txt`, the
  Python lane's own note, untracked); this run neither read nor moved it.
- The run measured `2c9b89c`, whose published face still had the drop column. This file therefore proves the
  *finding*, not the fix: the face without the column is what a later clone has to reproduce, and if that reading
  is added here it will be added below this section with its own capture, not asserted from this one.


## Third run, 14:11 +0800 — the drop numbers quoted above were themselves a defect

Sections 1 and 2 of this file are genuine captures of what the tools printed. Two of those readings were wrong
about the repository, because the classifier that produced them was wrong.

`filter_tracked` compared `git ls-files` paths (normalised to pure backslashes) against `glob` results, and
`glob` keeps whatever separator was typed inside the pattern:

```
G| 'D:\\sendguard-work\\seat-qoder\\impl/java/build\\CellProbe.class' in? False
```

So four committed `.class` files, the tracked `impl/python/sg_run.py` and seven tracked TypeScript sources were
all counted as untracked. The `java:4` and `typescript:7` in section 2's side-by-side table are that bug
reporting itself, and the sentence in section 2 that reads "the table counts tracked *build output*, and there is
none" is superseded: there are 14 tracked artifact files.

The defect was found by an independent witness added to the leg, not by re-reading the leg:
`git_artifact_paths(port)` asks git's own pathspec matcher which tracked files live under the port's prefixes,
and `self_check` refuses to publish when the two disagree. Its first message named the leg and the witness both:

```
OUTCOME=INSTRUMENT-RED the table above is not a measurement - 1 instrument problem(s), first: java: this leg's
file classifier kept 6 tracked artifact(s) and git's own pathspec names 0; the two enumerate the same commit, so
a difference is a bug in the leg (-)
```

`names 0` was the witness's own translator being wrong - it used `fnmatch` with `**` replaced by `*`, which turns
`impl/java/build/**/*.class` into a two-segment pattern and matches none of the six real files. That is why the
translator is explicit now (`pattern_to_regex`) and why arm A18 asserts both its sides: `**/` must accept the
zero-directory and the nested case, a single `*` must not cross a separator, and one port's directory must not
leak into another's pattern.

Corrected readings, same command, this time with leg and witness in agreement
(`instrument_problems=0`, `arms=18 passed=18`, generator rc=0):

```
seat  14:12  untracked_ignored=2 tracked_paths=1167 drops=csharp:0,go:0,java:0,python:0,rust:2,typescript:0
```

The artifact columns of the published table after the fix, which is what a buyer reads (the import-count and
timing columns are elided here, not in the file):

```
| java | 86 | ... | 6 | class | 6 | 86,825 | `impl/java/build-check/CellProbe.class` |
| python | 123 | ... | 1 | py | 0 | 81,900 | `impl/python/sg_run.py` |
| typescript | 87 | ... | 7 | ts | 0 | 141,416 | `impl/typescript/src/runner.ts` |
```

`csharp`, `go` and `rust` are the three ports that commit no build output. The earlier "no port's build output is
tracked" reading was this leg's third wrong answer in a day, and all three had the same shape: a count that
agreed with itself across two machines because nothing in the leg could ask a second party whether the file set
was right.

## Fourth run, 14:13 +0800 — clone of `d6994fd`, the corrected table reproduces

```
seat HEAD| d6994fd9cf8fded589fcfc080b7750e558961b01
clone HEAD| d6994fd9cf8fded589fcfc080b7750e558961b01  equals seat HEAD: True
clone status rc=0 lines=0 (a cold clone must start clean)
clone tracked paths| 1167 (git ls-files rc=0)
```

```
LEG| selftest                 rc=0  OUTCOME=PASS
LEG| lint                     rc=0  lint: OK  arms=24 passed=24  workflows=1 runner_labels_checked=7 tracked=1167,untracked=0 names_checked=1167 json_scanned=974
LEG| validate_cells           rc=0  arms=24 passed=24
LEG| spec_drift               rc=0  arms=15 passed=15
LEG| delivery_form            rc=0  arms=18 passed=18
LEG| equality                 rc=1  OUTCOME=RED verdict_disagreements=54 verdict_identical_cells=24/44 cells_fully_recorded_and_identical=4 verdict_not_recorded_pairs=121 verdict_pairs_recorded=2281/2640 probe_cells_differing=29 unpinned_input=0 cells_excluded=0 channel_abstentions=13 truncated_values=2 required_cells_missing=0
LEG| triangle                 rc=0  OUTCOME=CLEAN
LEG| gen ci/delivery_form.py  rc=0  wrote docs/delivery-form.md bytes=4798 ports=6 cells_total=569 installers_found=0 not_measured_cells=3 instrument_problems=0 untracked_ignored=0 installers_untracked=0 tracked_paths=1167 drops=csharp:0,go:0,java:0,python:0,rust:0,typescript:0
```

```
SAME| docs/delivery-form.md            4798 bytes regenerated identically modulo timestamps
DIFF| docs/evidence.md                 head=24 lines disk=24 lines differing=1
parity| faces identical=11 differing=1 of 12
```

The face reads java 6, python 1, typescript 7 in the clone exactly as in the working copy, and the disk-only
count is 0 there against 2 here - which is the point of moving it out of the face. The single remaining
difference is `docs/evidence.md`'s line that names the HEAD and the uncommitted-face count of the tree that
generated it; it states its own basis and is the exception this file has carried since the first run.

## What this file now establishes

- Every derived face reproduces from a clone of the same commit on this host, modulo timestamps, with one
  self-describing exception that names its own basis.
- The repository's tracked delivery content is measured, not asserted: 14 artifact files, 310,141 bytes,
  concentrated in java/python/typescript, three ports with none, zero installers, and `tool/check.py` at 81,759
  bytes as the one file that runs without a compiler.
- The delivery leg has 18 arms, an independent git witness for its file classification, and a floor check that
  refuses a parse it cannot trust. All four of its defects are caught by something other than the author's
  re-read of the same code.
- Still not established, unchanged: no port harness rebuilt from source, no macOS/Linux execution, CI never run
  because nothing has been pushed, and the interpreter line remains a host fact at the minute it was written.


## One-line note appended at 15:16 +0800

Two limits in this file said the instrument job "has never executed, because nothing has been pushed". They were
true at the runs they record. At 15:14 the owner ordered the push and it went through (public `main`
`7151f58` -> `28562e2`, fast-forward, 87 commits, no force, no tags), so the job has now been triggered; its
conclusion is not readable from this seat without a token, and the accurate status word is *triggered, outcome
unread here*. The full correction, with the disclosure scan that preceded the push, is in
`evidence/S11/rehearsal-20261011.md`.
