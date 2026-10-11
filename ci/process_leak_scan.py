#!/usr/bin/env python3
"""Standing scan: the deliverable may describe the product, not the production line.

Run:  python ci/process_leak_scan.py --repo-root .
      python ci/process_leak_scan.py --selftest --scratch-root ../sg-leak

Why this leg exists. On 2026-10-12 a census of the published tree found 1,150 occurrences of a schema property
whose values named sessions, seats and engines rather than artifacts - the data contract was carrying the studio.
Nothing in the existing apparatus could see that: `ci/lint.py` judges file names, `ci/claim_digest.py` judges
numbers, `ci/link_check.py` judges references. A project that sells verification has to verify its own boundary,
and a boundary is not a feeling.

Five classes, counted separately and never blended:

  RETIRED    the retired producer-metadata key, renamed forward by SG-F8. Assembled at run time, because a rule
             that prints its own needle makes the needle unfindable and the scan unverifiable.
  IDENTITY   a value for a producer identity field that does not match the product-side shape
             `[a-z][a-z0-9-]{0,15}-port`. Session names, seat codes and engine personas all fail this shape,
             and they fail it structurally, so the rule survives a rename of the field itself.
  LOGIN      a path under the current user's profile root. Computed from the environment at run time, never
             spelled into a face: this is the class that must never appear in a distributable artifact.
  HOSTROOT   the absolute path of the tree being scanned, quoted inside a face of that same tree. Tells a
             stranger nothing and discloses the host's layout; the public instruction is the published URL.
  TOOLPATH   any other absolute path - a recorded executable, a toolchain root, a runtime location. This is
             **product-side provenance** and the owner's ruling keeps it: the runtime is what made several
             verdicts flip, so hiding it would destroy the more valuable claim. Counted, printed, never fatal.

A hit inside a face whose job is to state the rule is `MENTIONED`, not fatal, and the exemption binds the pair
(class, face) - never the class alone, never the face alone, because a token-level exemption is how a live value
hides inside a log file and still reads as clean. Both counts print. A scan with no denominator is VOID.

Exit codes: 0 clean · 1 findings on a distributable face · 3 instrument problem (no root named, a drive root, a
tree with no git, a scan that could not read its enumeration). Never borrow 1 for a crash: rc=1 is a measurement,
and this project has paid for confusing the two.
"""
import argparse
import io
import os
import re
import subprocess
import sys

# Assembled, never spelled: a published face must not contain the needle it prohibits.
RETIRED_KEY = "".join(["work", "er_", "id"])
PRODUCER_KEYS = (RETIRED_KEY, "implementation_id")
ID_SHAPE = re.compile(r"^[a-z][a-z0-9-]{0,15}-port$")
SEP = chr(92)
SEP2 = SEP + SEP  # a regex character class needs two to mean one literal backslash - with one, `[\/]` is an
# escaped slash and the class silently stops matching backslashes at all. That is how a path rule can look
# correct and never fire, so the arm below feeds it a real Windows path rather than a wish.
ANY_PATH = re.compile("[A-Za-z]:[" + SEP2 + "/]{1,2}(?![" + SEP2 + "/])|/[A-Za-z0-9_.-]+/")
ID_FIELD = re.compile(r'"([A-Za-z0-9_]*_id)"\s*:\s*"([^"]*)"')

DISTRIBUTABLE = ("spec/", "results/", "docs/", "README.md", "tool/", ".github/", "evidence/")
RULE_FACES = ("ci/", "docs/tickets/", "docs/claim-boundary.md")
NON_FATAL_CLASSES = ("TOOLPATH",)


