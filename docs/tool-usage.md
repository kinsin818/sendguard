# Using `tool/check.py`

A folder pre-flight check: point it at a folder, it prints which **file names** in that
folder may not survive the trip to a client's machine.

It is a thin human-facing layer over the frozen rule set in `spec/cases.yaml` and the closed
vocabulary in `spec/canonical.md`. It reuses neither the measurement harness nor any of the
six language ports: it is standalone stdlib Python and imports no third-party package.

## Run it

```
python tool/check.py <folder>
python tool/check.py <folder> --target windows      # or macos | ubuntu | linux | all
python tool/check.py --selftest-spec               # does the engine flag the frozen samples?
```

`--target` defaults to **all three**, because "wherever it is going" is the normal case for a
send. Name one target when you know the recipient's machine.

`tool/sendguard.bat` is a two-line launcher so a Windows user can drag a folder onto it.
The folder path becomes the argument; anything else you add after it is passed through.

### Does double-click actually work?

No guarantee, and this file will not pretend otherwise:

* The launcher needs Python on the machine. It tries the `py` launcher first, then `python`.
  With neither installed, the window opens, says the command is not recognised, and waits for
  a keypress. That is a missing prerequisite, not a bug in the checker.
* A downloaded `.bat` carries the Mark of the Web. Explorer will not run it until the user
  right-clicks, Properties, **Unblock**; browsers warn about downloading batch files at all,
  and SmartScreen can interpose a reputation warning. **None of this is measured in this
  repository** - there is no test of an unsigned download, no signed code-signing certificate,
  and `docs/evidence.md` lists unsigned-executable launch behaviour as not evidenced.
* What is safe to promise without any of that: `python tool/check.py <folder>` from a terminal,
  on any machine that has Python 3. If you are shipping this to a non-technical client, ship
  the folder and that one line, or zip it and tell them to unblock - and say you did not test
  the download path yourself.

## Exit codes

| code | meaning |
|---|---|
| 0 | scanned, no risk found |
| 1 | scanned, at least one risk found |
| 2 | could not scan (path missing or unreadable) |
| 3 | bad usage |
| 4 | this tool crashed |

4 exists because Python's own unhandled-exception exit code is 1, which is this tool's
"risky names" answer. A bug in the tool must never read as a verdict about your folder, so
`run()` traps it, prints the traceback, and returns 4 instead.

## Reading a line

```
  ./trailsp\x20  target=windows  mechanism_class=path_preprocessing_policy
      os_legality_verdict=legal  backed_by=T04 [16 cells, 4 ports]
      risk: will probably be renamed to trailsp on the recipient's machine
```

* **Every printed line is a risk statement, not an error.** `os_legality_verdict=legal` with a
  risk line is normal and is the whole point: the name is allowed, and it still changes on the
  way to the client. Nothing in this tool says "broken" about a name that a browser or drive is
  known to rewrite silently; it says **will probably be renamed to X**, and X is computed from
  the Unicode data or from the measured stripping behaviour, never guessed.
* `mechanism_class` and `os_legality_verdict` are words from `spec/canonical.md` sections 10 and 6.
  The tool adds none.
* `backed_by` names the frozen traps that have result cells on disk for that target, with how
  many cells and how many ports produced them. `backed_by=none` means no cell covers it.
* `os_legality_verdict=unknown` means **this project has not measured it**, not "nobody knows".
  For `macos` and `ubuntu` that is every line: there are zero result cells for those operating
  systems in this repository (README section 2), so the prose says what the public
  specification claims and labels it as unmeasured. Read the header block of every report -
  it prints the cell count per target.
* `path_form=plain|extended` appears on length findings: the same path is refused in the plain
  form and accepted through the `\\?\` prefix or a long-path-aware manifest. That is measured
  (T18-plain vs T18-extended), and it matters because you cannot make the recipient's Explorer,
  browser or mail client opt in.

## What a clean report does not prove

The report ends with a `LIMITS` block, and it is not boilerplate to skim:

* `zip_roundtrip` is out of reach from a folder listing - it lives in the archive's header flag
  bits, so a `.zip` in the folder can still unpack into a name that fails.
* The tool sees names **as the filesystem reports them**. What a browser, cloud drive or mail
  gateway rewrites on the way out is not measured here. Two of the cases in the self-check
  never reached the tool at all for exactly this reason (see `evidence/S10/tool-selfcheck.md`).
* exFAT/FAT32 volumes, phone storage, and whether the recipient has long paths enabled are
  per-machine. The 260 figure is the classic plain-form budget, and the tool measures the path
  **at the location you scanned**.
* Collision rules (`case_folding`, `unicode_normalization`) need two names in the same folder to
  fire. A single legal-looking name stays silent on purpose; a checker that reported every
  frozen trap against a clean folder would be a false-positive machine, which is why
  `--selftest-spec` prints the not-flagged list instead of hiding it.

## Two safety properties, on purpose

* **The tool never opens, reads, writes or stats a scanned name.** It only enumerates. A
  reserved device name (`CON`, `NUL`, `AUX`, `COM1`-`COM9`, `LPT1`-`LPT9`) can block an open on
  Windows, so the folder it checks may contain files the checker itself must not touch. Do not
  add `open()`, `os.stat`, `shutil` or `send2trash` to this file without re-testing against a
  folder holding a real `CON.txt`.
* **Output is ASCII only.** Names are printed escaped (`\u202e`, `\x20`, `\U0001f600`), so a
  bidi or zero-width name cannot reorder or truncate the report line it appears in, and a
  console on code page 936 cannot garble it. Unescaped, a single U+202E in a folder would
  corrupt the rest of the page the user is reading to decide whether to send.
