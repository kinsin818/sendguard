#!/usr/bin/env python3
"""SENDGUARD S02 python port -- planner + parent driver (the seat's runner).

    python impl/python/sg_run.py                 # full batch
    python impl/python/sg_run.py --plan          # print the plan, touch nothing
    python impl/python/sg_run.py --cells T01,T-CTRL-ASCII   # subset (smoke test)

What it does:
  * reads the frozen question set from the COMMITTED blob face of spec/cases.yaml
    (git cat-file), so the names measured are the names in history;
  * builds one cell per (case_group, case_id, sub_identity);
  * gives every cell one fresh uuid scratch directory, verified empty before use;
  * runs every probe as a child process with an externally enforced 5-second
    timeout (subprocess timeout, shell=False, argv list only);
  * assembles the cell record and writes results/python.windows.x64/*.json.

It never deletes anything (red line M19), never reads another lane's code or
results, and has no third-party dependency.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
RESULTS = os.path.join(REPO, "results", "python.windows.x64")
PROBE = os.path.join(HERE, "sg_probe.py")
PROBE_ZIP = os.path.join(HERE, "sg_probe_zip.py")
PY = sys.executable
TIMEOUT_S = 5.0
HARNESS_VERSION = "sg-python-s02-rederive-1"
CONTRACT_REV = "rev4 (298d6e4: rulers aligned, read_result not_applicable, gate honours " \
               "declared sub_identity and excludes extra cells)"
IMPLEMENTATION_ID = "python-port"

SCRATCH_TEMP = os.path.join(tempfile.gettempdir(), "sendguard-run")
SCRATCH_SHORT = "D:\\g"          # rev2 anchor, kept only to label the older extra cells
REQUIRED_BASES = [78, 120, 200]  # spec/cells-required.json base_len_ladder (rev3)
# rev7 pins what the two length components are made of. Parsed from the
# committed spec face; the value here is only a default that parse_len_fill
# overwrites after asserting it matches.
LEN_FILL_UNIT = "a"
LEN_FILL_HEX = "61"
EXT = "\\\\?\\"

PINNED_ENTRIES = ["open_wb", "os.mkdir", "pathlib.write_bytes", "os.rename"]
PRIMARY_ENTRY = "open_wb"

# Control-cell names and payloads come from `control_samples` in spec/cases.yaml
# (pinned by contract rev6). Before the pin, this seat took the CANON name from
# harness/ctrl-baseline.mjs -- which is exactly the hole rev6 closed: four ports
# spelled four different names, and two different payloads were hashed under
# T-CTRL-CANON. CTRL_NAMES is filled at run time from the committed blob face.
CTRL_NAMES = {}
CTRL_SAMPLES = {}
CTRL_PAYLOAD_HEX = None
CTRL_ORDER = ["T-CTRL-NAMETOOLONG", "T-CTRL-ASCII", "T-CTRL-ILLEGAL-CHAR",
              "T-CTRL-PARSE", "T-CTRL-CANON"]

CTRL_EXPECT = {
    "T-CTRL-NAMETOOLONG": {"create_result": "err_at_syscall", "error_stage": "syscall"},
    "T-CTRL-ASCII": {"create_result": "ok", "bytes_written": 28, "bytes_on_disk": 28,
                     "read_result": "ok", "roundtrip_ok": True},
    "T-CTRL-ILLEGAL-CHAR": {"create_result": "err_at_syscall", "error_stage": "syscall"},
    "T-CTRL-PARSE": {"create_result": "err_at_parse", "error_stage": "parse"},
    "T-CTRL-CANON": {"create_result": "ok", "read_result": "ok", "roundtrip_ok": True},
}
CTRL_BASELINE_SHA = "c9fe45b2fee8ea846f0cf4f2cacc2a891e7b082e7719923502d12a9813e21994"
CTRL_MECH = {"T-CTRL-NAMETOOLONG": "component_length_limit",
             "T-CTRL-ASCII": "unknown", "T-CTRL-ILLEGAL-CHAR": "illegal_char_filter",
             "T-CTRL-PARSE": "control_char_handling", "T-CTRL-CANON": "unknown"}

RESERVED = {"reserved_device_name"}


# ---------------------------------------------------------------- frozen spec
def git_blob(path, ref="HEAD"):
    r = subprocess.run(["git", "-C", REPO, "cat-file", "blob", "%s:%s" % (ref, path)],
                       capture_output=True)
    if r.returncode != 0:
        raise SystemExit("FATAL git cat-file %s:%s rc=%d %s" %
                         (ref, path, r.returncode, r.stderr[:120]))
    return r.stdout, r.returncode


def yval(s):
    """Split a YAML scalar from its trailing comment.

    cases.yaml carries a prose annotation beside every hex sample. Taking the
    comment along with the value would put a prose-derived name into the
    measurement, which N12 forbids -- so the hex and the comment are kept apart,
    and the comment is used only as a cross-check that the parser took the right
    token.
    """
    s = s.strip()
    comment = ""
    if s.startswith('"'):
        m = __import__("re").match(r'"((?:[^"\\]|\\.)*)"', s)
        val = m.group(1) if m else s.strip('"')
        rest = s[len(val) + 2:]
        comment = rest.split("#", 1)[1].strip() if "#" in rest else ""
    elif "#" in s:
        val, _, comment = s.partition("#")
        val, comment = val.strip(), comment.strip()
    else:
        val = s
    return val, comment



def parse_cases(blob_text):
    """Minimal reader for the shapes present in spec/cases.yaml.

    stdlib only (no pyyaml on this box). Returns (cases, top, control_cells).
    """
    import re
    head, _, tail = blob_text.partition("\ncases:\n")
    top = {}
    for m in re.finditer(r"(?m)^([a-z_]+):\s*(.+)$", head):
        top[m.group(1)] = yval(m.group(2))[0]
    # the api_entry lists are indented two spaces under api_entry:
    for m in re.finditer(r"(?m)^  (\w+): \[([^\]]*)\]$", head):
        top[m.group(1)] = [yval(x)[0] for x in m.group(2).split(",") if x.strip()]
    ctrl = re.findall(r"(?m)^  - (T-CTRL-[A-Z0-9-]+)\s*$", head)
    cases = []
    cur = None
    key = None
    for ln in tail.split("\n"):
        if ln.startswith("  - id: "):
            cur = {"id": ln.split(":", 1)[1].strip(), "sample_hex_list": [], "_comments": []}
            cases.append(cur)
            key = None
            continue
        if cur is None:
            continue
        st = ln.strip()
        if st.startswith("- ") and key == "sample_hex_list":
            v, cm = yval(st[2:])
            cur["sample_hex_list"].append(v)
            cur["_comments"].append(cm)
            continue
        if ":" in st:
            k, _, v = st.partition(":")
            k = k.strip()
            val, cm = yval(v)
            key = k
            if k == "sample_hex_list":
                continue
            cur[k] = val
            if k == "sample_hex":
                cur["sample_hex_list"] = [val]
                cur["_comments"] = [cm]
    return cases, top, ctrl




def is_hex(s):
    if not s or len(s) % 2:
        return False
    return all(ch in "0123456789abcdef" for ch in s.lower())


def audit_parse(cases, top, ctrl):
    """Assert the parse before measuring anything (denominator discipline).

    Returns (problems, notes). A non-hex sample is only allowed on T17/T18,
    whose sample_hex is a length-bisection marker and not a name at all.
    """
    problems, notes = [], {}
    ids = [c["id"] for c in cases]
    want = ["T%02d" % i for i in range(1, 21)]
    if ids != want:
        problems.append("case ids=%r != frozen %r" % (ids, want))
    confirmed = 0
    for c in cases:
        if c.get("expectation") not in (None, "null"):
            problems.append("%s expectation is not null: %r" % (c["id"], c.get("expectation")))
        if not c["sample_hex_list"]:
            problems.append("%s carries no sample" % c["id"])
        for i, h in enumerate(c["sample_hex_list"]):
            cm = (c.get("_comments") or [""] * 99)[i]
            if not is_hex(h):
                if c["id"] in ("T17", "T18"):
                    notes.setdefault("prose_marker_cases", []).append(
                        {"id": c["id"], "marker": h})
                    continue
                problems.append("%s member %d is not UTF-8 hex: %r" % (c["id"], i, h))
                continue
            try:
                nm = bytes.fromhex(h).decode("utf-8")
            except Exception as e:
                problems.append("%s sample hex undecodable: %s (%s)" % (c["id"], h, e))
                continue
            if not nm:
                problems.append("%s member %d decodes to an empty name" % (c["id"], i))
            if cm and cm == nm:
                confirmed += 1
        if len(c["sample_hex_list"]) > 1:
            notes.setdefault("multi_member_cases", []).append(
                {"id": c["id"], "members": len(c["sample_hex_list"])})
    if top.get("python") != PINNED_ENTRIES:
        problems.append("pinned python entries %r != %r" % (top.get("python"), PINNED_ENTRIES))
    if len(ctrl) != 5:
        problems.append("control cells parsed %d != 5" % len(ctrl))
    notes["comment_literal_confirmed"] = "%d of %d members" % (
        confirmed, sum(len(c["sample_hex_list"]) for c in cases
                       if c["id"] not in ("T17", "T18")))
    notes["trap_cases_with_hex"] = len([c for c in cases if c["id"] not in ("T17", "T18")])
    return problems, notes




# ---------------------------------------------------------------- scratch
def fresh_dir(prefix_len=None, root=None):
    """One fresh directory, verified empty. Never deleted (M19)."""
    root = root or SCRATCH_TEMP
    os.makedirs(root, exist_ok=True)
    for _ in range(6):
        tag = uuid.uuid4().hex[:8] if prefix_len is None else uuid.uuid4().hex[:prefix_len]
        d = os.path.join(root, tag)
        if os.path.exists(d):
            if os.path.isdir(d):
                try:
                    if len(os.listdir(d)) == 0:
                        return d, True
                except OSError:
                    pass
            continue
        os.makedirs(d)
        return d, True
    raise RuntimeError("could not build a fresh scratch dir under %s" % root)


def build_base(cell_dir, base_len):
    """Extend cell_dir until its path length is exactly base_len."""
    cur = cell_dir
    guard = 0
    while len(cur) < base_len:
        guard += 1
        if guard > 64:
            return None, "guard-exceeded"
        need = base_len - len(cur) - 1
        if need < 1:
            return None, "unreachable"
        take = min(need, 255)
        cand = os.path.join(cur, "b" * take)
        try:
            os.makedirs(cand, exist_ok=True)
        except OSError as e:
            return None, "makedirs-failed:%s(winerror=%s)" % (type(e).__name__,
                                                              getattr(e, "winerror", None))
        cur = cand
    if len(cur) != base_len:
        return None, "overshot"
    if len(os.listdir(cur)) != 0:
        return None, "base-not-empty"
    return cur, None


def parse_len_fill(cases_text):
    """rev7: read the pinned length filler from the committed spec face."""
    global LEN_FILL_UNIT, LEN_FILL_HEX
    import re
    head = cases_text.split("\ncases:")[0]
    block = head.split("len_fill:")[-1] if "len_fill:" in head else ""
    unit = applies = nsr = None
    # explicit, because these values contain spaces and a '#' comment
    for ln in block.split("\n"):
        s = ln.strip()
        if s.startswith("unit_hex:"):
            unit = yval(s[len("unit_hex:"):])[0]
        elif s.startswith("applies_to:"):
            applies = [x.strip() for x in yval(s[len("applies_to:"):])[0].strip("[]").split(",")]
        elif s.startswith("name_source_rule:"):
            nsr = yval(s[len("name_source_rule:"):])[0]
    if not unit or len(bytes.fromhex(unit)) != 1:
        raise SystemExit("FATAL len_fill.unit_hex missing or not one code unit: %r" % unit)
    if applies != ["T17", "T18"]:
        raise SystemExit("FATAL len_fill.applies_to unexpected: %r" % applies)
    LEN_FILL_UNIT = bytes.fromhex(unit).decode("utf-8")
    LEN_FILL_HEX = unit
    return {"unit_hex": unit, "unit_codepoint": "U+%04X" % ord(LEN_FILL_UNIT),
            "applies_to": applies, "name_source_rule": nsr,
            "read_from": "git cat-file blob HEAD:spec/cases.yaml len_fill"}


def len_name_hex(base_len):
    """The pinned component: one code unit repeated base_len times, nothing appended."""
    return LEN_FILL_HEX * base_len


def name_of_len(comp_len, seed=None):
    """A legal component of exactly comp_len code units, made of the pinned unit."""
    if comp_len < 1:
        return None
    return LEN_FILL_UNIT * comp_len


# ---------------------------------------------------------------- run a leg
def run_child(script, task, out_path, io_dir):
    """One probe = one child process, 5-second external timeout, shell=False.

    Task and result files live in a sibling `-io` directory, never inside the
    directory being measured.
    """
    task_path = os.path.join(io_dir, "task-%s.json" % uuid.uuid4().hex[:8])
    with open(task_path, "wb") as fh:
        fh.write(json.dumps(task, ensure_ascii=True, sort_keys=True).encode("utf-8"))
    argv = [PY, script, "--task", task_path, "--out", out_path]
    t0 = time.monotonic()
    status = {"rc": None, "timed_out": False, "stdout_tail": "", "stderr_tail": "",
              "error": None}
    try:
        cp = subprocess.run(argv, capture_output=True, timeout=TIMEOUT_S, shell=False)
        status["rc"] = cp.returncode
        status["stdout_tail"] = cp.stdout.decode("utf-8", "replace")[-200:]
        status["stderr_tail"] = cp.stderr.decode("utf-8", "replace")[-400:]
    except subprocess.TimeoutExpired as te:
        status["timed_out"] = True
        status["stderr_tail"] = (te.stderr or b"").decode("utf-8", "replace")[-200:] if te.stderr else ""
    except Exception as e:
        status["error"] = "%s: %s" % (type(e).__name__, str(e)[:200])
        status["rc"] = -1
    elapsed = int((time.monotonic() - t0) * 1000)
    docs = None
    if os.path.isfile(out_path):
        try:
            docs = json.loads(open(out_path, "rb").read().decode("utf-8"))
        except Exception as e:
            docs = {"phase": "unreadable", "results": [], "read_error": str(e)[:120]}
    return docs, status, elapsed, argv


def payload_of(meta):
    return meta["payload_hex"]


def build_zip_bytes(entry_hex_list, payload_hex):
    """Compose the archive that T16 measures, IN MEMORY (no filesystem access).

    T16's own sample is pure ASCII and cannot set ZIP flag bit 11, so the
    archive holds two entries: the T16 sample and the T06 sample. Composing the
    sample is not a probe -- every probe is still one child process -- so the
    bytes are built here with stdlib zipfile and handed to the child as payload.
    """
    import io
    import zipfile
    payload = bytes.fromhex(payload_hex)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for hx in entry_hex_list:
            nm = bytes.fromhex(hx).decode("utf-8")
            zi = zipfile.ZipInfo(nm, date_time=(2026, 10, 11, 12, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(zi, payload)
    return buf.getvalue().hex()



def run_leg(it, entry, leg_dir, io_dir, meta, idx, name_hex=None):
    """Spawn one child for one (cell leg x entry) and salvage its record."""
    names = [name_hex] if name_hex else it["name_hexes"]
    out = os.path.join(io_dir, "out-%d-%s.json" % (idx, uuid.uuid4().hex[:6]))
    task = {"dir": leg_dir, "entry": entry, "name_hex_list": names,
            "payload_hex": it.get("payload_hex_override") or payload_of(meta),
            "path_form": it["path_form"],
            "reserved": bool(it.get("reserved")),
            "zip_report": bool(it.get("zip_report")),
            "zip_content_hex": it.get("zip_content_hex"),
            "zip_expect_entry_hex": it.get("zip_expect", [])}
    docs, status, elapsed, argv = run_child(PROBE, task, out, io_dir)
    recs, phase = salvage(docs, status, elapsed, names)
    return recs, status, elapsed, argv, phase


def salvage(docs, status, elapsed, name_hex_list):
    """Turn a child document (possibly partial, possibly a timeout) into records."""
    recs, phase = [], (docs or {}).get("phase", "none")
    got = (docs or {}).get("results", [])
    for i in range(len(name_hex_list)):
        if i < len(got):
            recs.append(dict(got[i]))
        else:
            recs.append({"member_index": i, "requested_name_hex": name_hex_list[i],
                         "phases_reached": [], "create_result": None})
    for rec in recs:
        pr = rec.get("phases_reached") or []
        if status["timed_out"]:
            if "created" not in pr and rec.get("create_result") is None:
                rec["create_result"] = "hang"
                rec["hang_phase"] = "create"
            elif "read" not in pr and rec.get("read_result") is None and \
                    rec.get("create_result") == "ok":
                rec["read_result"] = "hang"
                rec["hang_phase"] = "read_or_later"
        if rec.get("probe_crashed"):
            rec["create_result"] = None
        rec["_elapsed_child"] = rec.get("elapsed_ms_child")
    return recs, phase


# ---------------------------------------------------------------- cell build
def base_fields(spec, run_meta):
    c = {
        "format_version": 1,
        "case_id": spec["case_id"],
        "case_group": spec["case_group"],
        "language": "python",
        "os": "windows",
        "os_version": run_meta["os"]["os_version"],
        "arch": run_meta["os"]["arch"],
        "locale": run_meta["locale"],
        "interpreter_resolved": run_meta["interpreter"]["resolved_executable"],
        "api_entry": spec["api_entry"],
        "attempt": 1,
        "sub_identity": spec["sub_identity"],
        "sub_identity_order": list(spec["sub_identity"].keys()),
        "name_source": spec["name_source"],
        "name_source_kind": spec["name_source_kind"],
        "path_form": spec["path_form"],
        "longpath_mechanism": spec["longpath_mechanism"],
        # rev3: length_unit is the unit THIS port counts lengths in -- python's
        # len(str) counts code points, and every length field here comes from it.
        # name_encoding is how the record spells the name bytes: raw UTF-8 hex.
        "length_unit": "code_points",
        "length_unit_basis": "len(python str) == code points; the utf16/utf8 counts are published beside it in len_triple, never used as the reported length",
        "name_encoding": "hex_raw_bytes",
        # every varying dimension also sits at the top level: spec/cell-identity.md
        # section 1 says a dimension that varies "must appear as a named field
        # inside the cell", and ci/equality.py reads sub-identity dimensions from
        # the cell's own fields (SUB_FIELDS), not from a nested object.
        "sub_identity_fields_top_level": sorted(spec["sub_identity"].keys()),
        "mechanism_class": spec["mechanism_class"],
        "harness_version": HARNESS_VERSION,
        # rev6 names this field for a cell that could not be run at all. Note for
        # the contract: "measured"/"blocked" are not words in spec/canonical.md
        # section 1, whose closed set is valid/void/instrument_red -- see the
        # self-check report, defect list.
        "run_status": "measured",
        "run_status_basis": "measured = both legs ran, or ran and produced an OS answer; "
                            "blocked = the cell could not be run, with command+exit code+fix",
        "contract_rev_seen": CONTRACT_REV,
        "implementation_id": IMPLEMENTATION_ID,
        "spec_sha256": run_meta["spec_sha256"],
        "spec_face": run_meta["spec_face"],
        "env": run_meta["env"],
        "deps_direct": 0,
        "deps_total": 0,
        "deps_basis": "imports are stdlib only (argparse ctypes hashlib json os pathlib stat sys time uuid zipfile shutil); third-party count = 0",
        "scratch_root": spec["scratch_root"],
        "scratch_dir": spec["scratch_dir"],
        "scratch_verified_empty": spec["scratch_verified_empty"],
        "cleanup_attempted": False,
        "probe_timeout_s": TIMEOUT_S,
        "child_spawn_form": "subprocess.run(argv list, shell=False, timeout=5.0); one child per probe",
        "cleanup_note": "M19: no deletion logic exists in this port; run dirs accumulate outside the repo",
        "instrument_red": False,
        "instrument_conflict": False,
        "entries_run": spec.get("entries_run", [PRIMARY_ENTRY]),
        "primary_entry": PRIMARY_ENTRY,
        "error_stage_rule": "non-OSError raised before the syscall -> parse; OSError carrying errno/winerror -> syscall (fs/tool unused, see selfcheck)",
    }
    for k, v in spec["sub_identity"].items():
        c[k] = v
    return c


def fill_from_record(cell, rec, spec, controls_ok):
    """Map one probe record onto the cell's canonical fields."""
    cell["phases_reached"] = rec.get("phases_reached", [])
    cell["requested_triple"] = rec.get("requested_triple")
    cell["landed_triple"] = rec.get("landed_triple")
    cell["len_triple"] = {"requested": rec.get("requested_triple"),
                          "landed": rec.get("landed_triple")}
    cell["bytes_written"] = rec.get("bytes_written")
    cell["bytes_on_disk"] = rec.get("bytes_on_disk")
    cell["name_landed_as"] = rec.get("name_landed_as_hex")
    cell["landed_linkage"] = rec.get("landed_linkage")
    cell["new_entries_hex"] = rec.get("new_entries_hex")
    cell["residual_src_new_entries"] = rec.get("residual_src_new_entries")
    cell["pre_existing_entries"] = rec.get("pre_existing_entries")
    cell["same_name_hits"] = rec.get("same_name_hits")
    cell["dir_view_count"] = rec.get("dir_view_count")
    cell["dir_view"] = rec.get("dir_view")
    cell["residual_src_entries"] = rec.get("residual_src_entries")
    cell["path_view"] = rec.get("path_view")
    cell["os_legality_verdict"] = rec.get("os_legality_verdict") or "unknown"
    cell["os_legality_detail"] = rec.get("os_legality_detail")
    # rev3: a verdict must name the tool asked. This port asks Win32 directly
    # (kernel32.GetFileAttributesW through ctypes); where no tool was reached at
    # all -- the zip-extract legs, and any name a wide string cannot carry --
    # the honest value is "none".
    detail = rec.get("os_legality_detail") or {}
    probe = str(detail.get("probe", ""))
    cell["verdict_via"] = "win32" if probe.startswith("GetFileAttributesW") else "none"
    cell["verdict_via_detail"] = ("kernel32.GetFileAttributesW via ctypes, extended prefix, "
                                  "parser bypassed" if cell["verdict_via"] == "win32"
                                  else "no tool reached: " + (detail.get("outcome")
                                                              or "legality not probed in this leg"))
    cell["win32_fullpath"] = rec.get("win32_fullpath")
    cell["delivered_nothing"] = rec.get("delivered_nothing")
    if rec.get("create_result") is not None:
        cell["create_result"] = rec["create_result"]
        cell["error_stage"] = rec.get("error_stage") or "null"
    for k_src, k_dst in (("error_type", "error_type"), ("error_errno", "error_errno"),
                         ("error_winerror", "error_winerror"),
                         ("error_strerror", "error_strerror"),
                         ("error_message_redacted", "error_message")):
        if rec.get(k_src) is not None:
            cell[k_dst] = rec[k_src]
    if rec.get("error_winerror") is not None or rec.get("error_errno") is not None:
        cell["error_code"] = "%s:errno=%s:winerror=%s" % (rec.get("error_type"),
                                                          rec.get("error_errno"),
                                                          rec.get("error_winerror"))
    if rec.get("read_result") is not None:
        cell["read_result"] = rec["read_result"]
        cell["bytes_read"] = rec.get("bytes_read")
        cell["sha256_self"] = rec.get("sha256_self")
        cell["sha256_truth"] = rec.get("sha256_truth")
        cell["roundtrip_ok"] = bool(rec.get("roundtrip_ok"))
    else:
        if rec.get("read_attempt_outcome") is not None:
            cell["read_attempt_outcome"] = rec["read_attempt_outcome"]
        # rev4 added the fifth read_result word for precisely this case: nothing
        # was read because nothing landed, or the name is a device this project
        # refuses to open. It demands read_skipped_reason alongside it.
        why = rec.get("read_blocked_reason") or "read-unreachable"
        cell["read_result"] = "not_applicable"
        cell["read_skipped_reason"] = why
        cell["cell_blocked"] = True
        cell["blocked_leg"] = "read"
        cell["blocked_reason"] = why
    if rec.get("read_blocked_reason"):
        cell["read_blocked_reason"] = rec["read_blocked_reason"]
    for k in ("enum_to_stat_agrees", "phantom", "name_mutated"):
        if rec.get(k) is not None:
            cell[k] = bool(rec[k])
    if rec.get("zip_report") is not None:
        cell["zip_report"] = rec["zip_report"]
    if rec.get("instrument_conflict"):
        cell["instrument_conflict"] = True
        cell["instrument_conflict_reason"] = rec.get("instrument_conflict_reason")
    cell["artifact_dir_listing_count"] = rec.get("artifact_dir_listing_count")
    cell["attribution_layer"], cell["attribution_layer_basis"] = attribute(cell, spec)
    cell["control_pass"] = bool(controls_ok)
    cell["elapsed_ms"] = spec["elapsed_ms"]
    cell["started_at"] = spec["started_at"]
    return cell


