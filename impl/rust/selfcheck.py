#!/usr/bin/env python3
"""SENDGUARD rust seat self-check - the seat's own validator, not spec/validate.py.

Checks four things and prints its denominators:
  1. every published face against the frozen spec/schema.json (required fields, types, enums),
     with duplicate keys refused (a repeated key parses and silently keeps the last value)
  2. every status word against the closed set parsed out of spec/canonical.md, plus the rev3 words
     that live only in the schema (length_unit, name_encoding, verdict_via)
  3. the NOTICE rev3 rule that the schema does not encode: a cell carrying an
     os_legality_verdict must carry verdict_via naming the tool that was asked
  4. the denominators against spec/cells-required.json: required rows answered, missing rows
     (blocked with command + exit code + one attempted fix), and extras marked extra: true

Every rule it enforces is exercised green AND red on a synthetic face: a validator that has only
ever been seen accepting is not proven to work.

Exit codes:
  0 all cells valid, every required row answered, extras marked, arms pass
  1 at least one VOID cell
  2 an arm of this validator failed, or the controls failed (the ruler, not the measurement)
  3 a required row is unanswered and not blocked, or an extra is unmarked
  4 inputs unreadable / results dir missing
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
RESULTS = os.path.join(REPO, "results", "rust.windows.x64")
SCHEMA = os.path.join(REPO, "spec", "schema.json")
CANON = os.path.join(REPO, "spec", "canonical.md")
CASES = os.path.join(REPO, "spec", "cases.yaml")
REQUIRED_LIST = os.path.join(REPO, "spec", "cells-required.json")
RUN_CELLS = os.path.join(HERE, "run_cells.py")

SET_FIELDS = ("create_result", "read_result", "error_stage", "os_legality_verdict",
              "path_form", "longpath_mechanism", "case_group", "attribution_layer")
# rev3 words that exist only in the schema, not in canonical.md
SCHEMA_ONLY_SETS = ("length_unit", "name_encoding", "verdict_via")
# ci/equality.py's own behaviour list and identity fields, copied here so the audit is checkable
BEHAVIOUR = ["case_group", "create_result", "error_stage", "os_legality_verdict", "read_result",
             "path_form", "longpath_mechanism", "length_unit", "name_encoding", "name_source",
             "name_landed_as", "name_mutated", "roundtrip_ok", "enum_to_stat_agrees",
             "bytes_written", "bytes_on_disk", "phantom", "control_pass", "instrument_red",
             "deps_direct", "deps_total", "mechanism_class", "len_triple", "verdict_via"]
SUB_FIELDS = ("base_len", "builder", "reader", "packer", "extractor", "path_form",
              "member", "member_index", "requested_form")
NUMERIC = {"attempt": 1, "elapsed_ms": 0, "elapsed_ms_harness": 0, "total_path_len": 0,
           "name_len": 0, "bytes_written": None, "bytes_on_disk": None, "enumeration_count": 0,
           "unclaimed_extras": None, "deps_direct": 0, "deps_total": 0, "base_len": 0, "max_ok": 0}


def sha_hex(b):
    return hashlib.sha256(b).hexdigest()


def load_closed_sets():
    text = io.open(CANON, encoding="utf-8").read()
    sets = {}
    for m in re.finditer(r"(?m)^## \d+\. ([a-z_]+)[^\n]*$", text):
        field = m.group(1)
        if field not in SET_FIELDS:
            continue
        nxt = text.find("\n## ", m.end())
        block = text[m.end(): nxt if nxt > 0 else len(text)]
        # Only the WORD being defined is a status word. canonical.md section 5 defines
        # `not_applicable` and its meaning column says "Requires `read_skipped_reason`", and a
        # whole-block scan harvests that field name as a legal read_result value - which silently
        # accepts a typo instead of voiding it. ci/equality.py's load_closed_sets has the same
        # over-grab (measured: its read_result set carries read_skipped_reason); this seat reads
        # one token per table row's leading cell, and every non-table line's backticked words.
        words = set()
        for line in block.splitlines():
            row = line.strip()
            if row.startswith("|"):
                cells = [c for c in row.split("|")]
                lead = cells[1] if len(cells) > 1 else ""
                m2 = re.match(r"\s*`([A-Za-z][A-Za-z0-9_]*)`", lead)
                if m2:
                    words.add(m2.group(1))
            else:
                words.update(re.findall(r"`([A-Za-z][A-Za-z0-9_]*)`", line))
        sets[field] = words
    return sets


def load_schema():
    return json.loads(io.open(SCHEMA, encoding="utf-8").read())


def load_required(path):
    doc = json.loads(io.open(path, encoding="utf-8").read())
    rows = []
    for r in doc.get("required_cells", []):
        rows.append((r["case_group"], r["case_id"], tuple(sorted((r.get("sub_identity") or {}).items())), None))
    for r in doc.get("tapi_cells_per_language", []):
        if r.get("language") == "rust":
            rows.append(("tapi", r["case_id"], tuple(sorted((r.get("sub_identity") or {}).items())), r["api_entry"]))
    raw = open(path, "rb").read()
    return rows, doc, sha_hex(raw)


def declared_fields(c):
    """rev4's gate honours a cell-declared sub_identity; a port that adds a dimension must be able
    to say so, or its cells collide. Same rule is applied here so the two readers agree."""
    declared = c.get("sub_identity")
    if isinstance(declared, list):
        chosen = [f for f in declared if c.get(f) not in (None, "")]
        if chosen:
            return chosen
    elif isinstance(declared, dict):
        chosen = [f for f in declared if declared[f] is not None and c.get(f) not in (None, "")]
        if chosen:
            return chosen
    return [f for f in SUB_FIELDS if c.get(f) not in (None, "")]


def cell_contract_key(c):
    """The contract row this face answers, in cells-required.json's own shape.

    The cell's own declaration decides: a face that declares an empty sub_identity is saying
    "no dimension varies here", which is exactly the manifest's {} row. gate_identity() keeps the
    gate's fallback behaviour for the collision audit, because ci/equality.py substitutes its own
    default list when it sees an empty declaration.
    """
    declared = c.get("sub_identity")
    if isinstance(declared, list):
        fields = [f for f in declared if c.get(f) not in (None, "")]
    elif isinstance(declared, dict):
        fields = [f for f in declared if c.get(f) not in (None, "")]
    else:
        fields = [f for f in SUB_FIELDS if c.get(f) not in (None, "")]
    if c.get("case_group") == "tapi" and c.get("case_id") == "T-API":
        # the manifest keys a T-API row on api_entry outside sub_identity; keeping it out of the
        # tuple is what stops one dimension from being counted twice
        return (c["case_group"], c["case_id"], (), c.get("api_entry"))
    sub = tuple(sorted((f, c[f]) for f in fields if f != "api_entry"))
    return (c["case_group"], c["case_id"], sub, None)


SUB_FIELDS_REV4 = SUB_FIELDS + ("path_form", "member", "member_index", "requested_form")


def gate_identity(c):
    """rev4's ci/equality.py honours a cell-declared sub_identity; fall back to the known dimensions."""
    declared = c.get("sub_identity")
    fields = list(SUB_FIELDS_REV4)
    if isinstance(declared, list):
        chosen = [f for f in declared if c.get(f) not in (None, "")]
        fields = chosen or fields
    elif isinstance(declared, dict):
        fields = [f for f in declared if declared[f] is not None] or fields
    sub = tuple((f, c[f]) for f in fields if isinstance(c.get(f), (int, str)) and c.get(f) != "")
    return (c.get("case_group"), c.get("case_id"), sub)


