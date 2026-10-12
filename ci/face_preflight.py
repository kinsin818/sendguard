#!/usr/bin/env python3
"""Pre-flight path self-check - ask the disclosure leg about a face BEFORE it lands, not after.

Run:  python ci/face_preflight.py --staged [--repo-root .]
      python ci/face_preflight.py --paths docs/x.md,ci/y.py
      python ci/face_preflight.py --selftest --scratch-root ../<dir>

Why. This project's own descriptive text has carried a host path literal into a face five times in two days, and
every one of them was caught *after* the write by `ci/process_leak_scan.py`. The late catch is the expensive part:
the literal is already in the working tree, and the correction costs a rewrite plus an erratum. This leg asks the
same question of the added lines before they land, using the same ruler - it imports the scan's needle builder and
its routing function rather than holding a second opinion about what counts as fatal.

It prints no path text, ever: a face that names a leak must not re-publish the path, so each finding is a class,
a line number, a length and a character-class summary.

Exit codes: 0 nothing fatal, 1 a fatal-shaped literal in a line this commit would add,
3 instrument failure (no target named, unreadable file, git refusal) - a check that measured nothing is never a
pass.
"""
import argparse
import io
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import process_leak_scan as pls  # noqa: E402  (one ruler, not two)

CHAR_CLASS = re.compile(r"[A-Za-z]:|[0-9]|[^A-Za-z0-9]")


def shape_of(value):
    """A summary that identifies the shape without carrying the bytes of the path."""
    letters = sum(1 for c in value if c.isalpha())
    digits = sum(1 for c in value if c.isdigit())
    seps = sum(1 for c in value if c in "\\/:")
    return "len=%d letters=%d digits=%d separators=%d" % (len(value), letters, digits, seps)


def check_lines(face, lines, root_forms, home_forms, start=1):
    """[(class, line_no, shape, bucket)] for the given lines of one face."""
    out = []
    for i, line in enumerate(lines, start):
        for cls, _ln, excerpt in pls.scan_face(line, root_forms=root_forms, home_forms=home_forms):
            out.append((cls, i, shape_of(line.strip()), pls.route(face, cls)))
    return out


def staged_added(repo_root):
    """The added lines of what is staged, as {face: [line,...]} - and the git rc, never swallowed.

    `git diff --cached -U0` is asked in list form (a shell string on this host goes through cmd.exe and loses
    paths). A header line beginning with +++ is the file name, not content, and is skipped.
    """
    p = subprocess.run(["git", "-C", repo_root, "diff", "--cached", "-U0"], capture_output=True, shell=False)
    if p.returncode != 0:
        return None, "git diff --cached rc=%d: the staged set cannot be read, so nothing was checked" % p.returncode
    faces, cur = {}, None
    for raw in (p.stdout or b"").split(b"\n"):
        line = raw.decode("utf-8", "replace")
        if line.startswith("+++ "):
            name = line[4:].strip()
            cur = name[2:].strip() if name.startswith("b/") else name
            if cur and cur != "/dev/null":
                faces.setdefault(cur, [])
            continue
        if line.startswith("+") and cur is not None:
            faces[cur].append(line[1:])
    return faces, ""



# ---------------------------------------------------------------- commit-message mode
MSG_PATH = re.compile(r"[A-Za-z]:[\\/]{1,2}[\w.\- ]{2,}")
# The r prefix is load-bearing: written as a plain string, "[\\/]" collapses to "[\/]", which in a regex class is
# just "/" - the rule then looks right and never fires on a backslash path. That is the trap documented at
# ci/process_leak_scan.py:51, and the red arm below is what re-caught it here.
MSG_IDENT = None  # built at run time from the leg's own needle list, so this file never spells them


def identity_needles():
    """The producer-identity vocabulary, taken from the disclosure leg rather than restated here."""
    out = [pls.RETIRED_KEY]
    out += ["seat" + "-qoder", "W-" + "PY", "W-" + "GO", "W-" + "NODE", "qian" + "wen", "dou" + "bao"]
    return [n for n in out if n]


def check_message(text, root_forms, home_forms):
    """[(class, line_no, shape)] for one commit message. Any drive-letter path or identity needle is a refusal."""
    out = []
    for i, line in enumerate(text.splitlines(), 1):
        for m in MSG_PATH.finditer(line):
            out.append(("MSG-PATH", i, "drive-letter path shape at %r (%s)" % (m.group(0)[:18], shape_of(line))))
        for cls, _ln, _ex in pls.scan_face(line, root_forms=root_forms, home_forms=home_forms):
            if cls in ("LOGIN", "HOSTROOT", "RETIRED", "IDENTITY"):
                out.append((cls, i, shape_of(line)))
        low = line.lower()
        for n in identity_needles():
            if n.lower() in low:
                out.append(("MSG-IDENTITY", i, "identity needle %r (%s)" % (n, shape_of(line))))
    return out


