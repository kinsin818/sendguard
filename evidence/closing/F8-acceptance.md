# SG-F8 acceptance - six lanes re-emitted, and what the purge could not reach

Accepted 2026-10-12 by the seat that owns `ci/`, against `docs/tickets/SG-F8-public-interface-process-metadata.md`
and `docs/tickets/SG-F8-dispatch-20261012.md`. Every number is from this session's captured output.

## Per-lane report (the three lines the dispatch asked for, one block per lane)

```
python-port   re-emitted: 123 records (73 purged through the runner's migrate path, 50 measured fresh) at this commit
              unchanged:  disagreements=54 identical=24/44 fully-recorded=4 not-recorded=121  (face-level verdict diff vs HEAD: 0 differences in 123 records x 10 fields)
              worker_id:  0 occurrences left in my canonical face   (leg: results/python.windows.x64 files=123 retired=0 implementation_id={'python-port': 123})

rust-port     re-emitted: 174 records at this commit
              unchanged:  same four readings; controls_pass=true; face-level verdict diff vs HEAD = 0 differences
              worker_id:  0 occurrences left (files=174 retired=0 implementation_id={'rust-port': 174})

typescript-port re-emitted: 84 records at this commit
              unchanged:  same four readings; controls_pass=true; verdict diff vs HEAD = 0 differences
              worker_id:  3 occurrences left - named below, in records the current runner does not produce

go-port       re-emitted: 49 records into results/go.windows.x64 at this commit
              unchanged:  same four readings; controls_pass=true
              worker_id:  0 in the canonical face (files=49 retired=0 implementation_id={'go-port': 49})

java-port     re-emitted: 86 records at this commit
              unchanged:  same four readings
              worker_id:  0 (files=86 retired=0 implementation_id={'java-port': 86})

csharp-port   re-emitted: 50 records at this commit
              unchanged:  same four readings; required_ids=48 produced_ids=50 missing=0
              worker_id:  0 (files=50 retired=0 implementation_id={'csharp-port': 50})
```

The gate's four readings after all six lanes:
`OUTCOME=RED verdict_disagreements=54 verdict_identical_cells=24/44 cells_fully_recorded_and_identical=4
verdict_not_recorded_pairs=121 verdict_pairs_recorded=2281/2640 probe_cells_differing=29 unpinned_input=0
cells_excluded=0 channel_abstentions=13 truncated_values=2 required_cells_missing=0` - byte-equal to the reading
published before the re-emit, which is what the dispatch required: the producer key is not a verdict field, so a
purge must not move a number.

## Emitter lines actually changed: 17, not 16

The ticket's rows sum to 17 (`python 5+1+1`, `rust 3+1`, `typescript 2`, `go 1+1`, `java 1`, `csharp 1`), and 17 is
what the tree contained. My own earlier note said "16 emitter lines"; that was wrong and the correction is here
rather than in a silent edit. The re-emit also needed **five more sites** the count did not name, because renaming
a published key is not only the write:

- `impl/rust/run_cells.py:1020,1022` - the lane's own provenance reader compares the key to decide whether a face
  is its work; left alone it would have skipped every one of the lane's new records.
- `impl/rust/run_cells.py:679` - the value passed to the child (`--worker` is now handed the lane value).
- `impl/go/main.go:94` and its six `WorkerID:` construction sites - the published key lived in a struct tag, so the
  Go field moved with it (`ImplementationID`), and the seat code `W-GO` was rewritten out of four comments and one
  emitted note string.
- `impl/python/sg_run.py` `migrate()` - see the next section; without it the runner re-measures 50 records and
  carries the retired key forward in the other 73.

## The purge is a rename in the emitter, and the leg proves it

`sg_run.py`'s migration path now renames the key on the way through, appends the reason to the record's existing
`rev3_migration_notes`, and does **not** carry the superseded value forward (it named a seat, not a lane). The
runner prints the result instead of being quoted:

```
cells_remeasured=50 cells_migrated_from_disk=73 cells_total=123
producer_keys_purged=73 records_still_carrying_retired_key=0 implementation_id_present=123/123
```

## RETIRED went 1143 -> 577; zero is not reachable by this route, and here is the composition

`python ci/process_leak_scan.py --repo-root .` fatal-by-class before the re-emit and after:

