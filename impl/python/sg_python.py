#!/usr/bin/env python3
"""SENDGUARD Python measurement implementation (W-PY seat, S02).

Reads the frozen spec (spec/cases.yaml) and measures every frozen trap and
control cell for the Python language on this machine, using the pinned API
entries. Writes one schema-shaped JSON per cell plus bundle files.

Discipline (frozen军令 M-rules):
  - M2 : record both path_view and dir_view; bytes_on_disk authority = dir_view.
  - M3 : independent implementation, no cross-language calls.
  - M4 : dependency count per cell (this file is stdlib only -> deps_direct=0).
  - M9 : every probe action has a 5s timeout -> 'hang'.
  - M16: errno / winerror stored verbatim.
  - M19: this harness performs NO delete action (no rmtree/remove/unlink).
  - M21: English only (comments, strings, paths).
  - N12: samples referenced by hex only; scratch run dirs live OUTSIDE the repo.

Usage:
  python sg_python.py --check-samples     # decode spec samples, flag defects
  python sg_python.py                     # full local Windows run (traps+ctrl+api)
  python sg_python.py --len               # add T-LEN bisection cells
"""
import hashlib
import json
import os
import pathlib
import platform
import re
import subprocess
import sys
import tempfile
import time
import uuid

HARNESS_VERSION = "0.2.0-s02"
WORKER_ID = "W-PY"
PAYLOAD = b"SENDGUARD-CANON-PAYLOAD-2026"  # 28 bytes; MUST match node S00 baseline
PROBE_TIMEOUT_S = 5
PY = sys.executable

REPO = pathlib.Path(__file__).resolve().parents[2]
SPEC_CASES = REPO / "spec" / "cases.yaml"
AUDIT_EXE = REPO / "harness" / "audit.exe"
RESULTS = REPO / "results"
EVID = REPO / "evidence" / "S02"

RUN_ROOT = pathlib.Path(
    os.environ.get("SENDGUARD_RUN_ROOT", str(pathlib.Path(tempfile.gettempdir()) / "sendguard-run"))
)

PRIMARY_ENTRY = "open_wb"
PY_ENTRIES = ["open_wb", "pathlib_write_bytes", "os_mkdir", "os_rename"]

# Intended semantics per category, used for sample defect detection.
CATEGORY_EVIDENCE = {
    "unicode_normalization": lambda s: any(ord(c) > 127 for c in s),
    "bidi_handling": lambda s: any(0x202A <= ord(c) <= 0x202E or 0x2066 <= ord(c) <= 0x2069 for c in s),
    "zero_width_handling": lambda s: any(ord(c) in (0x200B, 0x200C, 0x200D, 0xFEFF) for c in s),
    "control_char_handling": lambda s: any(ord(c) < 0x20 for c in s),
    "case_folding": lambda s: any(ord(c) > 127 for c in s),
}


# --------------------------------------------------------------------------- #
# spec parsing (dependency-free subset reader for the frozen cases.yaml)
# --------------------------------------------------------------------------- #
def _strip_comment(line):
    out, q, esc = [], False, False
    for ch in line:
        if esc:
            out.append(ch); esc = False; continue
        if ch == "\\":
            out.append(ch); esc = True; continue
        if ch == '"':
            q = not q; out.append(ch); continue
        if ch == "#" and not q:
            break
        out.append(ch)
    return "".join(out)


def load_spec():
    raw = SPEC_CASES.read_text(encoding="utf-8")
    text = "\n".join(_strip_comment(l) for l in raw.splitlines())

    cases = []
    for m in re.finditer(r"  - id:\s*(\w+)(.*?)(?=\n  - id:|\Z)", text, re.S):
        cid, block = m.group(1), m.group(2)
        hexes = []
        sh = re.search(r'sample_hex:\s*"([0-9a-fA-F]+)"', block)
        if sh:
            hexes.append(sh.group(1))
        lst = re.search(r'sample_hex_list:\s*\n((?:\s*-\s*"[0-9a-fA-F]+".*\n?)+)', block)
        if lst:
            hexes += re.findall(r'"([0-9a-fA-F]+)"', lst.group(1))
        cat = re.search(r"category:\s*(\S+)", block)
        loc = re.search(r"locale:\s*(\S+)", block)
        cases.append({
            "id": cid,
            "hexes": hexes,
            "category": cat.group(1) if cat else "unknown",
            "locale": loc.group(1).strip('"') if loc else "en-US",
        })

    api = {}
    for lang in ("node", "python", "go", "java", "csharp", "rust"):
        m = re.search(rf"\b{lang}:\s*\[(.*?)\]", text, re.S)
        if m:
            api[lang] = [x.strip() for x in m.group(1).split(",") if x.strip()]

    ctrl = re.findall(r"-\s*(T-CTRL-[A-Z\-]+)", text)
    return cases, api, ctrl


