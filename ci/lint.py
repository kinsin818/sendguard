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


def check_tracked_names(repo_root: pathlib.Path) -> list:
    errs = []
    try:
        out = subprocess.run(
            ["git", "-C", str(repo_root), "ls-files", "-z"],
            capture_output=True, text=True, check=True,
        ).stdout
    except subprocess.CalledProcessError as e:
        return [f"git ls-files failed: {e}"]
    for name in out.split("\0"):
        if not name:
            continue
        errs.extend(name_errors(name))
    return errs


def check_bom(repo_root: pathlib.Path) -> list:
    errs = []
    for p in sorted((repo_root / "evidence").rglob("*.json")):
        head = p.read_bytes()[:3]
        if head[:3] == b"\xef\xbb\xbf":
            errs.append(f"UTF-8 BOM found: {p.relative_to(repo_root)}")
        elif head[:2] == b"\xff\xfe" or head[:2] == b"\xfe\xff":
            errs.append(f"UTF-16 BOM found: {p.relative_to(repo_root)}")
    return errs


def selftest() -> list:
    """Red/green arms: a gate that only rejects is a dead gate."""
    errs = []

    # Piece 1 red/green
    good_yml = "runs-on: ubuntu-24.04"
    bad_yml = "runs-on: ubuntu-latest"
    if check_runs_on_text(good_yml):
        errs.append("selftest P1: green arm failed (ubuntu-24.04 flagged)")
    if not check_runs_on_text(bad_yml):
        errs.append("selftest P1: red arm failed (ubuntu-latest not flagged)")

    # Piece 2 red/green (string level, never materialized)
    good_names = ["report-2026.txt", "readme.md", "impl/node/main.js"]
    bad_names = ["CON.txt", "a<b.txt", "trail. ", "COM1.log", "data~1.txt"]
    for n in good_names:
        if name_errors(n):
            errs.append(f"selftest P2: green arm failed ({n} flagged)")
    for n in bad_names:
        if not name_errors(n):
            errs.append(f"selftest P2: red arm failed ({n} not flagged)")

    # Piece 3 red/green (temp files)
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        ev = root / "evidence"
        ev.mkdir(parents=True)
        good = ev / "good.json"
        good.write_bytes(b'{"ok":true}\n')  # no BOM
        bad = ev / "bad.json"
        bad.write_bytes(b"\xef\xbb\xbf{\"ok\":true}\n")  # UTF-8 BOM
        r = check_bom(root)
        if any("good.json" in str(x) for x in r):
            errs.append("selftest P3: green arm failed (no-BOM flagged)")
        if not any("bad.json" in str(x) for x in r):
            errs.append("selftest P3: red arm failed (BOM not flagged)")

    return errs


def main() -> int:
    ap = argparse.ArgumentParser(description="SENDGUARD CI lint")
    ap.add_argument("--repo-root", type=pathlib.Path)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    all_errs = []
    if args.selftest:
        all_errs.extend(selftest())
    if args.repo_root:
        root = args.repo_root.resolve()
        for wf in sorted((root / ".github" / "workflows").glob("*.yml")):
            all_errs.extend(f"{wf.name}: {e}" for e in check_runs_on_text(wf.read_text(encoding="utf-8")))
        all_errs.extend(check_tracked_names(root))
        all_errs.extend(check_bom(root))

    if all_errs:
        for e in all_errs:
            print(f"LINT-FAIL: {e}")
        print(f"lint: {len(all_errs)} violation(s)")
        return 1
    print("lint: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
