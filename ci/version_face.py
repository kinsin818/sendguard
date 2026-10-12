#!/usr/bin/env python3
"""One version, one place, and a leg that notices when a face disagrees with it.

Run:  python ci/version_face.py            # check every tracked face
      python ci/version_face.py --selftest # red and green arms

Why: the owner set the deliverable version at 0.1.0 on 2026-10-12. A version that is typed into prose is a
permanent claim with nobody watching it - the same shape as every other number this project has had to build a
leg for. So the file `VERSION` is the only source, the generated evidence face prints it, and this leg reads
every tracked face for the marker and refuses the tree when a copy differs.

Exit codes: 0 = every marker agrees · 1 = at least one face disagrees · 3 = instrument problem (no VERSION, a
VERSION that is not one clean semver line, or a tree with no committed faces to read). rc=1 is a measurement; a
crash never borrows it.
"""
import io
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
MARKER = re.compile(r"deliverable version: (\d+\.\d+\.\d+)")


def read_version():
    p = os.path.join(REPO, "VERSION")
    if not os.path.isfile(p):
        return None, "VERSION does not exist"
    lines = [l.strip() for l in io.open(p, encoding="utf-8").read().splitlines() if l.strip()]
    if len(lines) != 1:
        return None, "VERSION must be exactly one non-empty line, got %d" % len(lines)
    if not re.match(r"^\d+\.\d+\.\d+$", lines[0]):
        return None, "VERSION %r is not x.y.z" % lines[0]
    return lines[0], None


def tracked_faces():
    r = subprocess.run(["git", "-C", REPO, "ls-files", "-z"], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", shell=False)
    if r.returncode != 0:
        return None, "git ls-files rc=%d" % r.returncode
    return [p for p in r.stdout.split(chr(0)) if p], None


def check(argv=None):
    """Returns (findings, version, faces_scanned, markers_found)."""
    version, err = read_version()
    if err:
        return None, None, 0, err
    faces, err = tracked_faces()
    if err:
        return None, None, 0, err
    findings, markers = [], 0
    for rel in faces:
        p = os.path.join(REPO, rel.replace("/", os.sep))
        if not os.path.isfile(p):
            continue
        try:
            text = io.open(p, encoding="utf-8", errors="replace").read()
        except OSError as e:
            return None, None, 0, "cannot read %s: %s" % (rel, str(e)[:60])
        for i, line in enumerate(text.splitlines(), 1):
            m = MARKER.search(line)
            if m:
                markers += 1
                if m.group(1) != version:
                    findings.append("%s:%d says %s, VERSION says %s" % (rel, i, m.group(1), version))
    return findings, version, len(faces), markers


def selftest():
    errs = []
    n = [0]

    def chk(cond, label):
        n[0] += 1
        if not cond:
            errs.append(label)

    v, err = read_version()
    chk(err is None and v == "0.1.0", "green: VERSION is one clean line and reads 0.1.0, got %r %r" % (v, err))
    chk(MARKER.search("x - deliverable version: 0.1.0 (from VERSION)") is not None,
        "green: the marker the generators write is the marker this leg reads")
    bad = MARKER.search("deliverable version: 0.2.0")
    chk(bad is not None and bad.group(1) != v,
        "red: a disagreeing copy is recognised as a value, not ignored as prose")
    chk(MARKER.search("version: 1.2") is None, "red: a two-part number is not a version claim and is not matched")
    findings, version, scanned, markers = check()
    chk(findings is not None, "green: the real tree is readable, got %r" % (markers,))
    chk(all(v == version for v in [version]), "green: the compared version is the file's own value")
    chk(scanned > 1000, "green: the check enumerates the committed faces (scanned=%d) rather than a handful"
        % scanned)
    chk(markers >= 1, "red: at least one face must carry the marker, or this leg is checking nothing and "
                      "reporting success (markers=%d)" % markers)
    return errs, n[0]


def main(argv):
    if "--selftest" in argv:
        errs, arms = selftest()
        for e in errs:
            print("SELFTEST-FAIL: %s" % e)
        print("arms=%d passed=%d" % (arms, arms - len(errs)))
        return 1 if errs else 0
    extra = [a for a in argv if a not in ("--quiet",)]
    if extra:
        print("OUTCOME=INSTRUMENT-RED this leg reads only, it takes no %r" % (extra,))
        return 3
    findings, version, scanned, info = check()
    if findings is None:
        print("OUTCOME=INSTRUMENT-RED %s" % info)
        return 3
    for f in findings[:20]:
        print("MISMATCH| %s" % f)
    print("OUTCOME=%s version=%s faces_scanned=%d markers_found=%d mismatches=%d source=VERSION"
          % ("CLEAN" if not findings else "RED", version, scanned, info, len(findings)))
    return 1 if findings else 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as exc:
        print("OUTCOME=INSTRUMENT-RED %s: %s" % (type(exc).__name__, str(exc)[:160]))
        sys.exit(3)