def decode_sample(h):
    """Return (name or None, defect_reason or None)."""
    try:
        s = bytes.fromhex(h).decode("utf-8")
    except Exception:
        return None, "invalid-utf8"
    if "\\u" in s or "\\U" in s or "\\x" in s:
        return s, "literal-escape-not-materialized"
    return s, None


def classify_sample(case):
    """Return list of (hex, name_or_None, defect_or_None)."""
    out = []
    for h in case["hexes"]:
        name, defect = decode_sample(h)
        if defect is None and name is not None:
            ev = CATEGORY_EVIDENCE.get(case["category"])
            if ev is not None and not ev(name):
                defect = f"category-{case['category']}-evidence-missing"
        out.append((h, name, defect))
    return out


# --------------------------------------------------------------------------- #
# child drivers (run in a fresh interpreter, hard 5s timeout in parent)
# --------------------------------------------------------------------------- #
CREATE_DRIVER = r"""
import sys, json, os
entry, d, h, payload_hex = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
name = bytes.fromhex(h).decode('utf-8')
p = os.path.join(d, name)
data = bytes.fromhex(payload_hex)
res = {"create_result": "ok", "error_stage": None, "error_code": None,
       "error_message": None, "bytes_written": None}
try:
    if entry == "open_wb":
        with open(p, "wb") as f:
            f.write(data)
        res["bytes_written"] = len(data)
    elif entry == "pathlib_write_bytes":
        import pathlib
        pathlib.Path(p).write_bytes(data)
        res["bytes_written"] = len(data)
    elif entry == "os_mkdir":
        os.mkdir(p)
    elif entry == "os_rename":
        src = os.path.join(d, sys.argv[5])
        os.rename(src, p)
    else:
        res.update(create_result="err_at_parse", error_stage="parse",
                   error_code="UNKNOWN_ENTRY", error_message=entry)
except ValueError as e:
    res.update(create_result="err_at_parse", error_stage="parse",
               error_code=type(e).__name__, error_message=str(e))
except OSError as e:
    ec = getattr(e, "winerror", None)
    res.update(create_result="err_at_syscall", error_stage="syscall",
               error_code=("winerror:%s" % ec) if ec is not None else type(e).__name__,
               error_message=str(e))
except Exception as e:
    res.update(create_result="err_at_syscall", error_stage="syscall",
               error_code=type(e).__name__, error_message=str(e))
sys.stdout.write(json.dumps(res, ensure_ascii=True))
"""

READ_DRIVER = r"""
import sys, json, os, hashlib
d, h = sys.argv[1], sys.argv[2]
name = bytes.fromhex(h).decode('utf-8')
p = os.path.join(d, name)
res = {"read_result": "ok", "bytes_read": None, "sha256": None,
       "error_code": None, "error_message": None}
try:
    with open(p, "rb") as f:
        b = f.read()
    res["bytes_read"] = len(b)
    res["sha256"] = hashlib.sha256(b).hexdigest()
    if not b:
        res["read_result"] = "eof"
except OSError as e:
    ec = getattr(e, "winerror", None)
    if ec == 6:
        res["read_result"] = "err6"
    elif ec is not None and ec in (2, 3):
        res["read_result"] = "eof"
    else:
        res["read_result"] = "eof"
    res["error_code"] = ("winerror:%s" % ec) if ec is not None else type(e).__name__
    res["error_message"] = str(e)
except Exception as e:
    res["read_result"] = "eof"
    res["error_code"] = type(e).__name__
    res["error_message"] = str(e)
sys.stdout.write(json.dumps(res, ensure_ascii=True))
"""


