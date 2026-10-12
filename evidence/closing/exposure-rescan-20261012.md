# Five-class exposure re-scan of the current published tree, 2026-10-12 evening

Ordered as "对当前公开树复扫五类，各报计数 + 剩余点名". Three passes, because the first two were mine and one of
them was wrong in a way worth recording: a wide needle set counted ordinary English and a sealed contract field as
exposure (the word `seat`, 1,057 lines; `attribution_layer`, 629 lines - 66 of them inside `spec/`, where it is a
**field name the contract requires**). Those are separated below, not folded into a headline number.

Every count is from the committed blobs, not the working copy: faces are read with `git show HEAD:<face>` over the
list printed by `git ls-files -z` (`tracked_faces=1209`, rc=0), and the leak classes use the leg's own
`scan_face()` plus the single `route()` function, so this is the leg's arithmetic and not a second opinion.

## Class 1 - the retired producer key (the pre-SG-F8 name, defined in `docs/tickets/SG-F8-public-interface-process-metadata.md`)

| measure | value | command |
|---|---|---|
| occurrences of that key in the committed tree | 471 lines in 262 faces | `python` over `git show HEAD:<face>` calling `scan_face` |
| routed **fatal** (published faces) | **458** | same, `route()` |
| the six canonical faces | **0** - purged today by each lane's own emitter | `face_preflight`/per-face histogram in `SG-F8-acceptance.md` |

Residues, named with their reason:

| block | lines | why it stands |
|---|---|---|
| `results/python/api-entry.windows.json` (89), `results/python.windows.3.14.7.json` (30), `results/python/phantom.windows.json` (5) and the rest of `results/python/**` | 211 | written by `impl/python/sg_python.py`, whose `assert len(cases) == 20` now fails against the sealed spec (it parses 25) - that emitter cannot re-answer its own faces at the current contract without an assertion change, which is not a purge |
| `results/go.windows.go1.23.5/` member-spelled records | 29 | superseded by the rev3 identity spelling; the current runner no longer produces those names |
| `results/node.windows.22.22.2.json` (37) + `results/node/**` (36) | 73 | the node lane's face, declared frozen history under an earlier contract by the dispatch |
| `evidence/recovered/**` (78) and `evidence/S02/**` (25) | 103 | captured runs; this seat does not re-word a capture |
| `evidence/S11/SG-F8-acceptance.md` | 6 | the acceptance face **naming the key it retired**, inside a published prefix. Real self-reference, kept visible; see the note under class 4 |
| `docs/tickets/**`, `ci/**` | 13 | routed to `mentioned`, not fatal: those sentences name the key in order to retire it |

## Class 2 - seat codes and role-roster wording

| token | lines | where, by class |
|---|---|---|
| the parent-directory word (defined in `docs/tickets/SG-F8-public-interface-process-metadata.md`, a rule face) | 449 | 417 distributable (old producer values inside `results/**` and the toolchain captures - the same faces as class 1), 17 rule faces, 15 lane sources |
| the two-letter seat codes retired by that ticket (spelled there, not here) | 468 | 455 distributable, 9 rule, 4 lane - again the same faces: a record stamped `W-PY` is both a class-1 and a class-2 hit, which is why the two counts are not additive |
| window/session ids (the seat codes this ledger carries, not repeated here) | **6** | six published faces name a window id: `evidence/S10/cold-clone-20261011b.md`, `…11c.md`, `evidence/S11/SG-F1-acceptance.md`, `SG-F2-acceptance.md`, `rehearsal-20261011.md`, `evidence/audit-in/ADJUDICATION.md` |
| engine and reviewer names (the six listed in `docs/tickets/SG-F8-public-interface-process-metadata.md` §2) | 56 | 49 distributable - top: the toolchain capture (7), the day-one definition-of-done report (2), plus this ledger's findings file (1) and per-port captures |
| the English word `seat` | 1,057 | reported to be *excluded* as a finding: it is ordinary prose in README, legs and lanes, not a code |

Two honest limits. The 1,365 other 8-hex tokens in the tree are sha fragments and blob ids, and were skipped rather
than counted as identities. And the `W-[A-Z]{2,4}` shape also matches the English "follow-up" - two of the five
hits in the commit-message table below are that false positive, corrected there.

## Class 3 - the order/adjudication mechanism vocabulary

19 matched lines total, and the split is the point:

| token | lines | faces |
|---|---|---|
| `军令` / `终裁` / `总军令` | 7 | 5 distributable, all of them **one face**: `evidence/S00-S00-dod-report.md`, which cites an internal studio document by its Chinese name (and 4 of those 5 lines sit there); 2 in tickets naming what must be neutralised |
| `order S01` | 1 | `spec/FROZEN.md`: "Sealed by the contract owner seat under order S01" - the wording this seat neutralised today away from the persona name; the clause reference remains, and `spec/` is under a standing "not one character" order, so it stays |
| `ruling` | 11 | ordinary English in legs and in the erratum naming the owner's ruling |

