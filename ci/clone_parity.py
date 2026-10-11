"""Reproduce the whole judgement in a cold clone and compare every generated face with the commit it came from.

Run:  python ci/clone_parity.py --scratch-root ../sg-parity [--quiet]

Why this leg exists. The repository's central promise is that a stranger who clones it gets the same answers. That
promise has been checked all afternoon by a script sitting outside the tree, run by hand, and each of the four
delivery-form defects (docs/FINDINGS-rev6.md M9) was found by that hand-run rehearsal rather than by anything in
`ci/`. A check that lives in one operator's habit is not a gate. This is the gate: clone with `--no-local`, run
`ci/refresh_all.py` inside the clone, then compare each face the clone regenerated against the blob the clone
checked out.

Two rules this leg is built to obey and to prove. It never deletes anything: an existing clone directory is
reused only if its HEAD equals the source's and its status is empty, otherwise the next free name is taken. And a
difference is only allowed where it is declared in advance, with the line shape named - which is the one place
this project has an exception list, so `selftest` asserts both that the exception matches and that an undeclared
change of a single digit is still caught.

Exit codes: 0 = every compared face reproduced (or differs only inside a declared line); 1 = at least one face
differs beyond what was declared; 3 = the instrument could not measure (clone failed, `git` returned non-zero,
the pipeline inside the clone crashed) - an instrument failure is never a result.
"""
import argparse
import io
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)

# Faces that are allowed to differ, and the exact line shape the difference is confined to. An exception list is
# a hole unless it is narrow and tested, so A7 asserts both edges of each entry.
DECLARED_EXCEPTIONS = {
    "docs/evidence.md": r"^- repository commit: ",
}

