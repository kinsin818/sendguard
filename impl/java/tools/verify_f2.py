#!/usr/bin/env python3
"""Verify F2 landed as specified, from the files, not from memory. Read-only except the
verification output path it is given. Exit 0 = every claim holds; 1 = a claim does not; 3 = the
verifier itself could not run.

Checks
  A  the twelve java.io spread cells: identity, pinned filler, the three widths, the ceiling field,
     the instrument face, the JVM and toolchain naming, and the pair they point at
  B  the required Files.write records were NOT re-answered: every cell that is not a control cell is
     byte-identical to the committed face, and a control cell may differ only by added control_pass_*
     fields - no recorded field may move
  C  a deliberately broken spread fixture must be refused by these same checks (the verifier has to
     be able to say no, or it is decoration)
"""
import glob
import hashlib
import io
import json
import os
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
RESULTS = os.path.join(REPO, "results", "java.windows.x64")
PRIMARY = "Files.write"
IO_ENTRY = "FileOutputStream.write"


def cells():
    out = {}
    for p in sorted(glob.glob(os.path.join(RESULTS, "*.json"))):
        out[os.path.basename(p)] = json.loads(io.open(p, encoding="utf-8").read())
    return out


def check_spread(name, d, problems):
    sid = d.get("sub_identity") or {}
    bl = sid.get("base_len")
    form = sid.get("path_form")

    def bad(msg):
        problems.append("%s: %s" % (name, msg))
    if d.get("extra") is not True:
        bad("must be extra")
    if "extra_reason" not in d:
        bad("no extra_reason")
    if sid.get("builder") != IO_ENTRY or d.get("api_entry") != IO_ENTRY:
        bad("builder/api_entry mismatch: %r / %r" % (sid.get("builder"), d.get("api_entry")))
    if bl is None or form is None:
        # a fixture with a hole in it must be REFUSED, not crash the verifier
        bad("sub_identity is missing base_len or path_form (%r)" % (sid,))
        return
    if ("base_len-%d" % bl) not in name or ("__%s__" % form) not in name:
        bad("filename lost a rung dimension")
    if ("builder-" + IO_ENTRY) not in name:
        bad("filename lost the builder slot")
    if d.get("name_source") != "61" * int(bl):
        bad("name_source is not the pinned filler repeated base_len times (len=%d want=%d)"
            % (len(str(d.get("name_source"))), 2 * bl))
    tri = d.get("len_triple") or {}
    if set(tri.values()) != {bl}:
        bad("len_triple is not the pinned component's three widths: %r" % tri)
    lc = d.get("len_ceiling") or {}
    if not lc:
        bad("no len_ceiling field")
    if lc.get("measured_through_this_cells_entry") != IO_ENTRY:
        bad("len_ceiling does not name the entry this cell measured through")
    if "String" not in str(d.get("instrument_face") or ""):
        bad("instrument_face does not name the String-form call")
    if not d.get("points_column_note"):
        bad("no points_column_note")
    if not d.get("spread_pair", {}).get("paired_cell_read"):
        bad("paired cell not read")
    pair = os.path.join(RESULTS, str(d.get("spread_pair", {}).get("paired_cell")))
    if not os.path.isfile(pair):
        bad("paired cell file missing")
    else:
        pd = json.loads(io.open(pair, encoding="utf-8").read())
        if pd.get("api_entry") != PRIMARY:
            bad("paired cell is not the %s record" % PRIMARY)
    if not (d.get("jvm_self_report") or {}).get("java_version"):
        bad("no jvm_self_report.java_version")
    if not (d.get("toolchain") or {}).get("java"):
        bad("no toolchain.java")
    if d.get("read_attempted") is True and d.get("read_result") == "ok":
        if not d.get("sha256_truth") or d.get("bytes_on_disk") is None:
            bad("read_result=ok without the bytes and the digest that back it")


def committed_blob(name):
    # git addresses paths with forward slashes on every platform; a backslash path here returns
    # "fatal: not a valid object name", which a careless reader would score as "no committed face"
    r = subprocess.run(["git", "-C", REPO, "cat-file", "blob",
                        "HEAD:" + ("results/java.windows.x64/" + name).replace("\\", "/")],
                       capture_output=True)
    return None if r.returncode != 0 else r.stdout


