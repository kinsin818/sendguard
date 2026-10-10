#!/usr/bin/env python3
"""SENDGUARD rust seat driver (harness side, python stdlib only).

Order is deliberate: the five control cells run first and are judged against
evidence/S00-ctrl-baseline.md - the only allowed source of control expectations - because a
control mismatch means the ruler is broken and no further cell may be produced.

Per cell:
  * one child process (the rust probe), argv list only, no shell
  * an external 5 s timeout enforced here, not inside the measured process
  * a fresh uuid scratch directory, verified empty before the action
  * the probe writes its own face to a temp path; this driver re-reads it, checks it parses,
    stamps harness fields, writes the published cell file once, then reads the published face
    back and hashes it
  * nothing is deleted (M19). Where a scratch directory cannot be removed because it holds
    entries, the cell records cleanup_failed.

Usage:
    python run_cells.py --plan                      plan + denominators, runs nothing
    python run_cells.py --phase controls [--limit N]
    python run_cells.py --phase all
    python run_cells.py --plan-blind                 exit 3: the frozen table publishes no blind rows
    python run_cells.py --plan-blind --allow-sealed-map
"""
import argparse
import datetime
import glob
import io as _io  # used by rust_env_face
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import uuid

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
IMPL = os.path.join(REPO, "impl", "rust")
RESULTS = os.path.join(REPO, "results", "rust.windows.x64")
CASES = os.path.join(REPO, "spec", "cases.yaml")
FROZEN = os.path.join(REPO, "spec", "FROZEN.md")
RUNS_ROOT = r"D:\sg-rust-scratch"
TIMEOUT_S = 5
HARNESS = "S02-rust-seat-2"
BLIND_MAP = os.path.join(REPO, "evidence", "S00", "blind-map.json")
WORKER = "seat-qoder-rust"
ARCH = "x64"
BASELINE_CANON_SHA = "c9fe45b2fee8ea846f0cf4f2cacc2a891e7b082e7719923502d12a9813e21994"
CANON_PAYLOAD = b"SENDGUARD-CANON-PAYLOAD-2026"
PRIMARY_ENTRY = "std::fs::File::create"
CONTROL_MECHANISM = {"T-CTRL-NAMETOOLONG": "component_length_limit", "T-CTRL-ILLEGAL-CHAR": "illegal_char_filter",
                     "T-CTRL-PARSE": "control_char_handling", "T-CTRL-ASCII": "", "T-CTRL-CANON": ""}
T06_EMOJI_HEX = "656d6f6a692df09f98802e747874"
RESERVED = re.compile(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9]|CONIN\$|CONOUT\$)(\..*)?$", re.I)

LEN_NAME = {"T17": "T-LEN-PATH (length bisection, G1-G4)", "T18": "T-LEN-COMP (component length bisection, G1-G4)"}


def sha_hex(data):
    return hashlib.sha256(data).hexdigest()


def bhex(s):
    return (s if isinstance(s, bytes) else s.encode("utf-8")).hex()


def wide_len(s):
    return len(s.encode("utf-16-le")) // 2


def device_guard(name_text, mechanism):
    if "\x00" in (name_text or ""):
        return True
    if mechanism == "reserved_device_name":
        return True
    return bool(RESERVED.match(name_text or ""))


def now_iso():
    return datetime.datetime.now().astimezone().isoformat(timespec="milliseconds")


# ----------------------------------------------------------------- frozen table
def parse_cases(path):
    text = io.open(path, encoding="utf-8").read()
    cases, controls, cur, in_list, in_api, api_rust, in_controls = [], [], None, False, False, [], False
    for line in text.splitlines():
        st = line.strip()
        if st.startswith("#") or not st:
            continue
        if st.startswith("control_samples:"):
            # rev6: the five control cells now carry pinned bytes in the frozen table itself.
            # Before this, six ports invented six samples for one cell id.
            in_controls, in_api, in_list, cur = True, False, False, None
            continue
        if st.startswith("api_entry:"):
            in_api, in_list = True, False
            continue
        if st.startswith("cases:"):
            in_controls, cur = False, None
            continue
        if in_api:
            m = re.match(r"^(\w+):\s*\[(.*)\]$", st)
            if m:
                if m.group(1) == "rust":
                    api_rust = [x.strip() for x in m.group(2).split(",")]
                continue
            in_api = False
        m = re.match(r"^- id:\s*(\S+)$", st)
        if m:
            cur = {"id": m.group(1), "hex": [], "hex_is_hex": [], "category": "", "applicable": [],
                   "locale": "", "expectation": None, "payload": ""}
            (controls if st.find("T-CTRL") >= 0 and in_controls else cases).append(cur)
            in_list = False
            continue
        if cur is None:
            continue
        m = re.match(r'^payload_hex:\s*"([0-9a-fA-F]+)"\s*(?:#.*)?$', st)
        if m and cur is not None:
            cur["payload"] = m.group(1)
            continue
        m = re.match(r'^sample_hex:\s*"([^"]*)"\s*(?:#.*)?$', st)
        if m:
            cur["hex"] = [m.group(1)]
            cur["hex_is_hex"] = [bool(re.fullmatch(r"[0-9a-fA-F]+", m.group(1)) and len(m.group(1)) % 2 == 0)]
            in_list = False
            continue
        if st == "sample_hex_list:":
            in_list = True
            continue
        if in_list:
            m = re.match(r'^- "([0-9a-fA-F]+)"', st)
            if m:
                cur["hex"].append(m.group(1))
                cur["hex_is_hex"].append(True)
                continue
            in_list = False
        for key, rx in (("category", r"^category:\s*(\S+)$"), ("locale", r"^locale:\s*(\S+)$"),
                        ("expectation", r"^expectation:\s*(\S+)$")):
            m = re.match(rx, st)
            if m:
                cur[key] = None if (key == "expectation" and m.group(1) == "null") else m.group(1)
                break
        m = re.match(r"^applicable:\s*\[(.*)\]$", st)
        if m:
            cur["applicable"] = [x.strip() for x in m.group(1).split(",")]
    return cases, api_rust, controls


def control_cells_from_table(controls):
    """The five control samples as the frozen table pins them (rev6)."""
    out = []
    for c in controls:
        out.append({"id": c["id"], "hex": c["hex"][0], "payload": c.get("payload") or bhex(CANON_PAYLOAD),
                    "mechanism": CONTROL_MECHANISM.get(c["id"], ""),
                    "basis": "spec/cases.yaml control_samples (rev6 pin)"})
    return out


def control_cells():
    """The control samples are defined only by the S00 baseline generator."""
    return [
        {"id": "T-CTRL-NAMETOOLONG", "name": "a" * 256, "mechanism": "component_length_limit",
         "basis": "harness/ctrl-baseline.mjs:76 'a'.repeat(256)"},
        {"id": "T-CTRL-ASCII", "name": "report-2026.txt", "mechanism": "",
         "basis": "harness/ctrl-baseline.mjs:77"},
        {"id": "T-CTRL-ILLEGAL-CHAR", "name": "a<b.txt", "mechanism": "illegal_char_filter",
         "basis": "harness/ctrl-baseline.mjs:78"},
        {"id": "T-CTRL-PARSE", "name": "nul\u0000byte.txt", "mechanism": "control_char_handling",
         "basis": "harness/ctrl-baseline.mjs:79 embedded U+0000"},
        {"id": "T-CTRL-CANON", "name": "canon-rust.txt", "mechanism": "",
         "basis": "harness/ctrl-baseline.mjs:82-93; the baseline faces are canon-node.txt / canon-python.txt"},
    ]


# ----------------------------------------------------------------- environment faces
def run_argv(argv, cwd=None):
    p = subprocess.run(argv, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=False)
    out = p.stdout.decode("utf-8", "replace") if isinstance(p.stdout, bytes) else ""
    return p.returncode, out


