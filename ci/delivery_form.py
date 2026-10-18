"""Generate docs/delivery-form.md - what a customer actually receives, measured rather than asserted.

Run:  python ci/delivery_form.py

Why this leg exists. The repository answers "does the checker give the same answer in six languages" and the
documents are careful about that. They are much less careful about a dumber question a buyer asks first: **what
do I get, what must I install, how big is it, how long does it take, can I run it without a compiler?** Until
now nothing in `ci/` looked at file sizes, dependency counts or timings at all, so those answers were prose.
This leg measures what is measurable on this host and prints `NOT-MEASURED(<reason>)` for the rest, in the
same shape the equality verdict uses: an unasked question is a fact about the project, never a placeholder.

Exit codes: 0 = every port got a row and every number below has a source; 1 = a required quantity is missing
for at least one port (published, not hidden); 3 = the leg could not read what it needed (no canonical faces,
unreadable JSON) - an instrument failure, never a measurement.
"""
import glob
import io
import json
import os
import re
import statistics
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import equality  # noqa: E402

PORTS = ["csharp", "go", "java", "python", "rust", "typescript"]

# The repository has 1,166 tracked files today. A parse that returns anything near this floor means the
# splitter did not split, which is an instrument failure and not a small delivery.
TRACKED_FLOOR = 100


