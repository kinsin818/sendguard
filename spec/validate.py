#!/usr/bin/env python3
"""SENDGUARD schema validator (self-contained, stdlib only).

Usage:
    python validate.py <file.json>        # validate one cell
    python validate.py <dir>              # validate every *.json under dir
    python validate.py --schema           # print frozen schema path

Exit 0 = all cells valid. Exit 1 = at least one VOID (details printed).
Status words are the closed set from spec/canonical.md; unknown words -> VOID.
"""
import json
import pathlib
import re
import sys

SCHEMA = pathlib.Path(__file__).resolve().parent / "schema.json"

CLOSED_SETS = {
    "case_group": {"trap", "ctrl", "tapi", "blind", "len"},
    "language": {"node", "python", "go", "java", "csharp", "rust"},
    "os": {"windows", "macos", "ubuntu"},
    "name_encoding": {"utf16_code_units", "code_points", "utf8_bytes"},
    "path_form": {"plain", "extended"},
    "longpath_mechanism": {"manifest", "prefix_rewrite", "none", "unknown"},
    "create_result": {"ok", "err_at_parse", "err_at_syscall", "hang"},
    "error_stage": {"parse", "syscall", "fs", "tool", "null"},
    "read_result": {"ok", "eof", "err6", "hang"},
    "os_legality_verdict": {"legal", "illegal", "unknown"},
    "attribution_layer": {"L1", "L2", "L3", "L3_interaction"},
}

REQUIRED = [
    "format_version", "case_id", "case_group", "language", "os", "api_entry",
    "attempt", "name_source", "path_form", "longpath_mechanism", "create_result",
    "error_stage", "read_result", "os_legality_verdict", "harness_version",
    "started_at", "elapsed_ms",
]

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def check_cell(obj: dict) -> list:
    """Return list of violation strings (empty = valid)."""
    errs = []
    for f in REQUIRED:
        if f not in obj:
            errs.append(f"missing required field: {f}")
    if "format_version" in obj and obj["format_version"] != 1:
        errs.append(f"format_version must be 1, got {obj.get('format_version')!r}")
    for key, closed in CLOSED_SETS.items():
        if key in obj and obj[key] not in closed:
            errs.append(f"unknown status word {key}={obj[key]!r} (not in closed set)")
    for sha_key in ("sha256_self", "sha256_truth"):
        if sha_key in obj and obj[sha_key] is not None:
            if not SHA256_RE.match(obj[sha_key]):
                errs.append(f"{sha_key} is not a 64-hex sha256")
    if "attempt" in obj and (not isinstance(obj["attempt"], int) or obj["attempt"] < 1):
        errs.append("attempt must be int >= 1")
    if "elapsed_ms" in obj and (not isinstance(obj["elapsed_ms"], int) or obj["elapsed_ms"] < 0):
        errs.append("elapsed_ms must be int >= 0")
    if "roundtrip_ok" in obj and not isinstance(obj["roundtrip_ok"], bool):
        errs.append("roundtrip_ok must be boolean")
    if "enum_to_stat_agrees" in obj and not isinstance(obj["enum_to_stat_agrees"], bool):
        errs.append("enum_to_stat_agrees must be boolean")
    return errs


def validate_file(p: pathlib.Path) -> tuple:
    """Return (ok: bool, label: str, violations: list)."""
    try:
        raw = p.read_text(encoding="utf-8")
        obj = json.loads(raw)
    except Exception as e:  # JSON parse failure -> VOID
        return False, p.name, [f"json parse failure: {e}"]
    if not isinstance(obj, dict):
        return False, p.name, ["top-level must be an object"]
    errs = check_cell(obj)
    return (len(errs) == 0), p.name, errs


def main() -> int:
    args = sys.argv[1:]
    if not args or args[0] == "--schema":
        print(SCHEMA)
        return 0
    target = pathlib.Path(args[0])
    if target.is_dir():
        files = sorted(target.rglob("*.json"))
    elif target.is_file():
        files = [target]
    else:
        print(f"not found: {target}")
        return 1
    bad = 0
    for f in files:
        ok, label, errs = validate_file(f)
        if ok:
            print(f"VALID   {label}")
        else:
            bad += 1
            print(f"VOID    {label}")
            for e in errs:
                print(f"        - {e}")
    print(f"summary: {len(files) - bad} valid / {bad} void (of {len(files)})")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
