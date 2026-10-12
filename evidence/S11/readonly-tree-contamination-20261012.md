# Contamination record - this session rewrote tracked faces in the read-only tree, and nothing was reverted

Recorded 2026-10-12 by the seat that owns `ci/`. The owner's ruling the same day was explicit: **do not restore
that tree, record the contamination only.** This file is that record. It changes nothing outside this repository,
and it is not a fix - the fix to the cause is `docs/tickets/SG-F15-go-lane-hardcoded-root.md`, which landed after
this event.

## What happened, in one paragraph

To re-emit the go lane's versioned data face, this seat ran that lane's own runner. It did not first read where
the runner writes. The runner resolves its project root from a string written into its source - `impl/go/main.go`
carried `repo = <a checkout path>` - and that path is a **second checkout of this project**, `D:\sendguard`, which
the standing order declares read-only evidence for this seat (no checkout, reset, clean, stash or write there). The
run completed normally, printed `go-port run complete`, and rewrote tracked faces inside that tree.

## Measured, from that tree's own status, read-only

| item | reading |
|---|---|
| its HEAD before and after | `776b92e5eb23066d340d92aca017a10de5afa198` - unchanged; no commit was made there |
| tracked faces rewritten by this session | **129**, all of them under `results/go.windows.go1.23.5/` |
| tracked faces already modified before this session | 124 (mtimes in the 2026-10-10 23:xx and 22:xx buckets) - **not** this session's work |
| its `git status --porcelain -uall` line count | 254 before this session's run, 254 after (the 129 newly written are inside that set) |
| files deleted there | 0 |
| revert attempted | **none** - that tree is not this seat's to restore, and `git checkout <ref> -- path` would additionally rewrite line endings under autocrlf, which is a second defect laid on the first |

Two corrections to what this seat said earlier the same day, recorded here rather than quietly edited:

1. the commit message of the six-lane re-emit attributed a modification of
   `evidence/S02/defects/sample-corruption.json` to this run. It did not. That file's mtime falls in the
   2026-10-10 buckets, so it belongs to the 124 faces that were already dirty. The run's footprint is exactly the
   129 names below, one directory, nothing else.
2. that message also implied the frozen-contract check that printed a stale digest was part of the same invocation.
   It was a separate invocation of the same broken root, and it is wrong for a different reason: the digest it
   printed (`f387ec4b...`) belongs to the **other** checkout's `spec/schema.json`, which sits at an earlier contract
   revision than the one this repository ships (`c1a5097c...`, freeze revision 4, `spec/FROZEN.md`).

## The 129 faces, named

The list is this seat's reading of that tree's `git status` filtered to the hour this session ran, captured to a
file outside the repository and inserted by name - not retyped.