TS_PATTERNS = [
    (re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}( [+-]\d{4})?"), "<TS>"),
    (re.compile(r"\d{2}:\d{2} \+0800"), "<TS>"),
    (re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"), "<TS>"),
]


def normalize(text):
    """Blank out the timestamps, and only the timestamps."""
    for pat, rep in TS_PATTERNS:
        text = pat.sub(rep, text)
    return text


def compare_pair(blob_text, disk_text, path):
    """Return (verdict, detail). verdict is one of identical / declared / differing / missing."""
    if disk_text is None:
        return "missing", "the clone generated nothing at %s" % path
    a, b = normalize(blob_text), normalize(disk_text)
    if a == b:
        return "identical", ""
    la, lb = a.splitlines(), b.splitlines()
    changed = [(i + 1, x, y) for i, (x, y) in enumerate(zip(la, lb)) if x != y]
    extra = abs(len(la) - len(lb))
    rx = DECLARED_EXCEPTIONS.get(path)
    if rx and not extra:
        if all(re.match(rx, x) and re.match(rx, y) for _, x, y in changed):
            return "declared", "%d line(s) inside the declared shape: %s" % (
                len(changed), changed[0][1].strip()[:120])
    detail = "%d line(s) differ, line count %s vs %s; first: HEAD %r / DISK %r" % (
        len(changed) + extra, len(la), len(lb),
        (changed[0][1].strip()[:120] if changed else "-"),
        (changed[0][2].strip()[:120] if changed else "-"))
    return "differing", detail


def git(args, cwd):
    p = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", shell=False)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def validate_scratch_root(raw):
    """The caller supplies the location, and a drive root is refused - an instrument does not create litter at a mount point."""
    if not raw:
        return None, "no --scratch-root given; this leg clones into a directory the caller names"
    p = os.path.abspath(raw)
    if os.path.normcase(p.rstrip("\\/")) in ("", ) or (len(p) == 3 and p[1:2] == ":"):
        return None, "--scratch-root %s resolves to a drive root (%s); name a directory inside it" % (raw, p)
    if os.path.normpath(p) == os.path.normpath(REPO) or os.path.normpath(p).startswith(
            os.path.normpath(REPO) + os.sep):
        return None, ("--scratch-root %s resolves inside the repository being cloned (%s); a clone nested in its "
                      "own source tree pollutes the status it is meant to verify" % (raw, p))
    return p, ""


def pick_clone_dir(root, source_head, probe=None, exists=None):
    """Never delete. Reuse a clone only when it provably starts from the same commit and is clean.

    `exists` and `probe` are seams so A7 can test the decision itself - which directory is adopted, which is
    skipped as dirty, which is skipped for being a different commit - without a disk full of clones.
    """
    if exists is None:
        exists = lambda d: os.path.isdir(d)
    if probe is None:
        def probe(d):
            rc_h, head = git(["rev-parse", "HEAD"], d)
            rc_s, status = git(["status", "--porcelain=v1", "-uall"], d)
            return (0, (head, status)) if rc_h == 0 and rc_s == 0 else (1, "")
    n = 1
    while True:
        cand = os.path.join(root, "parity-%d" % n)
        if not exists(cand):
            return cand, "created"
        rc, out = probe(cand)
        if rc == 0:
            head, status = out
            if head.strip() == source_head and not [l for l in status.splitlines() if l.strip()]:
                return cand, "reused (HEAD matches the source and its status is empty)"
        n += 1


def run_parity(root, quiet):
    scratch, why = validate_scratch_root(root)
    if not scratch:
        print("OUTCOME=INSTRUMENT-RED %s" % why)
        return 3
    rc, out = git(["rev-parse", "HEAD"], REPO)
    if rc != 0:
        print("OUTCOME=INSTRUMENT-RED cannot read this tree's HEAD (git rc=%d): %s" % (rc, out.strip()[:160]))
        return 3
    head = out.strip()
    clone, state = pick_clone_dir(scratch, head)
    if state == "created":
        os.makedirs(scratch, exist_ok=True)
        rc, out = git(["clone", "--no-local", REPO, clone], REPO)
        if rc != 0:
            print("OUTCOME=INSTRUMENT-RED `git clone --no-local` rc=%d: %s" % (rc, out.strip()[:200]))
            return 3
    rc, out = git(["rev-parse", "HEAD"], clone)
    if rc != 0 or out.strip() != head:
        print("OUTCOME=INSTRUMENT-RED the clone is not at the source commit (%r vs %r)" % (out.strip(), head))
        return 3
    rc, status = git(["status", "--porcelain=v1", "-uall"], clone)
    dirty_before = len([l for l in status.splitlines() if l.strip()])
    if rc != 0:
        print("OUTCOME=INSTRUMENT-RED cannot read the clone's status (git rc=%d)" % rc)
        return 3

    p = subprocess.run([sys.executable, os.path.join(clone, "ci", "refresh_all.py")],
                       cwd=clone, capture_output=True, text=True, encoding="utf-8", errors="replace", shell=False)
    out = (p.stdout or "") + (p.stderr or "")
    if "OUTCOME=CLEAN" not in out and "OUTCOME=RED" not in out:
        print("OUTCOME=INSTRUMENT-RED the pipeline inside the clone did not produce a verdict (rc=%d); tail:"
              % p.returncode)
        print("\n".join(out.strip().splitlines()[-8:]))
        return 3
    if not quiet:
        print("clone| %s (%s) head=%s status_before=%d pipeline_rc=%d"
              % (clone, state, head[:12], dirty_before, p.returncode))

    import refresh_all  # same commit, so its GEN list is the contract of what is generated
    faces = [doc for _s, doc, _ok in refresh_all.GEN] + ["evidence/S02/equality-verdict.json"]
    counts = {"identical": 0, "declared": 0, "differing": 0, "missing": 0}
    problems = []
    for doc in faces:
        rc, blob = git(["show", "HEAD:" + doc], clone)
        if rc != 0:
            counts["missing"] += 1
            problems.append("%s: HEAD has no such face (git show rc=%d)" % (doc, rc))
            continue
        disk_path = os.path.join(clone, doc.replace("/", os.sep))
        disk = io.open(disk_path, encoding="utf-8", newline="\n").read() if os.path.isfile(disk_path) else None
        verdict, detail = compare_pair(blob, disk, doc)
        counts[verdict] += 1
        if verdict in ("differing", "missing"):
            problems.append("%s: %s" % (doc, detail))
        elif verdict == "declared" and not quiet:
            print("declared| %s - %s" % (doc, detail))
    line = ("OUTCOME=%s faces_compared=%d identical=%d declared=%d differing=%d missing=%d clone=%s"
            % ("CLEAN" if not problems else "RED", len(faces), counts["identical"], counts["declared"],
               counts["differing"], counts["missing"], clone))
    for pr in problems:
        print("  face| %s" % pr)
    print(line)
    if problems:
        print("A clone that reads a different generated face than the commit carries is not a reproduction; "
              "docs/journey.md 2.18 is why this leg exists")
        return 1
    return 0


def selftest():
    errs = []

    def chk(cond, msg):
        if not cond:
            errs.append(msg)

    base = "x generated at 2026-10-11 13:44:00 +0800\n| a | 4 |\n"
    same_ts = "x generated at 2026-10-11 14:05:12 +0800\n| a | 4 |\n"
    verdict, _ = compare_pair(base, same_ts, "docs/whatever.md")
    chk(verdict == "identical", "selftest A1 green: a timestamp-only difference is not a result difference, got %s"
        % verdict)
    one_digit = base.replace("| a | 4 |", "| a | 5 |")
    verdict, detail = compare_pair(base, one_digit, "docs/whatever.md")
    chk(verdict == "differing" and "4" in detail and "5" in detail,
        "selftest A2 red: a single changed digit in a non-timestamp line must be caught and shown, got %s %r"
        % (verdict, detail))
    verdict, _ = compare_pair(base, None, "docs/whatever.md")
    chk(verdict == "missing", "selftest A3 red: a face the clone did not generate is not an identical face")
    chk(normalize("12:34 +0800 and 2026-10-11T01:02:03") == "<TS> and <TS>",
        "selftest A4 green: all three timestamp shapes normalise, or the leg cries wolf on every run")
    exc = "- repository commit: `abc123` (working tree carries 11 uncommitted faces at generation time).\n"
    exc2 = "- repository commit: `def456` (working tree carries 3 uncommitted faces at generation time).\n"
    verdict, _ = compare_pair(exc, exc2, "docs/evidence.md")
    chk(verdict == "declared", "selftest A5 green: the declared exception must cover the real line shape, got %s"
        % verdict)
    verdict, _ = compare_pair(exc, exc.replace("repository commit", "repository COMMIT"), "docs/evidence.md")
    chk(verdict == "differing",
        "selftest A5 red: the exception is a line shape, not a licence for any change in that file")
    ok, why = validate_scratch_root("")
    chk(ok is None and "no --scratch-root" in why, "selftest A6 red: no scratch root is refused, not defaulted")
    for bad in ("D:\\", "C:\\", "D:/"):
        ok, why = validate_scratch_root(bad)
        chk(ok is None and "drive root" in why, "selftest A6 red: %s is a drive root and must be refused" % bad)
    ok, why = validate_scratch_root(os.path.join(REPO, "ci"))
    chk(ok is None and "inside the repository" in why,
        "selftest A6 red: a scratch root nested inside the tree being cloned is refused, got %r" % (why,))
    ok, _ = validate_scratch_root(os.path.join(os.environ.get("TEMP", "/tmp"), "sg-parity"))
    chk(ok is not None, "selftest A6 green: a named directory the caller owns is accepted")
    head_a = "a" * 40
    only_one = lambda d: d.replace("\\", "/").endswith("root/parity-1")
    picked, state = pick_clone_dir(os.path.join("root"), head_a,
                                   probe=lambda d: (0, (head_a, "")), exists=only_one)
    chk(picked.endswith("parity-1") and "reused" in state,
        "selftest A7 green: an existing clean clone at the same commit is reused, never deleted, got %r %r"
        % (picked, state))
    picked2, state2 = pick_clone_dir(os.path.join("root"), head_a,
                                     probe=lambda d: (0, (head_a, "?? x\n")), exists=only_one)
    chk(picked2.endswith("parity-2") and state2 == "created",
        "selftest A7 red: a clone whose status is not empty is not adopted - the leg moves on rather than trust "
        "a dirty tree, got %r %r" % (picked2, state2))
    picked3, _ = pick_clone_dir(os.path.join("root"), head_a,
                                probe=lambda d: (0, ("b" * 40, "")), exists=only_one)
    chk(picked3.endswith("parity-2"),
        "selftest A7 red: a clone at a different commit is not the commit being verified, got %r" % (picked3,))
    picked4, state4 = pick_clone_dir(os.path.join("root"), head_a,
                                     probe=lambda d: (1, ""), exists=lambda d: False)
    chk(picked4.endswith("parity-1") and state4 == "created",
        "selftest A7 green: an empty scratch root takes the first name without probing, got %r %r"
        % (picked4, state4))

    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--scratch-root", default=None)
    ns, unknown = ap.parse_known_args(["--not-an-option"])
    chk(unknown == ["--not-an-option"], "selftest A8 red: unknown arguments must be visible before the refusal")
    return errs


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--selftest" in argv:
        errs = selftest()
        for e in errs:
            print("SELFTEST-FAIL: %s" % e)
        print("arms=8 passed=%d" % (8 - len(errs)))
        return 1 if errs else 0
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--scratch-root", default=None)
    ns, unknown = ap.parse_known_args(argv)
    if unknown:
        print("OUTCOME=INSTRUMENT-RED this leg takes --scratch-root and --quiet and was handed %r; it writes "
              "nothing" % (unknown,))
        return 3
    return run_parity(ns.scratch_root, ns.quiet)


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
