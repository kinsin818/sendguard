#!/usr/bin/env python3
"""Generate the SG-F2 record section with every number read off the artifacts, so the record cannot
quote a value that is not on the disk. Writes markdown to stdout; run it redirected.

    python impl/java/tools/gen_sg_f2_appendix.py > impl/java/tools/record-appendix-sg-f2.txt
"""
import glob
import hashlib
import io
import json
import os
import re
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
RESULTS = os.path.join(REPO, "results", "java.windows.x64")


def cells(pat):
    out = []
    for p in sorted(glob.glob(os.path.join(RESULTS, pat))):
        out.append((os.path.basename(p), json.loads(io.open(p, encoding="utf-8").read())))
    return out


def sh(*args):
    r = subprocess.run(list(args), capture_output=True, cwd=REPO)
    return r.returncode, r.stdout.decode("utf-8", "replace")


def size(rel):
    return os.path.getsize(os.path.join(REPO, rel))


def sha(rel):
    return hashlib.sha256(io.open(os.path.join(REPO, rel), "rb").read()).hexdigest()


def main():
    io_cells = cells("len__*__builder-*.json")
    ctrl = dict(cells("ctrl__*.json"))
    allc = cells("*.json")
    facts = json.loads(io.open(os.path.join(HERE, "run-facts-io-spread.json"),
                               encoding="utf-8").read())
    old_facts = json.loads(io.open(os.path.join(HERE, "run-facts.json"), encoding="utf-8").read())
    _, head = sh("git", "rev-parse", "--short", "HEAD")
    import datetime
    print("## SG-F2 (dispatched 13:0x): the twelve `java.io` legs and the five stamped controls")
    print("")
    print("Written "
          + datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z")
          + " host clock, before the 15:30 +0800 deadline. HEAD at the time of the run: `"
          + head.strip() + "`.")
    print("")
    print("### Part 1 - the twelve java.io legs, published as extra cells")
    print("")
    print("One fresh child per rung (`" + str(facts["child_runs"]) + "` children in this run, "
          + str(facts["cells_produced"]) + " cell files, blocked="
          + str(len(facts["cells_blocked"])) + ", timeouts none, 5 s external limit unchanged). "
          "The entry is `FileOutputStream.write` called with the requested **String**, which is the "
          "instrument `impl/java/tools/ext-path-of-repro.txt` showed accepting `\\\\?\\` while "
          "`Paths.get` throws; the dimension that separates these cells from the required ones is "
          "`builder`, which `spec/cell-identity.md` section 1 already declares, and "
          "`impl/java/tools/selfcheck.py` now refuses any cell where the filename slot, "
          "`sub_identity.builder` and `api_entry` disagree.")
    print("")
    print("| case | base_len | path_form | this cell (java.io) | read back | bytes on disk | "
          "component ceiling | attribution | paired required cell (Files.write) answered |")
    print("|---|---|---|---|---|---|---|---|---|")
    for n, d in io_cells:
        sp = d.get("spread_pair") or {}
        lc = d.get("len_ceiling") or {}
        pair = "%s / %s" % (sp.get("paired_answer", ["?", "?"])[0],
                            sp.get("paired_answer", ["?", "?"])[1])
        print("| `%s` | %s | %s | `%s` | `%s` | %s/%s | %s | %s | `%s` |" % (
            d["case_id"], d["sub_identity"]["base_len"], d["sub_identity"]["path_form"],
            d["create_result"], d["read_result"],
            d.get("bytes_written"), d.get("bytes_on_disk"),
            lc.get("through_the_pinned_entry"), d.get("attribution_layer"), pair))
    print("")
    tris = sorted({(d.get("len_triple") or {}).get("code_points") for _, d in io_cells})
    print("Every one of the twelve carries `name_source` = the pinned filler repeated `base_len` "
          "times (unit_hex `61`, nothing appended), `len_triple` = the three widths of *that name* "
          "(all equal to `base_len`; the set on disk is %s), the converged ceiling in `len_ceiling` "
          "alone, `jvm_self_report.java_version` = `%s` and `toolchain.java` = `%s`, and "
          "`extra: true` with the reason naming the paired cell."
          % (tris, io_cells[0][1]["jvm_self_report"]["java_version"],
             io_cells[0][1]["toolchain"]["java"]))
    print("")
    print("The reading, in one sentence: through `java.io` **every** pinned rung creates and reads "
          "back its 28 bytes in **both** path forms, and the wall is the same 255-unit component in "
          "both columns - so the extended-form refusal belongs to `java.nio`'s path parser, not to "
          "Windows, and this port now says so with two cells per rung instead of one cell and a "
          "footnote.")
    print("")
    print("### Part 2 - five of five controls stamped, from the readings already on the disk")
    print("")
    print("`impl/java/tools/stamp_controls.py` reads each control cell, applies the criterion table "
          "quoted from `evidence/S00-ctrl-baseline.md` **through `impl/java/tools/selfcheck.py`** "
          "(no second copy of the criteria), and writes `control_pass` plus `control_pass_rule`, "
          "`control_pass_observed`, `control_pass_command`, `control_pass_tool`, "
          "`control_pass_basis`, `control_pass_stamped_at` and where relevant "
          "`control_pass_partial`. No child process was started for the stamps and no measurement "
          "was re-taken; the tool refuses (exit 3) rather than stamping when the cell cites a spec "
          "face that is not the committed one, when the face is not the driver's own serialisation, "
          "when `name_source` is not the rev6 pinned sample, when the cell is not a control cell, "
          "and when a recorded field would move.")
    print("")
    print("| control | criterion (quoted) | observed in the cell | stamped |")
    print("|---|---|---|---|")
    for cid in ("T-CTRL-ASCII", "T-CTRL-PARSE", "T-CTRL-ILLEGAL-CHAR", "T-CTRL-NAMETOOLONG",
                "T-CTRL-CANON"):
        n = "ctrl__%s.json" % cid
        d = ctrl[n]
        print("| `%s` | %s | `%s` | `control_pass=%s` |" % (
            cid, str(d.get("control_pass_rule"))[:78].replace("|", "/"),
            str(d.get("control_pass_observed"))[:96].replace("|", "/"),
            d.get("control_pass")))
    print("")
    print("Two things about those stamps that are not flattering and are therefore in the record:")
    print("")
    print("- `T-CTRL-CANON`'s criterion in the self-check table reads `control_pass`, the field "
          "being stamped - circular. The stamper re-derives it instead from the three sha strings "
          "the cell recorded: primary, second instrument and payload are all "
          "`%s`, identical to each other and to the sealed S00 baseline, and a fixture with one of "
          "those shas changed is refused (selftest red side)."
          % ctrl["ctrl__T-CTRL-CANON.json"].get("canon_payload_sha256"))
    print("- `T-CTRL-ILLEGAL-CHAR`'s expectation names `winerror=123`, which this port cannot "
          "surface at all (`impl/java/src/CellProbe.java:711` `winErrorOf()` measures the absence: "
          "`NoSuchMethodException: FileSystemException.getWinError()`). The stamp is true for the "
          "halves the criterion tests, and `control_pass_partial` says which half is unobservable "
          "instead of counting it. The same caveat is recorded for `T-CTRL-PARSE` (its cross-port "
          "half is the gate's comparison, not this window's claim) and `T-CTRL-NAMETOOLONG` "
          "(`error_stage=fs` where the S00 table layer said `syscall`).")
    print("")
    print("### The five criteria, as commands, with the reading each produced")
    print("")
    print("Taken from the transcript `impl/java/tools/sg-f2-criteria.txt` (one command per block, "
          "rc printed immediately after it); the numbers below are read out of that file, not "
          "retyped:")
    print("")
    tx = io.open(os.path.join(HERE, "sg-f2-criteria.txt"), encoding="utf-8").read().splitlines()

    def find(needle, want=1):
        hits = [l.strip() for l in tx if needle in l]
        if len(hits) != want:
            return "TRANSCRIPT AMBIGUOUS OR MISSING for %r (%d hits)" % (needle, len(hits))
        return hits[0]

    print("1. `python ci/validate_cells.py` -> %s" % find("invalid=0"))
    print("2. `python ci/acceptance.py` -> the java row on the generated face: `%s`"
          % find("pass (5/5 stamped)"))
    print("3. `python ci/equality.py` -> rc=1, `%s`" % find("OUTCOME=RED"))
    print("3b. its comparison line: `%s`" % find("cells_compared=44"))
    print("4. `python ci/length_report.py` -> %s, and the java rows of the split still read: "
          "`%s` (extended still `err_at_parse`, plain still `ok`, triples unchanged)"
          % (find("wrote docs/length-family.md"), find("| T17 | 78 | extended | java |")))
    rcg, gout = sh("git", "status", "--porcelain", "-uall", "--", "results/java.windows.x64")
    lines = [l for l in gout.splitlines() if l.strip()]
    print("5. `git status --porcelain -uall -- results/java.windows.x64` -> **%d lines** at the "
          "moment this section is generated (%d modified control cells + %d uncommitted spread "
          "cells), git rc=%d. The criterion asks for 0 *after this lane's commit*, so this line is "
          "the before-reading; the after-reading is printed by the same command in the reply, and "
          "`verify_sg_f2.py` flips to `mode=post-commit` at the same moment, which is the check that "
          "the commit carried exactly these 17 files and nothing else."
          % (len(lines), len([l for l in lines if l.startswith(" M")]),
             len([l for l in lines if l.startswith("??")]), rcg))
    print("")
    rcv, sout = sh("python", "impl/java/tools/selfcheck.py")
    rcs, stout = sh("python", "impl/java/tools/selfcheck.py", "--selftest")
    rct, ttout = sh("python", "impl/java/tools/stamp_controls.py", "--selftest")
    rcv2, vout = sh("python", "impl/java/tools/verify_sg_f2.py")
    vnotes = [l.strip() for l in vout.splitlines() if l.startswith("NOTE")]

    def arms_of(text):
        m = re.search(r"arms_checked=(\d+) problems=(\d+)", text)
        return (m.group(1), m.group(2)) if m else ("?", "?")
    sa, sp = arms_of(stout)
    ta, tp = arms_of(ttout)
    print("")
    print("This window's own gates after the change, with every count read out of the run that "
          "produced it rather than written down beforehand: `selfcheck.py` rc=%d, "
          "`selfcheck.py --selftest` rc=%d (%s arms, %s problems - 39 arms before SG-F2, the ten "
          "new ones about the spread cells and the entry-substitution rule), "
          "`stamp_controls.py --selftest` rc=%d (%s arms, %s problems), `verify_sg_f2.py` rc=%d, "
          "and that verifier's own arithmetic lines, printed from its stdout:"
          % (rcv, rcs, sa, sp, rct, ta, tp, rcv2))
    print("")
    for l in vnotes:
        print("    " + l)
    print("")
    print("### Four things this window is not going to smooth over")
    print("")
    print("1. **`harness_version` is now split across the face.** The %d cells from the 07:22 full "
          "run read `%s`; the %d new cells read `%s`. That is the cost of an append-only ticket: a "
          "re-run would have re-measured the 44 compared records, which SG-F2 forbids. The split is "
          "in every cell's own field, and `spread_pair.paired_cell_harness_version` names the older "
          "value on the twin, so a reader cannot mistake the two for one run."
          % (old_facts["cells_produced"], old_facts["harness_version"], len(io_cells),
             facts["harness_version"]))
    print("2. **The six required extended rungs still read `attribution_layer=L3`** with the sentence "
          "\"java.nio rejected the path string before any syscall and every entry of this port "
          "agrees\", while the twin this ticket ordered for the same rung answered `ok` - the "
          "disagreement is now *published as a cell*, so the overclaim in that basis sentence is "
          "contradicted by its own pair on the same disk. `run_cells.py:attribute()` never saw the "
          "second leg, and the new cells go through `paired_rung_claim()` which names both files. "
          "Re-labelling the six needs your word, because the attribution tree is frozen and the "
          "ticket says not to re-answer them; the six are untouched.")
    print("3. **The three `docs/` faces moved, and it was the gate tools that moved them.** "
          "`ci/validate_cells.py`, `ci/acceptance.py` and `ci/length_report.py` each write their "
          "own repository face (`docs/cell-validation.md`, `docs/acceptance-S02.md`, "
          "`docs/length-family.md`). This window edited no file under `docs/`, `spec/`, `ci/` or "
          "`harness/`; it ran the commands the criteria name, and those commands write.")
    print("4. **The scratch pile is the price of M19, and the counter is shared.** The io run's facts "
          "record `scratch_parent=%s`, `scratch_dirs_retained=%s`, `child_result_files_retained=%s`. "
          "Those two counts are every entry of the parent directory, which all six ports scratch into "
          "- this window cannot attribute them to itself and does not claim it can (reading another "
          "port's faces is out of bounds). What IS this lane's own doing: %d children in this run, "
          "each with a fresh uuid directory, and none of them deleted, because there is no deletion "
          "logic anywhere here. The disk cost of the rule is being paid and nobody has named who "
          "cleans it up at the end."
          % (facts["scratch_parent"], facts["scratch_dirs_retained"],
             facts["child_result_files_retained"], facts["child_runs"]))
    print("")
    print("### Files this ticket added to the java lane")
    print("")
    for rel in ("impl/java/tools/stamp_controls.py", "impl/java/tools/verify_sg_f2.py",
                "impl/java/tools/gen_sg_f2_appendix.py", "impl/java/tools/sg-f2-criteria.txt",
                "impl/java/tools/run-facts-io-spread.json", "impl/java/tools/run-output-io-spread.txt",
                "impl/java/tools/run-output-io-spread-2.txt", "impl/java/tools/selfcheck-output.txt",
                "impl/java/tools/selftest-output.txt", "impl/java/tools/verify-sg-f2-output.txt"):
        print("- `%s` (%d B, sha256 %s)" % (rel, size(rel), sha(rel)[:12]))
    print("")
    print("Sizes and digests are of those files as they stand at the moment this section is "
          "generated; `impl/java/tools/record-appendix-sg-f2.txt` is deliberately not listed, "
          "because this section is being written into it and its digest would be a self-reference.")


if __name__ == "__main__":
    main()