def main():
    problems, notes = [], []
    on_disk = cells()
    spread = dict((n, d) for n, d in on_disk.items() if "builder-" in n)
    notes.append("cells_on_disk=%d spread_cells=%d" % (len(on_disk), len(spread)))
    if len(spread) != 12:
        problems.append("expected 12 java.io spread cells, found %d" % len(spread))
    for n, d in sorted(spread.items()):
        check_spread(n, d, problems)

    # B: nothing that was already published moved
    moved, rewritten, identical = [], [], 0
    uncommitted, stamped_ctrl = [], []
    spread_on_disk = []
    spread_committed = []
    for n in sorted(spread):
        if committed_blob(n) is not None:
            spread_committed.append(n)
    mode = ("pre-commit" if not spread_committed else
            ("post-commit" if len(spread_committed) == len(spread) else "MIXED-FACE"))
    notes.append("mode=%s spread_committed=%d/%d" % (mode, len(spread_committed), len(spread)))
    for n, d in sorted(on_disk.items()):
        blob = committed_blob(n)
        if n in spread:
            spread_on_disk.append(n)
            if blob is not None and mode == "pre-commit":
                rewritten.append(n)
            if mode == "pre-commit":
                continue
            # post-commit: a spread cell is now a committed record and must still match its face
        if blob is None:
            uncommitted.append(n)
            notes.append("no committed face for %s" % n)
            continue
        disk = io.open(os.path.join(RESULTS, n), "rb").read()
        if disk == blob:
            identical += 1
            continue
        old = json.loads(blob.decode("utf-8"))
        if d.get("case_group") != "ctrl":
            rewritten.append(n)
            continue
        stamped_ctrl.append(n)
        for k, v in old.items():
            if d.get(k) != v:
                moved.append("%s: %s %r -> %r" % (n, k, v, d.get(k)))
        for k in d:
            if k not in old and not k.startswith("control_pass"):
                moved.append("%s: non-control field %s appeared" % (n, k))
    notes.append("cells=%d identical_to_HEAD=%d stamped_ctrl=%d spread_new=%d rewritten=%s "
                 "uncommitted_extra=%d moved=%d"
                 % (len(on_disk), identical, len(stamped_ctrl), len(spread_on_disk), rewritten,
                    len(uncommitted), len(moved)))
    # a denominator that resolves to nothing is a hollow green, not a pass: the counts have to add up
    if uncommitted:
        problems.append("pre-existing files with no committed face (a lookup is broken, or a record "
                        "went missing): %s" % uncommitted[:4])
    if mode == "MIXED-FACE":
        problems.append("some but not all spread cells are committed: the face is mid-write, this "
                        "verifier cannot judge it. Finish the commit or discard it, then re-run.")
    elif mode == "pre-commit":
        if identical + len(stamped_ctrl) + len(spread_on_disk) != len(on_disk):
            problems.append("arithmetic: %d identical + %d stamped + %d spread != %d on disk"
                            % (identical, len(stamped_ctrl), len(spread_on_disk), len(on_disk)))
        if len(spread_on_disk) != 12:
            problems.append("expected 12 spread cells counted as additions, found %d"
                            % len(spread_on_disk))
        if len(stamped_ctrl) != 5:
            problems.append("expected all 5 control cells to differ from HEAD by their stamp, "
                            "found %d" % len(stamped_ctrl))
    else:  # post-commit: every cell on the disk must equal its own committed face
        if identical != len(on_disk):
            problems.append("post-commit mode but %d of %d files differ from HEAD"
                            % (len(on_disk) - identical, len(on_disk)))
        if stamped_ctrl:
            problems.append("post-commit mode but control cells still differ from HEAD: %s"
                            % stamped_ctrl[:3])
    if rewritten:
        problems.append("a compared record was rewritten outside the ticket: %s" % rewritten[:4])
    if moved:
        problems.append("a recorded field moved: %s" % moved[:4])

    # C: the verifier must be able to say no
    red_caught = 0
    if spread:
        base_name, base = sorted(spread.items())[0]
        broken = json.loads(json.dumps(base))
        for tag, mut in (("pinned-name-swapped", {"name_source": "00"}),
                         ("builder-dimension-dropped", {"sub_identity": {}}),
                         ("jvm-self-report-dropped", {"jvm_self_report": {}})):
            c = json.loads(json.dumps(base))
            for k, v in mut.items():
                c[k] = v
            sub = []
            check_spread(base_name, c, sub)
            if sub:
                red_caught += 1
            else:
                problems.append("RED side %s was not refused" % tag)
        green = []
        check_spread(base_name, base, green)
        if green:
            problems.append("red-side test but the GOOD cell also failed: %s" % green[:2])
        notes.append("arms=4 red_caught=%d (one arm is the green side, which must stay clean)"
                     % red_caught)
        if red_caught != 3:
            problems.append("the spread checks did not refuse all 3 broken fixtures: %d" % red_caught)

    for x in notes:
        print("NOTE %s" % x)
    print("spread_checked=%d problems=%d" % (len(spread), len(problems)))
    for p in problems:
        print("PROBLEM %s" % p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
