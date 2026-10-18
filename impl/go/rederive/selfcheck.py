#!/usr/bin/env python3
"""SENDGUARD Go port self-check (session-token), re-derived against contract rev3.

Written by the Go local and independent of the Go code it judges: it re-parses
spec/cases.yaml, reads the required-cell list out of spec/cells-required.json, re-reads
the closed words out of spec/canonical.md, re-reads the control expectations out of
evidence/ctrl-baseline.md, and validates every published cell against
spec/schema.json (the rev3 face) plus the three sentences the NOTICE of 04:21 adds.

It prints the counters the NOTICE asks for and nothing else decides:

    cells_required / cells_produced / cells_valid / cells_blocked / extra

Exit codes: 0 clean, 2 a control cell failed (INSTRUMENT-RED), 3 a cell-level or
denominator defect, 4 the checker could not load its own inputs.

Stdlib only. Every file is read as bytes and decoded as UTF-8 explicitly, never through
the host locale (this machine's console code page is 936).
"""
import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import sys

# spec/cell-identity.md section 1, as ci/equality.py implements it: the varying
# dimensions are FLAT top-level fields, and api_entry is NOT part of the key.
SUB_FIELDS = ("base_len", "builder", "reader", "packer", "extractor")
CLOSED = {
    "case_group": {"trap", "ctrl", "tapi", "blind", "len"},
    "language": {"node", "typescript", "python", "go", "java", "csharp", "rust"},
    "os": {"windows", "macos", "ubuntu"},
    "length_unit": {"utf16_code_units", "code_points", "utf8_bytes"},
    "name_encoding": {"hex_utf16le", "hex_raw_bytes"},
    "verdict_via": {"win32", "dotnet", "cmd", "posix", "none"},
    "path_form": {"plain", "extended"},
    "longpath_mechanism": {"manifest", "prefix_rewrite", "none", "unknown"},
    "create_result": {"ok", "err_at_syscall", "err_at_parse", "hang"},
    "error_stage": {"parse", "syscall", "fs", "tool", "null"},
    "read_result": {"ok", "eof", "err6", "hang"},
    "os_legality_verdict": {"legal", "illegal", "unknown"},
    "attribution_layer": {"L1", "L2", "L3", "L3_interaction"},
}
CLASSES = {"reserved_device_name", "path_preprocessing_policy", "illegal_char_filter",
           "component_length_limit", "unicode_normalization", "case_folding",
           "control_char_handling", "bidi_handling", "zero_width_handling",
           "zip_roundtrip", "os_legality", "unknown"}
# The NOTICE of 04:21 makes these three required. spec/validate.py, frozen at sha
# f19a5d14, does not know them yet: enforced here, divergence reported, nothing patched.
REV3_REQUIRED_EXTRA = ("length_unit", "name_encoding", "verdict_via")


def read_bytes(p):
    return io.open(p, "rb").read()


def idval(v):
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    return str(v)


def identity(cell):
    """Render (case_group, case_id, sub_identity) the way ci/equality.py does: the flat
    dimension fields, then the cell's declared object on top of them, and for the len
    group path_form is one of the dimensions (rev6), because plain and extended are two
    different questions about the same rung."""
    group = cell.get("case_group") or "?"
    dims = {}
    fields = list(SUB_FIELDS)
    if group == "len":
        fields.append("path_form")
    for f in fields:
        v = cell.get(f)
        if v not in (None, "", []):
            dims[f] = idval(v)
    declared = cell.get("sub_identity")
    if isinstance(declared, dict):
        for k, v in declared.items():
            if v is None or k == "api_entry":
                continue
            if k in fields:
                dims[k] = idval(v)
    elif isinstance(declared, list):
        for e in declared:
            if not isinstance(e, dict):
                continue
            k = e.get("dim")
            if not k or k == "api_entry" or k not in fields:
                continue
            dims[k] = idval(e.get("value"))
    out = "%s/%s" % (group, cell.get("case_id"))
    if dims:
        out += "[" + ",".join("%s=%s" % (k, dims[k]) for k in sorted(dims)) + "]"
    if group == "tapi" and cell.get("api_entry"):
        out += "{api_entry=%s}" % cell["api_entry"]
    return out