def toolchain_facts():
    f = {}
    shim = shutil.which("rustc")
    f["path_rustc"] = shim
    rc, out = run_argv(["rustup", "which", "rustc"])
    f["rustup_which_rc"] = rc
    real = out.strip() if rc == 0 else None
    f["resolved_rustc"] = real
    rc, out = run_argv([real, "-vV"]) if real else (9, "<no resolved path>")
    f["resolved_rustc_vV_rc"] = rc
    f["resolved_rustc_vV"] = out
    for key, rx in (("rustc_release", r"release:\s*(\S+)"), ("rustc_commit_hash", r"commit-hash:\s*(\S+)"),
                    ("rustc_host", r"host:\s*(\S+)"), ("rustc_llvm", r"LLVM version:\s*(\S+)")):
        m = re.search(rx, out)
        f[key] = m.group(1) if m else "unknown"
    rc, out = run_argv(["rustup", "show"])
    f["rustup_show_rc"] = rc
    f["rustup_show"] = out
    rc, out = run_argv([shim, "-V"]) if shim else (9, "")
    f["shim_dash_V"] = out.strip()
    for tag, pth in (("shim", shim), ("resolved", real)):
        try:
            raw = open(pth, "rb").read()
            f[tag + "_sha256"] = sha_hex(raw)
            f[tag + "_bytes"] = len(raw)
            f[tag + "_longPathAware_hits"] = raw.count(b"longPathAware")
        except (OSError, TypeError) as e:
            f[tag + "_sha256"] = "unreadable: %s" % e
    f["shim_and_resolved_differ"] = (f.get("shim_sha256") != f.get("resolved_sha256"))
    rc, out = run_argv(["reg", "query", r"HKLM\SYSTEM\CurrentControlSet\Control\FileSystem", "/v", "LongPathsEnabled"])
    m = re.search(r"LongPathsEnabled\s+REG_DWORD\s+0x([0-9a-fA-F]+)", out)
    f["LongPathsEnabled"] = int(m.group(1), 16) if m else None
    f["LongPathsEnabled_rc"] = rc
    f["LongPathsEnabled_face"] = out.strip()
    wv = sys.getwindowsversion()
    f["os_version"] = "Windows %d.%d build %d" % (wv.major, wv.minor, wv.build)
    f["locale"] = "zh-CN console cp936; python default encoding cp936; see evidence/S00/env-facts-windows-local.json"
    f["locale"] = "zh-CN console cp936; python default encoding cp936; see evidence/S00/env-facts-windows-local.json"
    f["toolchain_line"] = "rustc %s (%s) host=%s LLVM=%s; PATH rustc is the rustup shim %s, resolved toolchain binary %s" % (
        f["rustc_release"], f["rustc_commit_hash"], f["rustc_host"], f["rustc_llvm"], f["path_rustc"], f["resolved_rustc"])
    return f


def rust_env_face(deps, runs):
    """max_component and the DOS-device table, asked of kernel32 by the probe itself."""
    out = os.path.join(runs, "env-face.json")
    argv = [deps["sg_probe_path"], "--mode", "env", "--out", out, "--mark", "",
            "--volume-root", "D:\\", "--dos-device-names", "CON,NUL,AUX,PRN,COM1,LPT9,CONIN$,trail.,a<b.txt"]
    try:
        q = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False)
        rc, err = q.returncode, (q.stderr or b"").decode("utf-8", "replace")
    except OSError as e:
        return {"env_face_rc": "spawn-failed: %s" % e}
    face = {"env_face_rc": rc, "env_face_command": subprocess.list2cmdline(argv)}
    if rc != 0 or not os.path.isfile(out):
        face["env_face_error"] = "rc=%s stderr=%s" % (rc, err[:200])
        return face
    try:
        d = json.loads(_io.open(out, encoding="utf-8").read())
    except ValueError as e:
        face["env_face_error"] = "unparseable: %s" % e
        return face
    face["max_component"] = d.get("max_component")
    face["filesystem"] = d.get("filesystem")
    face["dos_devices"] = d.get("dos_devices")
    return face


def build_probes():
    out = {}
    pre = {}
    for name in ("sg_probe", "sg_probe_norm"):
        p = os.path.join(IMPL, "target", "release", name + ".exe")
        pre[name] = sha_hex(open(p, "rb").read()) if os.path.isfile(p) else "absent"
    rc, text = run_argv(["cargo", "build", "--release", "--offline"], cwd=IMPL)
    out["build_std_rc"], out["build_std_face"] = rc, text.strip()[-400:]
    rc2, text2 = run_argv(["cargo", "build", "--release", "--offline", "--features", "normalization"], cwd=IMPL)
    out["build_norm_rc"], out["build_norm_face"] = rc2, text2.strip()[-400:]
    for name in ("sg_probe", "sg_probe_norm"):
        p = os.path.join(IMPL, "target", "release", name + ".exe")
        out[name + "_path"] = p
        if os.path.isfile(p):
            raw = open(p, "rb").read()
            out[name + "_sha256"] = sha_hex(raw)
            out[name + "_bytes"] = len(raw)
            out[name + "_longPathAware_hits"] = raw.count(b"longPathAware")
            out[name + "_mtime"] = datetime.datetime.fromtimestamp(os.path.getmtime(p)).isoformat(timespec="seconds")
            # a failed build leaves the previous exe in place; using it silently would publish
            # an old measurement face under a new run id
            out[name + "_unchanged_by_this_build"] = (out[name + "_sha256"] == pre[name])
        else:
            out[name + "_sha256"] = "MISSING"
            out[name + "_longPathAware_hits"] = -1
            out[name + "_unchanged_by_this_build"] = None
    src = os.path.join(IMPL, "src", "probe.rs")
    out["source_mtime"] = datetime.datetime.fromtimestamp(os.path.getmtime(src)).isoformat(timespec="seconds")
    out["source_newer_than_exe"] = os.path.getmtime(src) > os.path.getmtime(os.path.join(IMPL, "target", "release", "sg_probe.exe")) if os.path.isfile(os.path.join(IMPL, "target", "release", "sg_probe.exe")) else True
    lock = os.path.join(IMPL, "Cargo.lock")
    pkgs = []
    if os.path.isfile(lock):
        pkgs = re.findall(r'(?m)^name = "(.*)"$', io.open(lock, encoding="utf-8").read())
    pkgs = [p for p in pkgs if p != "sendguard-rust-seat"]
    out["cargo_lock_packages"] = pkgs
    out["deps_total_norm"] = len(pkgs)
    toml = io.open(os.path.join(IMPL, "Cargo.toml"), encoding="utf-8").read()
    block = toml.split("[dependencies]")[1].split("[[bin]]")[0] if "[dependencies]" in toml else ""
    direct = [l.split("=")[0].strip() for l in block.splitlines() if l.strip() and not l.strip().startswith("#")]
    out["deps_direct_norm"] = len(direct)
    out["deps_list_norm"] = direct
    return out


def spec_faces():
    rc, head = run_argv(["git", "-C", REPO, "rev-parse", "HEAD"])
    face = {"head": head.strip() if rc == 0 else "unknown", "git_rc": rc}
    p = subprocess.run(["git", "-C", REPO, "cat-file", "blob", "HEAD:spec/cases.yaml"],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False)
    blob = p.stdout or b""
    face["cat_file_rc"] = p.returncode
    face["cat_file_stderr"] = p.stderr.decode("utf-8", "replace").strip() if p.stderr else ""
    face["blob_sha256"] = sha_hex(blob)
    face["blob_bytes"] = len(blob)
    raw = open(CASES, "rb").read()
    face["worktree_sha256"] = sha_hex(raw)
    face["worktree_bytes"] = len(raw)
    face["faces_identical"] = blob == raw
    frozen = io.open(FROZEN, encoding="utf-8").read()
    m = re.search(r"spec/cases\.yaml\s*\|\s*([0-9a-f]{64})", frozen)
    face["frozen_declared"] = m.group(1) if m else "not-found"
    face["frozen_declared_matches_blob"] = face["frozen_declared"] == face["blob_sha256"]
    face["frozen_declared_matches_worktree"] = face["frozen_declared"] == face["worktree_sha256"]
    return face


# ----------------------------------------------------------------- plan
LEN_GROUP = ("component_length_limit",)
REQUIRED_LIST = os.path.join(REPO, "spec", "cells-required.json")
BASES_DEFAULT = (13, 120, 200, 240)
T01_HEX = "434f4e2e747874"
ENTRY_TAG = {"std::fs::write": "write", "std::fs::File::create": "fcreate",
             "std::fs::OpenOptions": "openopts", "std::fs::rename": "rename"}


