#!/usr/bin/env python3
"""SENDGUARD S02 C# port harness.

Drives the pinned csharp entries through the frozen case table, one child process per
cell, with an externally enforced 5 s timeout. Writes one file per cell into
results/csharp.windows.x64/.

Discipline this file implements (it does not interpret the contract freely):
  - spec/cases.yaml is read for hex samples ONLY; names are decoded at runtime (N12).
  - reserved device names are created and listed, never opened for content; their cells
    get a ZERO-LENGTH payload so no bytes are ever pushed into a live device.
  - the cell scratch dir is a fresh uuid dir, verified empty by the child before any attempt.
  - no deletion logic anywhere (M19): scratch dirs are left in place.
  - dir_view (bytes_on_disk authority) is taken by THIS process in Python, not by the
    measured language, so path_view and dir_view can actually disagree.

Usage:
    python impl/csharp/run_csharp.py --plan      # print the cell plan, touch nothing
    python impl/csharp/run_csharp.py --controls  # run the 5 control cells only
    python impl/csharp/run_csharp.py --matrix    # run trap / tapi / blind / len cells
"""
import argparse
import datetime
import glob
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import time
import uuid

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CASES_YAML = os.path.join(REPO, "spec", "cases.yaml")
RESULTS_DIR = os.path.join(REPO, "results", "csharp.windows.x64")
DOTNET = r"C:\Program Files\dotnet\dotnet.exe"
PROBE_DLL = r"D:\sg-cs-scratch\build\SendGuardProbe.dll"
SCRATCH_BASE13 = r"D:\sgcs"              # len cells need a directory path of exactly 13 chars
SCRATCH_ROOT = r"D:\sg-cs-scratch\cells"
REPORT_DIR = r"D:\sg-cs-scratch\reports"
TIMEOUT_S = 5.0
HARNESS_VERSION = "csharp-s02-4-rev6"
WORKER_ID = "seat-qoder/csharp-port"
LANG = "csharp"
OS = "windows"
LENGTH_UNIT = "utf16_code_units"      # rev3: the unit this port measures lengths in
RECORD_ENCODING = "hex_raw_bytes"     # rev3: how the name in the record is encoded (UTF-8 hex)
VERDICT_VIA = "win32"                 # the legality probe is kernel32 CreateFileW, not .NET
PRIMARY_ENTRY = "File.WriteAllBytes"
PINNED_ENTRIES = ["File.WriteAllBytes", "File.Create", "FileStream", "File.Move"]
CANON_PAYLOAD_SHA = "c9fe45b2fee8ea846f0cf4f2cacc2a891e7b082e7719923502d12a9813e21994"
REQUIRED_MANIFEST = os.path.join(REPO, "spec", "cells-required.json")
# the frozen grid points that belong to a base rung (spec/FROZEN.md); base 78 has none defined
GRID_BY_BASE = {120: [137, 138, 139], 200: [254, 255, 256], 13: [244, 245, 246]}
LEN_SHAPE = {"T17": "nested", "T18": "comp"}

RESERVED_RE = re.compile(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9]|CONIN\$|CONOUT\$)(\..*)?$", re.I)
UNSAFE_CONTENT_RE = re.compile(r'[<>:"|?*\x00-\x1f]')
TRAILING_DOT_SPACE_RE = re.compile(r"[. ]$")

LEN_LITERAL = {"T17": "T-LEN-PATH", "T18": "T-LEN-COMP"}
# rev3: the cell set comes from spec/cells-required.json, not from a reading of the yaml.
# spec/cases.yaml still supplies the SAMPLES (hex) and the member order (m1 = first member).
REQUIRED_TRAP_MEMBER_COUNT = {"T09": 2, "T14": 3, "T19": 2}


# ------------------------------------------------------------------ spec reading
def utf8hex(s):
    return "".join("%02x" % b for b in s.encode("utf-8"))


def hexdecode(h):
    return bytes.fromhex(h).decode("utf-8")


def scrub_str(text, needles):
    """N12: no raw sample name and no scratch path is ever published in a result file."""
    if not isinstance(text, str) or not text:
        return text
    out = text
    for n in needles:
        if n and n in out:
            out = out.replace(n, "<HEX:" + utf8hex(n) + ">")
    return out


def scrub(obj, needles):
    if isinstance(obj, str):
        return scrub_str(obj, needles)
    if isinstance(obj, list):
        return [scrub(x, needles) for x in obj]
    if isinstance(obj, dict):
        return {k: scrub(v, needles) for k, v in obj.items()}
    return obj


def read_spec():
    """Minimal reader for the frozen table: id -> {hex list, category, locale, applicable}."""
    with io.open(CASES_YAML, encoding="utf-8") as f:
        lines = f.read().split("\n")
    cases = {}
    cur = None
    in_list = False
    for ln in lines:
        m = re.match(r"^  - id: (\S+)\s*$", ln)
        if m:
            cur = m.group(1)
            cases[cur] = {"hex": [], "category": None, "locale": None, "applicable": [],
                          "payload_hex": None}
            in_list = False
            continue
        if cur is None:
            continue
        m = re.match(r"^\s+sample_hex: \"([0-9a-fA-F]+)\"", ln)
        if m:
            cases[cur]["hex"] = [m.group(1).lower()]
            continue
        m = re.match(r"^\s+payload_hex: \"([0-9a-fA-F]+)\"", ln)
        if m:
            cases[cur]["payload_hex"] = m.group(1).lower()
            continue
        m = re.match(r"^\s+sample_hex_list:\s*$", ln)
        if m:
            in_list = True
            cases[cur]["hex"] = []
            continue
        if in_list:
            m = re.match(r"^\s+- \"([0-9a-fA-F]+)\"", ln)
            if m:
                cases[cur]["hex"].append(m.group(1).lower())
                continue
            in_list = False
        m = re.match(r"^\s+category: (\S+)\s*$", ln)
        if m:
            cases[cur]["category"] = m.group(1)
            continue
        m = re.match(r"^\s+locale: (\S+)\s*$", ln)
        if m:
            cases[cur]["locale"] = m.group(1)
            continue
        m = re.match(r"^\s+applicable: \[([^\]]*)\]\s*$", ln)
        if m:
            cases[cur]["applicable"] = [x.strip() for x in m.group(1).split(",")]
            continue
        m = re.match(r"^\s+sample_hex: \"(T-LEN[^\"]*)\"", ln)
        if m:
            cases[cur]["literal"] = m.group(1)
    return cases


def read_blind_map():
    p = os.path.join(REPO, "evidence", "S00", "blind-map.json")
    with io.open(p, encoding="utf-8") as f:
        doc = json.load(f)
    return [(int(e["blind_id"]), e["name_utf8_hex"].lower()) for e in doc["entries"]], doc


def spec_sha256_from_blob():
    """spec_sha256 comes from the COMMITTED blob face, not the working tree."""
    r = subprocess.run(["git", "-C", REPO, "cat-file", "blob", "HEAD:spec/cases.yaml"],
                       capture_output=True)
    if r.returncode != 0:
        raise RuntimeError("git cat-file rc=%d stderr=%s" % (r.returncode, r.stderr[:120]))
    return hashlib.sha256(r.stdout).hexdigest(), r.returncode


# ------------------------------------------------------------------ environment
def registry_longpaths():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\FileSystem") as k:
            v, _ = winreg.QueryValueEx(k, "LongPathsEnabled")
        return int(v)
    except Exception as e:
        return None