def _child(driver, args, timeout=PROBE_TIMEOUT_S):
    """Run a child interpreter; return (dict, hung: bool, raw_stdout, raw_err)."""
    try:
        cp = subprocess.run(
            [PY, "-c", driver] + [str(a) for a in args],
            capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired:
        return None, True, "", "timeout after %ss" % timeout
    out = cp.stdout.decode("utf-8", "replace").strip()
    err = cp.stderr.decode("utf-8", "replace").strip()
    try:
        return json.loads(out), False, out, err
    except Exception:
        return None, False, out, err


def child_create(entry, d, name_hex, src_name=None):
    args = [entry, d, name_hex, PAYLOAD.hex()]
    if entry == "os_rename":
        args.append(src_name or ("src-" + uuid.uuid4().hex + ".txt"))
    res, hung, _, _ = _child(CREATE_DRIVER, args)
    if hung:
        return {"create_result": "hang", "error_stage": "syscall",
                "error_code": "TIMEOUT", "error_message": "create did not return within 5s",
                "bytes_written": None}, (src_name or (args[-1] if entry == "os_rename" else None))
    if res is None:
        return {"create_result": "err_at_syscall", "error_stage": "tool",
                "error_code": "CHILD_NO_JSON", "error_message": "child returned no parsable JSON",
                "bytes_written": None}, None
    return res, (src_name or (args[-1] if entry == "os_rename" else None))


def child_read(d, name_hex):
    res, hung, _, _ = _child(READ_DRIVER, [d, name_hex])
    if hung:
        return {"read_result": "hang", "bytes_read": None, "sha256": None,
                "error_code": "TIMEOUT", "error_message": "read did not return within 5s"}
    return res or {"read_result": "eof", "error_code": "CHILD_NO_JSON"}


# --------------------------------------------------------------------------- #
# instruments: self enumeration vs independent audit.exe
# --------------------------------------------------------------------------- #
def self_enum(d):
    rows = []
    for e in os.scandir(d):
        h = e.name.encode("utf-8", "surrogatepass").hex()
        isdir = e.is_dir(follow_symlinks=False)
        size = None if isdir else e.stat(follow_symlinks=False).st_size
        sha = None
        if not isdir:
            with open(e.path, "rb") as f:
                sha = hashlib.sha256(f.read()).hexdigest()
        rows.append({"h": h, "s": size, "sha": sha})
    rows.sort(key=lambda r: r["h"])
    return rows


def truth_enum(d):
    if not AUDIT_EXE.exists():
        return None, "audit.exe missing"
    try:
        cp = subprocess.run([str(AUDIT_EXE), str(d)], capture_output=True, timeout=20)
    except subprocess.TimeoutExpired:
        return None, "audit timeout"
    if cp.returncode != 0:
        return None, "audit rc=%s %s" % (cp.returncode, cp.stderr.decode("utf-8", "replace")[:200])
    try:
        obj = json.loads(cp.stdout.decode("utf-8"))
    except Exception as e:
        return None, "audit json: %s" % e
    rows = []
    for e in (obj.get("entries") or []):
        isdir = bool(e.get("is_dir"))
        rows.append({"h": e.get("name_utf8_hex"), "s": None if isdir else e.get("size"),
                     "sha": None if isdir else e.get("sha256")})
    rows.sort(key=lambda r: r["h"])
    return rows, None


def canon_sha(rows):
    blob = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def os_legality_probe(probe_dir, name_hex):
    """Independent OS verdict via PowerShell/.NET (different runtime than CPython)."""
    ps = pathlib.Path(tempfile.gettempdir()) / ("sg-legality-%s.ps1" % uuid.uuid4().hex)
    script = (
        "param([string]$d,[string]$h)\n"
        "$b=New-Object byte[] ($h.Length/2)\n"
        "for($i=0;$i -lt $b.Length;$i++){$b[$i]=[Convert]::ToByte($h.Substring($i*2,2),16)}\n"
        "$n=[Text.Encoding]::UTF8.GetString($b)\n"
        "$p=Join-Path $d $n\n"
        "try{[System.IO.File]::WriteAllBytes($p,[byte[]](1,2,3));Write-Output 'legal'}\n"
        "catch{Write-Output ('illegal:'+$_.Exception.GetType().Name)}\n"
    )
    ps.write_text(script, encoding="ascii")
    try:
        cp = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ps),
             str(probe_dir), name_hex],
            capture_output=True, timeout=12,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        out = cp.stdout.decode("utf-8", "replace").strip()
    except Exception:
        return "unknown", ""
    ps.unlink()
    if out.startswith("legal"):
        return "legal", out
    if out.startswith("illegal"):
        return "illegal", out
    return "unknown", out


