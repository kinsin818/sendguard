# The unpushed range was rewritten twice, and both passes are listed here

Ordered by the owner on 2026-10-12 (his option A: move the reviewer packets out of the published set, and do
not re-root the published branch). Executed at about 11:1x host clock. A history rewrite that is not documented
is indistinguishable from a cover-up, so this face is the documentation: what moved, what was removed, what was
scrubbed, what still resolves only through the table below, and what the rewrite cannot do.

## Pass one - five third-party files removed from every commit that carried them

```
evidence/audit-in/auditor-1-2026-10-11.md   auditor-2   auditor-3   auditor-4
evidence/audit-in/CROSS-AUDIT-SUMMARY-2026-10-11.md
```

Applied with `git filter-branch --index-filter 'git rm -r --cached --ignore-unmatch <the five paths>' 1b4abc6..main`.
Verification rather than intent: `git log --name-only 1b4abc6..main` returns **0** matches for those paths, and
`git diff --stat backup/pre-history-fix-20261012 main` was **empty** after the pass - the tree at the tip is
byte-for-byte the tree it started from, minus files that were already deleted from it, so nothing else moved.

Why exactly these five: they are third-party text. The repository publishes what this seat measured and what it
judged; it does not publish other people's working directories. Those files carry 21 absolute host paths, four
of which this project's own leg grades FATAL under `HOSTROOT`/`LOGIN`, and each reviewer's scratch layout -
rule 7 of `docs/AUDIT-KIT.md` asked auditors to redact precisely that, and four did not. The adjudication of
everything they raised survives in `evidence/audit-in/ADJUDICATION.md`: claim, command, reading, disposition,
in this seat's words, with no host path in it. The files themselves are held unedited in the private register
beside the repository, and the pre-rewrite tip is kept in the local branch
`backup/pre-history-fix-20261012`, so the act is reversible on this machine.

## Pass two - the same needles were still inside commit messages

Measuring the result before pushing found them: a reviewer's workspace path, a user-profile root, and two
reviewer seat names. Removing five files while publishing the messages that quote those paths would have kept
the letter of option A and defeated its point, so a second filter ran over the same unpushed range,
`--msg-filter`, replacing exactly these strings and touching nothing else - no rewording, no reordering, no
date change:

```
<reviewer workspace path>       -> "<the reviewer's own workspace file, path withheld>"
<cross-check file path>         -> "<the cross-check file, path withheld>"
<private register path>         -> "<the private register, path withheld>"
C:\Users...                  -> "<a user profile root>"
two reviewer seat names          -> "the kit review" / "the cross-check seat"
```

A scan of every message in `1b4abc6..main` for those needles now returns **NONE**. The pseudonymous labels
`auditor-1` through `auditor-4` are kept deliberately: they carry no host information, they are how the
adjudication table stays traceable to a specific packet, and removing them would delete accountability rather
than a path.

## The final mapping, both passes included

| old (pre-rewrite) | new (now the branch) | subject, unchanged |
|---|---|---|
| `4f144de58555` | `3cf68ffc1398` | An audit kit for outside reviewers, written so it can be a |
| `10b18b92fefd` | `4977136dcf74` | The audit kit's own commit message carried the wrong lag: |
| `dc44b8885a30` | `eccfea594ab4` | The audit kit names a gap the reviewer will hit first, and |
| `639a5fcc62f2` | `ee215c377d93` | A leg for the boundary the existing legs could not see: th |
| `304bc66fdf4c` | `c64ba5dff207` | The gate artifact carries only its own write timestamp, an |
| `c2de04ee557c` | `a8dc501a530f` | Four audit packets and their cross-summary land in the int |
| `31fbb839bf90` | `b041dd5da0e7` | The audit batch is adjudicated: four reviewers landed on o |
| `18d6e84f15be` | `b01a587be428` | Host-bound values move into their own face, so the reprodu |
| `038899e45b92` | `5ac3c0c733af` | The prose follows the instrument: four reviewers' red is n |
| `e14869aec07c` | `1ca66fcc08f5` | Three faces carry nothing but their own generation stamps, |
| `3334ece48ad9` | `036cd323f007` | Seal revision 4: the producer field describes the lane, no |
| `cae4715a2f8d` | `6d15c6ca7eca` | Roles becomes a constraint table, the reviewer packets lea |
| `da01f07cf86b` | `722c3343b6d7` | The missing half of the last commit, named face by face, b |
| `75ceaeeaab47` | `c33c0726763e` | The parity reading da01f07 promised, taken after it landed |
| `c78e1392237b` | `864a738023ed` | The version leg caught its own fixture, and the fixture is |
| `1354410e3ae3` | `335fb1e85415` | The audit kit was told to hide the studio's address and ca |


<!-- the left column lists ids that deliberately no longer resolve on this branch; a sweep that repoints
stale ids must skip this table, because its purpose is to record what was replaced -->

Sixteen commits. Every left-hand id resolves only through this table or the backup branch; the right-hand column
is what `git log` shows. The references that pointed at left-hand ids inside faces were rewritten to the
right-hand ones (`evidence/S11/DELIVERY-RECEIPT-20261011.md`, `evidence/audit-in/ADJUDICATION.md`,
`evidence/S11/parity-after-fix-20261012.md`, and the generated `docs/evidence.md` by regenerating it), which is
a forward correction of a reference, not a rewriting of a claim: each corrected sentence still asserts what it
asserted, about the commit that still exists under its new name.

## What this rewrite does not do

**It un-publishes nothing.** The published tip is `1b4abc6` and is untouched by both passes, so everything
already out there stays out there: the 1,150 occurrences of the retired producer key in the result faces, the
role table's persona names, the S00 DoD report's studio vocabulary, and the commit messages that named seats and
lanes before today. `python ci/process_leak_scan.py --repo-root .` still reads
`RETIRED:1143 IDENTITY:1134 HOSTROOT:14 LOGIN:18` and will stay red until the six lanes re-emit and `SG-F9`
clears the narrative faces - the rewrite is not a way to make that number look better, and nothing on this page
claims it is.

**It is not the beginning of routine history editing.** The condition that made it defensible is narrow and
should be restated each time someone reaches for it: nothing in the rewritten range had ever been pushed, the
backup branch and the private register hold every byte that was removed, the tree at the tip is unchanged, and
the owner ordered it in writing. Any future rewrite that fails one of those four tests is a different act and
comes back to the owner first.