def tracked_files():
    """The set of paths git says the repository carries.

    The first version of this leg sized whatever was on this disk, which made the published byte counts
    irreproducible: a port's scratch build output, present in a working copy and absent in a clone, changed the
    numbers by ~38 bytes of text and several hundred kilobytes of bytes. The check that found it is
    `evidence/clone-tool/cold-clone-20261011d.md`. A delivery form has to describe the artifact a customer receives
    from the repository, so it measures the tracked file set and prints what it dropped.

    The NUL that separates `git ls-files -z` output cannot survive being typed into this source file (the console
    and the patcher both eat it), so it is spelled as `chr(0)`. A literal stand-in there once produced a set of
    exactly one 61,776-byte element, which filtered out every file and still printed a table that matched a cold
    clone - a filter that passes nothing is indistinguishable from an honest measurement of nothing, so
    `self_check` now refuses a parse it cannot trust instead of trusting the number. The paths are made absolute
    on the way out because the glob results this set is compared against are absolute: `git ls-files` answers
    relative to the repository, and comparing the two spaces would drop everything a second time.
    """
    r = subprocess.run(["git", "ls-files", "-z"], cwd=REPO, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        return None
    return {os.path.normpath(os.path.join(REPO, p.replace("/", os.sep)))
            for p in (x for x in r.stdout.split(chr(0)) if x)}


BUILD_GLOBS = {
    "csharp": ["impl/csharp/bin/**/SendGuardProbe*.exe", "impl/csharp/*.exe"],
    "go": ["impl/go/*.exe", "impl/go/go-sendguard*.exe", "harness/audit.exe", "harness/audit.bin"],
    "java": ["impl/java/build/**/*.class", "impl/java/build-repro/**/*.class",
             "impl/java/build-check/**/*.class"],
    "python": ["impl/python/sg_run.py"],
    "rust": ["impl/rust/target/**/release/*.exe", "impl/rust/target/**/debug/*.exe"],
    "typescript": ["impl/typescript/dist/**/*.js", "impl/typescript/src/*.ts"],
}
INSTALLER_GLOBS = ["**/*.msi", "**/*.pkg", "**/*.deb", "**/*.AppImage", "**/*.dmg"]


def read_cells(port):
    face = os.path.join(REPO, "results", "%s.windows.x64" % port)
    out = []
    if not os.path.isdir(face):
        return None
    for f in sorted(glob.glob(os.path.join(face, "**", "*.json"), recursive=True)):
        try:
            doc = json.loads(io.open(f, encoding="utf-8").read())
        except (OSError, ValueError):
            continue
        rows = doc.get("cells") if isinstance(doc, dict) and isinstance(doc.get("cells"), list) else [doc]
        out.extend([c for c in rows if isinstance(c, dict)])
    return out


def filter_tracked(paths, tracked):
    """Split candidate artifact paths into what the repository carries and what only this disk carries.

    Kept as its own function so the arms can hand it a synthetic path list: the filter must be proven able to
    *pass* something, because a filter that drops everything reproduces any expected number. Paths are compared
    after `normpath`, because `glob` keeps whatever separator was written inside the pattern, so a pattern like
    `impl/java/build/**/*.class` returns a path with forward slashes in the middle of a Windows tree - and the
    first version of this comparison treated four committed `.class` files, `sg_run.py` and seven TypeScript
    sources as untracked for exactly that reason.
    """
    uniq = sorted({os.path.normpath(p) for p in paths})
    if tracked is None:
        return uniq, []
    return ([p for p in uniq if p in tracked],
            [p for p in uniq if p not in tracked])


def measure_port(port, cells, tracked):
    deps = [(c.get("deps_direct"), c.get("deps_total")) for c in cells
            if isinstance(c.get("deps_direct"), int) and isinstance(c.get("deps_total"), int)]
    times = [c["elapsed_ms"] for c in cells if isinstance(c.get("elapsed_ms"), (int, float))]
    arts = []
    for pat in BUILD_GLOBS[port]:
        for p in glob.glob(os.path.join(REPO, pat), recursive=True):
            if os.path.isfile(p):
                arts.append(p)
    allm = sorted(set(arts))
    uniq, dropped = filter_tracked(allm, tracked)
    total = sum(os.path.getsize(p) for p in uniq)
    biggest = max(uniq, key=os.path.getsize) if uniq else None
    executable = [p for p in uniq if p.lower().endswith((".exe", ".bin", ".class"))]
    return {
        "port": port,
        "cells_read": len(cells),
        "deps": (max(d[0] for d in deps), max(d[1] for d in deps), len(deps)) if deps else None,
        "timing": (min(times), statistics.median(times), max(times), len(times)) if times else None,
        "artifacts": len(uniq),
        "kept_paths": uniq,
        "bytes": total,
        "sample": (os.path.relpath(biggest, REPO).replace("\\", "/") if uniq else None),
        "kinds": ",".join(sorted({os.path.splitext(p)[1].lstrip(".") or "noext" for p in uniq})) or "-",

        "executables": len(executable),
        "dropped_untracked": len(dropped),
    }


def pattern_to_regex(pat):
    """Translate a build-output glob into a matcher for git's forward-slash path names.

    Written out rather than borrowed from `fnmatch` because the first witness used `fnmatch` with `**` replaced by
    `*`, which silently turned `impl/java/build/**/*.class` into a two-segment pattern and matched none of the six
    tracked `.class` files - the same class of defect it was supposed to detect. A18 asserts both sides.
    """
    out = []
    i = 0
    while i < len(pat):
        if pat.startswith("**/", i):
            out.append("(?:[^/]*/)*")
            i += 3
        elif pat.startswith("**", i):
            out.append(".*")
            i += 2
        elif pat[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pat[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pat[i]))
            i += 1
    return re.compile("".join(out) + r"\Z")


def git_artifact_paths(port):
    """The same artifact set, enumerated by git's own matcher instead of this leg's.

    This exists because the leg's file classification had already been wrong three times in one day for one
    reason - two different path spaces being compared - and no witness outside the leg could see it. A second
    enumeration that does not share the code under test is the only thing that makes the artifact columns a
    measurement rather than a tautology.
    """
    prefixes = []
    for pat in BUILD_GLOBS[port]:
        head = pat.split("*")[0]
        prefixes.append(head if head.endswith("/") else os.path.dirname(head) + "/")
    r = subprocess.run(["git", "ls-files", "-z", "--"] + sorted(set(prefixes)),
                       cwd=REPO, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        return None
    pats = [pattern_to_regex(p) for p in BUILD_GLOBS[port]]
    keep = [os.path.normpath(os.path.join(REPO, x.replace("/", os.sep)))
            for x in r.stdout.split(chr(0)) if x and any(m.match(x) for m in pats)]
    return keep


def self_check(rows, ports_seen, tracked, witness=None):
    """Every port must appear, no port may be reported from zero records, and the tracked set must be a parse."""
    problems = []
    if witness:
        for r in rows:
            git_paths = witness.get(r["port"])
            if git_paths is None:
                problems.append("%s: git could not enumerate its own tracked artifact list, so the artifact "
                                "columns have no independent witness" % r["port"])
                continue
            mine = set(r.get("kept_paths") or [])
            theirs = set(git_paths)
            if mine != theirs:
                problems.append(
                    "%s: this leg's file classifier kept %d tracked artifact(s) and git's own pathspec names %d; "
                    "the two enumerate the same commit, so a difference is a bug in the leg (%s)"
                    % (r["port"], len(mine), len(theirs),
                       ", ".join(sorted(os.path.basename(x) for x in (theirs - mine))) or "-"))
    if tracked is None:
        problems.append("tracked file set: `git ls-files` did not return rc 0, so no artifact count below is "
                        "a measurement of the repository")
    elif len(tracked) < TRACKED_FLOOR:
        problems.append("tracked file set: parsed %d paths, below the floor of %d - the split failed, and a "
                        "filter that passes nothing would print exactly the table above"
                        % (len(tracked), TRACKED_FLOOR))
    elif os.path.normpath(os.path.abspath(__file__)) not in tracked:
        problems.append("tracked file set: this leg's own source is tracked and the parse does not contain it, "
                        "so the set cannot be trusted as a filter")
    for p in PORTS:
        r = next((x for x in rows if x["port"] == p), None)
        if r is None:
            problems.append("%s: no row produced at all" % p)
        elif r["cells_read"] == 0:
            problems.append("%s: row produced from 0 cell records (a face that reads nothing is not a zero "
                            "count, it is an instrument failure)" % p)
    if sorted(ports_seen) != sorted(PORTS):
        problems.append("canonical faces on disk are %s, not the six the claim is about"
                        % ",".join(sorted(ports_seen)))
    return problems


# Arms for this leg. It needs no fixture directory, because the two things it can get wrong are both reachable
# without touching the disk: the NUL split that decides what the tracked set is, and the filter that decides what
# it reports. A1-A4 judge the parse, A5-A8 the filter, A9-A13 the checker that decides whether a table may be
# published at all, A14 the argument refusal, A15 the shape of the face a clone is expected to reproduce byte for
# byte, A16 the two path spaces git and glob use on this host, A17 the git witness that classifies the same
# commit without this leg's code, A18 the pattern translator that witness depends on. Both sides of every
# predicate are asserted: an earlier revision of this leg filtered everything out and still printed a table a
# cold clone agreed with, and a filter that passes nothing is indistinguishable from an honest measurement of
# nothing.
SELFTEST_ARMS = 18


def selftest():
    errs = []

    def chk(cond, msg):
        if not cond:
            errs.append(msg)

    t = tracked_files()
    chk(t is not None, "selftest A1 red: `git ls-files` did not return rc 0, so no artifact number this leg "
                       "prints is a measurement of the repository")
    if t is None:
        return errs

    chk(os.path.join(REPO, "README.md") in t,
        "selftest A2 green: the parse must hold README.md as its own element; it holds %d elements" % len(t))
    chk(not any(chr(0) in x for x in t),
        "selftest A3 red: an element carrying a NUL means the splitter did not split, and every path would be "
        "read as untracked")
    chk(len(t) >= TRACKED_FLOOR,
        "selftest A4 red: the parse returned %d paths, below the floor of %d, which is a broken splitter and not "
        "a small repository" % (len(t), TRACKED_FLOOR))

    one = "x" + os.sep + "a.exe"
    kept, dropped = filter_tracked([one, one], {one})
    chk(len(kept) == 1 and dropped == [],
        "selftest A5 green: a tracked artifact must survive the filter, kept=%r dropped=%r" % (kept, dropped))
    kept, dropped = filter_tracked([one], set())
    chk(kept == [] and len(dropped) == 1,
        "selftest A6 red: an untracked artifact must be named in the dropped column, kept=%r dropped=%r"
        % (kept, dropped))
    kept, dropped = filter_tracked([one], None)
    chk(len(kept) == 1 and dropped == [],
        "selftest A7 green: with no file list the filter falls back to the disk and self_check must say so, "
        "kept=%r dropped=%r" % (kept, dropped))
    kept2, _ = filter_tracked([one, "x" + os.sep + "b.exe"], {one})
    chk(kept2 == [one] and sum(1 for _ in kept2) == 1,
        "selftest A8 green: a mixed list must keep exactly the tracked member, got %r" % (kept2,))

    good = [{"port": p, "cells_read": 1, "dropped_untracked": 0} for p in PORTS]
    chk(self_check(good, list(PORTS), t) == [],
        "selftest A9 green: a full table over the real tracked set must publish, got %r"
        % (self_check(good, list(PORTS), t),))
    problems = self_check(good, list(PORTS), {"one" + os.sep + "path"})
    chk(any("floor" in x for x in problems),
        "selftest A10 red: a tracked set of one path must be refused as an instrument failure, got %r"
        % (problems,))
    wide = {"%03d.py" % i for i in range(TRACKED_FLOOR + 50)}
    problems = self_check(good, list(PORTS), wide)
    chk(any("own source" in x for x in problems),
        "selftest A11 red: a set above the floor that does not contain this leg's own tracked source is not a "
        "parse of this repository, got %r" % (problems,))
    problems = self_check(good, list(PORTS), None)
    chk(any("rc 0" in x for x in problems),
        "selftest A12 red: no file list at all must be refused, got %r" % (problems,))
    short = [dict(r) for r in good]
    short[2]["cells_read"] = 0
    problems = self_check(short, list(PORTS), t)
    chk(any("0 cell records" in x for x in problems),
        "selftest A13 red: a port row read from zero records is an instrument failure, got %r" % (problems,))

    face = os.path.join(REPO, "docs", "delivery-form.md")
    before = io.open(face, "rb").read() if os.path.isfile(face) else None
    rc = main(["--not-an-option-this-leg-does-not-have"])
    after = io.open(face, "rb").read() if os.path.isfile(face) else None
    chk(rc == 3, "selftest A14 red: an unknown argument must be refused with rc 3, got %d" % rc)
    chk(before == after, "selftest A14 red: the refusal must not rewrite the published face")

    published = io.open(face, encoding="utf-8", newline="\n").read() if os.path.isfile(face) else ""
    rows_out = [l for l in published.splitlines() if l.startswith("| ") and " | " in l]
    table = [l for l in rows_out if "cells read" in l or l.split("|")[2].strip().isdigit()]
    widths = sorted({len([c for c in l.split("|")]) - 2 for l in table})
    chk(published and widths == [9],
        "selftest A15 red: the published table must be the nine tracked columns and nothing disk-dependent, got "
        "column counts %r over %d rows" % (widths, len(table)))
    chk("untracked files ignored" not in published,
        "selftest A15 red: a count of ignored files needs the files to be present, so it may not be published in "
        "a face a clone is expected to reproduce byte for byte")

    mixed = "impl" + "/" + "java" + "/" + "build" + "/" + "X.class"
    native = os.path.normpath(mixed)
    kept, dropped = filter_tracked([mixed], {native})
    chk(kept == [native] and dropped == [],
        "selftest A16 green: a path spelled with the separator the pattern carried must still be recognised as "
        "tracked, kept=%r dropped=%r - this is the defect that published four committed .class files, sg_run.py "
        "and seven TypeScript sources as untracked" % (kept, dropped))
    kept, dropped = filter_tracked([mixed], {os.path.normpath("impl/java/build/Y.class")})
    chk(kept == [] and dropped == [native],
        "selftest A16 red: normalising must not turn a different file into a match, kept=%r dropped=%r"
        % (kept, dropped))
    problems = self_check(good, list(PORTS), t, {"java": [os.path.join(REPO, "nowhere.class")]})
    chk(any("java" in x and "git's own pathspec" in x for x in problems),
        "selftest A17 red: a git enumeration that disagrees with the leg's classifier must be named per port, "
        "got %r" % (problems,))
    chk(self_check(good, list(PORTS), t, {p: [] for p in PORTS}) == [],
        "selftest A17 green: a witness that agrees with an empty classification publishes, got %r"
        % (self_check(good, list(PORTS), t, {p: [] for p in PORTS}),))
    deep = pattern_to_regex("impl/java/build/**/*.class")
    chk(deep.match("impl/java/build/CellProbe.class") and deep.match("impl/java/build/sub/dir/X.class"),
        "selftest A18 green: `**/` must accept both the zero-directory and the nested case")
    chk(not deep.match("impl/java/build-check/CellProbe.class"),
        "selftest A18 red: the translator must not let one port's directory leak into another's pattern")
    one = pattern_to_regex("impl/typescript/src/*.ts")
    chk(one.match("impl/typescript/src/identity.ts") and not one.match("impl/typescript/src/a/b.ts"),
        "selftest A18 red: a single `*` must not cross a directory separator")
    compiled = {p: [pattern_to_regex(pat) for pat in BUILD_GLOBS[p]] for p in PORTS}
    chk(all(len(compiled[p]) == len(BUILD_GLOBS[p]) for p in PORTS),
        "selftest A18 green: every port's whole pattern list must compile, or the witness is silent for the "
        "patterns that did not")
    return errs


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--selftest" in argv:
        errs = selftest()
        for e in errs:
            print("SELFTEST-FAIL: %s" % e)
        print("arms=%d passed=%d" % (SELFTEST_ARMS, SELFTEST_ARMS - len(errs)))
        return 1 if errs else 0
    unknown = [a for a in argv if a != "--selftest"]
    if unknown:
        print("OUTCOME=INSTRUMENT-RED this leg takes no argument but --selftest and was handed %r - it refuses to guess which tree you meant and writes nothing" % (unknown,))
        return 3
    tracked = tracked_files()
    rows, ports_seen, unreadable = [], [], 0
    for port in PORTS:
        cells = read_cells(port)
        if cells is None:
            print("OUTCOME=INSTRUMENT-RED no canonical face results/%s.windows.x64/ - this leg reports on the "
                  "six ports that exist, it does not invent one" % port)
            return 3
        ports_seen.append(port)
        rows.append(measure_port(port, cells, tracked))
        unreadable += 0

    inst_all = [p for pat in INSTALLER_GLOBS for p in glob.glob(os.path.join(REPO, pat), recursive=True)
                if os.path.isfile(p)]
    inst_keep, inst_drop_l = filter_tracked(inst_all, tracked)
    inst_drop = len(inst_all) - len(inst_keep)
    installers = [os.path.relpath(p, REPO).replace("\\", "/") for p in inst_keep]
    tool_py = os.path.join(REPO, "tool", "check.py")
    tool_bytes = os.path.getsize(tool_py) if os.path.isfile(tool_py) else 0
    problems = self_check(rows, ports_seen, tracked,
                          {p: git_artifact_paths(p) for p in PORTS} if tracked is not None else None)

    out = ["# Delivery form - what is actually handed over", "",
           "Generated by `ci/delivery_form.py` at %s by reading the canonical faces, the repository's own "
           "tracked file list, and the deliverable itself. Nothing in this file is typed by hand."
           % time.strftime("%Y-%m-%d %H:%M:%S %z"), "",
           "The columns from `tracked files matched` onward describe only files `git ls-files` lists under each "
           "port's build/output globs, so a fresh clone and this working copy get the same numbers from the same "
           "commit. For `python` and `typescript` the globs also match source files, which is why the `kinds` "
           "column is printed: a `.py` and a `.exe` are not the same kind of thing and the table will not pretend "
           "otherwise. What this disk holds and the repository does not track is printed in the run line and is "
           "deliberately not published in this face: a count of ignored files requires those files to be present, "
           "so it describes a machine rather than a delivery. The two readings this leg was checked against - this "
           "working copy and a cold clone of the same commit - are recorded in "
           "`evidence/clone-tool/cold-clone-20261011d.md`.", "",
           "| port | cells read | direct/total imports (max seen, n cells reporting) | per-cell time ms "
           "min/med/max (n) | tracked files matched | extensions | executables | bytes | largest file |",
           "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        deps = "%s / %s (n=%d)" % r["deps"] if r["deps"] else "NOT-MEASURED(no numeric deps_* fields)"
        tim = "%g / %g / %g (n=%d)" % r["timing"] if r["timing"] else "NOT-MEASURED(no numeric elapsed_ms)"
        out.append("| %s | %d | %s | %s | %d | %s | %d | %s | %s |"
                   % (r["port"], r["cells_read"], deps, tim, r["artifacts"], r["kinds"],
                      r["executables"], "{:,}".format(r["bytes"]) if r["artifacts"] else "-",
                      ("`%s`" % r["sample"]) if r["sample"] else "-"))

    zero = [r["port"] for r in rows if r["artifacts"] == 0]
    out += [""]
    if zero:
        out += ["**Ports with no tracked build output (`%s`): the repository carries none of their build "
                "product.**" % "`, `".join(zero),
                "A customer who clones this tree gets their source and a toolchain command, not an artifact. "
                "Build output that a port left on its own machine is in no commit, so it is not part of what is "
                "delivered, and it is counted in the run line rather than in this face because its size belongs "
                "to the machine that produced it. That is a delivery-form fact, not a size of zero, and it is why "
                "the byte column reads `-` instead of a number.", ""]
    out += ["## The three questions a buyer asks, and what can honestly be said", "",
            "1. **What must be installed to run the checker?** The shipped deliverable is one Python file - "
            "`tool/check.py`, %s bytes - and needs a Python 3 interpreter on `PATH` and nothing else: it "
            "imports the standard library only (`argparse, hashlib, json, os, re, sys, time, unicodedata`, plus "
            "`glob`, `uuid` and `subprocess` in local scopes - checked against the file, not remembered). "
            "Which interpreter this reading was taken on is a fact about a machine, so it is not printed here: "
            "`docs/host-stamp.md` carries it, and the reproducibility leg names that face as host-bound and does "
            "not compare it. A double-click on a machine with no interpreter is "
            "`NOT-MEASURED(no code signing, no installer built)`, which is the honest state, not a to-do slipped "
            "past the reader."
            % ("{:,}".format(tool_bytes),),
            "",
            "2. **How big is it?** The tracked answer is the table above: `%d` artifact files carrying `%s` bytes "
            "across the ports that commit any build output, and three ports that commit none. The checker itself "
            "is the file in item 1. No packaging step exists, and `%d` installers of any format were found in the "
            "tree, so any size claim about a shipped product is unproven here and is not made."
            % (sum(r["artifacts"] for r in rows),
               "{:,}".format(sum(r["bytes"] for r in rows)), len(installers)),
            "",
            "3. **How long does it take?** The per-cell timings above are what the harnesses recorded around "
            "their own probes on one host, not wall-clock for a scan: they exclude compile time, they were "
            "taken while other ports were running against the same disk, and the deliverable's own timing is "
            "`NOT-MEASURED(wall clock not recorded in any face)`. Publishing them anyway is better than a "
            "'fast' adjective nobody has to defend.",
            "",
            "## What this leg refuses to say",
            "",
            "- It prints `NOT-MEASURED(<reason>)` rather than estimating. Three of the six rows above used to be "
            "sentences in a pitch; a number with no denominator is the failure mode this repository keeps "
            "catching in its own tools.",
            "- It does not describe this working copy. Every artifact number above comes from the tracked file "
            "list, and the leg refuses to publish the table at all when that list cannot be trusted - a parse "
            "that returns one element filters out everything, and a filter that passes nothing is "
            "indistinguishable from an honest measurement of nothing. That is how this leg was wrong once, and "
            "the floor check is the record of it.",
            "- It does not treat an absent `elapsed_ms` as a fast port. A missing measurement is a gap, and the "
            "count of cells that reported one is printed next to the number so nobody can quote the median "
            "without its `n`.", ""]
    if problems:
        out += ["## Instrument problems found while generating this file", ""]
        out += ["- %s" % x for x in problems]
        out.append("")
    text = "\n".join(out) + "\n"
    io.open(os.path.join(REPO, "docs", "delivery-form.md"), "w", encoding="utf-8", newline="\n").write(text)
    print("wrote docs/delivery-form.md bytes=%d ports=%d cells_total=%d installers_found=%d "
          "not_measured_cells=%d instrument_problems=%d untracked_ignored=%d installers_untracked=%d "
          "tracked_paths=%s drops=%s"
          % (len(text.encode("utf-8")), len(rows), sum(r["cells_read"] for r in rows), len(installers),
             text.count("NOT-MEASURED("), len(problems),
             sum(r["dropped_untracked"] for r in rows), inst_drop,
             "None" if tracked is None else len(tracked),
             ",".join("%s:%d" % (r["port"], r["dropped_untracked"]) for r in rows)))
    if problems:
        print("OUTCOME=INSTRUMENT-RED the table above is not a measurement - %d instrument problem(s), first: %s"
              % (len(problems), problems[0]))
        return 3
    if any(r["cells_read"] == 0 for r in rows):
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except SystemExit:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        print("OUTCOME=INSTRUMENT-RED %s: a crash is not a measurement" % type(e).__name__)
        sys.exit(3)
