"""Every relative link in the tracked markdown must resolve to a face the repository actually carries.

Run:  python ci/link_check.py [--selftest]

Why. The repository became public at 15:14, which changes what a broken reference costs: a path that does not
resolve is no longer a private annoyance, it is a 404 in front of a buyer. Measuring it the obvious way is how
you get a gate that cries wolf - the one "broken link" found on the first sweep was `](:GRID[-_)`, a regular
expression inside `evidence/S02/rust-selfcheck.md`, not a link at all. So code spans and fenced blocks are
excluded before the link pattern is applied, and that exclusion is one of the arms.

Exit codes: 0 = every link resolves; 1 = at least one link does not, or a link escapes the repository; 3 = the
leg could not enumerate the tree (`git ls-files` failed) - an instrument failure, never a clean bill.
"""
import io
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

LINK = re.compile(r"\[([^\]]*)\]\(([^)\s]+)(?:#[^)]*)?\)")
FENCE = re.compile(r"^\s*(```|~~~)")


def strip_code(text):
    """Blank out fenced blocks and inline code spans, so a regex or a command inside them is not read as a link."""
    out = []
    inside = False
    for line in text.split("\n"):
        if FENCE.match(line):
            inside = not inside
            out.append("")
            continue
        if inside:
            out.append("")
            continue
        out.append(re.sub(r"`[^`]*`", "``", line))
    return "\n".join(out)


def relative_links(text, origin):
    """(line, label, target) for every markdown link in `text` that points at the repository.

    Absolute URLs are returned as kind=external so the face can print them as a denominator without pretending to
    have fetched them - a link check that silently skips the network must say so.
    """
    found = []
    base = os.path.dirname(origin)
    for i, line in enumerate(text.split("\n"), 1):
        for _label, tgt in LINK.findall(line):
            if tgt.startswith(("http://", "https://", "mailto:", "//")):
                found.append((i, tgt, "external"))
                continue
            norm = os.path.normpath(os.path.join(base, tgt)).replace(os.sep, "/") if base else \
                os.path.normpath(tgt).replace(os.sep, "/")
            found.append((i, tgt, "escape" if norm.startswith("..") else "relative"))
    return found


def check(tracked, docs):
    """Return (checked, ok, problems, externals)."""
    problems, ok, externals, checked = [], 0, 0, 0
    for doc in docs:
        text = strip_code(docs[doc])
        for line, tgt, kind in relative_links(text, doc):
            checked += 1
            if kind == "external":
                externals += 1
                continue
            if kind == "escape":
                problems.append("%s:%d `%s` leaves the repository - a link a stranger cannot resolve" % (doc, line, tgt))
                continue
            norm = os.path.normpath(os.path.join(os.path.dirname(doc), tgt)).replace(os.sep, "/") if os.path.dirname(doc) else tgt
            if norm in tracked or (norm + "/") in {d + "/" for d in tracked}:
                ok += 1
            elif any(t.startswith(norm + "/") for t in tracked):
                ok += 1  # a directory link: it resolves if anything lives under it
            else:
                problems.append("%s:%d links `%s`, which no face in the tree answers to" % (doc, line, tgt))
    return checked, ok, problems, externals


SELFTEST_ARMS = 6


def selftest():
    errs = []
    seen = set()

    def chk(cond, msg):
        m = re.match(r"selftest (A\d+)", msg)
        if m:
            seen.add(m.group(1))
        if not cond:
            errs.append(msg)

    tracked = {"README.md": "", "docs/a.md": "", "spec/cases.yaml": ""}
    good = {"docs/a.md": "see [the spec](../spec/cases.yaml) and [README](../README.md)\n"}
    c, ok, p, e = check(tracked, good)
    chk(c == 2 and ok == 2 and not p,
        "selftest A1 green: links that resolve must pass, or this gate is only able to say no, got %r" % (p,))
    bad = {"docs/a.md": "broken [target](../spec/nope.yaml)\n"}
    c, ok, p, e = check(tracked, bad)
    chk(c == 1 and ok == 0 and len(p) == 1 and "nope.yaml" in p[0],
        "selftest A2 red: a link to a face that does not exist must be named, got %r" % (p,))
    esc = {"docs/a.md": "out [there](../../elsewhere/file.md)\n"}
    c, ok, p, e = check(tracked, esc)
    chk(len(p) == 1 and "leaves the repository" in p[0],
        "selftest A3 red: a link that escapes the tree is its own failure, not a silent skip, got %r" % (p,))
    code = {"docs/a.md": "pattern ](:GRID[-_] is not a link\n\n```\n[fake](./nothere.md)\n```\n"
                         "and `inline [x](./missing.md)` too\n"}
    c, ok, p, e = check(tracked, code)
    chk(c == 0 and not p,
        "selftest A4 green: a regex or a command that looks like a link must not be counted - this was the false "
        "alarm on the first real sweep, got %r %r" % (c, p))
    ext = {"docs/a.md": "upstream [spec](https://example.com/x) here\n"}
    c, ok, p, e = check(tracked, ext)
    chk(c == 1 and e == 1 and not p and ok == 0,
        "selftest A5 green: an external link is counted as external and never as resolved - nothing here fetched "
        "it, got %r" % ((c, ok, e, p),))
    chk(len(seen) + 1 == SELFTEST_ARMS,
        "selftest A6 red: the published arm count must equal the labels that ran - %d (%s) against %d; the guard "
        "counts itself" % (len(seen), ",".join(sorted(seen)), SELFTEST_ARMS))
    return errs


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--selftest" in argv:
        errs = selftest()
        for e in errs:
            print("SELFTEST-FAIL: %s" % e)
        print("arms=%d passed=%d" % (SELFTEST_ARMS, SELFTEST_ARMS - len(errs)))
        return 1 if errs else 0
    unknown = [a for a in argv if a not in ("--selftest", "--quiet")]
    if unknown:
        print("OUTCOME=INSTRUMENT-RED this leg takes --selftest and --quiet and was handed %r; it writes nothing"
              % (unknown,))
        return 3
    r = subprocess.run(["git", "ls-files", "-z"], cwd=REPO, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print("OUTCOME=INSTRUMENT-RED `git ls-files` rc=%d - no enumeration, so no verdict on links" % r.returncode)
        return 3
    tracked = {}
    for f in [x for x in r.stdout.split(chr(0)) if x]:
        tracked[f] = True
    docs = {}
    unreadable = []
    for f in tracked:
        if not f.endswith(".md"):
            continue
        p = os.path.join(REPO, f.replace("/", os.sep))
        try:
            docs[f] = io.open(p, encoding="utf-8", errors="replace").read()
        except Exception as ex:
            unreadable.append("%s: %s" % (f, type(ex).__name__))
    checked, ok, problems, externals = check({k: 1 for k in tracked}, docs)
    for x in problems[:25]:
        print("  broken| %s" % x)
    if len(problems) > 25:
        print("  broken| TRUNCATED shown=25 total=%d" % len(problems))
    for x in unreadable[:5]:
        print("  unreadable| %s" % x)
    print("OUTCOME=%s markdown_faces=%d links_checked=%d resolved=%d external=%d broken=%d unreadable=%d"
          % ("CLEAN" if not problems else "RED", len(docs), checked, ok, externals, len(problems), len(unreadable)))
    return 1 if problems else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        print("OUTCOME=INSTRUMENT-RED %s: a crash is not a measurement" % type(e).__name__)
        sys.exit(3)
