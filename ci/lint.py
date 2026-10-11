#!/usr/bin/env python3
"""SENDGUARD CI lint - 3 pieces, each with red AND green arms.

Piece 1: runs-on label whitelist (standard images only; *-latest and
         larger/xl runners FORBIDDEN - M20).
Piece 2: tracked-name legality (git ls-files). Checks reserved device names,
         illegal chars, trailing dot/space, control chars, 8.3 short-name
         patterns. Names are checked at STRING level only; forbidden-name
         samples are never materialized in the repo (corpus discipline).
Piece 3: evidence BOM check. JSON evidence must be written by a program as
         UTF-8 WITHOUT BOM; UTF-8 BOM and UTF-16LE BOM are both failures.

Usage:
    python ci/lint.py --selftest                 # red/green arm self-test
    python ci/lint.py --repo-root <dir>          # lint the repo
    python ci/lint.py --repo-root <dir> --selftest
Exit 0 = pass, 1 = fail. All English (M21).
"""
import argparse
import pathlib
import re
import subprocess
import sys
import tempfile

ALLOWED_RUNS_ON = {"windows-2025", "windows-2022", "macos-15", "ubuntu-24.04"}
FORBIDDEN_PATTERNS = [r"\-latest", r"\-xl\b", r"larger", r"ubuntu-24.04-arm", r"macos-15-arm"]

RESERVED_NAMES = re.compile(
    r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9]|CONIN\$|CONOUT\$)(\..*)?$",
    re.IGNORECASE,
)
ILLEGAL_CHARS = re.compile(r"[<>:\"|?*]")
TRAILING_DOT_OR_SPACE = re.compile(r"[. ]$")
CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
SHORT_NAME_83 = re.compile(r"^[^.]{1,8}\.([^.]{1,3})?$")  # naive 8.3 shape


def check_runs_on_text(text: str) -> list:
    errs = []
    for m in re.finditer(r"runs-on\s*:\s*(.+)$", text, re.MULTILINE):
        val = m.group(1).strip().strip("'\"")
        if val.startswith("${{") and val.endswith("}}"):
            continue  # matrix template expression; validated via matrix.os whitelist
        if val not in ALLOWED_RUNS_ON:
            errs.append(f"runs-on {val!r} not in whitelist {sorted(ALLOWED_RUNS_ON)}")
        if any(re.search(p, val) for p in FORBIDDEN_PATTERNS):
            errs.append(f"runs-on {val!r} matches forbidden pattern")
    return errs


def name_errors(name: str) -> list:
    errs = []
    base = name.split("/")[-1]
    if RESERVED_NAMES.match(base):
        errs.append(f"reserved device name: {base!r}")
    if ILLEGAL_CHARS.search(base):
        errs.append(f"illegal char in name: {base!r}")
    if TRAILING_DOT_OR_SPACE.search(base):
        errs.append(f"trailing dot/space in name: {base!r}")
    if CONTROL_CHARS.search(name):
        errs.append("control char in name (hex-only discipline)")
    if SHORT_NAME_83.match(base) and "~" in base:
        errs.append(f"8.3 short-name-like basename: {base!r}")
    return errs


