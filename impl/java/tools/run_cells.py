#!/usr/bin/env python3
"""SENDGUARD java port cell runner (instrumentation, stdlib only).

Owns everything that is NOT a measurement: toolchain resolution, scratch dirs,
the external 5 s timeout, and the per-cell JSON files. Every filesystem
behaviour recorded here comes out of the JVM child (src/CellProbe.java); this
driver never touches a trap name itself.

Usage:
    python impl/java/tools/run_cells.py                  # whole matrix
    python impl/java/tools/run_cells.py --only T01,T04   # subset (same code path)
    python impl/java/tools/run_cells.py --dry            # plan only, no child process
Exit 0 = every planned (cell x entry) run reached a conclusion.
Exit 1 = at least one run blocked.  Exit 3 = plan or instrument broken.
"""
import argparse
import datetime
import hashlib
import io
import json
import os
import re
import subprocess

# the console on this host is cp936; a localized Windows error string must not be able to
# crash the runner while it is reporting a failure (the file faces are ASCII already)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
except Exception:
    pass
import sys
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(PORT))
BUILD = os.path.join(PORT, "build")
RESULTS_DIR = os.path.join(REPO, "results", "java.windows.x64")
SCRATCH_ROOT = "D:\\s\\"           # one parent dir outside the repo, never under D:\local-dir
FACTS_PATH = os.path.join(PORT, "tools", "run-facts.json")
OUT_DIR = [RESULTS_DIR]   # set from --out-dir in main; assemble reads a PAIRED cell from here
TIMEOUT_S = 5.0
HARNESS_VERSION = "sg-java-S02-r5-F2"
PAYLOAD_HEX_PINNED = "53454e4447554152442d43414e4f4e2d5041594c4f41442d32303236"   # rev6 control_samples, 28 bytes
PAYLOAD = bytes.fromhex(PAYLOAD_HEX_PINNED)   # its sha256 is the sealed S00 baseline value
PAD = "0123456789abcdef"

PRIMARY_ENTRY = "Files.write"
# F2 part 1: the second instrument of this port, published as its own cell per pinned length
# rung. It is a java.io call driven from the requested String, so it never passes through
# java.nio's path parser (impl/java/tools/ext-path-of-repro.txt is the reproduction).
IO_SPREAD_ENTRY = "FileOutputStream.write"
LENGTH_UNIT = "utf16_code_units"        # java.nio counts path/name length in UTF-16 code units
NAME_ENCODING = "hex_raw_bytes"         # the record carries the name as UTF-8 hex, the cases.yaml face
VERDICT_VIA = "win32"
VERDICT_VIA_EVIDENCE = (
    "the legality verdict is the answer of the Win32/NTFS layer reached through java.io "
    "(FileOutputStream over a raw extended-path string, which the JDK hands to CreateFileW); "
    "java.nio refuses that string at parse (recorded per cell as "
    "os_legality_probe.nio_accepts_ext_prefix=false), so no cmd, .NET or POSIX tool was asked")
REQ_SHA = [None]
SPREAD_SET = set()
SPREAD_ENTRIES = ["Files.createFile", "Files.newOutputStream", "Files.move",
                  "File.createNewFile", "FileOutputStream.write", "File.renameTo"]

# spec/FROZEN.md grid: G1 base13 x(244,245,246) G2 base120 x(137,138,139)
#                      G3 base13 x(254,255,256) G4 base200 x(254,255,256)
LEN_GRID = [("G1", 13, [244, 245, 246]), ("G2", 120, [137, 138, 139]),
            ("G3", 13, [254, 255, 256]), ("G4", 200, [254, 255, 256])]

RESERVED_RE = re.compile(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9]|CONIN\$|CONOUT\$)(\..*)?$", re.I)

# quoted from evidence/ctrl-baseline.md (T-CTRL-ASCII row); measured, not typed twice
BASELINE_SHA = "c9fe45b2fee8ea846f0cf4f2cacc2a891e7b082e7719923502d12a9813e21994"
assert re.fullmatch(r"[0-9a-f]{64}", BASELINE_SHA), "baseline hash face is not 64 hex chars"
assert hashlib.sha256(PAYLOAD).hexdigest() == BASELINE_SHA, \
    "the rev6 pinned payload does not hash to the sealed S00 baseline value"


def hx(s):
    return s.encode("utf-8").hex() if isinstance(s, str) else s.hex()


def stamp():
    return datetime.datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S.%f")


# ----------------------------------------------------------------- toolchain
def which_all(exe):
    out = []
    for d in os.environ.get("PATH", "").split(os.pathsep):
        if not d:
            continue
        p = os.path.join(d, exe)
        if os.path.isfile(p):
            out.append(p)
    return out


def probe_version(exe, args):
    try:
        r = subprocess.run([exe] + args, capture_output=True, timeout=30)
    except Exception as e:
        return {"exe": exe, "argv": [exe] + args, "rc": None, "status": type(e).__name__}
    so = r.stdout.decode("utf-8", "replace").strip()
    se = r.stderr.decode("utf-8", "replace").strip()
    text = so or se
    return {"exe": exe, "argv": [exe] + args, "rc": r.returncode,
            "status": "rc0-with-output" if (r.returncode == 0 and text) else
                      "rc0-NO-OUTPUT" if r.returncode == 0 else "nonzero-rc",
            "first_line": text.splitlines()[0] if text else "",
            "stdout": so, "stderr": se}


def resolve_toolchain():
    javas = which_all("java.exe") or which_all("java")
    javacs = which_all("javac.exe") or which_all("javac")
    f = {"JAVA_HOME_env": os.environ.get("JAVA_HOME"),
         "java_on_path": javas, "javac_on_path": javacs,
         "all_java_version_probes": [probe_version(p, ["-version"]) for p in javas],
         "all_javac_version_probes": [probe_version(p, ["-version"]) for p in javacs]}
    chosen = None
    for jc in javacs:
        jv = os.path.join(os.path.dirname(jc), "java.exe")
        if os.path.isfile(jv):
            chosen = (jc, jv)
            break
    if not chosen:
        f["status"] = "no-jdk-found"
        return f
    f["chosen_javac"], f["chosen_java"] = chosen
    f["chosen_javac_probe"] = probe_version(chosen[0], ["-version"])
    f["chosen_java_probe"] = probe_version(chosen[1], ["-version"])
    f["bare_path_java_is_chosen"] = bool(javas) and os.path.normcase(javas[0]) == os.path.normcase(chosen[1])
    f["JAVA_HOME_is_chosen_home"] = bool(os.environ.get("JAVA_HOME")) and \
        os.path.normcase(os.environ["JAVA_HOME"]) in os.path.normcase(chosen[1])
    f["status"] = "ok"
    return f


def local_env_facts():
    """Re-measured on this run, not copied from S00."""
    f = {}
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                           r"SYSTEM\CurrentControlSet\Control\FileSystem")
        v, _t = winreg.QueryValueEx(k, "LongPathsEnabled")
        f["LongPathsEnabled"] = v
        winreg.CloseKey(k)
    except Exception as e:
        f["LongPathsEnabled"] = None
        f["LongPathsEnabled_probe"] = "%s: %s" % (type(e).__name__, e)
    # second instrument for the same number: reg.exe as an argv list (no shell, so no
    # MSYS argument mangling) - a gate that has only one face is not a gate.
    rq = subprocess.run(["reg", "query",
                         r"HKLM\SYSTEM\CurrentControlSet\Control\FileSystem",
                         "/v", "LongPathsEnabled"], capture_output=True)
    rqt = rq.stdout.decode("cp936", "replace")
    mval = re.search(r"LongPathsEnabled\s+REG_DWORD\s+0x([0-9a-fA-F]+)", rqt)
    f["LongPathsEnabled_regexe"] = (int(mval.group(1), 16) if mval else None)
    f["LongPathsEnabled_regexe_rc"] = rq.returncode
    f["LongPathsEnabled_regexe_excerpt"] = " | ".join(
        x.strip() for x in rqt.splitlines() if x.strip())[:200]
    f["LongPathsEnabled_two_faces_agree"] = (
        f.get("LongPathsEnabled") == f["LongPathsEnabled_regexe"]
        if f["LongPathsEnabled_regexe"] is not None else None)
    r = subprocess.run(["fsutil", "8dot3name", "query", "D:\\"], capture_output=True)
    txt = r.stdout.decode("cp936", "replace")
    states = re.findall(r"(\d+)\s*\(8dot3", txt)
    f["dot3name_rc"] = r.returncode
    f["dot3name_volume_state_number"] = int(states[0]) if states else None
    f["dot3name_generation"] = {0: "enabled", 1: "disabled"}.get(
        int(states[0]) if states else -1, "unknown")
    f["dot3name_state_meaning"] = "fsutil prints <n> (8dot3 name creation ...); 0=enabled 1=disabled"
    f["dot3name_verbatim_excerpt"] = txt.strip().replace("\r\n", " | ")[:240]
    f["fsutil_decoded_as"] = "cp936 (console code page recorded in evidence/freeze/env-facts-windows-local.json)"
    f["max_component"] = 255
    f["max_component_basis"] = "NTFS; GetVolumeInformationW measured 255 at S00 (env-facts-windows-local.json), same host and same D: volume"
    f["unicode_version"] = "not-obtainable-here"
    f["unicode_version_note"] = "java does not expose a Unicode data version through a version command; not probed by an in-language program in this round"
    return f


