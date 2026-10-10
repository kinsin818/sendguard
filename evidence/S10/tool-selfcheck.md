# S10 — tool self-check (`tool/check.py` run against a planted folder)

Run: 2026-10-11 04:57 +0800, on Windows 10 build 10.0.19041 / AMD64, Python 3.14.7.
Repository commit under test: `298d6e4`. Tool face: `tool/check.py`, 42,985 bytes, 880 lines,
sha256 `eddb83be9907f3a721c3748f043ef5e13b10d59dbf08b5a7021515f46573734d`.
Launcher face: `tool/sendguard.bat`, 74 bytes, CRLF, two lines.
Rules face: `spec/cases.yaml` sha256 `a7f9a57df1b4…` — **matches** the hash published in
`spec/FROZEN.md`; the tool prints that comparison in every report header, so this claim is
re-runnable and not a promise made here.

**Nothing in this file is committed.** The three faces are on disk in `tool/`, `docs/tool-usage.md`
and this file; `git status` shows them untracked. I did not commit because the other five port
seats are working in this same working tree and a path-scoped commit here moves their shared index.

Synthetic folder (created, **not deleted** — see CLEANUP at the end):

    D:\sendguard-work\tool-selfcheck-68b75721b2ac        (root path = 45 characters)

It is outside the repository (N12: forbidden names are never materialised inside the repo).

## Safety method, stated before the results

* Every run was a **child process** (`subprocess.run([python, tool, folder])`) with an
  **external 90 s timeout**. The tool itself has no in-process timeout; nothing was ever called
  in-process that could touch a device name.
* The tool **never opens, reads, stats or writes a scanned name**. Audited: exactly one
  filesystem `open()` exists in `tool/check.py`, at line 194 inside `_read_bytes()`, and its four
  call sites are `spec/cases.yaml` (line 106), `spec/FROZEN.md` (114), `load_cases()` (123) and
  `results/**` cells (163). No call site receives a path from the enumerated folder. Enumeration
  is `os.scandir` plus `DirEntry.is_dir()`, which reads attributes already cached by the
  directory enumeration on Windows, so it does not re-open the file.
* Reserved names were **created and listed only**. The folder still contains a real
  `CON.txt` (hex `434f4e2e747874`, the byte-exact T01 sample) and the tool reported it with no
  hang: `default_all` returned in 0.3 s.
* Creating a file whose name Windows refuses to normalise away required the extended prefix.
  `os.path.abspath()` / `os.path.join()` **strip trailing dots and spaces** — my first planting
  attempt silently created `trail` when it meant to create `trail.`, and lost the trailing space
  of `trailsp `. Recorded because it is the same rewriting the product is about, hitting the
  test harness first.

## Planted cases

Names are given as UTF-8 hex (N12). Where a trap sample exists in the frozen table, the planted
name is **byte-equal to that sample**, not a hand-typed lookalike — checked by decoding
`spec/cases.yaml` and comparing.