| run | files_scanned | FATAL | HOSTROOT | IDENTITY | LOGIN | RETIRED |
|---|---|---|---|---|---|---|
| before, original needles | 1195 | 2305 | 13 | 1134 | 15 | 1143 |
| after python only, original needles | 1198 | 2059 | 13 | 1011 | 15 | 1020 |
| after python only, **needles fixed** | 1198 | 3480 | 338 | 1011 | 1111 | 1020 |
| after all six lanes, needles fixed | 1198 | 2530 | 274 | 568 | 1111 | 577 |

The re-emit and the needle fix are two different changes and the table keeps them apart, because the middle two
rows differ by nothing except the ruler.

Remaining `RETIRED`, by where it lives (the leg's own `scan_face`, counted per record):

| block | records | why it stands |
|---|---|---|
| `results/go.windows.go1.23.5/` | 154 | that face is written by `impl/go/main.go`, whose root is **hardcoded to a different checkout**; running it here is `SG-F15`, not this ticket |
| `results/python/` | 211 | written by `impl/python/sg_python.py`, whose `assert len(cases) == 20` now fails against the sealed spec (`parsed 25`); it is a superseded S02-era emitter and cannot re-answer 212 records at the current contract without an assertion change that is not a purge |
| `evidence/recovered/` | 78 | recovered captures. A capture is not prose this seat may re-word |
| `results/node.windows.22.22.2.json` + `results/node/` | 73 | the node lane's face, which the dispatch declares frozen history under an earlier contract; node is not one of the six |
| `evidence/S02/` | 25 | captures, including the `VOID-run1/` records whose whole purpose is to preserve a bad run |
| `results/typescript.windows.x64/` | 3 | `tapi__TAPI-T01__entry-{appendFileSync,createWriteStream,writeFileSync}.json` - records the current runner no longer produces; they carry no producer key of either name, so they are an unproduced stale face, not a mislabeled one |
| rule/prose faces (`docs/tickets/`, `ci/`, `docs/claim-boundary.md`, `spec/`) | 13 | these are the sentences that **name** the retired key in order to retire it; the leg routes them to `mentioned`, not fatal |

So `RETIRED=0` needs one of three things this seat is not authorised to do unilaterally: re-measure 365 records
with two emitters that no longer match the sealed contract, rewrite 103 captured evidence faces, or delete the
node lane's frozen face. The route that does work is `SG-F15` (154 records, a real defect with a real fix) plus a
decision about `impl/python/sg_python.py` (211 records: retire the emitter's faces, or let it grow an assertion
that matches the sealed spec). That decision is on the row below, not made here.

**The three typescript residues are named, not averaged away**, because a report that says `0` without the line
is treated as not done - which is the dispatch's own rule and the reason it exists.

## One untracked face the leg cannot see, reported rather than removed

`impl/python/sg_restamp_note.txt` (11,950 B, mtime 2026-10-11 13:08) is another lane's work note, left in the
tree by an earlier session. It carries a host profile path in a `scratch_root=` line, and because
`process_leak_scan.py` enumerates the **tracked** set, an untracked face is invisible to it: `files_scanned=1198`
does not include it. Nothing was deleted (M19); it is named here so the next reader can see the blind spot has a
name and a size.

## The needle fix, which is the finding I most want kept from this leg

While attributing a `+3` movement for SG-F11, I found that `ANY_PATH`-style needles in
`ci/process_leak_scan.py` compared the *unescaped* spelling of a path against faces that escape their
separators. A `.json` face writes `C:\\Users\\x`, and the leg only looked for `C:\Users\x`, so every path inside a
data face was invisible to it. `_paths_of()` now builds every separator spelling through `_escaped_forms()`, and
24 arms cover it in both directions - one of which (`A13` of that leg) asserts the form builder itself produces
the escaped spelling, because the fixture had been hand-written with the same omission as the rule and could not
catch it.

The effect is a measurement change, not a disclosure change: `LOGIN 15 -> 1111` and `HOSTROOT 13 -> 338`. The
deliverable contained those paths this morning too; the leg could not see them. The published count understated
the exposure by two orders of magnitude, and it is the second time this week a green leg was found to be reading
a tree or a form it was not looking at.
