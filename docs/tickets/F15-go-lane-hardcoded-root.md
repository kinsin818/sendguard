# F15 - the go lane's runner verifies and writes a *different* checkout, hardcoded

Opened 2026-10-12 by the local that owns `ci/`, during F8's six-lane re-emit. This is the most consequential
finding of the re-emit and it was found by my own hand, because I ran the harness before reading where it
writes.

## The defect, with the line

`impl/go/main.go:44`:

```go
	repo      = `D:\local-dir`
```

The lane's `run` and `verify` modes both resolve `spec/`, `results/` and `evidence/` under that constant. This
repository lives at `D:\work\session-token`; `D:\local-dir` is a **second checkout of the same project that
the project rules declares read-only evidence for this local** (no checkout, reset, clean, stash or write). The
constant predates the re-emit and is not a scratch directory, an output path or a caller-supplied root - it is the
project root, written into the source of one lane.

## What it did, measured

```
python - <<PY   # read-only inspection of the other tree; nothing in it was reverted or restored
cd /d/sendguard && git status --porcelain -uall | wc -l            -> 254
git rev-parse HEAD                                                  -> 776b92e5eb23066d340d92aca017a10de5afa198
mtimes of the modified tracked faces, bucketed by hour:
   129  2026-10-12 15     <- my `go run . run all`, this session
   121  2026-10-10 23     <- pre-existing, before I touched anything
     3  2026-10-10 22     <- pre-existing
PY
```

So: **129 tracked faces in the read-only tree were rewritten by my run**, on top of 124 faces that tree already
carried modified from 2026-10-10 (not mine). HEAD did not move; no commit was made there; nothing was deleted. The
rewritten faces are `results/go.windows.go1.23.5/*.json` plus one `evidence/judgement/defects/sample-corruption.json`
whose only change is a `note` field appended by that older runner.

**No revert was attempted here.** That tree is not this local's to restore, and a `git checkout <ref> -- path`
there would also rewrite line endings (autocrlf), which is a second defect on top of the first. Both faces are
reported; restoration belongs to whoever owns that tree.

## The second half of the defect, which is worse for the exhibit

`go run . verify` printed:

```
HASH-OK   spec/schema.json    f387ec4bc80a...
VERIFY PASS: frozen artifacts intact
```

while this repository's `spec/schema.json` hashes to `c1a5097ce4a7...` on disk, in `git show HEAD:` and in the
sealed table of `spec/FROZEN.md` (freeze revision 4). The verifier is not wrong about the tree it reads - it is
reading **the other tree**, whose schema is at the pre-F8 digest. A lane whose `verify` passes against a stale
checkout is a lane that reports the contract intact while the contract it is shipped against has moved. This is
the same class as `M10` (an instrument whose green side depends on the host) one level deeper: the green side here
depends on *which directory the source names*.

## Acceptance criteria

1. `repo` is derived, not hardcoded: `--repo` flag (required, refused if absent) defaulting to the directory the
   runner is invoked from, so `python ci/... ` style callers name the tree - the rule already in
   `docs/AUDIT-KIT.md` and enforced for the legs ("an instrument may not create a directory at a drive root, and
   the caller supplies the location"). The string `D:\local-dir` must not appear anywhere in `impl/` afterwards,
   with the grep printed and its `rc=0` asserted;
2. both `run` and `verify` print `repo=<resolved absolute path>` on every invocation, so a future reader can see
   which tree answered;
3. a two-sided arm in the lane's own self-check (`impl/go/rederive/selfcheck.py` or a Go test): planted - a runner
   pointed at tree A must not report a frozen artifact of tree B as verified, demonstrated by asserting the
   printed `repo=` equals the caller's argument and by refusing an absent `--repo` with a non-zero rc; green - a
   correctly named root still verifies;
4. re-run the lane against **this** repository, and the go face's 154 records in `results/go.windows.go1.23.5/`
   re-emit here (they are currently the largest single block of `RETIRED` residue in this tree, 154 of 577);
5. the four gate readings unchanged (`verdict_disagreements=54`, `verdict_identical_cells=24/44`,
   `cells_fully_recorded_and_identical=4`, `verdict_not_recorded_pairs=121`), and `RETIRED` for this repository
   dropping by the go1.23.5 block with the count printed before/after;
6. whoever owns `D:\local-dir` is told, in one row, which 129 faces this session rewrote and that no revert was
   attempted. The list is reproducible from `git -C /d/sendguard status --porcelain -uall` filtered to mtimes in
   the 15:00 hour of 2026-10-12.

## Do not

- Do not revert, restore, clean or stash anything inside `D:\local-dir` from this local. Report both faces.
- Do not delete the 129 modified faces or the untracked note in this repository (`impl/python/sg_restamp_note.txt`,
  mtime 2026-10-11 13:08, another lane's work note carrying a host profile path, untracked so the leak leg cannot
  see it). project rule.
- No history rewriting, no `spec/` edit, no bucket change in the gate.

## Allowed surface

`impl/go/main.go` (the `repo` constant, its two entry modes, and its prints), `impl/go/rederive/*` if it shares the
constant, the lane's self-check, and the acceptance row in `evidence/closing/`.

## Clock

24 h from dispatch. Queue position: **in front of** the remaining F8 residue work, because every later go run
repeats the breach until this lands.

## Landed 2026-10-12, same session

Criterion 1: the literal is gone; `resolveRepo()` takes `-repo`/`--repo` or walks up to a directory carrying
`spec/FROZEN.md`, and refuses with `rc=2` (capture in `evidence/closing/readonly-tree-contamination-20261012.md`).
Criterion 2: `repo=` prints on every invocation, parent and child. Criterion 3: seven arms in `impl/go/root_test.go`
- planted false tree must fail, this repository must pass, foreign `-repo` refused, no contract root refused,
walk-up lands above the module directory, and the source-carrying-no-checkout-literal arm. Criterion 4: the
versioned go face re-emitted here (129 records rewritten in this repository; `implementation_id=go-port`), and the
29 records the current runner no longer produces are named in the acceptance correction. Criterion 5: the four
readings unchanged. Criterion 6: the 129 faces in the other tree are listed by name in the contamination record,
with no revert attempted.

One thing this ticket did **not** predict and must record: removing the hardcoded root exposed a second defect of
the same family - the child process computed its results directory from that same variable, empty in the child, so
records went to a path relative to the operator's cwd. 128 files landed outside the repository before that was
caught; they were moved aside, not deleted, and the fix is the child inheriting `--repo` and refusing without it.
