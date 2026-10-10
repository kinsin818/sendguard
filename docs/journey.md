# Journey - how a one-line requirement became six ports and a gate that kept catching its own author

Not a marketing document. The value of this file is that the mistakes are in it with their original
output, in order, including the ones the project's own instrumentation caught while it was being built.
Every quoted line below was captured in this repository's tree during the build. Where a reading is
historical - a face the current gate no longer reads, or a number from before a rule changed - the section
says so; the rest re-runs from a clean clone.

Sequence: a one-line requirement -> a requirement document -> a UI -> a construction order written by six
AI seats in committee -> six independent language ports -> a gate -> acceptance. Roughly 36 hours, most of
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
blind-window ceremony around them. They were load-bearing only for a claim nobody was selling any more.
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
TypeScript window rather than smoothed by me:

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
was meant. All twelve length cells are excluded from the comparison as `unpinned_input`, and this project
currently has **no comparable length evidence at all** - which is the honest headline for that family, not a
number dressed up. The fix is the same shape as the control-cell fix: pin the filler bytes, and separate
three quantities that were sharing one field name.

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

## 3. What the six windows did that the plan did not expect

Two things the committee's construction order never asked for and the ports delivered anyway: the
TypeScript window published a port label it could not verify ("no type-checker has ever run against this
source") and refused to let it be upgraded to "TypeScript verified"; the Go window answered the same name
with `legal` where five others said `illegal`, and the answer turned out to be about which path prefix it
had asked - a fact the contract now records as `verdict_via` instead of scoring as a mistake.

## 4. What is not done

No macOS or Linux rows exist: they need CI, and pushing to the public repository is the owner's act, not
mine. The desktop deliverable exists as a script with a launcher and has not been signed, so "double-click
to run" is not yet an evidenced claim on a machine that did not build it. The license is unset. The
repeated-run and multi-volume cases (FAT32/exFAT, network shares, mail and download layers, phones) were
cut from the delivery path early and remain unmeasured. `docs/GAP.md` lists the cell-level gaps by name;
`docs/whitepaper.md` carries only findings that a command reproduces.