def env_block():
    import ctypes
    v = sys.getwindowsversion()
    k32 = ctypes.windll.kernel32
    return {
        "LongPathsEnabled": registry_longpaths(),
        "max_component": 255,
        "toolchain": "dotnet.exe " + dotnet_version() + " (" + DOTNET + ") / net8.0 / " + HARNESS_VERSION,
        "os_version": "Windows-10-10.0.%d-SP0" % v.build,
        "build": v.build,
        "arch": os.environ.get("PROCESSOR_ARCHITECTURE", "unknown"),
        "locale": locale_name(),
        "lcid": k32.GetUserDefaultLCID(),
        "console_cp": k32.GetConsoleCP(),
        "console_output_cp": k32.GetConsoleOutputCP(),
        "acp": k32.GetACP(),
        "unicode_version": "not-obtainable-here",
        "probe_dll_sha256": sha256_file(PROBE_DLL),
        "harness_py": sys.version.split()[0],
    }


def locale_name():
    import locale
    try:
        return "%s/%s" % (locale.getlocale()[0], locale.getdefaultlocale()[1])
    except Exception:
        return "unknown"


_VERSION_CACHE = None


def dotnet_version():
    global _VERSION_CACHE
    if _VERSION_CACHE is not None:
        return _VERSION_CACHE
    r = subprocess.run([DOTNET, "--version"], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0 or not r.stdout.strip():
        raise RuntimeError("dotnet --version rc=%d out=%r err=%r" % (r.returncode, r.stdout[:80], r.stderr[:80]))
    _VERSION_CACHE = r.stdout.strip().splitlines()[-1].strip()
    return _VERSION_CACHE


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


# ------------------------------------------------------------------ scratch
def cell_dir_for(base_len, need_len):
    """Return a directory path whose length is exactly base_len, ending in a fresh uuid tag.

    base_len 13 is the shortest the grid asks for, so the tree hangs off SCRATCH_BASE13
    (7 chars) + 1 + a 5-char tag. Longer bases add 60-char components.
    """
    tag = uuid.uuid4().hex[:5]
    p = SCRATCH_BASE13 + "\\" + tag
    if len(p) != 13:
        raise RuntimeError("base13 arithmetic broke: %r has %d chars" % (p, len(p)))
    if base_len == 13:
        return p
    while len(p) + 1 + 60 <= base_len - 1:
        p = p + "\\" + "d" * 60
    rem = base_len - len(p) - 1
    if rem < 1:
        raise RuntimeError("cannot build base of %d from %r" % (base_len, p))
    return p + "\\" + "d" * rem


def new_cell_dir():
    os.makedirs(SCRATCH_ROOT, exist_ok=True)
    d = os.path.join(SCRATCH_ROOT, "c" + uuid.uuid4().hex[:12])
    os.makedirs(d, exist_ok=False)
    return d


# ------------------------------------------------------------------ child call
def run_child(spec, dir_path):
    """One child process per cell. Returns (report_dict_or_None, meta)."""
    # the report file deliberately lives OUTSIDE the measured directory, so dir_view of a cell
    # contains only what the cell itself created and the phantom check needs no exclusions
    os.makedirs(REPORT_DIR, exist_ok=True)
    report_path = os.path.join(REPORT_DIR,
                               os.path.basename(dir_path) + "-" + uuid.uuid4().hex[:6] + ".json")
    argv = [DOTNET, "exec", PROBE_DLL,
            "--mode", spec["mode"], "--dir", dir_path, "--shape", spec["shape"],
            "--entry", spec["entry"], "--form", spec["form"],
            "--legality", "1" if spec["legality"] else "0",
            "--payload", spec["payload"], "--report", report_path]
    if spec["shape"] == "name":
        argv += ["--name-hex", spec["name_hex"]]
    else:
        argv += ["--comp-len", str(spec.get("comp_len") or 0), "--fill", spec["fill"]]
    if spec["mode"] == "len":
        argv += ["--bisect-lo", str(spec["bisect_lo"]), "--bisect-hi", str(spec["bisect_hi"])]
        if spec.get("points"):
            argv += ["--points", ",".join(str(x) for x in spec["points"])]
    elif spec["mode"] == "bisect":
        argv += ["--bisect-lo", str(spec["bisect_lo"]), "--bisect-hi", str(spec["bisect_hi"])]
    if spec.get("zip_entries"):
        argv += ["--zip-entry-hexes", ",".join(spec["zip_entries"])]
    if spec.get("co_name_hex"):
        argv += ["--co-name-hex", spec["co_name_hex"]]
    if spec.get("payload_hex"):
        argv += ["--payload-hex", spec["payload_hex"]]

    t0 = time.monotonic()
    started_at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    meta = {"argv": argv, "started_at": started_at, "timed_out": False, "rc": None,
            "stdout": "", "stderr": "", "child_ms": 0}
    try:
        p = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=TIMEOUT_S)
        meta["rc"] = p.returncode
        meta["stdout"] = (p.stdout or "")[:400]
        meta["stderr"] = (p.stderr or "")[:600]
    except subprocess.TimeoutExpired as e:
        meta["timed_out"] = True
        meta["rc"] = None
        meta["stdout"] = ((e.stdout or b"") if isinstance(e.stdout, bytes) else (e.stdout or ""))[:400]
        meta["stderr"] = ((e.stderr or b"") if isinstance(e.stderr, bytes) else (e.stderr or ""))[:600]
    meta["child_ms"] = int((time.monotonic() - t0) * 1000)
    rep = None
    if os.path.isfile(report_path):
        try:
            with io.open(report_path, encoding="utf-8") as f:
                rep = json.load(f)
        except Exception as e:
            meta["report_error"] = "%s: %s" % (type(e).__name__, str(e)[:160])
    meta["report_present"] = rep is not None
    return rep, meta


# ------------------------------------------------------------------ external dir_view
def ext_view(dir_path):
    """Independent enumeration in a language that is not the measured one. Opens no content."""
    rows = []
    target = "\\\\?\\" + dir_path
    try:
        for e in os.scandir(target):
            try:
                nm = e.name
            except Exception:
                nm = "?"
            is_dir = None
            size = None
            err = None
            try:
                is_dir = e.is_dir(follow_symlinks=False)
                if not is_dir:
                    size = e.stat(follow_symlinks=False).st_size
            except Exception as ex:
                err = "%s: %s" % (type(ex).__name__, str(ex)[:120])
            rows.append({"name_hex": utf8hex(nm),
                         # Python's len() is CODE POINTS; UTF-16 units are 2 bytes per BMP char
                         # and 4 for a surrogate pair. IV' compares like with like, so record both.
                         "name_utf16_units": len(nm.encode("utf-16-le")) // 2,
                         "name_code_points": len(nm),
                         "name_utf8_bytes": len(nm.encode("utf-8")),
                         "is_dir": bool(is_dir) if is_dir is not None else None,
                         "size": size, "stat_error": err})
    except Exception as ex:
        return {"ok": False, "error": "%s: %s" % (type(ex).__name__, str(ex)[:160]), "entries": rows,
                "count": len(rows)}
    return {"ok": True, "error": None, "entries": rows, "count": len(rows)}


def ext_read_sha256(dir_path, name):
    """Hash the landed bytes through the \\\\?\\ face. Refused for reserved / unsafe names."""
    if RESERVED_RE.match(name):
        return None, ("refused: the landed name is a reserved device name - the contract allows "
                      "create and list only, its content is never opened")
    if UNSAFE_CONTENT_RE.search(name) or TRAILING_DOT_SPACE_RE.search(name):
        return None, ("refused: the landed name cannot be reopened by its own literal string "
                      "(Win32 would re-parse it), so a read would not be a read of this entry")
    try:
        with open("\\\\?\\" + os.path.join(dir_path, name), "rb") as f:
            return hashlib.sha256(f.read()).hexdigest(), None
    except Exception as e:
        return None, "%s: %s" % (type(e).__name__, str(e)[:160])


