#!/usr/bin/env python3
"""SENDGUARD S02 python port -- self-owned validator, contract rev3.

    python impl/python/sg_selfcheck.py            # validate the produced cells
    python impl/python/sg_selfcheck.py --selftest # red/green arms for this ruler

Nothing here imports spec/validate.py or ci/equality.py. The closed sets are
parsed from spec/canonical.md, the field constraints from spec/schema.json and
the question set from spec/cells-required.json -- all three read from the
COMMITTED blob face (git cat-file), so a mid-run edit to the disk copy cannot
change the ruler under the measurement.

Where a frozen file contradicts another frozen file, this ruler reports BOTH
readings as separate counts instead of picking one silently.

Exit codes: 0 = every cell valid and every required cell covered,
2 = at least one void or missing required cell, 3 = a control cell failed
(INSTRUMENT-RED), 4 = this ruler could not load its inputs or its own arms.
"""
import glob
import hashlib
import io
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
CELLS = os.path.join(REPO, "results", "python.windows.x64")

# ci/equality.py:35-41 -- the behavioural fields the cross-port digest reads.
BEHAVIOUR = ["case_group", "create_result", "error_stage", "os_legality_verdict",
             "read_result", "path_form", "longpath_mechanism", "name_encoding",
             "name_source", "name_landed_as", "name_mutated", "roundtrip_ok",
             "enum_to_stat_agrees", "bytes_written", "bytes_on_disk", "phantom",
             "control_pass", "instrument_red", "deps_direct", "deps_total",
             "mechanism_class", "len_triple"]
# ci/equality.py:47 -- the ONLY sub-identity dimensions the gate can see, and it
# reads them as top-level fields of the cell, not from a nested object.
SUB_FIELDS = ("base_len", "builder", "reader", "packer", "extractor")

PROBE_TIMEOUT_S = 5.0
PINNED = ["open_wb", "os.mkdir", "pathlib.write_bytes", "os.rename"]
PRIMARY = "open_wb"
RESERVED_CLASS = "reserved_device_name"


def git_blob(path):
    r = subprocess.run(["git", "-C", REPO, "cat-file", "blob", "HEAD:%s" % path],
                       capture_output=True)
    if r.returncode != 0:
        raise SystemExit("VOID ruler cannot read blob %s rc=%d" % (path, r.returncode))
    return r.stdout


def load_canonical(blob):
    """Closed sets from spec/canonical.md, parsed here (not imported).

    Table sections take the first backticked token of each row; inline sections
    take every backticked token. Case-tolerant because attribution_layer's words
    are L1/L2/L3/L3_interaction -- ci/equality.py's lowercase-only pattern
    cannot capture those and so checks no words at all for that field.
    """
    text = blob.decode("utf-8")
    toks = r"`([A-Za-z][A-Za-z0-9_]*)`"
    heads = [(m.group(2), m.start(), m.end())
             for m in re.finditer(r"(?m)^## (\d+)\. ([A-Za-z_][A-Za-z0-9_]*)", text)]
    sets = {}
    for i, (field, _s, e) in enumerate(heads):
        nxt = heads[i + 1][1] if i + 1 < len(heads) else len(text)
        block = text[e:nxt]
        first_col = []
        for ln in block.split("\n"):
            if not ln.strip().startswith("|"):
                continue
            c0 = [c.strip() for c in ln.strip().strip("|").split("|")][0]
            m = re.match(toks, c0)
            if m:
                first_col.append(m.group(1))
        words = first_col if first_col else re.findall(toks, block)
        if words:
            sets[field] = set(words)
    return sets


def type_ok(val, t):
    kinds = t if isinstance(t, list) else [t]
    for k in kinds:
        if k == "string" and isinstance(val, str):
            return True
        if k == "integer" and isinstance(val, int) and not isinstance(val, bool):
            return True
        if k == "boolean" and isinstance(val, bool):
            return True
        if k == "number" and isinstance(val, (int, float)) and not isinstance(val, bool):
            return True
        if k == "object" and isinstance(val, dict):
            return True
        if k == "array" and isinstance(val, list):
            return True
        if k == "null" and val is None:
            return True
    return False


def check_cell(cell, schema, canon):
    """Return (violations, notes). Empty violations = valid cell."""
    v, notes = [], []
    props = schema.get("properties", {})
    for f in schema.get("required", []):
        if f not in cell:
            v.append("missing required field: %s" % f)
    for f, spec in props.items():
        if f not in cell or f.startswith("_"):
            continue
        val = cell[f]
        if "const" in spec and val != spec["const"]:
            v.append("const mismatch %s=%r want %r" % (f, val, spec["const"]))
        if "enum" in spec and val not in spec["enum"]:
            v.append("enum mismatch %s=%r not in %r" % (f, val, spec["enum"]))
        if "pattern" in spec and isinstance(val, str) and not re.match(spec["pattern"], val):
            v.append("pattern mismatch %s=%r" % (f, val))
        if "minimum" in spec and isinstance(val, int) and not isinstance(val, bool) \
                and val < spec["minimum"]:
            v.append("minimum violated %s=%r" % (f, val))
        t = spec.get("type")
        if t is not None and not type_ok(val, t):
            v.append("type mismatch %s=%r want %r" % (f, val, t))
    for f, words in canon.items():
        if f in cell and cell[f] is not None and cell[f] not in words:
            v.append("status word outside canonical: %s=%r (allowed: %s)"
                     % (f, cell[f], ",".join(sorted(words))))
    # rev3: NOTICE-rev3.md item 4 and cell-identity.md section 6. schema.json's
    # required[] does not list verdict_via, so it is enforced here, not there.
    if "os_legality_verdict" in cell and "verdict_via" not in cell:
        v.append("verdict_via missing on a cell that carries os_legality_verdict (rev3)")
    return v, notes


