# Journey - how a one-line requirement became six ports and a gate that kept catching its own author

Not a marketing document. The value of this file is that the mistakes are in it with their original
output, in order, including the ones the project's own instrumentation caught while it was being built.
Every quoted line below was captured in this repository's tree during the build. Where a reading is
historical - a face the current gate no longer reads, or a number from before a rule changed - the section
says so; the rest re-runs from a clean clone.

Sequence: a one-line requirement -> a requirement document -> a UI -> a construction order written by six
Six independent language ports, written blind to each other -> a gate -> acceptance. Roughly 36 hours, most of
it one night.

## 1. The requirement, and the reversal that decided everything

The brief was a file-name pre-flight checker: point it at a folder, it tells you which names will break on
the recipient's machine. The project was also meant to be a portfolio piece - six languages, three
operating systems, twenty traps - and the original construction order built its whole argument on
**divergence**: six ports disagreeing proves the problem is real.

The owner rejected that framing at 3 a.m. and replaced it with the opposite claim: *one frozen
specification, six implementations that have never seen each other's code, byte-identical output.* Divergence
became an appendix that falls out for free.

That reversal deleted more of the plan than it kept. Gone: the three-layer attribution tree (L1 OS / L2
stdlib policy / L3 language semantics), the divergence-hit Go/No-Go gate, the counting statistics, and the
blind-session ceremony around them. They were load-bearing only for a claim nobody was selling any more.
What replaced them is three legs: **the specification is one thing** (one frozen file, hashes published
before any port ran), **the implementations are independent** (no cross-language calls, no shared helper),
and **the result is checkable from outside** (the equality gate, a sealed expectation table, and the
machine's own tools as a referee).

## 2. Failures and retractions, in the order they happened

This section is more than a quarter of the document on purpose.

### 2.1 A gate that reported 29 of 29 cells failing, because it was comparing spellings

The first full six-port run:

```
OUTCOME=RED disagreeing_cells=29/29 required_cells_missing=51
   ctrl/T-CTRL-ASCII | name_encoding csharp:'hex_raw_bytes' vs go:'utf16_code_units';
                     name_landed_as csharp:'7265706f72742d323032362e747874' vs java:'report-2026.txt'
```

Reading the cells themselves showed four ports had recorded the *same fact*: create `ok`, 28 written, 28 on
disk, read `ok`, `legal`, and the same payload digest `c9fe45b2fee8ea84…`. The gate was comparing how each
language wrote a name down (hex versus text) and how each wrote a triple of numbers (a dict, `15/15/15`,
`[15,15,15]`, or not at all). **I fixed the gate, not the ports.** After canonicalising representations the
same data reads:

```
OUTCOME=RED verdict_disagreements=42 verdict_identical_cells=18/30 unpinned_input=12 incomparable=2
```

That number is worth looking at twice: the count of disagreements went *up*, because a gate that buries
signal in noise also hides real conflicts. 19 conflicts became 42 the moment the comparison was honest.

### 2.2 A required-cell list I published from a mis-parse, and had to withdraw by name

The first `spec/cells-required.json` counted only the 20 traps and missed the control cells, the member
splits and the length rungs. It was already published to six windows when I found it. The withdrawal is
written into the file itself rather than into a chat log, because a file a stranger can read has to
disown its own bad version:

```
WITHDRAWN: the 03:4x version of this list came from a mis-parse ... discard it and re-derive from the current file.
```

### 2.3 The two rulers started disagreeing with each other, and a port caught it

`spec/schema.json` and `spec/validate.py` enforce the same contract in two places. rev3 changed one and not
the other, so a port's cells validated green under one ruler and failed under the other. Reported by the
TypeScript session rather than smoothed by me:

```
cells_required=33 cells_produced=74 cells_valid=25 (strict, spec/schema.json rev3)
```

Both rulers now load the same closed sets, and the notice tells the ports: if they ever disagree again,
say so in the report instead of picking the convenient one.

### 2.4 A lock table I believed was broken, when my own measuring face was wrong

The frozen spec publishes sha256 digests of eight artifacts. My first check hashed the *checked-out* files
and reported that the lock was lying: 384 of 388 files differed between commit and clone. The commit was
honest - `core.autocrlf` rewrites line endings on checkout, and the digests were of blobs. The repository
now states one rule for every digest in it, in `spec/cell-identity.md` §7: *every digest in this repository
is a blob-face digest*, and `ci/blobhash.py` is the only way to compute one. A self-test arm
(`lock-table-faces`) checks both faces at once, so the mistake cannot be made silently a second time.

### 2.5 A gate that had only ever been seen refusing

Adding rules until everything fails is the failure mode of this whole genre of tooling. `ci/selftest.py`
exists because of it and now has 14 arms, of which four require the gate to **say yes**:

```
  green-identical              expect_rc=0 got_rc=0   OK   two ports agreeing must return 0 - a gate that cannot say yes is dead
  probe-difference-is-data     expect_rc=0 got_rc=0   OK   create_result alone must be published as spread, not judged as a broken claim
  alias-folds-spelling-drift   expect_rc=0 got_rc=0   OK   T09a / T-BLIND-1 are the same questions as T09-m1 / B1
  alias-refuses-to-guess-member expect_rc=3 got_rc=3  OK   bare T09 must not be folded into T09-m1
arms=14 passed=14 failed=0
```

### 2.6 Piping a self-test into `tail`, and committing broken code as a result

```
python ci/selftest.py | tail -3 && git commit -m ...
```

The exit code of a pipeline is the last command's, so `tail`'s 0 stood in for the gate's 1 and commit
`298d6e4` recorded a broken gate. Visible in the history, not removed: a later commit fixes it forward.
The rule now written into how this repo is operated: no gate's result goes through a pipe, and a `rc=0`
with no output is treated as a contradiction rather than a pass.

### 2.7 One port's own results were instrument-red, so they were excluded rather than edited

The Node face carried self-declared instrument failures and runtime crash text in the field where a verdict
belongs:

```
   node       instrument_red_or_conflict=31  control_pass_false=0  runtime_crash_text_in_error_message=31
   PORT node is INSTRUMENT-RED -> excluded from comparison; its cells are not evidence
```

That reading is historical: the exclusion was made by the health leg while the face was still canonical,
and rev6 later moved the same face to the non-canonical list, so the gate now prints it under
"faces on disk but not read" instead of re-running its health counts. The face is still on disk
(`results/node`), named in `docs/evidence.md`, and unread by the gate. Deleting it would have removed the evidence that the gate catches a bad run.

### 2.8 The length family: six ports asked six questions because the spec's sample was prose

`spec/cases.yaml` pinned a length and a path form for T17/T18 but wrote the sample as
`T-LEN-PATH (length bisection, G1-G4)` - a sentence, in a hex field. Six independent implementations then
did six true-but-different things:

```
   csharp      name_source='T-LEN-PATH (length bisection, G1-G4)'  len_triple=[48, 48, 48]
   go          name_source='616161616161616161616161616161616161'   len_triple=255/255/255
   java        name_source='303132333435363738396162636465663031'   len_triple={code_points: 256, ...}
   python      name_source='6636346339333230336e6e6e6e6e6e6e6e6e'   len_triple={requested: {code_points: 180 ...}}
   rust        name_source='742e62696e'                              len_triple={code_points: 32739, ...}
   typescript  name_source='61'                                     len_triple=[255, 255, 255]
```

One port recorded the label as the file name and its length; one reported a ceiling where a name's width
belongs; one recorded `t.bin` with 32,739 code points; one wrote the two characters `61` where a byte value
was meant. All twelve length cells were excluded from the comparison as `unpinned_input` at that hour, and the
project had **no comparable length evidence at all** - which was the honest headline for that family, not a
number dressed up. The fix was the same shape as the control-cell fix: pin the filler bytes, and separate
three quantities that were sharing one field name.

That resolution landed the same morning, and it is the part of this record worth reading for its outcome as
much as its diagnosis: five ports re-emitted the rungs at 09:0x, the last at 09:5x, and the length family
now produces a result no single-language checker could have stated - **all three plain-path rungs agree
across six independent ports, all three extended (`\\?\\`) rungs do not**. The disagreement is the customer-
legible form of "long paths are a per-executable manifest plus a per-call convention", and it took six
implementations to say it rather than one implementation plus an opinion.

### 2.9 A rule I wrote, tested and rejected inside the same hour

To stop the gate scoring a display-width cut as a divergence, I wrote a rule that removed any landed name
that turned out to be a prefix of the pinned input. It worked, and it was wrong within minutes: on `trail.`
and `trailsp ` the landed name genuinely **is** a prefix, because Windows drops the trailing dot and space -
that is the project's best finding. From the recorded bytes the two cases are indistinguishable, so the
rule was narrowed to *flag and keep*:

```
   PREFIX-SHAPED trap/T04 name_landed_as by csharp,go,java,python,rust - check each against that port's own length fields:
        a trailing character the OS dropped is a finding; a hex string cut at a display width is a record that contradicts its own name_mutated flag
```

A rule that cannot tell a finding from an artefact must not be given the power to delete one.

### 2.10 I put a false number in a commit message and appended a correction rather than rewriting

```
Correction to the previous commit message: five rows are NO-SUCH-CELL, not zero, and they stay that way
```

A commit message is a permanent set of assertions. The wrong one stayed; the correction is a new commit.

### 2.11 My own probe hung a session

Reading `CON.txt` to "see what happens" blocked for two minutes because reading a console device reads the
console's input buffer. Two permanent rules came from that: print the case name and flush **before** the
call, and a device-name probe may create and enumerate but never read the contents. The harnesses inherited
an external 5-second timeout per child process, because a timeout set inside a hung process cannot fire.

### 2.12 A fingerprint cascade, caught twice by the same arm

`spec/cells-required.json` carries the sha256 of the committed spec. Every time the spec gained a pinned
sample, that manifest went stale by one field, and the generator's determinism arm said so:

```
CHECK determinism: committed manifest == regenerated bytes -> DIFFERS (8575 vs 8575)
   only in committed: []   only in regenerated: []
```

Same length, same cell set, different bytes - the only kind of drift a human would call cosmetic and a
stranger cannot verify. It forced a second commit each time, which is the correct cost.

### 2.13 Three more, found between 09:00 and 10:30 while the morning report was being written

The same genre, three times over, so they go in the record rather than into a footer:

- **`aaaaaa` is valid hex.** After the representation fold, two ports that wrote the length component as text
  were decoded into three bytes of `0xAA`, and one name became a disagreement against four ports that wrote it
  as hex. Names are compared by the set of meanings a value could have; when that intersection is what
  rescued a cell the gate prints `NAME-CROSS-FORM-AGREE`, and an arm (`different-names-still-red`) keeps the
  rule from becoming a machine that declares different names equal.
- **The self-test overwrote the real verdict.** The gate emits `evidence/judgement/equality-verdict.json`; the path
  was hardcoded, so every fixture arm replaced the project's answer with a two-port toy - *while the
  self-test reported green*. Verdict paths are arguments now, arms write into their own scratch, the artifact
  records the face it came from, and `ci/matrix_table.py` refuses to publish a verdict that did not come from
  this repository's `results/`.
- **A crash reported itself as a disagreement.** `os.path.relpath` raises across mounts; with the caller's
  temp directory on `C:` and the repository on `D:`, the gate died with rc=1 - which is this gate's word for
  "the ports disagree". Eight arms went falsely red until the path handling was made total. The self-test is
  now run against two scratch roots whenever anything about paths changes, and the morning document tells the
  owner to do exactly that as a check on me.

Nothing was published between the first reading (29 of 29 cells failing) and the last (54 conflicting facts
over 44 compared cells): every number that reached a document was regenerated from a tree that had been
re-checked, and the two documents that went stale mid-morning say which reading they carry.

### 2.14 A sentence of mine filed one JVM's answer under a language's name

The whitepaper's §3 length row read "一门 False（它在 parse 层就拒绝了这个前缀）" - one port rejects this prefix at
its parse layer. The java session then reproduced the refusal against both JDKs installed on this host
(`impl/java/tools/ext-path-of-repro.txt`, one compiled class, both runs stamped `run_rc=0`), and the same class
file answers differently depending on which launcher reads it:

```
TAG 3 extended, SHORT, ordinary drive path | len=12 | input=\\?\D:\probe      [Temurin 17.0.17 - the exe the recorded cells ran on]
    Paths.get          -> THREW java.nio.file.InvalidPathException | Illegal character [?] in path at index 2
    new File(String)   -> OK  isAbsolute=true
TAG 3 extended, SHORT, ordinary drive path | len=12 | input=\\?\D:\probe      [Temurin 21.0.6 - same class file]
    Paths.get          -> OK  impl=sun.nio.fs.WindowsPath toString=D:\probe
```

The refusal was never "Java's". It belongs to one binary - and the recorded face had said so all along: it
carries a `toolchain` block, `jvm_self_report.java_version: 17.0.17`, and an `extended_leg_note` that names both
APIs and says java.nio throws on that string. My summary threw that detail away to make a tidier sentence, which
is the exact failure mode this project is supposed to be selling immunity against. The row is now qualified by
executable, and the measurement that should have been in the plan came out of it: how many ports even record
*which binary* answered (`docs/FINDINGS-rev6.md` M7 - java 74/74 faces, rust 174/174, python 123/125, under
three different field names and three different shapes; typescript 0/87, go 0/203, csharp 0/50 record nothing).
A promise of "byte-identical output" is only re-runnable on a machine that did not build it if the runtime
identity travels with the answer, and half the ports don't publish it. Giving that quantity a shared name is a
contract change and the current sealed round is the eighth, so the question goes up to the owner instead of
landing in this tree as a decision.

### 2.15 The headline I published was counting silence as agreement

The morning's report line was `24 cells with no verdict disagreement / 44`, and I repeated it in the README,
the claim boundary and the owner's one-pager. It was true. It was also the same mistake this project is
supposed to be immune to: a cell where six ports recorded three of ten verdict fields and contradicted on
none was being scored like a cell where six ports answered everything and matched.

The count surfaced while I was measuring something else - the TypeScript lane's schema conformance. Read
through the frozen manifest instead of the port's own claim, 25 of its 44 required cells are non-conforming,
and every one of them is missing exactly the fields that make a verdict comparable (`read_result`,
`roundtrip_ok`, `enum_to_stat_agrees`). That forced the question "what fraction of the verdict grid did
anybody actually fill in?", and the answer is in `docs/coverage.md`:

```
python ci/equality.py | sed -n '/coverage (who answered what)/,$p'

   verdict_pairs_recorded=2278/2640 (86.3%) cells_every_port_recorded_every_verdict_field=4/44
   pairs_no_port_recorded=10
   cells_with_no_verdict_disagreement=24/44  of_which_fully_recorded=4
```

So the strongest sentence the project can honestly say is narrower and better than the one I wrote: **on the
4 cells where all six ports recorded all ten verdict fields, they recorded them identically** - and those 4
are the plain-path length rungs (`len/T17` and `len/T18` at `base_len` 78 and 120). The 24 stays published,
but never without the 4 next to it, and both now ride in the same `OUTCOME=` line so neither can be quoted
alone.

Two things came out of hardening it that are worth more than the fix:

- **The gate had two rulers of its own.** `verdict["outcome"]` and the printed `OUTCOME=` word were separate
  expressions. Sabotaging only the artifact's expression left the file saying `outcome=PASS` while the
  process exited 3 - the exact two-rulers defect this project has caught in `matrix_table.py`, in
  `validate_cells` vs `cells_valid`, and in two ports arguing over a fingerprint. One `outcome_word` now
  feeds both.
- **The new arms had to be shown to bite, not just to pass.** `silence-is-not-agreement` flips to `rc=0`
  when the not-recorded tally is deleted; `nobody-answered-is-not-agreement` flips to `rc=0` when
  `all_blank` leaves `outcome_word`. And the green arm (`coverage-green-still-passes`) is what stops the
  rule from becoming a gate that can only complain. Writing them exposed a fixture of mine that had been
  leaning on the hole all along: `sub-identity-separates` left `bytes_on_disk` blank in *both* ports, so it
  had been passing on silence - it now records a value.

A blank is still not the same thing as "not applicable", and the contract does not yet say which verdict
fields apply to which case group (`len_triple` on a trap cell may be a legal blank; `roundtrip_ok` on a
length rung is not). Until it does, the gate reports every blank and judges none of them, which is the same
stance §2.9 took about prefix-shaped names: **a rule that cannot tell a finding from an artefact is not
allowed to choose which one to delete.**


### 2.16 "Conforming" and "answered" are different words, and my two rulers disagreed about which one they meant

`docs/cell-validation.md` went to `invalid=0` at 12:05 - every one of 557 cells on six faces carries the
fields `spec/schema.json` requires. In the same minute the gate reported 121 verdict field-cells blank. Both
readings are correct, because the two lists in this repository are not the same list:

```
python ci/validate_cells.py
wrote docs/cell-validation.md bytes=2536 invalid=0 missing_faces=0 verdict_fields_not_required=9 \
verdict_fields_undocumented=4 cells_omitting_a_compared_field=371
```

**Nine of the ten fields `ci/equality.py` treats as a port's verdict are not in the schema's `required` list,
and four of them (`phantom`, `name_mutated`, `len_triple`, `name_landed_as`) are not in its `properties`
either.** So a port can satisfy the contract and still leave the compared answer empty, and the product claim
- "six implementations, the same verdict" - rests on fields the contract never insisted anybody emit. That is
my defect, not a port's: I wrote both lists at different hours and never compared them.

How much of the emptiness is a gap and how much is a limit of the question was measurable, because six
implementations answer the same field differently. Denominator: the 44 required cells on each face
(`docs/coverage.md`):

| verdict field the schema does not require | best port | ports answering all 44 |
|---|---|---|
| `mechanism_class` | 44/44 | 5 of 6 |
| `phantom` | 44/44 | 5 of 6 |
| `len_triple` | 44/44 | 4 of 6 |
| `roundtrip_ok` | 44/44 | 2 of 6 |
| `name_mutated` | 44/44 | 2 of 6 |
| `bytes_on_disk` | 44/44 | 2 of 6 |
| `enum_to_stat_agrees` | 44/44 | 1 of 6 |
| `bytes_written` | **39/44** | none |
| `name_landed_as` | **39/44** | none |

For seven of the nine, at least one port answers every one of the 44 cells - so the blank is an
implementation gap, not an unanswerable question. For `bytes_written` and `name_landed_as` nobody reaches 44,
and 10 field-cells are blank in all six ports at once; those are where "this answer does not exist for this
cell" is plausible. Across all 557 cells the six faces published, 371 of them omit at least one compared
verdict field. The contract cannot tell a gap from a limit, which is the same wall §2.9 hit from the other
side: **a rule that cannot distinguish a finding from an artefact must not get to choose which one to
delete** - so the gate now publishes every blank and judges none of them.

Two instrument consequences landed with it:

- `ci/validate_cells.py` imports the gate's own `VERDICT_FIELDS` instead of keeping a second list, prints the
  requiredness gap and the per-port omission table, and gained 20 arms of its own. Its crash wrapper exists
  because a `KeyError` in the new counter exited **1** - which is this leg's word for "a cell does not
  conform" and is in `ci/refresh_all.py`'s acceptable set, so the crash would have been filed as a result. The
  wrapper is proven both ways: reintroducing the crash gives `OUTCOME=INSTRUMENT-RED` and rc=3, removing it
  gives rc=0.
- A `PASS` from the equality gate is now unreachable while a compared verdict field is blank, by one port or
  by all six (`arms=21`, and both new red arms were shown to flip when the rule they name is deleted).

The contract change this asks for is not mine to make unilaterally, and it is bigger than naming a field:
declare which verdict fields apply to which case group, and give a boolean a documented way to say
`not_applicable` (the closed set already does this for `read_result`, which is why `not_applicable` exists
there). Cost if the owner says yes: six ports re-emit their faces, and every "0 invalid" in the tree starts
carrying a second number.

**And a worker caught this local leaving a broken instrument in the shared tree.** At 12:02 the TypeScript
session reported that `ci/equality.py` would not parse - `SyntaxError: unmatched ')'` at line 944, 13 format
arguments against 11 placeholders - and refused to touch `ci/`, re-deriving its own counts from
`git show HEAD:ci/equality.py` so its report would not depend on the broken file. That was me: I was
sabotaging arms to prove they bite, and the work tree carried a half-edited gate for several minutes while a
worker was running against it. Two rules come out of it, and the second one is the one I would otherwise
skip: a local's tool edits are worker-facing files, so they belong in history before somebody else trips over
them; and a sabotage experiment is only honest if the file is shown to compile and its arms to pass **after**
it, which is now a step in the routine rather than something I remember to do (`python -m py_compile` on the
five `ci/` files touched today, rc=0, before the 12:27 commit). The lane's own wording, kept because it is
the cleanest description of the discipline in this whole build: "It ran cleanly for me minutes earlier, so
the edit is in flight, not abandoned."


### 2.17 "One frozen spec" was a line in a header, not a check on the records

The equality claim depends on all six ports having answered *the same* specification. I had that in
`spec/cells-required.json`'s header (`spec_blob_sha256`) and in every cell's `spec_sha256` field, and nothing
in the pipeline ever compared the two - the fingerprint was decoration until I looked at it because the
TypeScript lane's conformance fix made me check what the records were stamped with.

```
python ci/spec_drift.py
wrote docs/spec-drift.md bytes=2491 compared=264 current=237 older=27 unstamped=0 older_unresolvable=0 affected_by_delta=0
OUTCOME=CLEAN drift_reached_compared_cells=0 (older fingerprints disclosed above, 27 records)
```

**27 of the 264 compared records - all Python's trap, blind and T-API cells - are stamped with the fingerprint
committed at 05:05, not the one from 06:11.** That is the round before `len_fill` existed, which is also the
round the length family was unusable in. The leg does not let me hand-wave it: it locates the commit whose
`spec/cases.yaml` blob hashes to that fingerprint, diffs that face against HEAD, and intersects the ids the
delta touches with the ids of the cells carrying the older stamp. The delta touches `T17`/`T18` only; the 27
records are none of those, so the answers were asked under text that has not moved. `docs/spec-drift.md`
prints the whole chain, and if a future delta ever does reach a stale cell the leg exits 1 instead of writing
a sentence about it.

Two defects in the leg itself, caught by its own arms rather than by anyone else:

- Reading ids only off the changed line is **under-inclusive**: a case is a block, so editing `- id: T01`'s
  `name:` two lines below changes T01's question and names no id on that line. Arm A3 failed against the first
  version; the fix walks back to the enclosing `id:`. My docstring had promised the opposite bias ("wide on
  purpose") while the code was narrow - which is the worst kind of comment bug, because the comment is what a
  later reader trusts.
- `assess()` read the spec through git, so no fixture could reach the same code path the real run uses. A leg
  whose arms test a different path than production is decorated, not tested; there is now a `reader=` seam and
  A7/A8 exercise the real comparison through it. 15 arms, and the two red ones were shown to flip when the
  enclosing-id walk is deleted.

It also caught itself once on the way: my first hand count of "compared records" was 291 against the gate's
264, because I re-implemented which of a port's duplicate representations stands for a cell. The gate now
emits `compared_records` in its artifact and the drift leg reads that - the same fix as `matrix_table.py`
learning to consume the gate instead of judging again.


### 2.18 A filter that passes nothing looks exactly like a measurement of nothing

`docs/delivery-form.md` exists because the repository answered "do the six implementations agree" and never
answered "what does a customer actually get". Four times in one afternoon that leg published a confident table
that was wrong, and all four failures had the same shape: a number that agreed with itself across two machines,
because nothing in the leg could ask a second party whether its file set was right.

1. It sized whatever was on the disk, so a lane's scratch build output was published as the size of the
   deliverable and a cold clone read 3796 bytes where the working copy read 3834. Fixed by measuring
   `git ls-files`.
2. The fix did not work and looked like it did. The splitter read `split("SEP")` instead of `split(chr(0))`, so
   the "set" was one element of 61,776 characters holding 1,166 NUL-separated paths, and the filter dropped every
   file - producing exactly the table a clone produced, because the truth happened to be a zero. The clone
   agreement I had written up as the vindication of the fix was the bug's own symptom.
3. The column that counted dropped files was itself disk-dependent: a file must be present to be ignored, so the
   local read `untracked_ignored=14` and a clone of the same commit read `12`. Moved out of the published face into
   the run line.
4. `glob` keeps the separator typed inside the pattern, so its results came back as
   `D:\repo\impl/java/build\CellProbe.class` while the tracked set was pure backslashes. Nothing ever matched:
   four committed `.class` files, `impl/python/sg_run.py` and seven TypeScript sources were classified as
   untracked, and the leg's headline became "no port's compiled output is tracked" - a sentence that reached a
   commit message and a customer-facing table before anyone contradicted it.

Defect 4 is the one I did not find. The leg was given an independent witness -
`git_artifact_paths(port)` asks git's own pathspec matcher which tracked files live under that port's prefixes,
and `self_check` refuses to publish a table where leg and witness disagree - and on its first run the witness
said:

```
OUTCOME=INSTRUMENT-RED the table above is not a measurement - 1 instrument problem(s), first: java: this leg's
file classifier kept 6 tracked artifact(s) and git's own pathspec names 0; the two enumerate the same commit, so
a difference is a bug in the leg (-)
```

The witness was then wrong too, in the opposite direction, for the same class of reason: its translator was
`fnmatch` with `**` replaced by `*`, which silently turns `build/**/*.class` into a two-segment pattern. So the
translator is now written out (`pattern_to_regex`) and arm A18 asserts both its sides. That is the second time
this project has had to test the thing it used to test the thing - the first being `matrix_table.py` consuming the
gate rather than judging again.

What the leg now says, with `arms=18 passed=18` and `instrument_problems=0`, and reproduced byte-identical in a
cold clone of the commit that carries it (the import-count and timing columns are elided here, not in the file):

```
| java | 86 | 6 | class | 6 | 86,825 | `impl/java/build-check/CellProbe.class` |
| python | 123 | 1 | py | 0 | 81,900 | `impl/python/sg_run.py` |
| typescript | 87 | 7 | ts | 0 | 141,416 | `impl/typescript/src/runner.ts` |
```

14 tracked artifact files, 310,141 bytes, three ports (`csharp`, `go`, `rust`) committing no build output at all,
zero installers of any format, and `tool/check.py` at 81,759 bytes as the only file here that runs without a
compiler. The earlier retraction stands as a retraction: 8f04c39's last paragraph is false and was not rewritten.

Two rules came out of it, and both are now mechanical rather than advice. A leg that classifies files must be
checked against an enumeration it does not implement - a denominator proves how many it read, not which ones it
was right about. And a filter must have a green arm proving it passes something: `A5` in this leg's suite is "a
tracked artifact must survive the filter", because every other arm in the suite was satisfiable by a filter that
dropped the world.

What the four defects also changed in the process, not just in one file: the cold-clone rehearsal that found
three of them had been run all afternoon by a script outside the tree, which is a habit and not a gate.
`ci/clone_parity.py` (8900037) is that rehearsal as a leg - caller-supplied scratch root, drive root refused,
nothing ever deleted, an existing clone adopted only when its HEAD equals the source's and its status is empty,
and a difference allowed only inside a line shape declared in advance. Its red side was probed deliberately
without committing a false face: a one-digit tamper of `docs/coverage.md` was put into an unreachable probe
commit on a temporary branch in a separate work tree, and the leg answered
`OUTCOME=RED faces_compared=12 identical=10 declared=1 differing=1 missing=0`, naming the file, the line count
and both texts. The probe, its cleanup and the first attempt that failed because the probe commit predated the
leg itself are in `evidence/closing/parity-red-probe-20261011.md`.


## 3. What the six windows did that the plan did not expect

Two things the committee's construction order never asked for and the ports delivered anyway: the
TypeScript session published a port label it could not verify ("no type-checker has ever run against this
source") and refused to let it be upgraded to "TypeScript verified"; the Go session answered the same name
with `legal` where five others said `illegal`, and the answer turned out to be about which path prefix it
had asked - a fact the contract now records as `verdict_via` instead of scoring as a mistake.

## 4. What is not done

No macOS or Linux rows exist: they need CI, and pushing to the public repository is the owner's act, not
mine. The desktop deliverable exists as a script with a launcher and has not been signed, so "double-click
to run" is not yet an evidenced claim on a machine that did not build it. The license is unset. The
repeated-run and multi-volume cases (FAT32/exFAT, network shares, mail and download layers, phones) were
cut from the delivery path early and remain unmeasured. `docs/GAP.md` lists the cell-level gaps by name;
`docs/whitepaper.md` carries only findings that a command reproduces.