# ------------------------------------------------------------------ cell assembly
def find_entry(rows, name_hex):
    for r in rows:
        if r["name_hex"] == name_hex:
            return r
    return None


SCRUBBED_FIELDS = ("error_message", "child_exception", "dir_view_error", "blocked_command",
                   "blocked_fix_attempted", "zip_roundtrip", "path_view_entries_after_create",
                   "path_view_entries_after_legality", "dir_view_entries",
                   "dir_view_cell_entries", "unaccounted_entries")


def scrub_selected(cell, needles):
    """Only child-originated text is scrubbed: harness prose must never be rewritten by it."""
    for k in SCRUBBED_FIELDS:
        if k in cell:
            cell[k] = scrub(cell[k], needles)
    return cell


def build_cell(kind, spec, cases, blind, env, ctx):
    """Run one cell end to end. Returns (cell_dict, cell_scratch_dir)."""
    cid = spec["case_id"]
    group = spec["group"]
    entry = spec["entry"]
    form = spec["form"]
    name_hex = spec.get("name_hex")
    name = hexdecode(name_hex) if name_hex else None
    reserved = bool(name and RESERVED_RE.match(name))
    cell_id = spec["cell_id"]

    if spec["shape"] == "name" or spec["shape"] == "comp" or spec["shape"] == "nested":
        if spec.get("base_len"):
            cdir = cell_dir_for(spec["base_len"], spec["base_len"])
        else:
            cdir = new_cell_dir()
    else:
        cdir = new_cell_dir()
    os.makedirs(cdir, exist_ok=True)

    rep, meta = run_child(spec, cdir)
    elapsed = meta["child_ms"]

    cell = {}
    cell["format_version"] = 1
    cell["case_group"] = group
    cell["case_id"] = cid
    cell["language"] = LANG
    cell["os"] = OS
    cell["os_version"] = env["os_version"]
    cell["arch"] = env["arch"]
    cell["locale"] = spec.get("locale") or env["locale"]
    cell["api_entry"] = entry
    cell["primary_entry"] = (entry == PRIMARY_ENTRY)
    cell["attempt"] = 1
    # rev3 split: name_encoding says how the name in THIS record is encoded, length_unit says
    # what unit the port's lengths were counted in. They are different concepts and both exist.
    cell["name_encoding"] = RECORD_ENCODING
    cell["length_unit"] = LENGTH_UNIT
    cell["verdict_via"] = "none"          # upgraded to win32 below when the OS was actually asked
    cell["verdict_via_method"] = None
    cell["name_source"] = spec["name_source"]
    cell["path_form"] = form
    cell["extra"] = bool(spec.get("extra"))
    cell["in_required_list"] = bool(spec.get("in_required"))
    cell["sub_identity"] = dict(spec.get("sub_identity") or {})
    cell["required_identity"] = identity_key(spec)
    cell["create_result"] = None
    cell["error_stage"] = None
    cell["error_code"] = None
    cell["error_message"] = None
    cell["bytes_written"] = None
    cell["bytes_on_disk"] = None
    cell["read_result"] = None
    cell["os_legality_verdict"] = "unknown"
    cell["harness_version"] = HARNESS_VERSION
    cell["worker_id"] = WORKER_ID
    cell["started_at"] = meta["started_at"]
    cell["elapsed_ms"] = elapsed
    cell["cell_dir_hex"] = utf8hex(cdir)
    cell["scratch_uuid_tag"] = os.path.basename(cdir)
    cell["spec_sha256"] = ctx["spec_sha256"]
    if spec.get("control_pin"):
        # rev6: the control name and payload are pinned by the spec face, not chosen by this port
        cell["control_sample_pin"] = spec["control_pin"]["hex"]
        cell["control_payload_pin"] = spec["control_pin"]["payload_hex"]
        cell["control_payload_sha256"] = spec["control_pin"]["payload_sha256"]
        cell["control_payload_bytes"] = spec["control_pin"]["payload_bytes"]
        cell["control_pin_source"] = "control_samples in spec/cases.yaml (rev6)"
    cell["env"] = {
        "LongPathsEnabled": env["LongPathsEnabled"],
        "max_component": env["max_component"],
        "unicode_version": env["unicode_version"],
        "toolchain": env["toolchain"],
        "dotnet_used": DOTNET,
        "dotnet_other_candidate_on_path": r"C:\Program Files (x86)\dotnet\dotnet.exe",
        "probe_dll_sha256": env["probe_dll_sha256"],
        "console_cp": env["console_cp"],
        "acp": env["acp"],
        "lcid": env["lcid"],
    }

    # --- the ten digest fields ci/equality.py insists every port emits
    cell["name_landed_as"] = None
    cell["name_mutated"] = None
    cell["phantom"] = None
    cell["deps_direct"] = 0
    cell["deps_total"] = 0
    cell["mechanism_class"] = spec["mechanism_class"]
    cell["len_triple"] = None
    cell["roundtrip_ok"] = None
    cell["enum_to_stat_agrees"] = None
    cell["control_pass"] = None
    cell["instrument_red"] = False
    cell["instrument_conflict"] = False
    cell["sha256_self"] = None
    cell["sha256_truth"] = None
    cell["run_status"] = "ran"
    cell["blocked_command"] = None
    cell["blocked_exit_code"] = None
    cell["blocked_fix_attempted"] = None

    if meta["timed_out"]:
        cell["create_result"] = "hang"
        cell["error_stage"] = "syscall"
        cell["error_code"] = "timeout-5s"
        cell["error_message"] = "child killed by harness after %.1fs; stdout=%r" % (TIMEOUT_S, meta["stdout"][:120])
        cell["read_result"] = "hang"
        cell["hang_leg"] = "create"
    elif rep is None:
        cell["create_result"] = None
        cell["error_stage"] = "tool"
        cell["error_code"] = "child-rc=%s,no-report" % meta["rc"]
        cell["error_message"] = "child produced no report file; stderr=%s report_error=%s" % (
            meta["stderr"][:200], meta.get("report_error"))
        cell["run_status"] = "blocked"
        cell["blocked_command"] = " ".join(meta["argv"])
        cell["blocked_exit_code"] = meta["rc"]
        cell["blocked_fix_attempted"] = ctx["blocked_fix"]
    else:
        fill_from_report(cell, rep, meta, spec, cdir, name, name_hex, reserved, env)

    # --- length dimensions. One cell answers one question: where does the length stop binding
    # at THIS base rung. The child bisects inside the cell, so the cell's own create attempt is
    # the last length that succeeds and the boundary is that attempt's x (base_len is in the
    # cell, not only in the filename - spec/cell-identity.md s1).
    if group == "len":
        lm = (rep or {}).get("len_measure")
        cell["base_len"] = spec["base_len"]
        cell["base_len_measured"] = len(cdir)
        cell["len_shape"] = spec["shape"]
        cell["sub_identity"] = {"base_len": spec["base_len"], "path_form": spec["form"]}
        cell["frozen_grid_points_for_this_base"] = GRID_BY_BASE.get(spec["base_len"], [])
        if not lm:
            cell["len_measure_missing"] = True
            for f in ("grid_point", "len_target_extra_units", "component_len", "total_path_len",
                      "len_triple", "bisect_boundary", "bisect_conclusive"):
                cell[f] = None
        else:
            primary = lm.get("primary") or {}
            unit = int(primary.get("name_utf16_units") or 0)
            cell["grid_point"] = lm.get("boundary")
            cell["len_target_extra_units"] = lm.get("boundary")
            cell["component_len"] = unit
            # for the nested shape the x units are split across a chain of short directories, so
            # the component that binds is never near the volume limit - record the split
            if spec["shape"] == "nested":
                x = lm.get("boundary") or 0
                cell["nested_chain_depth"] = (x - unit) // 61
                cell["max_component_len"] = max(60, unit)
            else:
                cell["nested_chain_depth"] = 0
                cell["max_component_len"] = unit
            cell["total_path_len"] = cell.get("api_path_len") or (len(cdir) + 1 + unit)
            # the fill is ASCII, so the three counting units coincide for this corpus by fact
            cell["len_triple"] = [unit, unit, unit]
            cell["bisect_boundary"] = lm.get("boundary")
            cell["bisect_lo"] = lm.get("bisect_lo")
            cell["bisect_hi"] = lm.get("bisect_hi")
            cell["bisect_probes_run"] = (lm.get("bisect") or {}).get("probes_run")
            cell["bisect_conclusive"] = not lm.get("boundary_at_instrument_ceiling")
            cell["bisect_ceiling_is_instrument_not_filesystem"] = bool(
                lm.get("boundary_at_instrument_ceiling"))
            b1 = lm.get("boundary_plus1") or {}
            cell["boundary_plus1_result"] = b1.get("create_result")
            cell["boundary_plus1_error_code"] = b1.get("error_code")
            cell["grid_point_attempts"] = [
                {"x": g.get("x"), "create_result": g.get("create_result"),
                 "error_code": g.get("error_code"), "name_hex": g.get("name_hex"),
                 "path_len": g.get("path_len")} for g in (lm.get("grid_points") or [])]
            ext = lm.get("extended_corroboration") or {}
            cell["extended_corroboration"] = {k: ext.get(k) for k in
                                              ("create_result", "error_code", "form", "path_len",
                                               "name_hex", "name_utf16_units")}
            cell["extended_leg_lives_inside_cell_because"] = (
                "path_form is not part of the cell identity (ci/equality.py sub_identity carries "
                "base_len only), so a second record with this identity would be read as the port "
                "disagreeing with itself")

            # spec/gate.md s5 (rev4): the bisection regime is keyed by longpath_mechanism, NOT by
            # path_form, and a port that fits neither model is reported `unresolved`.
            mech = cell["longpath_mechanism"]
            b1 = lm.get("boundary_plus1") or {}
            obs_code = b1.get("error_code")
            cell["bisection_regime"] = mech
            cell["regime_observed_boundary_code"] = obs_code
            if spec["shape"] == "comp":
                if mech in ("manifest", "prefix_rewrite"):
                    cell["regime_expected_max_component"] = env["max_component"]
                    cell["regime_expected_boundary_code"] = "winerror=123"
                elif mech == "none":
                    cell["regime_expected_max_component"] = 259 - spec["base_len"] - 1
                    cell["regime_expected_boundary_code"] = "winerror=3"
                else:
                    cell["regime_expected_max_component"] = None
                    cell["regime_expected_boundary_code"] = None
                cell["regime_observed_max_component"] = unit
                cell["regime_verdict"] = (
                    "unresolved" if cell["regime_expected_max_component"] is None else
                    "satisfied" if (unit == cell["regime_expected_max_component"]
                                    and obs_code == cell["regime_expected_boundary_code"])
                    else "violated")
            else:
                # the nested shape varies the TOTAL, and the rev4 regime only predicts a component
                # ceiling; it says nothing about where the total stops. Reported, not bucketed.
                cell["regime_expected_max_component"] = None
                cell["regime_expected_boundary_code"] = None
                cell["regime_observed_max_component"] = cell["max_component_len"]
                cell["regime_verdict"] = "unresolved"
                cell["regime_unresolved_reason"] = (
                    "gate.md s5 (rev4) predicts max_component under a prefix-rewriting runtime; "
                    "this cell varies the total path length with every component <= 60, so no "
                    "regime covers it. Bisection ran to the instrument ceiling %s without "
                    "bracketing a boundary." % (lm.get("bisect_hi")))
        if cell["base_len"] != cell["base_len_measured"]:
            cell["instrument_conflict"] = True
            cell["base_len_conflict"] = "manifest says %s, directory is %s chars" % (
                cell["base_len"], cell["base_len_measured"])

    needles = [cdir]
    if spec.get("name_hex"):
        needles.append(hexdecode(spec["name_hex"]))
    if spec.get("fill") and spec.get("comp_len"):
        needles.append(spec["fill"] * spec["comp_len"])
    if spec.get("zip_entries"):
        for h in spec["zip_entries"]:
            needles.append(hexdecode(h))
    cell = scrub_selected(cell, needles)
    return cell, cdir