def attribute(cell, spec):
    """Layer per spec/attribution-tree.md, from one port on one OS.

    varies_across_OS is NOT observable from this seat, so the layer is the
    tree's second pass only (same-language entry switch) plus the OS-direct
    verdict; the pending axis is named in the basis string.
    """
    spread = cell.get("entry_spread") or {}
    agree = cell.get("entries_agree_with_primary")
    mech = cell.get("mechanism_class")
    if cell.get("create_result") == "ok" and cell.get("delivered_nothing") is True:
        return "L1", "OS parser routes the name to a device namespace; every python entry behaves alike; varies_across_OS pending"
    if agree is False:
        return "L2", "another stdlib entry of python answers differently (entry_spread disagrees) -> stdlib policy; varies_across_OS pending"
    if spec.get("group_kind") == "len":
        return "L3_interaction", "260-char legacy wall is OS policy that no stdlib entry of python removes, and it shadows NAME_MAX -> interaction cell, reported separately; varies_across_OS pending"
    if mech == "component_length_limit":
        return "L1", "NTFS NAME_MAX is an environment fact, identical across entries; varies_across_OS pending"
    if mech in ("illegal_char_filter", "reserved_device_name", "path_preprocessing_policy"):
        return "L1", "OS-level name policy; same for every entry of this language (entry_spread agrees); varies_across_OS pending"
    if cell.get("name_mutated") is True:
        return "L1", "name rewritten by the OS before it reaches the filesystem; varies_across_OS pending"
    return "L1", "no divergence observed on this port; provisional pending cross-OS data"