def check_order_terms(cell, spec_sha):
    """Sentences from the work order that a cell must be able to prove."""
    p = []
    if cell.get("probe_timeout_s") != PROBE_TIMEOUT_S:
        p.append("probe_timeout_s=%r not 5.0" % cell.get("probe_timeout_s"))
    if cell.get("attempt") != 1:
        p.append("attempt=%r not 1 (a hang must not be retried away)" % cell.get("attempt"))
    if "shell=False" not in str(cell.get("child_spawn_form", "")):
        p.append("child_spawn_form does not name shell=False")
    if cell.get("cleanup_attempted") is not False:
        p.append("cleanup_attempted=%r (M19 forbids deletion)" % cell.get("cleanup_attempted"))
    if cell.get("rev3_migrated"):
        # a migrated record keeps the spec face ITS PROBE READ, and must name the
        # face it was restamped under -- overwriting it would fake provenance
        if cell.get("migrated_under_spec_sha256") != spec_sha:
            p.append("migrated cell does not record migrated_under_spec_sha256 = the "
                     "current blob face")
        if cell.get("spec_sha256") == spec_sha:
            p.append("migrated cell claims the current spec face it never measured")
    elif cell.get("spec_sha256") != spec_sha:
        p.append("spec_sha256 does not equal the recomputed blob face")
    if cell.get("language") != "python" or cell.get("os") != "windows":
        p.append("language/os wrong: %r/%r" % (cell.get("language"), cell.get("os")))
    if cell.get("api_entry") not in PINNED:
        p.append("api_entry=%r outside the pinned python list" % cell.get("api_entry"))
    if cell.get("deps_direct") != 0 or cell.get("deps_total") != 0:
        p.append("dependency count non-zero")
    if cell.get("blocked_leg") and not (cell.get("blocked_reason") or cell.get("read_blocked_reason")):
        p.append("blocked_leg present with no reason string")
    if cell.get("mechanism_class") == RESERVED_CLASS and \
            cell.get("read_result") in ("ok", "eof", "err6", "hang"):
        p.append("RED-LINE-BREACH read_result=%r on a reserved device name"
                 % cell.get("read_result"))
    # rev3: the length unit and the record encoding are different facts now
    if cell.get("length_unit") == cell.get("name_encoding") and "length_unit" in cell:
        p.append("length_unit and name_encoding carry the same value: the rev3 split "
                 "was not applied")
    # rev4: not_applicable is only honest if it says why
    if cell.get("read_result") == "not_applicable":
        rsn = cell.get("read_skipped_reason")
        if not isinstance(rsn, str) or not rsn.strip():
            p.append("read_result=not_applicable without a read_skipped_reason (rev4)")
    if cell.get("read_skipped_reason") and cell.get("read_result") not in (
            "not_applicable", None):
        p.append("read_skipped_reason present but read_result=%r claims a read happened"
                 % cell.get("read_result"))
    # every declared dimension must also sit at the top level: ci/equality.py reads
    # a cell's declared sub_identity and then looks each name up as a cell field
    for k in (cell.get("sub_identity") or {}):
        if k not in cell:
            p.append("declared sub_identity dimension %r is not a top-level field, so "
                     "ci/equality.py cannot resolve it" % k)
    # rev7: the twelve length cells must name the bytes they passed, report the
    # three widths of THAT name, and keep the measured ceiling in its own field
    if cell.get("case_group") == "len" and cell.get("extra") is not True:
        b = (cell.get("sub_identity") or {}).get("base_len")
        ns = cell.get("name_source") or ""
        if isinstance(b, int):
            if len(ns) != 2 * b:
                p.append("rev7: name_source is %d hex chars, not the 2*base_len=%d of the "
                         "component actually passed" % (len(ns), 2 * b))
            lt = cell.get("len_triple")
            if not isinstance(lt, dict) or set(lt) != {"code_points", "utf16_code_units",
                                                       "utf8_bytes"}:
                p.append("rev7: len_triple must be the flat three widths of the name, got %r"
                         % (type(lt).__name__ if lt is not None else None))
            elif any(v != b for v in lt.values()):
                p.append("rev7: len_triple %r does not equal base_len %r for the pinned "
                         "single-unit filler -- this port counted something else" % (lt, b))
        if not isinstance(cell.get("len_ceiling"), int):
            p.append("rev7: measured ceiling must be published in len_ceiling")
    return p


def ident_key(group, case_id, sub, api_entry=None):
    sub = sub or {}
    k = (group, case_id, tuple(sorted((str(a), str(b)) for a, b in sub.items())))
    if group == "tapi":
        k = k + (api_entry,)
    return k


