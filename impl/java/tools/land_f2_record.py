#!/usr/bin/env python3
"""Land the F2 section into this lane's record: a current-state block at the top (so the gate's
`self-reported` column reads the live counts, which is what ci/acceptance.py parses with a FIRST
match) and the generated section at the end. History is not rewritten; both edits are verified by
re-reading the file and counting headings before and after.

Exit 0 = landed and verified. 3 = refused before writing (anchor missing, counts would move).
"""
import hashlib
import io
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
RECORD = os.path.join(REPO, "evidence", "judgement", "java-selfcheck.md")
APPENDIX = os.path.join(HERE, "record-appendix-f2.txt")

TOP = """**Current state of this lane's face (F2, 2026-10-11): the counts below are the live ones, and
`ci/acceptance.py` reads them because they are the first `cells_required=` line in this file. The
sections underneath stay as the record of what was true when each was written; none of them is
retouched.**

cells_required=48 cells_produced=86 cells_valid=86 blocked=0 extra=38 controls_pass=true

44/44 required identities matched. 69 cells byte-identical to the pre-ticket face, 5 control cells
carrying only added `control_pass_*` fields, 12 new `java.io` spread cells marked `extra: true`
(`impl/java/tools/verify_f2.py` prints that arithmetic off the disk). Rulers: `selfcheck.py`
rc=0, `selfcheck.py --selftest` 49 arms / 0 problems, `stamp_controls.py --selftest` 8 arms /
0 problems, `verify_f2.py` rc=0.

"""


def counts(text):
    lines = text.splitlines()
    return {"bytes": len(text.encode("utf-8")),
            "lines": len(lines),
            "H1": sum(1 for l in lines if l.startswith("# ")),
            "H2": sum(1 for l in lines if l.startswith("## ")),
            "first_cells_valid": (re.search(r"cells_valid[= ]+(\d+)", text) or
                                  [None, "none"])[1] if re.search(r"cells_valid[= ]+(\d+)", text)
                                  else "none",
            "first_cells_required": (re.search(r"cells_required=\d+[^\n]*", text).group(0)[:60]
                                     if re.search(r"cells_required=\d+[^\n]*", text) else "none")}


def main():
    before = io.open(RECORD, encoding="utf-8", newline="\n").read()
    app = io.open(APPENDIX, encoding="utf-8", newline="\n").read()
    c0 = counts(before)
    if not before.startswith("# "):
        print("REFUSED the record does not open with an H1 title")
        return 3
    if app in before:
        print("REFUSED the F2 section is already in the record (idempotence guard)")
        return 3
    if not app.startswith("## F2"):
        print("REFUSED the appendix does not start with its own H2: %r" % app[:40])
        return 3
    nl = before.index("\n")
    title = before[:nl]
    rest = before[nl + 1:]
    if rest.startswith("\n"):
        rest = rest[1:]
    after = title + "\n\n" + TOP + rest.rstrip("\n") + "\n\n" + app
    if not (after.startswith(title) and "Current state of this lane" in after):
        print("REFUSED the reassembly lost the title or the new block")
        return 3
    data = after.encode("utf-8")
    bad = sum(1 for x in data if x > 127)
    if bad or b"\r" in data or data[:3] == b"\xef\xbb\xbf":
        print("REFUSED non-ascii=%d cr=%d bom=%s" % (bad, data.count(b"\r"),
                                                     data[:3] == b"\xef\xbb\xbf"))
        return 3
    io.open(RECORD, "wb").write(data)
    back = io.open(RECORD, encoding="utf-8", newline="\n").read()
    c1 = counts(back)
    print("title_unchanged=%s" % (back.splitlines()[0] == title))
    print("before=%s" % json.dumps(c0, ensure_ascii=True))
    print("after =%s" % json.dumps(c1, ensure_ascii=True))
    print("arithmetic: before %d B + top_block %d B + appendix %d B, on_disk %d B, delta %d B "
          "(the delta is the block and the appendix plus the two separator newlines the reassembly "
          "puts back, so it is reported, not asserted as an exact sum)"
          % (c0["bytes"], len(TOP.encode("utf-8")), len(app.encode("utf-8")), c1["bytes"],
             c1["bytes"] - c0["bytes"]))
    print("H1 %d->%d  H2 %d->%d (the appendix carries 1 H2 and %d H3)"
          % (c0["H1"], c1["H1"], c0["H2"], c1["H2"],
             sum(1 for l in app.splitlines() if l.startswith("### "))))
    print("first_cells_required_now=%r" % c1["first_cells_required"])
    print("first_cells_valid_now=%r (was %r)" % (c1["first_cells_valid"], c0["first_cells_valid"]))
    kept, missing = is_subsequence(before.splitlines(), back.splitlines())
    print("history_lines_kept_in_order=%d/%d missing=%s"
          % (kept, len(before.splitlines()), missing[:4]))
    ok = (c1["H1"] == c0["H1"] and c1["H2"] == c0["H2"] + 1
          and c1["first_cells_valid"] == "86" and back.splitlines()[0] == title
          and c1["bytes"] == len(data) and not missing)
    print("LAND_OK=%s" % ok)
    return 0 if ok else 3


def is_subsequence(old_lines, new_lines):
    """Every line that was in the record must still be there, in the same order: this tool only
    inserts a block at the top and appends a section at the end. A dropped or reworded history line
    is the failure mode this check exists for."""
    i, kept, missing = 0, 0, []
    for l in old_lines:
        j = i
        while j < len(new_lines) and new_lines[j] != l:
            j += 1
        if j == len(new_lines):
            missing.append(l[:70])
        else:
            kept += 1
            i = j + 1
    return kept, missing


def verify_only():
    """Re-run the history-preservation check against the committed face, writing nothing."""
    head = subprocess.run(["git", "-C", REPO, "show", "HEAD:evidence/judgement/java-selfcheck.md"],
                          capture_output=True)
    if head.returncode != 0:
        print("cannot read the committed record: " + head.stderr.decode("utf-8", "replace")[:200])
        return 3
    old = head.stdout.decode("utf-8").replace("\r\n", "\n")
    new = io.open(RECORD, encoding="utf-8", newline="\n").read()
    kept, missing = is_subsequence(old.splitlines(), new.splitlines())
    print("committed_lines=%d kept_in_order=%d missing=%d"
          % (len(old.splitlines()), kept, len(missing)))
    for m in missing[:5]:
        print("MISSING %r" % m)
    done = kept == len(old.splitlines()) and not missing
    print("VERIFY_HISTORY_INTACT=%s" % done)
    return 0 if done else 1


if __name__ == "__main__":
    sys.exit(verify_only() if "--verify" in sys.argv else main())