| # | planted name (escaped) | hex | trap sample | creation | on disk as |
|---|---|---|---|---|---|
| 1 | `CON.txt` | `434f4e2e747874` | T01 exact | `\\?\` prefix | `CON.txt` |
| 2 | `a<b.txt` | `613c622e747874` | T03 exact | refused | **nothing** (creation failed, see below) |
| 3 | `photo:front.jpg` | `70686f746f3a66726f6e742e6a7067` | — (colon = macOS-illegal) | accepted | **`photo`** + a hidden NTFS stream |
| 4 | `trail.` | `747261696c2e` | T04 exact | `\\?\` prefix | `trail.` |
| 5 | `trailsp ` | `747261696c737020` | T05 exact | `\\?\` prefix | `trailsp ` |
| 6 | `nb- ` | `6e622dc2a0` | — | `\\?\` prefix | `nb-\u00a0` |
| 7 | `fw-　` | `66772de38080` | — | `\\?\` prefix | `fw-\u3000` |
| 8 | `L`×246 + `.txt` | 250 code points / 250 UTF-16 units / 250 bytes | — | `\\?\` prefix | same, full path 296 chars |
| 9 | 10 nested dirs of 18 chars + `deep-target.txt` | total path 251 | — | `\\?\` prefix | same |
| 10 | 13 nested dirs of 20 chars + `past260.txt` | total path 330 | — | `\\?\` prefix | **partly unreachable** (see MISSED) |
| 11 | `resume-e\u0301.txt` | `726573756d652d65cc812e747874` | T09a exact | plain | same |
| 12 | `resume-\u00e9.txt` | `726573756d652dc3a92e747874` | T09b exact | plain | same (planted as the twin of #11) |
| 13 | `ㄱㄴㄷ.txt` | `e384b1e384b4e384b72e747874` | T19b exact | plain | same |
| 14 | `ＡＢＣ.txt` | `efbca1efbca2efbca32e747874` | T19a exact | plain | same |
| 15 | `bidi-\u202e.txt` | `626964692de280ae2e747874` | T12 exact | plain | same |
| 16 | `zerowidth-\u200b.txt` | `7a65726f77696474682de2808b2e747874` | T13 exact | plain | same |
| 17 | `--force.txt` | `2d2d666f7263652e747874` | T20 exact | plain | same |
| 18 | `emoji-\U0001f600.txt` | `656d6f6a692df09f98802e747874` | T06 exact | plain | same — **negative control**, must stay silent |
| 19 | `report-2026.txt` | `7265706f72742d323032362e747874` | — | plain | same — **negative control** |
| 20 | `sub/notes.md` | `6e6f7465732e6d64` | — | plain | same — **negative control**, also the clean-folder run |

Two rows were **not plantable on this volume**, and I am not counting them as detections:

* **#2 `a<b.txt`** — `OSError [Errno 22] Invalid argument` even with the `\\?\` prefix. NTFS
  refuses `<` at its own level, so the Win32 parser is not the only gate. Consequence for the
  product: **a folder on a Windows machine can never contain a Windows-illegal character**, so
  `illegal_char_filter` cannot be verified by scanning a Windows folder; it can only be verified
  against a *list* of names coming from somewhere else (a manifest, an unzip, another volume).
  It is exercised that way in `--selftest-spec` below.
* **#3 `photo:front.jpg`** — creation "succeeded", and the result on disk is a 2-byte file named
  `photo` with `front.jpg` living as an **NTFS alternate data stream**. `os.scandir` reports
  `photo` and nothing about the stream. So the risk was realised *before* the tool could see it,
  and a checker that reads a Windows folder afterwards cannot know it happened.

## Run matrix

Each row is one child-process run with an external 90 s timeout. `nonascii` counts bytes > 0x7F
in stdout — zero in every run, which is the "a cp936 console cannot garble this" property, measured.
Each stdout was written to a file and read back for byte equality before being counted.

| run | argv | exit code | stdout bytes | nonascii | elapsed |
|---|---|---|---|---|---|
| default_all | `<folder>` | **1** | 13,722 | 0 | 0.3 s |
| windows | `--target windows <folder>` | **1** | 11,207 | 0 | 0.2 s |
| macos | `--target macos <folder>` | **1** | 3,969 | 0 | 0.2 s |
| ubuntu | `--target ubuntu <folder>` | **1** | 3,560 | 0 | 0.2 s |
| clean_subfolder | `<folder>\sub` | **0** | 2,316 | 0 | 0.2 s |
| selftest_spec | `--selftest-spec` | **0** | 3,130 | 0 | 0.2 s |
| no_arguments | (none) | **3** | 0 (usage on stderr) | 0 | 0.2 s |
| missing_folder | `<folder>\no-such-dir` | **2** | 0 (message on stderr) | 0 | 0.2 s |
| bat_launcher | `cmd /c tool\sendguard.bat <folder>\sub` | **0** | same report + `pause` | n/a | 0.6 s |

Exit codes are documented in the report footer and in `docs/tool-usage.md`:
`0=no risk 1=risk found 2=scan failed 3=bad usage 4=this tool crashed`.
Code 4 exists because an unhandled Python exception also exits 1 — the same value as "your folder
has risky names". Without the `run()` wrapper, a bug in the tool would be indistinguishable from a
finding by any script that branches on the code. That bug was not hypothetical: see DEFECTS BELOW.

## The tool's output line for each planted case

Taken verbatim from the `default_all` run (exit code 1). Only the field line is quoted; the
`risk:` prose that follows each line is in the full report.

```
./CON.txt  target=windows  mechanism_class=reserved_device_name  os_legality_verdict=illegal  backed_by=T01,T02,T10,T11,T14 [68 cells, 7 ports]
./trail.  target=windows  mechanism_class=path_preprocessing_policy  os_legality_verdict=legal  backed_by=T04,T05 [20 cells, 7 ports]
./trailsp\x20  target=windows  mechanism_class=path_preprocessing_policy  os_legality_verdict=legal  backed_by=T04,T05 [20 cells, 7 ports]
./nb-\u00a0  target=windows  mechanism_class=path_preprocessing_policy  os_legality_verdict=unknown  backed_by=none
./fw-\u3000  target=windows  mechanism_class=path_preprocessing_policy  os_legality_verdict=unknown  backed_by=none
./LLLL…LLLL.txt  target=windows  mechanism_class=component_length_limit  os_legality_verdict=legal  backed_by=T18-extended [1 cells, 2 ports]  path_form=extended
./LLLL…LLLL.txt  target=windows  mechanism_class=component_length_limit  os_legality_verdict=illegal  backed_by=T18-plain,T-CTRL-NAMETOOLONG [2 cells, 7 ports]  path_form=plain
./LLLL…LLLL.txt  target=windows  mechanism_class=component_length_limit  os_legality_verdict=legal  backed_by=T18-extended [1 cells, 2 ports]  path_form=extended
./aaaaaaaaaaaaaaaaaa/…/deep-target.txt  target=windows  mechanism_class=component_length_limit  os_legality_verdict=legal  backed_by=T18-plain [1 cells, 2 ports]  path_form=plain
./resume-e\u0301.txt  target=macos  mechanism_class=unicode_normalization  os_legality_verdict=unknown  backed_by=none
./resume-e\u0301.txt  target=ubuntu  mechanism_class=unicode_normalization  os_legality_verdict=unknown  backed_by=none
./resume-\u00e9.txt  target=macos  mechanism_class=unicode_normalization  os_legality_verdict=unknown  backed_by=none
./bidi-\u202e.txt  target=windows  mechanism_class=bidi_handling  os_legality_verdict=legal  backed_by=T12 [9 cells, 7 ports]
./zerowidth-\u200b.txt  target=windows  mechanism_class=zero_width_handling  os_legality_verdict=legal  backed_by=T13 [9 cells, 7 ports]
./--force.txt  target=windows  mechanism_class=unknown  os_legality_verdict=legal  backed_by=T20 [9 cells, 7 ports]
. [pair]  target=windows  mechanism_class=unicode_normalization  os_legality_verdict=unknown  backed_by=T06,T07,T08,T09 [48 cells, 7 ports]
. [pair]  target=macos  mechanism_class=unicode_normalization  os_legality_verdict=unknown  backed_by=none
. [pair]  target=ubuntu  mechanism_class=unicode_normalization  os_legality_verdict=unknown  backed_by=none
```

Plus five more `component_length_limit` lines for the intermediate directories of the two deep
chains (they are entries too, and each has its own path length), and the enumeration failure line:

```
cannot enumerate ./qqqqqqqqqqqqqqqqqqqq/…/qqqqqqqqqqqqqqqqqqqq  errno=2 message suppressed (localised on this build)
```

Two wordings worth reading closely, because they are the product requirement rather than cosmetics:

* `./trail.  …  risk: will probably be renamed to trail on the recipient's machine` — the target
  name is not a guess, it is what the frozen cells recorded (T04 landed as `747261696c`,
  T05 landed as `747261696c7370`).
