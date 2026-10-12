# The unpushed range was rewritten so that the reviewer packets never enter the published set

Ordered by the owner on 2026-10-12 (his option ①), executed at 11:0x host clock. This face exists because a
history rewrite that is not documented is indistinguishable from a cover-up, and the distinction has to be
readable from the tree.

## What was removed, and from where

Five files - four audit packets and one cross-summary - were dropped from **every commit that ever carried them**
inside the unpushed range `1b4abc6..main`:

```
evidence/audit-in/auditor-1-2026-10-11.md   auditor-2   auditor-3   auditor-4
evidence/audit-in/CROSS-AUDIT-SUMMARY-2026-10-11.md
```

They were removed with `git filter-branch --index-filter 'git rm -r --cached --ignore-unmatch …' 1b4abc6..main`,
which rewrites commits, not working files. Verification, not trust: `git log --name-only 1b4abc6..HEAD` now
returns **0** matches for those paths, and `git diff --stat backup/pre-history-fix-20261012 HEAD` is **empty**, so
the tree at the tip is byte-for-byte the tree the rewrite started from. Nothing else changed.

## Why these files, and not the rest

They are **third-party text**. The repository publishes what this seat measured and judged; it does not publish
other people's working directories. Their contents carry 21 absolute host paths (four of which this project's own
leg grades `HOSTROOT`/`LOGIN` FATAL) and each reviewer's scratch layout, and rule 7 of `docs/AUDIT-KIT.md` asked
auditors to redact exactly that - four of them did not, and I will not publish the omission on their behalf. The
adjudication of every finding they raised is **not** lost: `evidence/audit-in/ADJUDICATION.md` carries each claim,
each command, each reading and each disposition, in this seat's own words, and it contains no host paths.

Their absence from the published set is not their destruction. All five are held, unedited, in the private
register at `AUDIT-IN-PRIVATE` beside the repository, and the pre-rewrite tip is kept in the local branch
`backup/pre-history-fix-20261012` (`1354410`) so the rewrite itself is reversible.

## What a rewrite does not do

It does not un-publish anything. The published tip is `1b4abc6`, untouched by this operation, and everything
already in it - including the 1,150 occurrences of the retired producer key, the role table with its persona
names, and the commit messages that name seats and windows - stays published. `RETIRED:1143 IDENTITY:1134`
remains in the leak leg's reading and clears only when the six lanes re-emit under `SG-F8`. This rewrite removed
content that had **never** left this machine.

## Old to new, all sixteen commits

| old | new | subject |
|---|---|---|
| `4f144de58555` | unchanged | An audit kit for outside reviewers… |
| `10b18b92fefd` | unchanged | The audit kit's own commit message carried the wrong lag… |
| `dc44b8885a30` | unchanged | The audit kit names a gap the reviewer will hit first… |
| `639a5fcc62f2` | unchanged | A leg for the boundary the existing legs could not see… |
| `304bc66fdf4c` | unchanged | The gate artifact carries only its own write timestamp… |
| `c2de04ee557c` | `75504fbf26ec` | Four audit packets and their cross-summary land in the intake directory |
| `31fbb839bf90` | `32874649c852` | The audit batch is adjudicated… |
| `18d6e84f15be` | `aed3a72cd7b3` | Host-bound values move into their own face… |
| `038899e45b92` | `1181c3b91724` | The prose follows the instrument… |
| `e14869aec07c` | `4621cf5bedfc` | Three faces carry nothing but their own generation stamps… |
| `3334ece48ad9` | `719758a07ffd` | Seal revision 4: the producer field describes the lane… |
| `cae4715a2f8d` | `1ea6ec222fdf` | Roles becomes a constraint table… |
| `da01f07cf86b` | `930191e1ff1e` | The missing half of the last commit… |
| `75ceaeeaab47` | `dbfd98cf3e60` | The parity reading da01f07 promised… |
| `c78e1392237b` | `ee77a30f3c5c` | The version leg caught its own fixture… |
| `1354410e3ae3` | `8c6b1e6f5873` | The audit kit was told to hide the studio's address… |

Eleven commits moved because they carried at least one of the five paths, or sat behind one that did. Five are
unchanged because they never touched those files.

## Known breakage caused by this, named rather than hidden

Eight references in four faces quoted pre-rewrite ids (`docs/evidence.md` is generated and re-points itself; the
rest are `evidence/S11/DELIVERY-RECEIPT-20261011.md`, `evidence/S11/parity-after-fix-20261012.md`,
`evidence/audit-in/ADJUDICATION.md`). Several commit messages also name ids that now resolve only through the
mapping above. Each prose reference is corrected forward in the commit that lands this face, and the old ids are
not erased from the messages that wrote them - a message that named `da01f07` said something true at the time it
was written, and the mapping is the fix, not a rewrite of the claim.
