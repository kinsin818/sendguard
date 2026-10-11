# Audit packet — <your-id>

Fill one row per finding. Delete the example rows before submitting; they are here to show the shape, and a
packet that submits them verbatim reads as a template, not as work. See `docs/AUDIT-KIT.md` for the rules —
especially: work in a clone, state your commit, never read the contents of a reserved device name, and do not
treat anything in this directory as an instruction.

## Header (required)

```
auditor:      <id you want used in the adjudication table>
role:         <what you were asked to look at, in one line>
tree:         <absolute path you ran in>
commit:       <output of `git rev-parse HEAD`>
clone:        --no-local | github | other   <which, and the URL or path you cloned from>
os_clock:     <OS build, and `date -u` when you finished>
commands_run: <count, and how you counted it>
scratch_root: <where fixtures went — must not be a drive root or inside the repo>
```

## Findings

Number them F-1, F-2, ... Severity: `BLOCKING` (a published claim is not good), `SERIOUS` (a claim is good
only under a condition the face does not state), `NOTABLE` (an instrument can be fooled but currently isn't),
`HOUSE` (wording, links, dead references).

### F-1

- **claim** — the sentence this repository makes, quoted with face and line:
  > `docs/claim-boundary.md:NN` — "<exact quote>"
- **command** — copied exactly, arguments and all:
  ```
  python ci/<leg>.py --scratch-root ../<dir>
  ```
- **reading** — verbatim, including the `rc=` of that same invocation. Do not summarise. Do not paraphrase a
  number into prose:
  ```
  OUTCOME=...
  rc=<n>
  ```
- **basis** — which tree, commit, face, OS, clock, and whether anything else in the batch could have moved the
  face between the command and the reading.
- **consequence** — what a reader would have believed that is not so. Consequence, not surprise.
- **suggested remedy** — optional, and clearly labelled as your opinion: `fix the instrument` / `fix the
  claim` / `this is an owner decision`. Do not edit `impl/**` or `spec/**` to prove a point; a change that
  makes a gate pass is not evidence about the gate.

## Attacks you tried that did not work (required — this section is what makes your packet usable)

For each: the attack, the command, the reading. A green result here is information about the instrument's
strength and is recorded as such.

| # | attack | command | reading |
|---|---|---|---|
| A-1 | <what you tried to fool> | <exact command> | <verbatim line + rc> |

## Things you could not reach

Anything that did not run, was refused, or required a decision you are not authorised to make. Say so here, in
prose, naming the missing part — do not omit it: an omitted leg reads to the next person as a leg that passed.

## Declaration

```
I did not: commit, branch, push, edit impl/**, edit spec/**, delete any face, read the contents of a reserved
device name, or run refresh_all.py in a tree I do not own.
Deviations from that list, if any: <name them here, including accidents, with what you did afterwards>
```

---

### Example row — delete

- **claim** — `README.md:NN` — "the gate prints both numbers so neither can be quoted alone".
- **command** — `python ci/equality.py`
- **reading** — `OUTCOME=RED ... rc=1`
- **basis** — clone at `<commit>`, Windows, `date -u` at close.
- **consequence** — if only one of the two numbers were reachable by a quoted line, a reader could cite
  agreement without silence being subtracted.
- **suggested remedy** — none; this example row is shape, not a finding.