```
results/go.windows.go1.23.5/T01__os_Create.json
results/go.windows.go1.23.5/T01__os_Mkdir.json
results/go.windows.go1.23.5/T01__os_OpenFile.json
results/go.windows.go1.23.5/T01__os_WriteFile.json
results/go.windows.go1.23.5/T02__os_Create.json
results/go.windows.go1.23.5/T02__os_Mkdir.json
results/go.windows.go1.23.5/T02__os_OpenFile.json
results/go.windows.go1.23.5/T02__os_WriteFile.json
results/go.windows.go1.23.5/T03__os_Create.json
results/go.windows.go1.23.5/T03__os_Mkdir.json
results/go.windows.go1.23.5/T03__os_OpenFile.json
results/go.windows.go1.23.5/T03__os_WriteFile.json
results/go.windows.go1.23.5/T04__os_Create.json
results/go.windows.go1.23.5/T04__os_Mkdir.json
results/go.windows.go1.23.5/T04__os_OpenFile.json
results/go.windows.go1.23.5/T04__os_WriteFile.json
results/go.windows.go1.23.5/T05__os_Create.json
results/go.windows.go1.23.5/T05__os_Mkdir.json
results/go.windows.go1.23.5/T05__os_OpenFile.json
results/go.windows.go1.23.5/T05__os_WriteFile.json
results/go.windows.go1.23.5/T06__os_Create.json
results/go.windows.go1.23.5/T06__os_Mkdir.json
results/go.windows.go1.23.5/T06__os_OpenFile.json
results/go.windows.go1.23.5/T06__os_WriteFile.json
results/go.windows.go1.23.5/T07__os_Create.json
results/go.windows.go1.23.5/T07__os_Mkdir.json
results/go.windows.go1.23.5/T07__os_OpenFile.json
results/go.windows.go1.23.5/T07__os_WriteFile.json
results/go.windows.go1.23.5/T08__os_Create.json
results/go.windows.go1.23.5/T08__os_Mkdir.json
results/go.windows.go1.23.5/T08__os_OpenFile.json
results/go.windows.go1.23.5/T08__os_WriteFile.json
results/go.windows.go1.23.5/T09__os_Create.json
results/go.windows.go1.23.5/T09__os_Mkdir.json
results/go.windows.go1.23.5/T09__os_OpenFile.json
results/go.windows.go1.23.5/T09__os_WriteFile.json
results/go.windows.go1.23.5/T10__os_Create.json
results/go.windows.go1.23.5/T10__os_Mkdir.json
results/go.windows.go1.23.5/T10__os_OpenFile.json
results/go.windows.go1.23.5/T10__os_WriteFile.json
results/go.windows.go1.23.5/T11__os_Create.json
results/go.windows.go1.23.5/T11__os_Mkdir.json
results/go.windows.go1.23.5/T11__os_OpenFile.json
results/go.windows.go1.23.5/T11__os_WriteFile.json
results/go.windows.go1.23.5/T12__os_Create.json
results/go.windows.go1.23.5/T12__os_Mkdir.json
results/go.windows.go1.23.5/T12__os_OpenFile.json
results/go.windows.go1.23.5/T12__os_WriteFile.json
results/go.windows.go1.23.5/T13__os_Create.json
results/go.windows.go1.23.5/T13__os_Mkdir.json
results/go.windows.go1.23.5/T13__os_OpenFile.json
results/go.windows.go1.23.5/T13__os_WriteFile.json
results/go.windows.go1.23.5/T14__os_Create.json
results/go.windows.go1.23.5/T14__os_Mkdir.json
results/go.windows.go1.23.5/T14__os_OpenFile.json
results/go.windows.go1.23.5/T14__os_WriteFile.json
results/go.windows.go1.23.5/T15__os_Create.json
results/go.windows.go1.23.5/T15__os_Mkdir.json
results/go.windows.go1.23.5/T15__os_OpenFile.json
results/go.windows.go1.23.5/T15__os_WriteFile.json
results/go.windows.go1.23.5/T16__archive_zip.json
results/go.windows.go1.23.5/T17__os_Create.json
results/go.windows.go1.23.5/T17__os_Create__extended_b120_c137.json
results/go.windows.go1.23.5/T17__os_Create__extended_b120_c138.json
results/go.windows.go1.23.5/T17__os_Create__extended_b120_c139.json
results/go.windows.go1.23.5/T17__os_Create__extended_b13_c244.json
results/go.windows.go1.23.5/T17__os_Create__extended_b13_c245.json
results/go.windows.go1.23.5/T17__os_Create__extended_b13_c246.json
results/go.windows.go1.23.5/T17__os_Create__extended_b13_c254.json
results/go.windows.go1.23.5/T17__os_Create__extended_b13_c255.json
results/go.windows.go1.23.5/T17__os_Create__extended_b13_c256.json
results/go.windows.go1.23.5/T17__os_Create__extended_b200_c254.json
results/go.windows.go1.23.5/T17__os_Create__extended_b200_c255.json
results/go.windows.go1.23.5/T17__os_Create__extended_b200_c256.json
results/go.windows.go1.23.5/T17__os_Create__plain_b120_c137.json
results/go.windows.go1.23.5/T17__os_Create__plain_b120_c138.json
results/go.windows.go1.23.5/T17__os_Create__plain_b120_c139.json
results/go.windows.go1.23.5/T17__os_Create__plain_b13_c244.json
results/go.windows.go1.23.5/T17__os_Create__plain_b13_c245.json
results/go.windows.go1.23.5/T17__os_Create__plain_b13_c246.json
results/go.windows.go1.23.5/T17__os_Create__plain_b13_c254.json
results/go.windows.go1.23.5/T17__os_Create__plain_b13_c255.json
results/go.windows.go1.23.5/T17__os_Create__plain_b13_c256.json
results/go.windows.go1.23.5/T17__os_Create__plain_b200_c254.json
results/go.windows.go1.23.5/T17__os_Create__plain_b200_c255.json
results/go.windows.go1.23.5/T17__os_Create__plain_b200_c256.json
results/go.windows.go1.23.5/T17__os_Mkdir.json
results/go.windows.go1.23.5/T17__os_OpenFile.json
results/go.windows.go1.23.5/T17__os_WriteFile.json
results/go.windows.go1.23.5/T18__os_Create.json
results/go.windows.go1.23.5/T18__os_Create__extended_b120_c137.json
results/go.windows.go1.23.5/T18__os_Create__extended_b120_c138.json
results/go.windows.go1.23.5/T18__os_Create__extended_b120_c139.json
results/go.windows.go1.23.5/T18__os_Create__extended_b13_c244.json
results/go.windows.go1.23.5/T18__os_Create__extended_b13_c245.json
results/go.windows.go1.23.5/T18__os_Create__extended_b13_c246.json
results/go.windows.go1.23.5/T18__os_Create__extended_b13_c254.json
results/go.windows.go1.23.5/T18__os_Create__extended_b13_c255.json
results/go.windows.go1.23.5/T18__os_Create__extended_b13_c256.json
results/go.windows.go1.23.5/T18__os_Create__extended_b200_c254.json
results/go.windows.go1.23.5/T18__os_Create__extended_b200_c255.json
results/go.windows.go1.23.5/T18__os_Create__extended_b200_c256.json
results/go.windows.go1.23.5/T18__os_Create__plain_b120_c137.json
results/go.windows.go1.23.5/T18__os_Create__plain_b120_c138.json
results/go.windows.go1.23.5/T18__os_Create__plain_b120_c139.json
results/go.windows.go1.23.5/T18__os_Create__plain_b13_c244.json
results/go.windows.go1.23.5/T18__os_Create__plain_b13_c245.json
results/go.windows.go1.23.5/T18__os_Create__plain_b13_c246.json
results/go.windows.go1.23.5/T18__os_Create__plain_b13_c254.json
results/go.windows.go1.23.5/T18__os_Create__plain_b13_c255.json
results/go.windows.go1.23.5/T18__os_Create__plain_b13_c256.json
results/go.windows.go1.23.5/T18__os_Create__plain_b200_c254.json
results/go.windows.go1.23.5/T18__os_Create__plain_b200_c255.json
results/go.windows.go1.23.5/T18__os_Create__plain_b200_c256.json
results/go.windows.go1.23.5/T18__os_Mkdir.json
results/go.windows.go1.23.5/T18__os_OpenFile.json
results/go.windows.go1.23.5/T18__os_WriteFile.json
results/go.windows.go1.23.5/T19__os_Create.json
results/go.windows.go1.23.5/T19__os_Mkdir.json
results/go.windows.go1.23.5/T19__os_OpenFile.json
results/go.windows.go1.23.5/T19__os_WriteFile.json
results/go.windows.go1.23.5/T20__os_Create.json
results/go.windows.go1.23.5/T20__os_Mkdir.json
results/go.windows.go1.23.5/T20__os_OpenFile.json
results/go.windows.go1.23.5/T20__os_WriteFile.json
results/go.windows.go1.23.5/TAPI-T01__os_Create.json
results/go.windows.go1.23.5/TAPI-T01__os_Mkdir.json
results/go.windows.go1.23.5/TAPI-T01__os_OpenFile.json
results/go.windows.go1.23.5/TAPI-T01__os_WriteFile.json
```

