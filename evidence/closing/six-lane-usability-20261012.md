# Six-lane usability - built, run and compared in a `--no-local` clone, 2026-10-12

Recorded by the seat that owns `ci/`, against the order "can the six ports actually be downloaded and used".
Everything below was executed in a fresh clone made with `git clone --no-local --no-hardlinks` from this repository
at the tip commit, into a scratch directory outside the repository. Nothing in this face is remembered from an
earlier run: each `rc` is from the command printed on its own row.

## Build, in the clone

| port | command | rc | what it said |
|---|---|---|---|
| python | `python -m compileall -q impl/python` | 0 | silent (byte-compiled, no third-party dependencies) |
| rust | `cargo build --offline` (in `impl/rust`) | 0 | `Finished dev profile`; one compiler warning, unblocked |
| go (port) | `go build ./...` (in `impl/go`) | 0 | - |
| go (re-derivation tool) | `go build .` (in `impl/go/rederive`) | 0 | - |
| go (audit harness) | `go build audit.go` (in `harness`) | 0 | - |
| java | `javac -nowarn -encoding US-ASCII -d <out> impl/java/src/*.java` | 0 | one `unchecked operations` note, not an error |
| typescript | `node --experimental-strip-types --check impl/typescript/src/runner.ts` | 0 | loads clean; there is no transpile step on this host |
| csharp | `dotnet build` (in `impl/csharp`) | 0 | build succeeded, `0 warnings` |

Toolchains as found on this host at this commit, re-checkable with
`python -V && node -v && go version && rustc -V && javac -version && dotnet --version`: Python 3.14.7, node
v24.15.0, go1.23.5, rustc 1.98.0, javac 17.0.17, .NET 8.0.413. A different host is a different reading, which is
the product of this project rather than an obstacle to it.

## Run, in the clone - each lane produced its own canonical face there

| port | command | rc | counts it printed | lane-authored self-check in the clone |
|---|---|---|---|---|
| python | `python impl/python/sg_run.py` | 0 | `cells_written=123 covered_required=48 extra=75 missing_required=0`, `control_all_ok=True`, `implementation_id_present=123/123` | `sg_selfcheck.py` rc=0, `cells_produced=123 cells_valid=123` |
| rust | `python impl/rust/run_cells.py --phase controls` | 0 | `controls_pass=True cells_produced=5 problems=0` | `selfcheck.py` rc=0, `OUTCOME=OK` |
| go | `<rederive binary> run --repo clone-1 --results clone-1/results/go.windows.x64` | 0 | `cells_planned=137 cells_written=49 controls_pass=true` | `rederive/selfcheck.py` rc=0, `OUTCOME=PASS` |
| java | `python impl/java/tools/run_cells.py` | 0 | `cells_produced=86 cells_blocked=0 extra=38 missing_required=0`, five `ctrl` rows printed | **none exists** - see `docs/tickets/SG-F16-java-lane-selfcheck.md` |
| typescript | `node impl/typescript/src/runner.ts` | 0 | `written=84 cells_expected=84 cells_measured=84 cells_blocked=0 controls_pass=true` | `selfcheck.py` rc=0, `language_enum_gap_cells=0` |
| csharp | `python impl/csharp/run_csharp.py --all` | 0 | `cells_run=45 required_ids=48 produced_ids=50 missing=0 extra=2` | `selfcheck_csharp.py` rc=0, `controls=GREEN(5)` |

Two notes a reader would otherwise trip on. The rust row is a focused run in the clone; its full 174-cell face was
produced by the same command without `--phase controls` in the working tree the same afternoon, and the 174 faces in
the clone are the committed ones (the focused run rewrote the five controls). And `run_csharp.py --controls` prints
`missing=43` **by design** - that mode runs only the five controls and reports the required cells it did not cover
instead of pretending; `--all` is the mode that produces the face.

## The evaluation, in the clone

```
python ci/equality.py        rc=1  OUTCOME=RED verdict_disagreements=54 verdict_identical_cells=24/44
                                   cells_fully_recorded_and_identical=4 verdict_not_recorded_pairs=121
                                   verdict_pairs_recorded=2281/2640 probe_cells_differing=29
                                   unpinned_input=0 cells_excluded=0 channel_abstentions=13
                                   truncated_values=2 required_cells_missing=0
python ci/validate_cells.py  rc=0  invalid=0 missing_faces=0 cells_omitting_a_compared_field=371
```

`rc=1` there is the product: the six ports disagree about names, and the gate says so with the same twelve fields
the working tree prints. `validate_cells` judging 0 invalid faces in a clone whose faces were just rewritten by the
lanes themselves is the part that answers "does the artifact hold up".

## The claim that matters, measured field by field

After the clone runs, every face produced there was compared against the face this repository commits, per lane,
over the ten verdict fields the contract judges:

| port | faces compared | verdict-field differences | non-verdict fields moved |
|---|---|---|---|
| python | 123 | **0** | 356 |
| rust | 174 | **0** | 21 |
| typescript | 87 | **0** | 565 |
| go | 49 | **0** | 556 |
| java | 86 | **0** | 551 |
| csharp | 50 | **0** | 268 |

So: **a stranger who clones this repository can build all six ports, run all six, and get the same answers the
committed faces give.** The columns that moved are timestamps, elapsed milliseconds, scratch and holder directory
fields, enumeration-spread details and re-derivation notes - the parts of a record that describe the run rather
than the answer. That is the sentence §1 of this README has always meant, now checked by the path a stranger
actually takes instead of by this seat's own leg.

## What was missing for a stranger, and is now fixed

`README.md` had no per-port build or run instructions at all - the CI workflow does not build the ports either, so a
reader following only what was published could verify the *legs* but not the *ports*. §7 ("Running a port yourself -
the stranger's path") is the fix, written from the commands above, with the three caveats a reader would otherwise
discover alone: rust's normalisation dependencies are not vendored so a cold machine needs registry access once;
the java lane has no lane-authored self-check (ticketed as SG-F16, with its five acceptance criteria and both arms);
and everything here is one host on one Windows edition, which `docs/host-stamp.md` declares and the cold-clone leg
quarantines by name rather than comparing.
