# Cold-clone verification, third run - the whole pipeline inside a stranger's tree

Author: the delivery local (window `d9242392`). Host clock 2026-10-11 12:53 +0800.
Repository under test: `D:\work\session-token` at HEAD `e5055ce` ("Make the frozen-spec claim a
check…"). Clone: `git clone --no-local file:///D:/work/session-token cold-4` (`clone_rc=0`; inside it
`git status --porcelain=v1 -uall` = 0 lines).

## Everything, in the clone

| command (run inside `cold-4`) | rc | reading |
|---|---|---|
| `python ci/refresh_all.py` | 1 | `OUTCOME=CLEAN refusals=1 tool_failures=0` - the single refusal is `ci/equality.py`'s RED, which is the measurement, not a fault |
| ↳ `ci/selftest.py` | 0 | `arms=21 passed=21 failed=0 OUTCOME=PASS` |
| ↳ `ci/lint.py --selftest` | 0 | `lint: OK arms=18 passed=18 workflows=1 runner_labels_checked=4 tracked=1131,untracked=0 names_checked=1131 json_scanned=956` |
| ↳ `ci/validate_cells.py --selftest` | 0 | `arms=20 passed=20` |
| ↳ `ci/spec_drift.py --selftest` | 0 | `arms=15 passed=15` |
| ↳ `ci/equality.py` | 1 | `OUTCOME=RED verdict_disagreements=54 verdict_identical_cells=24/44 cells_fully_recorded_and_identical=4 verdict_not_recorded_pairs=121 verdict_pairs_recorded=2281/2640 probe_cells_differing=29 unpinned_input=0 cells_excluded=0 channel_abstentions=13 truncated_values=2 required_cells_missing=0` |
| ↳ `ci/triangle.py` | 0 | `OUTCOME=CLEAN` |
| ↳ the nine generators | 0 | `docs/spec-drift.md compared=264 current=237 older=27 unstamped=0 affected_by_delta=0`; `docs/coverage.md recorded=2281/2640 fully_recorded=4 clean_and_fully_recorded=4`; `docs/cell-validation.md invalid=0 verdict_fields_not_required=9 cells_omitting_a_compared_field=371`; `docs/acceptance.md faces_ahead_of_head=0`; `docs/GAP.md total_missing=0`; `docs/tapi.md entry_gaps=0` |
| `python tool/check.py --name "CON.txt"` | **1** = "risk found" (the tool's own table: `0=no risk 1=risk found 2=scan failed 3=bad usage 4=this tool crashed`, and 4 exists because a Python traceback also exits 1) | `phantom=true`, `roundtrip_ok=NOT-RECORDED`, `read_result=NOT-RECORDED because reserved device name: reading its contents can block, and this tool is told never to read one` |

Every number the work tree published this morning reproduces from history alone, including the three that
`evidence/clone-tool/cold-clone-20261011b.md` had to declare work-tree-only at 12:12 (`verdict_not_recorded_pairs`,
`cells_fully_recorded_and_identical`, the conformance count). They closed when `2037b15` landed, and this run
is the re-check, not a restatement.

## Parity was compared, not assumed

Comparing the ten generated docs byte-for-byte is meaningless because each prints a generation timestamp, and
comparing them *after* stripping timestamps hides real differences, so the normalisation was declared first and
the residue inspected: timestamps matching `2026-MM-DD[ ]HH:MM:SS` and the self-referential "working tree
carries N uncommitted faces" counter were folded to `@`, then every remaining line compared.

- **9 of 10 generated docs are identical** between the clone and the work tree (all of `GAP.md`, `STATUS.md`,
  `matrix.md`, `expected-summary.md`, `cell-validation.md`, `tapi.md`, `acceptance.md`, `coverage.md`,
  `spec-drift.md`);
- `docs/evidence.md` differed in one more place: it names `repository commit: a098484…` while the clone was at
  `e5055ce…`. That is not drift, it is a **self-reference lag** - a generated file cannot name the commit that
  contains it, so it necessarily names the HEAD it was generated under. The generator now says so in the line
  itself instead of leaving a reader to wonder why the commit quoted is one behind;
- `evidence/judgement/equality-verdict.json`, with `written_at` removed, is identical between the two trees (same
  JSON, compared as parsed objects so key order cannot flatter the result).

## Limits of this record, unchanged

One host (Windows 10 build 19041 x64, `LongPathsEnabled=0`, console code page 936), one volume family, nothing
pushed. The macOS and Linux rows still do not exist, and this run does not create them: they need CI, and
pushing is the owner's act. Scratch roots were passed in by the caller (`../cold-st`, `../cold-st3`) and no
instrument chose its own landing place.