## Why the write is worse than it looks, and what closed it

The same hardcoded root made the lane's contract check meaningless: `verify` compared the other checkout's frozen
files against the other checkout's own `FROZEN.md` and printed `VERIFY PASS: frozen artifacts intact`, while this
repository's sealed `spec/schema.json` digest was different. A reader of that line would have concluded the lanes
were shipped against the contract they were told to satisfy. After `SG-F15`, the same binary behaves like this:

```
$ sg-go verify                                     # invoked where no contract root is above the cwd
ROOT-REFUSED: no spec/FROZEN.md above the directory holding the repository: pass -repo <repository root>; this lane will not guess a checkout
rc=2

$ sg-go verify -repo <this repository>
repo=<this repository, resolved by walking up from the working directory>
HASH-OK   spec/cases.yaml                        8650a1863578...
HASH-OK   spec/schema.json                       c1a5097ce4a7...
(8 rows)  VERIFY PASS: frozen artifacts intact
rc=0
```

Seven arms in `impl/go/root_test.go` cover it in both directions: a planted tree whose frozen face does not match
its own table must make `verifyFrozen()` return an error; this repository must still pass; a `-repo` pointing at a
non-contract directory must be refused; and one arm asserts that no checkout literal is present in the lane's
source at all, which is the shape of the original defect.

A second defect of the same family surfaced while fixing the first, and it is recorded here because a **write**
found it rather than a read: the lane's child process built its results directory from that same root variable,
which was empty in the child, so records were written to `results/...` resolved against the operator's working
directory. That is how 128 files appeared at `a directory beside the repository\`. They were not deleted - the directory
was moved aside to `a directory beside the repository, named for the date of the run\`, outside the repository, reversible, and
named here. The child now inherits the parent's resolved root through `--repo` and exits 2 when it cannot see one,
which is the CLI capture above.

## What still needs an owner's decision

Whoever owns `D:\sendguard` decides what becomes of its 129 newly rewritten faces and its 124 older ones. This
seat will not touch that tree again. If a revert is wanted, it belongs in a ticket to the window that holds it,
with the list above as its scope - and the window that takes it should know that restoring tracked faces there by
`git checkout` changes line endings, so the byte comparison has to name which face it measured.