AGREE_KEYS = ("create_result", "error_stage", "read_result", "bytes_on_disk",
              "name_landed_as", "os_legality_verdict")


def normalise_view(rec):
    """Project a record onto the fields the entry-agreement test compares."""
    v = {"create_result": rec.get("create_result"),
         "error_stage": rec.get("error_stage") or ("null" if rec.get("create_result") == "ok" else None),
         "read_result": rec.get("read_result"),
         "bytes_on_disk": rec.get("bytes_on_disk"),
         "os_legality_verdict": rec.get("os_legality_verdict")}
    v["name_landed_as"] = rec.get("name_landed_as") or rec.get("name_landed_as_hex")
    return v


def entries_agree(primary, spread):
    """Do the other pinned stdlib entries answer like the primary one?

    A leg with no record at all is excluded and named -- an absent leg is not
    evidence of disagreement, and it must not be counted as agreement either.
    """
    base = normalise_view(primary)
    disagree, dead = [], []
    for e, v in spread.items():
        rec = normalise_view(v)
        if rec["create_result"] is None and rec["error_stage"] is None:
            dead.append(e)
            continue
        if rec != base:
            disagree.append(e)
    return (not disagree), disagree, dead



# ---------------------------------------------------------------- plan
def plan_items(cases, blind):
    """The frozen question set, as one plan item per cell-group.

    Returns a list of items; a 'probe' item with two name_hexes yields two
    cells from ONE coexistence leg (T09's spec_source is coexistence in one
    directory, so its members are deliberately not separated).
    """
    items = []
    for c in cases:
        cid = c["id"]
        if cid in ("T17", "T18"):
            continue
        cat = c.get("category", "unknown")
        reserved = cat in RESERVED
        hexes = c["sample_hex_list"]
        common = {"reserved": reserved, "mech": cat, "category": cat, "path_form": "plain",
                  "lpm": "none", "locale": c.get("locale", "en-US"),
                  "applicable": c.get("applicable", ""), "spec_source": c.get("spec_source", ""),
                  "kind": "trap", "case_id": cid,
                  "name_source_kind": "spec/cases.yaml blob-face sample hex (UTF-8 hex, decoded at run time)"}
        if cid == "T09":
            it = dict(common)
            it.update({"type": "probe", "name_hexes": hexes, "members": len(hexes),
                       "coexist": True,
                       "sub_keys": [],
                       "case_ids": ["%s-m%d" % (cid, i + 1) for i in range(len(hexes))],
                       "subs": [{} for _i in range(len(hexes))],
                       "member_indices": [str(i) for i in range(len(hexes))]})
            items.append(it)
            continue
        if len(hexes) > 1:
            for i, h in enumerate(hexes):
                it = dict(common)
                it.update({"type": "probe", "name_hexes": [h], "members": 1,
                           "sub_keys": [],
                           "case_ids": ["%s-m%d" % (cid, i + 1)],
                           "subs": [{}], "member_indices": [str(i)]})
                items.append(it)
            continue
        it = dict(common)
        it.update({"type": "probe", "name_hexes": hexes, "members": 1, "subs": [{}]})
        if cid == "T16":
            it["zip_report"] = True
            it["zip_expect"] = list(hexes)
            items.append(it)
            for ex in ("zipfile", "shutil"):
                z = dict(common)
                z.update({"type": "zip_extract", "extractor": ex, "subs": [{"packer": "zipfile",
                                                                            "extractor": ex}],
                          "name_source_kind": "spec/cases.yaml blob-face sample hex; entry names "
                                              "are the T16 sample plus the T06 sample (T16's own "
                                              "sample is pure ASCII and cannot exercise bit 11)"})
                items.append(z)
            continue
        items.append(it)

    for cid in CTRL_ORDER:
        name = CTRL_NAMES[cid]
        items.append({"type": "probe", "kind": "ctrl", "case_id": cid,
                      "name_hexes": [name.encode("utf-8").hex()], "members": 1, "subs": [{}],
                      "reserved": False, "mech": CTRL_MECH[cid], "path_form": "plain",
                      "lpm": "none", "locale": "en-US", "applicable": "windows",
                      "spec_source": "spec/cases.yaml control_samples (rev6 pin) + "
                                     "evidence/S00-ctrl-baseline.md for the expectation",
                      "name_source_kind": "control_samples sample_hex, pinned by contract rev6 "
                                          "and decoded at run time",
                      "ctrl": cid})
    for entry in PINNED_ENTRIES:
        items.append({"type": "probe", "kind": "tapi", "case_id": "T-API",
                      "name_hexes": ["434f4e2e747874"], "members": 1,
                      "subs": [{}], "filename_tag": {"api_entry": entry},
                      "single_entry": entry,
                      "reserved": True, "mech": "reserved_device_name", "path_form": "plain",
                      "lpm": "none", "locale": "en-US", "applicable": "windows",
                      "spec_source": "spec/cases.yaml T01 sample, pinned python entry list",
                      "name_source_kind": "spec/cases.yaml T01 sample hex (the sample T-API runs; "
                                          "the frozen spec does not pin which sample T-API uses)"})
    for b in blind:
        items.append({"type": "probe", "kind": "blind", "case_id": "B%d" % b["blind_id"],
                      "name_hexes": [b["name_utf8_hex"]], "members": 1, "subs": [{}],
                      "reserved": False, "mech": "unknown", "path_form": "plain",
                      "lpm": "none", "locale": "en-US", "applicable": "windows",
                      "spec_source": "evidence/S00/blind-map.json",
                      "name_source_kind": "evidence/S00/blind-map.json name_utf8_hex"})

    # rev7: the twelve required length cells. Identity is exactly
    # {base_len, path_form}; the INPUT is the pinned component -- one code unit
    # U+0061 repeated base_len times, nothing appended -- so name_source is
    # 2*base_len hex characters and all three widths of that name are base_len.
    # What the bisection converged to is a different quantity and goes in
    # len_ceiling, never in len_triple. `limit`, `probe` and the holder depths
    # stay data fields, not identity dimensions.
    for cid, limit in (("T17", "path"), ("T18", "component")):
        for b in REQUIRED_BASES:
            for face in ("plain", "extended"):
                items.append({"type": "len_pinned", "kind": "len", "case_id": cid,
                              "base_len": b, "limit": limit, "path_form": face,
                              "lpm": "none" if face == "plain" else "prefix_rewrite",
                              "mech": "component_length_limit", "locale": "en-US",
                              "applicable": "windows",
                              "name_hexes": [len_name_hex(b)], "members": 1,
                              "spec_source": "spec/cases.yaml len_fill + "
                                             "spec/cells-required.json base_len_ladder x path_form",
                              "name_source_kind": "hex of the component actually handed to the API: "
                                                  "len_fill unit U+0061 repeated base_len times, "
                                                  "nothing appended (rev7 pin)",
                              "subs": [{"base_len": b, "path_form": face}],
                              "face_note": "the pinned component is the input of this cell; the "
                                           "ceiling is measured by bisection at the same holder "
                                           "depth in a sibling fresh directory"})
    return items