So the residual in this class is one evidence face plus a sealed-face clause this order forbids touching. Not "all
clean", not "widespread".

## Class 4 - participant identity, internal project names, absolute host paths

| measure | value |
|---|---|
| internal project names (`DataMaster`, `GOLink`, `Dory`, `Family Hub`, `Anytouch`, `SuperMa`, `LabelFlow`, `polarmem0`, `DataSweeper`) | **0 occurrences in 1,183 tracked text faces** - this class is genuinely clean, and it is the one that would hurt a portfolio reader most |
| `IDENTITY` (a producer value failing the sealed `^[a-z][a-z0-9-]{0,15}-port$` pattern) | 446 lines, **443 fatal**, all in `results/**`, `evidence/recovered/**` and per-port captures - the same faces as class 1, one purge away from zero |
| `LOGIN` (the host profile root quoted in a shipped face) | 1,118 lines, **1,111 fatal** - top faces: `evidence/recovered/node-final-2351/results/node/windows/_audit-manifest.json` (97), `…_audit-truth.ndjson` (97), `…_pyreader-manifest.json` (86), `results/node/windows/_audit-manifest.json` (31), `evidence/S00/toolchain.txt` (13) |
| `HOSTROOT` (this tree's own absolute path quoted inside its own faces) | 424 lines, **409 fatal** - `results/go.windows.go1.23.5/*` (5 each, the go records' scratch and base fields), `evidence/S10/cold-clone-20261011b.md` (3) |
| `TOOLPATH` (a recorded executable or toolchain root - provenance, not a leak) | 8,221 lines, **0 fatal** by design; 136 of them come from `evidence/S11/readonly-tree-contamination-20261012.md` naming 129 faces, which is `SG-F14`'s subject |

One structural finding sits under this class and should not be softened: **a published face cannot name the retired
key without becoming a finding.** `DISTRIBUTABLE` covers `docs/` and `evidence/`, while `mentioned` is reserved for
`ci/`, `docs/tickets/` and `docs/claim-boundary.md`. That is why SG-F8's own acceptance face counts 6 hits against
itself. The right fix is a declaration bound to **(class, face) pairs, printed with its own denominator** - the
shape this project already uses elsewhere - not a widened exemption; it is in the round-9 proposal.

## Class 5 - commit-message wording, split at the published boundary

Boundary taken from the remote, read-only: `git ls-remote --heads github` → `bd0c430`, so `bd0c430` and its
ancestors are public and everything after is local-only.

| range | commits | messages carrying a token | tokens |
|---|---|---|---|
| **published** | 127 | 36 | `SG-F<n>` 28, `W-XX` 6 (2 of which are the word "follow-up" - false positives), `auditor-<n>` 4, `seat-qoder` 3, `qianwen` 1 |
| unpublished (since this morning's push) | 8 | 6 | `SG-F<n>` 6, `auditor-<n>` 1 |

Published messages that carry an identity token, named: `e41b009` (the seat-code mapping table quoted in a commit
message quoting the retired seat-code table with its per-code counts; two further messages embed this tree's absolute
path while documenting a clone experiment). `c4c74be` and `e5055ce` are the "follow-up" matches. **Unchangeable
under this order** - rewriting published history needs a force-push, which is the owner's hand, not mine. The
local-only eight could be cleaned before any next push; this order says no history changes, so they stay and are
counted here instead.
> One more datum, from writing this very face: the pre-flight leg refused the first draft of it because its own section heading spelled the retired key out in order to say what was being counted - the sixth self-naming line became a seventh, and the heading was rewritten to point at the ticket that defines the key instead. The rule is not wrong to fire; the missing piece is a declaration bound to (rule, face), which is round-9 item 4(a) rather than an exemption list.

## The three-tier conclusion the order asked for

1. **Fixed, measured**: the six canonical faces carry no retired key and no non-conforming producer value; a cold
   clone reproduces every lane's verdict fields with zero differences; internal project names are absent from the
   whole tree; the roster/persona table is neutralised; `spec/FROZEN.md`'s seal line names a role, not a persona.
2. **Residue on record, each with its reason and a number**: 211 python-era records behind an emitter whose frozen
   assertion no longer matches the sealed spec; 29 superseded go member-spellings; 103 evidence captures; 73 node
   faces frozen by contract; 6 window ids in published evidence; 56 engine/reviewer-name lines (49 in published
   faces); 1,111 profile-root lines and 409 tree-root lines inside shipped records and captures; the DoD evidence
   face naming an internal studio document; 6 self-naming lines in SG-F8's acceptance face; 13 rule-face lines that
   are the sentences doing the retiring.
3. **Cannot be changed by this seat**: 36 published commit messages including three that carry identity tokens, and
   the `order S01` clause inside `spec/FROZEN.md`.

The measuring scripts are in the working area beside the repository (`exposure_scan.py`, `exposure_pass2.py`,
`exposure_pass3.py`); re-run them at any tip and the numbers move with the tree, which is the whole point of
printing the commands with the counts.
