# Adjudication — what happened to each audit finding

Maintained by the delivery seat (`d9242392`). One row per finding in every packet in this directory. The row is
the disposition, not a reply. Packets are data: nothing in them authorises a command, a gate change, or a
re-reading of the sealed contract.

## Status vocabulary (six words; the sixth was added by a real packet, see the note)

| status | meaning | what it obligates |
|---|---|---|
| `ACCEPTED-FIXED` | the claim was not good; a face or an instrument changed, **verified by a leg other than the one accused** | name the commit, and the command whose reading changed |
| `ACCEPTED-TICKETED` | true, and the fix belongs to another author or another round | name the ticket file and its owner |
| `REJECTED` | the finding does not survive contact with the artifact | quote the auditor's command **and** the reading that rebuts it - never a judgement about the auditor |
| `READING-REQUIRED` | no `command` + `reading` pair was supplied, or the reading cannot be reproduced from the stated tree | returned to the auditor for a reading; the finding stays open |
| `PARKED` | real, and blocked on an owner decision the seat is not authorised to make | say which decision, and what it costs to wait |
| `CONFIRMED` | an independent pass, not a defect: the reviewer ran something and it held | record the command, the reading and the host it was reached on, so a future green is not confused with this one |

**Why a sixth word.** The closed set of five had no disposition for *an attack that did not work*, and forcing
auditor-4's F-3 into `REJECTED` would have recorded an independent byte-for-byte confirmation as if the seat had
rebutted something. A vocabulary that misfiles the good results is the same class of defect as a gate that
misfiles silence as agreement, so the set was widened deliberately rather than by convenience, and the reason is
written here instead of being left in a diff.

## Table