# -------------------------------------------------------------- spec loading
def load_cases(path):
    text = io.open(path, encoding="utf-8").read()
    NL = chr(10)
    # only the frozen trap section: control_samples also uses "- id:", and reading it as a
    # trap would invent five cells that are not in any list
    tail = text.split(NL + "cases:" + NL, 1)
    body = tail[1] if len(tail) > 1 else text
    cases = []
    for b in re.split(r"(?m)^  - id: ", body)[1:]:
        head = b.splitlines()[0].strip()
        sh = re.search(r'(?m)^    sample_hex: "?([^"\n]+?)"?\s*(?:#.*)?$', b)
        lst = re.findall(r'(?m)^      - "([0-9a-fA-F]+)"', b)
        cat = re.search(r"(?m)^    category: (\S+)", b)
        loc = re.search(r"(?m)^    locale: (\S+)", b)
        app = re.search(r"(?m)^    applicable: \[([^\]]*)\]", b)
        cases.append({
            "id": head,
            "sample_hex": sh.group(1).strip() if sh else None,
            "sample_hex_list": lst or None,
            "category": cat.group(1) if cat else "unknown",
            "locale": loc.group(1) if loc else "en-US",
            "applicable": [x.strip() for x in (app.group(1).split(",") if app else [])],
        })
    api = {}
    mam = re.search(r"(?m)^api_entry:\n((?:  \w+:.*\n)+)", text)
    if mam:
        for line in mam.group(1).splitlines():
            k, v = line.split(":", 1)
            api[k.strip()] = [x.strip() for x in v.strip().strip("[]").split(",")]
    ctrl_ids = re.findall(r"(?m)^  - (T-CTRL-[A-Z-]+)", text)
    cs = {}
    NL = chr(10)   # newline without depending on an escape surviving a copy
    blk = re.search("(?m)^control_samples:" + NL + "(.*?)(?:" + NL + "# |" + NL + "cases:)",
                    text, re.DOTALL)
    for b in re.split(r"(?m)^  - id: ", blk.group(1) if blk else "")[1:]:
        cid = b.splitlines()[0].strip()
        sh = re.search(r'sample_hex: "([0-9a-f]+)"', b)
        ph = re.search(r'payload_hex: "([0-9a-f]+)"', b)
        cs[cid] = {"sample_hex": sh.group(1) if sh else None,
                   "payload_hex": ph.group(1) if ph else None}
    return cases, api, ctrl_ids, cs


def parse_len_fill(path):
    """rev7: the length family finally has bytes instead of prose."""
    text = io.open(path, encoding="utf-8").read()
    NL = chr(10)
    m = re.search("(?m)^len_fill:" + NL + "((?:  .*?" + NL + ")+)", text)
    if not m:
        return None
    blk = m.group(1)
    unit = re.search(r'unit_hex: "([0-9a-f]+)"', blk)
    applies = re.search(r"applies_to: \[([^\]]*)\]", blk)
    rule = re.search(r'rule: "([^"]+)"', blk)
    nsr = re.search(r'name_source_rule: "([^"]+)"', blk)
    return {"unit_hex": unit.group(1) if unit else None,
            "applies_to": [x.strip() for x in (applies.group(1).split(",") if applies else [])],
            "rule": rule.group(1) if rule else None,
            "name_source_rule": nsr.group(1) if nsr else None}


def spec_sha_from_blob(repo, rel):
    r = subprocess.run(["git", "-C", repo, "cat-file", "blob", "HEAD:" + rel], capture_output=True)
    if r.returncode != 0:
        return None, r.returncode, r.stderr.decode("utf-8", "replace").strip()
    return hashlib.sha256(r.stdout).hexdigest(), 0, len(r.stdout)


