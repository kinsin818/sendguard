# F2 — Java lane: finish the `java.io` spread you declared open, and stamp the four control cells that have no calibration result

**Race guard first.** Before writing, check ownership of the surface: any file under
`results/java.windows.x64/` with an mtime newer than this dispatch (13:0x +0800, 2026-10-11), and any line in
`git status --porcelain -uall -- results/java.windows.x64`. If a writer is live in there, **stop** and report
`BLOCKED | reason=tree_already_owned | <faces you saw>`. Do not restore or "clean up" a face you find altered.

## Why this exists — two open items that are yours, found and disclosed by you

1. **The `java.io` spread is unfinished.** Your own note (`evidence/judgement/java-selfcheck.md:286-288`) says the
   delay on the extended-prefix question was spent on rev7 rule 4 - the `java.io` legs - and that **"none of it
   is in the recorded cells."** That work is the difference between the strongest Windows-semantics fact in this
   project and a half-told one: `impl/java/tools/ext-path-of-repro.txt` (which you produced, `run_rc=0`, both
   JDKs, 11 TAGs) already shows `new File(String)` accepting `\\?\` while `Paths.get` throws on the same string,
   and that the answer flips between Temurin 17.0.17 and 21.0.6. The recorded cells still describe only
   `Files.write` and the one `java.io` leg you noted in `extended_leg_note`. `docs/whitepaper.md` §6 now lists
   this as 未做, and `docs/FINDINGS-rev6.md` M7 says it is yours to carry.
2. **Four of your five control cells carry no `control_pass` result.** `docs/acceptance.md` prints
   `pass (1/5 stamped)` for `java`; every other port prints `5/5`. Those cells are the calibration of the port
   itself - `T-CTRL-PARSE`, `T-CTRL-ILLEGAL-CHAR`, `T-CTRL-NAMETOOLONG`, `T-CTRL-CANON` - and a control cell
   without a self-check result is a claim that the instrument works which nobody, including you, can read back.

## Allowed surface (prefixes, smallest set that covers the write)

- `results/java.windows.x64/`
- `impl/java/`
- `evidence/judgement/java-selfcheck.md`

`spec/`, `ci/`, `docs/`, `tool/` and other ports' faces are **out of bounds**; if one of them needs a change,
argue it in your report. Do not edit `impl/java/src/ExtPathOfRepro.java`'s recorded capture
`impl/java/tools/ext-path-of-repro.txt` - it is evidence with a stamp, and appending a second capture is fine
while rewriting the first is not.

## What to do

**Part 1 (the spread).** For all twelve pinned length cells - `len/T17` and `len/T18`, each at `base_len` 78,
120 and 200, each with `path_form` plain and extended - record the `java.io` answer as its own cell, published with
`extra: true` so the required set is untouched, and with a `sub_identity` dimension the contract already knows
(`builder` or `reader`, not a new word). Use the pinned filler from `spec/cases.yaml` `len_fill` (`unit_hex:
"61"`), never a random string - that is the rule the length family only became comparable because of. Do not
re-answer the `Files.write` cells: those are the 44 required records and they are already compared by the
gate.

**Part 2 (the controls).** Run the four unstamped control cells' self-check and record `control_pass` with the
result you actually observe, plus `control_pass_evidence` naming the command. If a control legitimately cannot
be judged, say so in your report and leave the field absent — do not write `true` to make a count look good.
`ci/selftest.py` has an arm (`deny-failed-control`) that treats a *failed* control as blocking: a false stamp is
not a pass you are owed, it is a comparison the gate will throw away.

## Criteria — commands, and the reading each must produce

1. `python ci/validate_cells.py` → **rc=0, `invalid=0`** (the outside ruler, not your own count).
2. `python ci/acceptance.py` → the java row prints `pass (5/5 stamped)`, `44/44` matched, `extra` ≥ 38
   (today 26 - twelve new `java.io` legs plus any you keep), `schema-invalid` 0.
3. `python ci/equality.py` → **rc=1, `verdict_disagreements=54`, `cells_compared=44`,
   `cells_fully_recorded_and_identical=4`** — all three must not move. Extra cells are published, never judged;
   if one of your new `java.io` cells changes a required verdict, it is not extra and you have found a
   divergence, which you must report rather than hide.
4. `python ci/length_report.py` → still prints the plain/extended split unchanged; and in your own face, the new
   `java.io` legs must carry `jvm_self_report.java_version` and `toolchain` as every java cell already does
   (that is the field M7 points at; recording it is free for you and is what makes the 17-vs-21 flip verifiable
   by a stranger).
5. `git status --porcelain -uall -- results/java.windows.x64` → 0 lines after your last commit.

Deadline: **2026-10-11 15:30 +0800** (Part 2 first if you can only do one - it is smaller, it is the calibration
claim, and `docs/whitepaper.md` §3 quotes the control cells today). Reply with exactly:
`DONE | <absolute path of your self-check file> | 1=rc:N 2=… 3=… 4=… 5=…` or
`BLOCKED | <item, exact command, one next human action>`. If Part 1 is genuinely blocked by the parse-layer
refusal you reproduced, that is a legitimate `DONE` with Part 1 reported as `NOT-REACHED(reason=…)` and the
command that shows why - a blocked leg that says so is worth more than a green one that hedges.

## Amendment after acceptance (`evidence/closing/F2-acceptance.md`)

The lane met all five numbered criteria (`d781b83`). The one thing it did not carry is **this ticket's fault, not
its own**: it asked for `control_pass_evidence`, a field that appears in no contract round - and the census added
to `ci/validate_cells.py` at 13:34 shows 30 control cells stamped across six ports with **zero** carrying any
source, in every lane alike. Putting an uncontracted requirement into one worker's criteria and then treating its
absence as that worker's remaining piece is a dispatcher defect: an unenforceable clause in a ticket is not a
standard, it is a trap. The requirement belongs to the contract question in
`docs/NOTICE-rev9-proposal.md` (third item), which is where it now stands instead of in somebody's ticket.