def count_cells(items):
    n = 0
    for it in items:
        n += len(it["subs"])
    return n


# ---------------------------------------------------------------- env facts
def volume_info(root):
    import ctypes
    from ctypes import wintypes
    name = ctypes.create_unicode_buffer(64)
    fs = ctypes.create_unicode_buffer(64)
    serial = wintypes.DWORD()
    maxc = wintypes.DWORD()
    flags = wintypes.DWORD()
    ok = ctypes.windll.kernel32.GetVolumeInformationW(
        root, name, 64, ctypes.byref(serial), ctypes.byref(maxc),
        ctypes.byref(flags), fs, 64)
    if not ok:
        return {"root": root, "ok": False, "winerror": ctypes.get_last_error()}
    return {"root": root, "ok": True, "filesystem": fs.value,
            "max_component": int(maxc.value), "volume_flags": int(flags.value)}


def longpaths_enabled():
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                           r"SYSTEM\CurrentControlSet\Control\FileSystem")
        v, _t = winreg.QueryValueEx(k, "LongPathsEnabled")
        winreg.CloseKey(k)
        return int(v), "winreg HKLM ...\\FileSystem\\LongPathsEnabled"
    except Exception as e:
        return None, "not-obtainable:%s" % type(e).__name__


def dot3(root):
    try:
        cp = subprocess.run(["fsutil", "8dot3name", "query", root],
                            capture_output=True, timeout=5.0, shell=False)
    except Exception as e:
        return {"root": root, "status": "not-obtainable", "error": type(e).__name__}
    if cp.returncode != 0:
        return {"root": root, "status": "not-obtainable", "rc": cp.returncode}
    txt = cp.stdout.decode("cp936", "replace")
    low = txt.replace(" ", "")
    m = None
    for token in ("1(8dot3", "0(8dot3"):
        if token in low:
            m = token[0]
    return {"root": root, "status": "ok", "rc": cp.returncode,
            "short_name_generation": {"1": "disabled", "0": "enabled"}.get(m, "unread"),
            "state_digits": m}


def build_run_meta(problems):
    cases_blob, _ = git_blob("spec/cases.yaml")
    cases_text = cases_blob.decode("utf-8")
    blind_blob, _ = git_blob("evidence/S00/blind-map.json")
    frozen = open(os.path.join(REPO, "spec", "FROZEN.md"), "rb").read().decode("utf-8")
    spec_sha = hashlib.sha256(cases_blob).hexdigest()
    blind_sha = hashlib.sha256(blind_blob).hexdigest()
    claims = dict(__import__("re").findall(
        r"(?m)^\|\s*(spec/cases\.yaml|evidence/S00/blind-map\.json)\s*\|\s*([0-9a-f]{64})\s*\|",
        frozen))
    mjs = open(os.path.join(REPO, "harness", "ctrl-baseline.mjs"), "rb").read().decode("utf-8")
    import re as _re
    samples = parse_control_samples(cases_text)
    build_ctrl_names(samples)          # raises if the rev6 pin is missing or inconsistent
    meta_len_fill = parse_len_fill(cases_text)   # rev7 pin; raises if absent or not one code unit
    payload = bytes.fromhex(CTRL_PAYLOAD_HEX)
    mjs_payload = _re.search(r'const PAYLOAD = Buffer\.from\("([^"]+)"\)', mjs)
    meta_pin = {"pinned_payload_equals_baseline_script_payload":
                bool(mjs_payload) and mjs_payload.group(1).encode("utf-8") == payload}
    lpe, lpe_src = longpaths_enabled()
    vi = {d: volume_info(d) for d in ("C:\\", "D:\\")}
    d3 = {d: dot3(d + "\\") for d in ("C:", "D:")}
    cons = 0
    try:
        import ctypes as _ct
        cons = int(_ct.windll.kernel32.GetConsoleWindow())
    except Exception as e:
        cons = "unread:%s" % type(e).__name__
    meta = {
        "spec_sha256": spec_sha,
        "spec_face": "git cat-file blob HEAD:spec/cases.yaml rc=0 bytes=%d" % len(cases_blob),
        "spec_disk_sha256": hashlib.sha256(
            open(os.path.join(REPO, "spec", "cases.yaml"), "rb").read()).hexdigest(),
        "spec_blob_equals_disk": spec_sha == hashlib.sha256(
            open(os.path.join(REPO, "spec", "cases.yaml"), "rb").read()).hexdigest(),
        "blind_map_sha256": blind_sha,
        "frozen_claims": claims,
        "frozen_claim_matches_cases_blob": claims.get("spec/cases.yaml") == spec_sha,
        "frozen_claim_matches_blind_map": claims.get("evidence/S00/blind-map.json") == blind_sha,
        "payload_hex": payload.hex(),
        "payload_len": len(payload),
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
        "payload_matches_baseline": hashlib.sha256(payload).hexdigest() == CTRL_BASELINE_SHA,
        "payload_source": "control_samples payload_hex, pinned by contract rev6 in the committed spec/cases.yaml",
        "pin_cross_checks": meta_pin,
        "len_fill_pin": meta_len_fill,
        "os": {"os_version": sys.platform, "arch": "x64"},
        "locale": "unknown",
        "env": {"LongPathsEnabled": lpe,
                "LongPathsEnabled_source": lpe_src,
                "max_component": {k: v.get("max_component") for k, v in vi.items()},
                "dot3name": {k: v.get("short_name_generation") for k, v in d3.items()},
                "unicode_version": __import__("unicodedata").unidata_version,
                "toolchain": "%s %s" % (PY, sys.version.split()[0]),
                "utf8_mode": int(sys.flags.utf8_mode),
                "longpath_manifest_on_interpreter": True,
                "longpath_manifest_source": "evidence/S00/env-facts-windows-local.json "
                                            "manifest_scan: C:\\Python314\\python.exe found=true"},
        "interpreter": {"resolved_executable": PY, "version": sys.version.split()[0],
                        "basis": "sys.executable of the process that spawned every child; "
                                 "this box also has C:\\Windows\\py.exe and the App-Execution "
                                 "launcher on PATH, which were NOT used"},
        "console_window_handle": cons,
        "volumes": vi, "dot3": d3,
        "parse_problems": problems,
    }
    import platform
    meta["os"]["os_version"] = platform.platform()
    meta["os"]["arch"] = platform.machine()
    try:
        import locale as _loc
        meta["locale"] = "%s code_page=%s utf8_mode=%s" % (
            _loc.getlocale(), _loc.getpreferredencoding(False), sys.flags.utf8_mode)
    except Exception as e:
        meta["locale"] = "unread:%s" % type(e).__name__
    meta["ctrl_samples_parsed"] = sorted(samples.keys())
    meta["ctrl_name_provenance"] = ctrl_provenance(samples)
    return meta, cases_text, json.loads(blind_blob.decode("utf-8"))