def load_cells(d):
    out = {}
    for name in sorted(os.listdir(d)):
        if not name.endswith(".json"):
            continue
        try:
            out[name] = json.loads(read_bytes(os.path.join(d, name)).decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            out[name] = {"_unreadable": "%s: %s" % (name, e)}
    return out


def expected_from_spec(cases_yaml):
    """Re-derive the corpus independently of the port that measured it."""
    txt = read_bytes(cases_yaml).decode("utf-8")
    ids, samples, cur, in_list = [], {}, None, False
    section = ""
    for line in txt.splitlines():
        if line and not line[0].isspace():
            section = line.split(":")[0].strip()
        if section != "cases":
            continue
        m = re.match(r"^\s*-\s+id:\s*(\S+)\s*$", line)
        if m:
            cur = m.group(1)
            ids.append(cur)
            samples[cur] = []
            in_list = False
            continue
        if cur is None:
            continue
        m = re.match(r"^\s+sample_hex:\s*\"?([0-9a-fA-F]+)\"?", line)
        if m:
            samples[cur] = [m.group(1).lower()]
            in_list = False
            continue
        if re.match(r"^\s+sample_hex_list:", line):
            samples[cur] = []
            in_list = True
            continue
        if in_list:
            m = re.match(r"^\s+-\s*\"?([0-9a-fA-F]+)\"?", line)
            if m:
                samples[cur].append(m.group(1).lower())
                continue
            in_list = False
    entries = re.search(r"^\s+go:\s*\[([^\]]*)\]", txt, re.M)
    n_entries = len([e for e in entries.group(1).split(",") if e.strip()]) if entries else 0
    members = sum(max(1, len(samples[i])) for i in ids if i not in ("T17", "T18"))
    return {"cases_in_spec": len(ids), "members": members, "pinned_entries": n_entries}


def closed_from_canonical(md):
    txt = read_bytes(md).decode("utf-8")
    sets = {}
    for m in re.finditer(r"(?m)^## \d+\. ([a-z_]+)[^\n]*$", txt):
        field = m.group(1)
        if field not in CLOSED:
            continue
        nxt = txt.find("\n## ", m.end())
        block = txt[m.end():nxt if nxt > 0 else len(txt)]
        sets[field] = set(re.findall(r"`([a-z0-9_]+)`", block))
    return sets


def pinned_control_samples(cases_yaml):
    """rev6 pins the five control sample hexes in spec/cases.yaml. A port that hashed a
    name it invented (T-CTRL-CANON arrived as four different names in the rev5 run) is now
    detectable, so the pinned hex is compared against, not trusted."""
    txt = read_bytes(cases_yaml).decode("utf-8")
    out, cur, inside = {}, None, False
    for line in txt.splitlines():
        if line.startswith("control_samples:"):
            inside = True
            continue
        if inside and line and not line.startswith((" ", "#", "-")):
            inside = False
        if not inside:
            continue
        m = re.match(r"^\s*-\s+id:\s*(\S+)", line)
        if m:
            cur = m.group(1)
            out[cur] = {}
            continue
        m = re.match(r'^\s+(sample_hex|payload_hex):\s*"?([0-9a-fA-F]+)', line)
        if m and cur:
            out[cur][m.group(1)] = m.group(2).lower()
    return out


def control_expectations(md):
    """evidence/ctrl-baseline.md is the only allowed source of control expectations."""
    txt = read_bytes(md).decode("utf-8")
    rows = {}
    for line in txt.splitlines():
        if not line.startswith("| T-CTRL-"):
            continue
        c = [x.strip() for x in line.strip().strip("|").split("|")]
        rows[c[0]] = {"create_result": c[1], "error_stage": c[2], "error_code": c[3],
                      "bytes_written": c[4], "bytes_on_disk": c[5], "read_result": c[6],
                      "roundtrip_ok": c[7], "sha256": c[8]}
    return rows


def load_required(path, repo):
    f = json.loads(read_bytes(path).decode("utf-8"))
    req = [identity(c) for c in f.get("required_cells", [])]
    go_tapi = [c for c in f.get("tapi_cells_per_language", []) if c.get("language") == "go"]
    req += [identity(c) for c in go_tapi]
    declared = ""
    fz = os.path.join(repo, "spec", "FROZEN.md")
    if os.path.isfile(fz):
        for line in read_bytes(fz).decode("utf-8").splitlines():
            if "cells-required.json" in line:
                for w in line.split():
                    if re.match(r"^[0-9a-f]{64}$", w):
                        declared = w
    measured = hashlib.sha256(read_bytes(path)).hexdigest()
    meta = {"measured_sha256": measured, "declared_in_frozen": declared,
            "agrees": bool(declared) and declared == measured,
            "generated_at": f.get("generated_at"),
            "withdraws_present": bool(f.get("withdraws"))}
    return req, f, meta, len(go_tapi)


def validate(cell, schema, cexp):
    errs = []
    if "_unreadable" in cell:
        return ["unreadable: " + cell["_unreadable"]]
    req, enums = schema
    for f in req:
        if f not in cell:
            errs.append("schema.json: missing required field %s" % f)
    for k, allowed in enums.items():
        if k in cell and cell[k] is not None and cell[k] not in allowed:
            errs.append("schema.json enum violation %s=%r" % (k, cell[k]))
    for f in REV3_REQUIRED_EXTRA:
        if f not in cell:
            errs.append("rev3 NOTICE requires %s and the cell does not carry it" % f)
    for k, closed in CLOSED.items():
        if k in cell and cell[k] is not None and cell[k] not in closed:
            errs.append("unknown status word %s=%r (not in the closed set)" % (k, cell[k]))
    if isinstance(cell.get("format_version"), str):
        errs.append("format_version is the string face; frozen spec/validate.py:52 demands the integer")
    for key in ("roundtrip_ok", "enum_to_stat_agrees"):
        # spec/schema.json types these as boolean, and the frozen spec/validate.py:67-71
        # voids them when they are present and not a boolean. A leg that did not run must
        # leave the field absent (rev6 s9.1: NOT-RECORDED is a completeness finding).
        if key in cell and not isinstance(cell[key], bool):
            errs.append("%s is present but not a boolean (%r); omit it when the leg did not run" % (key, cell[key]))
    for key in ("sha256_self", "sha256_truth"):
        v = cell.get(key)
        if v is not None and not re.match(r"^[0-9a-f]{64}$", v):
            errs.append("%s is not 64-hex: %r" % (key, v))
    if cell.get("language") != "go":
        errs.append("language is %r in the go port directory" % cell.get("language"))
    if cell.get("case_group") == "len":
        unit = (cell.get("len_pinned_fill") or {}).get("unit_hex")
        bl = cell.get("base_len")
        if isinstance(bl, int) and unit:
            want = unit * bl
            if cell.get("name_source") != want:
                errs.append("rev7 rule 1: name_source is %r, the pinned filler repeated to base_len=%d is %r (a case label or a boundary result is not the component handed to the API)"
                            % (str(cell.get("name_source"))[:24] + "...", bl, want[:24] + "..."))
        tri = cell.get("len_triple")
        if isinstance(tri, str) and isinstance(bl, int):
            parts = [x for x in re.split(r"[/,]", tri) if x != ""]
            if len(parts) == 3 and any(p != idval(bl) for p in parts):
                errs.append("rev7 rule 2: len_triple %r is not the width of this name (base_len=%d); a measured ceiling belongs in len_ceiling" % (tri, bl))
        if "len_ceiling" not in cell:
            errs.append("rev7 rule 3: no len_ceiling field, so the measured ceiling has nowhere to live")
        if cell.get("run_status") not in ("ran", "blocked"):
            errs.append("len cell run_status=%r outside ran|blocked" % cell.get("run_status"))
        if not isinstance(cell.get("base_len"), int):
            errs.append("len cell without an integer base_len inside the cell")
        if cell.get("path_form") not in ("plain", "extended"):
            errs.append("len cell without a lawful path_form (it is an identity dimension at rev6)")
    if cell.get("case_group") == "blind" and not isinstance(cell.get("blind_id"), int):
        errs.append("blind cell without blind_id")
    vp = cell.get("verdict_via_probe")
    if cell.get("verdict_via") == "none" and cell.get("os_legality_verdict") != "unknown":        errs.append("verdict_via=none but a verdict is claimed; none means the OS was never asked")
    if "os_legality_verdict" in cell and not vp:
        errs.append("verdict_via_probe absent: rev6 asks which layer was put the question")
    if vp and not str(vp).startswith("CreateFileW") and cell.get("verdict_via") != "none":
        errs.append("verdict taken from %r; rev6 measured FindFirstFileW answering "
                    "ERROR_FILE_NOT_FOUND for a<b.txt, so it cannot decide legality" % vp)
    if "run_status" not in cell:
        errs.append("rev6 run_status absent (ran|blocked)")
    # the legality probe must ask the form the cell claims: \\?\ for extended,
    # a drive-absolute plain path otherwise. A mistyped prefix is otherwise invisible.
    lp = cell.get("legality_create_probe") or {}
    head = lp.get("asked_path_head_hex") or ""
    if lp.get("attempted"):
        want = "5c5c3f5c" if lp.get("path_form") == "extended" else "443a5c"
        if not head.lower().startswith(want):
            errs.append("legality probe asked %r which is not the %s form the cell records (expected head %s...)"
                        % (head[:16], lp.get("path_form"), want))
    mc = cell.get("mechanism_class")
    if mc is not None and mc not in CLASSES:
        errs.append("mechanism_class=%r outside spec/canonical.md section 10" % mc)
    if "name_source" in cell and not re.match(r"^[0-9a-f]*$", str(cell["name_source"])):
        errs.append("name_source is not lowercase hex: %r" % cell["name_source"])
    if cell.get("case_group") == "ctrl":
        pin = (cexp.get("_pinned") or {}).get(cell.get("case_id"))
        if pin:
            if cell.get("name_source") != pin.get("sample_hex"):
                errs.append("CONTROL %s: name_source is %r, the pinned spec sample is %r"
                            % (cell.get("case_id"), cell.get("name_source"), pin.get("sample_hex")))
            if cell.get("payload_hex") != pin.get("payload_hex"):
                errs.append("CONTROL %s: payload is not the pinned 28 bytes" % cell.get("case_id"))
        e = cexp.get(cell.get("case_id"))
        if e is None:
            errs.append("no S00 baseline row for %s" % cell.get("case_id"))
        else:
            for col in ("create_result", "error_stage"):
                want = e[col]
                if want in ("-", "(canonical)", "(none)"):
                    continue
                if str(cell.get(col)) != want:
                    errs.append("CONTROL %s: baseline says %s=%s, cell says %r"
                                % (cell.get("case_id"), col, want, cell.get(col)))
            if cell.get("case_id") == "T-CTRL-ASCII":
                for col in ("bytes_written", "bytes_on_disk"):
                    if str(cell.get(col)) != e[col]:
                        errs.append("CONTROL T-CTRL-ASCII: baseline %s=%s cell=%r"
                                    % (col, e[col], cell.get(col)))
                if str(cell.get("roundtrip_ok")).lower() != e["roundtrip_ok"].lower():
                    errs.append("CONTROL T-CTRL-ASCII roundtrip_ok mismatch")
            if cell.get("case_id") == "T-CTRL-CANON":
                if not cell.get("sha256_self") or cell.get("sha256_self") != cell.get("sha256_truth"):
                    errs.append("CONTROL T-CTRL-CANON: the two instruments do not agree "
                                "(spec/gate.md section 8 -> INSTRUMENT-RED)")
    return errs


def claimed_universe(cells):
    """Every name this port requested, landed, or probed and published. A directory
    entry from outside this set is unclaimed evidence (spec/gate.md section 8)."""
    names = set()
    for c in cells.values():
        for k in ("name_source", "name_landed_as"):
            if c.get(k):
                names.add(c[k])
        for f in (c.get("bisection") or {}).get("faces") or []:
            for a in (f.get("attempts") or []) + (f.get("verify") or []):
                if a.get("name_hex"):
                    names.add(a["name_hex"])
    return names


def check_no_deletion(repo):
    root = os.path.join(repo, "impl", "go", "rederive")
    pat = re.compile(r"os\.(Remove|RemoveAll|Rename)|syscall\.DeleteFile|syscall\.MoveFile|"
                     r"SHFileOperation|EmptyRecycleBin|ioutil\.Remove")
    hits, files = [], 0
    for name in sorted(os.listdir(root)):
        if not name.endswith(".go"):
            continue
        files += 1
        text = io.open(os.path.join(root, name), "rb").read().decode("utf-8")
        for i, line in enumerate(text.splitlines(), 1):
            if pat.search(line):
                hits.append("%s:%d %s" % (name, i, line.strip()[:80]))
    return ["files_scanned=%d root=%s" % (files, root),
            "deletion_calls_found=%d (project rule requires 0)" % len(hits)] + hits


def run_repo_gates(repo):
    out = []
    for argv in ([sys.executable, os.path.join(repo, "ci", "lint.py"), "--selftest"],
                 [sys.executable, os.path.join(repo, "ci", "lint.py"), "--repo-root", repo],
                 [sys.executable, os.path.join(repo, "spec", "validate.py"),
                  os.path.join(repo, "results", "go.windows.x64")]):
        try:
            r = subprocess.run(argv, capture_output=True, timeout=180)
        except Exception as e:  # noqa: BLE001
            out.append("rc=-1 %s: %s" % (" ".join(argv[1:3]), e))
            continue
        tail = (r.stdout or b"").decode("utf-8", "replace").strip().splitlines()[-1:]
        err = (r.stderr or b"").decode("utf-8", "replace").strip().splitlines()[-1:]
        out.append("rc=%d %s | %s%s" % (r.returncode, " ".join(argv[1:]),
                                        " / ".join(tail),
                                        " | ERR " + " / ".join(err) if err else ""))
    return out


def selftest():
    """A checker that has only been seen passing is not proven to bite; one that has
    only been seen refusing is not proven to let anything through."""
    base = {
        "format_version": 1, "case_id": "T01", "case_group": "trap", "language": "go",
        "os": "windows", "api_entry": "os.Create", "attempt": 1, "name_source": "434f4e",
        "path_form": "plain", "longpath_mechanism": "none", "create_result": "ok",
        "error_stage": "null", "read_result": "ok", "os_legality_verdict": "illegal",
        "harness_version": "selftest", "started_at": "1970-01-01T00:00:00Z",
        "elapsed_ms": 0, "mechanism_class": "reserved_device_name",
        "length_unit": "utf16_code_units", "name_encoding": "hex_raw_bytes",
        "verdict_via": "win32", "verdict_via_probe": "CreateFileW+listing",
        "run_status": "ran",
    }
    arms = [("green: a rev3-shaped cell passes",
             not validate(base, (sorted(base.keys()), {}), {}), None)]
    for field, bad in (("create_result", "mostly_ok"), ("length_unit", "utf16_code_unit"),
                       ("name_encoding", "utf16_code_units"), ("verdict_via", "powershell"),
                       ("longpath_mechanism", "auto")):
        c = dict(base)
        c[field] = bad
        errs = validate(c, ({}, {}), {})
        arms.append(("red: %s=%r refused" % (field, bad), any(field in e for e in errs), errs))
    errs = validate({k: v for k, v in base.items() if k != "verdict_via"}, ({}, {}), {})
    arms.append(("red: verdict_via absent refused under the rev3 NOTICE",
                 any("verdict_via" in e for e in errs), errs))
    errs = validate(dict(base, format_version="1"), ({}, {}), {})
    arms.append(("red: string format_version flagged for the frozen validator",
                 any("format_version" in e for e in errs), errs))
    errs = validate(dict(base, case_group="len", case_id="T17"), ({}, {}), {})
    arms.append(("red: len cell without an integer base_len", any("base_len" in e for e in errs), errs))
    ctrl = dict(base, case_group="ctrl", case_id="T-CTRL-ASCII", create_result="ok",
                bytes_written=28, bytes_on_disk=28, roundtrip_ok=True, error_stage="null",
                read_result="ok", name_source="7265706f72742d323032362e747874",
                payload_hex="53454e4447554152442d43414e4f4e2d5041594c4f41442d32303236")
    exp = {"T-CTRL-ASCII": {"create_result": "ok", "error_stage": "null", "error_code": "-",
                            "bytes_written": "28", "bytes_on_disk": "28", "read_result": "ok",
                            "roundtrip_ok": "true", "sha256": "-"}}
    exp["_pinned"] = {"T-CTRL-ASCII": {"sample_hex": "7265706f72742d323032362e747874",
                                       "payload_hex": "53454e4447554152442d43414e4f4e2d5041594c4f41442d32303236"}}
    arms.append(("red: a control cell whose name is not the pinned sample is caught",
                 any("pinned spec sample" in e for e in validate(dict(ctrl, name_source="deadbeef"), ({}, {}), exp)),
                 None))
    arms.append(("green: control matching the S00 baseline passes",
                 not validate(ctrl, ({}, {}), exp), validate(ctrl, ({}, {}), exp)))
    errs = validate(dict(ctrl, create_result="err_at_syscall"), ({}, {}), exp)
    arms.append(("red: control flipped against the baseline is caught",
                 any("CONTROL" in e for e in errs), errs))
    canon = dict(base, case_group="ctrl", case_id="T-CTRL-CANON", create_result="ok",
                 error_stage="null", sha256_self="a" * 64, sha256_truth="b" * 64)
    cexp = {"T-CTRL-CANON": {"create_result": "ok", "error_stage": "-", "error_code": "-",
                             "bytes_written": "-", "bytes_on_disk": "-", "read_result": "-",
                             "roundtrip_ok": "-", "sha256": "-"}}
    errs = validate(canon, ({}, {}), cexp)
    arms.append(("red: CANON instrument disagreement is caught",
                 any("T-CTRL-CANON" in e for e in errs), errs))
    rung78 = identity({"case_group": "len", "case_id": "T17", "base_len": 78})
    rung120 = identity({"case_group": "len", "case_id": "T17", "base_len": 120})
    arms.append(("identity: base_len is part of the key and two rungs differ",
                 rung78 == "len/T17[base_len=78]" and rung78 != rung120, None))
    arms.append(("identity: api_entry is NOT part of the key (cell-identity s1)",
                 identity({"case_group": "trap", "case_id": "T01", "api_entry": "os.Create"}) ==
                 identity({"case_group": "trap", "case_id": "T01", "api_entry": "os.Mkdir"}), None))
    errs = validate(dict(base, roundtrip_ok=None), ({}, {}), {})
    arms.append(("red: roundtrip_ok published as null is refused (schema says boolean)",
                 any("roundtrip_ok" in e for e in errs), errs))
    labelish = dict(base, case_group="len", case_id="T17", base_len=78,
                    name_source="61" * 78, len_triple="48/48/48",
                    len_pinned_fill={"unit_hex": "61"}, len_ceiling={"ceiling_code_units": 255},
                    run_status="ran")
    errs = validate(labelish, ({}, {}), {})
    arms.append(("red: len_triple carrying a foreign width (a label's length) is refused",
                 any("len_triple" in e for e in errs), errs))
    boundaryish = dict(labelish, len_triple="255/255/255")
    errs = validate(boundaryish, ({}, {}), {})
    arms.append(("red: len_triple carrying the measured ceiling is refused (rev7 rule 2)",
                 any("len_triple" in e for e in errs), errs))
    noceil = dict(labelish, len_triple="78/78/78")
    del noceil["len_ceiling"]
    errs = validate(noceil, ({}, {}), {})
    arms.append(("red: len cell without len_ceiling is refused (rev7 rule 3)",
                 any("len_ceiling" in e for e in errs), errs))
    good = dict(labelish, len_triple="78/78/78")
    arms.append(("green: a rev7-shaped len cell passes", not any("rev7" in e for e in validate(good, ({}, {}), {})), validate(good, ({}, {}), {})))
    wrongbytes = dict(good, name_source="542d4c454e2d50415448")  # a case label, as spec/cases.yaml once printed
    errs = validate(wrongbytes, ({}, {}), {})
    arms.append(("red: name_source that is not the pinned filler repeated is refused",
                 any("rule 1" in e for e in errs), errs))
    good_head = dict(base)
    good_head["legality_create_probe"] = {"attempted": True, "path_form": "plain",
                                         "asked_path_head_hex": "443a5c73656e64"}
    arms.append(("green: a plain cell whose probe asked a drive-absolute path passes",
                 not any("legality probe asked" in e for e in validate(good_head, ({}, {}), {})), None))
    bad_head = dict(good_head)
    bad_head["legality_create_probe"] = {"attempted": True, "path_form": "extended",
                                        "asked_path_head_hex": "5c3f5c443a5c73"}
    arms.append(("red: an extended cell whose probe prefix is missing a backslash is caught",
                 any("legality probe asked" in e for e in validate(bad_head, ({}, {}), {})), None))
    errs = validate(dict(base, enum_to_stat_agrees=False), ({}, {}), {})
    arms.append(("green: a recorded boolean verdict passes", not any("enum_to_stat_agrees" in e for e in errs), errs))
    arms.append(("identity: required-file row and published cell render alike",
                 identity({"case_group": "len", "case_id": "T17",
                           "sub_identity": {"base_len": 78}}) == rung78, None))
    print("== checker self-test (green and red arms)")
    failed = 0
    for label, ok, detail in arms:
        print("   %-62s %s" % (label, "OK" if ok else "FAILED"))
        if not ok:
            failed += 1
            if detail:
                print("        detail: %s" % detail)
    print("selftest_arms=%d selftest_failed=%d" % (len(arms), failed))
    return failed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=False, default="")
    ap.add_argument("--results", default=None)
    ap.add_argument("--selftest", action="store_true",
                    help="run the green and red arms of this checker and exit")
    a = ap.parse_args()
    if a.selftest:
        return 1 if selftest() else 0
    repo = os.path.abspath(a.repo or ".")
    resdir = a.results or os.path.join(repo, "results", "go.windows.x64")
    canon_md = os.path.join(repo, "spec", "canonical.md")
    cases_yaml = os.path.join(repo, "spec", "cases.yaml")
    schema_json = os.path.join(repo, "spec", "schema.json")
    required_json = os.path.join(repo, "spec", "cells-required.json")
    ctrl_md = os.path.join(repo, "evidence", "ctrl-baseline.md")
    for p in (canon_md, cases_yaml, schema_json, required_json, ctrl_md, resdir):
        if not os.path.exists(p):
            print("OUTCOME=VOID reason=missing-input %s" % p)
            return 4

    sch = json.loads(read_bytes(schema_json).decode("utf-8"))
    schema = (sch.get("required", []),
              {k: set(v["enum"]) for k, v in sch["properties"].items() if "enum" in v})
    exp_count = expected_from_spec(cases_yaml)
    canon = closed_from_canonical(canon_md)
    cexp = control_expectations(ctrl_md)
    pinned = pinned_control_samples(cases_yaml)
    cexp["_pinned"] = pinned
    print("   pinned control samples in spec/cases.yaml=%d (rev6)" % len(pinned))
    req, reqfile, reqmeta, n_go_tapi = load_required(required_json, repo)
    cells = load_cells(resdir)

    for k, v in canon.items():
        if v and not v >= CLOSED[k]:
            print("CANON-DRIFT %s: file=%s checker=%s" % (k, sorted(v), sorted(CLOSED[k])))

    universe = claimed_universe(cells)
    valid, void, blocked, extras, unclaimed = [], [], [], [], []
    ids = {}
    for name, c in cells.items():
        errs = validate(c, schema, cexp)
        if c.get("blocked") is True or "create_result" not in c:
            blocked.append(name)
        if c.get("extra") is True:
            extras.append(name)
        if errs:
            void.append((name, errs))
        else:
            valid.append(name)
        ids.setdefault(identity(c), []).append(name)
        for e in c.get("dir_view") or []:
            if e.get("name_utf8_hex") not in universe:
                unclaimed.append((name, e.get("name_utf8_hex")))
    dups = {k: v for k, v in ids.items() if len(v) > 1}
    present = set(ids)
    missing = [k for k in req if k not in present]
    matched = [k for k in req if k in present]
    by_group = {}
    for c in cells.values():
        g = c.get("case_group") or "?"
        by_group[g] = by_group.get(g, 0) + 1

    print("== required list (spec/cells-required.json)")
    print("   sha256_measured=%s" % reqmeta["measured_sha256"])
    print("   sha256_declared_in_FROZEN=%s agrees=%s"
          % (reqmeta["declared_in_frozen"], reqmeta["agrees"]))
    print("   generated_at=%s withdraws_previous_version=%s"
          % (reqmeta["generated_at"], reqmeta["withdraws_present"]))
    print("   base_len_ladder=%s primary_entry_for_go=%s"
          % (reqfile.get("base_len_ladder"), reqfile.get("primary_entry_per_port", {}).get("go")))
    print("   required_for_go=%d (generic %d + go tapi %d)"
          % (len(req), len(reqfile.get("required_cells", [])), n_go_tapi))
    print("== denominators")
    print("   spec_corpus: cases=%d members=%d pinned_go_entries=%d"
          % (exp_count["cases_in_spec"], exp_count["members"], exp_count["pinned_entries"]))
    print("   produced_by_group=%s" % json.dumps(by_group, sort_keys=True))
    print("== counters")
    print("cells_required=%d" % len(req))
    print("cells_produced=%d" % len(cells))
    print("cells_valid=%d" % len(valid))
    print("cells_blocked=%d" % len(blocked))
    print("extra=%d" % len(extras))
    print("cells_void=%d" % len(void))
    print("required_matched=%d required_missing=%d" % (len(matched), len(missing)))
    print("identity_collisions=%d" % len(dups))
    print("unclaimed_dir_view_entries=%d" % len(unclaimed))
    for k in missing[:10]:
        print("MISSING-REQUIRED %s" % k)
    for name, errs in void[:10]:
        print("VOID %s" % name)
        for e in errs[:3]:
            print("      - %s" % e)
    for k, v in list(dups.items())[:5]:
        print("DUP-IDENTITY %s -> %s" % (k, v))
    for name, h in unclaimed[:5]:
        print("UNCLAIMED %s dir entry hex=%s" % (name, h))
    for n in extras:
        print("EXTRA %s" % n)

    print("== rev3 fields")
    print("   length_unit faces=%s" % json.dumps(sorted({str(c.get("length_unit")) for c in cells.values()})))
    print("   name_encoding faces=%s" % json.dumps(sorted({str(c.get("name_encoding")) for c in cells.values()})))
    print("   verdict_via faces=%s" % json.dumps(sorted({str(c.get("verdict_via")) for c in cells.values()})))
    print("   schema.json required[] contains verdict_via=%s (the NOTICE calls it required;"
          " this checker enforces the NOTICE and reports the gap)" % ("verdict_via" in sch.get("required", [])))
    print("   verdict_via='none' is in schema.json but not in spec/cell-identity.md s6; this port"
          " uses it only for the cell where no tool was asked at all")

    print("== deletion logic (project rule)")
    for line in check_no_deletion(repo):
        print("   %s" % line)
    print("== repo gates this port may run but not edit")
    for line in run_repo_gates(repo):
        print("   %s" % line)

    controls = sorted(n for n, c in cells.items() if c.get("case_group") == "ctrl")
    ctrl_fail = [n for n, e in void if n in controls]
    print("== controls")
    for n in controls:
        c = cells[n]
        print("   %-34s create=%-14s stage=%-8s control_pass=%s"
              % (n, c.get("create_result"), c.get("error_stage"), c.get("control_pass")))
    print("controls_found=%d controls_failed=%d" % (len(controls), len(ctrl_fail)))
    if ctrl_fail:
        print("OUTCOME=INSTRUMENT-RED controls=%s" % ctrl_fail)
        return 2
    if missing:
        print("OUTCOME=DEFECT required_cells_missing=%d" % len(missing))
        return 3
    if dups or unclaimed:
        print("OUTCOME=DEFECT identity_or_unclaimed")
        return 3
    if void:
        print("OUTCOME=PARTIAL blocked_or_void=%d" % len(void))
        return 0
    print("OUTCOME=PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