def final_len(x):
    k = 0
    while x - 61 * (k + 1) >= 1:
        k += 1
    return x - 61 * k


def fill_from_report(cell, rep, meta, spec, cdir, name, name_hex, reserved, env):
    att = (rep.get("attempts") or [None])[0]
    cell["precondition_ok"] = bool((rep.get("precondition") or {}).get("ok"))
    cell["precondition_reason"] = (rep.get("precondition") or {}).get("reason")
    cell["sha256_self"] = rep.get("sha256_payload_self")
    cell["payload_bytes"] = rep.get("payload_bytes")
    cell["payload_policy"] = rep.get("payload_policy")
    cell["name_hex_from_child"] = rep.get("name_hex")
    cell["name_utf16_units"] = rep.get("name_utf16_units")
    cell["name_code_points"] = rep.get("name_code_points")
    cell["name_utf8_bytes"] = rep.get("name_utf8_bytes")
    cell["child_elapsed_ms"] = rep.get("elapsed_child_ms")
    if rep.get("child_exception"):
        cell["child_exception"] = rep["child_exception"]
    if att is None:
        cell["create_result"] = None
        cell["error_stage"] = "tool"
        cell["error_code"] = "no-attempt-recorded"
        cell["error_message"] = "child returned a report with no create attempt"
        cell["run_status"] = "blocked"
        cell["blocked_command"] = " ".join(meta["argv"])
        cell["blocked_exit_code"] = meta["rc"]
        cell["blocked_fix_attempted"] = "re-run with --mode point after checking Setup()/ResolveName() in impl/csharp/Program.cs"
        return
    cell["create_result"] = att.get("create_result")
    cell["error_stage"] = att.get("error_stage")
    cell["error_code"] = att.get("error_code")
    cell["error_message"] = att.get("error_message")
    cell["bytes_written"] = att.get("bytes_written")
    cell["api_path_len"] = att.get("path_len")

    legality = rep.get("legality") or {}
    cell["legality_attempted"] = legality.get("attempted")
    cell["legality_winerror"] = legality.get("winerror")
    cell["legality_mechanism"] = legality.get("mechanism")
    cell["os_legality_verdict"] = legality.get("verdict", "unknown")
    # rev3: a legality verdict must name the tool that was asked. This port asks kernel32
    # CreateFileW directly (through the \\?\ face, dwDesiredAccess=0), NOT the .NET file APIs,
    # so the verdict is not coloured by the runtime under test.
    if legality.get("attempted"):
        cell["verdict_via"] = VERDICT_VIA
        cell["verdict_via_method"] = "kernel32.CreateFileW(\\\\?\\ + dwDesiredAccess=0 + CREATE_NEW) via P/Invoke"
    else:
        cell["verdict_via"] = "none"
        cell["verdict_via_method"] = legality.get("reason")
    if cell["os_legality_verdict"] not in ("legal", "illegal", "unknown"):
        cell["os_legality_verdict"] = "unknown"
        cell["legality_word_offclosedset"] = legality.get("verdict")

    # path_view (the measured language's own enumeration) vs dir_view (this harness, in Python,
    # i.e. a language that is not the one under test). dir_view runs on the directory the child
    # actually created into, which for a nested T-LEN cell is the end of the chain.
    tgt = cdir
    if rep.get("target_dir_hex"):
        try:
            tgt = hexdecode(rep["target_dir_hex"])
        except Exception:
            tgt = cdir
    pv = (rep.get("path_view_after_create") or {}).get("target_dir") or []
    pv_final = (rep.get("path_view_after_legality") or {}).get("target_dir") or []
    dv = ext_view(tgt)
    dvc = ext_view(cdir) if tgt != cdir else dv
    cell["target_dir_hex"] = rep.get("target_dir_hex")
    cell["path_view_count"] = len(pv)
    cell["dir_view_count"] = dv["count"]
    cell["dir_view_error"] = dv["error"]
    cell["dir_view_entries"] = dv["entries"]
    cell["dir_view_cell_entries"] = dvc["entries"]
    cell["path_view_entries_after_create"] = pv
    cell["path_view_entries_after_legality"] = pv_final

    landed_hex = cell["name_hex_from_child"]
    pv_exact = find_entry(pv, landed_hex)
    exact = find_entry(dv["entries"], landed_hex)
    accounted = {utf8hex("leg")}
    if rep.get("move_source_name"):
        accounted.add(utf8hex(rep["move_source_name"]))
    # a cell may legitimately create more than one entry (the T-LEN ladder runs its bisection
    # inside the cell; the T09 sibling is created as coexistence evidence). Name every one of
    # them, otherwise a legitimate landing would be reported as a phantom.
    for h in (rep.get("created_names_hex") or []):
        accounted.add(h)
    co = rep.get("coexistence")
    if co:
        cell["coexistence"] = {k: co.get(k) for k in
                               ("sibling_name_hex", "sibling_utf16_units", "this_cell_name_hex",
                                "same_name_hits_sibling", "same_name_hits_this_cell", "coexist",
                                "dir_entry_count", "dir_entry_hexes")}
        cell["coexistence"]["sibling_create_result"] = (co.get("attempts") or [{}])[0].get("create_result")
        cell["coexistence"]["sibling_lives_in_same_dir_as"] = "this cell's measured entry"
        for h in (co.get("dir_entry_hexes") or []):
            accounted.add(h)
    z = rep.get("zip")
    if z:
        if z.get("artifact_name_hex"):
            accounted.add(z["artifact_name_hex"])
        accounted.add(utf8hex("_unz"))
    candidates = [r for r in dv["entries"] if r["name_hex"] not in accounted]
    if exact is None and len(candidates) == 1:
        # the precondition guaranteed an empty dir, so a lone unaccounted entry IS this
        # create's landing - under a different name than asked for (Win32 rewrote it)
        landed = candidates[0]
    else:
        landed = exact
    cell["name_landed_as"] = landed["name_hex"] if landed else None
    cell["landed_name_utf16_units"] = landed["name_utf16_units"] if landed else None
    cell["name_mutated"] = None if landed is None else (landed["name_hex"] != landed_hex)
    cell["requested_vs_landed_len_delta"] = (
        None if landed is None
        else landed["name_utf16_units"] - (cell.get("name_utf16_units") or 0))
    cell["bytes_on_disk"] = landed["size"] if landed is not None else 0
    cell["bytes_on_disk_authority"] = "dir_view (Python enumerator, not the measured language)"

    pv_candidates = [r for r in pv if r["name_hex"] not in accounted]
    pv_landed = pv_exact
    if pv_landed is None and len(pv_candidates) == 1:
        pv_landed = pv_candidates[0]
    cell["path_view_landed_as"] = pv_landed["name_hex"] if pv_landed else None
    if pv_landed is not None and landed is not None:
        cell["enum_to_stat_agrees"] = (pv_landed["name_hex"] == landed["name_hex"]
                                       and pv_landed["size"] == landed["size"])
        if not cell["enum_to_stat_agrees"]:
            cell["view_divergence"] = "path_view=%s/%s dir_view=%s/%s" % (
                pv_landed["name_hex"], pv_landed["size"], landed["name_hex"], landed["size"])
    else:
        cell["enum_to_stat_agrees"] = (pv_landed is None and landed is None)

    cell["longpath_mechanism"] = longpath_mechanism(cell, spec, env)

    # read side: observe what is actually on disk, never what the language claims
    landed_name = hexdecode(landed["name_hex"]) if landed else None
    cell["phantom"] = False
    cell["roundtrip_ok"] = False
    cell["roundtrip_basis"] = "no successful roundtrip: nothing was read back that matches what was written"
    # rev4 added the fifth read_result word: a cell with nothing to read says `not_applicable`
    # and carries `read_skipped_reason`. null was never a legal word and is not used here.
    if cell["create_result"] == "ok" and landed is None:
        cell["phantom"] = True
        cell["read_result"] = "not_applicable"
        cell["read_attempted"] = False
        cell["read_skipped_reason"] = ("create reported success but dir_view shows no entry at that "
                                       "name; there was no subject to read, so no open was issued")
    elif cell["create_result"] == "ok" and landed is not None:
        sha_truth, refuse = ext_read_sha256(tgt, landed_name)
        cell["sha256_truth"] = sha_truth
        if refuse:
            cell["read_result"] = "not_applicable"
            cell["read_attempted"] = False
            cell["read_skipped_reason"] = refuse
        else:
            size = landed["size"] or 0
            cell["read_result"] = "ok" if size > 0 else "eof"
            cell["read_attempted"] = True
            cell["read_skipped_reason"] = None
            cell["roundtrip_ok"] = (sha_truth == cell["sha256_self"]
                                    and cell["bytes_written"] == cell["bytes_on_disk"])
            cell["roundtrip_basis"] = "read-back bytes vs the bytes handed to the API"
    else:
        cell["read_result"] = "not_applicable"
        cell["read_attempted"] = False
        cell["read_skipped_reason"] = "create failed, so there was no subject to read (no open was issued)"

    unexplained = [r for r in dv["entries"] if r["name_hex"] not in accounted
                   and (landed is None or r["name_hex"] != landed["name_hex"])]
    if tgt != cdir:
        # a nested cell also lists its own cell dir: short probes land there directly, and the
        # chain root lives there too, so both are legitimate unless something else shows up
        unexplained += [r for r in dvc["entries"]
                        if r["name_hex"] not in accounted
                        and r["name_hex"] != utf8hex(os.path.basename(tgt))]
    cell["unaccounted_entries"] = unexplained
    if unexplained:
        cell["phantom"] = True

    if rep.get("zip"):
        cell["zip_roundtrip"] = rep["zip"]
        # packer/extractor are NOT copied to the top level on purpose: ci/equality.py treats a
        # top-level packer/extractor as part of the cell identity, while the required list gives
        # T16 an empty sub_identity. The names live inside zip_roundtrip instead.
        cell["zip_roundtrip_identity_note"] = (
            "packer/extractor kept nested: spec/cells-required.json gives trap/T16 sub_identity {} "
            "while ci/equality.py SUB_FIELDS would move them into the identity")

    if cell["sha256_self"] and cell["sha256_truth"]:
        cell["instrument_conflict"] = (cell["sha256_self"] != cell["sha256_truth"])

    if cell["payload_policy"] == "zero" and cell["bytes_written"] == 0 and cell["create_result"] == "ok":
        cell["type_II_note"] = ("zero-length payload by contract (reserved device name); "
                               "bytes_written=0 is the instrument policy, not a language choice")