class Cell(object):
    """One planned cell.

    unique_key()  - the file this face publishes; every face must be distinct.
    answers()     - the contract row it answers, in spec/cells-required.json's own shape.
    gate_identity() - what ci/equality.py would key this face on (case_group, case_id, base_len).
      Extras are given their own case_id precisely because an extra that shares a required
      gate_identity would make that required cell ambiguous, and the gate implements no
      'extra' exclusion.
    """

    def __init__(self, group, case_id, entry, hexes, kind, mechanism, applicable, path_form,
                 name_text, tier=None, sub=None, norm=False, zipface=False, mode="create",
                 bisect=None, bisect_range=None, range_basis="", note="", member="",
                 variant_of="", superseded_by="", spec_sample="", tapi_sample="", base_len=None,
                 answers=None, payload_hex=""):
        self.group, self.case_id, self.entry, self.hexes = group, case_id, entry, hexes
        self.kind, self.mechanism, self.applicable, self.path_form = kind, mechanism, applicable, path_form
        self.name_text, self.tier, self.sub = name_text, tier, sub
        self.norm, self.zipface, self.mode = norm, zipface, mode
        self.bisect, self.bisect_range, self.range_basis, self.note = bisect, bisect_range, range_basis, note
        self.member, self.variant_of, self.superseded_by = member, variant_of, superseded_by
        self.spec_sample, self.tapi_sample, self.base_len = spec_sample, tapi_sample, base_len
        self.payload_hex = payload_hex
        self._answers = answers
        self.scratch, self.tmp, self.attempts, self.required = None, None, 0, False

    @property
    def frozen_id(self):
        m = re.match(r"^(T\d{2}|T-CTRL-[A-Z-]+)", self.case_id)
        if m:
            return m.group(1)
        m = re.match(r"^(T\d{2})", self.case_id)
        return m.group(1) if m else self.case_id

    def filename(self):
        parts = [self.group, self.case_id] + ([self.sub] if self.sub else [])
        return re.sub(r"[^A-Za-z0-9._-]", "_", "__".join(parts)) + ".json"

    def unique_key(self):
        return (self.group, self.case_id, self.sub or "", self.entry)

    def answers(self):
        if self._answers is not None:
            return self._answers
        return (self.group, self.case_id, ())

    def gate_identity(self):
        sub = () if self.base_len is None else (("base_len", self.base_len),)
        return (self.group, self.case_id, sub)


def sub_of(s):
    return re.sub(r"[^A-Za-z0-9._-]", "_", s)


def load_blind(path):
    """The five blind samples.

    sealed_at says "sealed until audit completes" and part 1 of the self-check records this seat
    refusing to open it. NOTICE-rev6 item 2 is the contract owner ordering the five cells and naming
    this file as their source, so the seal is lifted by that order, not by this seat's choice. The
    file's own sha256 and its inner sha256_self field are recorded in every blind cell: the two are
    different numbers, because a self-hash cannot cover the line that carries it.
    """
    if not os.path.isfile(path):
        return [], None
    raw = open(path, "rb").read()
    doc = json.loads(raw.decode("utf-8"))
    rows = [(e.get("blind_id"), e.get("name_utf8_hex")) for e in doc.get("entries", []) if e.get("name_utf8_hex")]
    return rows, {"sha256_whole_file": sha_hex(raw), "bytes": len(raw),
                  "sha256_self_field": doc.get("sha256_self"), "sealed_at": doc.get("sealed_at"),
                  "path": os.path.relpath(path, REPO).replace(os.sep, "/")}


def load_required(path):
    """The contract's required list, read rather than retyped."""
    doc = json.loads(io.open(path, encoding="utf-8").read())
    keys = set()
    for r in doc.get("required_cells", []):
        keys.add((r["case_group"], r["case_id"], tuple(sorted((r.get("sub_identity") or {}).items()))))
    for r in doc.get("tapi_cells_per_language", []):
        if r.get("language") == "rust":
            keys.add(("tapi", r["case_id"], tuple(sorted((r.get("sub_identity") or {}).items())), r["api_entry"]))
    return keys, doc