* `./resume-\u00e9.txt  target=macos  …  risk: will probably be renamed to resume-e\u0301.txt …`
  followed by *`the rewritten form is computed from Unicode data, not observed`*. macOS has zero
  measured cells here, so the verdict word stays `unknown` even though the sentence names an X.
  Saying "broken" would be a lie; saying nothing would hide the rewrite.

## DENOMINATORS

Definitions, since the numbers are worthless without them: *planted* = a row that was attempted in
the folder; *detected* = at least one finding line carries that entry's escaped name;
*missed* = planted, enumerated, and no line; *false positive* = a finding line attached to a
negative control.

The 18 counted rows are table rows 1-9 and 11 and 13-20. **Table row 10 (the past-260 probe) and
table row 12 (the NFC twin) are not counted**: row 10 is reported separately as MISSED #4 because
it is a partial detection, and row 12 exists only to make row 11 a pair - it is where a finding
lands, not a case to detect.

```
cases_planted=18        (15 risk rows + 3 negative controls)
cases_detected=11       (of the 15 risk rows)
cases_missed=2          (jamo name, full-width ABC: enumerated, silent)
false_positives=0       (all three negative controls produced no line)
not_plantable=2         (row 2 `a<b.txt` refused by NTFS; row 3 `photo:front.jpg` rewritten into a stream at creation)
```

