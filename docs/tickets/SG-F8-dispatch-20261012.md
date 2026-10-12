# SG-F8 dispatch - the six re-emit orders, one row per lane, issued 2026-10-12 10:5x

Parent: `docs/tickets/SG-F8-public-interface-process-metadata.md`. The contract side is already sealed (freeze
revision 4: `spec/schema.json` carries `implementation_id` with the value pattern, `spec/FROZEN.md` re-pinned,
its superseded digest named). Nothing a lane has produced so far is invalidated by that seal - the rename breaks
no fingerprint and no record - so a re-emit is a purge of the old key from the data face, not a re-answer.

**Clock**: each lane lands its re-emit within **24 hours of reading this row**. No lane is waiting on another;
the equality gate compares whatever is canonical at the time and reports the mix honestly, so a partially
re-emitted set shows as `RETIRED` findings in `ci/process_leak_scan.py` and nobody has to take anyone's word
that the purge is done.

| lane | files to change (measured) | value to write | what must not move |
|---|---|---|---|
| `python-port` | `impl/python/sg_python.py` (5 lines), `impl/python/sg_run.py` (1), `impl/python/sg_selfcheck.py` (1) | `python-port` | its canonical face's verdict fields |
| `rust-port` | `impl/rust/run_cells.py` (3), `impl/rust/src/probe.rs` (1) | `rust-port` | the same |
| `typescript-port` | `impl/typescript/src/runner.ts` (2) | `typescript-port` | the same |
| `go-port` | `impl/go/main.go` (1), `impl/go/rederive/celljson.go` (1) | `go-port` | the same |
| `java-port` | `impl/java/tools/run_cells.py` (1) | `java-port` | the same |
| `csharp-port` | `impl/csharp/run_csharp.py` (1) | `csharp-port` | the same |

The node lane keeps its cells: `W-NODE` was the node face's producer stamp and those records are frozen history
under an earlier contract; if the node lane re-emits at any point, its value is `node-port`.

## What each lane reports back (the whole report, three lines)

```
re-emitted: <count of cells rewritten> at <commit>
unchanged:  <the gate's four readings on your face: disagreements / identical / fully-recorded / not-recorded>
worker_id:  0 occurrences left in my canonical face   # python ci/process_leak_scan.py --repo-root . | grep <your port>
```

That last line is not a promise, it is the leg's output. A lane that reports `0` without the line is treated as
not done, because this project has already been fooled by exactly that shape.

## Rules that apply to every row

- Do not hand-edit a result face. Change the emitter, re-run the harness, and let the face be generated. A
  hand-edited data face is indistinguishable from a fabricated one, which is the whole reason the faces exist.
- Do not touch `spec/`, `ci/`, another lane's directory, or this file's rows for another lane.
- Do not delete the old result files; the re-emit supersedes them and they stay in history. Rule M19: no deletion
  logic anywhere.
- Record on your own face which executable answered - the runtime fields already present are `harness_version`,
  `toolchain_path` / `toolchain_version` where the lane has them. If your lane has no runtime stamp, say so in
  your report rather than inventing one: three of six lanes currently do not, and that gap is a published
  finding, not a defect to hide.

## Where the count goes

`python ci/process_leak_scan.py --repo-root .` prints the remaining occurrences by class. It read
`RETIRED:1143 IDENTITY:1134` when this dispatch was written. It reaches `FATAL=0` when all six rows above have
landed; until then the leg is red on purpose and the number is the countdown, not a failure.

## Erratum on the last row of this dispatch

It predicted `FATAL=0` once the six rows landed. Measured after they landed: `FATAL=2401`, of which `RETIRED=458`.
The prediction was wrong in two ways - it counted only the retired producer key while the leg also counts producer
*values*, host paths and profile paths, and it assumed every retired key lived in a face a lane can re-emit. Some
of it lives in captured evidence and in a frozen node face, which this project does not re-word. Composition,
named block by block, is in `evidence/S11/SG-F8-acceptance.md` and the corrected counts in `docs/FINDINGS-rev6.md`
M12.
