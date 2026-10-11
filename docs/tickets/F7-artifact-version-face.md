# SG-F7 - the deliverable carries no version, so "which artifact did you audit" has no answer

Opened 2026-10-11 16:1x +0800 by the seat that owns `ci/`, prompted by the owner's question "then you update the
version after the audit". Answering it required measuring what "the version" would refer to. It refers to
nothing that exists.

## The hole, measured rather than suspected

- `tool/check.py` prints no version string. Its header lines print the interpreter and the platform
  (`sys.platform`, `sys.version.split()[0]` at `tool/check.py:1006`), which are facts about the machine, not
  about the artifact.
- No face in the repository carries a product version. The version-shaped tokens that do exist are
  `format_version` (a field of the contract's schema, integer `1`) and the sealed contract round (currently the
  eighth, `freeze_revision: 2` in `spec/cases.yaml`). Neither identifies a deliverable.
- Consequence that is live right now, not hypothetical: `evidence/audit-in/TEMPLATE.md` requires every auditor
  to state `commit:` in its header. That works for someone who cloned. A buyer handed a zip has no field to fill
  in, and a report that says "the version I ran" cannot be reproduced from anything inside the artifact.

## Owner input required — this is why the ticket is not executed

1. **The version string itself.** Its shape is product identity, not a technical constant, and this seat does
   not invent identifiers for things the owner sells. One string, and the ticket is executable as written.
2. **Whether the contract round moves with it.** Those are two different objects: `spec/` re-sealing cascades
   (manifest regenerated, `spec/FROZEN.md` digests re-pinned, every cell's `spec_sha256` stale until all six
   ports re-emit — see `docs/NOTICE-rev9-proposal.md` for the full cost). Advancing a version must not
   silently trigger that.

## Acceptance criteria (all runnable the moment the string exists)

1. One tracked file is the single source of truth (`VERSION` at the repository root, one line, no trailing
   prose). Any second hand-written copy of the string is a defect, not a convenience.
2. `tool/check.py` prints the string in its own header line, read from that file at run time.
3. `ci/clone_parity.py` compares the tool's output between the working copy and a `--no-local` clone. Adding a
   header line must be shown not to enter the scored field set **by name**, with a green arm that passes when
   the line is present and a red arm that fails if the line is ever parsed as a verdict field. A tolerance that
   works because the parser happens to ignore the line is the decoration this project has already caught itself
   building twice.
4. A leg refuses with `rc=3` (`OUTCOME=INSTRUMENT-RED`) when `VERSION` is missing, parses to something other
   than exactly one non-empty line, does not match the string the tool prints, or when any policed face carries
   a version-shaped token that differs from it. Missing file is an instrument problem, never a pass — the
   failure mode `ci/coverage_report.py` and `ci/claim_digest.py` already encode.
5. The red side is demonstrated, not asserted: change one digit in one policed face, the leg must go `RED`;
   change it back, `CLEAN`. A filter with no green arm is the pattern `docs/FINDINGS-rev6.md` M9 names - "every
   other arm in that leg's suite was satisfiable by a filter that discarded the world".
6. Every human-facing face prints the string by generation, not by typing: `README.md`'s run lines,
   `docs/evidence.md` and `docs/delivery-form.md` take it from the file through their generators, and
   `python ci/refresh_all.py` reproduces them byte-for-byte from a clone.
7. No leg creates a tag, and no leg pushes. Tag-for-public and publish are the owner's acts.

## Do not

- Do not bump `freeze_revision` or touch `spec/` as part of this ticket.
- Do not add deletion logic to any leg (rule `M19`, `docs/cleanup-notice.md`).
- Do not put the version into the gate's scored field list; the version is provenance about the artifact, not a
  verdict about a name.

## Cost estimate

One file, one print statement, one new leg with its two-sided arms, three generator touches. Under an hour once
the string is given. The waiting cost of not having it is what this ticket is really about: an audit is starting
against an artifact that cannot name itself.