def digest_of(c):
    return json.dumps({k: c.get(k, "<absent>") for k in BEHAVIOUR}, sort_keys=True, default=str)


def required_ok(cell, schema):
    errs = []
    for f in schema["required"]:
        if f not in cell:
            errs.append("missing required field: %s" % f)
    for f, spec in schema.get("properties", {}).items():
        if f == "properties" or not isinstance(spec, dict) or f not in cell:
            continue
        v = cell[f]
        if "const" in spec and v != spec["const"]:
            errs.append("%s=%r != schema const %r" % (f, v, spec["const"]))
        if "enum" in spec and v not in spec["enum"]:
            errs.append("%s=%r not in schema enum %s" % (f, v, spec["enum"]))
        t = spec.get("type")
        if t:
            allowed = t if isinstance(t, list) else [t]
            ok = (("null" in allowed and v is None)
                  or ("string" in allowed and isinstance(v, str))
                  or ("integer" in allowed and isinstance(v, int) and not isinstance(v, bool))
                  or ("boolean" in allowed and isinstance(v, bool))
                  or ("object" in allowed and isinstance(v, dict))
                  or ("array" in allowed and isinstance(v, list)))
            if not ok:
                errs.append("%s=%r has type %s, schema allows %s" % (f, v, type(v).__name__, allowed))
        if "pattern" in spec and isinstance(v, str) and not re.match(spec["pattern"], v):
            errs.append("%s does not match pattern %s" % (f, spec["pattern"]))
    return errs


