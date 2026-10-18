# F9 - narrative faces that describe the project rather than the artifact

Opened 2026-10-12 by the maintainer that owns `ci/` and the contract, alongside F8. That ticket fixes the **data
contract**; this one fixes the **narrative faces**, because a schema field renamed while the story stays put has
not moved the boundary - it has only moved one kind of evidence across it.

## What is exposed, with the reading that shows it

| face | what it publishes | how it was found |
|---|---|---|
| `docs/roles.md` | the machine-to-language assignment, the role names staffing each port, the B14 swap rule, the invariant "every port still holds exactly 2 languages", and who authored each generated document | read at the published tip; `git grep -l -e "worker_id" 1b4abc6 -- docs` returns nothing here, so this is a *separate* disclosure from F8 and would have been missed by that ticket's scan alone |
| `spec/FROZEN.md:3` | `Frozen by: the maintainer per project rule` - the seal record names the project's vocabulary and the sealing role | `git grep -n -e "project rule" 1b4abc6 -- spec` |
| `evidence/stage0-close-report.md` | acceptance report written in the project's own terms (`project rule`, `maintainer`, `acceptance`, `pass`) | `git grep -l` for each token at the tip |
| 14 faces quoting the tree's own absolute path, 17 quoting a user-profile path | host layout: where the work lives and whose profile runs it | `python ci/process_leak_scan.py --repo-root .` -> `fatal_by_class=HOSTROOT:14,LOGIN:17,...` |

## What "fixed" means here

This is not deletion and not redaction. A narrative face can keep every fact that bears on the artifact's
correctness while dropping the facts that describe staffing. Concretely, for each face:

1. **keep** the invariants and the reasons - "the instrument author is never the measured language", "the
   headline cell must not come from one hand", "these two cells were swapped because a port saw another's
   output" stated as *a rule about independence*, with the outcome it protects;
2. **replace** roles, internal codes, pass names and internal role vocabulary with the product-side labels the
   new contract uses (`python-port`, `rust-port`, ...);
3. **state the residue** in one line per face: the earlier wording was published, remains in the history of the
   published repository, was corrected forward, and the reason is F8/F9 - no sentence may imply it never
   existed.

`spec/FROZEN.md`'s seal line changes only at a seal (round 9, together with F8), never as a free edit; the two
evidence faces are records and get an appended correction row rather than rewritten prose, per the project's own
append-only rule.

## Allowed surface

- `docs/roles.md`, `evidence/stage0-close-report.md`, and an appended errata row in `docs/claim-boundary.md`
- `spec/FROZEN.md` line 3 - only inside the round-9 seal performed with F8
- the 14 + 17 faces named by the leak scan, for the path references only (replace with the published URL or a
  relative path; where a command genuinely needs an absolute path, the face must say it is one host's layout and
  not part of the claim)

Not allowed: touching `impl/**`, deleting any face, changing a verdict, adding deletion logic (rule project rule), or
rewriting history.

## Acceptance criteria

1. `python ci/process_leak_scan.py --repo-root .` reaches `OUTCOME=CLEAN ... FATAL=0`, and the run line still
   prints `files_scanned=`, `unreadable=`, and `fatal_by_class=` - an empty denominator is VOID, not clean;
2. the same leg run against a tree with no findings must print `OUTCOME=CLEAN` (positive control - already
   demonstrated against a sibling repository at `poscontrol_rc=0`, so `CLEAN` is reachable rather than
   theoretical);
3. every invariant in `docs/roles.md` survives the rewrite: the acceptance row shows the before/after count of
   invariant statements, and the count must not drop. A rewrite that quietly loses a rule is the failure mode
   this project has caught in itself twice;
4. `docs/claim-boundary.md` gains a row distinguishing **product provenance** (runtime, toolchain, harness
   version - kept, because verdicts flip with the executable) from **production metadata** (who staffed which
   port - removed), so the boundary is written down rather than re-litigated at the next release;
5. `python ci/selftest.py`, `python ci/lint.py --repo-root .`, `python ci/link_check.py` and
   `python ci/claim_digest.py --scratch-root ../<dir>` all stay green after the rewrite, since a rewrite of
   narrative faces can silently break a quoted number or a reference;
6. the equality readings are unchanged by this ticket, printed before/after in the same batch, exactly as in
   F8 criterion 4.
