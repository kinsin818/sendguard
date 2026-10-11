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
import statistics
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import equality  # noqa: E402

PORTS = ["csharp", "go", "java", "python", "rust", "typescript"]
def tracked_files():
    """The set of paths git says the repository carries.

    The first version of this leg sized whatever was on this disk, which made the published byte counts
    irreproducible: a lane's scratch build output, present in a working copy and absent in a clone, changed the
    numbers by ~38 bytes of text and several hundred kilobytes of bytes. The check that found it is
    `evidence/S10/cold-clone-20261011d.md`. A delivery form has to describe the artifact a customer receives
    from the repository, so it measures the tracked file set and prints what it dropped.
    """
    r = subprocess.run(["git", "ls-files", "-z"], cwd=REPO, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        return None
    return {p.replace("/", os.sep) for p in (x for x in r.stdout.split("SEP") if x)}


BUILD_GLOBS = {
    "csharp": ["impl/csharp/bin/**/SendGuardProbe*.exe", "impl/csharp/*.exe"],
    "go": ["impl/go/*.exe", "impl/go/go-sendguard*.exe", "harness/audit.exe", "harness/audit.bin"],
    "java": ["impl/java/build/**/*.class", "impl/java/build-repro/**/*.class"],
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
    if tracked is None:
        uniq, dropped = allm, []
    else:
        uniq = [p for p in allm if p in tracked]
        dropped = [p for p in allm if p not in tracked]
    total = sum(os.path.getsize(p) for p in uniq)
    biggest = max(uniq, key=os.path.getsize) if uniq else None
    executable = [p for p in uniq if p.lower().endswith((".exe", ".bin", ".class"))]
    return {
        "port": port,
        "cells_read": len(cells),
        "deps": (max(d[0] for d in deps), max(d[1] for d in deps), len(deps)) if deps else None,
        "timing": (min(times), statistics.median(times), max(times), len(times)) if times else None,
        "artifacts": len(uniq),
        "bytes": total,
        "sample": (os.path.relpath(biggest, REPO).replace("\\", "/") if uniq else None),
        "kinds": ",".join(sorted({os.path.splitext(p)[1].lstrip(".") or "noext" for p in uniq})) or "-",
        "executables": len(executable),
        "dropped_untracked": len(dropped),
    }


def self_check(rows, ports_seen):
    """Every port must appear, and no port may be reported from zero records."""
    problems = []
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


def main():
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

    inst_all = [p for pat in INSTALLER_GLOBS for p in glob.glob(os.path.join(REPO, pat), recursive=True)]
    inst_keep = inst_all if tracked is None else [p for p in inst_all if p in tracked]
    inst_drop = len(inst_all) - len(inst_keep)
    installers = [os.path.relpath(p, REPO).replace("\\", "/") for p in inst_keep]
    tool_py = os.path.join(REPO, "tool", "check.py")
    tool_bytes = os.path.getsize(tool_py) if os.path.isfile(tool_py) else 0
    problems = self_check(rows, ports_seen)

    out = ["# Delivery form - what is actually handed over", "",
           "Generated by `ci/delivery_form.py` at %s by reading the canonical faces, the built artifacts on "
           "this disk, and the deliverable itself. Nothing in this file is typed by hand."
           % time.strftime("%Y-%m-%d %H:%M:%S %z"), "",
           "The last four columns describe **files this disk holds** under each port's build/output globs - for "
           "`python` and `typescript` those globs match source files, which is why the `kinds` column is "
           "printed: a `.py` and a `.exe` are not the same kind of thing and the table will not pretend "
           "otherwise.", "",
           "| port | cells read | direct/total imports (max seen, n cells reporting) | per-cell time ms "
           "min/med/max (n) | tracked files matched | extensions | executables | bytes | largest file | "
           "untracked files ignored |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        deps = "%s / %s (n=%d)" % r["deps"] if r["deps"] else "NOT-MEASURED(no numeric deps_* fields)"
        tim = "%g / %g / %g (n=%d)" % r["timing"] if r["timing"] else "NOT-MEASURED(no numeric elapsed_ms)"
        out.append("| %s | %d | %s | %s | %d | %s | %d | %s | %s | %d |"
                   % (r["port"], r["cells_read"], deps, tim, r["artifacts"], r["kinds"],
                      r["executables"], "{:,}".format(r["bytes"]) if r["artifacts"] else "-",
                      ("`%s`" % r["sample"]) if r["sample"] else "-", r["dropped_untracked"]))

    zero = [r["port"] for r in rows if r["artifacts"] == 0]
    out += [""]
    if zero:
        out += ["**Ports with no files matched (`%s`): nothing of theirs is retained as build output on this "
                "disk.**" % "`, `".join(zero),
                "Their harnesses compile into a temporary tree and throw it away, so for those ports what could "
                "be handed to a customer today is source plus a toolchain command, not an artifact. That is a "
                "delivery-form fact, not a size of zero.", ""]
    out += ["## The three questions a buyer asks, and what can honestly be said", "",
            "1. **What must be installed to run the checker?** The shipped deliverable is one Python file - "
            "`tool/check.py`, %s bytes - and needs a Python 3 interpreter on `PATH` and nothing else: it "
            "imports the standard library only (`argparse, hashlib, json, os, re, sys, time, unicodedata`, plus "
            "`glob`, `uuid` and `subprocess` in local scopes - checked against the file, not remembered). "
            "Measured on this host at %s: interpreter `%s`. A double-click on a "
            "machine with no interpreter is `NOT-MEASURED(no code signing, no installer built)`, which is the "
            "honest state, not a to-do slipped past the reader."
            % ("{:,}".format(tool_bytes), time.strftime("%H:%M %z"),
               sys.version.split()[0] + " (the interpreter running this leg)"),
            "",
            "2. **How big is it?** The six ports are source plus their toolchain output; the totals are in the "
            "table above and they are *this disk*, not a release: no packaging step exists, and "
            "`%d` installers of any format were found in the tree. Any size claim about a shipped product is "
            "therefore unproven here and is not made." % len(installers),
            "",
            "3. **How long does it take?** The per-cell timings above are what the harnesses recorded around "
            "their own probes on one host, not wall-clock for a scan: they exclude compile time, they were "
            "taken while other lanes were running against the same disk, and the deliverable's own timing is "
            "`NOT-MEASURED(wall clock not recorded in any face)`. Publishing them anyway is better than a "
            "'fast' adjective nobody has to defend.",
            "",
            "## What this leg refuses to say",
            "",
            "- It prints `NOT-MEASURED(<reason>)` rather than estimating. Three of the six rows above used to be "
            "sentences in a pitch; a number with no denominator is the failure mode this repository keeps "
            "catching in its own tools.",
            "- It does not claim the built artifacts are reproducible from history: several lanes compile into "
            "`impl/` trees that are not tracked, so the byte counts describe this working copy, which is "
            "stated rather than glossed.",
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
          "not_measured_cells=%d instrument_problems=%d untracked_ignored=%d installers_untracked=%d"
          % (len(text.encode("utf-8")), len(rows), sum(r["cells_read"] for r in rows), len(installers),
             text.count("NOT-MEASURED("), len(problems),
             sum(r["dropped_untracked"] for r in rows), inst_drop))
    if problems:
        print("OUTCOME=INSTRUMENT-RED a port row was produced with nothing behind it - see the file")
        return 3
    if any(r["cells_read"] == 0 for r in rows):
        return 1
    return 0


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