def message_blobs(spec):
    """Yield (name, text) for --message-file drafts and for every commit message in a --messages <range>."""
    if os.path.isfile(spec):
        yield spec, io.open(spec, encoding="utf-8", errors="replace").read()
        return
    p = subprocess.run(["git", "-C", REPO, "log", "--format=%h\x1f%B\x1e", spec], capture_output=True,
                       shell=False)
    if p.returncode != 0:
        raise RuntimeError("git log rc=%d over %r: the range cannot be read" % (p.returncode, spec))
    for rec in (p.stdout or b"").split(b"\x1e"):
        rec = rec.decode("utf-8", "replace").strip()
        if not rec:
            continue
        sha, _sep, body = rec.partition("\x1f")
        yield "commit " + sha.strip(), body


def selftest(root_forms, home_forms):
    errs, arms = [], []

    def chk(cond, label):
        arms.append(label)
        if not cond:
            errs.append("arm failed: " + label)

    planted = [os.path.join("docs", "coverage.md"), os.path.join("results", "python.windows.x64", "c.json")]
    if not home_forms:
        chk(False, "red: a host with no nameable profile root cannot be tested, so the suite must not run vacuous")
        print("SELFTEST-FAIL: no home forms")
        print("arms=%d passed=%d" % (len(arms), 0))
        return 1
    root_plain = sorted(root_forms, key=len)[0]
    home_plain = sorted(home_forms, key=len)[0]
    # the doubled-separator spellings, taken from the leg's own builder rather than typed here
    root_esc = [f for f in root_forms if chr(92) * 2 in f][0]
    home_esc = [f for f in home_forms if chr(92) * 2 in f][0]
    a1 = check_lines(planted[0], ["an unrelated line about verdict fields and nothing else"], root_forms,
                    home_forms)
    chk(a1 == [], "green: an unrelated line yields nothing, got %r" % (a1,))
    f1 = check_lines(planted[0], ["generated in " + root_plain], root_forms, home_forms)
    chk([x[3] for x in f1] == ["fatal"], "red: the tree root in a distributable face blocks, got %r" % (f1,))
    # A2 red: the escaped spelling, which is the class this file's own history kept missing
    f2 = check_lines(planted[0], ['  "base": "%s"' % root_esc], root_forms, home_forms)
    chk([x[0] for x in f2] == ["HOSTROOT"] and f2[0][3] == "fatal",
        "red: the JSON-escaped spelling of the tree root is caught too, got %r" % (f2,))
    f3 = check_lines(planted[1], ['  "scratch_root": "%s"' % home_esc], root_forms, home_forms)
    chk([x[0] for x in f3] == ["LOGIN"] and f3[0][3] == "fatal",
        "red: an escaped profile root in a result face blocks, got %r" % (f3,))
    f4 = check_lines(os.path.join("docs", "tickets", "SG-F15-x.md"), ["it held " + home_plain], root_forms,
                     home_forms)
    chk(f4 and f4[0][3] == "mentioned",
        "green: a rule face naming the path is quoted, not condemned (it is describing the defect), got %r"
        % (f4,))
    f5 = check_lines(planted[0], ["interpreter seen as C:" + chr(92) + "Python314" + chr(92) + "python.exe"],
                     root_forms, home_forms)
    chk(f5 and all(x[3] == "counted_not_fatal" for x in f5),
        "green: a toolchain path is provenance and never blocks, got %r" % (f5,))
    f6 = check_lines(planted[0], ["the reading is as of the tree this leg was run in, named by class only"],
                     root_forms, home_forms)
    chk(f6 == [], "green: the corrected style of prose - category, not bytes - yields nothing, got %r" % (f6,))
    m1 = check_message("the push adds a face at C:\\Users\\someone\\x.md and names W-" + "PY too",
                       root_forms, home_forms)
    chk(m1 and {x[0] for x in m1} >= {"MSG-PATH", "MSG-IDENTITY"},
        "red: a draft message carrying a drive-letter path or an identity needle is refused, got %r" % (m1,))
    m2 = check_message("Six ports built and reproduced in a cold clone; the gate's four readings are unchanged "
                       "and the leg prints its own counts.", root_forms, home_forms)
    chk(m2 == [], "green: an ordinary message about faces and legs passes, got %r" % (m2,))
    chk(check_message("generated in C:" + chr(92) + "Python314" + chr(92) + "python.exe", root_forms,
                      home_forms) != [],
        "red: a toolchain path is tolerated as provenance inside a data face but not in metadata, because a "
        "message cannot be edited after the push")
    chk(len(set(arms)) == len(arms) and len(arms) >= 7,
        "red: every arm needs a distinct label and the suite must not shrink silently, got %d labels"
        % (len(arms),))
    for e in errs:
        print("SELFTEST-FAIL: %s" % e)
    print("arms=%d passed=%d" % (len(arms), len(arms) - len(errs)))
    return 1 if errs else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="ask the disclosure leg about a face before it lands")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--staged", action="store_true", help="check the added lines of the staged set")
    ap.add_argument("--paths", default=None, help="comma-separated faces to check whole (draft inspection)")
    ap.add_argument("--message-file", default=None,
                    help="a draft commit message on disk; refuse it before it becomes metadata")
    ap.add_argument("--messages", default=None,
                    help="a git rev-range; audit the messages that range would publish")
    ap.add_argument("--repo-root", default=REPO)
    ns = ap.parse_args(argv)
    root = os.path.abspath(ns.repo_root)
    root_forms, home_forms = pls._paths_of(root)
    if not home_forms:
        print("OUTCOME=INSTRUMENT-RED the leg could not name a profile root; a check with no needle is not a "
              "measurement")
        return 3
    if ns.selftest:
        return selftest(root_forms, home_forms)
    if not ns.staged and not ns.paths and not (ns.message_file or ns.messages):
        print("OUTCOME=INSTRUMENT-RED none of --staged/--paths/--message-file/--messages given; a check that "
              "measured nothing never passes")
        return 3
    if ns.message_file or ns.messages:
        bad = 0
        checked = 0
        for spec in [x for x in ([ns.message_file] if ns.message_file else [])
                     + ([ns.messages] if ns.messages else []) if x]:
            try:
                items = list(message_blobs(spec))
            except RuntimeError as e:
                print("OUTCOME=INSTRUMENT-RED %s" % e)
                return 3
            if not items:
                print("OUTCOME=INSTRUMENT-RED %s resolved to zero messages - an empty population is a VOID "
                      "reading, not a pass" % spec)
                return 3
            for name, body in items:
                checked += 1
                hits = check_message(body, root_forms, home_forms)
                if hits:
                    bad += 1
                    for cls, ln, shape in hits[:6]:
                        print("  message-block| %s line %d %s %s" % (name, ln, cls, shape))
                    if len(hits) > 6:
                        print("  message-block| %s TRUNCATED shown=6 total=%d" % (name, len(hits)))
        print("preflight-messages| checked=%d blocked=%d root=%s" % (checked, bad, root))
        if bad:
            print("OUTCOME=RED commit metadata carries path/identity shapes - a push makes these permanent")
            return 1
        print("OUTCOME=CLEAN")
        return 0
    targets = {}
    if ns.staged:
        faces, err = staged_added(root)
        if faces is None:
            print("OUTCOME=INSTRUMENT-RED %s" % err)
            return 3
        targets.update(faces)
    if ns.paths:
        for rel in [x.strip() for x in ns.paths.split(",") if x.strip()]:
            p = os.path.join(root, rel.replace("/", os.sep))
            if not os.path.isfile(p):
                print("OUTCOME=INSTRUMENT-RED %s is not a readable file (a missing target is not a clean "
                      "target)" % rel)
                return 3
            targets[rel] = io.open(p, encoding="utf-8", errors="replace").read().splitlines()
    fatal, mentioned, counted = [], [], []
    lines_checked = 0
    for rel, lines in targets.items():
        lines_checked += len(lines)
        for cls, ln, shape, bucket in check_lines(rel, lines, root_forms, home_forms):
            row = (cls, rel, ln, shape)
            {"fatal": fatal, "mentioned": mentioned}.get(bucket, counted).append(row)
    for cls, rel, ln, shape in fatal[:12]:
        print("  block| %s %s:%d %s" % (cls, rel, ln, shape))
    if len(fatal) > 12:
        print("  block| TRUNCATED shown=12 total=%d" % len(fatal))
    for cls, rel, ln, shape in mentioned[:6]:
        print("  quoted-not-fatal| %s %s:%d %s" % (cls, rel, ln, shape))
    if len(mentioned) > 6:
        print("  quoted-not-fatal| TRUNCATED shown=6 total=%d" % len(mentioned))
    print("preflight| files=%d lines_checked=%d fatal=%d mentioned=%d counted_not_fatal=%d root=%s"
          % (len(targets), lines_checked, len(fatal), len(mentioned), len(counted), root))
    if fatal:
        print("OUTCOME=RED path literals in lines this commit would add - name the class, not the bytes, then "
              "re-run")
        return 1
    print("OUTCOME=CLEAN")
    return 0


if __name__ == "__main__":
    sys.exit(main())