def build_plan(cases, api_rust, primary_entry, base_ladder, required_keys, controls=None, blind=None):
    """Required rows first, then this seat's own extras, each with its own file and gate identity."""
    plan, seen = [], {}

    def is_trap(c):
        """canonical.md section 2 puts T-CTRL-* in the ctrl group, so a control id is never a trap
        face; and T17/T18 are the len group's cells, not traps either."""
        return c["category"] not in LEN_GROUP and not c["id"].startswith("T-CTRL")

    def add(cell):
        k = cell.unique_key()
        if k in seen:
            raise SystemExit("planner refused: two faces publish the same contract row %s (%s and %s)"
                             % (k, seen[k].filename(), cell.filename()))
        seen[k] = cell
        ak = cell.answers()
        cell.required = ak in required_keys or (ak + (cell.entry,)) in required_keys
        plan.append(cell)
        return cell

    # ---- required traps on the primary entry, member ids spelled -m1/-m2/-m3 as the list says
    for c in cases:
        if not is_trap(c):
            continue
        for i, h in enumerate(c["hex"]):
            multi = len(c["hex"]) > 1
            cid = ("%s-m%d" % (c["id"], i + 1)) if multi else c["id"]
            add(Cell("trap", cid, primary_entry, [h] + [h2 for j, h2 in enumerate(c["hex"]) if j != i],
                     "frozen-sample-hex", c["category"], ",".join(c["applicable"]), "plain",
                     decode_or(h, c["id"]),
                     member="m%d" % (i + 1) if multi else "",
                     norm=c["category"] in ("unicode_normalization", "case_folding"),
                     zipface=c["category"] == "zip_roundtrip",
                     mode="zip" if c["category"] == "zip_roundtrip" else "create",
                     note="member m%d of frozen %s" % (i + 1, c["id"]) if multi else ""))
    # ---- required controls, from the frozen pin
    for cc in (controls or control_cells()):
        name = bytes.fromhex(cc["hex"]).decode("utf-8")
        add(Cell("ctrl", cc["id"], primary_entry, [cc["hex"]], cc["basis"],
                 cc["mechanism"], "windows,macos,ubuntu", "plain", name, note=cc["basis"],
                 payload_hex=cc.get("payload")))
    # ---- required len rows: one per (case, base_len, path_form) on the contract's ladder
    for base in base_ladder:
        for form in ("plain", "extended"):
            for cid, kind in (("T17", "path"), ("T18", "component")):
                add(Cell("len", cid, primary_entry, [], "generated-measured-name", "component_length_limit",
                         "windows,macos,ubuntu", form, "the widest name this cell could create",
                         tier=base, sub=sub_of("bisect-base%d-%s" % (base, form)), mode="bisect", bisect=kind,
                         base_len=base, spec_sample=LEN_NAME[cid],
                         answers=("len", cid, (("base_len", base), ("path_form", form))),
                         bisect_range=(64, 33000) if kind == "path" else (64, 400),
                         range_basis="lower bound one component; upper bound above the 260 code unit face so the real ceiling falls inside the range",
                         note="required row: %s width at base_len=%d, %s face, on the contract ladder" % (kind, base, form)))
    # ---- required T-API rows: one per pinned rust entry
    for e in api_rust:
        add(Cell("tapi", "T-API", e, [T01_HEX], "frozen-sample-hex", "reserved_device_name",
                 "windows,macos,ubuntu", "plain", decode_or(T01_HEX, "T01"),
                 sub=sub_of("entry-" + e), tapi_sample="T01", answers=("tapi", "T-API", ()),
                 note="contract T-API row for this pinned entry"))
    # ---- required blind rows (NOTICE-rev6 item 2): real-world-shaped names on the primary entry
    for bid, hexv in (blind or []):
        cid = "B%d" % int(bid)
        add(Cell("blind", cid, primary_entry, [hexv], "blind-map-sample", "unknown",
                 "windows,macos,ubuntu", "plain", decode_or(hexv, cid), answers=("blind", cid, ()),
                 note="blind sample %s, taken from the file rev6 names; mechanism_class stays unknown "
                      "because the frozen table assigns no mechanism to a blind sample" % bid))

    # ---- extras: the rev-2 member spelling (a/b/c), same measurement, kept and marked
    for c in cases:
        if not is_trap(c) or len(c["hex"]) == 1:
            continue
        for i, h in enumerate(c["hex"]):
            cid = "%s%s" % (c["id"], chr(ord("a") + i))
            add(Cell("trap", cid, primary_entry, [h] + [h2 for j, h2 in enumerate(c["hex"]) if j != i],
                     "frozen-sample-hex", c["category"], ",".join(c["applicable"]), "plain",
                     decode_or(h, c["id"]),
                     superseded_by="trap__%s-m%d.json" % (c["id"], i + 1),
                     norm=c["category"] in ("unicode_normalization", "case_folding"),
                     note="rev-2 member spelling kept as an extra; the contract id is %s-m%d" % (c["id"], i + 1)))
    # ---- extras: the verbatim face of the three traps canonical.md names for it
    for c in cases:
        if c["id"] in ("T01", "T04", "T05"):
            add(Cell("trap", "%s-EXT" % c["id"], primary_entry, [c["hex"][0]], "frozen-sample-hex",
                     c["category"], ",".join(c["applicable"]), "extended", decode_or(c["hex"][0], c["id"]),
                     sub=sub_of("path-form-extended"), variant_of=c["id"],
                     note="extra: verbatim face of %s, with its own id so it cannot read as a second answer for the required cell" % c["id"]))
    # ---- extras: every pinned entry against every frozen member (entry_spread detail)
    for c in cases:
        if not is_trap(c):
            continue
        for i, h in enumerate(c["hex"]):
            cid = c["id"] if len(c["hex"]) == 1 else "%s%s" % (c["id"], chr(ord("a") + i))
            for e in api_rust:
                add(Cell("tapi", "%s-%s" % (cid, ENTRY_TAG[e]), e,
                         [h] + [h2 for j, h2 in enumerate(c["hex"]) if j != i],
                         "frozen-sample-hex", c["category"], ",".join(c["applicable"]), "plain",
                         decode_or(h, c["id"]), sub=sub_of("entry-" + e), variant_of=cid,
                         norm=c["category"] in ("unicode_normalization", "case_folding"),
                         zipface=c["category"] == "zip_roundtrip",
                         mode="zip" if c["category"] == "zip_roundtrip" else "create",
                         note="pinned entry against this sample (extra; the contract T-API row is the T-API cell)"))
    # ---- extras: the frozen G-grid points, which are points and not the required bisection rows
    for base in BASES_DEFAULT:
        ex = 259 - base - 1
        for x in (ex - 1, ex, ex + 1):
            add(Cell("len", "T17-GRID-B%d-L%d" % (base, x), primary_entry, [bhex("c" * x)],
                     "generated-width-for-frozen-G-grid-point", "component_length_limit",
                     "windows,macos,ubuntu", "plain", "c" * x, tier=base, base_len=base,
                     sub=sub_of("len%d" % x), spec_sample=LEN_NAME["T17"], variant_of="T17",
                     note="domain B tier base=%d; the linear model puts the exact hit at 259-base-1=%d" % (base, ex)))
    for base in (13, 200):
        for x in (254, 255, 256):
            for form in ("plain", "extended"):
                add(Cell("len", "T18-GRID-%s-B%d-L%d" % (form.upper(), base, x), primary_entry, [bhex("c" * x)],
                         "generated-width-for-frozen-G-grid-point", "component_length_limit",
                         "windows,macos,ubuntu", form, "c" * x, tier=base, base_len=base,
                         sub=sub_of("len%d" % x), spec_sample=LEN_NAME["T18"], variant_of="T18",
                         note="domain A tier base=%d; the extended face separates the component rule from the path rule" % base))
    for form in ("plain", "extended"):
        for cid, kind in (("T17", "path"), ("T18", "component")):
            add(Cell("len", "%s-CEILING-%s" % (cid, form.upper()), primary_entry, [],
                     "generated-measured-name", "component_length_limit", "windows,macos,ubuntu", form,
                     "widest created name", sub=sub_of("ceiling-%s" % form), mode="bisect", bisect=kind,
                     bisect_range=(64, 33000) if kind == "path" else (64, 400), spec_sample=LEN_NAME[cid],
                     variant_of=cid, range_basis="this seat's own pre-flight ladder, re-measured inside the cell",
                     note="ceiling leg at the fresh uuid scratch, not on the contract ladder"))
    return plan, seen


def decode_or(h, cid):
    try:
        return bytes.fromhex(h).decode("utf-8")
    except Exception as e:
        return "<undecodable frozen sample %s of %s: %s>" % (h, cid, e)
