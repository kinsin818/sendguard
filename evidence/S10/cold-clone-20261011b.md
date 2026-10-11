# Cold-clone verification, second run - after the gate learned to count silence

Author: the delivery seat (window `d9242392`). Host clock 2026-10-11 12:12 +0800.
Repository under test: `D:\sendguard-work\seat-qoder` at HEAD `578ba56` ("Make silence a counted fact").
Clone: `D:\sendguard-work\cold-2`, made with `git clone --no-local file:///D:/sendguard-work/seat-qoder cold-2`
(`clone_rc=0`, `git status --porcelain` = 0 lines in the clone). Scratch root for the self-test:
`D:\sendguard-work\cold-st` (passed in by the caller; the instrument picks no landing place, and it is not a
drive root).

## What ran in the clone, and what it said

| command (in the clone) | rc | reading |
|---|---|---|
| `python ci/selftest.py --scratch-root ../cold-st` | 0 | `arms=21 passed=21 failed=0` `OUTCOME=PASS` |
| `python ci/lint.py --repo-root . --selftest` | 0 | `lint: OK arms=18 passed=18 workflows=1 runner_labels_checked=4 tracked=1120,untracked=0 names_checked=1120 json_scanned=949` |
| `python ci/validate_cells.py --selftest` | 0 | `arms=15 passed=15` - the clone's HEAD carries the 15-arm version; the work tree has 20 (see "the two trees differ" below) |
| `python ci/validate_cells.py` | 0 | `wrote docs/cell-validation.md bytes=2657 invalid=56 missing_faces=0` |
| `python ci/equality.py` | 1 | `OUTCOME=RED verdict_disagreements=54 verdict_identical_cells=24/44 cells_fully_recorded_and_identical=0 verdict_not_recorded_pairs=127 verdict_pairs_recorded=2266/2640 probe_cells_differing=29 unpinned_input=0 cells_excluded=0 channel_abstentions=13 truncated_values=2 required_cells_missing=0` |

rc=1 from `ci/equality.py` is the measurement (ports disagree), not a crash; every leg printed its own
denominators, and no leg was piped into another command, so no exit code was laundered.

## The two trees differ, and the difference is the point

| quantity | clone (HEAD `578ba56`) | work tree | reading |
|---|---|---|---|
| cells compared | 44 | 44 | same |
| verdict disagreements | 54 | 54 | **same - the finding reproduces from history** |
| cells with no verdict conflict | 24 | 24 | **same** |
| verdict field-cells blank | 127 | 121 | differ |
| cells every port recorded every field on | 0 | 4 | differ |
| conforming cells (`invalid`) | 56 | 0 | differ |

The three differing rows are all TypeScript-lane data, and the reason is written on the work tree: 56 faces
under `results/typescript.windows.x64/` are modified and 7 more are untracked (63 ahead of HEAD), and
none are committed, so HEAD still holds that
port's 11:35 face set. Consequences for how these numbers may be used:

- **"six ports, 54 conflicting facts, 24 cells nobody contradicted" is a cold-clone claim.** A reader who
  clones this repository gets it.
- **"4 cells are fully recorded and identical, and the tree is schema-conformant" is a work-tree claim for
  now.** It becomes a history claim when the TypeScript lane commits, and the way to check is to re-run this
  exact table: `python ci/equality.py | grep OUTCOME=` in a fresh clone and compare the three rows above.
  Until then any document that prints the 4 must say which tree it was read from, and `docs/journey.md` 2.15
  and `docs/coverage.md` both carry the reading timestamp for that reason.
- The `arms=15` vs `arms=20` line is the same phenomenon in the tooling: the coverage-and-requiredness
  instrumentation in `ci/validate_cells.py` is in the work tree and not in history at this minute.

## Limits of this record

- Single host, single OS: Windows 10 build 19041 x64, `LongPathsEnabled=0`, console code page 936. The macOS
  and Linux rows still do not exist, and this run does not create them - they need CI, and pushing is the
  owner's act.
- The clone is of `main` at one commit; it is not a test that the *published* repository is reproducible,
  because nothing has been pushed.
- Face-set sizes differ between the trees (the work tree carries 87 TypeScript faces against HEAD's 80), so
  per-port cell counts in `docs/GAP.md` and `docs/cell-validation.md` move when the lane commits. This record
  compares the six quantities above and nothing else.

## 12:29 re-run against `2037b15` - the three rows closed (this section supersedes the caveat above)

The TypeScript lane's 12:02 batch landed as `2037b15` ("Land the TypeScript lane's 12:02 batch…", 67 files:
56 modified faces, 7 new faces, its `selfcheck.py`/`runner.ts`/`probe.ts` and its own closing report), so the
work tree was re-cloned and the same commands run again: `git clone --no-local file:///D:/sendguard-work/seat-qoder cold-3`
(`clone_rc=0`, clean status, `git status --porcelain -uall` = 0 lines).

| command (in the new clone at `2037b15`) | reading |
|---|---|
| `python ci/selftest.py --scratch-root ../cold-st3` | `arms=21 passed=21 failed=0` `OUTCOME=PASS` |
| `python ci/equality.py` | `OUTCOME=RED verdict_disagreements=54 verdict_identical_cells=24/44 cells_fully_recorded_and_identical=4 verdict_not_recorded_pairs=121 verdict_pairs_recorded=2281/2640 … required_cells_missing=0` |
| `python ci/validate_cells.py` | `invalid=0 missing_faces=0 verdict_fields_not_required=9 verdict_fields_undocumented=4 cells_omitting_a_compared_field=371` |
| `python ci/coverage_report.py` | `recorded=2281/2640 fully_recorded=4 clean_and_fully_recorded=4 blanks_by_everybody=10` |
| `python ci/acceptance.py` | `faces_ahead_of_head=0 git_status_rc_nonzero=0` |

So the three rows that this record earlier declared work-tree-only - `verdict_not_recorded_pairs`,
`cells_every_port_recorded_every_verdict_field` and the conformance count - now reproduce from history, and the
`faces_ahead_of_head` row reads 0 in a stranger's clone. Parity was checked two ways rather than assumed: the
verdict artifact minus its `written_at` field is byte-identical between clone and work tree (21,396 bytes on
both sides, same JSON), and the only differing lines in `docs/coverage.md`, `docs/cell-validation.md` and
`docs/STATUS.md` are their own `Generated by … at <timestamp>` headers (`diff` output inspected, 1 line each).

**The caveat's rule survives its subject.** The claim was not "these numbers are wrong" but "a number is only
quotable with the tree it was read from", and the next lane to leave faces uncommitted will make the same row
non-zero again - which is exactly why `docs/acceptance-S02.md` prints the count on every run instead of
trusting this record. Limits unchanged from above: one host, one OS, nothing pushed, so the macOS and Linux
rows still do not exist anywhere.