def parse_control_samples(cases_text):
    """Read `control_samples:` from the committed spec face (the rev6 pin)."""
    import re
    head = cases_text.split("\ncases:")[0]
    block = head.split("control_samples:")[-1] if "control_samples:" in head else ""
    out = {}
    cur = None
    for ln in block.split("\n"):
        m = re.match(r"^\s*-\s+id:\s*(\S+)\s*$", ln)
        if m:
            cur = {"id": m.group(1)}
            out[cur["id"]] = cur
            continue
        if cur is None:
            continue
        m2 = re.match(r"^\s+(sample_hex|payload_hex|expectation):\s*(.+)$", ln)
        if m2:
            cur[m2.group(1)] = yval(m2.group(2))[0]
    return out


def build_ctrl_names(samples):
    """Decode the pinned control names; refuse to run when the pin is not there.

    rev6 closed a real hole: before the pin, this seat took the CANON name out of
    harness/ctrl-baseline.mjs, so T-CTRL-CANON asked a different question per port
    (canon-python.txt here, canon-go-arm.txt and canon-csharp.txt elsewhere).
    """
    global CTRL_PAYLOAD_HEX
    CTRL_NAMES.clear()
    for cid in CTRL_ORDER:
        row = samples.get(cid) or {}
        hx = row.get("sample_hex")
        if not hx or not is_hex(hx):
            raise SystemExit("FATAL control_samples has no valid sample_hex for %s" % cid)
        CTRL_NAMES[cid] = bytes.fromhex(hx).decode("utf-8")
        ph = row.get("payload_hex")
        if not ph or not is_hex(ph):
            raise SystemExit("FATAL control_samples has no valid payload_hex for %s" % cid)
        if CTRL_PAYLOAD_HEX is None:
            CTRL_PAYLOAD_HEX = ph
        elif ph != CTRL_PAYLOAD_HEX:
            raise SystemExit("FATAL control_samples payloads differ across cells at %s" % cid)
    if hashlib.sha256(bytes.fromhex(CTRL_PAYLOAD_HEX)).hexdigest() != CTRL_BASELINE_SHA:
        raise SystemExit("FATAL pinned payload does not reproduce the sealed baseline sha")
    return CTRL_NAMES


def ctrl_provenance(samples):
    """What the rev6 pin guarantees, asserted rather than assumed."""
    return {
        "cells_pinned": sorted(samples.keys()),
        "all_five_present": sorted(samples.keys()) == sorted(CTRL_ORDER),
        "payload_sha_matches_sealed_baseline": bool(CTRL_PAYLOAD_HEX) and
            hashlib.sha256(bytes.fromhex(CTRL_PAYLOAD_HEX)).hexdigest() == CTRL_BASELINE_SHA,
        "one_payload_for_all_five": len({(samples.get(c) or {}).get("payload_hex")
                                         for c in CTRL_ORDER}) == 1,
        "hex_decodes_losslessly": all(
            samples[c]["sample_hex"] == CTRL_NAMES[c].encode("utf-8").hex()
            for c in CTRL_ORDER if c in samples),
        "canon_name_is_pinned_not_transcribed":
            (samples.get("T-CTRL-CANON") or {}).get("sample_hex") ==
            CTRL_NAMES.get("T-CTRL-CANON", "").encode("utf-8").hex(),
        "nametoollong_component_len": len(CTRL_NAMES.get("T-CTRL-NAMETOOLONG", "")),
        "parse_source": "control_samples in git cat-file blob HEAD:spec/cases.yaml",
    }




def compact(rec):
    keys = ("create_result", "error_stage", "error_type", "error_errno", "error_winerror",
            "bytes_written", "bytes_on_disk", "read_result", "read_blocked_reason",
            "name_landed_as_hex", "name_mutated", "same_name_hits", "dir_view_count",
            "delivered_nothing", "phantom", "enum_to_stat_agrees", "os_legality_verdict",
            "sha256_self", "sha256_truth", "elapsed_ms_child", "phases_reached",
            "landed_linkage", "residual_src_new_entries", "pre_existing_entries", "probe_crashed")
    out = {k: rec.get(k) for k in keys}
    if out.get("create_result") == "ok" and out.get("error_stage") is None:
        out["error_stage"] = "null"
    return out


def run_leg_retry_once(it, entry, leg_dir, io_dir, meta, idx, name_hex=None):
    """One probe = one child. A crash or an unreadable result gets exactly one
    re-spawn (recorded); a timeout is never retried away."""
    recs, status, elapsed, argv, phase = run_leg(it, entry, leg_dir, io_dir, meta, idx, name_hex)
    reruns = 0
    bad = (status["rc"] != 0 or status.get("error") or not recs or docs_missing(recs))
    if bad and not status["timed_out"]:
        reruns = 1
        recs2, status2, elapsed2, argv2, phase2 = run_leg(it, entry, leg_dir, io_dir, meta,
                                                           idx, name_hex)
        status2["rerun_of"] = " ".join(argv)
        status2["reruns"] = reruns
        if not status2.get("stderr_tail"):
            status2["stderr_tail"] = status.get("stderr_tail", "")
        return recs2, status2, elapsed2, argv2, phase2, reruns
    status["reruns"] = reruns
    return recs, status, elapsed, argv, phase, reruns


def docs_missing(recs):
    return all((not r) or r.get("phases_reached") in ([], None) for r in recs)


def run_zip_leg(it, leg_dir, io_dir, meta):
    task = {"dir": leg_dir, "zip_name_hex": it["name_hexes"][0],
            "entry_name_hex_list": ZIP_ENTRY_HEX, "payload_hex": payload_of(meta),
            "extractor": it["extractor"]}
    out = os.path.join(io_dir, "out-zip-%s.json" % uuid.uuid4().hex[:6])
    tpath = os.path.join(io_dir, "task-zip-%s.json" % uuid.uuid4().hex[:6])
    with open(tpath, "wb") as fh:
        fh.write(json.dumps(task, ensure_ascii=True, sort_keys=True).encode("utf-8"))
    argv = [PY, PROBE_ZIP, "--task", tpath, "--out", out]
    t0 = time.monotonic()
    status = {"rc": None, "timed_out": False, "stderr_tail": "", "error": None}
    try:
        cp = subprocess.run(argv, capture_output=True, timeout=TIMEOUT_S, shell=False)
        status["rc"] = cp.returncode
        status["stderr_tail"] = cp.stderr.decode("utf-8", "replace")[-400:]
    except subprocess.TimeoutExpired:
        status["timed_out"] = True
    except Exception as e:
        status["error"] = "%s: %s" % (type(e).__name__, str(e)[:160])
        status["rc"] = -1
    elapsed = int((time.monotonic() - t0) * 1000)
    rec = {}
    if os.path.isfile(out):
        try:
            doc = json.loads(open(out, "rb").read().decode("utf-8"))
            rec = (doc.get("results") or [{}])[0]
            rec["phases_reached"] = rec.get("phases_reached", [])
            rec["_doc_phase"] = doc.get("phase")
        except Exception as e:
            rec = {"phases_reached": [], "zip_child_unreadable": str(e)[:120]}
    if status["timed_out"] and rec.get("create_result") is None:
        rec["create_result"] = "hang"
        rec["hang_phase"] = "pack_or_extract"
    return rec, status, elapsed, argv