def load_required():
    blob = git_blob("spec/cells-required.json")
    doc = json.loads(blob.decode("utf-8"))
    rows = list(doc.get("required_cells", []))
    tapi = [r for r in doc.get("tapi_cells_per_language", []) if r.get("language") == "python"]
    keys = {}
    for r in rows:
        keys[ident_key(r["case_group"], r["case_id"], r.get("sub_identity"),
                       r.get("api_entry"))] = r
    tkeys = {}
    for r in tapi:
        tkeys[ident_key(r["case_group"], r["case_id"], r.get("sub_identity"),
                        r.get("api_entry"))] = r
    return doc, keys, tkeys, hashlib.sha256(blob).hexdigest()


def gate_key(cell):
    """This ruler's replica of the gate's declared-first keying (rev4).

    The gate's own committed code is executed for the reported number; this
    replica exists only so a disagreement between the two is visible.
    """
    declared = cell.get("sub_identity")
    fields = list(SUB_FIELDS)
    if isinstance(declared, dict):
        fields = [f for f in declared if declared[f] is not None] or fields
    elif isinstance(declared, list):
        fields = [f for f in declared if cell.get(f) is not None] or fields
    parts = []
    for f in fields:
        v = cell.get(f)
        if v is None or v == "":
            continue
        parts.append((f, v if not isinstance(v, dict) else json.dumps(v, sort_keys=True)))
    return (cell.get("case_group") or "?", cell.get("case_id"), tuple(parts))


