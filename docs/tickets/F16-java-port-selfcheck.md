# F16 - the java port is the only port without a self-check of its own

Opened 2026-10-12 by the maintainer that owns `ci/`, found while writing `README.md` §7 (the stranger's path): five of
six ports ship a port-authored script that re-parses the contract and judges the port's own face; the java port does
not. That asymmetry is not a published-number problem today - every java face passes the shared rulers - but it means
the java port's answer is checked only by rulers that every other port also answers to, and this project's rule is
that a claim needs an instrument the claimant did not write.

## Measured, from the cold-clone run recorded in `evidence/closing/six-port-usability-20261012.md`

| port | port-authored self-check | result in the clone |
|---|---|---|
| python | `impl/python/sg_selfcheck.py` | `rc=0`, `cells_produced=123 cells_valid=123` |
| rust | `impl/rust/selfcheck.py` | `rc=0`, `OUTCOME=OK` |
| typescript | `impl/typescript/selfcheck.py` | `rc=0`, `language_enum_gap_cells=0` |
| csharp | `impl/csharp/selfcheck_csharp.py` | `rc=0`, `controls=GREEN(5)` |
| go | `impl/go/rederive/selfcheck.py` | `rc=0`, `OUTCOME=PASS` |
| java | **absent** - the port ships `tools/run_cells.py` and captured records, no validator of its own | the face passes `ci/validate_cells.py` (`invalid=0`) and `ci/equality.py`, which is a shared ruler, not a second one |

`impl/java/tools/` holds a runner, two record-appending helpers and a facts file; nothing there re-parses
`spec/cases.yaml` against the produced faces.

## Acceptance criteria

1. `impl/java/tools/selfcheck.py` exists and is port-authored: it re-parses `spec/cases.yaml`, reads the required
   list out of `spec/cells-required.json`, re-reads the closed status words out of `spec/canonical.md`, re-reads the
   control expectations from `evidence/ctrl-baseline.md`, and validates every face under the canonical java
   directory against `spec/schema.json` - the same five inputs the other ports' self-checks use, reached through
   the same kind of code, never by importing `ci/` (the shared ruler must stay the second ruler);
2. it prints denominators, not adjectives: `cells_required=`, `cells_produced=`, `cells_valid=`, `cells_blocked=`,
   `extra=`, `invalid_by_reason=`, and a `files_scanned=` for the directories it read;
3. exit codes are distinct and documented: 0 clean, 2 a control failed, 3 a cell-level or denominator defect, 4 it
   could not load its own inputs - a check that loaded nothing must never read as a pass (the empty-rule-set
   failure this repository has already caught in itself four times);
4. both directions are covered by arms inside the file: a planted control failure yields 2, a planted schema
   violation yields 3, an unreadable spec yields 4, and an untouched tree yields 0;
5. run it in a `--no-local` clone, print the command and the last line; the java face's ten verdict fields must
   still show zero differences against the committed face, and the gate's four readings must not move.

## Do not

- Do not weaken or alter `impl/java/tools/run_cells.py` to make the self-check pass - the runner's numbers are the
  subject, the self-check is a new judge.
- Do not touch `spec/`, `ci/`, or another port. No deletion (project rule). No history rewriting.

## Allowed surface

`impl/java/tools/` plus the acceptance row in `evidence/closing/`.

## Clock

24 h from issuance. Queue position: it blocks nothing; `README.md` §7 already tells the stranger which port has no
second ruler, so the gap is advertised rather than hidden.