def read_result_words(schema, sets):
    """The two rulers' word sets for read_result, measured, so the disagreement is on the record."""
    canon = sets.get("read_result", set())
    sch = set(schema.get("properties", {}).get("read_result", {}).get("enum", []))
    return canon, sch


def check_cell(cell, schema, sets, pinned_entries, require_verdict_via=True):
    errs = []
    canon_rr, schema_rr = read_result_words(schema, sets)
    allowed = canon_rr | schema_rr
    if cell.get("read_result") in allowed and cell.get("read_result") not in schema_rr:
        # a rev4 word canonical.md carries and schema.json does not: not a VOID, it is the contract's
        # own fifth word; every other field is still checked against schema.json verbatim
        patched = json.loads(json.dumps(schema))
        patched.setdefault("properties", {}).setdefault("read_result", {})["enum"] = sorted(allowed)
        errs = required_ok(cell, patched)
    else:
        errs = required_ok(cell, schema)
    if cell.get("read_result") == "not_applicable" and not cell.get("read_skipped_reason"):
        errs.append("read_result=not_applicable without read_skipped_reason (canonical.md section 5 requires it)")
    for f in SET_FIELDS:
        if f == "read_result" and cell.get(f) == "not_applicable":
            continue
        if f in cell and cell[f] is not None and f in sets and cell[f] not in sets[f]:
            errs.append("status word %s=%r is outside the closed set of spec/canonical.md" % (f, cell[f]))
    for f in SCHEMA_ONLY_SETS:
        enum = schema.get("properties", {}).get(f, {}).get("enum")
        if enum and f in cell and cell[f] not in enum:
            errs.append("%s=%r not in rev3 enum %s" % (f, cell[f], enum))
    if require_verdict_via and "os_legality_verdict" in cell and "verdict_via" not in cell:
        errs.append("NOTICE rev3 item 4: the cell carries os_legality_verdict but does not name the tool asked (verdict_via missing)")
    for f, minimum in NUMERIC.items():
        if f in cell and cell[f] is not None:
            if not isinstance(cell[f], int) or isinstance(cell[f], bool):
                errs.append("%s must be an integer, got %r" % (f, cell[f]))
            elif minimum is not None and cell[f] < minimum:
                errs.append("%s=%r below the floor %r" % (f, cell[f], minimum))
    if cell.get("language") != "rust":
        errs.append("language=%r is not this seat's language" % cell.get("language"))
    if cell.get("os") != "windows":
        errs.append("os=%r is not the os this face measured" % cell.get("os"))
    if cell.get("api_entry") not in pinned_entries:
        errs.append("api_entry=%r is not in the pinned rust entry list" % cell.get("api_entry"))
    for t in ("sha256_self", "sha256_truth"):
        if t in cell and cell[t] is not None and not re.fullmatch(r"[0-9a-f]{64}", str(cell[t])):
            errs.append("%s is not 64 hex" % t)
    lengths = [f for f in ("name_len", "total_path_len", "base_len", "max_ok") if f in cell]
    if lengths and "length_unit" not in cell:
        errs.append("cell records %s but no length_unit, so those widths are unlabelled (NOTICE rev3 item 3)" % ",".join(lengths))
    if cell.get("name_encoding") == "utf16_code_units":
        errs.append("name_encoding records a length unit, which is the pre-rev3 collision NOTICE item 3")
    if cell.get("create_result") == "ok" and cell.get("bytes_on_disk") is None:
        errs.append("create_result=ok with bytes_on_disk=null (no disk truth behind the claim)")
    return errs