def longpath_mechanism(cell, spec, env):
    """Classified from what the attempt DID, not from what the recipe intended.

    The host-manifest explanation was tested and REFUTED by impl/csharp/apphost_probe.py:
    the published apphost carries no longPathAware token (byte-scan hit_count=0) yet a
    264-char plain path still succeeded with LongPathsEnabled=0, exactly as dotnet.exe did.
    So a plain path past the legacy wall that succeeds was extended by the runtime itself.
    """
    if spec["form"] == "extended":
        cell["prefix_source"] = "recipe-explicit"
        return "prefix_rewrite"                      # the recipe itself supplied \\?\
    total = cell.get("api_path_len") or cell.get("total_path_len") or 0
    if total <= 259:
        return "none"
    if cell["create_result"] == "ok":
        cell["prefix_source"] = "runtime-auto"
        cell["longpath_mechanism_note"] = (
            "plain path of %d chars succeeded while LongPathsEnabled=%s: the runtime extended "
            "the path itself. Not the host manifest - the published apphost with no "
            "longPathAware token behaves identically (impl/csharp/apphost_probe.py)."
            % (total, env["LongPathsEnabled"]))
        return "prefix_rewrite"
    return "none"


# ------------------------------------------------------------------ plan
def read_required():
    with io.open(REQUIRED_MANIFEST, encoding="utf-8") as f:
        return json.load(f)