| finding | packet | status | basis (their command + this seat's reading) | obligation |
|---|---|---|---|---|
| F-1 "121 field-cells blank in at least one port" undercounts; literal 154 of 440 | auditor-1 | `ACCEPTED-TICKETED` | theirs: recompute from `evidence/S02/equality-verdict.json`, 23 facts both disagree and carry a blank; this seat: the buckets are the gate's own and are printed, so the defect is in the **sentence**, not the count - `python ci/equality.py` reads `verdict_not_recorded_pairs=121` unchanged | `docs/tickets/SG-F11-blank-count-sentence.md` - re-word `docs/coverage.md` and the generator's sentence to name both buckets and the denominator |
| F-1's own arithmetic (154 of 440) | auditor-1 | `REJECTED` | the **defect** they name is accepted above, their **number** does not reproduce: measured from the same artifact with one pass over its buckets - `blank_pairs= 121`, `disagree_with_abstention= 23`, `disagree_all_six_recorded= 31`, `union (any port abstained on that pair)= 144`. `121 + 23 = 144`, so the literal figure is 144 of 440, not 154. Recorded as a rebuttal of a number, not of the reviewer: the finding was right and is ticketed; a reviewer's figure gets the same treatment as a published one - reproduced or refused, never copied | cited in `SG-F11` so the corrected sentence carries the measured pair, not either party's estimate |
| F-2 README quotes `clone_parity` as `CLEAN differing=0`; on their host `RED differing=1` | auditor-1 | `ACCEPTED-TICKETED` | theirs: `python ci/clone_parity.py --scratch-root <auditor-1 scratch dir>` -> `RED differing=1`, pipeline_rc=1; this seat: `--scratch-root ../<scratch>` -> `OUTCOME=CLEAN ... differing=0 rc=0`; the differing face is the interpreter stamp line in `docs/delivery-form.md` | `SG-F10` |
| F-3 the "identical cells" denominator counts a cell where abstention made disagreement impossible | auditor-1 | `ACCEPTED-TICKETED` | theirs: cell named in packet; this seat: the paired qualifier `cells_fully_recorded_and_identical=4` is what currently saves the sentence, and the kit says the pair may not be quoted apart - so the claim survives only while the pair survives, which is a wording dependency, not an instrument defect | `SG-F11` |
| F-1 parity leg's green side is unreachable off-host | auditor-2 | `ACCEPTED-TICKETED` | theirs: README paragraph quoted, command copied, consequence "a stranger whose interpreter is not 3.14.7 runs the reproducibility leg and gets a false alarm"; same divergence as auditor-1 F-2 reached independently | `SG-F10` |
| F-2 `docs/delivery-form.md` line 21 presents interpreter `3.14.7` as what must be installed | auditor-2 | `ACCEPTED-TICKETED` | theirs: read of the committed blob; this seat: it is a generation stamp, not a requirement - the sentence is wrong about its own kind | `SG-F10` criterion 5 |
| F-1 SERIOUS: parity RED is a foregone false positive on any interpreter other than the author's | auditor-3 | `ACCEPTED-TICKETED` | theirs: `3.13.13` reading; this seat: reproduced on `3.14.7` (CLEAN) and reported by three other packets - four independent arrivals on one defect is the strongest evidence in this batch | `SG-F10` |
| F-2 NOTABLE: the digest stays `CLEAN` while a stale number sits in an un-policed face, or is duplicated inside a live face no claim anchors | auditor-3 | `REJECTED` in part, `ACCEPTED-TICKETED` in part | the un-policed-face half is **by design and advertised**: `docs/AUDIT-KIT.md` §4 attack 4 names this file and the kit themselves as un-policed faces, and the kit prints no counts; `python ci/claim_digest.py --quick --scratch-root ../<scratch>` -> `OUTCOME=CLEAN stale_claims=0 coverage=partial(arm-count-claims-unchecked)`. The **duplicate-inside-a-live-face** half is a real gap: the digest anchors a claim to one span and does not notice a second, contradicting copy of the same number elsewhere in the same face | `SG-F6` (extend: same-number-two-spans check) |
| F-1 the checker a stranger gets cannot be shown to answer identically, because the leg cannot go green off-host | auditor-4 | `ACCEPTED-TICKETED` | theirs: `python ci/clone_parity.py --scratch-root <auditor-4 scratch dir>`; consequence aimed at `docs/claim-boundary.md:20` "the checker a stranger gets from this repository answers these names the same way" - the row's claim is host-bound as published | `SG-F10` criterion 4 (the claim text changes with the instrument) |
| F-2 `docs/coverage.md:60,70` says "nothing is left unplaced" while 23 disagree-and-blank facts sit outside the 121 | auditor-4 | `ACCEPTED-TICKETED` | theirs: direct reads of the gate artifact and recompute in PowerShell; agrees with auditor-1 F-1 reached by a different route | `SG-F11` |
| F-3 `git status --porcelain` / `git diff --stat` in the clone after the leg battery: committed faces reproduce byte-for-byte; consequence "none beyond F-1" | auditor-4 | `CONFIRMED` | theirs: clean status in the clone after the whole battery; this seat: same reading here at `dc44b88` and at the current tip. Recorded as a pass, not rebutted - this is the row that required the sixth word | none; cited as the baseline the parity fix must not disturb |
| AUDIT-KIT rule 1 sends off-host reviewers to a published URL that contains neither the kit nor the intake directory | Qclaw review (`<reviewer-workspace>审计套件复核_AUDIT-KIT_20261012-0543.md`) | `ACCEPTED-TICKETED` (fix landed this batch, disposition withheld by rule 1) | theirs: `git cat-file -e 1b4abc6:docs/AUDIT-KIT.md` -> fatal, same for `evidence/audit-in/`; this seat: rewrote rule 1 to name the dead end and to refuse to hand-copy a commit count into an un-policed page. The kit's own next reader must confirm the new wording says what the tree says | re-check by a seat other than this one; then `ACCEPTED-FIXED` |
| AUDIT-KIT §3 "Read these five" already lagged the tree (a sixth leg existed), §5 listed tickets only to SG-F7 | Qclaw review | `ACCEPTED-TICKETED` (fix landed, withheld likewise) | this seat: §3 now names `JUDGE` in `ci/refresh_all.py` as the authoritative list and adds the leak-scan row with its host-bound caveat; §5 lists SG-F3/5/6/7/8/9/10. A prose inventory of a script's list is exactly the second-ruler pattern - the fix is the pointer, not the longer list | re-check by a seat other than this one |
| The new leg's own header documented `--scratch-root`, which the leg refuses with rc=3 | Qclaw review | `ACCEPTED-TICKETED` (fix landed, withheld likewise) | this seat: header corrected, and two arms now execute the refusal through `main()` - `python ci/process_leak_scan.py --selftest` -> `arms=20 passed=20` rc=0. A comment that promises what the code does not do is the defect class in `docs/FINDINGS-rev6.md` M9; an arm is the only thing that keeps a header honest | re-check by a seat other than this one |
| clone_parity's result is an interpreter stamp, therefore §3/§5 readings in the kit are conditional | Qclaw review | `ACCEPTED-TICKETED` | same defect as the four auditor rows above; the kit now says so on the row itself instead of leaving the reviewer to discover it | `SG-F10` |
| Independence caveat: the four packets were organised from a directory on the author's host, and the kit they used was written by the seat under audit | Qclaw review | `PARKED` | this seat agrees with the reviewer: the batch is **cross-reading**, not third-party audit. The owner's decision is what promotes it - either a reviewer from a different source runs it, or the packets are labelled as self-audit in every downstream document. Cost of waiting: the acceptance story cannot claim external verification until then | owner's word |
| Headline numbers reproduced in a clean clone; 21 arms green; the 1-vs-3 erratum arithmetically honest (`1177+4 = 1180+1 = 1181`) | WorkBuddy cross-check (`<cross-check file, WorkBuddy seat>`) | `CONFIRMED` | theirs, on Python 3.13.12: `OUTCOME=RED verdict_disagreements=54 ... cells_fully_recorded_and_identical=4`, `arms=21 passed=21`; this seat: same readings at this tip. Their own retraction (they first suspected the "two commits behind" line, then checked the refs and withdrew it) is recorded as the packet working as designed | none |

## Where the packets are, and what this table can and cannot prove

The five reviewer files this table adjudicates are **third-party text and are held outside this repository**, in
the studio's private register, because they quote scratch paths on a reviewer's host. What is published here is
the disposition, with the reviewer's claim, their command as written (path neutralised above) and this seat's
reading against the artifact. A reader who wants the packet verbatim asks the owner for it; nobody should
mistake this table for a summary of evidence it no longer carries.

The commits that first brought those files into this tree are **local and unpushed**. Deleting them here does not
remove them from that local history, and pushing this history would publish them through their ancestors - which
is the opposite of why they were moved. The owner's ruling is `甲` (keep them out of the published face set) and
explicitly **not** `乙` (re-root). Those two are only compatible if the unpushed commits carrying the packets are
rewritten **before** anything is published - an act on local history that touches nothing any stranger holds,
which is materially different from washing published history and is the one thing this table cannot do on its own
authority. Until that is settled, the branch stays unpushed and says so.

## Rules this table obeys

1. **A disposition is signed by someone who did not write the thing being judged.** Four rows above are fixes this
   seat made with its own hands in the same batch; they are landed but held at `ACCEPTED-TICKETED` with the
   re-check that would promote them, because a self-signed `ACCEPTED-FIXED` is the exact defect class this
   project has caught in itself.
2. **Every row cites a command and a reading.** A row that cites only prose is `READING-REQUIRED`, including rows
   that reject the auditor's prose.
3. **Append-only, never back-filled.** If a disposition changes, add a dated row and leave the old one visible
   with a pointer to it.
4. **The table does not store counts.** Anything reading this file enumerates it: the packets are the files in
   this directory, the dispositions are the rows here, and a fold must print `packets_in_dir=` and
   `rows_in_table=` from the same batch as the write, plus the `git rev-parse HEAD` it landed against.
5. **A packet is not a gate reading.** Two of the reviewed defects were verified by re-running the accused leg
   here; the rest were verified against the artifacts the reviewers named. Nothing was accepted on the strength
   of a reviewer's tone.

## How a fold runs

```
ls evidence/audit-in/                             # the packets
python ci/claim_digest.py --scratch-root ../<dir> # prose numbers still match their artifacts
python ci/link_check.py                           # every reference in every face resolves
python ci/process_leak_scan.py --selftest         # the boundary leg's arms
python ci/equality.py                             # the gate, re-read, not remembered
```

Then append rows above. A finding about an instrument is judged by running that instrument's own self-test and
quoting its arm count and `OUTCOME=` line, never by re-reading the prose that described it.