def check_names(repo_root: pathlib.Path):
    """Names on the **tracked face and the working tree**, because the push this leg protects happens
    after a commit: a forbidden name that is only untracked right now becomes published one command
    later. Printed with a denominator - a scan that reports no count of what it looked at is VOID,
    not clean.

    Returns (errors, names_checked, sources)."""
    errs = []
    seen = set()
    sources = []
    try:
        out = subprocess.run(
            ["git", "-C", str(repo_root), "ls-files", "-z"],
            capture_output=True, text=True, shell=False,
        )
    except OSError as e:
        return [f"git ls-files could not run: {e}"], 0, sources
    if out.returncode != 0:
        return ["git ls-files rc=%d: %s" % (out.returncode, (out.stderr or "")[:120])], 0, sources
    tracked = [n for n in out.stdout.split("\0") if n]
    sources.append("tracked=%d" % len(tracked))
    seen.update(tracked)
    # untracked faces, excluding anything git ignores
    untracked = subprocess.run(
        ["git", "-C", str(repo_root), "ls-files", "--others", "--exclude-standard", "-z"],
        capture_output=True, text=True, shell=False)
    extra = []
    if untracked.returncode == 0:
        extra = [n for n in untracked.stdout.split("\0") if n and n not in seen]
        sources.append("untracked=%d" % len(extra))
        seen.update(extra)
    for name in tracked + extra:
        errs.extend(name_errors(name))
    return errs, len(tracked) + len(extra), sources


def check_bom(repo_root: pathlib.Path):
    """Every JSON in the tree, not just evidence/: the byte-shape rule is about what gets published, and
    results/ and spec/ carry the corpus and the contract. Returns (errors, files_scanned)."""
    errs = []
    scanned = 0
    for sub in ("evidence", "results", "spec", "docs", "ci", "impl", "tool", ".github"):
        base = repo_root / sub
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*.json")):
            scanned += 1
            head = p.read_bytes()[:3]
            rel = str(p.relative_to(repo_root))
            if head == b"\xef\xbb\xbf":
                errs.append("UTF-8 BOM found: %s" % rel)
            elif head[:2] in (b"\xff\xfe", b"\xfe\xff"):
                errs.append("UTF-16 BOM found: %s" % rel)
    return errs, scanned


def check_workflow_file(path: pathlib.Path):
    """Lint a workflow's runner labels **after resolving the matrix**, because `runs-on: ${{ matrix.os }}`
    is invisible to a text predicate: the first version of this leg printed OK on this repository while the
    real labels sat in a matrix list it never read. A gate that cannot see the thing it guards is worse than
    no gate, because it issues a pass.

    Returns (errors, labels_checked)."""
    text = path.read_text(encoding="utf-8")
    errs = []
    matrices = {}
    in_matrix = False
    matrix_indent = None
    for line in text.splitlines():
        if re.match(r"^\s*matrix:\s*$", line):
            in_matrix = True
            matrix_indent = len(line) - len(line.lstrip())
            continue
        if in_matrix:
            if line.strip() and (len(line) - len(line.lstrip())) <= matrix_indent:
                in_matrix = False
            else:
                m = re.match(r"^\s*(\w+):\s*\[([^\]]*)\]", line)
                if m:
                    matrices[m.group(1)] = [v.strip().strip("'\"") for v in m.group(2).split(",") if v.strip()]
                continue
        m = re.match(r"^\s*(\w+):\s*\[([^\]]*)\]\s*$", line)
        if m and m.group(1) not in matrices:
            matrices.setdefault(m.group(1), [v.strip().strip("'\"") for v in m.group(2).split(",") if v.strip()])

    checked = 0
    for line in text.splitlines():
        m = re.match(r"^\s*runs-on:\s*(.+?)\s*$", line)
        if not m:
            continue
        value = m.group(1)
        var = re.match(r"^\$\{\{\s*matrix\.(\w+)\s*\}\}$", value)
        if var:
            key = var.group(1)
            if key not in matrices:
                errs.append("runs-on uses '${{{{ matrix.{0} }}}}' but no matrix.{0} list is defined in this "
                            "file - the label cannot be verified, which is not a pass".format(key))
                continue
            for label in matrices[key]:
                checked += 1
                errs.extend("matrix.%s entry %r: %s" % (key, label, e)
                            for e in check_runs_on_text("runs-on: %s" % label))
        else:
            checked += 1
            errs.extend(check_runs_on_text("runs-on: %s" % value))
    return errs, checked


