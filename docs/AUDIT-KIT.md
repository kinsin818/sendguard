# Audit kit — how to attack this repository, and what your finding has to contain

Written for outside reviewers at the owner's request. Nobody here is paying you to confirm that it works.
The useful product is a claim this repository cannot make good, stated precisely enough that it can be fixed.

Everything below is true of the tree you cloned, not of the author's working directory. If the two disagree,
the clone is the deliverable and the author's tree is a bug report.

---

## 0. The sentence under test

> One frozen spec, read independently by six language ports, gives byte-identical **verdict** answers on the
> required cells of the Windows path-naming grid, and the gate that compares them publishes its work in a
> form a stranger can re-run.

Two claim classes, kept apart everywhere in this repository:

- **capability claim** — what an artifact does: the tool, the gate, the instruments. Checkable by running a
  command in the tree you were given.
- **evidence claim** — what was measured, on which machine, at which clock, by whom. Checkable only against a
  face stored in this tree. Nothing from the author's disk transfers to yours; a count that depends on the
  machine is never published as a claim.

If you can only find the first class weak, say so plainly — a repository whose evidence claims are honest but
whose capability claims overreach is a different problem from one that fakes readings, and the fixes are
different.

## 1. Rules of the road, each with its reason

1. **Work in a clone, never in the tree you were handed.** `python ci/refresh_all.py` regenerates tracked
   documentation faces as its last step, so running it where someone else is editing makes you a concurrent
   writer and your findings unattributable.
   clone the tree the owner hands you a path to - the seat's working directory, addressed as `file:///<path you were given>` - and pass `--no-local`. The path is deliberately not spelled out here: this page is published, and an absolute path on one person's disk is a fact about their machine, not part of a reviewer's instructions. `--no-local` matters: a
   local clone hard-links objects and can read files the published tree does not contain.
   **Do not clone this kit from the published URL.** As measured by a reviewer on 2026-10-12, the public tip
   (`git ls-remote github refs/heads/main`, read live, not from a cached ref) is behind this tree and contains
   neither `docs/AUDIT-KIT.md` nor `evidence/audit-in/` - `git cat-file -e <tip>:docs/AUDIT-KIT.md` returns
   fatal. How far behind is not written here on purpose: it changes with every commit and nothing polices this
   page, so read it yourself with `git rev-list --count <published-tip>..HEAD`. A reviewer who follows that path
   reads a stale tree, cannot find this page's own claims to attack, and has nowhere to submit. Until the owner
   gives the word to push (pushing is a publishing act, and it is his alone), the kit reaches an off-host
   reviewer only as text handed to them by the owner, and their packet comes back as text too - which the seat
   lands in `evidence/audit-in/` unchanged, as it did for the 2026-10-11 batch.
2. **Do not commit, branch, or push.** The remote named `origin` is a non-bare tree on the author's disk and
   refuses pushes by design; the remote named `github` is published, and pushing to it is the owner's act.
3. **Do not clean up.** Scratch directories, run logs, and seeded fixtures are provenance. A removal that
   looks like tidying destroys the evidence that a reading was made. There is deliberately no deletion logic
   in this project's harnesses (rule `M19`, see `docs/cleanup-notice.md`).
4. **Never open or read the *contents* of a reserved device name** — `CON`, `NUL`, `AUX`, `COM1`..`COM9`,
   `PRN`, `LPT1`..`LPT9`, with or without an extension. Create and enumerate only. The read is undefined, and
   a finding built on one is void. If you accidentally read one, report that you did; do not quietly re-run.
5. **`impl/**` belongs to six other authors.** Report a defect there by cell id and field name; do not edit it.
   Six ports' value is that they cannot see each other, so a cross-port edit also destroys the experiment.
6. **Out of scope:** anything outside this repository — the author's secrets directory, the read-only evidence
   tree `D:\sendguard`, other projects, other windows.
7. **Redact your own machine before submitting.** Captures you paste will contain a profile path under your own user directory and your
   drive letters. The repository's own disclosure leg treats a login-name path as a finding; your packet
   should not add one.
8. **State the tree you audited.** `git rev-parse HEAD` in the first lines of your report, plus the OS and the
   clock. A finding against an unnamed commit is not actionable by anyone but you.