def parse_face(raw):
    """Parse, refusing duplicate keys - json.loads otherwise keeps the last value silently."""
    dups = []

    def hook(pairs):
        keys = [k for k, _ in pairs]
        for k in set(keys):
            if keys.count(k) > 1:
                dups.append(k)
        return dict(pairs)

    obj = json.loads(raw.decode("utf-8"), object_pairs_hook=hook)
    if dups:
        raise ValueError("duplicate keys in one object: %s" % sorted(set(dups)))
    return obj


BASE_FACE = {
    "format_version": 1, "case_id": "T01", "case_group": "trap", "language": "rust", "os": "windows",
    "api_entry": "std::fs::File::create", "attempt": 1, "name_source": "434f4e2e747874",
    "length_unit": "utf16_code_units", "name_encoding": "hex_raw_bytes", "verdict_via": "win32",
    "path_form": "plain", "longpath_mechanism": "none", "create_result": "ok", "error_stage": "null",
    "read_result": "eof", "os_legality_verdict": "illegal", "harness_version": "S02-rust-seat-1",
    "started_at": "2026-10-11T04:30:00+08:00", "elapsed_ms": 3, "mechanism_class": "reserved_device_name",
    "attribution_layer": "L1", "bytes_written": 28, "bytes_on_disk": 0, "deps_direct": 0, "deps_total": 0,
    "sha256_self": "0" * 64, "phantom": True, "name_len": 7, "total_path_len": 90,
}


def arms(schema, sets, pinned):
    """Two-sided self-test. A red arm that does not fail is a dead rule."""
    base = dict(BASE_FACE)
    res = [("green: a rev3-compliant cell passes", check_cell(dict(base), schema, sets, pinned) == [],
            check_cell(dict(base), schema, sets, pinned))]
    mutations = [
        ("verdict_via missing", lambda c: c.pop("verdict_via")),
        ("verdict_via invented word", lambda c: c.update(verdict_via="rust")),
        ("length_unit missing after rename", lambda c: c.pop("length_unit")),
        ("length_unit holding the old name_encoding value", lambda c: c.update(length_unit="hex_raw_bytes")),
        ("name_encoding still recording a length unit", lambda c: c.update(name_encoding="utf16_code_units")),
        ("name_encoding hex_utf16le spelled wrong", lambda c: c.update(name_encoding="hex_utf16")),
        ("format_version as the string true", lambda c: c.update(format_version="true")),
        ("unknown status word", lambda c: c.update(create_result="refused_silently")),
        ("missing required field", lambda c: c.pop("read_result")),
        ("attempt zero", lambda c: c.update(attempt=0)),
        ("sha256_self truncated", lambda c: c.update(sha256_self="abc123")),
        ("unpinned entry", lambda c: c.update(api_entry="std::io::copy")),
        ("create ok without disk truth", lambda c: c.update(bytes_on_disk=None)),
        ("attribution_layer outside set", lambda c: c.update(attribution_layer="L4")),
    ]
    for label, mutate in mutations:
        c = dict(base)
        mutate(c)
        errs = check_cell(c, schema, sets, pinned)
        res.append(("red: %s is refused" % label, len(errs) > 0, errs[:1]))
    # duplicate-key arm, on raw text rather than a dict
    good_raw = b'{"a": 1, "b": 2}'
    dup_raw = b'{"a": 1, "a": 2}'
    try:
        parse_face(good_raw)
        ok_good = True
    except ValueError:
        ok_good = False
    try:
        parse_face(dup_raw)
        ok_dup = False
    except ValueError:
        ok_dup = True
    res.append(("green: a plain object parses", ok_good, None))
    res.append(("red: a duplicate key is refused", ok_dup, None))
    # the closed-set scan must not silently return an empty rule
    blind = [f for f in SET_FIELDS if not sets.get(f)]
    res.append(("green: every canonical.md field has a parsed closed set", blind == [], blind))
    missing_enum = [f for f in SCHEMA_ONLY_SETS if not schema.get("properties", {}).get(f, {}).get("enum")]
    res.append(("green: every rev3 word has a schema enum", missing_enum == [], missing_enum))
    # rev4 fifth word: green when it passes, red when not_applicable is used without a reason
    canon, sch = read_result_words(schema, sets)
    good = dict(BASE_FACE, read_result="not_applicable", read_skipped_reason="creation refused the name")
    res.append(("green: canonical.md's rev4 word is accepted", check_cell(good, schema, sets, pinned) == [],
                check_cell(good, schema, sets, pinned)))
    naked = dict(BASE_FACE, read_result="not_applicable")
    naked.pop("read_skipped_reason", None)
    res.append(("red: not_applicable without read_skipped_reason is refused",
                len(check_cell(naked, schema, sets, pinned)) > 0, check_cell(naked, schema, sets, pinned)[:1]))
    declared_empty = dict(BASE_FACE)
    declared_empty["sub_identity"] = {}
    res.append(("green: an empty sub_identity object means no varying dimension",
                cell_contract_key(declared_empty) == ("trap", "T01", (), None), cell_contract_key(declared_empty)))
    obj = dict(BASE_FACE, sub_identity={"base_len": 78, "path_form": "plain"}, base_len=78)
    res.append(("green: an object declaration keys the cell on both dimensions",
                cell_contract_key(obj) == ("trap", "T01", (("base_len", 78), ("path_form", "plain")), None),
                cell_contract_key(obj)))
    # the over-grab rule: a field name must never be an accepted status word
    fake = dict(BASE_FACE, read_result="read_skipped_reason")
    res.append(("red: a field name mentioned in canonical.md is not a status word",
                len([e for e in check_cell(fake, schema, sets, pinned) if "read_result" in e]) > 0,
                check_cell(fake, schema, sets, pinned)[:1]))
    for w in ("ok", "eof", "err6", "hang"):
        good_w = dict(BASE_FACE, read_result=w, read_skipped_reason=None)
        good_w.pop("read_skipped_reason", None)
        res.append(("green: the pre-rev4 word %s still passes" % w,
                    len([e for e in check_cell(good_w, schema, sets, pinned) if "read_result" in e]) == 0, None))
    res.append(("note: read_result word sets differ between the two rulers", True,
                ["canonical=%s schema=%s" % (sorted(canon), sorted(sch)) if canon != sch else "identical"]))
    return res


