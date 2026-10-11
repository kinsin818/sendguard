# `tool/check.py` — usage (rev6 shape)

Two questions, one file:

* **"Is this one name safe?"** → it asks this machine and prints the verdict block.
* **"Is this whole folder safe to send?"** → it enumerates the folder and prints one risk statement per
  name per target, without touching a single file.

This file documents the tool. `docs/tool-usage.md` describes the same tool as it stood before contract
rev6 (folder-only, no verdict/probe split); the owner froze `docs/` tonight, so it is left as he wrote it
and **this file is the current face**. Do not read the two as independent statements.

## Ask about one name (the morning deliverable)

```
python tool/check.py --name "trail."
python tool/check.py --name=--force.txt          # a leading dash needs the equals sign
python tool/check.py -- --force.txt              # ...or come after this separator
python tool/check.py --name-hex 6e622dc2a0       # the same name as UTF-8 hex, like spec/cases.yaml pins it
python tool/check.py --name "trail." --extended  # ask through the \\?\ prefix instead of the plain form
```

It creates the name in a fresh scratch directory **outside the repository**, enumerates, and prints:

```
VERDICT   os_legality_verdict, mechanism_class, verdict_via, phantom, name_mutated,
          enum_to_stat_agrees, roundtrip_ok, len_triple, bytes_written, bytes_on_disk, name_landed_as
PROBE     create_result, error_stage, error_code, read_result, longpath_mechanism, deps_*, elapsed_ms
```

Those two blocks are `ci/equality.py`'s `VERDICT_FIELDS` and `PROBE_FIELDS`, and the split matters when you
read the output: **the verdict is the answer about your name; the probe is what one language's standard
library happened to do**, which is allowed to differ between ports (spec/cell-identity.md 9.3). The field
names and the spellings of `name_landed_as` and `len_triple` are the gate's own: `canon_name` and
`canon_triple` are mirrored in this file and were checked against the gate's functions (36 comparisons,
0 mismatches — see `evidence/S10/tool-selfcheck.md`).

Three things the block always prints, on purpose:

* `criterion_for_that_word=...` — what `legal` was made to mean in this run. `os_legality_verdict=legal`
  is not "safe to send": a name can be legal and still land as a different name (see `trail.`).
* `verdict_via=win32` — the layer that was asked. spec/cell-identity.md 6 says a verdict without the tool
  named is not comparable, and the referee measured why: the same trailing U+00A0 name is stripped by the
  .NET layer and preserved by `cmd`. This tool asks Win32 through Python's own create call, so it stamps
  `win32` and nothing else.
* `RULE vs MACHINE` — the frozen rule set's answer, computed before the machine was asked, beside what the
  machine did. They can legitimately differ: if the rulebook has no cell for the name it says `unknown`,
  which is printed as silence, not as contradiction.
* `COMMITTED CELLS ASKED ABOUT THESE EXACT INPUT BYTES` — every canonical-face cell in `results/` that was
  asked about the same bytes, with a `VERDICT-DISAGREE` line wherever the ports or this tool answered a
  different word. On `trail.` this prints `go=illegal` against `csharp/java/python=legal`, which is a
  verdict-class disagreement, found from one command on one name.

## Drag and drop, or one argument

`tool/sendguard.bat` takes **one** argument and routes it:

| you give it | what happens |
|---|---|
| a folder | the folder report (enumeration only, no writes) |
| a file | the verdict block for that file's **name** |
| a path the plain form cannot address (a `CON.txt`, an orphan `trail.`) | the tool says the directory lists it and the path cannot address it, then prints the verdict for the name |
| a bare word that is not a path (`python tool/check.py CON.txt`) | the verdict block for that name |

The launcher runs `py -3` then `python`; it needs Python installed, and a downloaded `.bat` carries the
Mark of the Web, so Explorer will not run it until the user unblocks it. Neither the launcher nor the
unblock path is measured in this repository — see the honesty note in `docs/tool-usage.md`, which still
stands. Because the batch file ends in `pause`, its own exit code is the pause's, not the checker's: read
the printed report when you script on it, or call `check.py` directly.

## Ask the tool whether its own ruler works

```
python tool/check.py --controls       # the five pinned control_samples in spec/cases.yaml
python tool/check.py --selftest-spec  # every frozen trap sample through the rules, no disk writes
```

`--controls` compares against `evidence/S00-ctrl-baseline.md`, which FROZEN.md names as the only allowed
source of control expectations; nothing there is a criterion this tool invented. The columns it checks are
probe-class fields **on purpose**: a control cell calibrates the ruler (spec/gate.md 8). It prints
`INSTRUMENT-RED` at the top and exits 1 if any control misses the baseline, `CONTROLS-OK` and exits 0
otherwise. As of this writing all five match on this machine.

`--selftest-spec` prints which frozen samples the engine flags **and which it does not**, with the reasons
the misses are correct (a lone `é`-shaped name is measured legal and lands unchanged; those families only
become reportable as a pair, which is what the folder mode's collision rules do).

## Exit codes

| code | meaning |
|---|---|
| 0 | no risk | 
| 1 | risk found, or a control cell missed the sealed baseline |
| 2 | could not scan or probe (path missing, argument not a name) |
| 3 | bad usage |
| 4 | this tool crashed |

4 exists because an unhandled Python exception also exits 1, which is this tool's "risk found" answer.
A bug in the tool must never read as a verdict about your folder.

## What the tool will not do

* **Read the contents of a reserved device name.** `CON`, `PRN`, `AUX`, `NUL`, `COM1`-`COM9`, `LPT1`-`LPT9`
  are created and listed, never opened; the read is refused in the parent before the child is even spawned,
  and the field prints `roundtrip_ok=NOT-RECORDED` with the reason. An orphan `CON.txt` sits in the test
  folder and this tool has been run over it without hanging.
* **Delete anything.** Folder mode never writes. Name mode leaves one scratch directory per probe and prints
  its path (M19: no deletion logic). Expect litter after `--controls`: five directories.
* **Invent a status word.** Words come from spec/canonical.md (closed sets) and an unmeasured field prints
  `NOT-RECORDED`, which is spec/cell-identity.md 9.1's word for an absence — not a value, not a zero.
* **Speak anything but ASCII.** Every name is printed escaped (`\u202e`, `\x20`, `\U0001f600`), so a bidi or
  zero-width name cannot reorder the report line it appears in, and a cp936 console cannot garble it.
  Measured: zero bytes above 0x7F in every output captured in `evidence/S10/tool-selfcheck.md`.
* **Claim a verdict for a name it could not address.** `os.path.abspath` on `…\CON.txt` returns `\\.\CON`
  on this machine — Python hands your argument to the console device — so the tool splits the argument by
  hand and tells you when the canonicaliser disagreed with the path you typed.

## Reading the folder report

One line per (name, target): `name_hex`, the verdict fields, then `EVIDENCE backed_by=…`, then the risk
sentence. `unknown` means this project has no cell for it, never that nothing is known; the report header
prints the cell count per target, and macOS and Ubuntu have zero. A clean folder report does not cover
`zip_roundtrip`, does not see what a browser or cloud drive rewrites on the way out, and measures path
length at the location you scanned — the LIMITS block at the end says all of this in the output itself.