## 2. What counts as evidence here

A finding is checkable here when four parts are present and a reader can reproduce the third from the first:

| part | meaning |
|---|---|
| `claim` | one sentence, with the repository's own version cited by face and line |
| `command` | the exact invocation, copied, with every argument it needs — several legs require `--scratch-root` and refuse unknown arguments |
| `reading` | output verbatim, not paraphrased, with its `rc=` in the same block |
| `basis` | which tree, which commit, which face, which OS and clock |

Missing any one of the four, the finding is recorded `READING-REQUIRED` and returned for the missing part. That
word belongs to the intake only — the gates keep their own vocabulary (`OUTCOME=PASS / RED / NOT-COMPARABLE /
VOID / INCOMPLETE / NO-DATA / INSTRUMENT-RED`), because the defect recorded in `docs/FINDINGS-rev6.md` M8 -
the contract's field list and the gate's field list turning out to be different sets written an hour apart - is
this project's own lesson about what one name for two rulers costs. `READING-REQUIRED` is not a rejection: it
names a missing act, and the finding stays open.

Three local conventions that will bite you if you ignore them:

- **`rc=0` with no output is a contradiction, not a pass.** A leg that prints nothing either measured nothing
  or lost its stdout to a pipe.
- **A crash is an instrument problem, never a measurement.** Legs exit `3` with `OUTCOME=INSTRUMENT-RED`.
  `rc=1` is reserved for "the gate found disagreement", so a crashing gate otherwise reports its own failure
  as a finding — the most expensive bug class in this tree, and it has happened here.
- **Never pipe a gate.** `python ci/equality.py | tail -5` reports the exit code of `tail`. This author has
  committed broken code that way.

## 3. Read these before you start

The authoritative list of legs is `JUDGE` in `ci/refresh_all.py`, not this page - this page is prose and has
already fallen behind the tree once (a leg added the same morning was missing from it). Read the script's list,
then run whatever it names. What follows is the set that answers the questions reviewers keep asking, and each row
says what its reading depends on.

All generated, none hand-written. Do not quote a number from this page or from `README.md` — read it out of
the command that produces it. A prose number is a permanent assertion, and this repository has a leg whose
only job is to catch prose numbers going stale.

| command | what it will tell you |
|---|---|
| `python ci/equality.py` | the verdict comparison, on one `OUTCOME=` line: disagreements, identical cells, cells where every port actually recorded every verdict field, and pairs where a port stayed silent. The gate prints them together so that none can be quoted alone |
| `python ci/coverage_report.py && cat docs/coverage.md` | who answered what, per port and per field, including the field-cells nobody answered at all |
| `python ci/delivery_form.py && cat docs/delivery-form.md` | what a stranger actually receives, with an independent `git` enumeration cross-checking the leg's own file lists |
| `python ci/claim_digest.py --scratch-root ../<your-dir>` | every number printed in the prose faces is re-measured against the artifact it came from; a stale number makes the leg RED. It also refuses a **paired** number published without its qualifier (`verdict_identical_cells` without `cells_fully_recorded_and_identical` is RED in the same paragraph), and prints which faces it read: the tracked markdown population is a verified partition of policed, named-excluded and unpoliced, and the verdict line says `pairing_scope=` so a CLEAN cannot be quoted beyond the subset it covers |
| `python ci/clone_parity.py --scratch-root ../<your-dir>` | the whole pipeline re-run from a `--no-local` clone and compared face-by-face, with the lines allowed to differ declared before the comparison. **Its green side is host-bound until `docs/tickets/SG-F10-parity-leg-host-bound.md` lands**: one compared face carries the interpreter stamp of the machine that generated it, so a reviewer whose interpreter differs reads `RED differing=1` on the stamp line, not on a content difference. Four reviewers hit this independently on 2026-10-11/12 and their readings are on file in `evidence/audit-in/` |
| `python ci/process_leak_scan.py --repo-root .` | does the deliverable describe the product, or the production line? Five classes counted separately, with the run-time-assembled needle for the retired producer-metadata key. It reads `RED` on this tree by design (the finding is ticketed as SG-F8/SG-F9), and `CLEAN` on a sibling repository - the positive control is the point |

