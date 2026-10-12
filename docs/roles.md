# SENDGUARD lane assignment - constraints, not a staffing chart

Frozen at S00. This face records **who may not do what**, because that is a property of the experiment. It does
not record who did do it: a persona, a seat code, a session name, or an ordering of people and machines is a fact
about the studio, and the studio is not part of any cell's correctness. The staffing history that used to be in
this table (including a mid-experiment swap and the identities behind each lane) remains in the published history
of the repository, was corrected forward on 2026-10-12 under `SG-F9`, and is not restated here.

A reader who wants to test the independence claims should run the instruments, not read this page:
`python ci/selftest.py --scratch-root ../<dir>` (21 arms, includes the lock table),
`python ci/validate_cells.py --selftest` (29 arms), `python ci/process_leak_scan.py --repo-root .` - that last
leg is what checks whether the deliverable still carries production metadata.

## Invariants (nine, each stated as a constraint)

1. **An instrument's author is never the language it measures** (`M10`/`M17`): implementation code and instrument
   code share zero files. A lane that writes the ruler also gets to choose what it can see.
2. **An auditor never audits its own cells.**
3. **No self-signed PASS** (`M17`): a verdict is issued by a leg, not by the hand that produced the record.
4. **Two independent review instances** sit on the audit stages, and neither audits the seat it reviewed.
5. **The headline cell's two sides come from different lanes**: the compared pair must not be producible by one
   hand, or the headline is one implementation agreeing with itself.
6. **Every lane holds exactly two languages**, counted after the re-assignment made at S00's close. The count is
   the invariant; which lane, and why, is not.
7. **The record keeps its failures**: at least one quarter of the build narrative is a retraction or a defect,
   each with its original output attached. A narrative with no failures in it is not a record, it is advertising.
8. **Per language group, at least one implementation must be proven (`S07`); all six proven is the red line
   (`M11`).** A group with nothing proven is reported as such rather than covered by a neighbour's result.
9. **The comparison unit is declared, never implied.** Name length is measured in the group's own unit below;
   a verdict reached in a different unit is a different question and is excluded from comparison as
   `unpinned_input`, printed by name.

## Language groups and their measurement unit (frozen)

| group | unit | lanes |
|---|---|---|
| UTF-16 code units | 3 lanes | node, java, csharp |
| code points | 1 lane | python |
| UTF-8 bytes | 2 lanes | go, rust |

## Lane identifiers used by the data contract

`node-port`, `python-port`, `go-port`, `java-port`, `csharp-port`, `rust-port`, `typescript-port` - the value
shape is enforced by the schema (`^[a-z][a-z0-9-]{0,15}-port$`) and by `ci/validate_cells.py` arms A25-A29.
Anything naming a session, a persona or an engine is a disclosure finding, counted by
`ci/process_leak_scan.py`, not a style preference.