# ---------------------------------------------------------------- item runner
def run_item(it, meta, controls):
    is_len = it["type"] in ("len_grid", "len_bisect", "len_pinned")
    # rev3 (cell-identity.md section 6): an instrument may not create directories
    # at a drive root, so the length cells live under the documented %TEMP% root.
    # A short 8-hex cell component keeps base_len 78 reachable there.
    root = SCRATCH_TEMP
    cell_dir, _ = fresh_dir(prefix_len=(8 if is_len else None), root=root)
    io_dir = cell_dir + "-io"
    os.makedirs(io_dir, exist_ok=True)
    seed = os.path.basename(cell_dir)
    started = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime())
    legs = {}
    extra = {}

    if it["type"] == "zip_extract":
        leg_dir = os.path.join(cell_dir, "L0")
        os.makedirs(leg_dir, exist_ok=True)
        pre = len(os.listdir(leg_dir))
        rec, status, elapsed, argv = run_zip_leg(it, leg_dir, io_dir, meta)
        legs[PRIMARY_ENTRY] = {"recs": [rec], "status": status, "elapsed": elapsed,
                               "argv": argv, "leg_dir": leg_dir, "leg_pre_existing": pre}
        entries_run = [PRIMARY_ENTRY]
    elif it["type"] == "len_pinned":
        # the holder for the pinned component is the fresh cell directory itself;
        # its depth is recorded because the plain-face ceiling depends on it
        holder = cell_dir
        if len(os.listdir(holder)) != 0:
            raise SystemExit("FATAL length holder not empty: %s" % holder)
        recs, status, elapsed, argv, phase, reruns = run_leg_retry_once(
            it, PRIMARY_ENTRY, holder, io_dir, meta, 0)
        legs[PRIMARY_ENTRY] = {"recs": recs, "status": status, "elapsed": elapsed,
                               "argv": argv, "leg_dir": holder, "leg_pre_existing": 0}
        entries_run = [PRIMARY_ENTRY]
        extra["holder_dir"] = holder
        extra["holder_dir_len"] = len(holder)
        # the ceiling is a separate quantity: a bisection at the SAME holder depth
        # in a sibling fresh directory, so no step can collide with the pinned name
        bdir, _ = fresh_dir(prefix_len=8, root=root)
        if len(bdir) != len(holder):
            bdir, _be = build_base(bdir, len(holder))
        bs = bisect(it, bdir, io_dir, meta, seed)
        bs.pop("_final_leg", None)
        extra.update(bs)
        extra["bisect_holder_dir_len"] = len(bdir)
        extra["len_ceiling"] = bs.get("bisection_boundary_comp_len")
        extra["len_ceiling_rejected"] = bs.get("bisection_rejected_comp_len")
        extra["ceiling_source"] = ("largest component that landed among the bisection steps, at "
                                  "holder depth %d; the bracket lo/hi are taken from the steps "
                                  "themselves, and the boundary re-probe is discarded because the "
                                  "pinned filler makes two same-length names identical"
                                  % len(bdir))
        if recs:
            landed = recs[0].get("create_result") == "ok"
            ceil = bs.get("bisection_boundary_comp_len")
            extra["ceiling_agrees_with_pinned_probe"] = (
                None if ceil is None else (it["base_len"] <= ceil) == landed)
    elif is_len:
        base_dir, err = build_base(cell_dir, it["base_len"])
        if err:
            legs[PRIMARY_ENTRY] = {"recs": [{}], "status": {"rc": None, "error": err,
                                                            "timed_out": False, "reruns": 0},
                                   "elapsed": 0, "argv": ["<not spawned>"], "leg_dir": cell_dir,
                                   "leg_pre_existing": None}
            extra["base_build_error"] = err
        else:
            if it["type"] == "len_grid":
                nm = name_of_len(it["comp_len"], seed)
                nm_hex = nm.encode("utf-8").hex()
                it["_planned"] = [nm_hex]
                recs, status, elapsed, argv, phase, reruns = run_leg_retry_once(
                    it, PRIMARY_ENTRY, base_dir, io_dir, meta, 0, nm_hex)
                legs[PRIMARY_ENTRY] = {"recs": recs, "status": status, "elapsed": elapsed,
                                       "argv": argv, "leg_dir": base_dir,
                                       "leg_pre_existing": 0}
                extra["base_len_measured"] = len(base_dir)
                extra["base_dir"] = base_dir
            else:
                extra.update(bisect(it, base_dir, io_dir, meta, seed))
                legs[PRIMARY_ENTRY] = extra.pop("_final_leg")
                it["_planned"] = [extra.get("final_name_hex", "")]
        entries_run = [PRIMARY_ENTRY]
    else:
        entries = [it["single_entry"]] if it.get("single_entry") else PINNED_ENTRIES
        for i, e in enumerate(entries):
            leg_dir = os.path.join(cell_dir, "L%d" % i)
            os.makedirs(leg_dir, exist_ok=True)
            pre = os.listdir(leg_dir)
            recs, status, elapsed, argv, phase, reruns = run_leg_retry_once(
                it, e, leg_dir, io_dir, meta, i)
            legs[e] = {"recs": recs, "status": status, "elapsed": elapsed, "argv": argv,
                       "leg_dir": leg_dir, "leg_pre_existing": len(pre)}
        entries_run = entries

    cells = []
    for k, sub in enumerate(it["subs"]):
        primary_entry = it.get("single_entry") or PRIMARY_ENTRY
        pleg = legs[primary_entry]
        prec = (pleg["recs"][k] if k < len(pleg["recs"]) else {})
        spread = {}
        for e in entries_run:
            if e == primary_entry:
                continue
            rlist = legs[e]["recs"]
            spread[e] = compact(rlist[k] if k < len(rlist) else {})
        planned = it.get("_planned") or it.get("name_hexes") or [""]
        cid_this = it["case_ids"][k] if "case_ids" in it else it["case_id"]
        spec = {
            "case_id": cid_this,
            "case_group": {"trap": "trap", "ctrl": "ctrl", "tapi": "tapi",
                           "blind": "blind", "len": "len"}[it["kind"]],
            "api_entry": primary_entry,
            "sub_identity": sub,
            "name_source": (prec.get("requested_name_hex") or
                            (planned[k] if k < len(planned) else "")),
            "name_source_kind": it["name_source_kind"],
            "path_form": it["path_form"],
            "longpath_mechanism": it["lpm"],
            "mechanism_class": it["mech"],
            "scratch_root": root,
            "scratch_dir": cell_dir,
            "scratch_verified_empty": (pleg.get("leg_pre_existing") == 0),
            "entries_run": entries_run,
            "group_kind": it["kind"],
            "started_at": started,
            "elapsed_ms": pleg["elapsed"],
            "reserved": bool(it.get("reserved")),
        }
        cell = base_fields(spec, meta)
        if it.get("face_note"):
            cell["face_note"] = it["face_note"]
        if it["type"] == "len_bisect":
            cell["probe"] = "bisection"
            cell["limit_measured"] = it["limit"]
        cell["sub_identity_fields_top_level"] = sorted((cell.get("sub_identity") or {}).keys())
        if it.get("filename_tag"):
            cell["filename_sub_tag"] = it["filename_tag"]
        if "member_indices" in it:
            cell["member_index"] = it["member_indices"][k]
            cell["member_identity_note"] = ("rev3 lists members in the case_id (T09-m1); "
                                            "member_index here is the 0-based position in the "
                                            "frozen sample_hex_list, kept as data, not identity")
        if "packer" in sub:
            cell["packer_version"] = "zipfile (CPython %s)" % meta["interpreter"]["version"]
            cell["extractor_version"] = "%s (CPython %s)" % (
                sub["extractor"], meta["interpreter"]["version"])
        if it.get("zip_report"):
            # zip side, but NOT under the names packer/extractor: ci/equality.py
            # builds identity from top-level SUB_FIELDS, so putting them here
            # would move this required cell to a different key than the
            # required list states.
            cell["zip_packer"] = "zipfile (CPython %s)" % meta["interpreter"]["version"]
            cell["zip_extractor"] = "zipfile.ZipFile.read (CPython %s)" % meta["interpreter"]["version"]
        if it.get("zip_packer_side"):
            cell["zip_packer_side"] = it["zip_packer_side"]
        cell["leg_dir"] = pleg["leg_dir"]
        cell["leg_pre_existing_entries"] = pleg.get("leg_pre_existing")
        cell["entry_spread"] = spread
        agree, disagree, dead = entries_agree(normalise_view(prec), spread)
        cell["entries_agree_with_primary"] = agree
        cell["entries_disagreeing"] = disagree
        cell["entries_without_record"] = dead
        cell["child_rc"] = pleg["status"].get("rc")
        cell["child_timed_out"] = bool(pleg["status"].get("timed_out"))
        cell["child_reruns"] = pleg["status"].get("reruns", 0)
        if pleg["status"].get("stderr_tail"):
            cell["child_stderr_tail"] = pleg["status"]["stderr_tail"]
        if pleg["status"].get("error"):
            cell["child_spawn_error"] = pleg["status"]["error"]
        cell.update(extra)
        if not prec.get("create_result") and not pleg["status"].get("timed_out"):
            cell["cell_blocked"] = True
            cell["blocked_leg"] = "cell"
            cell["blocked_command"] = " ".join(pleg["argv"])
            cell["blocked_exit_code"] = pleg["status"].get("rc")
            cell["blocked_reason"] = ("child produced no create record; rc=%s err=%s base_err=%s"
                                      % (pleg["status"].get("rc"), pleg["status"].get("error"),
                                         extra.get("base_build_error")))
            cell["attempted_fix"] = ("re-spawned the identical argv once into a fresh out file "
                                     "(reruns=%s); if that also failed the cell stays blocked "
                                     "rather than being dropped" % cell["child_reruns"])
        else:
            fill_from_record(cell, prec, spec, True)
        if it["type"] == "len_pinned":
            # rev7 rule 2: len_triple is the three widths OF THAT NAME and nothing
            # else. Applied after fill_from_record, which publishes the nested
            # requested/landed pair used by the other groups.
            nsrc = cell.get("name_source") or ""
            nm = bytes.fromhex(nsrc).decode("utf-8")
            cell["len_triple"] = {"code_points": len(nm),
                                  "utf16_code_units": len(nm.encode("utf-16-le")) // 2,
                                  "utf8_bytes": len(nm.encode("utf-8"))}
            cell["len_triple_basis"] = ("widths of the single pinned component handed to the API; "
                                        "the measured ceiling is in len_ceiling, not here")
            cell["name_source_hex_chars"] = len(nsrc)
            cell["name_source_is_pinned_filler"] = (
                nsrc == len_name_hex(it["base_len"])
                and len(nsrc) == 2 * it["base_len"])
            cell["name_landed_triple"] = prec.get("landed_triple")
        cell["spec_provenance"] = {
            "category": it.get("category"), "applicable": it.get("applicable"),
            "case_locale": it.get("locale"), "spec_source": it.get("spec_source")}
        mism = check_ctrl(cell)
        if mism is not None:
            controls[cell["case_id"]] = mism
        cells.append(cell)
    return cells


def bisect(it, base_dir, io_dir, meta, seed):
    """Binary search for the largest component length that lands.

    Every step is its own child process with the same 5-second external cap. A
    timeout ends the search and is recorded as the outcome, not retried away.
    The cell's own create/read fields come from a final confirmation probe at the
    boundary length, so the record describes one concrete artifact.
    """
    lo, hi = 1, 400
    steps = []
    out = {"bisection_search_range": [lo, hi],
           "scratch_note": "the base directory is fresh and empty at cell creation; it then "
                           "holds one artifact per bisection step by design (each step is a "
                           "distinct component length), so leg_pre_existing is not zero for "
                           "the confirmation probe"}
    hanging = False

    def probe(length, idx):
        nm_hex = name_of_len(length, "s" + seed).encode("utf-8").hex()
        recs, status, elapsed, argv, phase, reruns = run_leg_retry_once(
            it, PRIMARY_ENTRY, base_dir, io_dir, meta, idx, nm_hex)
        r = recs[0] if recs else {}
        steps.append({"comp_len": length, "create_result": r.get("create_result"),
                      "error_type": r.get("error_type"),
                      "error_winerror": r.get("error_winerror"),
                      "bytes_written": r.get("bytes_written"),
                      "bytes_on_disk": r.get("bytes_on_disk"),
                      "name_landed_as_hex": r.get("name_landed_as_hex"),
                      "same_name_hits": r.get("same_name_hits"),
                      "elapsed_ms": elapsed, "rc": status.get("rc"),
                      "timed_out": bool(status.get("timed_out"))})
        return r, status, elapsed, argv

    r_hi, s_hi, e_hi, a_hi = probe(hi, 0)
    if s_hi.get("timed_out"):
        hanging = True
    r_lo, s_lo, _e, _a = probe(lo, 1)
    if s_lo.get("timed_out"):
        hanging = True
    ok_lo = r_lo.get("create_result") == "ok"
    fail_hi = r_hi.get("create_result") in ("err_at_syscall", "err_at_parse")
    if ok_lo and fail_hi and not hanging:
        while hi - lo > 1 and len(steps) < 24:
            mid = (lo + hi) // 2
            r, s, _e2, _a2 = probe(mid, len(steps))
            if s.get("timed_out") or r.get("create_result") == "hang":
                hanging = True
                break
            if r.get("create_result") == "ok":
                lo = mid
            else:
                hi = mid
    confirm_hex = name_of_len(lo, "f" + seed).encode("utf-8").hex()
    confirm, cs, ce, ca, cp, cr = run_leg_retry_once(it, PRIMARY_ENTRY, base_dir, io_dir,
                                                     meta, 99, confirm_hex)
    cs["reruns"] = cr
    out.update({"bisection_boundary_comp_len": lo,
                "bisection_rejected_comp_len": hi,
                "bisection_steps": len(steps),
                "bisection_attempts": steps,
                "bisection_hang_encountered": hanging,
                "bisection_lo_ok": ok_lo, "bisection_hi_fail": fail_hi,
                "final_name_hex": confirm_hex,
                "boundary_winerror": (confirm[0].get("error_winerror") if confirm else None)})
    out["_final_leg"] = {"recs": confirm, "status": cs, "elapsed": ce, "argv": ca,
                         "leg_dir": base_dir, "leg_pre_existing": None}
    return out



