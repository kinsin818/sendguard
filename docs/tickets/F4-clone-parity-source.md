# F4 - make `ci/clone_parity.py` able to verify a source other than this working copy

Maintainer: this machine, which owns `ci/`. Written 2026-10-11 15:26 +0800, from work already done by hand.

## Why

Since the push, the sentence a buyer cares about is "the **public** repository reproduces". The standing leg only
knows how to clone `REPO`, so at 15:24 the public check had to be done with a throwaway script beside the
repository - which then got two things wrong that the leg would not have got wrong (an incomplete timestamp
pattern, and a second verdict parser). The public result is recorded in
`evidence/closing/public-clone-20261011.md`; this ticket exists so the next such check is one command instead of one
riskier improvisation.

## Deliverable

`python ci/clone_parity.py --source <url-or-path> --scratch-root <caller-named-dir>`:

- `--source` defaults to the current behaviour (clone this repository) so nothing that runs today changes;
- the tip of the source is read from the source (`git ls-remote` for a URL, `git rev-parse` for a path), never
  from a cached remote-tracking ref - two documents in this repository asserted "nothing has been pushed" because
  they trusted the cached ref;
- it refuses, with rc=3 and before writing anything, when the source is a local path that does not exist, or when
  the source tip differs from the tree it is being compared against (that difference is the whole point of the
  check and must never be smoothed over);
- `--no-local` is passed only when the source is a local path, because it means nothing for a URL.

## Also in scope

The leg's arm count is a hardcoded literal (`print("arms=12 passed=%d" % (12 - len(errs)))`), which is the shape
that drifted twice today. Give it the same self-counting guard `ci/coverage_report.py` gained: collect the
`selftest A<n>` labels that actually ran and fail when the published count differs, counting the guard's own label
explicitly because Python evaluates the condition before the label can be registered.

## Acceptance criteria

1. `python ci/clone_parity.py --selftest` - arms all pass, and the printed count equals the distinct labels run;
2. a new red-side arm: a source path that does not exist returns rc=3 and creates no directory;
3. a green-side arm: a URL-shaped source is recognised as remote, so `--no-local` is not claimed where it is inert;
4. one live run against `https://github.com/kinsin818/sendguard` reporting `OUTCOME=CLEAN` with the same
   identical/declared counts as `evidence/closing/public-clone-20261011.md` section 3;
5. no face under `results/`, `spec/` or `impl/` moves, and nothing under `D:\local-dir` is touched at all.

## Landed, 15:34 +0800

All five acceptance criteria are met in `ci/clone_parity.py` (commit following this one): `--source` defaults to
this repository, the tip is read from the source (`ls-remote` for a URL, `rev-parse` for a path, and a path that
does not exist is refused with rc=3 before anything is cloned), a differing tip is refused rather than smoothed
over, `--no-local` is passed only for a local source, and the arm count is now `SELFTEST_ARMS` with the
self-counting guard that `ci/coverage_report.py` carries. `--selftest` reads `arms=14 passed=14`.

Live run against the public repository, which is what the ticket was opened for:

```
clone| D:\work\sg-public\parity-1 (created) source=https://github.com/kinsin818/sendguard head=02807a92edd2 status_before=0 pipeline_rc=1
declared| docs/evidence.md - 1 line(s) inside the declared shape: - repository commit: `38446a01d551` (working tree carries 15 uncommitted faces at generation time). That is the HEAD thi
tool| names=5 fields_compared=55 differing=0
OUTCOME=CLEAN faces_compared=12 identical=11 declared=1 differing=0 missing=0 clone=D:\work\sg-public\parity-1 source=https://github.com/kinsin818/sendguard
```

One consequence worth noting: because the deliverable comparison runs between this tree and the clone, pointing
`--source` at the public URL strengthens it - the 55 fields are now local-versus-public-clone, not
local-versus-clone-of-local.

## Limits to state in the face, not only here

A public-clone run proves the public bytes and this machine's answers. It does not prove CI's conclusion (unread
without a token) and it does not produce macOS or Linux result rows.