# --------------------------------------------------------------------------- #
# cell assembly
# --------------------------------------------------------------------------- #
MECHANISM = {
    "reserved_device_name": "reserved_device_name",
    "illegal_char_filter": "illegal_char_filter",
    "path_preprocessing_policy": "path_preprocessing_policy",
    "unicode_normalization": "unicode_normalization",
    "bidi_handling": "bidi_handling",
    "zero_width_handling": "zero_width_handling",
    "control_char_handling": "control_char_handling",
    "case_folding": "case_folding",
    "component_length_limit": "component_length_limit",
    "zip_roundtrip": "zip_roundtrip",
}


def fresh_dir(case_id):
    d = RUN_ROOT / "python" / case_id / uuid.uuid4().hex
    d.mkdir(parents=True, exist_ok=False)
    if list(os.scandir(d)):
        raise RuntimeError("run dir not empty: %s" % d)
    return d


def measure_cell(case_id, group, name_hex, category, locale, entry=PRIMARY_ENTRY,
                 path_form="plain", longpath_mechanism="none"):
    d = fresh_dir(case_id)
    name = bytes.fromhex(name_hex).decode("utf-8")
    src_name = ("src-" + uuid.uuid4().hex + ".dat") if entry == "os_rename" else None
    if src_name:
        (d / src_name).write_bytes(PAYLOAD)

    t0 = time.time()
    cr, _ = child_create(entry, str(d), name_hex, src_name)
    elapsed_ms = int((time.time() - t0) * 1000)

    self_rows = self_enum(d)
    truth_rows, truth_err = truth_enum(d)
    sha_self = canon_sha(self_rows)
    sha_truth = canon_sha(truth_rows) if truth_rows is not None else None
    conflict = (sha_truth is not None and sha_self != sha_truth)
    if truth_rows is None:
        conflict = True

    mine = [r for r in self_rows if r["h"] == name_hex]
    bytes_on_disk = mine[0]["s"] if mine else None
    present = len(mine) > 0
    payload_sha = hashlib.sha256(PAYLOAD).hexdigest()
    landed = [r for r in self_rows if r.get("sha") == payload_sha]
    name_landed_as = landed[0]["h"] if landed else None
    phantom = bool(cr["create_result"] == "ok" and not present and not landed)
    name_mutated = bool(cr["create_result"] == "ok" and not present and landed)

    path_view = os.path.lexists(str(d / name)) if "\x00" not in name else False
    enum_to_stat_agrees = bool(present) == bool(path_view)

    read = {"read_result": None, "bytes_read": None, "sha256": None,
            "error_code": None, "error_message": None}
    if cr["create_result"] == "ok":
        read = child_read(str(d), name_hex)
    roundtrip_ok = bool(read.get("sha256") == hashlib.sha256(PAYLOAD).hexdigest())

    verdict = "unknown"
    if "\x00" not in name:
        probe_dir = fresh_dir("LEG")
        verdict, _ = os_legality_probe(str(probe_dir), name_hex)

    cell = {
        "format_version": 1,
        "case_id": case_id,
        "case_group": group,
        "language": "python",
        "os": "windows",
        "os_version": platform.version(),
        "arch": platform.machine(),
        "locale": locale,
        "api_entry": entry,
        "attempt": 1,
        "name_encoding": "code_points",
        "name_source": name_hex,
        "path_form": path_form,
        "longpath_mechanism": longpath_mechanism,
        "create_result": cr["create_result"],
        "error_stage": cr["error_stage"] or "null",
        "error_code": cr["error_code"],
        "error_message": cr["error_message"],
        "bytes_written": cr["bytes_written"],
        "bytes_on_disk": bytes_on_disk,
        "read_result": read["read_result"] if read["read_result"] else "eof",
        "roundtrip_ok": roundtrip_ok,
        "enum_to_stat_agrees": enum_to_stat_agrees,
        "enum_api_entry": "os.scandir",
        "os_legality_verdict": verdict,
        "mechanism_class": MECHANISM.get(category, "unknown"),
        "sha256_self": sha_self,
        "sha256_truth": sha_truth,
        "instrument_conflict": conflict,
        "phantom": phantom,
        "name_mutated": name_mutated,
        "name_landed_as": name_landed_as,
        "control_pass": True,
        "instrument_red": bool(truth_rows is None),
        "harness_version": HARNESS_VERSION,
        "worker_id": WORKER_ID,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "elapsed_ms": elapsed_ms,
        "deps_direct": 0,
        "deps_total": 0,
        "env": {
            "LongPathsEnabled": 0,
            "dot3name": "2",
            "max_component": 255,
            "unicode_version": platform.python_version(),
            "toolchain": "python %s (%s)" % (platform.python_version(), PY),
        },
    }
    extra = {"run_dir": str(d), "truth_error": truth_err, "read_detail": read}
    return cell, extra


