# SG-F3 — Six lanes: make the harnesses able to answer on macOS and Ubuntu at all

Status: **not dispatched to anyone yet, and deliberately unscheduled.** This file exists because the project's
outward documents said "the macOS and Linux rows need CI to run", which is what a reader of
`.github/workflows/matrix.yml` would reasonably conclude and what is not true. Writing the work down is the
correction; nobody has agreed to do it, and no deadline is set, because whether it is worth six harness
rewrites is the owner's call, not this seat's.

## The measured reason the rows do not exist

| fact | where it was measured |
|---|---|
| The sealed expectation table already predicts non-Windows behaviour: 22 macOS rows and 22 Ubuntu rows (23 lines each, three of which fold to "same as macos row") | `spec/expectations.sealed.md`, published by `python ci/expected_summary.py` → `sealed_by_os=macos:22,ubuntu:22,windows:22` |
| Every port's runner writes to a **hard-coded** `results/<port>.windows.x64/` | `impl/python/sg_run.py:32`, `impl/csharp/run_csharp.py:37`, `impl/rust/run_cells.py:41`, `impl/typescript/selfcheck.py:28`, and the same pattern in go/java |
| Every cell record carries `"os": "windows"` as a produced value, not a derived one | any file under `results/*`, field `os` |
| The traps are Windows semantics: reserved device names, trailing dot/space stripping, `\\?\` prefix handling, 8.3 short names, NTFS alternates | the six lanes' own findings (`docs/FINDINGS-rev6.md` M1-M3, `docs/length-family.md`) |
| Nothing in CI builds or runs a port harness on any OS | `.github/workflows/matrix.yml` before 13:14 today |

So the missing rows are **not** a missing `git push`. The push gives you the instrument re-verified on three
operating systems (which is what the new `instrument` job does, and it says so in the file); it does not give
you six ports × two operating systems of measured behaviour.

## What each lane would have to do (the honest shape, not a wish)

1. **Derive the face name and the `os` field from the runner**, not from a constant:
   `results/<port>.<os>.<arch>/` where `<os>` comes from the host at run time. The gate's canonical-face
   regex (`ci/equality.py` `RE_CANON_FACE`) already accepts any `<os>`, and `discover()` excludes
   non-canonical faces by naming them, so no gate change is needed to accept a second OS - but the equality
   verdict would then need to be **per operating system**, not global: a macOS answer and a Windows answer
   agreeing is not a finding, it is a different question. That is a contract decision (round 9), not a harness
   detail.
2. **Decide, per trap, whether it applies off Windows** - the contract already carries the field for exactly
   this (`spec_applicable_on_windows`), and it is currently written but never read by any leg. A POSIX run
   that answers `T10 CON` is answering "what does POSIX do", and the sealed table says `legal`; a run that
   *skips* it must say so as `not_applicable`, not as a blank - which is the same
   applicability/blanks question as `docs/NOTICE-rev9-proposal.md`.
3. **Keep the Windows face byte-identical.** The 557 records already in history are the product's evidence;
   a portability change that rewrites them is not portability, it is a new measurement series.
4. **Volume-family work stays out of scope here** - the FAT32/exFAT, network-share and mail/attachment layers
   are separate tickets and separate machines.

## Two things the contract has to say first

- Is the equality claim per-OS (six ports agree *on Windows*, and separately *on macOS*), or across OSes?
  Per-OS is the only version that means something; say so in `spec/gate.md` and `docs/claim-boundary.md`.
- Which verdict fields are `not_applicable` off Windows (`docs/NOTICE-rev9-proposal.md` option A).

## What would be verifiable the day it lands

- `python ci/equality.py` prints two verdict lines (one per OS face set) instead of one, and
  `docs/STATUS.md` gains an `os=` column - the gate already refuses to merge non-canonical faces, so this is
  additive;
- `python ci/expected_summary.py` moves rows from `NOT-RUN(no face for that OS)` into REPRODUCED / PARTIAL /
  CONTRADICTED, and its invariant (`sealed_by_os` vs published) is already in place to catch a leg that
  quietly stops publishing one;
- `python ci/lint.py` fails if `.github/workflows/matrix.yml` claims a port run on an OS that no face
  demonstrates - the current arm (`check_workflow_instrument`, P4 in `ci/lint.py --selftest`) already
  requires the honest absence marker to be *present*, so removing the claim is a lint failure, not a silent
  edit.
