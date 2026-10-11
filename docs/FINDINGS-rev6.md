# Findings from the six-port run (contract rev6), grouped by mechanism

Every number in M1-M6 is a reading of `python ci/equality.py` on the canonical faces
`results/<port>.windows.x64/` at HEAD `f15b399`, host clock 2026-10-11 05:08 +0800. Six ports
(TypeScript/Node, Python, Go, Java, C#, Rust), one frozen spec, one Windows 10 build 19041 x64 host,
`LongPathsEnabled=0`, console code page 936.

**Superseded in its counts by `docs/STATUS.md` at 10:20 host clock.** The comparison rules improved
three times after this file was written: 17 compared cells became 44, 12 clean became 24, 19 conflicting
facts became 54 - and the conflict count moving twice was each time a *stricter* instrument, not a softer
one. Sections M1-M3 still describe measured data; M5 has a continuation in M6, and M6 is the section to
read if you want to know what independent verification actually costs. **M7 corrects a sentence in this
project's own whitepaper** — a finding that was filed under "Java says no" turned out to be a fact about a
specific JVM build. **M8 corrects a claim about the contract itself**: the fields the gate scores as verdicts
are largely not the fields the frozen schema requires, so "every cell conforms" and "many answers are missing"
are both true at once.

Original reading at the time of writing: 44 required cells, 29 answered by every port. Of those 29, 12 are set aside because the
ports did not ask the same question (5 with different input bytes, 7 with a different `verdict_via` or
`path_form`), leaving **17 cells compared: 12 with no verdict disagreement, and 5 cells that carry 19
conflicting verdict facts between them**. 51 required cells have not been run by at least one port.
Nothing here is a completion claim; the gaps are listed by name in `docs/GAP.md`.

## M1 — one name, five different answers: `trail.` and `trail␣` (13 of the 19 conflicts)

The two names are `trail.` (T04) and `trailsp␣` (T05, a trailing space). The frozen sample is pinned by
`spec/cases.yaml`; the answers are not:

| what a port said | TypeScript | Python | Go | Java | C# | Rust |
|---|---|---|---|---|---|---|
| is the name legal on this OS | legal | legal | **illegal** | legal | legal | **illegal** |
| did the name arrive changed | **no** | yes | yes | (not recorded) | yes | yes |
| what the directory enumerates | `trail.` | `trail` | `trail` | `trail` | `trail` | `trail` |
| bytes on disk | 28 | 28 | 28 | (not recorded) | 28 | **0** |
| does the enumerated name stat back | yes | yes | **no** | (not recorded) | yes | (not recorded) |
| length triple | 6/6/6 | **6 and 5** | 6/6/6 | 6/6/6 | (not recorded) | 6/6/6 |

"(not recorded)" is printed as the gate prints it: a port that did not record that fact on that cell. It
is a completeness finding against that port, and the gate refuses to read it as agreement.

Reproduce one row at a time:

```
python ci/equality.py | grep "trap/T04 "
python -c "import os,glob; os.chdir(tempfile:=__import__('tempfile').mkdtemp()); open('trail.','wb').write(b'x'*28); print(os.listdir('.'), [os.path.getsize(n) for n in os.listdir('.')])"
```

What this shows, and what it does not:

- The strip set is a property of the API the port called, not of Windows. Two ports refuse the name at
  their legality layer while four create it; one port sees the name on disk unchanged; two report both
  the requested and the landed length. A checker written in any single one of these six would answer
  the customer's question "can I name a file this?" differently from the other five on the same machine
  in the same directory.
- It does **not** show which port is right. The spec asks for the OS answer; four of the six got it from
  the directory enumeration authority (the name the parent lists), which is the authority `spec/gate.md`
  pins, and two refused before reaching it. Whether the refusal is a language-side parse or an OS-layer
  answer is exactly the open question the two ports were asked to state in their self-check.
- `bytes_on_disk=0` from one port against `28` from three is the single most consequential row here: a
  pre-flight checker that reports zero bytes for a file it just created is either reading a different
  entry or reading before the flush. It is published as a conflict, not resolved, because both readings
  are self-consistent inside their own harness.

## M2 — `a<b.txt`: the legality question depends on which prefix you asked with (2 conflicts)

Five ports return `illegal` for T03 (`a<b.txt`) and one returns `legal`; the same split repeats on the
`T-CTRL-ILLEGAL-CHAR` control cell. The extended path form (`\\?\`) makes `<` a legal character, and the
port that probed legality through that form answered correctly for the form it used. That port was asked
to record which form it used in its own cell, and the gate now routes a cell whose `path_form` or
`verdict_via` differ into a named `incomparable` list instead of scoring it. The control cell also
produced `mechanism_class=unknown` from one port where five produced `illegal_char_filter`: a port that
declines to classify is published as declining, not as agreeing.

Reproduce:
```
python ci/equality.py | grep -E "T03|ILLEGAL-CHAR"
```

## M3 — the zip cell measured three different archives (2 conflicts)

T16 packs a file with the port's own zip writer and reads the entry name back. `bytes_written` came
back 28 from three ports, 296 from one, 292 from another. Same input name, same pinned payload, three
archive sizes: the writers differ in what they store (the UTF-8 flag, and whether the name is stored at
all or via an extra field), so the byte counts differ before any reader is involved.

Reproduce:
```
python ci/equality.py | grep "trap/T16"
```
This row is not a defect in the ports and not a defect in the spec. It is the reason the project's own
subject - a zip that arrives garbled on another machine - exists at all.

## M4 — what did not disagree, and why that matters more than the four mechanisms

Twelve of the seventeen compared cells produced no verdict disagreement at all:

`ctrl/T-CTRL-ASCII`, `trap/T06` (emoji), `trap/T07` (NFD), `trap/T08` (NFC), `trap/T09-m1`, `trap/T09-m2`
(the NFC/NFD coexistence pair), `trap/T12` (bidi U+202E), `trap/T13` (zero-width U+200B), `trap/T15`
(control character), `trap/T19-m1` (fullwidth), `trap/T19-m2` (Hangul jamo), `trap/T20` (`--force.txt`).

Six independent implementations of one spec, six different standard libraries, one byte-identical answer
on every Unicode-normalisation cell - the pair that produces the "Mac zip arrives garbled on Windows"
complaint is in that set twice. The cells that do *not* agree are the ones where the answer comes from an
API policy (trailing characters, illegal-character filtering) rather than from the file system's
normalisation rules. That split was not predicted in the spec; it fell out of the comparison.

Seven of the 29 shared cells are in neither the clean nor the conflicting set - they are
`incomparable`: `trap/T01` (`CON.txt`), `trap/T02` (`NUL.tar.gz`), `trap/T10` (`CON`), `trap/T11`
(`COM1.log`) and `trap/T14-m1..m3` (`PRN`, `AUX.log`, `LPT9`). One port answered those with
`verdict_via: none` - it has no OS-level legality channel on this host - while the other five answered
through Win32. Counting them as agreement or as disagreement would both be false, so they are published
as not comparable with the reason attached. A further five cells are `unpinned_input` (three control
cells whose samples the ports invented, and two length rungs whose filler bytes differ); those are the
cells the rev6 `control_samples` pin exists to fix on the next run.

The three-way cross-check (`ci/triangle.py`) reads the sealed expectation table, the six ports, and the
machine's own tools against each other: **66 expectation rows, six live ports,
`collective_misreadings=0`, `OUTCOME=CLEAN`** - there is no cell where all six ports agreed with each
other and disagreed with the expectation written before any port ran. That is the check that a shared
misreading would have to pass, and it passed on every row measured so far.

Reproduce:
```
python ci/triangle.py | tail -3
```

## M5 — process findings, kept because they are the reusable part

- The gate found four ports recording one fact in four shapes (hex vs text for a name; dict vs
  `15/15/15` vs `[15,15,15]` vs omitted for a length triple) and reported it as 29/29 disagreement.
  Fixing the comparison, not the ports, is what turned the number into 19.
- Six ports invented six identifiers for the same question (`B1` / `BLIND-1` / `T-BLIND-1`,
  `T09a` / `T09-m1`, `T17-GRID-B120-L137`). Completed work was reading as missing work until the
  spelling rules were written down and tested on both sides.
- The five control cells had names but no pinned bytes, so the calibration cells asked six different
  questions - including two different payloads hashed under one cell id. They are pinned in
  `spec/cases.yaml` now (`control_samples`).
- A required-cell manifest that carries the spec fingerprint went stale the moment the spec gained those
  samples. The generator's determinism arm caught it (`only in committed: []`, `only in regenerated: []`,
  same length, different bytes) rather than letting a fingerprint that no longer matches its source sit
  in a frozen contract.
- Two ports had no type-checker or no OS-legality channel available on this host; those absences are
  published as their own rows instead of being smoothed into agreement.

No absolute claim appears in this file without a command above it. Unmeasured cells are in
`docs/GAP.md` by name.

## M6 — three more instrument defects, found after M5 and by the same method

1. **A run of the letter `a` is valid hex.** The rev6 representation-fold decoded anything hex-shaped, so the
   two ports that wrote the length component as text were read as three bytes of `0xAA` - not valid UTF-8 -
   and one name became a disagreement against four ports that wrote it as hex. Names are now compared as the
   *set of meanings* a value could have (literal UTF-8 hex, hex decoded as UTF-8, as UTF-16LE, raw bytes),
   and the gate prints `NAME-CROSS-FORM-AGREE` when that intersection is what rescued a cell, so the rescue
   is visible rather than a silent widening of the rule. Same data: 66 conflicting facts became 54, cells
   with no conflict went 18 -> 24. Two arms hold both edges - `same-name-two-encodings-agree`, and
   `different-names-still-red` (`aaaaab` is also valid hex characters, so a matcher one notch more generous
   would have called a different name the same one).
2. **The self-test wrote into the evidence face.** The gate emits a machine-readable verdict artifact; the
   path was hardcoded in `evidence/S02/`, so every fixture arm overwrote the real verdict with a two-port
   toy result - *while the self-test stayed green*, and `docs/matrix.md` read the toy as the project's
   answer. Fixed by making the path an argument, sending each arm's verdict into its own scratch directory,
   recording the source face inside the artifact, and refusing to publish a matrix built from a verdict that
   did not come from this repository's `results/`.
3. **A crash was wearing the mask of a measurement.** `os.path.relpath` raises when a scratch root sits on
   another mount; the gate died with rc=1, and rc=1 is this gate's code for "the ports disagree". The same
   18 arms passed on `D:` and reported 8 false failures on `C:` until the path handling was made total. The
   self-test is now run against two scratch roots whenever anything about paths changes.

Process note, kept deliberately: all three were found by re-reading the gate's own output after changing it,
not by a port complaining. The rule this project keeps having to earn is that a change to a measuring
instrument is not finished until the instrument has been shown to say yes, to say no, and to survive being
run somewhere it has never been run before.

## M7 — one port, two answers: the `\\?\` refusal is a property of the JVM, not of "Java"

The length family reported exactly one port refusing the extended prefix while three others round-tripped it
(`docs/length-family.md`, and the row in `docs/whitepaper.md` §3). That row read "one port rejects this prefix
at its parse layer". The sentence was about a language, and it should have been about an executable. `impl/java/src/ExtPathOfRepro.java` compiles once; `impl/java/tools/ext-path-of-repro.txt` is the
capture of the same class file run against the launchers actually installed on this host (both runs stamped
`run_rc=0`, 11 TAGs each, `javac_rc=0` with empty stderr):

| launcher | `TAG 3`, input `\\?\D:\Qoder` (12 code units) | `new File(String)` in the same run |
|---|---|---|
| Temurin `17.0.17` — the exe the recorded cells ran on | `Paths.get` THREW `java.nio.file.InvalidPathException`, message `Illegal character [?] in path at index 2`, at `sun.nio.fs.WindowsPathParser.nextSlash(WindowsPathParser.java:212)`; `Path.of` same throw | `OK`, `getPath` preserved verbatim, `isAbsolute=true` |
| Temurin `21.0.6` | `Paths.get` **OK** — `toString()` is `D:\Qoder`: this parser accepts the prefix and drops it | `OK` |
| `1.8.0_31` on `PATH` | **not run**, deliberately — the class calls `Path.of`, a JDK 11 API, so a 1.8 run returns `UnsupportedClassVersionError`. That is a fact about a launcher, not a measurement, and the file says so | — |

Three consequences, and they are the reason this is a finding rather than a footnote:

1. **The recorded cell is more honest than the sentence written about it.** The face reads `error_stage: parse`,
   `roundtrip_ok: false`, `api_entry: Files.write`, `jvm_self_report.java_version: 17.0.17`, a `toolchain` block
   pinning both `javac.exe` and `java.exe` to that JDK, and an `extended_leg_note` that already says the second
   leg is `java.io` because "java.nio throws InvalidPathException on that string". The face is faithful to the
   run, in two APIs and with its own binary named. What was wrong is any summary that files it under
   "Java says no" — inside one port `java.io` and `java.nio.file` disagree (row 1 of the table above), and now
   the same two APIs disagree with themselves across versions of the same vendor's JDK.
2. **The criterion needs the runtime identity; three ports record it, three do not, and no two record it the
   same way.** Measured over the canonical faces in the same batch as this section (`faces` = JSON files read,
   all parsable): `java` 74/74 carry a `toolchain` dict *and* a `jvm_self_report` dict, `rust` 174/174 carry a
   `toolchain` string (`rustc 1.98.0 … host=x86_64-pc-windows-msvc LLVM=22.1.8; PATH rustc is the rustup shim
   …`), `python` 123/125 carry `interpreter_resolved` (a path), and `typescript` 0/87, `go` 0/203, `csharp`
   0/50 carry no equivalent field at all. So "which executable answered" is a quantity this contract records in
   three names and three shapes in half the ports and not at all in the other half — which means the gate
   cannot compare runtimes across ports even though M7 shows a verdict field flipping between two runtimes of
   one port. Naming that field is a contract change, and the current sealed round is the eighth, so it is not
   this seat's to make unilaterally;
   until then every document that says "port X answered" must keep saying *with which executable*, which is
   what the row in `docs/whitepaper.md` §3 now does.
3. **A third instrument is worth excluding in writing.** The 1.8 row is included even though it produced no
   measurement, because "we did not run it, here is why" is the difference between a controlled comparison and
   a lucky one. The same discipline is what caught M3's zip cell measuring three different archives.

Clock honesty: the question was put to the java lane at 08:40 host clock and the capture is stamped
10:53:14 +0800, so this finding landed 2h13m late; the delay is recorded here rather than in the numbers, and
it does not change any verdict field — the gate's counts (`docs/STATUS.md`) are unaffected because the repro
lives in `impl/java/`, not in `results/`. The same note in `evidence/S02/java-selfcheck.md:286-288` states what
the delay was spent on and says plainly that it is **not** finished: the rev7 rule-4 `java.io` spread cells are
still open and "none of it is in the recorded cells". `docs/GAP.md` cannot carry that row - it is generated
from cell coverage, and Java is 44/44 there - so the unfinished work is listed in `docs/whitepaper.md` §6's
未做 list instead of being closed here.

**Landed 13:34** (`b56e9c4`): the lane recorded twelve `java.io` cells - `FileOutputStream.write` at every pinned
rung, plain and extended - and all twelve say `roundtrip_ok=true`, including the extended rungs where its own
`Files.write` cells record the parse-layer refusal. The divergence is now data in the tree rather than a
reproduction file a reader has to trust, and each of the twelve carries `toolchain` and `jvm_self_report`. What is
still open is narrower than what was: the remaining `java.io` entries, and the second runtime's answer as a cell
rather than as a capture. Acceptance - and one requirement this seat wrote into a ticket that no contract round
contains (`control_pass_evidence`; the new census shows 30 stamps across six ports and zero sources, in every lane
alike) - is recorded in `evidence/S11/SG-F2-acceptance.md`.

## M8 - the contract's required list and the gate's verdict list are different sets

Reading at 12:05 host clock: `python ci/validate_cells.py` prints `invalid=0` for all 557 cells on the six
canonical faces, and `python ci/equality.py` in the same minute prints `verdict_not_recorded_pairs=121`. Both
are correct. `spec/schema.json` requires 17 fields; **nine of the ten fields the gate scores as a verdict are
not among them**, and four (`phantom`, `name_mutated`, `len_triple`, `name_landed_as`) are not even listed in
the schema's `properties`. The product promise is about those nine.

This is worth recording as a finding rather than a bug because the six ports' own behaviour separates the two
kinds of blank, which the contract cannot:

- seven of the nine optional verdict fields are answered on all 44 required cells by at least one port
  (`mechanism_class`, `phantom`, `len_triple`, `roundtrip_ok`, `name_mutated`, `bytes_on_disk`,
  `enum_to_stat_agrees`) - so for those, a blank is that implementation's gap;
- `bytes_written` and `name_landed_as` top out at 39/44 with **no** port at 44, and 10 field-cells are blank
  in every port at once - the pattern a genuinely non-existent answer would leave.

`docs/coverage.md` (field x port) and `docs/cell-validation.md` (omissions x port) publish the two views of
the same cells side by side; `docs/journey.md` 2.16 records what changed in the instruments. The decision
this needs from the owner is one contract round: say which verdict fields apply to which case group, and give
the boolean fields the same `not_applicable` escape `read_result` already has. Tightening `required` without
saying which blanks are legal would make every port fail on cells where the answer truly does not exist, and
tightening it in neither direction leaves a tree that is simultaneously 0-invalid and 121-blank.


## M9 - the delivery-form leg was wrong four times in one afternoon, and the four wrong answers were mutually consistent

`ci/delivery_form.py` answers the buyer's first question - what do I get, what must I install, how big is it -
which nothing in `ci/` had ever measured. Four defects in roughly three hours, all four invisible from inside the
leg, because each one produced a number that another honest-looking reading agreed with.

1. **Disk as delivery.** The first version sized whatever `impl/**` build output existed on this disk, so a
   lane's scratch artifacts were published as the size of the deliverable. A cold clone read 3,796 bytes of
   generated face where the working copy read 3,834. Found by the clone, not by reading the code.
2. **A filter that dropped everything, verified by the number it was supposed to verify.** The fix read
   `git ls-files -z`, but the splitter was written `split("SEP")` instead of `split(chr(0))`, so the "set" was one
   element of 61,776 characters. Every path was therefore judged untracked, every artifact column came out zero -
   and the clone agreed, because a zero agrees with a zero. I wrote the clone agreement up as the vindication of
   the fix in the commit message of the fix.
3. **A disk-dependent column in a repository-level face.** `untracked files ignored` counts files that had to be
   present to be ignored: the same commit read `14` in the working copy and `12` in a clone. Moved out of the
   published face into the run line, where it is still printed per port and now labelled as a machine fact.
4. **Two path spaces, silently disjoint.** `glob` keeps whichever separator was typed inside the pattern, so its
   results came back as `D:\repo\impl/java/build\CellProbe.class` while the tracked set was normalised to pure
   backslashes. Nothing ever matched: six committed `.class` files, the tracked `impl/python/sg_run.py` and seven
   tracked TypeScript sources were classified as untracked, and the leg's headline - "no port's build output is
   tracked, a clone gets source plus a toolchain command" - reached a published face and two commit messages.
   `8f04c39`'s last paragraph is false and stays in history; `d6994fd` corrects it forward.

Defect 4 was found by something other than me re-reading the leg: `git_artifact_paths(port)` asks git's own
pathspec matcher which tracked files live under the port's prefixes, and `self_check` refuses to publish when the
leg's classification and git's disagree. Its first message read

```
java: this leg's file classifier kept 6 tracked artifact(s) and git's own pathspec names 0; the two enumerate
the same commit, so a difference is a bug in the leg
```

The witness was then wrong too, in the opposite direction, for the same class of reason: its pattern translator
was `fnmatch` with `**` replaced by `*`, which turns `build/**/*.class` into a two-segment pattern and matched
none of the six real files. That is why the translator is explicit (`pattern_to_regex`) and why it has its own
two-sided arm. This is the second time in this project that the instrument used to test an instrument had to be
tested; the first was `matrix_table.py` being made to consume the gate instead of judging again.

Current state, all of it reproducible: `arms=18 passed=18`, `instrument_problems=0` (leg and witness enumerate
the same files), generator rc=0, and `docs/delivery-form.md` at 4,798 bytes regenerated byte-identically inside a
cold clone of `d6994fd` apart from its timestamp line. The measured answer the leg now gives:

- 14 tracked artifact files, 310,141 bytes - java 6 `.class` (86,825 B), python `sg_run.py` (81,900 B),
  typescript 7 `.ts` (141,416 B);
- `csharp`, `go` and `rust` commit no build output at all, and rust's two release executables exist only on the
  disk that built them (`drops=...rust:2` in the working copy, `rust:0` in the clone);
- zero installers of any format in the tree, so no size claim about a shipped product is supportable here;
- `tool/check.py`, 81,759 bytes, standard library only, is the one file that runs today with just a Python 3
  interpreter.

Two rules came out of it and both are now mechanical, not advice:

- **A leg that classifies files must be checked against an enumeration it does not implement.** A denominator
  proves how many records were read, not which ones were read correctly; `files_scanned=` and `tracked_paths=` are
  necessary and were not sufficient.
- **A filter must carry a green arm proving it passes something.** Every other arm in this leg's suite was
  satisfiable by a filter that discarded the world. A5 is that arm, and A16 is its separator-specific twin.

`docs/journey.md` 2.18 carries the narrative with the original outputs;
`evidence/S10/cold-clone-20261011d.md` carries all four clone runs, including the two whose numbers this section
supersedes.