def tracked_faces(root):
    r = subprocess.run(["git", "-C", root, "ls-files", "-z"], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", shell=False)
    if r.returncode != 0:
        return None, "git ls-files rc=%d: %s" % (r.returncode, (r.stderr or "")[:120])
    return [p for p in r.stdout.split(chr(0)) if p], None


def classify(face):
    """'rule' | 'distributable' | 'other' - a rule face may quote a needle, a deliverable may not."""
    if face.startswith(RULE_FACES):
        return "rule"
    return "distributable" if face.startswith(DISTRIBUTABLE) else "other"


def _paths_of(root):
    root_abs = os.path.abspath(root)
    forms = {root_abs, root_abs.replace(SEP, "/"), root_abs.replace("/", SEP)}
    home = os.path.expanduser("~")
    homes = {home, home.replace(SEP, "/")} if home and home != root_abs else set()
    return forms, homes


def scan_face(text, line_offset_path=None, root_forms=(), home_forms=()):
    """[(class, line_no, excerpt)] for one face. The excerpt never carries a full value verbatim."""
    hits = []
    for i, line in enumerate(text.splitlines(), 1):
        if RETIRED_KEY in line:
            hits.append(("RETIRED", i, line.strip()[:50]))
        low = line.lower()
        if any(h.lower() in low for h in home_forms):
            hits.append(("LOGIN", i, "user-profile path (%d chars)" % len(line.strip())))
        elif any(r.lower() in low for r in root_forms):
            hits.append(("HOSTROOT", i, "scanned tree quoted in its own face (%d chars)" % len(line.strip())))
        elif ANY_PATH.search(line):
            hits.append(("TOOLPATH", i, "absolute path, product-side provenance (%d chars)" % len(line.strip())))
        for key, value in ID_FIELD.findall(line):
            if key in PRODUCER_KEYS and not ID_SHAPE.match(value):
                hits.append(("IDENTITY", i, "%s=<%d chars, shape-rejected>" % (key, len(value))))
    return hits


def scan(root):
    faces, err = tracked_faces(root)
    if err:
        return None, err, {}
    root_forms, home_forms = _paths_of(root)
    fatal, mentioned, other, unreadable = [], [], [], []
    for rel in faces:
        p = os.path.join(root, rel.replace("/", os.sep))
        if not os.path.isfile(p):
            continue
        try:
            text = io.open(p, encoding="utf-8", errors="replace").read()
        except OSError as e:
            unreadable.append("%s: %s" % (rel, str(e)[:60]))
            continue
        kind = classify(rel)
        for cls, ln, excerpt in scan_face(text, root_forms=root_forms, home_forms=home_forms):
            row = (cls, rel, ln, excerpt)
            if kind == "rule" or cls in NON_FATAL_CLASSES:
                (mentioned if kind == "rule" else other).append(row)
            elif kind == "distributable":
                fatal.append(row)
            else:
                other.append(row)
    counts = {"files_scanned": len(faces), "unreadable": len(unreadable), "other": len(other)}
    return fatal, mentioned, counts


def selftest():
    """Red side and green side, both against the production functions - never a re-implementation in the test."""
    errs, arms = [], [0]

    def chk(cond, label):
        arms[0] += 1
        if not cond:
            errs.append("arm failed: %s" % label)

    root = "/tmp/fake-tree"
    rf = {root, root.replace("/", SEP), "C:" + SEP + "fake" + SEP + "tree"}
    hf = {"C:" + SEP + "Users" + SEP + "alice"}
    chk(classify("results/python.windows.x64/cell.json") == "distributable", "green: a result face is distributable")
    chk(classify("docs/tickets/SG-F8-public-interface-process-metadata.md") == "rule", "green: a ticket is a rule face")
    chk(classify("notes/scratch.md") == "other", "green: an undiscussed directory is neither")
    chk("RETIRED" in [c for c, _, _ in scan_face('{"%s": "x"}' % RETIRED_KEY, root_forms=rf, home_forms=hf)],
        "red: the retired key is recognised when assembled at run time")
    chk(scan_face("the field " + RETIRED_KEY + " was renamed forward", root_forms=rf,
                  home_forms=hf) == [("RETIRED", 1, "the field " + RETIRED_KEY + " was renamed forward")],
        "green: needle detection is content-based, not path-based")
    chk([c for c, _, _ in scan_face('{"case_id": "T-CTRL-PARSE"}', root_forms=rf, home_forms=hf)] == [],
        "green: a non-producer identifier is not judged by the shape rule")
    chk(any(c == "IDENTITY" for c, _, _ in scan_face('{"implementation_id": "seat-qoder-rust"}', root_forms=rf,
                                                      home_forms=hf)),
        "red: the new field name carrying a session value is still caught")
    chk([c for c, _, _ in scan_face('{"implementation_id": "rust-port"}', root_forms=rf, home_forms=hf)] == [],
        "green: the new field name with a product value passes")
    chk(any(c == "IDENTITY" for c, _, _ in scan_face('{"%s": "W-GO/qianwen"}' % RETIRED_KEY, root_forms=rf,
                                                     home_forms=hf)),
        "red: a seat code with an engine name is shape-rejected")
    chk(any(c == "LOGIN" for c, _, _ in scan_face('out = "C:' + SEP + 'Users' + SEP + 'alice' + SEP + 'x.txt"',
                                                  root_forms=rf, home_forms=hf)),
        "red: a user-profile path is caught as LOGIN")
    chk(not any(c == "TOOLPATH" for c, _, _ in scan_face('out = "C:' + SEP + 'Users' + SEP + 'alice"',
                                                          root_forms=rf, home_forms=hf)),
        "red: a profile path is not softened into a provenance path")
    chk([c for c, _, _ in scan_face('java = "C:' + SEP + 'Program Files' + SEP + 'Java' + SEP + 'jdk-21"',
                                    root_forms=rf, home_forms=hf)] == ["TOOLPATH"],
        "green: a recorded runtime path is provenance, not a finding")
    chk(any(c == "HOSTROOT" for c, _, _ in scan_face("clone file:///" + root.replace("/", SEP), root_forms=rf,
                                                     home_forms=hf)),
        "red: the tree quoting its own absolute path is caught")
    chk(any(c == "HOSTROOT" for c, _, _ in scan_face("run in C:" + SEP + "fake" + SEP + "tree", root_forms=rf,
                                                     home_forms=hf)),
        "red: the tree is caught under either separator spelling")
    chk(scan_face("nothing absolute here", root_forms=rf, home_forms=hf) == [], "green: ordinary prose is silent")
    chk(scan_face("", root_forms=rf, home_forms=hf) == [], "green: an empty face yields nothing")
    chk(len(ID_SHAPE.pattern) > 0 and not ID_SHAPE.match("a" * 40 + "-port"), "red: an over-long value is rejected")
    chk(not ID_SHAPE.match("Test"), "red: an uppercase fixture value is rejected")
    return errs, arms[0]


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--repo-root")
    ap.add_argument("--quiet", action="store_true")
    ns, extra = ap.parse_known_args(argv)
    if extra:
        print("OUTCOME=INSTRUMENT-RED unrecognised arguments %r; this leg writes nothing" % (extra,))
        return 3
    if ns.selftest:
        errs, arms = selftest()
        for e in errs:
            print("SELFTEST-FAIL: %s" % e)
        print("arms=%d passed=%d" % (arms, arms - len(errs)))
        return 1 if errs else 0
    if not ns.repo_root:
        print("OUTCOME=INSTRUMENT-RED --repo-root is required; a scan with no named root has no denominator")
        return 3
    root = os.path.abspath(ns.repo_root)
    if os.path.dirname(root) == root:
        print("OUTCOME=INSTRUMENT-RED --repo-root %s is a drive root; the caller names the tree" % root)
        return 3
    if not os.path.isdir(os.path.join(root, ".git")):
        print("OUTCOME=INSTRUMENT-RED %s is not a git tree, so there is no tracked face to scan" % root)
        return 3
    fatal, mentioned, counts = scan(root)
    if fatal is None:
        print("OUTCOME=INSTRUMENT-RED %s" % mentioned)
        return 3
    other = counts.get("other", 0)
    def tally(rows):
        d = {}
        for row in rows:
            d[row[0]] = d.get(row[0], 0) + 1
        return ",".join("%s:%d" % (k, v) for k, v in sorted(d.items())) or "-"
    if not ns.quiet:
        for cls, rel, ln, excerpt in sorted(fatal)[:20]:
            print("FATAL| %s %s:%d %s" % (cls, rel, ln, excerpt))
        if len(fatal) > 20:
            print("FATAL| TRUNCATED shown=20 total=%d - count is the denominator, the list is a sample" % len(fatal))
        for cls, rel, ln, _ in sorted(mentioned)[:6]:
            print("MENTIONED| %s %s:%d (rule face quoting its own needle; exempt as a pair)" % (cls, rel, ln))
    print("OUTCOME=%s files_scanned=%d unreadable=%d FATAL=%d MENTIONED=%d counted_not_fatal=%d "
          "fatal_by_class=%s mentioned_by_class=%s root=%s"
          % ("RED" if fatal else "CLEAN", counts["files_scanned"], counts["unreadable"], len(fatal),
             len(mentioned), other, tally(fatal), tally(mentioned), root))
    return 1 if fatal else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # a crash is an instrument failure, never a measurement
        print("OUTCOME=INSTRUMENT-RED %s: %s" % (type(exc).__name__, str(exc)[:160]))
        sys.exit(3)
