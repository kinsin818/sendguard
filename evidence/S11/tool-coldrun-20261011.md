# S11 - the deliverable itself, asked the same names from the working copy and from a cold clone (2026-10-11)

Run at 14:30 +0800 by `ci/clone_parity.py`, which had so far only compared *generated faces*: the recorded
evidence reproduced from history, but nothing in `ci/` had ever run `tool/check.py` inside a clone and asked
whether it answers the same way there. A buyer's sentence is "the checker reproduces", not "the checker's
transcripts reproduce", so that gap was the last flattering-but-unverified claim in the delivery story.

```
clone| D:\sendguard-work\sg-parity\parity-3 (created) head=c54aa63e806a status_before=0 pipeline_rc=1
declared| docs/evidence.md - 1 line(s) inside the declared shape: - repository commit: `8f04c391ac49` (working tree carries 13 uncommitted faces at generation time). That is the HEAD thi
tool| names=5 fields_compared=55 differing=0
OUTCOME=CLEAN faces_compared=12 identical=11 declared=1 differing=0 missing=0 clone=D:\sendguard-work\sg-parity\parity-3
```

## What was asked

Five names, in both trees, through the hex route the spec pins samples with (so no shell quoting can quietly
change which name is being probed), and each answer compared over the eleven fields the gate scores: the ten
`VERDICT_FIELDS` plus `verdict_via`. The field list is imported from `ci/equality.py`, not copied - two field
lists in one repository is a defect this project already paid for (M8).

| name | why it is in the list |
|---|---|
| `report-2026.txt` | the control: a plain legal name, everything should agree |
| `trail.` | trailing dot: the family where four ports say "legal but mutated" and two say "illegal" |
| `CON.txt` | reserved device name: the phantom family, and the name whose *contents* the checker refuses to read |
| `COM1.log` | a reserved name with an extension, the case that separates "the OS rejects it" from "the directory entry is not there" |
| `a` x 200 + `.txt` | the length family, where the answer depends on which rung of the triple you are on |

`tool| names=5 fields_compared=55 differing=0` - five names x eleven fields, and no field differs between the
working copy at `c54aa63` and a `--no-local` clone of the same commit.

## What this does and does not prove

It proves the deliverable does not depend on the working copy: the clone's checkout contains everything the
checker needs (a missing tracked file would have shown as a non-answer code, which this leg reports as
`OUTCOME=INSTRUMENT-RED` rather than as a difference), and the answer it gives about these names is a property of
the commit plus this machine, not of whichever files the seat happened to have lying around.

It does **not** prove cross-machine or cross-OS reproducibility: both runs are on the same Windows host with the
same Python 3.14.7 interpreter, and several of these names are exactly the ones whose answer depends on the OS
and on the executable's manifest. The clone's `docs/evidence.md` differing line is the declared exception named
above and is a self-reference, not a measurement difference. The checker's timing fields are not in the compared
set, because they are per-run by construction.

The leg's own arms cover the parse rather than trusting the run: a verdict block missing one scored field is an
instrument failure and not a smaller comparison (`A9`), output with no verdict block cannot parse into zero
differences, one flipped field between the trees is named rather than counted as a match (`A10`), the hex handed
to the checker must decode back to the name intended (`A11` - a wrong needle probes a different name and reports
agreement), and the checker's own failure codes are never read as answers (`A12`). `arms=12 passed=12`.


## Second reading, 14:34 +0800 - the checker's own spec self-test, in both trees

Five names and eleven fields is this seat choosing what to ask. The deliverable has a self-test that asks what the
*spec* says to ask: `python tool/check.py --selftest-spec` walks every frozen sample in `spec/cases.yaml` through
the same rules. It was run in the working copy and in the cold clone `D:\sendguard-work\sg-parity\parity-5`
(a `--no-local` clone of `2e67e84` produced by the parity leg seconds earlier; the leg had regenerated the
generated faces inside it, which does not touch `tool/` or `spec/`):

```
seat  rc=0  bytes=3086   lines=44
clone rc=0  bytes=3086   lines=44
byte-identical output: True
rc equal: True
differing lines: 0 (+0 unpaired)
  line| SENDGUARD spec self-test: every frozen sample in spec/cases.yaml, through the same rules,
  line| rules: spec/cases.yaml freeze_revision=2 sha256=8650a1863578
  line| traps_in_spec=20  samples_decoded=22  samples_not_decodable=2
```

Same bytes out, same exit code, from a tree that has never seen the author's working copy - and the spec
fingerprint it reads is the committed one (`freeze_revision=2`, the same `8650a1863578…` that
`docs/evidence.md` names), which is the frozen-spec claim being exercised by the product rather than by a
generated document.

The `samples_not_decodable=2` line is the self-test's own published denominator: `tool/check.py` adds to that
count when a frozen case's sample hex cannot be decoded into a name, or when the case carries no sample at all,
and it lists the misses instead of tuning them away - the same reading the morning's tool record already carries
(`evidence/S10/tool-selfcheck.md`: `traps_in_spec=20 samples_decoded=22 samples_not_decodable=2
samples_flagged=14 samples_not_flagged=8`). What is established here is not that the two are benign but that the
number is a property of the committed spec: it is identical on both sides of the clone, and it is not being read
as a pass.

Limits, same as above: one host, one interpreter, this is the deliverable's rule table being exercised, not the
six ports' recorded faces. Together the two readings cover the two things a buyer asks: does it run from the
repository (yes, and its spec self-test is byte-identical), and does it answer the same way there (yes, over the
five declared names and the eleven scored fields).