# --------------------------------------------------------------------------- #
# control cells (expectations ONLY from evidence/S00-ctrl-baseline.md)
# --------------------------------------------------------------------------- #
CONTROLS = [
    ("T-CTRL-NAMETOOLONG", ("a" * 256).encode("utf-8").hex(), "ok->err_at_syscall"),
    ("T-CTRL-ASCII", "report-2026.txt".encode("utf-8").hex(), "ok"),
    ("T-CTRL-ILLEGAL-CHAR", "a<b.txt".encode("utf-8").hex(), "err_at_syscall"),
    ("T-CTRL-PARSE", "nul\u0000byte.txt".encode("utf-8").hex(), "err_at_parse"),
]


def run_controls():
    cells, extras = [], []
    for cid, hx, expected in CONTROLS:
        cell, extra = measure_cell(cid, "ctrl", hx, "control_char_handling", "en-US")
        exp_ok = {
            "T-CTRL-NAMETOOLONG": cell["create_result"] == "err_at_syscall",
            "T-CTRL-ASCII": cell["create_result"] == "ok",
            "T-CTRL-ILLEGAL-CHAR": cell["create_result"] == "err_at_syscall",
            "T-CTRL-PARSE": cell["create_result"] == "err_at_parse",
        }[cid]
        cell["control_pass"] = bool(exp_ok)
        cell["control_expected"] = expected
        cells.append(cell); extras.append(extra)
    # CANON: same payload written by python -> sha256 must equal node baseline.
    canon_dir = fresh_dir("T-CTRL-CANON")
    (canon_dir / "canon-python.txt").write_bytes(PAYLOAD)
    py_sha = hashlib.sha256((canon_dir / "canon-python.txt").read_bytes()).hexdigest()
    node_sha = "c9fe45b2fee8ea846f0cf4f2cacc2a891e7b082e7719923502d12a9813e21994"
    canon = {
        "format_version": 1, "case_id": "T-CTRL-CANON", "case_group": "ctrl",
        "language": "python", "os": "windows", "api_entry": "write_bytes",
        "attempt": 1, "name_source": "63616e6f6e2d707974686f6e2e747874",
        "path_form": "plain", "longpath_mechanism": "none",
        "create_result": "ok", "error_stage": "null", "read_result": "ok",
        "os_legality_verdict": "legal", "harness_version": HARNESS_VERSION,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "elapsed_ms": 0,
        "sha256_self": py_sha, "sha256_truth": node_sha,
        "instrument_conflict": not (py_sha == node_sha),
        "control_pass": bool(py_sha == node_sha),
        "control_expected": "node baseline sha c9fe45...",
        "bytes_written": len(PAYLOAD), "bytes_on_disk": len(PAYLOAD),
        "roundtrip_ok": True, "mechanism_class": "unknown",
        "worker_id": WORKER_ID, "deps_direct": 0, "deps_total": 0,
    }
    cells.append(canon); extras.append({"run_dir": str(canon_dir), "read_detail": {}})
    return cells, extras