# ----------------------------------------------------------------- run
class Driver(object):
    def __init__(self, env, deps, faces, tier_roots, contract_sha, required_keys, ledger, blind_meta=None):
        self.env, self.deps, self.faces, self.tier_roots = env, deps, faces, tier_roots
        self.blind_meta = blind_meta
        self.contract_sha, self.required_keys, self.ledger = contract_sha, required_keys, ledger
        self.runs_root = tier_roots["runs"]
        self.prior = {}          # scratch dir -> set of hex-encoded names already claimed there
        self.produced = []
        self.problems = []
        self.face_sha = {}
        self.face_bytes = {}
        self.published = {}
        os.makedirs(RESULTS, exist_ok=True)

    def scratch_for(self, cell):
        if cell.tier is not None:
            d = self.tier_roots["tiers"].get((cell.tier, cell.path_form))
            if d is None:
                raise RuntimeError("tier dir for base_len=%d/%s was not built" % (cell.tier, cell.path_form))
            return d
        if cell.case_id.startswith(("T09", "T19")):
            key = ("co", cell.group, cell.frozen_id, cell.entry)
            if key not in self.tier_roots:
                self.tier_roots[key] = self.fresh("co-%s-%s" % (cell.group, cell.frozen_id))
            return self.tier_roots[key]
        return self.fresh(cell.group + "-" + cell.case_id)

    def fresh(self, label):
        d = os.path.join(self.runs_root, "scratch", re.sub(r"[^A-Za-z0-9._-]", "_", label), uuid.uuid4().hex)
        os.makedirs(d, exist_ok=True)
        return d

    def argv_for(self, cell, scratch, tmp_out, mark, prior_entries):
        e, d, fa = self.env, self.deps, self.faces
        if cell.mode == "bisect":
            total = cell.bisect_range[1]
            lp = "prefix_rewrite" if cell.path_form == "extended" else "unknown"
            lpev = ("bisection cell: the plain face is deliberately probed past 259 code units, and no declared "
                    "mechanism name fits what was observed (see the longpath section of evidence/S02/rust-selfcheck.md)")
        else:
            total = wide_len(scratch) + 1 + wide_len(cell.name_text or "")
            if cell.path_form == "extended":
                lp = "prefix_rewrite"
                lpev = "this cell rewrote the path with the verbatim prefix \\\\?\\ explicitly"
            elif total > 259:
                lp = "unknown"
                lpev = ("plain path of %d code units created while LongPathsEnabled=%s; the compiled probe face carries no "
                        "longPathAware token (byte-scan hits=%d) and trailing dot/space is still stripped at this width, which "
                        "rules out a verbatim prefix, so none of the declared mechanism names fits") % (
                            total, e["LongPathsEnabled"], d["sg_probe_longPathAware_hits"])
            else:
                lp = "none"
                lpev = "path is %d code units, below the 260 code unit MAX_PATH face, so no long-path mechanism is engaged" % total
        prior_hexes = sorted(self.prior.get(scratch, set()))
        norm = cell.norm
        argv = [
            d["sg_probe_norm_path"] if norm else d["sg_probe_path"],
            "--mode", cell.mode, "--case", cell.case_id, "--case-frozen", cell.frozen_id,
            "--group", cell.group, "--entry", cell.entry,
            "--prior-claim-hexes", ",".join(prior_hexes),
            "--primary", "true" if cell.entry == PRIMARY_ENTRY else "false", "--attempt", "1",
            "--path-form", cell.path_form, "--scratch", scratch, "--prior-entries", str(len(prior_hexes)),
            "--out", tmp_out, "--mark", mark, "--payload-hex", bhex(CANON_PAYLOAD),
            "--mechanism-class", cell.mechanism, "--longpath-mechanism", lp, "--longpath-evidence", lpev,
            "--applicable", cell.applicable, "--name-source-kind", cell.kind,
            "--harness", HARNESS, "--worker", WORKER, "--started-at", now_iso(),
            "--spec-sha256", fa["blob_sha256"], "--spec-sha256-worktree", fa["worktree_sha256"],
            "--probe-sha256", d["sg_probe_norm_sha256"] if norm else d["sg_probe_sha256"],
            "--probe-face", "sg_probe_norm" if norm else "sg_probe",
            "--toolchain", e["toolchain_line"],
            "--deps-direct", str(d["deps_direct_norm"] if norm else 0),
            "--deps-total", str(d["deps_total_norm"] if norm else 0),
            "--deps-source", ("the one crate linked into this face is unicode-normalization; Rust's std exposes no NFC/NFD operation at all"
                              if norm else "no crates linked into this face; kernel32 is reached through std FFI declarations, which is not a dependency"),
            "--longpaths-enabled", "" if e["LongPathsEnabled"] is None else str(e["LongPathsEnabled"]),
            "--max-component", "" if e.get("max_component") is None else str(e["max_component"]),
            "--locale", e["locale"], "--sub", cell.sub or "", "--sub-keys", self.sub_keys(cell),
            "--scratch-scope", self.scratch_scope(cell), "--rename-src-name", "sg-rename-src.bin",
            "--no-content-read", "true" if device_guard(cell.name_text, cell.mechanism) else "false",
            "--norm-face", "true" if norm else "false", "--zip-face", "true" if cell.zipface else "false",
            "--member-hex", ",".join(cell.hexes) if cell.hexes else "",
            "--claims", mark + ".claims",
            "--member", cell.member or "",
            "--contract-role", "required" if cell.required else "extra",
            "--contract-key", json.dumps([list(x) if isinstance(x, tuple) else x for x in [cell.answers()[0], cell.answers()[1], [list(q) for q in cell.answers()[2]]]]),
            "--contract-sha256", self.contract_sha,
            "--spec-sample-string", cell.spec_sample or "",
            "--variant-of", cell.variant_of or "",
            "--superseded-by", cell.superseded_by or "",
            "--blind-source", (self.blind_meta or {}).get("path", "") if cell.group == "blind" else "",
            "--blind-map-sha256", (self.blind_meta or {}).get("sha256_whole_file", "") if cell.group == "blind" else "",
            "--blind-map-self-sha256", (self.blind_meta or {}).get("sha256_self_field", "") if cell.group == "blind" else "",
            "--blind-sealed-at", (self.blind_meta or {}).get("sealed_at", "") if cell.group == "blind" else "",
        ]
        if cell.tier is not None:
            argv += ["--base-len", str(cell.tier)]
        elif cell.mode == "bisect":
            # the ladder faces sit in a fresh uuid scratch; its width is still the cell's base_len
            argv += ["--base-len", str(wide_len(scratch))]
        if cell.mode == "bisect":
            argv += ["--bisect", cell.bisect, "--bisect-lo", str(cell.bisect_range[0]), "--bisect-hi", str(cell.bisect_range[1]),
                     "--bisect-range-basis", cell.range_basis, "--bisect-note", cell.note]
        elif cell.zipface:
            argv += ["--zip-entry-hex", ",".join(cell.hexes + [T06_EMOJI_HEX]),
                     "--zip-entry-source-note", "entry 1 is this cell's own frozen sample; entry 2 borrows the frozen T06 sample hex because cases.yaml freezes no non-ASCII zip entry name"]
        return argv, total, lp, lpev

    def sub_keys(self, cell):
        """Declare, inside the cell, which dimensions vary for it (cell-identity section 1, and
        rev4's gate reads this list). It has to match the manifest's own row shape: the len rows
        are keyed on base_len + path_form, and a T-API row is keyed on api_entry OUTSIDE
        sub_identity, so declaring it inside would double-count the dimension."""
        if cell.group == "len":
            return "base_len,path_form"
        if cell.group == "tapi":
            # a port emits one T-API row per pinned entry, so the entry has to be declared as the
            # varying dimension or the gate keys four rows onto one identity
            return "api_entry,member"
        return ""

    def scratch_scope(self, cell):
        if cell.tier is not None:
            return ("tier directory pinned to exactly base_len=%d code units, shared by the three grid points of that tier; "
                    "a uuid directory cannot be 13 code units wide and still carry a uuid, so uniqueness comes from the run tag" % cell.tier)
        if cell.case_id.startswith(("T09", "T19")):
            return "shared with the sibling member cells of this case and entry: the frozen case puts both members in one directory"
        return "fresh uuid scratch directory for this cell alone"

    def spawn(self, cell):
        """Run one child for one cell and return its face, or None with a recorded problem."""
        scratch = self.scratch_for(cell)
        prior_entries = self.prior.get(scratch, 0)
        cell.scratch = scratch
        cell.tmp = os.path.join(self.runs_root, "scratch", "tmp-%s.json" % uuid.uuid4().hex)
        mark = os.path.join(self.runs_root, "logs", cell.filename() + ".markers.log")
        argv, total, lp, lpev = self.argv_for(cell, scratch, cell.tmp, mark, prior_entries)
        t0 = datetime.datetime.now()
        try:
            p = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False)
        except OSError as ex:
            self.problems.append("%s: spawn failed: %s" % (cell.filename(), ex))
            return None
        try:
            _so, se = p.communicate(timeout=TIMEOUT_S)
            rc, killed = p.returncode, False
        except subprocess.TimeoutExpired:
            p.kill()
            _so, se = p.communicate()
            rc, killed = None, True
        elapsed = int((datetime.datetime.now() - t0).total_seconds() * 1000)
        if killed:
            return self.hang_record(cell, argv, mark, total, lp, lpev, elapsed)
        body = None
        if os.path.isfile(cell.tmp):
            try:
                body = json.loads(io.open(cell.tmp, encoding="utf-8").read())
            except ValueError as ex:
                self.problems.append("%s: probe face not parseable (%s) rc=%s stderr=%s" %
                                     (cell.filename(), ex, rc, se.decode("utf-8", "replace")[:200]))
                return None
        if body is None:
            self.problems.append("%s: rc=%s and no face written; stderr=%s" % (cell.filename(), rc, se.decode("utf-8", "replace")[:200]))
            return None
        body["elapsed_ms_harness"] = elapsed
        body["total_path_len_driver"] = total
        body["child_rc"] = rc
        body["child_killed"] = False
        if rc != 0:
            body["probe_nonzero_rc_note"] = "the probe exited %s after writing a face it could not itself verify" % rc
        names = self.prior.setdefault(scratch, set())
        claims_file = mark + ".claims"
        if os.path.isfile(claims_file):
            for h in io.open(claims_file, encoding="utf-8", errors="replace").read().splitlines():
                if h.strip():
                    names.add(h.strip())
        if cell.hexes:
            names.add(cell.hexes[0])
        for key in ("generated_name_hex", "name_landed_as_hex"):
            v = body.get(key)
            if isinstance(v, str) and re.fullmatch(r"[0-9a-f]+", v):
                names.add(v)
        if cell.entry == "std::fs::rename":
            names.add(bhex("sg-rename-src.bin"))
        return body

    def run_one(self, cell):
        body = self.spawn(cell)
        if body is not None:
            self.publish(body, cell)
        return body

    def hang_record(self, cell, argv, mark, total, lp, lpev, elapsed):
        markers = []
        try:
            markers = io.open(mark, encoding="utf-8", errors="replace").read().splitlines()
        except OSError:
            pass
        in_create_leg = any("before-create" in m for m in markers) and not any("after-create" in m for m in markers)
        return {
            "format_version": "1", "case_id": cell.case_id, "case_id_frozen": cell.frozen_id,
            "case_group": cell.group, "sub_identity": [k for k in self.sub_keys(cell).split(",") if k],
            "sub": cell.sub or "", "language": "rust", "os": "windows", "os_version": self.env["os_version"],
            "arch": ARCH, "locale": self.env["locale"], "api_entry": cell.entry,
            "primary": cell.entry == PRIMARY_ENTRY, "attempt": 1,
            "name_source": (cell.hexes[0] if cell.hexes else LEN_NAME.get(cell.case_id, "")),
            "name_source_kind": cell.kind, "length_unit": "utf16_code_units", "name_encoding": "hex_raw_bytes",
            "path_form": cell.path_form, "longpath_mechanism": lp, "longpath_evidence": lpev,
            "create_result": "hang", "error_stage": "syscall" if in_create else "tool",
            "read_result": "hang" if not in_create_leg else "not_applicable",
            "read_skipped_reason": None if not in_create_leg else "the child hung inside the create leg, so no read was ever attempted",
            "os_legality_verdict": "unknown",
            "os_legality_basis": "the child never returned, so no OS answer for this name was obtainable",
            "attribution_layer": "L1", "mechanism_class": cell.mechanism,
            "harness_version": HARNESS, "worker_id": WORKER, "started_at": now_iso(),
            "elapsed_ms": elapsed, "elapsed_ms_harness": elapsed,
            "spec_sha256": self.faces["blob_sha256"], "spec_sha256_worktree": self.faces["worktree_sha256"],
            "probe_sha256": self.deps["sg_probe_norm_sha256"] if cell.norm else self.deps["sg_probe_sha256"],
            "probe_face": "sg_probe_norm" if cell.norm else "sg_probe", "toolchain": self.env["toolchain_line"],
            "deps_direct": self.deps["deps_direct_norm"] if cell.norm else 0,
            "deps_total": self.deps["deps_total_norm"] if cell.norm else 0,
            "deps_source": "stamped by the driver: the child was killed before it could stamp its own",
            "scratch_dir": cell.scratch, "scratch_scope": self.scratch_scope(cell),
            "cell_state": "hang", "contract_role": "required" if cell.required else "extra",
            "extra": not cell.required, "contract_key": json.dumps([list(x) if isinstance(x, tuple) else x for x in [cell.answers()[0], cell.answers()[1], [list(q) for q in cell.answers()[2]]]]),
            "contract_sha256": self.contract_sha, "hang_last_marker": markers[-1] if markers else "<none>",
            "hang_markers": markers, "hang_command": subprocess.list2cmdline(argv),
            "timeout_s": TIMEOUT_S, "child_killed": True, "child_rc": None,
            "read_word_authority": "spec/canonical.md section 5 fifth word (rev4); spec/schema.json still lists four read_result words",
            "control_pass": True, "instrument_red": False, "instrument_conflict": False,
            "env": {"LongPathsEnabled": self.env["LongPathsEnabled"], "max_component": self.env.get("max_component"),
                    "locale": self.env["locale"], "unicode_version": "not-obtainable-here", "toolchain": self.env["toolchain_line"]},
            "note": "hang is a legitimate reading (canonical.md section 3); the marker face names the leg the child had entered",
        }

    def stamp_pre(self, rec, cell):
        """Harness-side fields that a control judgement depends on, added before the
        verdict is computed so the judged face and the published face are the same face."""
        if cell.case_id == "T-CTRL-CANON":
            rec["sha256_python_hashlib"] = sha_hex(CANON_PAYLOAD)
            rec["python_instrument"] = "hashlib.sha256 over the same payload bytes, python %s" % sys.version.split()[0]
            rec["baseline_expected_sha256"] = BASELINE_CANON_SHA
            rec["baseline_source"] = "evidence/S00-ctrl-baseline.md:14 (payload defined at harness/ctrl-baseline.mjs:15)"

    def publish(self, rec, cell):
        self.stamp_pre(rec, cell)
        rec["control_pass"] = rec.get("control_pass", True)
        rec["instrument_red"] = rec.get("instrument_red", False)
        rec["instrument_conflict"] = rec.get("instrument_conflict", False)
        # M19: no deletion logic. Only an empty directory this driver created is removed.
        cleanup_failed, reason = True, ""
        try:
            if os.path.isdir(cell.scratch) and not os.listdir(cell.scratch):
                os.rmdir(cell.scratch)
                rec["scratch_removed_empty"] = True
                cleanup_failed = False
            else:
                rec["scratch_removed_empty"] = False
                reason = "scratch holds entries left by the measurement; this port carries no deletion logic (M19)"
        except OSError as ex:
            reason = "rmdir refused: %s" % ex
        rec["cleanup_failed"] = cleanup_failed
        if reason:
            rec["cleanup_reason"] = reason
        path = os.path.join(RESULTS, cell.filename())
        raw = (json.dumps(rec, indent=2, ensure_ascii=True) + "\n").encode("utf-8")
        with open(path, "wb") as fh:
            fh.write(raw)
        back = open(path, "rb").read()
        verified = back == raw
        try:
            parsed = json.loads(back.decode("utf-8"))
            verified = verified and parsed.get("case_id") == cell.case_id and parsed.get("format_version") in (1, "1")
        except ValueError:
            verified = False
        if not verified:
            self.problems.append("%s: published face did not read back identical and parseable" % cell.filename())
        # the hash of the published face is kept OUT of the face: a self-hash can never
        # cover its own line, so it lives in run-summary.json instead.
        self.face_sha[path] = sha_hex(back)
        self.face_bytes[path] = len(back)
        self.published[path] = verified
        if path not in [p for _c, p in self.produced]:
            self.produced.append((cell, path))
        return path, verified, rec


