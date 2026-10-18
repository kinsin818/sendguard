# F10 - the reproducibility leg cannot reach its green side on any host but the author's

Opened 2026-10-12 by the maintainer that owns `ci/`. **Four outside reviewers reached this independently** (auditor-1 F-2,
auditor-2 F-1, auditor-3 F-1, auditor-4 F-1), and a fifth reader reproduced the same divergence on a third
interpreter. A finding four blind implementers land on at once is not a nuisance report - it is the most
important thing in the audit batch, because it is aimed at the one claim this repository exists to make.

## The defect, with the readings that prove it

`ci/clone_parity.py` compares each generated documentation face in a `--no-local` clone against
`git show HEAD:<face>` in the source tree, and permits differences only through a declared-exception table. That
table currently covers exactly one line shape in one face:

```
DECLARED_EXCEPTIONS = {"docs/evidence.md": r"^- repository commit: "}
```

`docs/delivery-form.md` also carries a **host stamp** - the interpreter that ran the generation - and that line is
inside a face the leg compares byte-for-byte. So the leg's result depends on the interpreter of whoever runs it:

| who ran it | interpreter | reading |
|---|---|---|
| this machine, on this tree | 3.14.7 (the stamped value) | `OUTCOME=CLEAN faces_compared=12 identical=11 declared=1 differing=0 rc=0` |
| auditor-1 / auditor-3 / auditor-4, own clones | 3.13.13 | `OUTCOME=RED ... differing=1`, the single differing face being the interpreter line of `docs/delivery-form.md` |
| WorkBuddy cross-check | 3.13.12 | same divergence class, reported as the leg's green side being unreachable off-host |

**Why this is worse than a cosmetic mismatch.** The leg is the repository's only proof that *a stranger's tree
reproduces the author's numbers*. A leg whose green side is reachable only on the machine that generated the
stamp is not a reproducibility instrument - it is a host fingerprint checker wearing its clothes. It also
contradicts the project's own published boundary: `docs/claim-boundary.md` already says reproducibility is
claimed for one host, one interpreter; the leg, however, **silently converts that limit into a failure signal**
for everybody else, which is the inverse of honest - a reader is told the artifact differs when only the machine
does.

## What a fix must do, and what it must not

1. **Declare host-bound lines before comparing, not after.** The exception table gains a structural entry for the
   interpreter/runtime stamp, and the leg prints `host_bound=` with the count of lines excluded on that basis and
   the names of the faces carrying them. An exclusion that is not counted is a tolerance nobody can audit - this
   is attack 3 in `docs/AUDIT-KIT.md`, found by four reviewers rather than by me.
2. **Split the face rather than excuse the line.** The better shape: keep host-dependent stamps out of the
   compared faces entirely, writing them to a separate generated face (`docs/host-stamp.md`) that the parity leg
   does not compare. Then the compared faces are genuinely host-independent, and the exclusion list shrinks
   instead of growing. Prefer this; the exception-table route is the fallback if re-generation cost is too high.
3. **Both sides of the arm.** A green arm showing the leg reaches `CLEAN` under an interpreter that is *not* the
   stamped one - constructible without two interpreters by injecting a fake stamp through the leg's own seams
   (`run_stamp=` or equivalent), exactly the pattern already used by the legs whose fixtures call production
   code. And a red arm showing the leg still refuses a **real** content drift (a changed number in
   `docs/coverage.md`) while the host-bound exclusion is active - otherwise criterion 1 becomes a way to make the
   leg blind.
4. **The published claim changes with the instrument.** README's reproducibility paragraph and
   `docs/claim-boundary.md`'s "Deliverable reproducibility" row must state which interpreters the claim was
   reached on, and stop quoting `differing=0` as though it were host-free. Until this ticket lands, those two
   faces are quoting a reading that is true of one machine.
5. `docs/delivery-form.md`'s line that presents `3.14.7` as "the interpreter to install" (auditor-2 F-2) is
   re-worded in the same batch: it is a fact about when the face was generated, not a requirement on the reader.

## Allowed surface

`ci/clone_parity.py` (+ its self-test arms), `ci/delivery_form.py`'s stamp emission, the generated
`docs/delivery-form.md` / new `docs/host-stamp.md`, `README.md`'s reproducibility paragraph, the
`Deliverable reproducibility` row of `docs/claim-boundary.md`, `docs/AUDIT-KIT.md` §3, and an appended errata row
naming that `differing=0` was host-bound before this fix.

Not allowed: editing the exception table to swallow a *content* difference, deleting a face, touching `impl/**`,
or rewriting published history.

## Acceptance criteria

1. on a host whose interpreter is not the stamped one, `python ci/clone_parity.py --scratch-root ../<dir>` reads
   `OUTCOME=CLEAN ... differing=0 host_bound=<n>` - the reviewer's command, from their own packet, becomes a
   passing case rather than a false alarm;
2. the leg still reads `RED` when a substantive line is changed in any compared face, with the red side
   demonstrated by planting it, and that planted-face arm must fail if the exclusion logic is widened beyond the
   stamp;
3. `python ci/selftest.py --scratch-root ../<dir>` stays `arms=21 passed=21`, and the new arms are counted in the
   leg's own self-test output, not in prose;
4. `docs/STATUS.md`, `docs/coverage.md`, `docs/delivery-form.md` and the gate artifact are byte-identical before
   and after this ticket on every **judged** number - a parity fix that moves a verdict is not a parity fix;
5. `python ci/claim_digest.py --scratch-root ../<dir>` and `python ci/process_leak_scan.py --selftest` stay green,
   and `python ci/link_check.py` reports `broken=0` after the README and claim-boundary re-wording.