ZIP_ENTRY_HEX = None   # filled in main() from the frozen blob faces


def cell_filename(cell):
    """results/<lang>.<os>.<arch>/<group>__<case_id>[__<sub>].json

    The sub tag spells every sub_identity dimension as key=value, joined by '+':
    reversible, deterministic, and legal as a Windows component (no <>:"|?*).
    T-API rows carry sub_identity {} per spec/cells-required.json and are
    separated by api_entry, so their tag names that field instead.
    """
    tag_src = cell.get("filename_sub_tag") or cell.get("sub_identity") or {}
    order = [k for k in (cell.get("sub_identity_order") or []) if k in tag_src]
    order = order or sorted(tag_src.keys())
    tag = "+".join("%s=%s" % (k, tag_src[k]) for k in order)
    parts = [cell["case_group"], cell["case_id"]]
    if tag:
        parts.append(tag)
    return "__".join(parts) + ".json"


def check_ctrl(cell):
    """Control expectation comes ONLY from evidence/S00-ctrl-baseline.md."""
    cid = cell["case_id"]
    exp = CTRL_EXPECT.get(cid)
    if not exp:
        return None
    mism = []
    for k, want in exp.items():
        got = cell.get(k)
        if got != want:
            mism.append("%s=%r want %r" % (k, got, want))
    if cid == "T-CTRL-CANON":
        if cell.get("sha256_self") != cell.get("sha256_truth"):
            mism.append("two instruments disagree: sha256_self=%r sha256_truth=%r" %
                        (cell.get("sha256_self"), cell.get("sha256_truth")))
        if cell.get("sha256_truth") != CTRL_BASELINE_SHA:
            mism.append("sha256_truth=%r != sealed baseline %r" %
                        (cell.get("sha256_truth"), CTRL_BASELINE_SHA))
    return mism


def _ident_key(group, case_id, sub, api_entry=None):
    sub = sub or {}
    k = (group, case_id,
         tuple(sorted((str(a), str(b)) for a, b in sub.items())))
    if group == "tapi":
        k = k + (api_entry,)
    return k


def key_of_cell(c):
    return _ident_key(c.get("case_group"), c.get("case_id"), c.get("sub_identity"),
                      c.get("api_entry"))


def key_of_row(r):
    return _ident_key(r.get("case_group"), r.get("case_id"), r.get("sub_identity"),
                      r.get("api_entry"))


def fmt_key(k):
    g, c, s = k[0], k[1], k[2]
    tail = k[3] if len(k) > 3 else None
    return "%s/%s%s%s" % (g, c,
                          "[" + ",".join("%s=%s" % p for p in s) + "]" if s else "",
                          " api_entry=" + str(tail) if tail else "")


def try_run_identity(row, items):
    """One attempted fix for a required cell the plan did not produce.

    The runner is re-invoked in a separate process filtered to that case_id; its
    exit code is recorded verbatim. Nothing is invented to fill the gap.
    """
    cmd = [PY, os.path.join(HERE, "sg_run.py"), "--cells", row["case_id"]]
    rc = None
    try:
        cp = subprocess.run(cmd, capture_output=True, timeout=300.0, shell=False, cwd=REPO)
        rc = cp.returncode
    except Exception as e:
        rc = "spawn-error:%s" % type(e).__name__
    has_item = any(it["case_id"] == row["case_id"] or
                   row["case_id"] in (it.get("case_ids") or []) for it in items)
    return {"command": " ".join(cmd), "rc": rc,
            "reason": "plan produced no cell with this identity (plan_item_for_case_id=%s)"
                      % has_item,
            "fix": "re-invoked the runner filtered to this case_id in a child process; "
                   "exit code recorded in blocked_exit_code"}


def load_required():
    """spec/cells-required.json from the committed blob face."""
    blob, rc = git_blob("spec/cells-required.json")
    doc = json.loads(blob.decode("utf-8"))
    rows = list(doc.get("required_cells", []))
    rows += [r for r in doc.get("tapi_cells_per_language", [])
             if r.get("language") == "python"]
    return doc, rows, hashlib.sha256(blob).hexdigest(), rc


def migrate(cell, meta, remeasured):
    """Bring a record written before rev3 up to rev3 without touching its numbers."""
    notes = []
    if "worker_id" in cell:
        # SG-F8: the producer key is renamed on the way through, so a re-emit purges the retired name from the
        # data face instead of carrying it forward. This renames a field in the record being written; it does not
        # delete a file, which M19 forbids, and the old value is not preserved because it named a seat, not a lane.
        del cell["worker_id"]
        cell["implementation_id"] = IMPLEMENTATION_ID
        notes.append("producer key renamed from the retired name under SG-F8; the measurement is unchanged and "
                     "the superseded value is not carried forward because it identified a seat, not a lane")
    if cell.get("name_encoding") == "utf16_code_units" or "length_unit" not in cell:
        notes.append("name_encoding=utf16_code_units (a length unit) split per rev3: "
                     "length_unit=code_points, name_encoding=hex_raw_bytes")
        cell["length_unit"] = "code_points"
        cell["length_unit_basis"] = ("len(python str) == code points; utf16/utf8 counts are "
                                     "published in len_triple, never used as the reported length")
        cell["name_encoding"] = "hex_raw_bytes"
    sub = cell.get("sub_identity") or {}
    for k, v in sub.items():
        if k not in cell:
            cell[k] = v
            notes.append("sub_identity dimension %r copied to a top-level field "
                         "(ci/equality.py reads SUB_FIELDS from the cell, not from a nested object)" % k)
    cell["sub_identity_fields_top_level"] = sorted(sub.keys())
    if "verdict_via" not in cell:
        detail = cell.get("os_legality_detail") or {}
        asked = str(detail.get("probe", "")).startswith("GetFileAttributesW")
        cell["verdict_via"] = "win32" if asked else "none"
        cell["verdict_via_detail"] = ("kernel32.GetFileAttributesW via ctypes, extended prefix, "
                                      "parser bypassed" if asked else
                                      "no tool reached: " + (detail.get("outcome")
                                                             or "legality not probed in this leg"))
        notes.append("verdict_via added per rev3")
    if "read_result" not in cell and cell.get("cell_blocked"):
        why = cell.get("read_blocked_reason") or cell.get("blocked_reason") or "read-unreachable"
        cell["read_result"] = "not_applicable"
        cell["read_skipped_reason"] = why
        notes.append("read_result added as not_applicable with read_skipped_reason (rev4 "
                     "fifth word); the create-side measurement is unchanged")
    if cell.get("scratch_root") == SCRATCH_SHORT:
        cell["instrument_base_noncompliant"] = (
            "this cell's base directory was built under %s, a directory created at a drive "
            "root; spec/cell-identity.md section 6 (rev3) forbids that and states the shortest "
            "legal base measured is ~78. The measurement stands as recorded, the reachability "
            "method does not comply with the sentence added after it was taken."
            % SCRATCH_SHORT)
    cell["run_status"] = ("blocked" if cell.get("blocked_leg") == "cell"
                          and cell.get("create_result") is None else "measured")
    cell["migrated_under_spec_sha256"] = meta["spec_sha256"]
    cell["migrated_under_spec_face"] = meta["spec_face"]
    cell["rev3_migrated"] = not remeasured
    cell["rev3_migration_notes"] = notes
    return cell


def blocked_required_cell(row, meta, attempted):
    """A required cell this port could not produce: blocked, never omitted."""
    cell = base_fields({
        "case_id": row["case_id"], "case_group": row["case_group"],
        "api_entry": PRIMARY_ENTRY, "sub_identity": row.get("sub_identity") or {},
        "name_source": "", "name_source_kind": "not produced",
        "path_form": "plain", "longpath_mechanism": "none",
        "mechanism_class": "unknown", "scratch_root": SCRATCH_TEMP,
        "scratch_dir": None, "scratch_verified_empty": False,
        "entries_run": [PRIMARY_ENTRY], "group_kind": row["case_group"],
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime()),
        "elapsed_ms": attempted.get("elapsed_ms", 0), "reserved": False,
    }, meta)
    cell["cell_blocked"] = True
    cell["run_status"] = "blocked"
    cell["blocked_leg"] = "cell"
    cell["blocked_command"] = attempted.get("command", "python impl/python/sg_run.py --cells %s"
                                            % row["case_id"])
    cell["blocked_exit_code"] = attempted.get("rc")
    cell["blocked_reason"] = attempted.get("reason", "no plan item produces this identity")
    cell["attempted_fix"] = attempted.get("fix", "ran the runner filtered to this case_id once")
    cell["os_legality_verdict"] = "unknown"
    cell["verdict_via"] = "none"
    cell["read_result"] = "not_applicable"
    cell["read_skipped_reason"] = "the cell did not run, so nothing landed to read"
    cell["create_result"] = "hang" if attempted.get("hang") else None
    if cell["create_result"] is None:
        cell.pop("create_result", None)
    cell["error_stage"] = "null"
    cell["extra"] = False
    cell["required_but_missing"] = True
    return cell