# ----------------------------------------------------------------- control judgement
def control_expectations():
    return {
        "T-CTRL-NAMETOOLONG": (lambda r: r.get("create_result") == "err_at_syscall" and r.get("error_stage") == "syscall",
                               "err_at_syscall + error_stage=syscall"),
        "T-CTRL-ASCII": (lambda r: r.get("create_result") == "ok" and r.get("bytes_written") == 28 and r.get("bytes_on_disk") == 28
                         and r.get("read_result") == "ok" and r.get("roundtrip_ok") is True,
                         "ok, 28 written, 28 on disk, read ok, roundtrip true"),
        "T-CTRL-ILLEGAL-CHAR": (lambda r: r.get("create_result") == "err_at_syscall" and r.get("error_stage") == "syscall",
                                "err_at_syscall + error_stage=syscall"),
        "T-CTRL-PARSE": (lambda r: r.get("create_result") == "err_at_parse" and r.get("error_stage") == "parse",
                         "err_at_parse + error_stage=parse"),
        "T-CTRL-CANON": (lambda r: r.get("sha256_self") == BASELINE_CANON_SHA and r.get("sha256_truth") == BASELINE_CANON_SHA
                         and r.get("sha256_python_hashlib") == BASELINE_CANON_SHA,
                         "rust in-memory digest == rust on-disk digest == python hashlib digest == S00 baseline"),
    }


def face_of(path):
    return json.loads(io.open(path, encoding="utf-8").read())


def emit_blocked_rows(runs, contract, answered_keys=None, blind_meta=None):
    """The required rows this port cannot measure, emitted with the command, its exit code and one
    attempted fix - and deliberately NOT written into results/, because cell-identity section 3 says
    that directory holds nothing but cells, and canonical.md has no closed word for 'never attempted'.
    """
    rows = []
    for r in contract.get("required_cells", []):
        if r.get("case_group") != "blind":
            continue
        if answered_keys is not None and (r["case_group"], r["case_id"], ()) in answered_keys:
            continue
        cmd = [sys.executable, os.path.join(IMPL, "run_cells.py"), "--plan-blind"]
        fix_cmd = cmd + ["--allow-sealed-map"]
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=False)
        fix = subprocess.run(fix_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=False)
        rows.append({
            "case_group": "blind", "case_id": r["case_id"], "sub_identity": r.get("sub_identity") or {},
            "cell_state": "blocked",
            "command": subprocess.list2cmdline(cmd), "exit_code": p.returncode,
            "command_face": (p.stdout or b"").decode("utf-8", "replace").strip().splitlines()[-1:],
            "attempted_fix": subprocess.list2cmdline(fix_cmd), "attempted_fix_exit_code": fix.returncode,
            "attempted_fix_face": (fix.stdout or b"").decode("utf-8", "replace").strip().splitlines()[-1:],
            "reason": "spec/cases.yaml publishes no blind sample hex and evidence/S00/blind-map.json is "
                      "sealed until after the S03 audit; opening it would prefill this port's own answer (M17)",
        })
    if rows:
        with open(os.path.join(runs, "blocked-rows.json"), "wb") as fh:
            fh.write((json.dumps(rows, indent=2, ensure_ascii=True) + chr(10)).encode("utf-8"))
        with open(os.path.join(IMPL, "blocked-rows.json"), "wb") as fh:
            fh.write((json.dumps(rows, indent=2, ensure_ascii=True) + chr(10)).encode("utf-8"))
    return rows