INSTRUMENT_REQUIRED_SUBSTRINGS = (
    "instrument:",
    "ci/selftest.py --scratch-root",
    "ci/lint.py --selftest",
    "ci/validate_cells.py --selftest",
    "ci/spec_drift.py --selftest",
    "ci/equality.py",
    "PORT-HARNESS: NOT-REACHED(reason=harness_is_windows_only)",
    "if-no-files-found: error",
)
FROZEN_OS_LABELS = ("windows-2025", "macos-15", "ubuntu-24.04")


def check_workflow_instrument(text):
    """The workflow must state what it runs, what it cannot run here, and must publish its own denominator.

    Why this is a lint arm and not a paragraph: `.github/workflows/matrix.yml` was an S00 probe skeleton while
    README and the whitepaper said "macOS and Linux rows need CI to run", which a reader reasonably takes to
    mean "pushing produces them". Measured 13:10 today, no step in that file runs a port harness - each
    `impl/<port>/` runner writes `results/<port>.windows.x64/` by hard-coded path and probes Windows-only
    semantics. Neither the file nor the prose lied on its own; the pair did. The absence is now a checked
    property of the file, so the implication cannot come back.
    """
    errs = []
    missing = [needle for needle in INSTRUMENT_REQUIRED_SUBSTRINGS if needle not in text]
    if missing:
        errs.append("instrument job missing required lines: %s" % ", ".join(repr(m) for m in missing))
    for label in FROZEN_OS_LABELS:
        if label not in text:
            errs.append("instrument job does not run on the frozen label %r" % label)
    for floating in ("ubuntu-latest", "macos-latest", "windows-latest"):
        if floating in text:
            errs.append("floating runner label present: %r (M20 forbids them)" % floating)
    return errs


def selftest():
    """Red/green arms: a gate that only rejects is a dead gate. Returns (errors, arms_run, arms_passed)."""
    errs = []
    arms = 0
    good = 0

    def arm(label, condition):
        nonlocal arms, good
        arms += 1
        if condition:
            good += 1
        else:
            errs.append("selftest: %s" % label)

    # Piece 1 red/green
    arm("P1 green (ubuntu-24.04 must pass)", not check_runs_on_text("runs-on: ubuntu-24.04"))
    arm("P1 red (ubuntu-latest must fail)", bool(check_runs_on_text("runs-on: ubuntu-latest")))
    arm("P1 red (a macOS xl larger runner must fail)",
        bool(check_runs_on_text("runs-on: [macos-15-xl]")[:1] or
            check_runs_on_text("runs-on: macos-latest")))

    # Piece 1b: matrix resolution, the case the first version silently passed
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        ok_wf = root / "ok.yml"
        ok_wf.write_text("jobs:\n  a:\n    strategy:\n      matrix:\n        os: [ubuntu-24.04, macos-15]\n"
                         "    runs-on: ${{ matrix.os }}\n", encoding="utf-8")
        bad_wf = root / "bad.yml"
        bad_wf.write_text("jobs:\n  a:\n    strategy:\n      matrix:\n        os: [ubuntu-latest]\n"
                          "    runs-on: ${{ matrix.os }}\n", encoding="utf-8")
        unres_wf = root / "unres.yml"
        unres_wf.write_text("jobs:\n  a:\n    runs-on: ${{ matrix.os }}\n", encoding="utf-8")
        e_ok, n_ok = check_workflow_file(ok_wf)
        e_bad, _n_bad = check_workflow_file(bad_wf)
        e_un, _n_un = check_workflow_file(unres_wf)
        arm("P1b green (resolved matrix labels must pass, 2 seen)", (not e_ok) and n_ok == 2)
        arm("P1b red (a floating label inside the matrix must fail)", bool(e_bad))
        arm("P1b red (an unresolvable matrix variable must fail, not pass)", bool(e_un))

    # Piece 2 red/green (string level, never materialized)
    for n in ["report-2026.txt", "readme.md", "impl/node/main.js"]:
        arm("P2 green (%s must pass)" % n, not name_errors(n))
    for n in ["CON.txt", "a<b.txt", "trail. ", "COM1.log", "data~1.txt"]:
        arm("P2 red (%s must fail)" % n, bool(name_errors(n)))

    # Piece 3 red/green (temp files)
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        ev = root / "evidence"
        ev.mkdir(parents=True)
        (ev / "good.json").write_bytes(b'{"ok":true}\n')  # no BOM
        (ev / "bad.json").write_bytes(b"\xef\xbb\xbf{\"ok\":true}\n")  # UTF-8 BOM
        (ev / "u16.json").write_bytes(b"\xff\xfe" + b"{" * 4)
        r, scanned = check_bom(root)
        arm("P3 denominator (3 json files seen)", scanned == 3)
        arm("P3 green (no-BOM file must pass)", not any("good.json" in x for x in r))
        arm("P3 red (UTF-8 BOM must fail)", any("bad.json" in x for x in r))
        arm("P3 red (UTF-16 BOM must fail)", any("u16.json" in x for x in r))

    # Piece 4: the workflow's promises are policed, not assumed. Green is a complete instrument job; each red
    # arm removes one promise and requires the lint to notice.
    good_wf = "instrument:\n" + "\n".join(s for s in INSTRUMENT_REQUIRED_SUBSTRINGS if s != "instrument:")
    good_wf += "\n" + "\n".join(FROZEN_OS_LABELS)
    arm("P4 green (a complete instrument job must pass)", not check_workflow_instrument(good_wf))
    for mutation, why in ((good_wf.replace("ci/equality.py", ""), "a leg the job claims to run"),
                          (good_wf.replace("PORT-HARNESS: NOT-REACHED(reason=harness_is_windows_only)", ""),
                           "the honest absence declaration"),
                          (good_wf.replace("if-no-files-found: error", ""), "the artifact denominator"),
                          (good_wf.replace("ubuntu-24.04", "ubuntu-latest"), "a floating label"),
                          (good_wf.replace("macos-15", ""), "an OS the job claims to cover")):
        arm("P4 red (%s removed must be caught)" % why, bool(check_workflow_instrument(mutation)))
    return errs, arms, good