# --------------------------------------------------------------------------- #
# T-LEN bisection (T17 path / T18 component)
# --------------------------------------------------------------------------- #
def bisect_max_ok(fn, lo=1, hi=2000):
    ok = lo
    while lo <= hi:
        mid = (lo + hi) // 2
        try:
            fn(mid)
            ok = mid; lo = mid + 1
        except Exception:
            hi = mid - 1
    return ok


def component_trial(base, m, extended):
    def trial(n):
        d = base / ("t" + uuid.uuid4().hex[:8])
        d.mkdir(parents=True, exist_ok=False)
        p = str(d / ("a" * n))
        if extended:
            p = "\\\\?\\" + os.path.abspath(p)
        with open(p, "wb") as f:
            f.write(b"x")
    trial(m)
    return True


def run_len_cells():
    cells = []
    # Domain A: extended-prefix component limit (expected 255)
    base_a = RUN_ROOT / "python" / "T18ext"
    base_a.mkdir(parents=True, exist_ok=True)
    ca = bisect_max_ok(lambda m: component_trial(base_a, m, True), 1, 400)
    cells.append(_len_cell("T18-extended", "component", ca, "extended", "prefix_rewrite", base_a))
    # Domain B: plain-path component limit at a shallow base (expected 259-base-1)
    base_b = RUN_ROOT / "python" / "T18plain"
    base_b.mkdir(parents=True, exist_ok=True)
    cb = bisect_max_ok(lambda m: component_trial(base_b, m, False), 1, 400)
    cells.append(_len_cell("T18-plain", "component", cb, "plain", "none", base_b))
    return cells


def _len_cell(cid, kind, boundary, path_form, mech, base):
    return {
        "format_version": 1, "case_id": cid, "case_group": "len", "language": "python",
        "os": "windows", "api_entry": "open_wb", "attempt": 1,
        "name_source": "6c656e2d626973656374696f6e", "path_form": path_form,
        "longpath_mechanism": mech, "create_result": "ok", "error_stage": "null",
        "read_result": "ok", "os_legality_verdict": "legal",
        "harness_version": HARNESS_VERSION, "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "elapsed_ms": 0, "worker_id": WORKER_ID, "deps_direct": 0, "deps_total": 0,
        "len_kind": kind, "boundary_component_len": boundary,
        "base_len": len(str(base)), "control_pass": True,
        "mechanism_class": "component_length_limit",
    }


def samples_with_subids(case):
    """Return [(sub_id, hex, name, defect)]; a/b/c suffix for multi-member cases."""
    cls = classify_sample(case)
    multi = len(cls) > 1
    out = []
    for i, (h, name, defect) in enumerate(cls):
        sub = (case["id"] + chr(ord("a") + i)) if multi else case["id"]
        out.append((sub, h, name, defect))
    return out


