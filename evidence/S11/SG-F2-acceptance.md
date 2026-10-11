# Acceptance record — SG-F2 (Java lane: the `java.io` spread, and the control-cell stamps)

Seat: delivery (`d9242392`). Host clock 2026-10-11 13:34 +0800.
Ticket: `docs/tickets/SG-F2-java-io-spread-and-control-stamps.md`, dispatched 13:05. Lane's commit:
`b56e9c4` ("Land SG-F2 in the java lane: twelve java.io legs as cells, five of five controls stamped"), plus
its own transcript `impl/java/tools/verify-sg-f2-output.txt` (one command per block, `rc` printed after each —
including a `3b rc of equality alone` block, because it noticed its first reading came through a pipe).

## Verdict: ACCEPTED on all five criteria, read by this seat's instruments

| # | criterion | expected | read at 13:33, tree = HEAD `b56e9c4` | rc |
|---|---|---|---|---|
| 1 | `python ci/validate_cells.py` | `invalid=0` | `invalid=0 missing_faces=0 cells_omitting_a_compared_field=371` (371 unchanged - the new cells are `extra`, so they do not move the required-set counts) | 0 |
| 2 | `python ci/acceptance.py`, java row | `pass (5/5 stamped)`, `44/44`, `extra >= 38` | java row: 86 faces, 44/44, **38 extra**, `pass (5/5 stamped)`, schema-invalid 0 | 0 |
| 3 | `python ci/equality.py` must not move | 54 / 44 / 4 | `verdict_disagreements=54 cells_compared=44(24/44 identical) cells_fully_recorded_and_identical=4 verdict_not_recorded_pairs=121 required_cells_missing=0` | 1 (RED = the measurement) |
| 4 | spread cells carry their own runtime identity, and the pinned filler | every new cell | 12/12 carry `toolchain` **and** `jvm_self_report`; `name_source` is 240 hex characters = 120 × `61` (the `len_fill` unit), and `sub_identity` uses the contract's existing `builder` dimension with `extra: true` | - |
| 5 | nothing left uncommitted in the lane | 0 lines | `git status --porcelain -uall -- results/java.windows.x64` → 0, and `docs/acceptance-S02.md` prints `faces_ahead_of_head=0` | 0 |

## The finding the ticket was actually after, now sitting in cells rather than in prose

All twelve `FileOutputStream.write` legs - plain **and** extended, at `base_len` 78/120/200 - record
`roundtrip_ok=true` with `error_stage=null`. The lane's required `Files.write` cells on the same extended rungs
record the prefix being refused at the parse layer (`InvalidPathException`, and M7's finding that Temurin 17
refuses while 21 accepts). So the tree now contains, as data rather than as a paragraph:

- **same port, same string, two APIs, opposite answers** - `java.nio.file` refuses what `java.io` round-trips;
- **same port, same API, two runtimes, opposite answers** - captured at `impl/java/tools/ext-path-of-repro.txt`.

`ci/spec_drift.py` reads `older=0` after this batch, and the `extra` cells are published
and not compared, so the equality verdict is untouched: the divergence is evidence, and the contract still
judges only the 44 required cells.

## One instruction that was mine to write, not theirs to guess

The ticket asked for `control_pass` **plus** `control_pass_evidence` naming the command behind the result. The
lane stamped all five controls `true` and recorded no pointer - and so, the census now shows, does **every**
lane: 30 control cells on disk, 30 stamped, **0 carrying a source**, because `control_pass_evidence` appears in
no contract round and no leg read it until this afternoon. `python ci/validate_cells.py` prints that table now
(`Control-cell stamps and whether they say where they came from`, arms=24 including a red arm that keeps a
pointer-less stamp in its own bucket rather than in "verified" and a green arm that keeps non-control cells out
of the census entirely).

So the miss is mine twice over: I wrote a requirement into one ticket that the contract does not contain, and
then treated its absence as a lane's remaining piece. It is not. Either round 9 names the field - which is the
same family of decision as `runtime_executable` and the applicability table, all three being "what must a record
say about itself" - or the requirement should not have been put to a lane at all. Corrected here rather than
left in the ticket, and the ticket's acceptance is unaffected: the five numbered criteria are met, and a false
stamp would have been the thing to refuse.

## Net effect on the deliverable

- The java.io-versus-java.nio divergence, which this morning existed only as a reproduction file, is now twelve
  recorded cells - published as `extra`, judged by nothing, and carrying the runtime identity that made M7 a
  finding.
- The control-cell story got sharper rather than greener: five of five ports-per-cell now report a result, and
  the honest next question is what any of them can be asked to prove about it.