def split_member(cid):
    """`T09-m1` -> (`T09`, 1). A plain id -> (id, None)."""
    m = re.match(r"^(T\d+)-m(\d+)$", cid)
    if m:
        return m.group(1), int(m.group(2))
    return cid, None


def ctrl_pins(cases, manifest):
    """rev6: the five control cells now have pinned sample bytes in spec/cases.yaml
    (`control_samples`). A port may no longer invent the name for a control id - the measured
    hole was that T-CTRL-CANON arrived as four different names and two different payloads."""
    want = [r["case_id"] for r in manifest["required_cells"] if r["case_group"] == "ctrl"]
    pins = {}
    for cid in want:
        c = cases.get(cid)
        if c is None or not c["hex"]:
            raise RuntimeError("control_samples has no pinned sample for %s" % cid)
        if not c.get("payload_hex"):
            raise RuntimeError("control_samples has no pinned payload for %s" % cid)
        payload = bytes.fromhex(c["payload_hex"])
        sha = hashlib.sha256(payload).hexdigest()
        if sha != CANON_PAYLOAD_SHA:
            raise RuntimeError("pinned payload for %s hashes to %s, expected the sealed %s"
                               % (cid, sha[:12], CANON_PAYLOAD_SHA[:12]))
        pins[cid] = {"hex": c["hex"][0], "payload_hex": c["payload_hex"],
                     "payload_bytes": len(payload), "payload_sha256": sha}
    if len(pins) != len(want):
        raise RuntimeError("pinned controls %d != manifest controls %d" % (len(pins), len(want)))
    return pins


def make_plan():
    """Cell set is DRIVEN by spec/cells-required.json (rev3); samples come from cases.yaml."""
    cases = read_spec()
    blind_ids, blind_doc = read_blind_map()
    req = read_required()
    pins = ctrl_pins(cases, req)
    plan = []

    ctrl_class = {"T-CTRL-NAMETOOLONG": "component_length_limit",
                  "T-CTRL-ILLEGAL-CHAR": "illegal_char_filter",
                  "T-CTRL-PARSE": "control_char_handling",
                  "T-CTRL-CANON": "os_legality",
                  "T-CTRL-ASCII": "unknown"}
    for cid in ["T-CTRL-ASCII", "T-CTRL-CANON", "T-CTRL-ILLEGAL-CHAR", "T-CTRL-NAMETOOLONG", "T-CTRL-PARSE"]:
        pin = pins[cid]
        plan.append({
            "phase": "controls", "group": "ctrl", "case_id": cid, "cell_id": cid,
            "entry": PRIMARY_ENTRY, "form": "plain", "shape": "name", "name_hex": pin["hex"],
            "mode": "point", "legality": True, "payload": "canon", "payload_hex": pin["payload_hex"],
            "name_source": pin["hex"], "mechanism_class": ctrl_class[cid],
            "fill": "a", "extra": False, "in_required": True,
            "control_pin": pin,
        })

    blind_by_id = {bid: h for bid, h in blind_ids}
    for r in req["required_cells"]:
        group = r["case_group"]
        cid = r["case_id"]
        sub = r.get("sub_identity") or {}
        if group == "ctrl":
            continue                      # already emitted above, ruler-first
        if group == "blind":
            h = blind_by_id[int(cid[1:])]
            plan.append({
                "phase": "matrix", "group": "blind", "case_id": cid, "cell_id": cid,
                "entry": PRIMARY_ENTRY, "form": "plain", "shape": "name", "name_hex": h,
                "mode": "point", "legality": True, "payload": "canon", "name_source": h,
                "mechanism_class": "unknown", "sub": None, "blind_id": int(cid[1:]),
                "extra": False, "in_required": True, "sub_identity": dict(sub),
            })
            continue
        if group == "len":
            base = int(sub["base_len"])
            form = sub.get("path_form") or "plain"   # rev5: plain and extended are two measurements
            shape = LEN_SHAPE[cid]
            plan.append({
                "phase": "matrix", "group": "len", "case_id": cid, "cell_id": cid,
                "entry": PRIMARY_ENTRY, "form": form, "shape": shape, "name_hex": None,
                "mode": "len", "legality": True, "payload": "canon",
                "name_source": cases[cid].get("literal") or LEN_LITERAL[cid],
                "mechanism_class": "component_length_limit",
                "base_len": base, "points": GRID_BY_BASE.get(base, []),
                "bisect_lo": 1, "bisect_hi": 300 if shape == "comp" else 2000,
                "fill": "a" if form == "plain" else "z",
                "sub": "base%d-%s" % (base, form), "comp_len": None,
                "sub_identity": {"base_len": base, "path_form": form},
                "extra": False, "in_required": True,
            })
            continue
        base_id, member = split_member(cid)
        c = cases[base_id]
        hexes = c["hex"]
        if member is not None:
            name_hex = hexes[member - 1]
            co_hex = ""
            if base_id == "T09" and len(hexes) > 1:
                # the headline question is coexistence; the sibling is created inside this cell
                # as evidence, because the required identity gives one cell per member
                co_hex = hexes[0] if member == 2 else hexes[1]
        else:
            name_hex = hexes[0]
            co_hex = ""
        nm = hexdecode(name_hex)
        spec = {
            "phase": "matrix", "group": "trap", "case_id": cid, "cell_id": base_id,
            "entry": PRIMARY_ENTRY, "form": "plain", "shape": "name", "name_hex": name_hex,
            "mode": "point", "legality": True,
            "payload": "zero" if RESERVED_RE.match(nm) else "canon",
            "name_source": name_hex, "mechanism_class": c["category"],
            "member": member, "sub": None, "extra": False, "in_required": True,
            "locale": c.get("locale"), "co_name_hex": co_hex,
            "co_role": ("member%d_of%d" % (member, len(hexes))) if member else "single",
        }
        if base_id == "T16":
            spec["zip_entries"] = [name_hex, cases["T06"]["hex"][0]]
        plan.append(spec)

    # spec/gate.md s5 (rev4): "the ladder is {78, 120, 200} required and 13 permitted as extra".
    # Base 13 is the rung the frozen G1/G3 grid sits on, so it is measured and kept, marked extra.
    for cid in ("T17", "T18"):
        shape = LEN_SHAPE[cid]
        plan.append({
            "phase": "matrix", "group": "len", "case_id": cid, "cell_id": cid,
            "entry": PRIMARY_ENTRY, "form": "plain", "shape": shape, "name_hex": None,
            "mode": "len", "legality": True, "payload": "canon",
            "name_source": cases[cid].get("literal") or LEN_LITERAL[cid],
            "mechanism_class": "component_length_limit",
            "base_len": 13, "points": [244, 245, 246, 254, 255, 256],
            "bisect_lo": 1, "bisect_hi": 300 if shape == "comp" else 2000,
            "fill": "a", "sub": "base13-plain", "comp_len": None,
            "sub_identity": {"base_len": 13, "path_form": "plain"},
            "extra": True, "in_required": False,
            "extra_reason": "spec/gate.md s5 (rev4) permits base depth 13 as extra; it is the rung "
                            "the frozen G1/G3 grid sits on",
        })

    probe_hex = cases["T01"]["hex"][0]
    for t in req["tapi_cells_per_language"]:
        if t["language"] != LANG:
            continue
        plan.append({
            "phase": "matrix", "group": "tapi", "case_id": t["case_id"], "cell_id": t["case_id"],
            "entry": t["api_entry"], "form": "plain", "shape": "name", "name_hex": probe_hex,
            "mode": "point", "legality": True, "payload": "zero",
            "name_source": probe_hex, "mechanism_class": "reserved_device_name",
            "sub": slug(t["api_entry"]), "extra": False, "in_required": True,
            "primary_entry": t["api_entry"] == req["primary_entry_per_port"][LANG],
        })
    return plan, cases, blind_doc