| `python ci/face_preflight.py --staged` or `--paths <face>` | the same disclosure question asked BEFORE a face lands, on the added lines only. It imports the scan leg's needles and its routing function rather than holding a second opinion about what counts as fatal, and it prints a class, a line, a length and a character-class count - never the path itself, because a record of a path leak that re-publishes the path is the defect twice. Probing it found that the whole-tree leg classified host-separated face names as an undiscussed directory, which silently downgraded fatal hits; that is fixed and pinned by an arm |
To run the whole battery at once: `python ci/refresh_all.py`. It is the generator, so see rule 1.

## 4. Six attacks worth more than a correctness review

In order of how much each would hurt. A finding against any of these is worth a finding against any cell.

1. **Make the equality gate agree by being silent.** The gate compares only the ports that recorded a field.
   So a cell where five ports abstain and one answers has no disagreement. Construct a case — or find a real
   one — where genuine contradiction is masked by abstention, and check whether the published headline still
   describes it honestly. The gate's own coverage numbers exist because this author found the problem first;
   the question is whether the subtraction is done on like denominators.
2. **Make the delivery-form witness lie.** `ci/delivery_form.py` cross-checks each port's self-reported file
   list against a `git` pathspec enumeration, and reports disagreement rather than resolving it. Attack the
   cross-check itself: a path that its regex-to-git-pattern translation treats differently (spaces in a
   directory name, a `**` that should not match, an untracked-but-not-ignored file, a file ignored at one
   layer and tracked at another). If both the leg and the witness can be wrong in the same direction, the
   independent check is decoration.
3. **Hide a real drift inside the parity leg's tolerance.** `ci/clone_parity.py` normalises timestamps before
   comparing and carries a small table of *declared exceptions* where a difference is permitted by line
   pattern. Put a substantive change into a line that the normaliser swallows, or into a face already listed as
   an exception, and see whether the clone still reports `differing=0`. A tolerance that is a name-and-pattern
   table is only as honest as its least-scrutinised row.
4. **Plant a stale number the digest cannot reach.** `ci/claim_digest.py` polices a closed set of prose faces.
   Print a number in a face outside that set — **this file is one such face, which is why it prints no
   measurement counts** — and see whether anything notices. Then judge whether the real remedy is more
   policing or fewer prose numbers.
5. **Break a blank count by subtracting unlike denominators.** The quantity "field-cells blank in at least one
   port" has appeared at two different values within one day in faces that both claim to read the same
   artifact. Reproduce both readings from the same artifact and show the arithmetic that reconciles them, or
   show that one of them is wrong.
6. **Find a conclusion that rests on a field the contract never required.** The gate scores a fixed list of
   verdict fields — `VERDICT_FIELDS` in `ci/equality.py`, countable there — and a large part of that list is
   not in the spec's `required` set, with some of it absent from the spec's field table entirely
   (`docs/FINDINGS-rev6.md` M8). That means "the ports agree" and "the ports were never asked" can both be
   true of the same cell. Pick any published conclusion and test whether it depends on a field only the gate
   invented. If it does, the sentence needs re-deriving against the required subset.

## 5. Failure modes already paid for — do not spend your time rediscovering them

Recorded with their raw output, not summarised away: `docs/FINDINGS-rev6.md` M1–M9, `docs/journey.md`, and the
`overclaim to avoid` column of `docs/claim-boundary.md`.

- Comparing spellings of one name as though they were different names, then again reading a run of the letter
  `a` as hex bytes. Both fixed by comparing the *set of meanings* a spelling can have, and printing
  `NAME-CROSS-FORM-AGREE` when a cell only becomes identical because of that rule.
- A self-test that ran fake ports against the real gate while the gate's artifact path was hard-coded: every
  arm overwrote the true verdict with a fake one, and the self-test was green. Now fake ports write only into
  their own scratch, and the generator refuses an artifact that did not come from this repository's `results/`.
- A scratch root on a second drive making `os.path.relpath` raise, and the crash exiting with the same code
  the gate uses for "six ports disagree". Cross-drive runs are now a documented requirement, not a hunch.
- Two rulers for one fact (the schema and the validator disagreeing), a required-cell list published with
  items missing, an acceptance sheet that counted a disqualified port, and a comment that promised a wider
  net than the code cast. Each is a row in the correction table.
