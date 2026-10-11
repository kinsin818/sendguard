# Cold-clone verification - 2026-10-11 10:2x +0800

The repository's central outward promise is "clone it and re-run it". That was checked from a stranger's
tree rather than asserted, because the seat that wrote the gates also owns their inputs and a green run in
the author's own working tree proves less than it looks like it proves.

## What was done

```
git clone --no-local D:/sendguard-work/seat-qoder stranger-clone      # a real clone, not a copy
cd stranger-clone
git status --porcelain -uall | wc -l                                 # 0
python ci/selftest.py --scratch-root <a different directory>         # arms=18 passed=18 failed=0
python ci/equality.py                                                # OUTCOME=RED ... 24/44 clean
python ci/triangle.py                                                # OUTCOME=CLEAN, rows=66, live ports=6
```

## The spec lock, computed from the clone's own bytes

`spec/FROZEN.md` publishes sha256 for eight artifacts. Recomputed here from `git cat-file blob HEAD:<file>`
inside the clone - the clone's own object store, not the author's disk:

| artifact | blob digest | matches the published table |
|---|---|---|
| `spec/cases.yaml` | `8650a1863578…` | yes |
| `spec/gate.md` | `6a3894573214…` | yes |
| `spec/canonical.md` | `f3fe3122c131…` | yes |
| `spec/attribution-tree.md` | `286f81914c73…` | yes |
| `spec/validate.py` | `66f8c0035981…` | yes |
| `spec/schema.json` | `52abbc86c889…` | yes |
| `spec/cell-identity.md` | `5c87c7c66cfe…` | yes |
| `spec/cells-required.json` | `ed8a8a29c0ee…` | yes |

8 rows, 0 mismatches. This is the property the `.gitattributes` `-text` rule exists to keep: an earlier
reading hashed the *checked-out* files and reported the lock broken on 384 of 388 files, because
`core.autocrlf` rewrites line endings on checkout (see `spec/cell-identity.md` §7: every digest in this
repository is a blob-face digest, and `ci/blobhash.py` is the only way to compute one).

## The verdict reproduces byte for byte

The per-port digests over the 24 cells that carry no verdict conflict, compared between the author's tree
and the cold clone:

```
csharp      5208415301dcb1c2      go  83f176b960ee24e5      java e9a665f371462bd5
python      beb7b1b5786b253d      rust 1d5473c51addbaf8      typescript 6173d3b5a5ed1edc
OUTCOME=RED verdict_disagreements=54 verdict_identical_cells=24/44 ... required_cells_missing=0
```

`diff` of the two runs: empty. Same verdict line, same six digests, from a tree that had never been touched
by any port window.

## What this does not prove

- It does not make the macOS or Linux rows exist. Those need CI, and pushing this line to the public
  repository is the owner's act (the clone's `origin` is a local path, and the published repository is
  currently 44 commits behind this line, not ahead).
- It does not make the deliverable double-clickable on a machine that did not build it: the tool is unsigned,
  and SmartScreen behaviour is unmeasured. `docs/claim-boundary.md` carries that row.
- It does not make the 54 verdict conflicts agree. The claim being tested is that six independent ports
  produce the same checker verdict *where the answer is the same*; the 20 conflicting cells are the product,
  published by name in `docs/STATUS.md` and `docs/matrix.md`, not smoothed.
- Reproducibility was tested on the same machine, same Windows build, one file system. A clone on another
  machine is the test that has not been run, and it is the one CI would give us.