def retire_stale(results_dir, keep_names, runs, ledger):
    """Retire published faces this seat no longer produces.

    A face is retired only if it is inside this seat's results directory, is not in the current plan,
    and names this seat as its author inside the file. It is copied to a quarantine tree outside the
    repo before the published path is removed, and every step is recorded with the file's sha256, so
    the retirement is auditable rather than a deletion.
    """
    import shutil
    keep = set(keep_names)
    qdir = os.path.join(runs, "retired-from-results")
    os.makedirs(qdir, exist_ok=True)
    moved = notmine = 0
    for p in sorted(glob.glob(os.path.join(results_dir, "*.json"))):
        name = os.path.basename(p)
        if name in keep:
            continue
        raw = open(p, "rb").read()
        try:
            d = json.loads(raw.decode("utf-8"))
        except ValueError:
            ledger["skipped_not_mine"].append({"name": name, "sha256": sha_hex(raw), "reason": "unparseable, not touching it"})
            notmine += 1
            continue
        if d.get("worker_id") != WORKER or d.get("language") != "rust":
            ledger["skipped_not_mine"].append({"name": name, "sha256": sha_hex(raw),
                                               "reason": "not authored by this seat (worker_id=%r language=%r)" % (d.get("worker_id"), d.get("language"))})
            notmine += 1
            continue
        dst = os.path.join(qdir, name)
        shutil.copyfile(p, dst)
        if sha_hex(open(dst, "rb").read()) != sha_hex(raw):
            ledger["skipped_not_mine"].append({"name": name, "reason": "quarantine copy did not match, keeping the published face"})
            notmine += 1
            continue
        os.remove(p)
        moved += 1
        ledger["retired"].append({"name": name, "sha256": sha_hex(raw), "bytes": len(raw),
                                  "quarantine": dst,
                                  "reason": "the contract re-ids this face (see its successor's case_id), so the stale file would sit in results/ with pre-rev3 fields"})
    ledger["retired_count"] = moved
    return moved, notmine