11 + 2 + 2 = 15, so the risk rows are fully accounted for. Report-level denominators printed by
the tool itself in the same run (a different unit: entries and lines, not planted cases):

```
entries_enumerated=52  entries_checked=51  entries_with_risk=17  entries_clean=34
findings=23  findings_by_target=windows=18 macos=3 ubuntu=2
findings_backed_by_a_measurement_cell=16  findings_unverified(os_legality_verdict=unknown)=8
```

## MISSED — left in the report, not tuned away

1. **`ㄱㄴㄷ.txt` (T19b sample) — no line.** The collision rules need a twin; I planted the jamo
   name alone. A lone name in this family is measured legal and lands unchanged (T19a/T19b cells),
   so inventing a per-name rule would be inventing a risk the frozen table does not carry. The
   honest reading is *both*: the tool is silent here, and a silent tool is how a client learns
   about it later.
2. **`ＡＢＣ.txt` (T19a sample) — no line.** Same reason: full-width ABC folds to `ABC` under NFKC,
   but no `ABC.txt` was planted, so nothing collides.
3. **`photo:front.jpg` — no line, and none is possible.** The colon name never existed on disk as
   that name (see above). `photo` is a perfectly legal name. No folder scanner can report this
   event after the fact.
4. **`past260.txt` (the deliberately-over chain) — directories reported, leaf not reached.** The
   tool enumerated 11 of the 14 levels, printed path-length findings for them, then failed to
   enumerate deeper and printed one `cannot enumerate … errno=2` line in LIMITS. So the *worst*
   member of the folder is the one the tool could not inspect, and the report only says so in a
   footnote. A client reading `entries_clean=34` would not learn that 3 entries beyond the plain
   path limit were invisible to the check. **This is the most dangerous gap in the tool and it is
   not fixed here**, because fixing it means the tool takes over the long-path problem it is
   reporting on.

## Coverage gaps in my own evidence, stated rather than smoothed over

* Two of the three collision branches never fired on disk: `casefold` (NTFS is case-insensitive,
  so `A.txt` and `a.txt` cannot coexist in one folder — untestable on the only OS with measured
  cells) and `NFKC` (the pair I did plant, `resume-e\u0301.txt` / `resume-é.txt`, folds identically
  under NFC and NFKC, and the code reports a pair once, so the NFKC text never got exercised).
  Only the NFC branch is proven by a real folder. Both unproven branches ship.
* `--selftest-spec` is the only thing that touches the `illegal_char_filter` rule at all, for the
  reason in row 2 above.
* `zip_roundtrip` is not covered by the tool in any form; it prints that as the first LIMITS line.

## Spec self-test (`--selftest-spec`, exit code 0)

Same rules, run against the 22 decoded frozen samples, nothing materialised:

```
traps_in_spec=20  samples_decoded=22  samples_not_decodable=2
samples_flagged=14  samples_not_flagged=8
traps_with_at_least_one_flagged_sample=12  traps_without=8
NOT DECODABLE T17, T18 — sample_hex is a label ("T-LEN-PATH (length bisection, G1-G4)"), not UTF-8 hex
NOT FLAGGED T06 T07 T08 T09a T09b T16 T19a T19b
```

T17/T18 cannot be decoded: their `sample_hex` fields hold a description, not hex. That is a defect
in the frozen table, not in the tool, and the tool prints it instead of working around it.

## Defects found and fixed during this self-check (each one shipped broken first)

1. `WIN_ILLEGAL_CHARS` was written as a space-separated list, `'<>: "|?*'`, and so contained a
   literal space. Every name with a trailing or interior space therefore got a bogus
   `illegal_char_filter` finding — `trailsp ` (row 5) is the planted victim, and that build would
   have scored `false_positives=1`. The string is now `'<>:"|?*'` (seven characters,
   no space), and the shipped build above scores 0. Caught only because the frozen samples were
   run through the engine, not because the folder was inspected by eye.
2. `length_rules()` was called with 5 arguments against a 4-parameter definition: every scan
   crashed. Compile-time invisible (it is a runtime arity error), caught by the first real run.