def slug(e):
    return re.sub(r"[^A-Za-z0-9.]+", "-", e)


def render_id(group, case_id, sub, api_entry=None):
    key = "%s/%s%s" % (group, case_id,
                       "".join("[%s=%s]" % (k, sub[k]) for k in sorted(sub) if sub[k] is not None))
    if group == "tapi":
        key += "[api_entry=%s]" % api_entry
    return key


def identity_key(spec):
    """The contract identity, spelled the way ci/equality.py builds it. Filenames are not identity."""
    sub = dict(spec.get("sub_identity") or {})
    if spec["group"] == "len":
        sub.setdefault("base_len", spec["base_len"])
        sub.setdefault("path_form", spec["form"])
    return render_id(spec["group"], spec["case_id"], sub, spec["entry"])


def required_identities(manifest):
    out = set()
    for r in manifest["required_cells"]:
        out.add(render_id(r["case_group"], r["case_id"], r.get("sub_identity") or {}))
    for t in manifest["tapi_cells_per_language"]:
        if t["language"] != LANG:
            continue
        out.add(render_id(t["case_group"], t["case_id"], t.get("sub_identity") or {}, t["api_entry"]))
    return out


def produced_identity(cell):
    """Mirror of ci/equality.py sub_identity(): the cell's own declared dimensions win, and the
    known fields are the fallback."""
    declared = cell.get("sub_identity")
    sub = {}
    if isinstance(declared, dict):
        sub = {k: v for k, v in declared.items() if v is not None}
    for f in ("base_len", "builder", "reader", "packer", "extractor"):
        if cell.get(f) is not None and f not in sub:
            sub[f] = cell[f]
    if cell.get("case_group") == "len" and "path_form" not in sub and cell.get("path_form"):
        sub["path_form"] = cell["path_form"]
    return render_id(cell["case_group"], cell["case_id"], sub, cell.get("api_entry"))


def cell_filename(spec):
    parts = [spec["group"], spec["case_id"]]
    if spec.get("sub"):
        parts.append(spec["sub"])
    elif spec["group"] == "tapi":
        parts.append(slug(spec["entry"]))
    # member cells carry `-mN` inside case_id (spec/cells-required.json spells them that way),
    # so the filename must not append the member a second time
    return "__".join(parts) + ".json"


CONTROL_STAMP = r"D:\sg-cs-scratch\controls-green.json"
CONTROL_EXPECTATIONS = {
    # evidence/S00-ctrl-baseline.md is the ONLY allowed source of these (spec/cases.yaml s31)
    "T-CTRL-NAMETOOLONG": {"create_result": "err_at_syscall", "error_stage": "syscall"},
    "T-CTRL-ASCII": {"create_result": "ok", "bytes_written": 28, "bytes_on_disk": 28,
                     "read_result": "ok", "roundtrip_ok": True},
    "T-CTRL-ILLEGAL-CHAR": {"create_result": "err_at_syscall", "error_stage": "syscall"},
    "T-CTRL-PARSE": {"create_result": "err_at_parse", "error_stage": "parse"},
    "T-CTRL-CANON": {"create_result": "ok"},
}


def evaluate_control(cell):
    exp = CONTROL_EXPECTATIONS[cell["case_id"]]
    fails = []
    for k, v in exp.items():
        if cell.get(k) != v:
            fails.append("%s=%r expected %r" % (k, cell.get(k), v))
    if cell["case_id"] == "T-CTRL-CANON":
        for k in ("sha256_self", "sha256_truth"):
            if cell.get(k) != CANON_PAYLOAD_SHA:
                fails.append("%s=%s expected baseline %s" % (k, cell.get(k), CANON_PAYLOAD_SHA))
    return fails


def write_cell(cell, spec):
    path = os.path.join(RESULTS_DIR, cell_filename(spec))
    with io.open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(cell, f, indent=2, sort_keys=True, ensure_ascii=True)
        f.write("\n")
    return path