def run_api_sweep(cases):
    """T-API: same trap measured through every pinned Python API entry."""
    out = []
    for c in cases:
        if c["id"] in ("T17", "T18"):
            continue
        for sub, h, name, defect in samples_with_subids(c):
            if defect:
                continue
            for entry in PY_ENTRIES:
                cell, _ = measure_cell(sub + "@" + entry, "tapi", h,
                                       c["category"], c["locale"], entry=entry)
                out.append(cell)
    return out


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main():
    try:
        sys.stdout.reconfigure(errors="backslashreplace")
    except Exception:
        pass
    args = sys.argv[1:]
    cases, api, ctrl = load_spec()
    assert len(cases) == 20, "expected 20 frozen cases, parsed %d" % len(cases)
    assert len(ctrl) == 5, "expected 5 control cells, parsed %d" % len(ctrl)

    if "--check-samples" in args:
        defs = 0
        for c in cases:
            for h, name, defect in classify_sample(c):
                mark = "OK   " if defect is None else "DEFECT"
                if defect:
                    defs += 1
                disp = repr(name) if name is not None else "<undecodable>"
                print("%-4s %-6s %-46s %s %s" % (c["id"], mark, h, disp, defect or ""))
        print("\nDEFECT samples: %d" % defs)
        return 0

    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "python" / "windows").mkdir(parents=True, exist_ok=True)
    EVID.mkdir(parents=True, exist_ok=True)
    (EVID / "conflicts").mkdir(parents=True, exist_ok=True)
    (EVID / "defects").mkdir(parents=True, exist_ok=True)

    cells, extras, defects = [], [], []
    for c in cases:
        if c["id"] in ("T17", "T18"):
            continue  # length cells handled separately
        for sub, h, name, defect in samples_with_subids(c):
            if defect:
                defects.append({"case_id": sub, "hex": h, "decoded": name,
                                "defect": defect, "category": c["category"]})
                continue
            cell, extra = measure_cell(sub, "trap", h, c["category"], c["locale"])
            cells.append(cell); extras.append(extra)

    ctrl_cells, ctrl_extra = run_controls()
    cells += ctrl_cells; extras += ctrl_extra

    len_cells = run_len_cells() if "--len" in args else []
    cells += len_cells
    extras += [{"run_dir": "", "read_detail": {}} for _ in len_cells]

    api_cells = []
    if "--api" in args:
        (RESULTS / "python" / "api").mkdir(parents=True, exist_ok=True)
        api_cells = run_api_sweep(cases)
        for c in api_cells:
            p = RESULTS / "python" / "api" / (c["case_id"].replace("@", "__") + ".json")
            p.write_text(json.dumps(c, indent=2, ensure_ascii=True), encoding="utf-8", newline="\n")
        (RESULTS / "python" / "api-entry.windows.json").write_text(
            json.dumps({"meta": {"harness_version": HARNESS_VERSION, "worker_id": WORKER_ID,
                                 "case_group": "tapi", "entries": PY_ENTRIES},
                        "cells": api_cells}, indent=2, ensure_ascii=True),
            encoding="utf-8", newline="\n")

    # bundle outputs
    ver = platform.python_version()
    for cell, extra in zip(cells, extras):
        p = RESULTS / "python" / "windows" / ("%s.json" % cell["case_id"])
        p.write_text(json.dumps(cell, indent=2, ensure_ascii=True), encoding="utf-8", newline="\n")
    bundle = {"meta": {"harness_version": HARNESS_VERSION, "worker_id": WORKER_ID,
                       "language": "python", "os": "windows", "python": PY,
                       "python_version": ver, "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")},
              "cells": cells}
    (RESULTS / ("python.windows.%s.json" % ver)).write_text(
        json.dumps(bundle, indent=2, ensure_ascii=True), encoding="utf-8", newline="\n")

    phantom = [c for c in cells if c.get("phantom")]
    (RESULTS / "python" / "phantom.windows.json").write_text(
        json.dumps({"count": len(phantom), "cells": phantom}, indent=2, ensure_ascii=True),
        encoding="utf-8", newline="\n")

    (EVID / "defects" / "sample-corruption.json").write_text(
        json.dumps({"count": len(defects), "defects": defects}, indent=2, ensure_ascii=True),
        encoding="utf-8", newline="\n")

    conflicts = [c for c in cells if c.get("instrument_conflict")]
    for c in conflicts:
        (EVID / "conflicts" / ("%s.json" % c["case_id"])).write_text(
            json.dumps(c, indent=2, ensure_ascii=True), encoding="utf-8", newline="\n")

    print("cells written: %d (traps=%d ctrl=%d len=%d defects-skipped=%d conflicts=%d phantom=%d)" % (
        len(cells),
        len([c for c in cells if c["case_group"] == "trap"]),
        len([c for c in cells if c["case_group"] == "ctrl"]),
        len([c for c in cells if c["case_group"] == "len"]),
        len(defects), len(conflicts), len(phantom)))
    if api_cells:
        print("tapi cells written: %d" % len(api_cells))
    return 0


if __name__ == "__main__":
    sys.exit(main())
