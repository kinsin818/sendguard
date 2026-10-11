# Acceptance rehearsal — README's own command list, run by a stranger's clone

Seat: delivery (`d9242392`). Host clock 2026-10-11 13:23 +0800.
Clone: `git clone --no-local file:///D:/sendguard-work/seat-qoder rehearse` → HEAD `0c7c098`, `clone_rc=0`.
Scratch root passed in by the caller (`../rehearse-st`); no instrument chose its own landing place.

This is the list the README tells a reader to run, executed exactly as printed - no `refresh_all` shortcut, no
helper. It is a rehearsal of the acceptance act itself, because a document whose commands only work on the
machine that wrote them is not evidence, and because the README had been quietly updated (three judging legs
added to the list at 13:22) without anyone running the new sequence end to end.

| command | rc | what it printed |
|---|---|---|
| `python ci/selftest.py --scratch-root ../rehearse-st` | 0 | `arms=21 passed=21 failed=0` |
| `python ci/equality.py` | **1** | `NAME-CROSS-FORM-AGREE …` then `OUTCOME=RED verdict_disagreements=54 verdict_identical_cells=24/44 cells_fully_recorded_and_identical=4 verdict_not_recorded_pairs=121 … required_cells_missing=0` |
| `python ci/coverage_report.py` | 0 | `recorded=2281/2640 fully_recorded=4 clean_and_fully_recorded=4 blanks_by_everybody=10` |
| `python ci/validate_cells.py --selftest` | 0 | `arms=20 passed=20` |
| `python ci/spec_drift.py` | 0 | `compared=264 current=264 older=0 unstamped=0 affected_by_delta=0` → `OUTCOME=CLEAN` |
| `python ci/gap_report.py` | 0 | `ports=6 total_missing=0` |
| `python ci/matrix_table.py` | 0 | `rows_agree=24 rows_differ=20 unpinned=0 incomparable=0` |
| `python ci/expected_summary.py` | 0 | `rows=78 counts={'REPRODUCED': 50, 'PARTIAL': 20, 'CONTRADICTED': 3, 'NO-SUCH-CELL': 5}` plus the 22 macOS / 22 Ubuntu sealed rows published as untested |
| `python ci/triangle.py` | 0 | `OUTCOME=CLEAN` |
| `python ci/acceptance.py` | 0 | `ports=6 faces_excluded=5 faces_ahead_of_head=0 git_status_rc_nonzero=0` |
| `python ci/evidence_table.py` | 0 | verdict line quoted, `selftest=arms=21 passed=21 failed=0` |
| `python ci/status_brief.py` | 0 | `conflicts=54 clean=24/44 abstain=13` |
| `python tool/check.py --name "trail."` | **1** | the deliverable's verdict block; 1 is that tool's documented "risk found" (its table: `0=no risk 1=risk found 2=scan failed 3=bad usage 4=this tool crashed`) |

## What the rehearsal establishes

- **Nothing in the acceptance path depends on this seat's working directory.** Two exit codes are non-zero and
  both are the documented outcome of a measurement, not of a tool: the equality gate's RED is the finding
  (54 conflicting facts), and the deliverable's 1 is the risk it exists to report.
- **`faces_ahead_of_head=0` in the clone** while the work tree was carrying a lane's in-flight Java faces - the
  row a stranger reads is the row history supports, and the same leg prints the non-zero number in the author's
  tree. That is the pair this project asks of every number: claim, and the tree it was read from.
- `spec_drift` reads `older=0` in a clone, i.e. the Python lane's re-stamp (`e0d80a8`) is a property of
  history, not of a disk state.

## What the rehearsal does not establish

- It ran on one host (Windows 10 19041 x64). The `instrument` job in `.github/workflows/matrix.yml` is meant
  to run this same list on three operating systems, and **it has never run**: nothing has been pushed, and no
  document claims otherwise.
- No port harness was rebuilt here. The six faces are read as committed; compiling all six from source on a
  clean machine is a different act and has its own gap (`docs/STATUS.md` and `docs/acceptance-S02.md` say what
  each lane actually re-ran).
- The Java lane's SG-F2 work was in flight while this ran (its tool files modified, nothing committed); it is
  not part of this reading, and nothing here accepts it on the lane's behalf.