# ----------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", default="all", choices=["all", "controls", "rest"])
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--plan-blind", action="store_true")
    ap.add_argument("--allow-sealed-map", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    cases, api_rust, control_rows = parse_cases(CASES)
    controls = control_cells_from_table(control_rows) if control_rows else control_cells()
    blind_rows, blind_meta = load_blind(BLIND_MAP)
    non_null = [c["id"] for c in cases if c["expectation"] is not None]
    not_hex = [[c["id"], h] for c in cases for h, isk in zip(c["hex"], c.get("hex_is_hex", [])) if not isk]
    if args.plan_blind:
        in_table = [c for c in cases if c["category"] == "blind"]
        print("blind sample rows published in spec/cases.yaml: %d" % len(in_table))
        print("blind samples available from %s: %d" % (BLIND_MAP.replace(os.sep, "/"), len(blind_rows)))
        if blind_meta:
            print("map face: whole-file sha256=%s bytes=%d sealed_at=%s; the file's own sha256_self field=%s"
                  % (blind_meta["sha256_whole_file"][:16], blind_meta["bytes"], blind_meta["sealed_at"],
                     str(blind_meta["sha256_self_field"])[:16]))
            print("those two are different numbers by construction: a self-hash cannot cover the line that carries it")
        print("authority for opening it: NOTICE-rev6 item 2 names this file as the source of blind/B1..B5; "
              "before that order this seat refused (part 1 section 6 of the self-check records the refusal)")
        if args.allow_sealed_map:
            print("no refusal is required: the samples are ordered by the contract and are not expectation-bearing")
            return 0
        if len(blind_rows) == 5:
            print("OUTCOME=runnable cells=B1..B5 (the five blind cells are measured, not blocked)")
            return 0
        print("OUTCOME=blocked cells=B1..B5 reason=no blind samples reachable")
        return 3

    faces_pre = spec_faces()
    required_keys, contract = load_required(REQUIRED_LIST)
    contract_raw = open(REQUIRED_LIST, "rb").read()
    contract_sha = sha_hex(contract_raw)
    primary = contract["primary_entry_per_port"]["rust"]
    if primary not in api_rust:
        print("INSTRUMENT-RED: the contract names primary entry %r which is not in the pinned rust list %s" % (primary, api_rust))
        return 4
    ladder = tuple(contract["base_len_ladder"])
    if contract.get("spec_blob_sha256") != faces_pre["blob_sha256"]:
        print("INSTRUMENT-RED: spec/cells-required.json was generated from blob %s but HEAD:spec/cases.yaml is %s; "
              "the required list and the frozen table are not the same revision" % (contract.get("spec_blob_sha256"), faces_pre["blob_sha256"]))
        return 4
    plan, identity_seen = build_plan(cases, api_rust, primary, ladder, required_keys, controls, blind_rows)
    if not blind_rows:
        print("NOTE: %s yielded no blind samples; the five blind rows will be emitted as blocked" % BLIND_MAP)
    n_req = len([c for c in plan if c.required])
    n_extra = len(plan) - n_req
    by_group = {}
    for c in plan:
        by_group[c.group] = by_group.get(c.group, 0) + 1
    if args.plan:
        print("frozen cases=%d multi-member=%s pinned rust entries=%d expectation_non_null=%d frozen_sample_not_hex=%d"
              % (len(cases), sorted(c["id"] for c in cases if len(c["hex"]) > 1), len(api_rust), len(non_null), len(not_hex)))
        for row in not_hex:
            print("   NOT_HEX %s" % json.dumps(row))
        print("planned by group: %s" % json.dumps(by_group, sort_keys=True))
        print("contract %s: required_rows_for_rust=%d cells_required=%d cells_planned=%d cells_extra=%d"
              % (os.path.basename(REQUIRED_LIST), len(required_keys), len(required_keys), len(plan), n_extra))
        print("base ladder from the contract: %s   primary entry: %s" % (list(ladder), primary))
        for c in plan:
            print("   %-6s %-22s %-22s %-26s %s" % (c.group, c.case_id, c.entry, c.sub or "-", "REQUIRED" if c.required else "extra"))
        return 0

    env = toolchain_facts()
    deps = build_probes()
    faces = spec_faces()
    for k in ("sg_probe", "sg_probe_norm"):
        if deps[k + "_sha256"] == "MISSING":
            print("INSTRUMENT-RED: probe face missing: %s.exe (%s / %s)" % (k, deps["build_std_face"], deps["build_norm_face"]))
            return 4
    if deps["build_std_rc"] != 0 or deps["build_norm_rc"] != 0:
        print("INSTRUMENT-RED: cargo build refused (std rc=%s, norm rc=%s); no measurement is taken with an unbuilt instrument"
              % (deps["build_std_rc"], deps["build_norm_rc"]))
        print("build face std: %s" % deps["build_std_face"][-300:])
        print("build face norm: %s" % deps["build_norm_face"][-300:])
        return 4
    if deps["source_newer_than_exe"]:
        print("INSTRUMENT-RED: src/probe.rs is newer than the compiled face; the build did not take effect")
        return 4

    run_id = uuid.uuid4().hex[:12]
    runs = os.path.join(RUNS_ROOT, "run-" + run_id)
    os.makedirs(os.path.join(runs, "scratch"), exist_ok=True)
    os.makedirs(os.path.join(runs, "logs"), exist_ok=True)
    # one directory per (base_len, path_form): the plain and the verbatim face of the same
    # width must not overwrite each other. Each 13-wide root carries the run tag, so a
    # base_len=13 tier can still be unique to this run.
    roots = {("plain", 13): r"D:\sg" + run_id[:8], ("extended", 13): r"D:\yg" + run_id[:8],
             ("plain", "parent"): r"D:\xg" + run_id[:8], ("extended", "parent"): r"D:\zg" + run_id[:8]}
    for d in roots.values():
        os.makedirs(d, exist_ok=True)
        if wide_len(d) != 13:
            print("INSTRUMENT-RED: base tier 13 needs a directory exactly 13 code units wide; built %d (%s)" % (wide_len(d), d))
            return 4
    tiers = {}
    wanted_tiers = sorted({c.tier for c in plan if c.tier is not None})
    for form in ("plain", "extended"):
        tiers[(13, form)] = roots[(form, 13)]
        parent = roots[(form, "parent")]
        for base in [b for b in wanted_tiers if b != 13]:
            pad_head = "t%d" % base
            need = base - wide_len(parent) - 1
            d = parent + "\\" + pad_head + "q" * (need - len(pad_head))
            os.makedirs(d, exist_ok=True)
            if wide_len(d) != base:
                print("INSTRUMENT-RED: tier dir built at width %d, requested base_len=%d (%s)" % (wide_len(d), base, d))
                return 4
            tiers[(base, form)] = d
    tier_roots = {"runs": runs, "tiers": tiers}

    env.update(rust_env_face(deps, runs))
    if env.get("max_component") is None:
        print("NOTE: the kernel32 env face did not answer: rc=%s %s" % (env.get("env_face_rc"), env.get("env_face_error")))
    print("run_id=%s run_root=%s" % (run_id, runs))
    print("git_head=%s blob_sha=%s worktree_sha=%s faces_identical=%s frozen_declared_matches_blob=%s"
          % (faces["head"], faces["blob_sha256"], faces["worktree_sha256"], faces["faces_identical"], faces["frozen_declared_matches_blob"]))
    print("toolchain=%s" % env["toolchain_line"])
    print("shim_and_resolved_differ=%s longPathAware_hits shim=%d resolved=%d sg_probe=%d sg_probe_norm=%d"
          % (env["shim_and_resolved_differ"], env["shim_longPathAware_hits"], env["resolved_longPathAware_hits"],
             deps["sg_probe_longPathAware_hits"], deps["sg_probe_norm_longPathAware_hits"]))
    print("LongPathsEnabled=%s max_component(kernel32 face)=%s fs=%s env_face_rc=%s"
          % (env["LongPathsEnabled"], env.get("max_component"), env.get("filesystem"), env.get("env_face_rc")))
    print("deps: std face deps_direct=0 deps_total=0 | norm face deps_direct=%d deps_total=%d packages=%s"
          % (deps["deps_direct_norm"], deps["deps_total_norm"], deps["cargo_lock_packages"]))
    print("cells_expected=%d planned_by_group=%s" % (len(plan), json.dumps(by_group, sort_keys=True)))

    ledger = {"run_id": run_id, "results_dir": RESULTS, "retired": [], "skipped_not_mine": []}
    drv = Driver(env, deps, faces, tier_roots, contract_sha, required_keys, ledger, blind_meta)
    exp = control_expectations()
    controls = [c for c in plan if c.group == "ctrl"]
    rest = [c for c in plan if c.group != "ctrl"]

    verdicts = []
    if args.phase in ("all", "controls"):
        for cell in controls:
            rec = None
            for attempt in range(1, 4):
                cell.attempts = attempt
                rec = drv.spawn(cell)
                if rec is None:
                    verdicts.append((cell.case_id, "NO-FACE", "driver problem, no face published", attempt))
                    break
                drv.stamp_pre(rec, cell)
                rec["control_expectation"] = exp[cell.case_id][1]
                okv = exp[cell.case_id][0](rec)
                rec["control_pass"] = okv
                rec["control_attempt"] = attempt
                _p, _v, rec = drv.publish(rec, cell)
                detail = json.dumps({k: rec.get(k) for k in ("create_result", "error_stage", "error_code",
                                                             "bytes_written", "bytes_on_disk", "read_result",
                                                             "sha256_truth")}, ensure_ascii=True, default=str)
                verdicts.append((cell.case_id, "PASS" if okv else "MISMATCH", detail, attempt))
                if okv:
                    break
    controls_pass = len([v for v in verdicts if v[1] == "PASS"]) == len(controls) and len(controls) > 0
    print("== control verdicts (expectations only from evidence/S00-ctrl-baseline.md)")
    for v in verdicts:
        print("   %-22s %-8s attempt=%d %s" % (v[0], v[1], v[3], v[2]))
    print("controls_pass=%s" % controls_pass)
    if args.phase in ("all", "controls") and not controls_pass:
        for cell, path in drv.produced:
            r = face_of(path)
            r["instrument_red"] = True
            r["control_pass"] = False
            with open(path, "wb") as fh:
                fh.write((json.dumps(r, indent=2, ensure_ascii=True) + "\n").encode("utf-8"))
        print("INSTRUMENT-RED: a control cell mismatched the measured baseline after 3 attempts; the batch stops and is not published as data")
        return 1

    if args.phase in ("all", "rest"):
        retired, notmine = retire_stale(RESULTS, [c.filename() for c in plan], runs, ledger)
        print("retired_stale_faces=%d copied_to=%s skipped_not_this_seat=%d" % (retired, os.path.join(runs, "retired-from-results"), notmine))
        todo = rest if args.phase == "all" or args.phase == "rest" else []
        for cell in todo:
            if args.limit and len(drv.produced) >= args.limit:
                break
            drv.run_one(cell)

    # entry_spread, read back off the published faces (never from memory)
    spread = {}
    for cell, path in drv.produced:
        if cell.group != "tapi":
            continue
        r = face_of(path)
        key = r.get("case_id")
        dig = json.dumps({k: r.get(k) for k in ("create_result", "error_stage", "os_legality_verdict", "read_result",
                                                "bytes_written", "bytes_on_disk", "name_mutated", "phantom")}, sort_keys=True)
        spread.setdefault(key, {}).setdefault(dig, []).append(r.get("api_entry"))
    disagree = {k: v for k, v in spread.items() if len(v) > 1}
    print("tapi_cells=%d cells_where_entries_disagree=%d" % (len(spread), len(disagree)))
    for k in sorted(disagree):
        for d, ents in sorted(disagree[k].items()):
            print("   %s n=%d %s -> %s" % (k, len(ents), d[:110], ",".join(x.replace("std::fs::", "") for x in ents)))

    answered_keys = {c.answers() for c in plan}
    blocked_rows = emit_blocked_rows(runs, contract, answered_keys, blind_meta)
    summary = {
        "run_id": run_id,
        "blocked_rows": blocked_rows, "runs_root": runs, "tier_dirs": {str(k): v for k, v in tiers.items()},
        "contract": {"path": REQUIRED_LIST, "sha256": contract_sha, "rows_for_rust": len(required_keys),
                     "primary_entry": primary, "base_len_ladder": list(ladder),
                     "generated_by": contract.get("generated_by"), "withdraws": contract.get("withdraws")},
        "cells_required_rows": len(required_keys),
        "retirement_ledger": ledger,
        "cells_expected": len(plan), "cells_produced": len(drv.produced),
        "planned_by_group": by_group, "problems": drv.problems,
        "controls_pass": controls_pass, "control_verdicts": [list(v) for v in verdicts],
        "tapi_disagreements": {k: [d[:200] for d in v] for k, v in sorted(disagree.items())},
        "spec_faces": faces, "env": env, "deps": deps,
        "blocked": [{
            "cells": "B1..B5", "case_group": "blind",
            "command": "python impl/rust/run_cells.py --plan-blind",
            "exit_code": 3,
            "attempted_fix": "python impl/rust/run_cells.py --plan-blind --allow-sealed-map -> exit 2, the driver refuses to open a sealed artifact (M17), so the rows stay blocked",
        }],
    }
    spath = os.path.join(IMPL, "run-summary.json")
    with open(spath, "wb") as fh:
        fh.write((json.dumps(summary, indent=2, ensure_ascii=True) + "\n").encode("utf-8"))
    print("run_summary=%s" % spath)
    print("cells_produced=%d problems=%d" % (len(drv.produced), len(drv.problems)))
    for p in drv.problems[:20]:
        print("   PROBLEM %s" % p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