# ------------------------------------------------------------------- scratch
def padded_name(n):
    return (PAD * ((n // len(PAD)) + 1))[:n]


def make_scratch(base_len=None):
    uid = uuid.uuid4().hex[:6]
    prefix = SCRATCH_ROOT + uid + "\\"
    if base_len is None:
        d = prefix + uuid.uuid4().hex[:8]
    else:
        need = base_len - len(prefix)
        if need < 1:
            raise RuntimeError("base_len %d unreachable with prefix len %d" % (base_len, len(prefix)))
        d = prefix + padded_name(need)
    d = d.rstrip("\\")
    if len(d) != (base_len if base_len else len(d)):
        raise RuntimeError("scratch length drift: want %s got %d" % (base_len, len(d)))
    os.makedirs(d, exist_ok=False)
    if os.listdir(d):
        raise RuntimeError("fresh scratch dir is not empty: " + d)
    return d


# --------------------------------------------------------------------- child
def run_child(tc, scratch, entry, members_hex, grades, out_path, zip_leg, ext="on", sweep=None,
              mechanism=False, extra_args=None, path_form=None, fill_unit=None):
    argv = [tc["chosen_java"], "-cp", BUILD, "CellProbe",
            "--entry", entry, "--scratch", scratch, "--payload", hx(PAYLOAD),
            "--out", out_path, "--extended", ext]
    if zip_leg:
        argv += ["--zip", "on"]
    if sweep:
        argv += ["--sweep", ",".join(str(g) for g in sweep)]
    if mechanism:
        argv += ["--mechanism", "on"]
    if path_form and path_form != "plain":
        argv += ["--path-form", path_form]
    if fill_unit:
        argv += ["--fill-unit-hex", fill_unit]
    if extra_args:
        argv += list(extra_args)
    if grades:
        argv += ["--grades", ",".join(str(g) for g in grades)]
    else:
        argv += ["--members", ",".join(members_hex)]
    started = stamp()
    CHILD_RUNS[0] += 1
    t0 = time.monotonic()
    timed_out = False
    try:
        r = subprocess.run(argv, capture_output=True, timeout=TIMEOUT_S)
        rc, so, se = r.returncode, r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace")
    except subprocess.TimeoutExpired as e:
        timed_out = True
        rc = e.returncode
        so = (e.stdout or b"").decode("utf-8", "replace")
        se = (e.stderr or b"").decode("utf-8", "replace")
    elapsed = int(round((time.monotonic() - t0) * 1000))
    doc = None
    read_err = None
    if os.path.isfile(out_path):
        try:
            doc = json.loads(io.open(out_path, encoding="utf-8").read())
        except Exception as e:
            read_err = "%s: %s" % (type(e).__name__, e)
    return {"argv": argv, "rc": rc, "stdout": so.strip(), "stderr": se.strip(),
            "timed_out": timed_out, "started_at": started,
            "elapsed_ms": max(elapsed, 0), "doc": doc, "out_path": out_path,
            "result_file_present": os.path.isfile(out_path), "read_err": read_err}


# ---------------------------------------------------------------- cell plan
def rev3_grid(base):
    """Grid for a required length rung: the linear-model hit (259-base-1) at +/-1, and the
    component-wall candidates 254/255/256. The pre-rev3 tiers bracketed only one candidate."""
    hit = 259 - base - 1
    return sorted(set([hit - 1, hit, hit + 1, 254, 255, 256]))


def build_plan(cases, api, ctrl_ids, blind_entries, java_entries, req, csamples, len_fill):
    """One plan row = one set of child processes (case x entry, all members sequential in one
    fresh directory). A row may EMIT several cell files: rev3 identities are per member."""
    plan = []
    required_ids = set()
    for rc in req["required_cells"]:
        required_ids.add((rc["case_group"], rc["case_id"], rc["sub_identity"].get("base_len")))
    req_tapi = {(t["api_entry"]): t for t in req["tapi_cells_per_language"] if t["language"] == "java"}
    by_id = {c["id"]: c for c in cases}

    for c in cases:
        if c["id"] in ("T17", "T18"):
            rungs = sorted({rc["sub_identity"]["base_len"] for rc in req["required_cells"]
                            if rc["case_group"] == "len" and rc["case_id"] == c["id"]})
            unit = (len_fill or {}).get("unit_hex") or "61"
            for base in rungs:
                # rev7: the component this cell passes is base_len units of the pinned filler unit,
                # and name_source is the hex of exactly that string - not a label, not prose
                pinned = bytes.fromhex(unit) * base
                grades = [base] + [g for g in rev3_grid(base) if g != base]
                for form in ("plain", "extended"):
                    sub_id = {"base_len": base, "path_form": form}
                    plan.append({
                        "kind": "len", "group": "len", "case_id": c["id"],
                        "sub_parts": ["base_len-%d" % base, form], "sub": None,
                        "tier": None, "base_len": base, "grades": grades, "sweep": None,
                        "path_form": form,
                        "mechanism": (c["id"] == "T17" and base == min(rungs) and form == "plain"),
                        "members_hex": None, "name_source": pinned.hex(),
                        "category": c["category"], "locale": c["locale"],
                        "applicable": c["applicable"], "fill_unit": unit,
                        "headline": "pinned", "pinned_component_bytes": len(pinned),
                        "entries": [PRIMARY_ENTRY], "zip": False, "grid_rule": "rev7",
                        "emits": [{"case_id": c["id"], "group": "len",
                                   "sub_parts": ["base_len-%d" % base, form],
                                   "member_index": None, "sub_identity": sub_id,
                                   "path_form": form, "extra": False},
                                   # the rev5 filename (base_len only) is re-emitted from this same
                                   # run, marked extra, so no stale cell is left on disk
                                  {"case_id": c["id"], "group": "len",
                                   "sub_parts": ["base_len-%d" % base], "member_index": None,
                                   "sub_identity": {"base_len": base}, "path_form": form,
                                   "extra": True,
                                   "extra_reason": "rev5 rung identity without path_form; superseded "
                                                   "by the rev6 (base_len, path_form) pair"}
                                  ] if form == "plain" else [
                                  {"case_id": c["id"], "group": "len",
                                   "sub_parts": ["base_len-%d" % base, form],
                                   "member_index": None, "sub_identity": sub_id,
                                   "path_form": form, "extra": False}]})
                    # F2 part 1: the same rung measured by this port's second instrument, as its
                    # own extra cell. `builder` is a dimension spec/cell-identity.md section 1
                    # already declares, and its value is the entry this cell called; the arm in
                    # impl/java/tools/selfcheck.py requires builder == api_entry, so the filename
                    # cannot lie about which instrument answered.
                    req_fn = "len__%s__base_len-%d__%s.json" % (c["id"], base, form)
                    plan.append({
                        "kind": "len", "group": "len", "case_id": c["id"], "row_tag": "io-spread",
                        "sub_parts": ["base_len-%d" % base, form, "builder-" + IO_SPREAD_ENTRY],
                        "sub": None, "tier": None, "base_len": base, "grades": grades, "sweep": None,
                        "path_form": form, "mechanism": False, "members_hex": None,
                        "name_source": pinned.hex(), "category": c["category"],
                        "locale": c["locale"], "applicable": c["applicable"], "fill_unit": unit,
                        "headline": "pinned", "pinned_component_bytes": len(pinned),
                        "entries": [IO_SPREAD_ENTRY], "zip": False, "grid_rule": "F2-part1",
                        "paired_required_cell": req_fn,
                        "emits": [{"case_id": c["id"], "group": "len",
                                   "sub_parts": ["base_len-%d" % base, form,
                                                 "builder-" + IO_SPREAD_ENTRY],
                                   "member_index": None,
                                   "sub_identity": dict(list(sub_id.items()) +
                                                        [("builder", IO_SPREAD_ENTRY)]),
                                   "path_form": form, "extra": True,
                                   "paired_required_cell": req_fn,
                                   "extra_reason":
                                       "F2 part 1: the java.io leg of this pinned rung published "
                                       "as its own cell on the contract's own `builder` dimension. "
                                       "Extra because api_entry is not part of the equality key "
                                       "(spec/cell-identity.md section 1), so it is published and "
                                       "never compared; the required Files.write answer for the same "
                                       "rung is the paired cell " + req_fn}]})
            # the pre-rev3 FROZEN.md tier cells stay on the disk, marked extra
            for tier, base, grades in LEN_GRID:
                sweep = None
                if c["id"] == "T17" and tier == "G1":
                    sweep = list(range(247, 254))
                elif c["id"] == "T18" and tier == "G3":
                    sweep = [253, 254, 255, 256, 257]
                plan.append({
                    "kind": "len", "group": "len", "case_id": c["id"], "sub_parts": [tier],
                    "sub": None, "tier": tier, "base_len": base, "grades": grades, "sweep": sweep,
                    "path_form": "plain", "headline": "largest", "fill_unit": None,
                    "mechanism": False, "members_hex": None,
                    "name_source": hx(padded_name(grades[-1])), "category": c["category"],
                    "locale": c["locale"], "applicable": c["applicable"],
                    "entries": [PRIMARY_ENTRY], "zip": False,
                    "emits": [{"case_id": c["id"], "group": "len", "sub_parts": [tier],
                               "member_index": None, "base_len": base, "path_form": "plain",
                               "extra": True,
                               "extra_reason": "FROZEN.md G1-G4 tier identity, kept as extra; the "
                                               "required rungs are the base_len x path_form grid"}]})
            continue

        hexes = c["sample_hex_list"] or None
        if hexes is None and c["sample_hex"] and re.fullmatch(r"[0-9a-f]+", c["sample_hex"]):
            hexes = [c["sample_hex"]]
        if hexes is None:
            plan.append({"kind": "trap", "group": "trap", "case_id": c["id"], "sub": None,
                         "members_hex": [], "name_source": c["sample_hex"],
                         "category": c["category"], "locale": c["locale"],
                         "applicable": c["applicable"], "entries": [PRIMARY_ENTRY],
                         "zip": False, "plan_defect": "no UTF-8 hex sample for this id",
                         "emits": [{"case_id": c["id"], "group": "trap", "sub": None,
                                    "member_index": 0, "extra": True,
                                    "extra_reason": "no hex sample, nothing measurable"}]})
            continue
        emits = []
        for i, h in enumerate(hexes):
            rid = ("%s-m%d" % (c["id"], i + 1)) if len(hexes) > 1 else c["id"]
            in_req = ("trap", rid, None) in required_ids
            emits.append({"case_id": rid, "group": "trap", "sub": None, "member_index": i,
                          "extra": not in_req,
                          "extra_reason": None if in_req else
                          "member cell not present in spec/cells-required.json"})
        if len(hexes) > 1:
            emits.append({"case_id": c["id"], "group": "trap", "sub": None, "member_index": 0,
                          "aggregate": True, "extra": True,
                          "extra_reason": "whole-case cell (all members inside); rev3 requires one "
                                          "cell per member, so this identity is kept and marked"})
        plan.append({"kind": "trap", "group": "trap", "case_id": c["id"], "sub": None,
                     "members_hex": hexes, "name_source": ",".join(hexes),
                     "category": c["category"], "locale": c["locale"],
                     "applicable": c["applicable"],
                     "entries": [PRIMARY_ENTRY] + SPREAD_ENTRIES,
                     "zip": c["category"] == "zip_roundtrip",
                     "reserved_family": bool(RESERVED_RE.match(
                         bytes.fromhex(hexes[0]).decode("utf-8"))),
                     "emits": emits})

    for cid in ctrl_ids:
        # rev6 pins the control input bytes: the name and the payload come from
        # spec/cases.yaml control_samples, not from what this port happened to pick.
        pin = csamples.get(cid) or {}
        if not pin.get("sample_hex"):
            plan.append({"kind": "ctrl", "group": "ctrl", "case_id": cid, "sub": None,
                         "members_hex": [], "name_source": None, "category": "unknown",
                         "locale": "en-US", "applicable": ["windows", "macos", "ubuntu"],
                         "entries": [PRIMARY_ENTRY], "zip": False,
                         "plan_defect": "no pinned control_sample for this id",
                         "emits": [{"case_id": cid, "group": "ctrl", "sub": None,
                                    "member_index": 0, "extra": True,
                                    "extra_reason": "no pinned sample bytes in the spec"}]})
            continue
        if pin.get("payload_hex") and pin["payload_hex"] != PAYLOAD_HEX_PINNED:
            print("PLAN-DEFECT %s pins a different payload than the other controls" % cid)
            return []
        hexes = [pin["sample_hex"]]
        note = ("input pinned by spec/cases.yaml control_samples at rev6: sample_hex "
                "%s and the 28-byte payload whose sha256 is %s" % (pin["sample_hex"], BASELINE_SHA))
        plan.append({"kind": "canon" if cid == "T-CTRL-CANON" else "ctrl",
                     "group": "ctrl", "case_id": cid, "sub": None,
                     "members_hex": hexes, "name_source": ",".join(hexes),
                     # control cells verify the ruler; the frozen spec assigns a category
                     # only to the 20 traps, so no mechanism is claimed here
                     "category": "unknown", "locale": "en-US",
                     "applicable": ["windows", "macos", "ubuntu"],
                     "entries": [PRIMARY_ENTRY] + SPREAD_ENTRIES, "zip": False,
                     "construction_note": note, "pinned_sample_hex": pin["sample_hex"],
                     "emits": [{"case_id": cid, "group": "ctrl", "sub": None, "member_index": 0,
                                "extra": ("ctrl", cid, None) not in required_ids}]})

    for e in blind_entries:
        bid = "B%d" % e["blind_id"]
        legacy = "BLIND-%d" % e["blind_id"]
        plan.append({"kind": "blind", "group": "blind", "case_id": bid, "sub": None,
                     "members_hex": [e["name_utf8_hex"]],
                     "name_source": e["name_utf8_hex"], "category": "unknown",
                     "locale": "en-US", "applicable": ["windows", "macos", "ubuntu"],
                     "entries": [PRIMARY_ENTRY], "zip": False, "blind_id": e["blind_id"],
                     "emits": [{"case_id": bid, "group": "blind", "sub": None, "member_index": 0,
                                "extra": ("blind", bid, None) not in required_ids,
                                "blind_id": e["blind_id"]},
                               {"case_id": legacy, "group": "blind", "sub": None, "member_index": 0,
                                "extra": True, "blind_id": e["blind_id"],
                                "extra_reason": "this port's pre-rev6 blind id; rev6 asks for %s "
                                                "and the gate folds the spelling, so the cell is "
                                                "kept, marked and excluded" % bid}]})

    probes = [hx("report-2026.txt"), hx("CON.txt"), hx("trail."), hx("a<b.txt")]
    for i, ent in enumerate(java_entries, 1):
        is_req = ent in req_tapi
        plan.append({"kind": "tapi", "group": "tapi", "case_id": "T-API", "sub": ent,
                     "members_hex": probes, "name_source": ",".join(probes),
                     "category": "unknown", "locale": "en-US",
                     "applicable": ["windows", "macos", "ubuntu"],
                     "entries": [ent], "zip": False, "tapi_entry_under_test": ent,
                     "construction_note": "instrument self-check: one pinned entry against 4 "
                                          "known-behaving names",
                     "emits": [{"case_id": "T-API", "group": "tapi", "sub": ent,
                                "member_index": 0, "aggregate": True, "extra": not is_req},
                               {"case_id": "T-API-%d" % i, "group": "tapi", "sub": None,
                                "member_index": 0, "aggregate": True, "extra": True,
                                "extra_reason": "pre-rev3 per-entry case_id; rev3 fixes the id as "
                                                "T-API with api_entry carrying the distinction"}]})
    return plan


NULLABLE_BY_SCHEMA = ("bytes_written", "bytes_on_disk")


def strip_unmeasured(rec):
    """A field the schema types as string/boolean may not carry null: absence = not measured."""
    return {k: v for k, v in rec.items() if v is not None or k in NULLABLE_BY_SCHEMA}


def rev4_regime(mech, max_ok_component, base_len):
    """spec/gate.md 5 (rev4): the regime is keyed by longpath_mechanism, not by path_form."""
    if mech in ("manifest", "prefix_rewrite"):
        if max_ok_component is not None and max_ok_component == 255:
            return "model-1 component ceiling (rev4 gate.md 5): max_component == volume max_component"
        return "model-1 expected but ceiling not at 255: reported as unresolved"
    if mech == "none":
        if max_ok_component is not None and max_ok_component == 259 - (base_len or 0) - 1:
            return "model-2 linear 259-base-1 (rev4 gate.md 5)"
        return ("unresolved: mechanism reads as none yet the last ok component is %s, not "
                "259-base-1=%s (rev4 gate.md 5 says report this, do not bucket it)"
                % (max_ok_component, 259 - (base_len or 0) - 1))
    return ("unresolved: longpath_mechanism=%s, so rev4 gate.md 5 offers no regime for this port; "
            "the final-component leg answered %s" % (mech, MECH2[0].get("combined_verdict")))


def cell_filename(rec, emit):
    e = emit or {}
    parts = [rec["case_group"], rec["case_id"]] + list(e.get("sub_parts") or
                                                     ([e["sub"]] if e.get("sub") else []))
    return "__".join(parts) + ".json"


# --------------------------------------------------------------- attribution
def attribute(primary, spread, ext, entry_count):
    """One word per cell, and the basis sentence must be the evidence for THAT word.

    R1 entries of this port disagree                  -> L2 (switching stdlib entry removes it)
    R2 the language refused the path string itself,
       identically for every entry                   -> L3 (the OS may refuse the same name too;
                                                          that is third evidence, not a reclassify)
    R3 the call reached the filesystem                -> L1 (OS / environment fact on this machine)
    """
    keys = ("create_result", "error_stage")
    tuples = {tuple((s.get("record") or {}).get(k) for k in keys) for s in spread
              if s.get("record") is not None}
    tuples.add(tuple(primary.get(k) for k in keys))
    if len(tuples) > 1:
        return "L2", ("R1: %d entries of this port answered %d distinct behaviour tuples for this "
                      "name %s, so switching a stdlib entry removes the divergence (a tuple is "
                      "create_result/error_stage; a payload-less entry such as Files.createFile "
                      "is an API shape, not a divergence)"
                      % (entry_count, len(tuples), sorted(tuples)))
    if primary["create_result"] == "err_at_parse":
        return "L3", ("R2: java.nio rejected the path string before any syscall and every entry of "
                      "this port agrees; third evidence: the OS-level leg answered %s, so the name "
                      "verdict is not language-only but the refusal STAGE is"
                      % ext.get("create_result"))
    return "L1", ("R3: nothing refused at parse and the call reached the filesystem "
                  "(OS leg create_result=%s, landed=%s), so the behaviour is an "
                  "environment/OS fact for this port on this machine"
                  % (ext.get("create_result"), ext.get("landed_by_enumeration")))


def paired_rung_claim(plan, head, spec_sha):
    """F2 part 1. This row ran exactly ONE entry, so it may not say "every entry of this port
    agrees" - that claim needs evidence about the other entries, and here there is none in the row.
    The paired required cell for the same rung IS published, so read it and describe the agreement
    or disagreement as what was observed, naming both files."""
    fn = plan.get("paired_required_cell")
    out = {"paired_cell": fn, "paired_cell_read": False, "keys_compared": ["create_result",
                                                                           "error_stage"]}
    if not fn:
        out["paired_cell_read_error"] = "the plan row names no paired cell"
        return None, None, out
    path = os.path.join(OUT_DIR[0], fn)
    try:
        d = json.loads(io.open(path, encoding="utf-8").read())
    except Exception as e:
        out["paired_cell_read_error"] = "%s: %s" % (type(e).__name__, e)
        return None, None, out
    out["paired_cell_read"] = True
    out["paired_cell_api_entry"] = d.get("api_entry")
    out["paired_cell_spec_sha256_matches_this_run"] = (d.get("spec_sha256") == spec_sha)
    out["paired_cell_harness_version"] = d.get("harness_version")
    a = tuple(d.get(k) for k in out["keys_compared"])
    b = tuple(head.get(k) for k in out["keys_compared"])
    out["paired_answer"] = list(a)
    out["this_answer"] = list(b)
    if a != b:
        return "L2", ("R1 across two published cells of this port: for this same rung the paired %s "
                      "cell (entry %s) answered %s/%s and this cell (entry %s) answered %s/%s, so "
                      "switching a stdlib entry of the SAME language removes the difference - an "
                      "L2 fact about java on this machine, not a Windows fact"
                      % (fn, d.get("api_entry"), a[0], a[1], plan["entries"][0], b[0], b[1])), out
    if a[0] == "err_at_parse":
        return "L3", ("R2: both entries of this port that were asked refuse the requested string at "
                      "parse, the paired %s cell at %s/%s and this cell at %s/%s, so no stdlib entry "
                      "of this language removes it - core path-model behaviour"
                      % (fn, a[0], a[1], b[0], b[1])), out
    return "L1", ("R3: both entries reached the filesystem and answered the same (%s/%s in the "
                  "paired %s cell, %s/%s here), so the answer is an environment/OS fact on this "
                  "machine" % (a[0], a[1], fn, b[0], b[1])), out


def assemble(tc, plan, runs, spec_sha, env, canon_extra=None, emit=None):
    emit = emit or {"case_id": plan["case_id"], "group": plan["group"], "sub": plan.get("sub"),
                    "member_index": 0, "extra": False}
    prim = runs.get(plan["entries"][0])
    entry_under_test = plan["entries"][0]
    mi = emit.get("member_index")
    sub_id = dict(emit.get("sub_identity") if emit.get("sub_identity") is not None
                  else ({} if emit.get("base_len") is None else {"base_len": emit["base_len"]}))
    form = emit.get("path_form") or "plain"
    if mi is not None and not emit.get("aggregate") and plan.get("members_hex"):
        name_source = plan["members_hex"][mi]
    else:
        name_source = plan["name_source"]
    rec = {
        "format_version": 1,
        "case_id": emit["case_id"],
        "case_group": emit["group"],
        "sub_identity": sub_id,
        "language": "java",
        "os": "windows",
        "os_version": "10.0.19041",
        "arch": "x64",
        "locale": plan.get("locale", "en-US"),
        "api_entry": entry_under_test,
        "attempt": 1,
        "name_source": name_source,
        # rev3 split: name_encoding describes how THIS RECORD encodes the name bytes,
        # length_unit describes what a length was counted in. java.nio counts UTF-16 units.
        "name_encoding": NAME_ENCODING,
        "length_unit": LENGTH_UNIT,
        "verdict_via": VERDICT_VIA,
        "verdict_via_evidence": VERDICT_VIA_EVIDENCE,
        "path_form": form,
        "run_status": "ok",
        "longpath_mechanism": "none",
        "harness_version": HARNESS_VERSION,
        "implementation_id": "java-port",
        "started_at": prim["started_at"],
        "elapsed_ms": prim["elapsed_ms"],
        "spec_sha256": spec_sha,
        "required_cells_sha256": REQ_SHA[0],
        "env": env,
        "toolchain": {"javac": tc.get("chosen_javac"), "java": tc.get("chosen_java"),
                      "javac_version": (tc.get("chosen_javac_probe") or {}).get("first_line"),
                      "java_version": (tc.get("chosen_java_probe") or {}).get("first_line")},
    }
    doc = prim["doc"]
    if doc is None:
        rec.update({
            "create_result": "hang" if prim["timed_out"] else "err_at_syscall",
            "error_stage": "tool",
            "error_code": "child rc=%s" % prim["rc"],
            "error_message": (prim["stderr"] or prim["stdout"] or
                              "no result document at --out path" + (" | " + prim["read_err"] if prim["read_err"] else ""))[:700],
            "read_result": "hang" if prim["timed_out"] else "not_applicable",
            "read_attempted": False,
            "read_skipped_reason": "the child produced no result document, so nothing was read",
            "os_legality_verdict": "unknown",
            "verdict_via": "none",
            "verdict_via_evidence": "the child produced no document, so no tool was asked about "
                                    "legality in this cell",
            "mechanism_class": plan.get("category", "unknown"),
            "attribution_layer": "L1",
            "bytes_written": None, "bytes_on_disk": None,
            "name_landed_as": None, "name_mutated": None, "roundtrip_ok": False,
            "enum_to_stat_agrees": None, "phantom": None, "len_triple": None,
            "deps_direct": 0, "deps_total": 0,
            "instrument_red": False, "control_pass": None,
            "blocked": True,
            "run_status": "blocked",
            "blocked_reason": "child timed out (5 s external limit)" if prim["timed_out"]
                              else "child produced no result document",
            "blocked_command": " ".join(prim["argv"]),
            "blocked_exit_code": "timeout-killed" if prim["timed_out"] else str(prim["rc"]),
            "attempted_fix": "pre-compiled the probe once and re-ran the child with -Xshare:auto; "
                             "second failure is reported as blocked, never substituted with another entry",
            "members": [], "entry_spread": [],
            "scratch": None, "cleanup_failed": True,
        })
        rec["child_rc"] = prim["rc"]
        rec["child_timed_out"] = prim["timed_out"]
        return rec

    members = doc["members"]
    if plan["kind"] == "len":
        head = members[0] if plan.get("headline") == "pinned" else members[-1]
        rec["headline_rule"] = (
            "the component of exactly base_len units of the pinned filler unit IS the cell; the "
            "other grid points are bracket evidence, not the cell"
            if plan.get("headline") == "pinned" else
            "largest grid point describes this tier cell")
        rec["members"] = members
        rec["members_observed"] = len(members)
        rec["tier"] = plan["tier"]
        rec["base_len"] = plan["base_len"]
        rec["base_len_actual"] = doc["scratch_len"]
        rec["grid_name_lens"] = plan["grades"]
        rec["pinned_component_units"] = plan["base_len"] if plan.get("headline") == "pinned" else None
        rec["breakpoint_rule"] = ("top-level fields describe the largest grid point; "
                                  "every grade is kept in grades[]")
        rec["grades"] = [{k: m.get(k) for k in ("label", "name_utf16_units", "name_utf8_bytes",
                                                 "total_path_len_plain", "create_result",
                                                 "error_stage", "error_class", "bytes_written",
                                                 "bytes_on_disk_dir_view", "same_name_hits")}
                         for m in members]
        sweep = doc.get("sweep") or []
        if sweep:
            rec["supplementary_sweep"] = [{k: mm.get(k) for k in (
                "label", "name_utf16_units", "total_path_len_plain", "create_result",
                "error_stage", "error_class", "same_name_hits")} for mm in sweep]
            rec["supplementary_sweep_note"] = ("points outside the frozen G1-G4 grid, kept separate "
                                               "so the frozen denominator stays 4 tiers x 3 points")
        pts = [dict(label=mm.get("label"), name_len=mm.get("name_utf16_units"),
                    total=mm.get("total_path_len_plain"),
                    plain=mm.get("create_result"),
                    extended=(mm.get("extended_probe") or {}).get("create_result"),
                    frozen=str(mm.get("label", "")).startswith("grade:")) for mm in members + sweep]
        rec["points"] = pts
        ok_plain = [q["total"] for q in pts if q["plain"] == "ok"]
        fail_plain = [q["total"] for q in pts if q["plain"] not in ("ok", None)]
        ok_ext = [q["total"] for q in pts if q["extended"] == "ok"]
        fail_ext = [q["total"] for q in pts if q["extended"] not in ("ok", None)]
        rec["measured_plain_wall"] = {"max_total_len_observed_ok": max(ok_plain) if ok_plain else None,
                                      "min_total_len_observed_fail": min(fail_plain) if fail_plain else None,
                                      "linear_model_prediction_259": "259-base-1 name units => total 259"}
        rec["measured_extended_wall"] = {"max_total_len_observed_ok": max(ok_ext) if ok_ext else None,
                                         "min_total_len_observed_fail": min(fail_ext) if fail_ext else None,
                                         "instrument": "java.io.File with the extended-prefix "
                                                       "string (NIO rejects that string)"}
        rec["longpath_mechanism_extended_leg"] = "prefix_rewrite"
    else:
        idx = 0 if mi is None else mi
        if idx >= len(members):
            idx = 0
        head = members[idx]
        if emit.get("aggregate"):
            rec["members"] = members
            rec["members_observed"] = len(members)
            rec["aggregate_cell_of_members"] = [m.get("name_hex") for m in members]
        else:
            rec["members"] = [head]
            rec["members_observed"] = 1
            rec["member_index_in_case"] = idx
            rec["sibling_members_in_same_directory"] = [
                {"name_hex": m.get("name_hex"), "same_name_hits": m.get("same_name_hits")}
                for j, m in enumerate(members) if j != idx]
            rec["coexistence_note"] = (
                "members of one frozen case are created sequentially in the same fresh directory, "
                "because T09's spec_source is 'NFC/NFD coexistence in one directory'; the landed "
                "array of this member shows what that directory held")

    spread = []
    for e in SPREAD_ENTRIES:
        r = runs.get(e)
        if r is None or e == plan["entries"][0]:
            continue
        if r["doc"] is None or not r["doc"].get("members"):
            spread.append({"api_entry": e, "blocked": True,
                           "blocked_exit_code": r["rc"], "blocked_timed_out": r["timed_out"],
                           "create_result": "hang" if r["timed_out"] else None,
                           "record": None})
            continue
        sidx = -1 if plan["kind"] == "len" else (0 if mi is None else mi)
        mm = r["doc"]["members"][sidx] if len(r["doc"]["members"]) > max(sidx, 0) else None
        if mm is None:
            continue
        sx = mm.get("extended_probe") or {}
        spread.append({"api_entry": e, "blocked": False,
                       "timed_out": r["timed_out"],
                       "scratch_len": r["doc"]["scratch_len"],
                       "record": dict(
                           {k: mm.get(k) for k in (
                               "create_result", "error_stage", "error_class", "error_message",
                               "bytes_written", "bytes_on_disk", "bytes_on_disk_dir_view",
                               "read_result", "read_attempted", "read_skipped_reason", "roundtrip_ok", "same_name_hits",
                               "case_variant_hits", "norm_variant_hits", "name_landed_as",
                               "name_mutated", "phantom", "total_path_len_plain")},
                           extended_create_result=sx.get("create_result"),
                           extended_landed_by_enumeration=sx.get("landed_by_enumeration"),
                           extended_os_legality_verdict=sx.get("os_legality_verdict"))})

    ext = head.get("extended_probe") or {}
    legality = ext.get("os_legality_verdict", "unknown")
    rec.update({
        "create_result": head["create_result"],
        "error_stage": head["error_stage"],
        "error_class": head.get("error_class"),
        "error_message": head.get("error_message"),
        "bytes_written": head.get("bytes_written"),
        "bytes_on_disk": head.get("bytes_on_disk"),
        "bytes_on_disk_dir_view": head.get("bytes_on_disk_dir_view"),
        "read_result": head["read_result"],
        "read_attempted": head.get("read_attempted"),
        "read_skipped_reason": head.get("read_skipped_reason"),
        "roundtrip_ok": head.get("roundtrip_ok"),
        "sha256_self": head.get("sha256_self"),
        "sha256_truth": head.get("sha256_truth"),
        "name_landed_as": head.get("name_landed_as"),
        "name_mutated": head.get("name_mutated"),
        "enum_to_stat_agrees": head.get("enum_to_stat_agrees"),
        "phantom": head.get("phantom"),
        "same_name_hits": head.get("same_name_hits"),
        "case_variant_hits": head.get("case_variant_hits"),
        "norm_variant_hits": head.get("norm_variant_hits"),
        "enum_only_names": head.get("enum_only_names"),
        "members_observed_for_this_child": len(members),
        "entry_spread": spread,
        "entry_spread_distinct_create_results": sorted({(s.get("record") or {}).get("create_result")
                                                        for s in spread} - {None}),
        "os_legality_verdict": legality,
        "os_legality_probe": ext,
        "mechanism_class": plan.get("category", "unknown"),
        "deps_direct": 0,
        "deps_total": 0,
        "len_triple": {"code_points": head.get("name_code_points"),
                       "utf16_code_units": head.get("name_utf16_units"),
                       "utf8_bytes": head.get("name_utf8_bytes")},
        "jvm_self_report": {k: doc.get(k) for k in ("java_version", "java_vendor", "java_home",
                                                     "os_name", "os_arch", "os_version",
                                                     "file_encoding", "sun_jnu_encoding", "pid")},
        "scratch": doc.get("scratch"),
        "scratch_len": doc.get("scratch_len"),
        "scratch_entry_count_before": doc.get("scratch_entry_count_before"),
        "scratch_entry_count_after": doc.get("scratch_entry_count_after"),
        "cleanup_failed": True,
        "cleanup_reason": "project rule: this port has no deletion logic, so every fresh scratch dir is left in place",
        "child_rc": prim["rc"],
        "child_timed_out": prim["timed_out"],
        "instrument_red": False,
        "blocked": False,
        "spec_applicable_on_windows": "windows" in plan.get("applicable", []),
    })
    if doc.get("mechanism_probe"):
        rec["mechanism_probe"] = doc["mechanism_probe"]
    if plan.get("mechanism"):
        rec["mechanism_preflight"] = MECH
    if form == "extended":
        # rev6: for this port the extended form is refused by the language parser itself, and the
        # string handed over already carries the prefix, so the mechanism is stated as such
        rec["longpath_mechanism"] = "prefix_rewrite"
        rec["longpath_mechanism_basis"] = (
            "the requested path form IS the extended prefix, so no separate long-path mechanism "
            "is in play beyond the form the cell asked for")
    tpl = (head.get("total_path_len_plain") or 0)
    if tpl > 259 and form != "extended":
        mv = MECH.get("verdict")
        dv = MECH2[0].get("combined_verdict") or MECH2[0].get("verdict")
        # only a positive rewrite result licenses prefix_rewrite. "not-rewritten" does NOT
        # license "none": a plain CreateFileW past 260 should have failed, and it did not, so
        # the tolerance is still unexplained and the honest word is unknown.
        rec["longpath_mechanism"] = ("prefix_rewrite" if dv == "rewritten-for-long-paths"
                                     else "unknown")
        rec["longpath_mechanism_verdict_source"] = ("mechanism_preflight: dot leg verdict %s, "
                                                   "device-name leg verdict %s (one child run, "
                                                   "this port only)" % (mv, dv))
        rec["longpath_mechanism_basis"] = (
            "requested plain path is %d code units (>259) and this entry created it, while "
            "LongPathsEnabled=%s on this run and evidence/freeze/env-facts-windows-local.json found "
            "no longPathAware token in any of the three java binaries (raw-byte scan, not a PE "
            "manifest parse); dot leg verdict %s; device-name leg verdict %s"
            % (tpl, env.get("LongPathsEnabled"), mv, dv))
    elif form == "plain":
        rec["longpath_mechanism_basis"] = ("requested plain path is %s code units, below the 259 "
                                           "legacy limit, so no long-path mechanism was engaged" % tpl)
    if plan["kind"] == "len":
        rec["decisive_wall_note"] = (
            "measured on this machine, not assumed: the plain leg kept creating past the 259-unit "
            "legacy limit (see measured_plain_wall) and stopped where a single component exceeds 255 "
            "UTF-16 units; LongPathsEnabled read 0 by two instruments this run, and the S00 raw-byte "
            "scan found no longPathAware token in any java binary, so no mechanism in "
            "spec/canonical.md section 8 accounts for what was observed")
        rec["extended_leg_note"] = (
            "the second leg is java.io with the extended-prefix string (java.nio throws "
            "InvalidPathException on that string); it isolates the component wall from the path wall")
    if plan["kind"] == "len":
        # rev4 keys the bisection regime on longpath_mechanism; only the length group bisects,
        # so a trap cell that never varied a length gets no regime claim at all
        ok_names = [q["name_len"] for q in rec.get("points", []) if q["plain"] == "ok"]
        max_ok_component = max(ok_names) if ok_names else None
        rec["max_name_len_observed_ok"] = max_ok_component
        ok_ext = [q["name_len"] for q in rec.get("points", []) if q["extended"] == "ok"]
        rec["len_ceiling"] = {
            "through_the_pinned_entry": max_ok_component,
            "through_the_os_leg": max(ok_ext) if ok_ext else None,
            "leg_instrument": "java.nio Files.write for the plain column; java.io handing the same "
                              "string to CreateFileW for the extended column",
            "bracket": {"last_ok_total": (rec.get("measured_plain_wall") or {}).get(
                            "max_total_len_observed_ok"),
                        "first_fail_total": (rec.get("measured_plain_wall") or {}).get(
                            "min_total_len_observed_fail")},
            "note": "rev7 cell-identity 9.7: the requested name's width, the landed name's width "
                    "and the ceiling a bisection converged on are three quantities; len_triple "
                    "carries only the first, this field carries the third"}
        rec["bisection_regime"] = rev4_regime(rec.get("longpath_mechanism"), max_ok_component,
                                            rec.get("base_len"))
        if plan.get("row_tag") == "io-spread":
            # both columns of this cell are the same instrument, so the inherited key names need
            # saying what they hold here rather than quietly meaning something else
            rec["len_ceiling"]["measured_through_this_cells_entry"] = entry_under_test
            rec["len_ceiling"]["leg_instrument"] = (
                "this cell ran one instrument, %s, called with the requested String. The column "
                "named 'plain' in points[] is this cell's own create through the path form the rung "
                "asked for (%s); the column named 'extended' is the second leg inside the same "
                "child, which for this entry is the SAME instrument on the SAME kind of string, so "
                "the two columns agreeing here is by construction, not a confirmation. "
                "through_the_pinned_entry keeps the key name the required cells use, but on this "
                "cell it holds %s's answer, not Files.write's; the Files.write answer for this rung "
                "is the paired required cell." % (entry_under_test, plan.get("path_form"),
                                                  entry_under_test))
            rec["points_column_note"] = (
                "points[].plain = create through the requested path form via this cell's entry; "
                "points[].extended = the java.io extended-string leg of the same child. On the "
                "required Files.write cells these two columns are two different instruments; on "
                "this cell they are one instrument twice, which is why they never differ.")
    if rec.get("bisection_regime"):
        rec["bisection_regime_evidence"] = {
            "max_name_len_observed_ok": max_ok_component,
            "base_len": rec.get("base_len"),
            "volume_max_component": env.get("max_component"),
            "model_1_manifest_or_prefix": "expect max_component == volume max_component (255)",
            "model_2_none": "expect max_component == 259 - base_len - 1",
            "read_result_word": "rev4 gate.md section 5 keys the regime on longpath_mechanism"}
    layer, basis = attribute(head, spread, ext, len(runs))
    if head.get("instrument_face"):
        rec["instrument_face"] = head["instrument_face"]
    if plan.get("row_tag") == "io-spread":
        pl, pb, pe = paired_rung_claim(plan, head, spec_sha)
        rec["spread_pair"] = pe
        rec["why_this_cell_exists"] = (
            "F2 part 1: the twelve pinned length rungs were recorded through Files.write only, "
            "with the java.io answer kept as a leg inside that cell. The java.io answer is now "
            "published as its own extra cell so a stranger can compare the two entries of this "
            "port as cells, not as a note. api_entry is not an equality dimension "
            "(spec/cell-identity.md section 1), so this cell is extra and is never compared.")
        if plan.get("row_tag") == "io-spread":
            rec["extended_leg_note"] = (
                "this cell IS the leg the paired Files.write cell kept as a footnote: the requested "
                "string (%s form) is handed to java.io as a String, which is why instrument_face "
                "says 'called with the requested String'. java.nio's parser throws "
                "InvalidPathException on the extended string (index 2; "
                "impl/java/tools/ext-path-of-repro.txt TAG 2/3/4/6/8/10) and the paired cell records "
                "that as create_result=err_at_parse; java.io never asks that parser and reached the "
                "filesystem instead." % plan.get("path_form"))
        if pl:
            layer, basis = pl, pb
    rec["attribution_layer"] = layer
    rec["attribution_basis"] = basis
    if head.get("zip_leg", {}).get("attempted"):
        rec["zip_leg"] = head["zip_leg"]
    # dir-view hygiene: the OS-legality leg creates through java.io, so an entry the plain leg
    # did not produce can still show up in the directory enumeration of a later member.
    probe_landed = bool(ext.get("landed_by_enumeration")) and head.get("same_name_hits") == 0
    rec["dir_view_contains_probe_created_files"] = probe_landed or any(
        (m.get("extended_probe") or {}).get("landed_by_enumeration")
        and m.get("same_name_hits") == 0 for m in members)
    if rec["dir_view_contains_probe_created_files"]:
        rec["dir_view_note"] = (
            "the landed arrays list every entry of the fresh directory, including names created by "
            "this cell's own os_legality_probe (java.io writing the extended-path form, which is a "
            "create-and-list operation as ordered); appeared_names per member separates what each "
            "leg produced from what was already there")
    if canon_extra:
        rec.update(canon_extra)
    if emit.get("blind_id") is not None:
        rec["blind_id"] = emit["blind_id"]
    if emit.get("extra"):
        rec["extra"] = True
        rec["extra_reason"] = emit.get("extra_reason") or "not present in spec/cells-required.json"
    else:
        rec["required_by_contract"] = True
    return rec


# --------------------------------------------------- long-path mechanism leg
MECH = {"attempted": False, "verdict": "not-run"}
MECH2 = [{"attempted": False, "verdict": "not-run"}]
CHILD_RUNS = [0]


def mechanism_preflight(tc, out_parent):
    """One differential child run that names the long-path mechanism for this port.

    Legs differ only in total path length and in whether the caller writes a
    dot-suffixed directory name, so a long call that bypasses name parsing shows up
    as leg B ok / leg C refused. CellProbe.mechanismProbe documents the same shape.
    """
    scratch = make_scratch()
    out = os.path.join(out_parent, uuid.uuid4().hex + ".json")
    argv_extra = ["--mechanism2", "on"]
    r = run_child(tc, scratch, PRIMARY_ENTRY, [hx("preflight-base.txt")], None, out, False,
                  ext="off", mechanism=True, extra_args=argv_extra)
    dev = (r["doc"] or {}).get("device_namespace_probe")
    if isinstance(dev, dict):
        MECH2[0] = dev
    mp = (r["doc"] or {}).get("mechanism_probe")
    if not isinstance(mp, dict):
        mp = {"attempted": False, "verdict": "not-obtainable",
              "why": "child produced no mechanism_probe document"}
    mp["child_rc"] = r["rc"]
    mp["child_timed_out"] = r["timed_out"]
    mp["child_argv"] = " ".join(r["argv"])
    mp["scratch"] = scratch
    return mp


# --------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--only-row-tag", dest="only_row_tag")
    ap.add_argument("--facts-out", dest="facts_out", default=FACTS_PATH)
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--out-dir", default=RESULTS_DIR)
    a = ap.parse_args()
    OUT_DIR[0] = a.out_dir
    facts_path = a.facts_out

    log = []
    cases_path = os.path.join(REPO, "spec", "cases.yaml")
    cases, api, ctrl_ids, csamples = load_cases(cases_path)
    blind = json.loads(io.open(os.path.join(REPO, "evidence", "freeze", "blind-map.json"),
                               encoding="utf-8").read())["entries"]
    java_entries = api["java"]
    req_path = os.path.join(REPO, "spec", "cells-required.json")
    rb = subprocess.run(["git", "-C", REPO, "cat-file", "blob", "HEAD:spec/cells-required.json"],
                        capture_output=True)
    # the PLAN comes off the committed face, the same face REQ_SHA[0] describes and the same one
    # spec/FROZEN.md publishes; reading the working tree here would cite one face and obey another
    if rb.returncode != 0:
        print("INSTRUMENT-RED cannot read the committed required list: %s"
              % rb.stderr.decode("utf-8", "replace")[:200])
        return 3
    req = json.loads(rb.stdout.decode("utf-8"))
    REQ_SHA[0] = hashlib.sha256(rb.stdout).hexdigest()
    sha_disk_list = hashlib.sha256(io.open(req_path, "rb").read()).hexdigest()
    if sha_disk_list != REQ_SHA[0]:
        # repo rule (ci commit "hash the committed blob face, never the checkout"): the committed
        # face is authoritative. A working tree that differs is disclosed, not silently followed.
        print("WARN_DIRTY_CHECKOUT spec/cells-required.json working tree %s != committed blob %s;"
              % (sha_disk_list[:16], REQ_SHA[0][:16]))
        print("   this port derives its cells from the committed face, which is the value "
              "spec/FROZEN.md publishes. The checkout difference is reported, not chased.")
    if req.get("spec_blob_sha256") != hashlib.sha256(
            subprocess.run(["git", "-C", REPO, "cat-file", "blob", "HEAD:spec/cases.yaml"],
                           capture_output=True).stdout).hexdigest():
        print("INSTRUMENT-RED spec/cells-required.json cites a different cases.yaml hash than the "
              "committed blob face")
        return 3
    print("required list: %d cells + %d java T-API rows (blob sha %s)"
          % (len(req["required_cells"]),
             len([t for t in req["tapi_cells_per_language"] if t["language"] == "java"]),
             REQ_SHA[0][:16]))
    len_fill = parse_len_fill(cases_path)
    print("len_fill pinned unit=%s applies_to=%s" % ((len_fill or {}).get("unit_hex"),
                                                    (len_fill or {}).get("applies_to")))
    plan = build_plan(cases, api, ctrl_ids, blind, java_entries, req, csamples, len_fill)
    if a.only:
        want = set(x.strip() for x in a.only.split(","))
        plan = [p for p in plan if p["case_id"] in want
                or any(e["case_id"] in want for e in p["emits"])
                or p.get("tapi_entry_under_test") in want]
    if a.only_row_tag:
        # F2 runs append-only: the 44 required Files.write cells were measured and published
        # already, and the ticket says not to re-answer them. A filtered run must therefore NOT
        # overwrite the facts face the record cites, hence --facts-out.
        wantt = set(x.strip() for x in a.only_row_tag.split(","))
        plan = [p for p in plan if p.get("row_tag") in wantt]
        print("ROW_FILTER %s -> plan_rows=%d" % (",".join(sorted(wantt)), len(plan)))
        if not plan:
            print("INSTRUMENT-RED the row filter selected nothing")
            return 3
    names = [cell_filename({"case_group": e["group"], "case_id": e["case_id"]}, e)
             for p in plan for e in p["emits"]]
    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:
        print("INSTRUMENT-RED two emits would write the same cell file: %s" % ",".join(dupes[:6]))
        return 3
    emits_total = sum(len(p["emits"]) for p in plan)
    print("plan rows=%d cell_files=%d case_ids=%s"
          % (len(plan), emits_total, ",".join(sorted({e["case_id"] for p in plan for e in p["emits"]}))))
    if a.dry:
        for p in plan:
            for e in p["emits"]:
                print("  %-5s %-22s sub=%-14s entries=%d member=%s extra=%s"
                      % (e["group"], e["case_id"], str(e.get("sub")), len(p["entries"]),
                         e.get("member_index"), bool(e.get("extra"))))
        return 0

    tc = resolve_toolchain()
    if tc.get("status") != "ok":
        print("INSTRUMENT-RED toolchain unresolved: %s" % json.dumps(tc)[:400])
        return 3
    print("TOOLCHAIN javac=%s" % tc["chosen_javac"])
    print("TOOLCHAIN java =%s" % tc["chosen_java"])
    cr = subprocess.run([tc["chosen_javac"], "-nowarn", "-d", BUILD,
                         os.path.join(PORT, "src", "CellProbe.java")], capture_output=True)
    if cr.returncode != 0:
        print("INSTRUMENT-RED compile rc=%s %s" % (cr.returncode,
              cr.stderr.decode("utf-8", "replace")[:400]))
        return 3
    sha_blob, blob_rc, blob_info = spec_sha_from_blob(REPO, "spec/cases.yaml")
    if blob_rc != 0:
        print("INSTRUMENT-RED cannot read the committed spec blob: %s" % blob_info)
        return 3
    sha_disk = hashlib.sha256(io.open(cases_path, "rb").read()).hexdigest()
    env = local_env_facts()
    env["toolchain"] = tc["chosen_java"] + " | " + (tc.get("chosen_java_probe") or {}).get("first_line", "")

    os.makedirs(a.out_dir, exist_ok=True)
    scratch_parent = SCRATCH_ROOT.rstrip("\\")
    os.makedirs(scratch_parent, exist_ok=True)
    out_parent = os.path.join(SCRATCH_ROOT.rstrip("\\"), "_out")
    os.makedirs(out_parent, exist_ok=True)

    global MECH
    MECH = mechanism_preflight(tc, out_parent)
    print("MECHANISM verdict=%s" % MECH.get("verdict"))

    produced, blocked, files_expected = [], [], 0
    for p in plan:
        runs = {}
        base_len = p["base_len"] if p["kind"] == "len" else None
        for entry in p["entries"]:
            try:
                scratch = make_scratch(base_len)
            except Exception as e:
                runs[entry] = {"argv": ["<scratch-create-failed>"], "rc": None, "stdout": "",
                               "stderr": "%s: %s" % (type(e).__name__, e), "timed_out": False,
                               "started_at": stamp(), "elapsed_ms": 0, "doc": None,
                               "result_file_present": False, "read_err": None}
                continue
            out_path = os.path.join(out_parent, uuid.uuid4().hex + ".json")
            if not p.get("members_hex") and not p.get("grades"):
                runs[entry] = {"argv": ["<no hex member supplied by the plan>"], "rc": None,
                               "stdout": "", "stderr": "plan row carries no hex members and no grades",
                               "timed_out": False, "started_at": stamp(), "elapsed_ms": 0,
                               "doc": None, "result_file_present": False, "read_err": None}
                continue
            runs[entry] = run_child(tc, scratch, entry, p["members_hex"], p.get("grades"),
                                    out_path, p.get("zip", False), sweep=p.get("sweep"),
                                    mechanism=p.get("mechanism", False),
                                    path_form=p.get("path_form"),
                                    fill_unit=p.get("fill_unit"))
        canon_extra = None
        if p["kind"] == "canon":
            a1 = (runs.get(PRIMARY_ENTRY, {}).get("doc") or {}).get("members", [{}])[0]
            a2 = (runs.get("FileOutputStream.write", {}).get("doc") or {}).get("members", [{}])[0]
            same = a1.get("sha256_truth") is not None and a1.get("sha256_truth") == a2.get("sha256_truth")
            canon_extra = {
                "canon_instruments": [PRIMARY_ENTRY, "FileOutputStream.write"],
                "canon_sha256_primary": a1.get("sha256_truth"),
                "canon_sha256_second_instrument": a2.get("sha256_truth"),
                "canon_instruments_agree": same,
                "canon_payload_sha256": hashlib.sha256(PAYLOAD).hexdigest(),
                "canon_baseline_crosscheck": {
                    "baseline_field": "evidence/ctrl-baseline.md sha256_on_disk for T-CTRL-ASCII",
                    "baseline_value": BASELINE_SHA,
                    "baseline_value_hex_chars": len(BASELINE_SHA),
                    "baseline_publishes_payload_bytes": False,
                    "this_port_payload_sha256": hashlib.sha256(PAYLOAD).hexdigest(),
                    "verdict": "not-determinate across ports: the baseline publishes a hash but not "
                               "the payload bytes, so a payload of the same declared length cannot "
                               "be ruled in or out against it; the canon control this port can run is "
                               "agreement between two of its own instruments, and control_pass reports "
                               "exactly that",
                },
                "control_pass": bool(same),
            }
        extra_files = 0
        for emit in p["emits"]:
            try:
                rec = assemble(tc, p, runs, sha_blob, env, canon_extra, emit)
            except Exception as e:
                print("ASSEMBLE-FAIL %s/%s: %s: %s"
                      % (p["case_id"], emit["case_id"], type(e).__name__, e))
                return 3
            rec = strip_unmeasured(rec)
            fn = cell_filename(rec, emit)
            path = os.path.join(a.out_dir, fn)
            data = json.dumps(rec, ensure_ascii=True, indent=1, sort_keys=False) + "\n"
            io.open(path, "w", encoding="utf-8", newline="\n").write(data)
            again = json.loads(io.open(path, encoding="utf-8").read())
            if again["case_id"] != rec["case_id"] or again.get("verdict_via") != rec.get("verdict_via"):
                print("WRITE-VERIFY-FAIL %s" % fn)
                return 3
            produced.append(fn)
            if rec.get("extra"):
                extra_files += 1
            if rec.get("blocked"):
                blocked.append(fn)
            print("CELL %-5s %-22s %-14s entry=%-24s create=%-14s read=%-6s legality=%-8s "
                  "via=%-6s spread=%d%s%s"
                  % (rec["case_group"], emit["case_id"], str(emit.get("sub")), rec["api_entry"],
                     rec["create_result"], rec["read_result"], rec["os_legality_verdict"],
                     rec.get("verdict_via"), len(rec.get("entry_spread", [])),
                     " BLOCKED" if rec.get("blocked") else "",
                     " EXTRA" if rec.get("extra") else ""))
        files_expected += extra_files

    required_names = set()
    for rc in req["required_cells"]:
        dims = rc["sub_identity"]
        required_names.add(cell_filename({"case_group": rc["case_group"], "case_id": rc["case_id"]},
                                         {"sub_parts": ["base_len-%s" % dims["base_len"],
                                                        dims["path_form"]]
                                          if "base_len" in dims else []}))
    for t in req["tapi_cells_per_language"]:
        if t["language"] == "java":
            required_names.add(cell_filename({"case_group": "tapi", "case_id": t["case_id"]},
                                             {"sub": t["api_entry"]}))
    missing_all = sorted(required_names - set(produced))
    # under a row filter the absent required identities are this run's scope, not a gap in the
    # matrix: reporting them as MISSING would read as a blocked cell that was never attempted
    missing = [] if a.only_row_tag else missing_all
    if a.only_row_tag and missing_all:
        print("ROW_FILTER append-only: %d required identities are outside this run's filter; they "
              "are on the disk from the full run and were NOT re-answered here" % len(missing_all))
    elif missing_all:
        print("MISSING_REQUIRED %s" % ",".join(missing_all))
    facts = {"started_local": stamp(), "clock_note": "host-local time, UTC+08:00, no offset in string",
             "toolchain": tc, "spec_sha256_blob": sha_blob,
             "spec_sha256_disk": sha_disk, "blob_equals_disk": sha_blob == sha_disk,
             "required_list_sha256_blob": REQ_SHA[0],
             "required_list_sha256_worktree": sha_disk_list,
             "required_list_face_equal": sha_disk_list == REQ_SHA[0],
             "head_commit": subprocess.run(["git", "-C", REPO, "rev-parse", "HEAD"],
                                           capture_output=True, text=True).stdout.strip(),
             "required_cells_declared": len(req["required_cells"]) + len(
                 [t for t in req["tapi_cells_per_language"] if t["language"] == "java"]),
             "required_cells_produced": len(set(produced) & required_names),
             "required_cells_missing": missing,
             "extra_cells_produced": sorted(set(produced) - required_names),
             "env_facts_this_run": env, "cells_produced": len(produced),
             "cells_blocked": blocked, "scratch_root": SCRATCH_ROOT,
             "scratch_parent": scratch_parent,
             "scratch_dirs_retained": len([x for x in os.listdir(scratch_parent)
                                           if x != "_out"]) if os.path.isdir(scratch_parent) else None,
             "child_result_files_retained": len(os.listdir(out_parent)) if os.path.isdir(out_parent) else None,
             "child_runs": CHILD_RUNS[0],
             "payload_bytes": len(PAYLOAD), "payload_sha256": hashlib.sha256(PAYLOAD).hexdigest(),
             "timeout_s": TIMEOUT_S, "harness_version": HARNESS_VERSION,
             "contract_revision_read": "rev3 (docs/NOTICE-rev3.md)",
             "length_unit": LENGTH_UNIT, "name_encoding": NAME_ENCODING, "verdict_via": VERDICT_VIA,
             "mechanism_preflight": MECH,
             "device_namespace_preflight": MECH2[0],
             "primary_entry": PRIMARY_ENTRY, "spread_entries": SPREAD_ENTRIES,
             "io_spread_entry": IO_SPREAD_ENTRY,
             "plan_size": len(plan), "cell_files": len(produced)}
    if a.only_row_tag:
        facts["row_filter"] = {
            "only_row_tag": a.only_row_tag,
            "required_cells_not_in_this_run": len(required_names) - len(
                set(produced) & required_names),
            "note": "append-only run. The required Files.write cells this run did not touch were "
                    "measured by the earlier full run and are deliberately NOT re-answered: F2 "
                    "orders it, and rewriting them would move faces the derived docs already quote. "
                    "This facts file therefore describes THIS run only; the full-matrix face is "
                    "run-facts.json.",
        }
    io.open(facts_path, "w", encoding="utf-8", newline="\n").write(
        json.dumps(facts, ensure_ascii=True, indent=1) + "\n")
    print("FACTS %s" % facts_path)
    print("cells_produced=%d cells_blocked=%d extra=%d missing_required=%d results_dir=%s"
          % (len(produced), len(blocked), len(set(produced) - required_names), len(missing), a.out_dir))
    return 1 if (blocked or missing) else 0


if __name__ == "__main__":
    sys.exit(main())
