# Findings from the six-port run (contract rev6), grouped by mechanism

Every number in this file is a reading of `python ci/equality.py` on the canonical faces
`results/<port>.windows.x64/` at HEAD `f15b399`, host clock 2026-10-11 05:08 +0800. Six ports
(TypeScript/Node, Python, Go, Java, C#, Rust), one frozen spec, one Windows 10 build 19041 x64 host,
`LongPathsEnabled=0`, console code page 936.

Current reading: 44 required cells, 29 answered by every port. Of those 29, 12 are set aside because the
ports did not ask the same question (5 with different input bytes, 7 with a different `verdict_via` or
`path_form`), leaving **17 cells compared: 12 with no verdict disagreement, and 5 cells that carry 19
conflicting verdict facts between them**. 51 required cells have not been run by at least one port.
Nothing here is a completion claim; the gaps are listed by name in `docs/GAP.md`.

## M1 — one name, five different answers: `trail.` and `trail␣` (13 of the 19 conflicts)

The two names are `trail.` (T04) and `trailsp␣` (T05, a trailing space). The frozen sample is pinned by
`spec/cases.yaml`; the answers are not:

| what a port said | TypeScript | Python | Go | Java | C# | Rust |
|---|---|---|---|---|---|---|
| is the name legal on this OS | legal | legal | **illegal** | legal | legal | **illegal** |
| did the name arrive changed | **no** | yes | yes | (not recorded) | yes | yes |
| what the directory enumerates | `trail.` | `trail` | `trail` | `trail` | `trail` | `trail` |
| bytes on disk | 28 | 28 | 28 | (not recorded) | 28 | **0** |
| does the enumerated name stat back | yes | yes | **no** | (not recorded) | yes | (not recorded) |
| length triple | 6/6/6 | **6 and 5** | 6/6/6 | 6/6/6 | (not recorded) | 6/6/6 |

"(not recorded)" is printed as the gate prints it: a port that did not record that fact on that cell. It
is a completeness finding against that port, and the gate refuses to read it as agreement.

Reproduce one row at a time:

```
python ci/equality.py | grep "trap/T04 "
python -c "import os,glob; os.chdir(tempfile:=__import__('tempfile').mkdtemp()); open('trail.','wb').write(b'x'*28); print(os.listdir('.'), [os.path.getsize(n) for n in os.listdir('.')])"
```

What this shows, and what it does not:

- The strip set is a property of the API the port called, not of Windows. Two ports refuse the name at
  their legality layer while four create it; one port sees the name on disk unchanged; two report both
  the requested and the landed length. A checker written in any single one of these six would answer
  the customer's question "can I name a file this?" differently from the other five on the same machine
  in the same directory.
- It does **not** show which port is right. The spec asks for the OS answer; four of the six got it from
  the directory enumeration authority (the name the parent lists), which is the authority `spec/gate.md`
  pins, and two refused before reaching it. Whether the refusal is a language-side parse or an OS-layer
  answer is exactly the open question the two ports were asked to state in their self-check.
- `bytes_on_disk=0` from one port against `28` from three is the single most consequential row here: a
  pre-flight checker that reports zero bytes for a file it just created is either reading a different
  entry or reading before the flush. It is published as a conflict, not resolved, because both readings
  are self-consistent inside their own harness.

## M2 — `a<b.txt`: the legality question depends on which prefix you asked with (2 conflicts)

Five ports return `illegal` for T03 (`a<b.txt`) and one returns `legal`; the same split repeats on the
`T-CTRL-ILLEGAL-CHAR` control cell. The extended path form (`\\?\`) makes `<` a legal character, and the
port that probed legality through that form answered correctly for the form it used. That port was asked
to record which form it used in its own cell, and the gate now routes a cell whose `path_form` or
`verdict_via` differ into a named `incomparable` list instead of scoring it. The control cell also
produced `mechanism_class=unknown` from one port where five produced `illegal_char_filter`: a port that
declines to classify is published as declining, not as agreeing.

Reproduce:
```
python ci/equality.py | grep -E "T03|ILLEGAL-CHAR"
```

## M3 — the zip cell measured three different archives (2 conflicts)

T16 packs a file with the port's own zip writer and reads the entry name back. `bytes_written` came
back 28 from three ports, 296 from one, 292 from another. Same input name, same pinned payload, three
archive sizes: the writers differ in what they store (the UTF-8 flag, and whether the name is stored at
all or via an extra field), so the byte counts differ before any reader is involved.

Reproduce:
```
python ci/equality.py | grep "trap/T16"
```
This row is not a defect in the ports and not a defect in the spec. It is the reason the project's own
subject - a zip that arrives garbled on another machine - exists at all.

## M4 — what did not disagree, and why that matters more than the four mechanisms

Twelve of the seventeen compared cells produced no verdict disagreement at all:

`ctrl/T-CTRL-ASCII`, `trap/T06` (emoji), `trap/T07` (NFD), `trap/T08` (NFC), `trap/T09-m1`, `trap/T09-m2`
(the NFC/NFD coexistence pair), `trap/T12` (bidi U+202E), `trap/T13` (zero-width U+200B), `trap/T15`
(control character), `trap/T19-m1` (fullwidth), `trap/T19-m2` (Hangul jamo), `trap/T20` (`--force.txt`).

Six independent implementations of one spec, six different standard libraries, one byte-identical answer
on every Unicode-normalisation cell - the pair that produces the "Mac zip arrives garbled on Windows"
complaint is in that set twice. The cells that do *not* agree are the ones where the answer comes from an
API policy (trailing characters, illegal-character filtering) rather than from the file system's
normalisation rules. That split was not predicted in the spec; it fell out of the comparison.

Seven of the 29 shared cells are in neither the clean nor the conflicting set - they are
`incomparable`: `trap/T01` (`CON.txt`), `trap/T02` (`NUL.tar.gz`), `trap/T10` (`CON`), `trap/T11`
(`COM1.log`) and `trap/T14-m1..m3` (`PRN`, `AUX.log`, `LPT9`). One port answered those with
`verdict_via: none` - it has no OS-level legality channel on this host - while the other five answered
through Win32. Counting them as agreement or as disagreement would both be false, so they are published
as not comparable with the reason attached. A further five cells are `unpinned_input` (three control
cells whose samples the ports invented, and two length rungs whose filler bytes differ); those are the
cells the rev6 `control_samples` pin exists to fix on the next run.

The three-way cross-check (`ci/triangle.py`) reads the sealed expectation table, the six ports, and the
machine's own tools against each other: **66 expectation rows, six live ports,
`collective_misreadings=0`, `OUTCOME=CLEAN`** - there is no cell where all six ports agreed with each
other and disagreed with the expectation written before any port ran. That is the check that a shared
misreading would have to pass, and it passed on every row measured so far.

Reproduce:
```
python ci/triangle.py | tail -3
```

## M5 — process findings, kept because they are the reusable part

- The gate found four ports recording one fact in four shapes (hex vs text for a name; dict vs
  `15/15/15` vs `[15,15,15]` vs omitted for a length triple) and reported it as 29/29 disagreement.
  Fixing the comparison, not the ports, is what turned the number into 19.
- Six ports invented six identifiers for the same question (`B1` / `BLIND-1` / `T-BLIND-1`,
  `T09a` / `T09-m1`, `T17-GRID-B120-L137`). Completed work was reading as missing work until the
  spelling rules were written down and tested on both sides.
- The five control cells had names but no pinned bytes, so the calibration cells asked six different
  questions - including two different payloads hashed under one cell id. They are pinned in
  `spec/cases.yaml` now (`control_samples`).
- A required-cell manifest that carries the spec fingerprint went stale the moment the spec gained those
  samples. The generator's determinism arm caught it (`only in committed: []`, `only in regenerated: []`,
  same length, different bytes) rather than letting a fingerprint that no longer matches its source sit
  in a frozen contract.
- Two ports had no type-checker or no OS-legality channel available on this host; those absences are
  published as their own rows instead of being smoothed into agreement.

No absolute claim appears in this file without a command above it. Unmeasured cells are in
`docs/GAP.md` by name.