def main() -> int:
    ap = argparse.ArgumentParser(description="SENDGUARD CI lint")
    ap.add_argument("--repo-root", type=pathlib.Path)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    all_errs = []
    stats = []
    if args.selftest:
        e, arms, good = selftest()
        all_errs.extend(e)
        stats.append("arms=%d passed=%d" % (arms, good))
    if args.repo_root:
        root = args.repo_root.resolve()
        wfs = sorted((root / ".github" / "workflows").glob("*.yml"))
        labels = 0
        for wf in wfs:
            e, n = check_workflow_file(wf)
            labels += n
            all_errs.extend("%s: %s" % (wf.name, x) for x in e)
            all_errs.extend("%s: %s" % (wf.name, x)
                            for x in check_workflow_instrument(wf.read_text(encoding="utf-8")))
        nerrs, names_checked, sources = check_names(root)
        all_errs.extend(nerrs)
        berrs, json_scanned = check_bom(root)
        all_errs.extend(berrs)
        stats.append("workflows=%d runner_labels_checked=%d %s names_checked=%d json_scanned=%d"
                     % (len(wfs), labels, ",".join(sources), names_checked, json_scanned))

    if not stats:
        # nothing was actually looked at: this is not a pass
        print("lint: VOID - pass --repo-root and/or --selftest; a scan that ran nothing is not a clean result")
        return 2
    if all_errs:
        for e in all_errs[:40]:
            print("LINT-FAIL: %s" % e)
        print("lint: %d violation(s)  %s" % (len(all_errs), "  ".join(stats)))
        return 1
    print("lint: OK  %s" % "  ".join(stats))
    return 0


if __name__ == "__main__":
    sys.exit(main())