def main():
    print("results_root=%s" % RESULTS)
    if not os.path.isdir(RESULTS):
        print("INSTRUMENT-RED\nOUTCOME=VOID reason=results dir missing")
        return 4
    schema = load_schema()
    sets = load_closed_sets()
    required_rows, contract, contract_sha = load_required(REQUIRED_LIST)
    blocked_path = os.path.join(HERE, "blocked-rows.json")
    blocked_rows = json.loads(io.open(blocked_path, encoding="utf-8").read()) if os.path.isfile(blocked_path) else []
    blocked_keys = set()
    blocked_problems = []
    for b in blocked_rows:
        blocked_keys.add((b.get("case_group"), b.get("case_id"),
                          tuple(sorted((b.get("sub_identity") or {}).items())), None))
        for need in ("command", "exit_code", "attempted_fix"):
            if b.get(need) in (None, ""):
                blocked_problems.append("%s: blocked row without %s" % (b.get("case_id"), need))
    sys.path.insert(0, HERE)
    import run_cells  # the seat's own driver, reused only to recompute the plan and the pinned list

    parsed = run_cells.parse_cases(CASES)
    cases, api_rust = parsed[0], parsed[1]
    pinned = set(api_rust)
    primary = contract["primary_entry_per_port"]["rust"]
    if primary not in pinned:
        print("INSTRUMENT-RED: contract primary entry %r is not pinned for rust %s" % (primary, sorted(pinned)))
        return 2

    files = sorted(glob.glob(os.path.join(RESULTS, "*.json")))
    faces, void, unparseable = {}, [], []
    for p in files:
        name = os.path.basename(p)
        raw = open(p, "rb").read()
        if raw[:3] == b"\xef\xbb\xbf":
            void.append((name, ["UTF-8 BOM on a published face"]))
            continue
        try:
            cell = parse_face(raw)
        except (ValueError, UnicodeDecodeError) as e:
            unparseable.append((name, str(e)[:120]))
            void.append((name, ["unparseable or duplicate-keyed: %s" % str(e)[:120]]))
            continue
        errs = check_cell(cell, schema, sets, pinned)
        if errs:
            void.append((name, errs))
        else:
            faces[name] = cell

    # contract comparison
    answered = {}
    for name, c in faces.items():
        answered.setdefault(cell_contract_key(c), []).append(name)
    missing = [r for r in required_rows if r not in answered and r not in blocked_keys]
    blocked_answered = [r for r in required_rows if r not in answered and r in blocked_keys]
    dup_rows = {k: v for k, v in answered.items() if k in required_rows and len(v) > 1}
    required_set = set(required_rows)
    extras = {n: c for n, c in faces.items() if cell_contract_key(c) not in required_set}
    unmarked_extra = [n for n, c in extras.items() if c.get("extra") is not True]
    marked_as_extra_but_required = [n for n, c in faces.items()
                                    if c.get("extra") is True and cell_contract_key(c) in required_rows]

    # gate identity audit: this port's faces keyed the way ci/equality.py keys them
    identities = {}
    for n, c in faces.items():
        identities.setdefault(gate_identity(c), []).append(n)
    multi = {k: v for k, v in identities.items() if len(v) > 1}
    disagree = {}
    for k, v in multi.items():
        digs = {digest_of(faces[n]) for n in v}
        if len(digs) > 1:
            disagree[k] = v
    print("gate_identity_audit: faces=%d identities=%d identities_with_more_than_one_face=%d of_which_digest_disagree=%d"
          % (len(faces), len(identities), len(multi), len(disagree)))
    for k, v in sorted(disagree.items()):
        req = "REQUIRED-ROW" if k[1] == "T-API" else "extra"
        print("   %s %s -> %s" % (req, str(k), ", ".join(sorted(v))[:150]))

    arm_results = arms(schema, sets, pinned)
    arms_fail = [r for r in arm_results if not r[1]]

    ctrl = [c for c in faces.values() if c.get("case_group") == "ctrl"]
    controls_pass = len(ctrl) == 5 and all(c.get("control_pass") is True for c in ctrl)
    if len(ctrl) != 5:
        arms_fail.append(("green: five control faces are published", False, ["found %d" % len(ctrl)]))

    # blocked: asked of the driver, not asserted from prose. The rev3 required list contains no
    # blind rows, so the blind cells are reported as not_required instead.
    bp = subprocess.run([sys.executable, RUN_CELLS, "--plan-blind"], stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT, shell=False)
    blind_rc = bp.returncode
    blind_rows_in_required = [r for r in required_rows if r[0] == "blind"]
    print("blind rows in the rev3 required list=%d ; --plan-blind exit=%d" % (len(blind_rows_in_required), blind_rc))
    blocked = [{"row": r, "status": "blocked"} for r in missing]

    print("files_scanned=%d" % len(files))
    print("cells_required=%d" % len(required_rows))
    print("cells_required_answered=%d" % (len(required_rows) - len(missing)))
    print("cells_produced=%d" % len(faces))
    print("cells_valid=%d" % len(faces))
    print("cells_blocked=%d (emitted as blocked records with command, exit code and one attempted fix)" % len(blocked_answered))
    print("cells_unanswered_and_unblocked=%d" % len(missing))
    for b in blocked_problems:
        print("BLOCKED-ROW-INCOMPLETE %s" % b)
    if blocked_rows:
        print("blocked rows live in %s, not in results/: cell-identity section 3 keeps non-cells out of that directory, and canonical.md has no closed word for a measurement that never ran" % os.path.relpath(blocked_path, REPO))
    print("extra=%d" % len(extras))
    print("cells_void=%d" % len(void))
    print("cells_hang=%d" % sum(1 for c in faces.values() if c.get("create_result") == "hang"))
    print("controls_pass=%s (control faces read=%d)" % (controls_pass, len(ctrl)))
    print("contract=%s sha256=%s generated_by=%s" % (os.path.relpath(REQUIRED_LIST, REPO), contract_sha[:16], contract.get("generated_by")))
    print("arms_total=%d arms_failed=%d" % (len(arm_results), len(arms_fail)))
    print("closed_sets=%s" % json.dumps({k: sorted(v) for k, v in sorted(sets.items())}, ensure_ascii=True))
    print("verdict_via values=%s" % json.dumps(sorted({str(c.get("verdict_via")) for c in faces.values()})))
    print("rev3_fields: length_unit=%d name_encoding=%d verdict_via=%d format_version_int=%d"
          % (sum(1 for c in faces.values() if "length_unit" in c),
             sum(1 for c in faces.values() if "name_encoding" in c),
             sum(1 for c in faces.values() if "verdict_via" in c),
             sum(1 for c in faces.values() if c.get("format_version") == 1)))
    if missing:
        for r in missing:
            print("MISSING_REQUIRED_ROW %s" % json.dumps(list(map(str, r))))
    if unmarked_extra:
        print("UNMARKED_EXTRA %d %s" % (len(unmarked_extra), json.dumps(sorted(unmarked_extra)[:12])))
    if marked_as_extra_but_required:
        print("REQUIRED_ROW_MARKED_EXTRA %s" % json.dumps(sorted(marked_as_extra_but_required)))
    if dup_rows:
        for k, v in dup_rows.items():
            print("DUPLICATE_ANSWER_FOR_REQUIRED_ROW %s -> %s" % (json.dumps([str(x) for x in k]), ", ".join(sorted(v))))
    for name, errs in void:
        print("VOID %s" % name)
        for e in errs[:4]:
            print("      - %s" % e)
    for r in arms_fail:
        print("ARM-FAIL %s | %s" % (r[0], r[2]))

    # rev3 report numbers, read back off the faces
    buckets = {}
    for c in faces.values():
        buckets.setdefault(c.get("case_group"), {}).setdefault(c.get("create_result"), 0)
        buckets[c.get("case_group")][c.get("create_result")] += 1
    print("per_group_create_result=%s" % json.dumps(buckets, sort_keys=True))
    print("phantom=%d mutated=%d unclaimed=%d cleanup_failed=%d deps_direct_1=%d deps_direct_0=%d"
          % (sum(1 for c in faces.values() if c.get("phantom") is True),
             sum(1 for c in faces.values() if c.get("name_mutated") is True),
             sum(1 for c in faces.values() if isinstance(c.get("unclaimed_extras"), int) and c["unclaimed_extras"] != 0),
             sum(1 for c in faces.values() if c.get("cleanup_failed") is True),
             sum(1 for c in faces.values() if c.get("deps_direct") == 1),
             sum(1 for c in faces.values() if c.get("deps_direct") == 0)))

    summary = {
        "files_scanned": len(files), "cells_required": len(required_rows),
        "cells_required_answered": len(required_rows) - len(missing), "cells_produced": len(faces),
        "cells_valid": len(faces), "cells_blocked": len(missing), "extra": len(extras),
        "cells_void": [list(n) for n, _ in void], "controls_pass": controls_pass,
        "arms_total": len(arm_results), "arms_failed": [r[0] for r in arms_fail],
        "contract": {"path": REQUIRED_LIST, "sha256": contract_sha, "rows_for_rust": len(required_rows),
                     "primary_entry": primary, "base_len_ladder": contract.get("base_len_ladder"),
                     "generated_by": contract.get("generated_by"), "withdraws": contract.get("withdraws"),
                     "spec_blob_sha256": contract.get("spec_blob_sha256")},
        "gate_identity": {"identities": len(identities), "multi_face": {str(k): v for k, v in multi.items()},
                          "disagreeing": {str(k): v for k, v in disagree.items()}},
        "missing_required_rows": [list(map(str, r)) for r in missing],
        "unmarked_extra": sorted(unmarked_extra),
        "blind": {"rows_in_required_list": len(blind_rows_in_required), "plan_blind_exit": blind_rc,
                  "note": "the rev3 required list publishes no blind rows; the frozen table still publishes no blind sample hex"},
    }
    with open(os.path.join(HERE, "selfcheck-summary.json"), "wb") as fh:
        fh.write((json.dumps(summary, indent=2, ensure_ascii=True) + "\n").encode("utf-8"))

    if arms_fail:
        print("INSTRUMENT-RED")
        return 2
    if not controls_pass:
        print("INSTRUMENT-RED")
        return 2
    if void or unparseable:
        print("OUTCOME=VOID cells=%d" % len(void))
        return 1
    if missing:
        print("OUTCOME=BLOCKED rows=%d (emit each as status blocked with command, exit code and one attempted fix)" % len(missing))
        return 3
    if blocked_problems:
        print("INSTRUMENT-RED")
        return 2
    if unmarked_extra or dup_rows or marked_as_extra_but_required:
        print("OUTCOME=NOT-COMPARABLE reason=extra_or_duplicate_marking")
        return 3
    print("OUTCOME=OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
