# S11 - fitness probe of `ci/clone_parity.py`: the gate must refuse a face that does not reproduce (2026-10-11)

Run by the delivery seat at 14:24 +0800. `ci/clone_parity.py` was committed at `8900037` after a green reading
(`OUTCOME=CLEAN faces_compared=12 identical=11 declared=1 differing=0 missing=0`). A gate that has only ever been
seen agreeing with itself is the thing this repository has been catching in itself all day, so the red side of
its plumbing was exercised deliberately - and without putting a false face into history.

## Method, and why no commit carries the tampered file

1. `git show 8900037:docs/coverage.md` into memory, change one digit (`44` to `45`) - the work tree is never
   touched.
2. `git hash-object -w` the tampered text, `git read-tree HEAD` into a throwaway index
   (`.git/parity-red-index`, via `GIT_INDEX_FILE`), `git update-index --cacheinfo` the tampered blob over that
   one path, `git write-tree`, `git commit-tree` with a message that says it is a fitness probe.
3. Put that commit on a temporary branch `parity-red-probe` - never merged, never checked out into the seat's
   work tree - and `git worktree add --detach` it into `D:\sendguard-work\parity-red-worktree`.
4. Run `python ci/clone_parity.py --scratch-root D:\sendguard-work\parity-red-scratch` from that work tree, so
   the leg's own HEAD is the probe commit while the generator that runs inside its clone is unchanged. The clone
   must therefore regenerate `44` where the commit carries `45`.
5. `git worktree remove`, `git branch -D`, delete the two throwaway `.git` files. Nothing in the seat's history
   changes; the probe commit becomes unreachable and the branch is gone.

The scratch clone itself is left on disk: this leg never deletes, and neither does the probe.

## Output

```
HEAD|890003736e4b2a4832d63fd4d5042b2047d57ae9
probe commit|75710f8fc2940bddbc550760a90425c38794cc90 (reachable only through the temp branch created next)
gate rc=1  (1 = it refused a face that does not reproduce)
   gate|clone| D:\sendguard-work\parity-red-scratch\parity-1 (created) head=75710f8fc294 status_before=0 pipeline_rc=1
   gate|declared| docs/evidence.md - 1 line(s) inside the declared shape: - repository commit: `8f04c391ac49` (working tree carries 13 uncommitted faces at generation t
   gate|  face| docs/coverage.md: 2 line(s) differ, line count 70 vs 71; first: HEAD 'answered everything and matched. **Cells compared: 45. Verdict field-cells possibl
   gate|OUTCOME=RED faces_compared=12 identical=10 declared=1 differing=1 missing=0 clone=D:\sendguard-work\parity-red-scratch\parity-1
   gate|A clone that reads a different generated face than the commit carries is not a reproduction; docs/journey.md 2.18 is why this leg exists
```

The digit I changed is visible in the quoted HEAD line (`Cells compared: 45`), which is the clone's *checked-out*
blob, while the face the clone regenerated says 44 - the gate named the file, the line count, and both texts
rather than reporting a bare failure.

Two things the run also demonstrates without being asked: the declared exception for `docs/evidence.md` still
fires on a real commit (`declared=1`, the line quoted), and the pipeline verdict inside the clone is read as
`pipeline_rc=1` without being mistaken for the parity result - the equality gate is RED by design, and the parity
leg does not launder that into a tool failure.

## Cleanup, verified rather than asserted

```
cleanup| worktree remove rc=0
cleanup| branch -D parity-red-probe rc=0 Deleted branch parity-red-probe (was 75710f8).
cleanup| removed parity-red-index
cleanup| removed parity-red-blob.txt
verify| worktrees now:
   D:/sendguard-work/seat-qoder 8900037 [main]
verify| seat HEAD|890003736e4b2a4832d63fd4d5042b2047d57ae9 status lines=1
   status|?? impl/python/sg_restamp_note.txt
verify| temp branch present? rc=0 output=''
```

The one remaining status line is the Python lane's own untracked note, which was dirty before this probe and is
left alone. `git worktree list` shows a single work tree again, and the temp branch reads empty.

## First attempt, kept because it is the kind of mistake this project keeps making

The probe was tried once before, at 14:23, against a probe commit built on `9fd8aa3` - which is the last commit
*before* `ci/clone_parity.py` was tracked. The detached work tree therefore contained no
`ci/clone_parity.py` to run, and the leg reported nothing:

```
gate rc=2
   gate|python.exe: can't open file 'D:\\sendguard-work\\parity-red-worktree\\ci\\clone_parity.py': [Errno 2] No such file or directory
```

rc=2 is outside the leg's documented exit set, so it is a broken instrument reading and not a result; the cleanup
branch ran and removed the worktree and branch, leaving nothing behind, and the probe was re-issued on top of the
commit that actually carries the leg. The general form: a probe must be built from a revision that contains the
thing under test, or it measures the absence of the tool instead of its behaviour.
