"""Run every leg of the verification pipeline, in one command, and print what each one said.

    python ci/refresh_all.py            # regenerates docs/* from the committed data
    python ci/refresh_all.py --check    # also fails if a generated doc differs from what is on disk

Exit codes:
  0  every leg ran and every generated file matches its generator
  1  a leg refused (RED / INCOMPLETE / NOT-COMPARABLE) - reported, not hidden
  3  a leg crashed or a generator could not run: this is a tool failure, never a measurement
"""
import argparse
import io
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

# evidence_table runs the other legs internally to quote their verdict, so it goes last: a doc that
# records a verdict must be regenerated after every other doc has been brought up to date.
# (script, doc, acceptable non-zero readings). ci/validate_cells.py exits 1 when a cell does not
# conform, and that is the result it exists to publish - treating it as a tool failure would hide it.
GEN = [("ci/gap_report.py", "docs/GAP.md", (0,)),
       ("ci/matrix_table.py", "docs/matrix.md", (0,)),
       ("ci/expected_summary.py", "docs/expected-summary.md", (0,)),
       ("ci/validate_cells.py", "docs/cell-validation.md", (0, 1)),
       ("ci/tapi_report.py", "docs/tapi.md", (0,)),
       ("ci/acceptance.py", "docs/acceptance-S02.md", (0,)),
       ("ci/status_brief.py", "docs/STATUS.md", (0,)),
       ("ci/coverage_report.py", "docs/coverage.md", (0,)),
       ("ci/evidence_table.py", "docs/evidence.md", (0,))]
JUDGE = [("ci/selftest.py", ["--scratch-root", os.path.join(REPO, "..", "sg-selftest-refresh")]),
         ("ci/lint.py", ["--repo-root", REPO, "--selftest"]),
         ("ci/validate_cells.py", ["--selftest"]),
         ("ci/equality.py", []),
         ("ci/triangle.py", [])]


def run(script, args):
    p = subprocess.run([sys.executable, os.path.join(REPO, script)] + args,
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       cwd=REPO, shell=False)
    out = (p.stdout or "") + (p.stderr or "")
    verdict = ""
    for line in out.splitlines():
        if line.startswith("OUTCOME=") or line.startswith("arms="):
            verdict = line.strip()
    return p.returncode, verdict, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    refusals = tool_failures = 0
    before = {}
    if a.check:
        for _s, doc, _ok in GEN:
            p = os.path.join(REPO, doc)
            before[doc] = io.open(p, "rb").read() if os.path.isfile(p) else None

    print("== judging legs (a refusal is a result, a crash is a tool failure)")
    for script, args in JUDGE:
        rc, verdict, out = run(script, args)
        ok = rc in (0, 1, 3)
        print("   %-22s rc=%-2s %s %s" % (script, rc, verdict, "" if ok else "<-- TOOL FAILURE"))
        if not ok:
            tool_failures += 1
            print("        " + "\n        ".join(out.strip().splitlines()[-6:]))
        elif rc != 0:
            refusals += 1

    print("== generating docs")
    for script, doc, okay in GEN:
        rc, verdict, out = run(script, [])
        if rc not in okay:
            print("   %-28s rc=%-2s %s  <- TOOL FAILURE, doc not regenerated" % (script, rc, verdict))
            print("        " + "\n        ".join(out.strip().splitlines()[-4:]))
            tool_failures += 1
            continue
        line = [l for l in out.splitlines() if l.startswith("wrote")]
        print("   %-28s rc=%-2s  %s" % (script, rc, line[0] if line else out.strip().splitlines()[-1]))
        if a.check and before.get(doc) is not None:
            now = io.open(os.path.join(REPO, doc), "rb").read()
            if now != before[doc]:
                print("        note: %s changed (%+d bytes) - the committed copy was stale"
                      % (doc, len(now) - len(before[doc])))

    print("OUTCOME=%s refusals=%d tool_failures=%d"
          % ("CLEAN" if tool_failures == 0 else "TOOL-FAILURE", refusals, tool_failures))
    if tool_failures:
        return 3
    return 1 if refusals else 0


if __name__ == "__main__":
    sys.exit(main())