def legacy_equiv(c):
    """The rev3 identity a rev2-shaped record corresponds to, if any.

    rev3 moves member cells into the case_id (T09-m1) and T-API rows into
    api_entry, so the old nested-sub_identity spelling of the SAME measurement
    still sits on disk. Nothing is deleted (M19); the older file is marked
    superseded and points at the newer one.
    """
    sub = c.get("sub_identity") or {}
    if c.get("case_group") == "trap" and "member_index" in sub:
        return (c["case_group"], "%s-m%d" % (c["case_id"], int(sub["member_index"]) + 1),
                c.get("api_entry"))
    if c.get("case_group") == "tapi" and "tapi_entry" in sub:
        return ("tapi", "T-API", sub["tapi_entry"])
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--cells", default=None)
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--len-only", action="store_true",
                    help="rev7 focused re-run: measure the twelve length cells and the five "
                         "controls, migrate every other record unchanged, then reconcile")
    a = ap.parse_args()

    global ZIP_ENTRY_HEX
    meta, cases_text, blind_doc = build_run_meta([])
    cases, top, ctrl = parse_cases(cases_text)
    problems, notes = audit_parse(cases, top, ctrl)
    meta["parse_problems"] = problems
    meta["parse_notes"] = notes
    meta["blind_map_frozen_claim"] = "see selfcheck: sealed hash does not verify on either face"
    by_id = {c["id"]: c for c in cases}
    t16 = by_id["T16"]["sample_hex_list"][0]
    t06 = by_id["T06"]["sample_hex_list"][0]
    ZIP_ENTRY_HEX = [t16, t06]
    meta["zip_entry_hex"] = ZIP_ENTRY_HEX
    meta["zip_entry_provenance"] = ("entry 1 = T16 sample (ASCII, cannot set bit 11); "
                                   "entry 2 = T06 sample hex, reused because the frozen "
                                   "table offers no non-ASCII name of its own for T16")
    items = plan_items(cases, blind_doc["entries"])
    t16_archive_hex = build_zip_bytes(ZIP_ENTRY_HEX, meta["payload_hex"])
    for it in items:
        if it["type"] == "zip_extract":
            it["name_hexes"] = [t16]
        if it.get("zip_report"):
            it["zip_expect"] = ZIP_ENTRY_HEX
            it["payload_hex_override"] = t16_archive_hex
            it["zip_content_hex"] = meta["payload_hex"]
            it["zip_packer_side"] = "parent, in-memory stdlib zipfile (no filesystem access)"
    meta["t16_archive_len"] = len(bytes.fromhex(t16_archive_hex))
    expected = count_cells(items)
    print("cells_expected=%d plan_items=%d parse_problems=%d" % (expected, len(items), len(problems)))
    print("parse_notes=%s" % json.dumps(notes, sort_keys=True, ensure_ascii=True))
    for p in problems:
        print("   PARSE-PROBLEM %s" % p)
    by_group = {}
    for it in items:
        by_group[it["kind"]] = by_group.get(it["kind"], 0) + len(it["subs"])
    print("   cells_by_group=%s" % json.dumps(by_group, sort_keys=True))
    print("spec_sha256=%s blob_equals_disk=%s" % (meta["spec_sha256"], meta["spec_blob_equals_disk"]))
    print("frozen_claim cases=%s blind=%s" % (meta["frozen_claim_matches_cases_blob"],
                                             meta["frozen_claim_matches_blind_map"]))
    print("payload len=%d matches_baseline=%s" % (meta["payload_len"],
                                                 meta["payload_matches_baseline"]))
    print("ctrl_provenance=%s" % json.dumps(meta["ctrl_name_provenance"], sort_keys=True))
    print("len_fill_pin=%s" % json.dumps(meta["len_fill_pin"], sort_keys=True))
    print("LongPathsEnabled=%s max_component=%s dot3=%s console=%s locale=%s" %
          (meta["env"]["LongPathsEnabled"], meta["env"]["max_component"],
           meta["env"]["dot3name"], meta["console_window_handle"], meta["locale"]))
    print("interpreter=%s %s" % (meta["interpreter"]["resolved_executable"],
                                 meta["interpreter"]["version"]))
    if a.plan:
        for i, it in enumerate(items):
            print("  plan[%d] %-5s %-20s subs=%d type=%s" % (i, it["kind"], it["case_id"],
                                                              len(it["subs"]), it["type"]))
        return 0
    if problems:
        print("REFUSING TO MEASURE: the frozen question set did not parse cleanly")
        return 4
    if not meta["payload_matches_baseline"]:
        print("REFUSING TO MEASURE: control payload does not reproduce the sealed baseline sha")
        return 4

    only = set(a.cells.split(",")) if a.cells else None
    os.makedirs(RESULTS, exist_ok=True)
    built = []
    controls = {}
    t0 = time.monotonic()
    for it in items:
        if only and it["case_id"] not in only:
            continue
        if a.len_only and it["kind"] not in ("len", "ctrl"):
            continue
        cs = run_item(it, meta, controls)
        built.extend(cs)
        for c in cs:
            print("  %-5s %-18s %-26s entry=%-20s create=%-14s read=%-4s w=%-4s disk=%-4s "
                  "mut=%-5s legal=%-7s via=%-6s hits=%s spread=%s" %
                  (c["case_group"], c["case_id"], cell_filename(c)[:26], c["api_entry"],
                   c.get("create_result"), c.get("read_result"), c.get("bytes_written"),
                   c.get("bytes_on_disk"), c.get("name_mutated"),
                   c.get("os_legality_verdict"), c.get("verdict_via"), c.get("same_name_hits"),
                   ("agree" if c.get("entries_agree_with_primary")
                    else "DIFF:" + ",".join(c.get("entries_disagreeing") or []))))
    all_ok = (len(controls) == 5 and all(v == [] for v in controls.values()))
    for cell in built:
        cell["control_pass"] = bool(all_ok)
    if only or a.no_write:
        print("smoke mode: no files written, no migration, required-list not reconciled")
        print("cells_this_smoke=%d control_all_ok=%s" % (len(built), all_ok))
        return 0

    # ---- rev3 reconciliation -------------------------------------------
    req_doc, req_rows, req_sha, req_rc = load_required()
    req_keys = {}
    for r in req_rows:
        req_keys[key_of_row(r)] = r
    new_keys = set(key_of_cell(c) for c in built)
    for c in built:
        c["rev3_migrated"] = False
        c["rev3_migration_notes"] = []
    kept = []
    for name in sorted(os.listdir(RESULTS)):
        if not name.endswith(".json"):
            continue
        p = os.path.join(RESULTS, name)
        try:
            obj = json.loads(open(p, "rb").read().decode("utf-8"))
        except Exception as e:
            print("  PREEXISTING-UNREADABLE %s %s" % (name, str(e)[:80]))
            continue
        if not isinstance(obj, dict) or not obj.get("case_id"):
            print("  PREEXISTING-NOT-A-CELL %s" % name)
            continue
        if key_of_cell(obj) in new_keys:
            continue          # this run re-measured it; the fresh record wins
        kept.append(migrate(obj, meta, remeasured=False))
    fresh_sig = {}
    for c in built:
        fresh_sig[(c["case_group"], c["case_id"], c["api_entry"])] = cell_filename(c)
    n_super = 0
    for c in kept:
        sig = legacy_equiv(c)
        if sig and sig in fresh_sig:
            c["superseded_by"] = fresh_sig[sig]
            c["superseded_reason"] = (
                "rev3 spells this identity as %s/%s (member position lives in case_id, T-API entry "
                "in api_entry); the measurement is unchanged and the older file is kept because "
                "this port contains no deletion logic (M19)" % (sig[0], sig[1]))
            n_super += 1
    everything = built + kept
    for c in everything:
        c["extra"] = key_of_cell(c) not in req_keys
    present = set(key_of_cell(c) for c in everything)
    missing = [k for k in req_keys if k not in present]
    for k in missing:
        row = req_keys[k]
        everything.append(blocked_required_cell(row, meta, try_run_identity(row, items)))
        print("  REQUIRED-MISSING %s -> blocked record emitted" % fmt_key(k))

    written = 0
    for cell in everything:
        with open(os.path.join(RESULTS, cell_filename(cell)), "wb") as fh:
            fh.write(json.dumps(cell, ensure_ascii=True, indent=1).encode("utf-8"))
        written += 1
    n_req = len([c for c in everything if not c.get("extra")])
    n_extra = len([c for c in everything if c.get("extra")])
    n_block = len([c for c in everything if c.get("cell_blocked")])
    n_cant = len([c for c in everything if c.get("blocked_leg") == "cell"])
    n_hang = len([c for c in everything if c.get("create_result") == "hang" or
                  c.get("read_result") == "hang"])
    print("controls=%s" % json.dumps(controls, sort_keys=True))
    print("control_all_ok=%s" % all_ok)
    print("cells_required=%d (rows=%d, tapi_python=%d, blob_sha=%s rc=%d)" %
          (len(req_keys), len(req_doc.get("required_cells", [])),
           len(req_keys) - len(req_doc.get("required_cells", [])), req_sha[:16], req_rc))
    print("cells_remeasured=%d cells_migrated_from_disk=%d cells_total=%d" %
          (len(built), len(kept), len(everything)))
    n_purge = len([c for c in everything if any("SG-F8" in x for x in (c.get("rev3_migration_notes") or []))])
    n_retired_left = len([c for c in everything if "worker_id" in c])
    print("producer_keys_purged=%d records_still_carrying_retired_key=%d "
          "implementation_id_present=%d/%d" % (n_purge, n_retired_left,
                                               len([c for c in everything if c.get("implementation_id")]),
                                               len(everything)))
    print("records_superseded_by_rev3_rename=%d" % n_super)
    print("cells_written=%d covered_required=%d extra=%d missing_required=%d" %
          (written, n_req, n_extra, len(missing)))
    print("cells_blocked=%d of_which_could_not_run=%d cells_with_hang=%d" % (n_block, n_cant, n_hang))
    print("wall_seconds=%.1f scratch_root=%s (length cells need base_len %s)" %
          ((time.monotonic() - t0), SCRATCH_TEMP, REQUIRED_BASES))
    with open(os.path.join(HERE, "sg_run_summary.json"), "wb") as fh:
        fh.write(json.dumps({"cells_required": len(req_keys), "cells_total": len(everything),
                             "covered_required": n_req, "extra": n_extra,
                             "missing_required": [fmt_key(k) for k in missing],
                             "cells_blocked": n_block, "controls": controls,
                             "required_blob_sha256": req_sha, "meta": meta},
                            ensure_ascii=True, indent=1).encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