def cell_digest(cell):
    keep = ["case_group", "case_id", "api_entry", "create_result", "error_stage", "read_result",
            "os_legality_verdict", "bytes_written", "bytes_on_disk", "path_form", "longpath_mechanism"]
    blob = json.dumps({k: cell.get(k, "<absent>") for k in keep}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def asc(s):
    """Console-safe: the host console is cp936, so a raw UTF-8 message prints as mojibake."""
    return (s or "").encode("ascii", "backslashreplace").decode("ascii")


def report_line(fn, cell):
    extra = ""
    if cell["create_result"] != "ok":
        extra = " | %s %s" % (cell["error_code"], asc(str(cell["error_message"] or ""))[:70])
    return ("%-52s create=%-14s read=%-5s legal=%-7s disk=%-5s wrote=%-4s %s%s"
            % (fn, cell["create_result"], cell["read_result"], cell["os_legality_verdict"],
               cell["bytes_on_disk"], cell["bytes_written"], cell["longpath_mechanism"], extra))


# ------------------------------------------------------------------ runner
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--controls", action="store_true")
    ap.add_argument("--matrix", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--only", default=None)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    plan, cases, blind_doc = make_plan()
    if args.plan:
        n = {}
        for s in plan:
            n[s["group"]] = n.get(s["group"], 0) + 1
        print("planned cells by group:", json.dumps(n, sort_keys=True))
        print("planned_total=%d" % len(plan))
        for s in plan:
            print("  %-6s %-16s %-40s %s" % (s["group"], s["case_id"], cell_filename(s), s["entry"]))
        return 0

    env = env_block()
    spec_sha, rc = spec_sha256_from_blob()
    if rc != 0:
        print("FATAL spec blob read rc=%d" % rc)
        return 4
    ctx = {"spec_sha256": spec_sha, "bisect": {},
           "blocked_fix": "rebuild probe: \"%s\" build \"%s\" -c Release -o D:/sg-cs-scratch/build "
                          "(rebuild succeeded locally; rc recorded per cell)" % (DOTNET, os.path.join(REPO, "impl", "csharp", "SendGuardProbe.csproj"))}
    os.makedirs(RESULTS_DIR, exist_ok=True)

    want = []
    if args.all or args.controls:
        want.append("controls")
    if args.all or args.matrix:
        want += ["matrix"]
    if not want:
        print("nothing selected: use --plan / --controls / --matrix / --all")
        return 2

    def selected(s):
        if s["phase"] not in want:
            return False
        if args.only and args.only not in cell_filename(s) and args.only != s["group"]:
            return False
        return True

    # ---------------- controls: they verify the ruler, they are not data (gate.md s8)
    control_ok = None
    if "controls" in want:
        ctrl_cells = []
        for spec in [s for s in plan if selected(s)]:
            if spec["phase"] != "controls":
                continue
            cell, cdir = build_cell("controls", spec, cases, blind_doc, env, ctx)
            fails = evaluate_control(cell)
            cell["control_expectation_source"] = "evidence/S00-ctrl-baseline.md"
            cell["required_manifest_sha256"] = hashlib.sha256(
                open(REQUIRED_MANIFEST, "rb").read()).hexdigest()
            cell["control_expectation_fails"] = fails
            cell["control_pass"] = not fails
            cell["instrument_red"] = bool(fails)
            ctrl_cells.append((spec, cell, cdir, fails))
            print(report_line(cell_filename(spec), cell), flush=True)
            if fails:
                print("    CONTROL-MISMATCH %s" % "; ".join(fails), flush=True)

        red = [(s, c, f) for s, c, d, f in ctrl_cells if f]
        if red:
            # gate.md s8: re-run 3x to verify the instrument; every reading is printed as-is
            for spec, cell, cdir, fails in red:
                print("RE-RUN x3 %s (verifying the ruler, not the result)" % cell_filename(spec), flush=True)
                for i in range(3):
                    rcell, rc_dir = build_cell("controls", spec, cases, blind_doc, env, ctx)
                    rfails = evaluate_control(rcell)
                    rcell["control_expectation_fails"] = rfails
                    rcell["required_manifest_sha256"] = hashlib.sha256(
                        open(REQUIRED_MANIFEST, "rb").read()).hexdigest()
                    rcell["control_pass"] = not rfails
                    rcell["instrument_red"] = True
                    rcell["rerun_index"] = i + 1
                    rcell["rerun_of_dir"] = cdir
                    print("    rerun%d %s" % (i + 1, report_line(cell_filename(spec) + ".rerun%d" % (i + 1), rcell)), flush=True)
                    if not rfails:
                        print("    rerun%d GREEN -> first reading was the unstable one" % (i + 1), flush=True)
                    write_cell(rcell, dict(spec, sub="rerun%d" % (i + 1)))
                write_cell(cell, spec)
            print("INSTRUMENT-RED controls_red=%d/%d -> matrix not run" % (len(red), len(ctrl_cells)))
            return 5
        if ctrl_cells:
            control_ok = True
            stamp = {"green_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                     "dotnet": dotnet_version(), "spec_sha256": spec_sha,
                     "harness_version": HARNESS_VERSION,
                     "controls": {cell["case_id"]: cell_digest(cell) for _, cell, _, _ in ctrl_cells}}
            with io.open(CONTROL_STAMP, "w", encoding="utf-8", newline="\n") as f:
                json.dump(stamp, f, indent=2, sort_keys=True)
            for spec, cell, cdir, fails in ctrl_cells:
                write_cell(cell, spec)
            print("CONTROLS-GREEN %d/%d stamp=%s" % (len(ctrl_cells), len(ctrl_cells), CONTROL_STAMP))

    # ---------------- matrix refuses to run on an unverified ruler
    if "matrix" in want:
        if not os.path.isfile(CONTROL_STAMP):
            print("MATRIX-REFUSED reason=no green control stamp at %s (run --controls first)" % CONTROL_STAMP)
            return 6
        with io.open(CONTROL_STAMP, encoding="utf-8") as f:
            stamp = json.load(f)
        if stamp.get("spec_sha256") != spec_sha or stamp.get("dotnet") != dotnet_version():
            print("MATRIX-REFUSED reason=stale control stamp (spec or toolchain moved since it was signed)")
            return 6

    manifest = read_required()
    req_ids = required_identities(manifest)
    planned_ids = {identity_key(s): cell_filename(s) for s in plan}
    # cells on disk that this round's plan no longer produces are superseded, not deleted: the
    # harness never deletes anything (M19), it only names what it replaced so the cleanup is an
    # operator decision with a list in hand.
    stale = []
    for p in sorted(glob.glob(os.path.join(RESULTS_DIR, "*.json"))):
        if os.path.basename(p) not in planned_ids.values():
            raw = open(p, "rb").read()
            stale.append({"file": os.path.basename(p), "bytes": len(raw),
                          "sha256": hashlib.sha256(raw).hexdigest()})
    ctx["stale"] = stale

    written = []
    for spec in plan:
        if not selected(spec) or spec["phase"] == "controls":
            continue
        if args.limit and len(written) >= args.limit:
            break
        cell, cdir = build_cell(spec["phase"], spec, cases, blind_doc, env, ctx)
        cell["control_pass"] = True
        cell["control_stamp_ref"] = CONTROL_STAMP
        cell["required_manifest_sha256"] = hashlib.sha256(
            open(REQUIRED_MANIFEST, "rb").read()).hexdigest()
        if stale:
            cell["supersedes_candidates"] = "%d files listed in the run log; harness deletes nothing" % len(stale)
        if cell["create_result"] == "hang":
            cell["hang_note"] = "5s external timeout, per spec/gate.md s10"
        written.append((cell_filename(spec), cell))
        print(report_line(cell_filename(spec), cell), flush=True)
        write_cell(cell, spec)

    ids_now = {produced_identity(c) for _, c in written} | {
        produced_identity(json.loads(io.open(os.path.join(RESULTS_DIR, cell_filename(s)), encoding="utf-8").read()))
        for s in plan if s["phase"] == "controls"}
    missing = sorted(req_ids - ids_now)
    extra = sorted(ids_now - req_ids)
    print("cells_run=%d spec_sha256=%s dotnet=%s LongPathsEnabled=%s"
          % (len(written), spec_sha, dotnet_version(), env["LongPathsEnabled"]))
    print("required_ids=%d produced_ids=%d missing=%d extra=%d"
          % (len(req_ids), len(ids_now), len(missing), len(extra)))
    for k in missing[:10]:
        print("   MISSING %s" % k)
    for k in extra[:10]:
        print("   EXTRA %s" % k)
    print("stale_files_on_disk=%d (not deleted by this harness)" % len(stale))
    for s in stale[:60]:
        print("   STALE %s %d B %s" % (s["file"], s["bytes"], s["sha256"][:12]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