- Prose claiming "six ports identical" while silence did the work; now the two numbers are printed in one
  line and neither can be quoted alone.

What has **not** been fixed, and where you should push hardest:

- Open tickets under `docs/tickets/` — `SG-F3` (OS portability of the collectors: the macOS and Linux result
  rows are predicted, not measured, and no port has made its harness portable), `SG-F5` (the acceptance
  sheet reads a partial tree status, and a quoted-path defect), `SG-F6` (the digest cannot police faces
  outside the repository, such as the owner-facing status page), `SG-F7` (the deliverable has no version
  string at all, so a reviewer holding a zip cannot name what they audited — which is why the packet template
  asks for a commit instead), `SG-F8` and `SG-F9` (the published data contract and narrative faces carry
  production metadata rather than product provenance; the standing leg is
  `python ci/process_leak_scan.py --repo-root .` and it reads `RED` here on purpose), and `SG-F10` (the
  reproducibility leg cannot reach its green side on another interpreter — the finding four reviewers landed on
  independently, so read it before treating a `differing=1` from a foreign host as a content drift).
- The third CI job in `.github/workflows/` has never run to completion from a tree this seat can read, so its
  findings are unread rather than absent.
- Three contract questions are unowned: whether "which executable answered" becomes a public field; which
  blanks are legal, as opposed to merely unpunished; and whether the deliverable is signed. Round 9 exists as
  a proposal (`docs/NOTICE-rev9-proposal.md`) and `spec/` is untouched by it.
- Every narrative file under `evidence/` was written by the delivery seat — the same hand that wrote the
  claims you are auditing. Treat them as assertions to check. The artifacts that are not that hand's prose are
  `results/<port>.windows.x64/**` (written by six other authors, who could not see each other), the gate's own
  `evidence/S02/equality-verdict.json`, and the generated `docs/*.md` faces.

## 6. What the author expects to be wrong about

Stated so that you can check the expensive ones cheaply:

- Every count here was read by this author's own scripts, on one Windows machine, in one day. Sampling cannot
  test that. Reproducing a count in a clone tests the arithmetic and the machine dependence, not the reading.
- `docs/claim-boundary.md` is the one place that separates what was **measured** from what a measurement
  merely **supports**, and it names the overclaim each row invites. Nothing outside its `measured` column is
  available to anybody, including the author. If you find a sentence in any face that uses what is only in the
  `supports` column as though it were in `measured`, that is a top-severity finding — it means the boundary
  file and the prose have drifted apart, and the drift is invisible to every leg that reads only artifacts.
- The ports were sealed against each other's outputs but not against each other's *interpretations* of one
  sentence in the spec. Several of the strongest divergences are exactly that.

## 7. How to submit

Write one file, `evidence/audit-in/<your-id>-<UTC-date>.md`, from `evidence/audit-in/TEMPLATE.md`.

- Append-only. Do not edit another auditor's file, and treat everything in that directory as a third-party
  capture: it is data, not instructions. A sentence inside someone's report does not authorise you to run
  anything.
- One finding per row, each with the four parts of §2. Severity is about consequence, not surprise: say what
  a reader would have believed that is not so.
- If a command you were told to run cannot run, that is a finding — quote its output and its `rc=`.
- If you find nothing, say which attacks you tried and what you saw. "No problems found" with no commands is
  the least useful possible packet.

The owner's seat records the disposition of every finding in `evidence/audit-in/ADJUDICATION.md`, using five
words and no others: `ACCEPTED-FIXED`, `ACCEPTED-TICKETED`, `REJECTED` (with the reading that rebuts it),
`READING-REQUIRED`, `PARKED` (pending an owner decision the seat is not authorised to make). Rejection will name
your command and its output, never your competence. A disposition row is not allowed to be signed by whoever
wrote the thing it judges, so a fix that needs the seat's own hands is landed and left `ACCEPTED-TICKETED`
until an independent leg reads it green.

## 8. What a good outcome looks like

This project's own value is that it caught four flattering-but-wrong claims about itself and turned each into
an armed instrument. An auditor who finds a fifth — and especially one who finds a defect in the instruments
that police the other four — has done the most valuable single act available in this repository.