3. After refactoring the evidence lookup, findings with no backing passed a plain `[]` where the
   new `Backing` object was expected: **`AttributeError` mid-report, exit code 1**, identical to
   "risk found", and stdout cut off at 2,341 bytes of a 13,722-byte report. Two lessons: the
   crash-vs-verdict collision is why exit code 4 now exists, and a truncated report is silent
   unless you count bytes — so the run matrix above counts them.
4. Denominators in the first version of `--selftest-spec` mixed units: `traps_with_samples=20`
   (traps) beside `flagged=14` (samples). Rewritten to name the unit on every count.
5. `os.path.abspath()` in the planter stripped trailing dots and spaces (see Safety method).
6. `strerror` came back in Chinese on this zh-CN build; the report now prints `errno` plus a
   suppression note (M21: English only).

## Contract opinions — where I think the order or the spec is wrong

* **"cases_planted / cases_detected" is the wrong denominator for a scanner, and the order asked
  for it anyway.** Detection can only be counted over what reached the disk, and this folder's
  whole subject matter is names that *do not reach the disk*. The two unplantedable rows are the
  interesting results, and they sit outside the four numbers. If a client ever sees
  `cases_detected=11/18` as a quality score, they will be reading it wrong.
* `spec/canonical.md` has **no word for "the renaming happened before you could look"**. The
  closest is `path_form`, which describes the caller's own string, not the delivery layer. I used
  `os_legality_verdict=unknown` + prose, which is the least dishonest fit, but the vocabulary has
  a real hole for exactly the case the product exists for.
* `os_legality_verdict=legal` is misleading **as a line a human reads first** for a name that will
  be rewritten (T04/T05). It is correct in the frozen sense — the OS permits the name — and the
  product answer is the opposite of what the word suggests. The tool puts the prose on the same
  line, but anyone who builds a badge on the verdict word alone will ship a green tick on
  `trail.`.
* `mechanism_class=unknown` is doing paid work in two unrelated places: T20 (`--force.txt`, a
  name that is legal and dangerous one layer up) and the full-width/jamo family's *collision*
  risk. FROZEN.md already says `unknown` "must be resolved before whitepaper"; this tool is a
  reason to resolve it, not a reason to keep it.
* `cases.yaml` T17/T18 `sample_hex` are prose labels, so any automated consumer of the frozen
  table either skips them silently (as an earlier reader might) or crashes. Fix at the next
  freeze; it is a contract-only change, like rev3's.
* The order's `--target macos|ubuntu` is honest only if the tool says it has no cells for them.
  `docs/evidence.md` currently reports `OUTCOME=NOT-COMPARABLE` for the ports too, so a `backed_by`
  field could imply agreement that the equality gate has not certified. The report now prints both
  facts in its header; the flag itself is a contract problem, not a tool problem.

## CLEANUP

**Not deleted, per the order.** Left on disk:

    D:\sendguard-work\tool-selfcheck-68b75721b2ac\   (52 enumerated entries, ~1 KB payloads)
    D:\sendguard-work\sg-probe-x1\                   (scratch from the API probes: CON.txt, trail., trailsp , photo, e1-e3.txt, e4dir)
    D:\sendguard-work\s10-plant.json  s10-plant2.json  s10-runs.json  s10-accounting.json  s10-lines.json  s10-final.json
    D:\sendguard-work\s10-run-*.txt  s10-final-*.txt  s10-out-all.txt  s10-selftest.txt

`cleanup_failed` does **not** apply: no cleanup was attempted, so there is nothing to fail. Both
folders contain orphan names that Windows tools cannot remove by ordinary means; if you want them
gone, the deletion needs the same extended prefix that created them:

    python -c "import os,shutil; shutil.rmtree('\\\\?\\D:\\sendguard-work\\tool-selfcheck-68b75721b2ac')"

I did not run that, and I did not test it. `CON.txt` in the probe folder is a real orphan file:
`dir` shows it, and Explorer will not delete it without the same trick.

`tool/__pycache__/check.cpython-314.pyc` — my own `py_compile` artifact, removed. `.gitignore` does
not cover `__pycache__`, so it would otherwise have been offered to the next commit.

## Reproduce

```
python tool/check.py D:\sendguard-work\tool-selfcheck-68b75721b2ac
python tool/check.py D:\sendguard-work\tool-selfcheck-68b75721b2ac --target windows
python tool/check.py D:\sendguard-work\tool-selfcheck-68b75721b2ac\sub     # exit code 0
python tool/check.py --selftest-spec
```
