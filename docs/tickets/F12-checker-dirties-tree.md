# SG-F12 - a leg that regenerates faces while checking them leaves the tree it just judged dirty

Found by this seat on 2026-10-12 while landing `SG-F10`, not by a reviewer: after
`python ci/claim_digest.py --scratch-root ../sg-cd-f10`, `git status` showed three tracked faces modified
(`docs/spec-drift.md`, `docs/tapi.md`, `evidence/S02/equality-verdict.json`), each by its own generation
timestamp and nothing else. The digest executes other suites, and those suites write faces.

## Why this is not cosmetic

Two of this project's published numbers are about exactly that state: `faces_ahead_of_head=0` in
`docs/acceptance-S02.md`, and the parity leg's `status_before=0` guard. A checker that dirties the tree makes
those two readings true only **between** runs - so the sequence "run the checks, then read the board" is
unfalsifiable, and the honest sequence "read the board, then run the checks" is a habit nobody keeps under
pressure. The instrument changed the condition it reports on, which is the same family as the delivery-form leg
whose own file list was not cross-checked (M9): the ruler has to be blind to its own hand.

## Acceptance criteria

1. every leg in `JUDGE` runs with writes suppressed - either a `--no-write`/`--check` mode on the generators, or
   executing them in a throwaway copy of the faces; the mechanism is the ticket author's choice, the requirement
   is that `git status --porcelain` is empty on exit;
2. the leg asserts its own cleanliness in its run line: `tree_dirty_after=<n>` must be printed and must be 0,
   with a red arm showing that a planted modification is reported - a self-clean claim with no red side is a
   preference;
3. `ci/claim_digest.py` (and anything else that executes suites) prints which legs it ran and whether the tree
   moved across the whole batch, so a later seat can tell a stale face from a dirty one;
4. the two faces that moved today are committed as stamps-only, naming what moved and showing the judged
   readings did not: `compared=264 current=264 older=0` and `entry_gaps=0` before and after;
5. `python ci/refresh_all.py --check` still reports the regeneration is stable, since that flag exists precisely
   to catch a generator that cannot reproduce its own output.

## Allowed surface

`ci/claim_digest.py`, the generator legs it executes, `ci/refresh_all.py`, and a new `tree_dirty_after=` field in
their run lines. Not `spec/`, not `impl/**`, no deletion logic (M19).