def gate_digest(cell):
    sub = {k: cell.get(k, "<absent>") for k in BEHAVIOUR}
    return hashlib.sha256(json.dumps(sub, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode("utf-8")).hexdigest()


def parse_baseline(blob):
    """evidence/S00-ctrl-baseline.md table -> control expectations.

    `null` means two different things in that table: in the error_stage column it
    is the canonical status word (spec/canonical.md section 4 lists null among the
    five values), elsewhere it means the baseline has no value. Conflating them
    once made this ruler declare a passing control run INSTRUMENT-RED.
    """
    text = blob.decode("utf-8")
    cols = ["create_result", "error_stage", "error_code", "bytes_written",
            "bytes_on_disk", "read_result", "roundtrip_ok", "sha256_on_disk"]
    out = {}
    for ln in text.split("\n"):
        if not ln.startswith("| T-CTRL-"):
            continue
        vals = [c.strip() for c in ln.strip().strip("|").split("|")]
        row = {}
        for k, v in zip(cols, vals[1:]):
            if k == "error_stage" and v == "null":
                row[k] = "null"
            elif v in ("null", "-"):
                row[k] = None
            elif v == "true":
                row[k] = True
            elif v == "false":
                row[k] = False
            elif v.isdigit():
                row[k] = int(v)
            else:
                row[k] = v
        out[vals[0]] = row
    sha = re.findall(r"[0-9a-f]{64}", text)
    return out, (sha[0] if sha else None)


def check_controls(cells, baseline, base_sha):
    res = {}
    for cid, exp in baseline.items():
        mine = [c for c in cells if c.get("case_id") == cid]
        if not mine:
            res[cid] = ["control cell not produced"]
            continue
        c, mm = mine[0], []
        if cid == "T-CTRL-CANON":
            if c.get("sha256_self") != c.get("sha256_truth"):
                mm.append("two instruments disagree: %r vs %r" %
                          (c.get("sha256_self"), c.get("sha256_truth")))
            if base_sha and c.get("sha256_truth") != base_sha:
                mm.append("sha256_truth=%r != sealed %r" % (c.get("sha256_truth"), base_sha))
        else:
            for k in ("create_result", "error_stage", "bytes_written", "bytes_on_disk",
                      "read_result", "roundtrip_ok"):
                want, got = exp.get(k), c.get(k)
                if want is None:
                    # The S00 baseline was taken by node, which left these columns
                    # empty whenever nothing landed. rev4's fifth word is the same
                    # statement made in a cell, so not_applicable + reason AGREES
                    # with an empty baseline cell; anything else does not.
                    if k == "read_result" and got == "not_applicable" \
                            and c.get("read_skipped_reason"):
                        continue
                    if got is not None:
                        mm.append("%s=%r but the baseline has no value for it" % (k, got))
                elif got != want:
                    mm.append("%s=%r want %r" % (k, got, want))
        res[cid] = mm
    return res


def green_cell(**over):
    c = {
        "format_version": 1, "case_id": "T01", "case_group": "trap",
        "language": "python", "os": "windows", "os_version": "x", "arch": "x64",
        "locale": "en", "api_entry": "open_wb", "attempt": 1,
        "sub_identity": {}, "sub_identity_order": [],
        "name_source": "612e747874", "name_source_kind": "test",
        "path_form": "plain", "longpath_mechanism": "none",
        "length_unit": "code_points", "name_encoding": "hex_raw_bytes",
        "verdict_via": "win32",
        "create_result": "ok", "error_stage": "null", "read_result": "ok",
        "os_legality_verdict": "legal", "mechanism_class": "unknown",
        "attribution_layer": "L1", "harness_version": "test", "implementation_id": "python-port",
        "started_at": "2026-10-11T00:00:00+0800", "elapsed_ms": 1,
        "spec_sha256": "0" * 64, "probe_timeout_s": 5.0,
        "child_spawn_form": "argv list, shell=False, timeout=5.0",
        "cleanup_attempted": False, "deps_direct": 0, "deps_total": 0,
        "bytes_written": 28, "bytes_on_disk": 28, "name_landed_as": "612e747874",
        "name_mutated": False, "roundtrip_ok": True, "enum_to_stat_agrees": True,
        "phantom": False, "control_pass": True, "instrument_red": False,
        "instrument_conflict": False, "len_triple": None, "extra": True,
    }
    c.update(over)
    return c


def selftest(schema, canon, base_blob, cases_blob):
    """Red AND green arms: a ruler that has only ever refused is not proven."""
    arms = []

    def add(name, ok, detail=""):
        arms.append((name, bool(ok), detail))

    v, _n = check_cell(green_cell(), schema, canon)
    add("green: rev3-shaped cell accepted", v == [], str(v)[:160])
    v, _ = check_cell(green_cell(create_result="succeeded"), schema, canon)
    add("red: unknown create_result word flagged", any("canonical" in x or "enum" in x for x in v))
    v, _ = check_cell(green_cell(name_encoding="utf16_code_units"), schema, canon)
    add("red: pre-rev3 name_encoding value rejected by schema",
        any("enum mismatch name_encoding" in x for x in v), str(v)[:120])
    v, _ = check_cell(green_cell(length_unit="codepoint"), schema, canon)
    add("red: invented length_unit rejected", any("length_unit" in x for x in v))
    v, _ = check_cell(green_cell(verdict_via="oracle"), schema, canon)
    add("red: invented verdict_via rejected", any("verdict_via" in x for x in v))
    no_via = dict(green_cell())
    no_via.pop("verdict_via")
    v2, _ = check_cell(no_via, schema, canon)
    add("red: cell carrying a verdict but no verdict_via flagged",
        any("verdict_via missing" in x for x in v2), str(v2)[:120])
    v, _ = check_cell({k: val for k, val in green_cell().items() if k != "case_id"}, schema, canon)
    add("red: missing required field flagged", any("missing required field: case_id" in x for x in v))
    add("red: verdict_via absent from schema.json required[] (contract gap visible)",
        "verdict_via" not in schema.get("required", []))
    p = check_order_terms(green_cell(mechanism_class=RESERVED_CLASS, read_result="ok"), "0" * 64)
    add("red: content read of a reserved name is a breach", any("RED-LINE" in x for x in p))
    okc = green_cell(mechanism_class=RESERVED_CLASS)
    okc.pop("read_result")
    add("green: reserved name with NO read_result leg is not a breach",
        [x for x in check_order_terms(okc, "0" * 64) if "RED-LINE" in x] == [])
    na = green_cell(mechanism_class=RESERVED_CLASS, read_result="not_applicable",
                    read_skipped_reason="red line: contents never opened")
    add("green: reserved name carrying rev4 not_applicable + reason is not a breach",
        [x for x in check_order_terms(na, "0" * 64) if "RED-LINE" in x] == [])
    add("red: not_applicable with no reason is flagged",
        any("read_skipped_reason" in x for x in check_order_terms(
            green_cell(read_result="not_applicable"), "0" * 64)))
    add("red: a reason attached to a cell that claims it read bytes is flagged",
        any("claims a read happened" in x for x in check_order_terms(
            green_cell(read_result="ok", read_skipped_reason="x"), "0" * 64)))
    add("red: probe without the 5s cap is flagged",
        any("probe_timeout_s" in x for x in check_order_terms(green_cell(probe_timeout_s=30), "0" * 64)))
    add("red: attempted deletion is flagged",
        any("M19" in x for x in check_order_terms(green_cell(cleanup_attempted=True), "0" * 64)))
    add("red: length_unit equal to name_encoding is flagged (rev3 split not applied)",
        any("rev3 split" in x for x in check_order_terms(
            green_cell(length_unit="code_points", name_encoding="code_points"), "0" * 64)))
    add("red: base_len hidden only inside sub_identity is flagged",
        any("top-level" in x for x in check_order_terms(
            green_cell(sub_identity={"base_len": 78}), "0" * 64)))
    add("green: base_len copied to the top level is accepted",
        [x for x in check_order_terms(green_cell(sub_identity={"base_len": 78}, base_len=78),
                                      "0" * 64) if "top-level" in x] == [])
    g = green_cell(base_len=78, sub_identity={"base_len": 78})
    add("gate-key: equality.py sees base_len only at top level",
        gate_key(g) == ("trap", "T01", (("base_len", 78),)) and
        gate_key(green_cell(sub_identity={"base_len": 78})) == ("trap", "T01", ()),
        "%r vs %r" % (gate_key(g), gate_key(green_cell(sub_identity={"base_len": 78}))))
    add("green: canonical parse is keyed by field NAME, not section number",
        "create_result" in canon and "case_group" in canon and
        not any(k.isdigit() for k in canon) and
        canon.get("create_result") == {"ok", "err_at_parse", "err_at_syscall", "hang"},
        "keys=%s" % str(sorted(canon.keys()))[:160])
    add("red: a word only in the section-number keying would never be checked",
        canon.get("attribution_layer") == {"L1", "L2", "L3", "L3_interaction"},
        str(canon.get("attribution_layer")))
    der, mem = derive_from_cases(cases_blob,
                                 json.loads(git_blob("evidence/S00/blind-map.json").decode("utf-8")))
    add("green: member counts derived from the frozen hex lists are 2/3/2",
        mem.get("T09") == 2 and mem.get("T14") == 3 and mem.get("T19") == 2, str(mem)[:120])
    len_rows = [r for r in der if r[0] == "len"]
    blind_rows = [r for r in der if r[0] == "blind"]
    add("red: a manifest row the frozen table does not ask for is detected",
        ("trap", "T-BOGUS", ()) not in set(der) and len(len_rows) == 12 and
        len(blind_rows) == 5 and len(der) == 44,
        "len_rows=%d blind_rows=%d rows=%d" % (len(len_rows), len(blind_rows), len(der)))
    fake_bl = {"T-CTRL-X": {"create_result": "err_at_syscall", "error_stage": "syscall",
                           "bytes_written": None, "bytes_on_disk": None,
                           "read_result": None, "roundtrip_ok": None}}
    na_cell = green_cell(case_id="T-CTRL-X", create_result="err_at_syscall",
                         error_stage="syscall", bytes_written=None, bytes_on_disk=None)
    na_cell.pop("roundtrip_ok")
    na_cell.update({"read_result": "not_applicable", "read_skipped_reason": "nothing landed"})
    r1 = check_controls([na_cell], fake_bl, None)["T-CTRL-X"]
    add("green: rev4 not_applicable AGREES with a baseline that has no value there",
        r1 == [], str(r1)[:140])
    ok_cell = dict(na_cell)
    ok_cell["read_result"] = "ok"
    r2 = check_controls([ok_cell], fake_bl, None)["T-CTRL-X"]
    add("red: read=ok where the baseline saw nothing is still a mismatch",
        any("read_result" in x for x in r2), str(r2)[:140])
    bl, bsha = parse_baseline(base_blob)
    add("green: baseline error_stage 'null' is the canonical word, not an absence",
        bl.get("T-CTRL-ASCII", {}).get("error_stage") == "null")
    add("green: baseline bytes_on_disk 'null' is no value",
        bl.get("T-CTRL-PARSE", {}).get("bytes_on_disk") is None)
    add("red: the baseline table yields exactly 5 controls", len(bl) == 5, "got=%d" % len(bl))
    add("red: the sealed CANON sha is a 64-hex digest", bool(bsha) and len(bsha) == 64)
    bad = 0
    for name, ok, detail in arms:
        print("  ARM %-62s %s%s" % (name, "PASS" if ok else "FAIL",
                                    (" detail=" + detail) if (not ok and detail) else ""))
        if not ok:
            bad += 1
    print("selftest_arms=%d passed=%d failed=%d" % (len(arms), len(arms) - bad, bad))
    return bad == 0


def derive_from_cases(cases_blob, blind_doc):
    """Re-derive the required question set from the frozen faces, independently.

    This is not a copy of ci/gen_cells_required.py: member counts come straight
    off the frozen hex lists, the len group per canonical section 2, the rung
    ladder and the two path forms from the manifest itself, and the blind cells
    from evidence/S00/blind-map.json. If the manifest and the frozen table
    disagree, one of them is wrong and the ports cannot both be right.
    """
    text = cases_blob.decode("utf-8")
    _, _, tail = text.partition("\ncases:\n")
    cases, cur = [], None
    for ln in tail.split("\n"):
        m = re.match(r"^\s*-\s+id:\s*(\S+)\s*$", ln)
        if m:
            cur = {"id": m.group(1), "members": 0}
            cases.append(cur)
            continue
        if cur is None:
            continue
        if re.match(r'^\s*-\s+"[0-9a-fA-F]{2,}"\s*(#.*)?$', ln):
            cur["members"] += 1
        elif re.match(r'^\s+sample_hex:\s*"[0-9a-fA-F]{2,}"', ln):
            cur["members"] = max(cur["members"], 1)
    bases = [78, 120, 200]
    rows = []
    for c in cases:
        if c["id"] in ("T17", "T18"):
            for b in bases:
                for face in ("plain", "extended"):
                    rows.append(("len", c["id"], (("base_len", str(b)),
                                                  ("path_form", face))))
            continue
        if c["members"] > 1:
            for i in range(c["members"]):
                rows.append(("trap", "%s-m%d" % (c["id"], i + 1), ()))
        else:
            rows.append(("trap", c["id"], ()))
    for cid in ("T-CTRL-NAMETOOLONG", "T-CTRL-ASCII", "T-CTRL-ILLEGAL-CHAR",
                "T-CTRL-PARSE", "T-CTRL-CANON"):
        rows.append(("ctrl", cid, ()))
    for e in blind_doc.get("entries", []):
        rows.append(("blind", "B%d" % e["blind_id"], ()))
    return rows, {c["id"]: c["members"] for c in cases}


def gate_logic():
    """Use ci/equality.py's OWN committed keying and digest code, not my copy of it.

    The gate's rules moved twice while this port was running (SUB_FIELDS grew,
    then it learned to read a cell's declared sub_identity). Measuring collisions
    against a stale transcription would have published a defect that no longer
    exists, so this executes the committed blob face in a private namespace and
    calls its functions. It reads no results data -- the file's module level only
    defines functions and constants.
    """
    src = git_blob("ci/equality.py").decode("utf-8")
    ns = {"__name__": "sg_gate_under_test",
          "__file__": os.path.join(REPO, "ci", "equality.py")}
    try:
        exec(compile(src, "HEAD:ci/equality.py", "exec"), ns)
        if "key_of" not in ns or "digest" not in ns:
            raise AttributeError("key_of/digest not found")
        return ns, None
    except Exception as e:
        return None, "%s: %s" % (type(e).__name__, str(e)[:120])


def gate_keys_report(cells, req_keys):
    ns, err = gate_logic()
    if ns is None:
        return None, "GATE-LOGIC-UNREADABLE %s (falling back is refused; the number would be mine, not the gate's)" % err

    def collide(pool):
        bykey = {}
        for c in pool:
            try:
                k = ns["key_of"](c)
                d = ns["digest"](c)[0]
            except Exception as e:
                return None, "GATE-LOGIC-CALL-FAILED %s" % str(e)[:120]
            bykey.setdefault(k, []).append((c, d))
        amb = {k: v for k, v in bykey.items() if len(set(d for _c, d in v)) > 1}
        return bykey, amb

    # discover() drops a cell flagged extra BEFORE it keys anything, so an extra
    # cannot collide with a required cell in the real gate. Counting both ways is
    # deliberate: the "if not skipped" figure is the size of the trap that made
    # five ports appear not to have run cells they had published.
    live = [c for c in cells if c.get("extra") is not True]
    bykey, amb = collide(live)
    if amb is None:
        return None, "GATE-LOGIC-CALL-FAILED (live pool)"
    _ak, amb_all = collide(cells)
    req_involved = sum(1 for k, v in amb.items()
                       if any(ident_key(c["case_group"], c["case_id"], c.get("sub_identity"),
                                        c.get("api_entry")) in req_keys for c, _d in v))
    return {"gate_keys": len(bykey), "colliding_keys": len(amb),
            "required_identity_involved": req_involved, "live_cells": len(live),
            "colliding_if_extras_were_not_skipped": len(amb_all or {}),
            "sub_fields_seen": ns.get("SUB_FIELDS"),
            "verdict_fields": ns.get("VERDICT_FIELDS"),
            "probe_fields": ns.get("PROBE_FIELDS"),
            "examples": [(str(k), len(v), len(set(d for _c, d in v)))
                         for k, v in sorted(amb.items(), key=lambda x: str(x[0]))[:6]]}, None


def gate_match(req_doc, cells):
    """Match my cells against the manifest using ci/equality.py's OWN keying.

    This is the number docs/GAP.md will carry, reproduced rather than predicted:
    extra cells are skipped first (that is what made five ports look like they had
    not run blind cells they had published), and tapi keys are excluded from the
    required comparison the same way ci/gap_report.py excludes them.
    """
    ns, err = gate_logic()
    if err:
        return None, err
    req = {}
    for r in req_doc.get("required_cells", []):
        req[(r["case_group"], r["case_id"],
             tuple(sorted((r.get("sub_identity") or {}).items())))] = r
    have, skipped_extra, tapi_published = {}, 0, 0
    for c in cells:
        if c.get("extra") is True:
            skipped_extra += 1
            continue
        k = ns["key_of"](c)
        if k[0] == "tapi":
            tapi_published += 1
            continue
        have.setdefault(k, 0)
        have[k] += 1
    missing = sorted(set(req) - set(have))
    stray = sorted(set(have) - set(req))
    dupes = sorted(k for k, n in have.items() if n > 1)
    return {"required": len(req), "matched": len(set(req) & set(have)),
            "missing": [equality_fmt(k) for k in missing],
            "stray": [equality_fmt(k) for k in stray][:8], "n_stray": len(stray),
            "skipped_extra": skipped_extra, "tapi_published": tapi_published,
            "duplicate_keys": [equality_fmt(k) for k in dupes]}, None


def equality_fmt(k):
    g, c, s = k[0], k[1], k[2]
    return "%s/%s%s" % (g, c, "[" + ",".join("%s=%s" % p for p in s) + "]" if s else "")


def main():
    do_selftest = "--selftest" in sys.argv[1:]
    schema = json.loads(git_blob("spec/schema.json").decode("utf-8"))
    canon = load_canonical(git_blob("spec/canonical.md"))
    cases_blob = git_blob("spec/cases.yaml")
    spec_sha = hashlib.sha256(cases_blob).hexdigest()
    base_blob = git_blob("evidence/S00-ctrl-baseline.md")
    frozen = git_blob("spec/FROZEN.md").decode("utf-8")

    print("ruler_faces_read=git cat-file blob HEAD (not the disk copy)")
    claims = dict(re.findall(r"(?m)^\|\s*(\S+)\s*\|\s*([0-9a-f]{64})\s*\|", frozen))
    verified, mismatched = [], []
    for path, want in sorted(claims.items()):
        try:
            got = hashlib.sha256(git_blob(path)).hexdigest()
        except SystemExit:
            got = None
        (verified if got == want else mismatched).append("%s claim=%s got=%s" %
                                                        (path, want[:12], (got or "?")[:12]))
    print("frozen_hash_claims=%d verified=%d mismatched=%d" %
          (len(claims), len(verified), len(mismatched)))
    for m in mismatched:
        print("  SEAL-MISMATCH %s" % m)
    print("canonical_sets=%s" % json.dumps({k: len(v) for k, v in sorted(canon.items())}))
    missing_words = [w for w in ("name_encoding", "length_unit", "verdict_via")
                     if w not in canon]
    print("rev3_words_with_no_canonical_section=%s (spec/canonical.md line 1 makes any word "
          "outside that file void; these three are defined only in schema.json)"
          % missing_words)
    if do_selftest:
        return 0 if selftest(schema, canon, base_blob, cases_blob) else 4

    files = sorted(glob.glob(os.path.join(CELLS, "*.json")))
    print("cells_dir=%s files_in_cells_dir=%d non_json=%s" %
          (CELLS, len(files), [f for f in sorted(os.listdir(CELLS)) if not f.endswith(".json")]))
    cells, unparsed = [], []
    for f in files:
        try:
            obj = json.loads(io.open(f, encoding="utf-8").read())
        except Exception as e:
            unparsed.append("%s %s" % (os.path.basename(f), str(e)[:80]))
            continue
        if not isinstance(obj, dict) or not obj.get("case_id") or not obj.get("case_group"):
            unparsed.append("%s is not a cell record" % os.path.basename(f))
            continue
        obj["_file"] = os.path.basename(f)
        cells.append(obj)
    print("cells_parsed=%d cells_unparseable_or_not_a_cell=%d" % (len(cells), len(unparsed)))
    for u in unparsed:
        print("  NOT-A-CELL %s" % u)

    valid, void, blocked, order_problems = [], [], [], []
    missing_by_field = {}
    for c in cells:
        v, _n = check_cell(c, schema, canon)
        p = check_order_terms(c, spec_sha)
        if p:
            order_problems.append((c["_file"], p))
        if v:
            void.append((c["_file"], v))
        else:
            valid.append(c["_file"])
        if c.get("cell_blocked"):
            blocked.append(c["_file"])
        for f in BEHAVIOUR:
            if f not in c:
                missing_by_field.setdefault(f, []).append(c["_file"])

    # required-list coverage
    req_doc, req_keys, tapi_keys, req_sha = load_required()
    derived, members = derive_from_cases(
        cases_blob, json.loads(git_blob("evidence/S00/blind-map.json").decode("utf-8")))
    dset = set(derived)
    mset = set((g, c, tuple(s)) for (g, c, s, _e) in
               [(k[0], k[1], k[2], None) for k in req_keys if k[0] != "tapi"])
    only_manifest = sorted(mset - dset)
    only_cases = sorted(dset - mset)
    print("manifest_vs_frozen_table: manifest_rows=%d derived_rows=%d only_in_manifest=%d "
          "only_in_cases_yaml=%d" % (len(mset), len(dset), len(only_manifest), len(only_cases)))
    for x in only_manifest[:6]:
        print("  MANIFEST-ONLY %s" % str(x))
    for x in only_cases[:6]:
        print("  CASES-ONLY %s" % str(x))
    produced_keys = {}
    for c in cells:
        produced_keys.setdefault(ident_key(c["case_group"], c["case_id"],
                                           c.get("sub_identity"), c.get("api_entry")),
                                 []).append(c["_file"])
    all_req = dict(req_keys)
    all_req.update(tapi_keys)
    missing_req = [k for k in req_keys if k not in produced_keys]
    missing_tapi = [k for k in tapi_keys if k not in produced_keys]
    extra_keys = [k for k in produced_keys if k not in all_req]
    dup_keys = {k: v for k, v in produced_keys.items() if len(v) > 1}
    mislabeled = [c["_file"] for c in cells
                  if bool(c.get("extra")) != (ident_key(c["case_group"], c["case_id"],
                                                         c.get("sub_identity"),
                                                         c.get("api_entry")) not in all_req)]
    # the trap that made five ports "miss" cells they had already published: a
    # required cell flagged extra is skipped by ci/equality.py before matching.
    flagged_but_required = [c["_file"] for c in cells
                            if c.get("extra") is True and
                            ident_key(c["case_group"], c["case_id"], c.get("sub_identity"),
                                      c.get("api_entry")) in all_req]
    print("cells_required=%d (+python_tapi=%d) blob_sha=%s"
          % (len(req_keys), len(tapi_keys), req_sha[:16]))
    print("cells_matched=%d/%d required_missing=%d | tapi %d/%d | extra_cells=%d "
          "extra_mislabelled=%d required_but_flagged_extra=%d"
          % (len(req_keys) - len(missing_req), len(req_keys), len(missing_req),
             len(tapi_keys) - len(missing_tapi), len(tapi_keys), len(extra_keys),
             len(mislabeled), len(flagged_but_required)))
    for k in missing_req:
        print("  REQUIRED-MISSING %s" % str(k))
    for k in missing_tapi:
        print("  TAPI-MISSING %s" % str(k))
    for f in flagged_but_required[:8]:
        print("  FLAGGED-EXTRA-BUT-REQUIRED %s" % f)
    for k, v in sorted(dup_keys.items()):
        print("  DUPLICATE-IDENTITY %s -> %s" % (str(k), v))
    for f in mislabeled[:8]:
        print("  EXTRA-FLAG-WRONG %s" % f)

    gm, gmerr = gate_match(req_doc, cells)
    if gmerr:
        print("  GATE-MATCH-UNREADABLE %s" % gmerr)
    else:
        print("gate_rules(gap_report's own path): matched=%d/%d missing=%d outside_list=%d "
              "skipped_as_extra=%d duplicate_keys=%d tapi_published=%d"
              % (gm["matched"], gm["required"], len(gm["missing"]), gm["n_stray"],
                 gm["skipped_extra"], len(gm["duplicate_keys"]), gm["tapi_published"]))
        for m in gm["missing"][:12]:
            print("  GATE-MISSING %s" % m)
        for s in gm["stray"][:6]:
            print("  GATE-OUTSIDE-LIST %s" % s)
        for dk in gm["duplicate_keys"][:6]:
            print("  GATE-DUPLICATE-KEY %s" % dk)

    # what the gate itself would do with these cells -- measured with its OWN
    # committed code, because its keying rules moved twice during this run
    res, gerr = gate_keys_report(cells, all_req)
    if gerr:
        print("  %s" % gerr)
    else:
        print("gate_own_logic SUB_FIELDS=%s" % (res["sub_fields_seen"],))
        print("digest split VERDICT=%s PROBE=%s"
              % (json.dumps(res["verdict_fields"]), json.dumps(res["probe_fields"])))
        print("live(after extra skipped)=%d gate_keys=%d colliding_keys=%d "
              "required_identity_involved=%d | colliding_if_extras_not_skipped=%d" %
              (res["live_cells"], res["gate_keys"], res["colliding_keys"],
               res["required_identity_involved"],
               res["colliding_if_extras_were_not_skipped"]))
        for k, n, d in res["examples"]:
            print("   GATE-COLLISION %s holds %d cells, %d digests" % (k, n, d))

    hist = {}
    for _f, vs in void:
        for x in vs:
            hist[x.split("=")[0][:58]] = hist.get(x.split("=")[0][:58], 0) + 1
    print("void_reason_histogram=%s" % json.dumps(hist, sort_keys=True))
    print("behavioural_fields_absent_from_some_cells=%s" %
          json.dumps({f: len(v) for f, v in sorted(missing_by_field.items())}, sort_keys=True))
    print("order_term_problems=%d" % len(order_problems))
    for f, p in order_problems[:8]:
        print("   ORDER-TERM %s %s" % (f, str(p)[:150]))

    baseline, base_sha = parse_baseline(base_blob)
    ctrl = check_controls(cells, baseline, base_sha)
    ctrl_fail = {k: v for k, v in ctrl.items() if v}
    print("controls_checked=%d control_mismatched=%d" % (len(ctrl), len(ctrl_fail)))
    for k, v in sorted(ctrl.items()):
        print("   CONTROL %-22s %s" % (k, "PASS" if not v else "MISMATCH " + str(v)[:140]))

    n_hang = len([c for c in cells if c.get("create_result") == "hang" or
                  c.get("read_result") == "hang"])
    n_extra = len([c for c in cells if c.get("extra")])
    n_mig = len([c for c in cells if c.get("rev3_migrated")])
    n_super = len([c for c in cells if c.get("superseded_by")])
    print("cells_with_hang=%d cells_blocked=%d could_not_run=%d migrated=%d superseded=%d" %
          (n_hang, len(blocked), len([c for c in cells if c.get("blocked_leg") == "cell"]),
           n_mig, n_super))
    print("")
    n_missing = len(missing_req) + len(missing_tapi)
    print("cells_required=%d cells_matched=%d blocked=%d extra=%d controls_pass=%s"
          % (len(req_keys), len(req_keys) - len(missing_req),
             len([c for c in cells if c.get("run_status") == "blocked" or
                  (c.get("cell_blocked") and c.get("blocked_leg") == "cell")]),
             n_extra, not ctrl_fail))
    print("detail: cells_produced=%d cells_valid=%d legs_blocked(read)=empty=%d "
          "cells_produced_incl_extra=%d python_tapi=%d/%d"
          % (len(cells), len(valid), len(blocked), n_extra,
             len(tapi_keys) - len(missing_tapi), len(tapi_keys)))
    if ctrl_fail:
        print("INSTRUMENT-RED: a control cell did not reproduce the sealed baseline")
        return 3
    if n_missing:
        print("INCOMPLETE: %d required cells absent and not carried as blocked" % n_missing)
        return 2
    return 0 if not void else 2


if __name__ == "__main__":
    sys.exit(main())
