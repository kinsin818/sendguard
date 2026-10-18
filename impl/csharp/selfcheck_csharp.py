#!/usr/bin/env python3
"""SENDGUARD S02 C# port self-check (contract rev3).

Independent of the harness that produced the cells: it re-derives the required cell set from
`spec/cells-required.json`, re-parses the closed words out of `spec/canonical.md` and the enums out
of `spec/schema.json` at run time (not from memory of them), and re-checks arithmetic the harness
cannot fake.

Rev3 fields it insists on: `length_unit` (unit the lengths were counted in), `name_encoding` (how
the name in the record is encoded - a different concept), `verdict_via` (which tool was asked for
the legality verdict).

Prints the denominators the contract asks for:
    cells_required / cells_produced / cells_valid / blocked / extra

Usage:
    python impl/csharp/selfcheck_csharp.py                # validate the port
    python impl/csharp/selfcheck_csharp.py --selftest     # + red/green arms for every gate

Exit codes: 0 clean, 1 at least one VOID cell, 2 INSTRUMENT-RED (control or arm), 3 denominator
mismatch (a required cell missing, or a file in results/ that is not a cell this port declared).
"""
import argparse
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
RESULTS_DIR = os.path.join(REPO, "results", "csharp.windows.x64")
SCHEMA = os.path.join(REPO, "spec", "schema.json")
CANON = os.path.join(REPO, "spec", "canonical.md")
FROZEN = os.path.join(REPO, "spec", "FROZEN.md")
CSPROJ = os.path.join(HERE, "SendGuardProbe.csproj")
GEN_CHECK = os.path.join(REPO, "ci", "gen_cells_required.py")

NULLABLE_OK = {"error_code", "error_message", "bytes_written", "roundtrip_ok",
               "sha256_truth", "sha256_self", "name_landed_as", "name_mutated",
               "requested_vs_landed_len_delta", "len_triple", "bisect_boundary",
               "bisect_conclusive", "create_result", "error_stage", "view_divergence",
               "path_view_landed_as", "stat_error", "legality_winerror", "legality_mechanism",
               "legality_attempted", "legality_reason", "blocked_command", "blocked_exit_code",
               "blocked_fix_attempted", "payload_bytes", "payload_policy", "name_hex_from_child",
               "name_utf16_units", "name_code_points", "name_utf8_bytes", "child_exception",
               "move_source_name", "target_dir_hex", "dir_view_error", "precondition_reason",
               "api_path_len", "landed_name_utf16_units", "read_reason", "child_elapsed_ms",
               "name_reserved", "packer", "extractor", "hang_leg", "verdict_via_method",
               "len_ceiling_boundary_code", "len_ceiling_boundary_attempt",
               "len_ceiling_at_boundary", "regime_expected_ceiling",
               "regime_expected_boundary_code", "regime_observed_ceiling",
               "regime_unresolved_reason", "len_measure_missing", "name_source_rule",
               "api_path_len_recorded", "tier_point_attempts", "len_fill_rule",
               "len_fill_unit_hex", "control_sample_pin", "control_payload_pin",
               "control_payload_sha256", "control_payload_bytes", "control_pin_source",
               "in_required_list", "required_identity", "hang_note", "name_hex_from_child",
               "len_triple_widths_disagree", "type_II_note", "read_attempted",
               "base_len_conflict", "precondition_ok", "instrument_conflict",

               "read_skipped_reason", "bisect_probes_run", "boundary_plus1_result",
               "boundary_plus1_error_code", "regime_expected_max_component",
               "regime_expected_boundary_code", "regime_observed_boundary_code",
               "regime_unresolved_reason", "extra_reason", "error_code", "extended_corroboration",
               "error_code", "supersedes_candidates", "nested_chain_depth", "max_component_len"}

# expectations come from evidence/ctrl-baseline.md, the only allowed source (spec/cases.yaml)
CTRL_EXPECT = {
    "T-CTRL-NAMETOOLONG": {"create_result": "err_at_syscall", "error_stage": "syscall"},
    "T-CTRL-ASCII": {"create_result": "ok", "bytes_written": 28, "bytes_on_disk": 28,
                     "read_result": "ok", "roundtrip_ok": True},
    "T-CTRL-ILLEGAL-CHAR": {"create_result": "err_at_syscall", "error_stage": "syscall"},
    "T-CTRL-PARSE": {"create_result": "err_at_parse", "error_stage": "parse"},
    "T-CTRL-CANON": {"create_result": "ok"},
}
CANON_SHA = "c9fe45b2fee8ea846f0cf4f2cacc2a891e7b082e7719923502d12a9813e21994"
SUB_FIELDS = ("base_len", "builder", "reader", "packer", "extractor")


def load_canonical_sets():
    text = io.open(CANON, encoding="utf-8").read()
    sets = {}
    for m in re.finditer(r"(?m)^## \d+\. ([a-z_]+)[^\n]*$", text):
        field = m.group(1)
        nxt = text.find("\n## ", m.end())
        block = text[m.end(): nxt if nxt > 0 else len(text)]
        sets[field] = set(re.findall(r"`([A-Za-z0-9_]+)`", block))
    return sets


def load_schema():
    with io.open(SCHEMA, encoding="utf-8") as f:
        return json.load(f)


def frozen_spec_sha():
    text = io.open(FROZEN, encoding="utf-8").read()
    m = re.search(r"spec/cases.yaml\s*\|\s*([0-9a-f]{64})", text)
    return m.group(1) if m else None


def harness():
    import importlib.util
    sp = importlib.util.spec_from_file_location("rc", os.path.join(HERE, "run_csharp.py"))
    rc = importlib.util.module_from_spec(sp)
    sys.modules["rc_selfcheck"] = rc
    sp.loader.exec_module(rc)
    return rc


def identity_of(cell):
    """Independent spelling of the contract identity; an arm below proves it agrees with the
    harness's own copy, which is in turn a copy of ci/equality.py's sub_identity()."""
    declared = cell.get("sub_identity")
    sub = {}
    if isinstance(declared, dict):
        sub = {k: v for k, v in declared.items() if v is not None}
    for f in SUB_FIELDS:
        if cell.get(f) is not None and f not in sub:
            sub[f] = cell[f]
    if cell.get("case_group") == "len" and "path_form" not in sub and cell.get("path_form"):
        sub["path_form"] = cell["path_form"]
    key = "%s/%s%s" % (cell["case_group"], cell["case_id"],
                       "".join("[%s=%s]" % (k, sub[k]) for k in sorted(sub) if sub[k] is not None))
    if cell["case_group"] == "tapi":
        key += "[api_entry=%s]" % cell["api_entry"]
    return key


def check_cell(cell, sets, schema, req_ids):
    """Return (errors, warnings). A status word outside canonical.md, or a rev3 field that is
    absent or off-enum, is an error: rev3 made those verdicts non-comparable without a tool name."""
    errs = []
    warn = []
    for f in schema["required"]:
        if f not in cell:
            errs.append("missing required field %s" % f)
    for f, v in cell.items():
        if v is None and f not in NULLABLE_OK:
            errs.append("null in non-nullable field %s" % f)
    props = schema["properties"]
    for f, rule in props.items():
        if f not in cell or cell[f] is None:
            continue
        if "enum" in rule and cell[f] not in rule["enum"]:
            errs.append("%s=%r outside schema enum" % (f, cell[f]))
        if "const" in rule and cell[f] != rule["const"]:
            errs.append("%s=%r != const %r" % (f, cell[f], rule["const"]))
    # rev3: these three are demanded of every port, but spec/schema.json's `required` array
    # still does not list them. Checked here so the gap is visible, not smoothed over.
    for f in ("length_unit", "name_encoding", "verdict_via"):
        if f not in cell:
            errs.append("rev3 field %s absent (docs/NOTICE-rev3.md demands it; schema required[] does not)" % f)
    for f in SET_FIELDS_FOR_CANON:
        if f in sets and cell.get(f) is not None and cell[f] not in sets[f]:
            errs.append("%s=%r outside canonical.md closed set %s" % (f, cell[f], sorted(sets[f])))
    if cell.get("language") != "csharp":
        errs.append("language=%r is not this port" % cell.get("language"))
    if cell.get("os_legality_verdict") in ("legal", "illegal") and cell.get("verdict_via") in (None, "none"):
        errs.append("a legality verdict with no tool named (verdict_via=%r)" % cell.get("verdict_via"))
    if cell.get("case_group") == "len":
        # rev7 rule 1: name_source is hex of the bytes handed to the API. The frozen spec kept prose
        # in its sample_hex for T17/T18, and one port copied that prose as if it were a name it had
        # created - so a length cell is only believed when the bytes say so.
        for f in ("base_len", "component_len", "total_path_len", "len_triple", "len_ceiling",
                  "len_ceiling_conclusive", "len_fill_unit_hex"):
            if cell.get(f) is None:
                errs.append("len cell without %s (cell-identity s1: the varying dimension must be "
                            "a named field, not only a filename)" % f)
        ns = str(cell.get("name_source") or "")
        base = cell.get("base_len") or 0
        unit = cell.get("len_fill_unit_hex") or LEN_FILL.get("unit_hex") or ""
        is_hex = bool(re.match(r"^(?:[0-9a-f]{2})+$", ns))
        if not ns:
            errs.append("len cell without name_source")
        elif not is_hex:
            errs.append("len name_source=%r is not even-length hex: it is a label, not the bytes "
                        "passed to the API (NOTICE-rev7 rule 1)" % ns[:48])
        elif unit and ns != unit * base:
            errs.append("len name_source is not the pinned filler repeated base_len times: expected "
                        "%d x %r, got %r" % (base, unit, ns[:24]))
        if is_hex and cell.get("name_hex_from_child") and ns != cell["name_hex_from_child"]:
            errs.append("name_source does not equal the component the child reported passing (%r vs %r)"
                        % (ns[:24], str(cell["name_hex_from_child"])[:24]))
        trip = cell.get("len_triple")
        if trip and is_hex:
            name = bytes.fromhex(ns)
            text = name.decode("utf-8")
            want = [len(text), len(text.encode("utf-16-le")) // 2, len(name)]
            if list(trip) != want:
                errs.append("len_triple=%r but the three widths of the recorded name are %r "
                            "(code points / UTF-16 units / UTF-8 bytes of THAT name)" % (trip, want))
        if (trip and is_hex and len(set(trip)) == 1 and trip[0] != base
                and cell.get("len_ceiling") in list(trip)):
            errs.append("len_triple carries %r which equals the ceiling %r: the measured ceiling is a "
                        "different quantity and belongs in len_ceiling only (rev7 rule 3)"
                        % (trip, cell.get("len_ceiling")))
        if cell.get("base_len") != cell.get("base_len_measured"):
            errs.append("base_len=%s but the directory measured %s"
                        % (cell.get("base_len"), cell.get("base_len_measured")))
        if cell.get("len_triple") is None or len(cell.get("len_triple") or []) != 3:
            errs.append("len cell without a 3-part len_triple")
    if cell.get("read_result") is None:
        errs.append("read_result=null: rev4 closed this with the word not_applicable, so null is "
                    "no longer a tolerated answer for a cell with nothing to read")
    if cell.get("read_result") == "not_applicable" and not cell.get("read_skipped_reason"):
        errs.append("read_result=not_applicable without read_skipped_reason (canonical.md s5)")
    if cell.get("create_result") == "ok" and cell.get("bytes_on_disk") is None:
        errs.append("create ok without disk truth")
    if cell.get("name_mutated") and cell.get("requested_vs_landed_len_delta") is None:
        errs.append("name mutated without the length delta the IV' gate reads")
    if cell.get("bytes_written") is not None and cell.get("create_result") == "ok":
        if cell.get("bytes_on_disk") is not None and cell["bytes_written"] != cell["bytes_on_disk"]:
            warn.append("TYPE-II bytes_written=%s bytes_on_disk=%s"
                        % (cell["bytes_written"], cell["bytes_on_disk"]))
    if not isinstance(cell.get("elapsed_ms"), int) or cell["elapsed_ms"] > 5000 + 2000:
        errs.append("elapsed_ms=%s exceeds the per-child 5s budget" % cell.get("elapsed_ms"))
    if cell.get("deps_direct") != 0 or cell.get("deps_total") != 0:
        errs.append("cell declares dependencies (%s/%s), port claims zero NuGet"
                    % (cell.get("deps_direct"), cell.get("deps_total")))
    if cell.get("run_status") == "blocked":
        for f in ("blocked_command", "blocked_exit_code", "blocked_fix_attempted"):
            if not cell.get(f):
                errs.append("blocked without %s" % f)
    ident = identity_of(cell)
    if cell.get("extra") and ident in req_ids:
        errs.append("marked extra but it is a required cell: %s" % ident)
    if not cell.get("extra") and ident not in req_ids:
        errs.append("not in the required list and not marked extra: %s" % ident)
    if cell.get("case_group") == "ctrl" and CTRL_PINS:
        pin = CTRL_PINS.get(cell.get("case_id"))
        if pin is None:
            errs.append("control cell %s has no pin in spec/cases.yaml control_samples" % cell.get("case_id"))
        else:
            if cell.get("name_source") != pin["hex"]:
                errs.append("control %s name_source=%s but the pinned sample_hex is %s - a port may "
                            "not invent the name of a control cell (rev6)"
                            % (cell.get("case_id"), str(cell.get("name_source"))[:20], pin["hex"][:20]))
            if cell.get("control_payload_sha256") != pin["payload_sha256"]:
                errs.append("control %s payload digest=%s != pinned %s"
                            % (cell.get("case_id"), cell.get("control_payload_sha256"),
                               pin["payload_sha256"][:12]))
    if cell.get("create_result") == "ok" and cell.get("bytes_on_disk") is not None:
        if cell.get("bytes_on_disk_authority") != AUTHORITY_EXPECTED:
            errs.append("bytes_on_disk without the stated authority (expected %r, got %r)"
                        % (AUTHORITY_EXPECTED, cell.get("bytes_on_disk_authority")))
    if cell.get("spec_sha256") != frozen_spec_sha():
        errs.append("spec_sha256=%s != FROZEN.md %s" % (cell.get("spec_sha256"), frozen_spec_sha()))
    if cell.get("instrument_red") is True:
        errs.append("cell self-declared instrument_red")
    return errs, warn


CTRL_PINS = {}          # populated in main() from spec/cases.yaml's rev6 control_samples
LEN_FILL = {}           # populated in main() from spec/cases.yaml's rev7 len_fill block
AUTHORITY_EXPECTED = "dir_view (Python enumerator, not the measured language)"


SET_FIELDS_FOR_CANON = ("create_result", "read_result", "error_stage", "os_legality_verdict",
                        "path_form", "longpath_mechanism", "case_group", "attribution_layer")


def arms(schema, sets, req_ids):
    """One green and one red for every gate this self-check leans on. `holds` is the assertion."""
    out = []

    def arm(name, holds, detail=""):
        out.append({"arm": name, "verdict": "PASS" if holds else "FAIL", "detail": str(detail)[:170]})

    good = {
        "format_version": 1, "case_id": "T01", "case_group": "trap", "language": "csharp",
        "os": "windows", "api_entry": "File.WriteAllBytes", "attempt": 1, "name_source": "434f4e",
        "path_form": "plain", "longpath_mechanism": "none", "create_result": "err_at_syscall",
        "error_stage": "syscall", "read_result": "not_applicable",
        "read_skipped_reason": "create failed, nothing landed",
        "os_legality_verdict": "legal",
        "harness_version": "csharp-s02-5-rev7", "started_at": "x", "elapsed_ms": 10,
        "bytes_on_disk": 0, "deps_direct": 0, "deps_total": 0,
        "length_unit": "utf16_code_units", "name_encoding": "hex_raw_bytes", "verdict_via": "win32",
        "extra": False, "spec_sha256": frozen_spec_sha(),
    }
    errs, _ = check_cell(dict(good), sets, schema, {"trap/T01"})
    arm("green: a rev3-shaped cell is accepted", not errs, errs)

    for field, bad in (("create_result", "sort_of_ok"), ("case_group", "trap2"),
                       ("path_form", "bare"), ("os_legality_verdict", "maybe"),
                       ("read_result", "not_attempted"), ("longpath_mechanism", "auto"),
                       ("language", "node")):
        c = dict(good)
        c[field] = bad
        errs, _ = check_cell(c, sets, schema, {"trap/T01"})
        arm("red: %s=%s is refused" % (field, bad), bool(errs), errs)

    # the three rev3 fields, each seen absent and each seen with a value from the OTHER field's set
    for f in ("length_unit", "name_encoding", "verdict_via"):
        c = dict(good)
        del c[f]
        errs, _ = check_cell(c, sets, schema, {"trap/T01"})
        arm("red: rev3 field %s absent is refused" % f, bool(errs), errs)
    c = dict(good)
    c["name_encoding"] = "utf16_code_units"
    errs, _ = check_cell(c, sets, schema, {"trap/T01"})
    arm("red: a length unit written into name_encoding is refused (the rev3 collision)",
        bool(errs), errs)
    c = dict(good)
    c["length_unit"] = "hex_raw_bytes"
    errs, _ = check_cell(c, sets, schema, {"trap/T01"})
    arm("red: a record encoding written into length_unit is refused", bool(errs), errs)
    c = dict(good)
    c["verdict_via"] = "dotnet"
    errs, _ = check_cell(c, sets, schema, {"trap/T01"})
    arm("green: verdict_via=dotnet is a legal word (this port just does not use it)", not errs, errs)
    c = dict(good)
    c["verdict_via"] = "shell32"
    errs, _ = check_cell(c, sets, schema, {"trap/T01"})
    arm("red: verdict_via=shell32 is refused", bool(errs), errs)
    c = dict(good)
    c["verdict_via"] = "none"
    errs, _ = check_cell(c, sets, schema, {"trap/T01"})
    arm("red: a legality verdict with no tool named is refused", bool(errs), errs)

    c = dict(good)
    c["read_result"] = None
    errs, _ = check_cell(c, sets, schema, {"trap/T01"})
    arm("red: read_result=null is refused now that canonical.md s5 has not_applicable", bool(errs), errs)
    c = dict(good)
    c["os_legality_verdict"] = "unknown"
    del c["read_skipped_reason"]
    errs, _ = check_cell(c, sets, schema, {"trap/T01"})
    arm("red: not_applicable without read_skipped_reason is refused", bool(errs), errs)
    c = dict(good)
    c["read_result"] = "not_applicable"
    c["read_skipped_reason"] = "create failed, nothing landed"
    c["os_legality_verdict"] = "unknown"
    c["verdict_via"] = "none"
    errs, _ = check_cell(c, sets, schema, {"trap/T01"})
    arm("green: not_applicable with a reason is accepted", not errs, errs)

    for drop in ("api_entry", "create_result", "name_source"):
        c = dict(good)
        del c[drop]
        errs, _ = check_cell(c, sets, schema, {"trap/T01"})
        arm("red: missing required field %s is refused" % drop, bool(errs), errs)

    c = dict(good)
    c["case_group"] = "len"
    errs, _ = check_cell(c, sets, schema, {"trap/T01"})
    arm("red: a len cell without base_len is refused", bool(errs), errs)
    c = dict(good)
    c.update({"case_group": "len", "base_len": 78, "base_len_measured": 120, "component_len": 255,
              "total_path_len": 334, "grid_point": 255, "len_target_extra_units": 255,
              "max_component_len": 255, "len_triple": [255, 255, 255]})
    errs, _ = check_cell(c, sets, schema, {"trap/T01"})
    arm("red: base_len disagreeing with the measured directory is refused", bool(errs), errs)

    c = dict(good)
    c["deps_total"] = 3
    errs, _ = check_cell(c, sets, schema, {"trap/T01"})
    arm("red: a cell claiming dependencies is refused (zero-NuGet claim)", bool(errs), errs)

    c = dict(good)
    c["extra"] = True
    errs, _ = check_cell(c, sets, schema, {"trap/T01"})
    arm("red: a required cell marked extra is refused (that is how cells go missing)", bool(errs), errs)

    ctrl_fx = {"format_version": 1, "case_id": "T-CTRL-CANON", "case_group": "ctrl",
               "language": "csharp", "os": "windows", "api_entry": "File.WriteAllBytes",
               "attempt": 1, "path_form": "plain", "longpath_mechanism": "none",
               "create_result": "ok", "error_stage": "null", "read_result": "ok",
               "os_legality_verdict": "legal", "verdict_via": "win32", "length_unit": "utf16_code_units",
               "name_encoding": "hex_raw_bytes", "harness_version": "csharp-s02-4-rev6",
               "started_at": "x", "elapsed_ms": 10, "bytes_on_disk": 28, "bytes_written": 28,
               "deps_direct": 0, "deps_total": 0, "extra": False,
               "bytes_on_disk_authority": "dir_view (Python enumerator, not the measured language)",
               "spec_sha256": frozen_spec_sha()}
    if CTRL_PINS:
        pin = CTRL_PINS["T-CTRL-CANON"]
        c = dict(ctrl_fx); c["name_source"] = "63616e6f6e2d6373686172702e747874"   # an invented name
        errs, _ = check_cell(c, sets, schema, {"ctrl/T-CTRL-CANON"})
        arm("red: a control cell naming itself with an invented sample is refused", bool(errs), errs)
        c = dict(ctrl_fx)
        c["name_source"] = pin["hex"]
        c["control_payload_sha256"] = pin["payload_sha256"]
        errs, _ = check_cell(c, sets, schema, {"ctrl/T-CTRL-CANON"})
        arm("green: a control cell on the pinned sample and pinned payload digest is accepted",
            not errs, errs)
        c = dict(ctrl_fx)
        c["name_source"] = pin["hex"]
        c["control_payload_sha256"] = "0" * 64
        errs, _ = check_cell(c, sets, schema, {"ctrl/T-CTRL-CANON"})
        arm("red: a control cell whose payload digest is not the pinned one is refused", bool(errs), errs)
    c = dict(ctrl_fx); c["name_source"] = CTRL_PINS.get("T-CTRL-CANON", {}).get("hex", "61")
    c["control_payload_sha256"] = CTRL_PINS.get("T-CTRL-CANON", {}).get("payload_sha256", CANON_SHA)
    c["bytes_on_disk_authority"] = "the measured language's own stat call"
    errs, _ = check_cell(c, sets, schema, {"ctrl/T-CTRL-CANON"})
    arm("red: bytes_on_disk without the stated authority is refused (a disk truth from another "
        "language's tool must be disclosed, not buried)", bool(errs), errs)

    # rev7: three quantities, three fields - and the pin parser must really read the pin block
    lf = {"format_version": 1, "case_id": "T18", "case_group": "len", "language": "csharp",
          "os": "windows", "api_entry": "File.WriteAllBytes", "attempt": 1,
          "path_form": "plain", "longpath_mechanism": "prefix_rewrite", "create_result": "ok",
          "error_stage": "null", "read_result": "ok", "os_legality_verdict": "legal",
          "verdict_via": "win32", "length_unit": "utf16_code_units",
          "name_encoding": "hex_raw_bytes", "harness_version": "csharp-s02-5-rev7",
          "started_at": "x", "elapsed_ms": 10, "bytes_written": 28, "bytes_on_disk": 28,
          "deps_direct": 0, "deps_total": 0, "extra": False, "spec_sha256": frozen_spec_sha(),
          "bytes_on_disk_authority": "dir_view (Python enumerator, not the measured language)",
          "base_len": 78, "base_len_measured": 78, "component_len": 78, "total_path_len": 157,
          "len_fill_unit_hex": "61", "name_hex_from_child": "61" * 78,
          "len_triple": [78, 78, 78], "len_ceiling": 255, "len_ceiling_conclusive": True,
          "name_source": "61" * 78}
    errs, _ = check_cell(dict(lf), sets, schema, {"len/T18[base_len=78][path_form=plain]"})
    arm("green: a rev7 length cell (name_source = pinned filler x base_len, ceiling elsewhere) "
        "is accepted", not errs, errs)
    for label, patch in (
            ("name_source is the frozen prose label", {"name_source": "T-LEN-COMP (length bisection)"}),
            ("name_source is the two characters 6 and 1", {"name_source": "61"}),
            ("name_source is not the pinned filler run", {"name_source": "62" * 78}),
            ("len_triple holds the ceiling instead of the name width", {"len_triple": [255, 255, 255]}),
            ("len_triple disagrees with the recorded name", {"len_triple": [48, 48, 48]}),
            ("there is no len_ceiling field", {"len_ceiling": None}),
            ("name_source is not the component the child passed", {"name_hex_from_child": "61" * 48})):
        c = dict(lf)
        c.update(patch)
        errs, _ = check_cell(c, sets, schema, {"len/T18[base_len=78][path_form=plain]"})
        arm("red: a length cell where %s is refused" % label, bool(errs), errs)
    import importlib.util as _iu
    _sp = _iu.spec_from_file_location("rc_pin", os.path.join(HERE, "run_csharp.py"))
    _rc = _iu.module_from_spec(_sp)
    _sp.loader.exec_module(_rc)
    _pin = _rc.len_fill_pin()
    arm("green: the pin parser reads every len_fill field, including the two lines that carry no "
        "trailing comment", bool(_pin.get("rule")) and bool(_pin.get("applies_to"))
        and _pin.get("unit_hex") == "61", _pin)
    arm("red: a comment-free pin line would be silently dropped (the bug this round hit)",
        "base_len" in (_pin.get("rule") or ""), _pin.get("rule"))

    # the required-list reproducibility arm: the gate must be able to re-derive the manifest
    r = subprocess.run([sys.executable, GEN_CHECK, "--check"], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    arm("green: spec/cells-required.json re-derives byte-identically from the committed spec face",
        r.returncode == 0, "rc=%d %s" % (r.returncode, r.stdout.strip()[:120]))

    rc = harness()
    sample = None
    for p in sorted(glob.glob(os.path.join(RESULTS_DIR, "*.json")))[:1]:
        sample = json.loads(io.open(p, encoding="utf-8").read())
    arm("green: this checker and the harness render the contract identity the same way",
        sample is not None and identity_of(sample) == rc.produced_identity(sample),
        "%s vs %s" % (identity_of(sample) if sample else None,
                      rc.produced_identity(sample) if sample else None))
    os.makedirs(rc.SCRATCH_ROOT, exist_ok=True)
    arm_spec = {"mode": "point", "shape": "comp", "entry": "File.WriteAllBytes", "form": "plain",
                "payload": "canon", "comp_len": 20, "fill": "a", "legality": True,
                "group": "trap", "case_id": "T-ARM", "name_hex": None, "cell_id": "T-ARM",
                "name_source": "61726d", "mechanism_class": "unknown"}
    scratch = os.path.join(rc.SCRATCH_ROOT, "arm" + os.urandom(4).hex())
    os.makedirs(scratch, exist_ok=True)
    saved = rc.TIMEOUT_S
    try:
        rc.TIMEOUT_S = 0.001
        rep, meta = rc.run_child(arm_spec, scratch)
    finally:
        rc.TIMEOUT_S = saved
    arm("red: the 5 s ceiling does kill a child that overruns (hang is reachable)",
        bool(meta["timed_out"]), "timed_out=%s rc=%s" % (meta["timed_out"], meta["rc"]))

    scratch2 = os.path.join(rc.SCRATCH_ROOT, "arm" + os.urandom(4).hex())
    os.makedirs(scratch2, exist_ok=True)
    rep2, meta2 = rc.run_child(arm_spec, scratch2)
    arm("green: the same child under the real ceiling is not called a hang",
        (not meta2["timed_out"]) and rep2 is not None,
        "timed_out=%s rc=%s report=%s" % (meta2["timed_out"], meta2["rc"], rep2 is not None))

    dirty = os.path.join(rc.SCRATCH_ROOT, "arm" + os.urandom(4).hex())
    os.makedirs(dirty, exist_ok=True)
    io.open(os.path.join(dirty, "planted.txt"), "w").write("planted")
    rep3, meta3 = rc.run_child(arm_spec, dirty)
    rejected = (meta3["rc"] == 3) or ((rep3 or {}).get("precondition") or {}).get("ok") is False
    arm("red: a non-empty scratch dir is rejected instead of measured", rejected,
        "rc=%s precondition=%s attempts=%s" % (meta3["rc"], (rep3 or {}).get("precondition"),
                                               (rep3 or {}).get("attempts")))
    clean = os.path.join(rc.SCRATCH_ROOT, "arm" + os.urandom(4).hex())
    os.makedirs(clean, exist_ok=True)
    rep4, meta4 = rc.run_child(arm_spec, clean)
    arm("green: a fresh scratch dir is measured", meta4["rc"] == 0 and rep4 is not None,
        "rc=%s" % meta4["rc"])

    refused_sha, why = rc.ext_read_sha256(scratch2, "CON.txt")
    arm("red: reading the content of a reserved name is refused",
        refused_sha is None and bool(why), (refused_sha, why))
    sha, why2 = rc.ext_read_sha256(scratch2, "a" * 20)
    arm("green: reading an ordinary landed name back works", sha is not None, (str(sha)[:12], why2))

    text = io.open(CSPROJ, encoding="utf-8").read()
    arm("green: the csproj carries no PackageReference element",
        not re.search(r"<PackageReference\b", text), re.findall(r"<PackageReference[^>]*>", text))
    arm("red: that same check fires when a package element is present",
        bool(re.search(r"<PackageReference\b", '<ItemGroup><PackageReference Include="x" /></ItemGroup>')))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    schema = load_schema()
    sets = load_canonical_sets()
    rc = harness()
    manifest = rc.read_required()
    req_ids = rc.required_identities(manifest)
    CTRL_PINS.update(rc.ctrl_pins(rc.read_spec(), manifest))
    LEN_FILL.update(rc.len_fill_pin())

    files = sorted(glob.glob(os.path.join(RESULTS_DIR, "*.json")))
    produced = {os.path.basename(p): p for p in files}
    cells = {}
    unreadable = []
    for name, path in sorted(produced.items()):
        try:
            cells[name] = json.loads(io.open(path, encoding="utf-8").read())
        except Exception as e:
            unreadable.append((name, "unreadable: %s" % e))

    print("closed words read from spec/canonical.md:")
    for f in SET_FIELDS_FOR_CANON:
        if f in sets:
            print("   %-20s %s" % (f, sorted(sets[f])))
    print("rev3 enums read from spec/schema.json:")
    for f in ("length_unit", "name_encoding", "verdict_via"):
        print("   %-14s %s" % (f, schema["properties"][f]["enum"]))
    auth = sorted({str(c.get("bytes_on_disk_authority")) for c in cells.values()})
    print("bytes_on_disk_authority=%s" % auth)
    print("   stated for the appendix: the disk truth in these cells comes from THIS harness's own "
          "Python os.scandir enumeration through the extended-prefix face, not from the measured C# runtime, "
          "so a port's bytes_on_disk is cross-language evidence; the language's own view is kept "
          "separately as path_view_entries_* and the two are compared per cell "
          "(enum_to_stat_agrees, view_divergence).")
    print("control pins enforced: %s -> %s"
          % (len(CTRL_PINS), {k: v["hex"][:16] for k, v in sorted(CTRL_PINS.items())}))
    print("required manifest: %s cells + %s T-API rows for csharp = %d required identities"
          % (len(manifest["required_cells"]),
             sum(1 for t in manifest["tapi_cells_per_language"] if t["language"] == "csharp"),
             len(req_ids)))
    print("   spec_blob_sha256=%s manifest_sha256=%s"
          % (manifest["spec_blob_sha256"][:16],
             hashlib.sha256(open(rc.REQUIRED_MANIFEST, "rb").read()).hexdigest()[:16]))

    void = list(unreadable)
    warns = []
    valid = 0
    blocked = 0
    ids_seen = {}
    for name, cell in sorted(cells.items()):
        errs, warn = check_cell(cell, sets, schema, req_ids)
        ident = identity_of(cell)
        ids_seen.setdefault(ident, []).append(name)
        if cell.get("run_status") == "blocked":
            blocked += 1
        if errs:
            void.append((name, errs))
        else:
            valid += 1
        for w in warn:
            warns.append((name, w))

    dupes = {k: v for k, v in ids_seen.items() if len(v) > 1}
    produced_ids = set(ids_seen)
    missing = sorted(req_ids - produced_ids)
    extra_ids = sorted(produced_ids - req_ids)
    declared = set()
    for s in rc.make_plan()[0]:
        declared.add(rc.cell_filename(s))
    undeclared_files = sorted(set(produced) - declared)

    ctrl_fail = []
    for name, cell in sorted(cells.items()):
        cid = cell.get("case_id")
        if cid not in CTRL_EXPECT:
            continue
        for k, v in CTRL_EXPECT[cid].items():
            if cell.get(k) != v:
                ctrl_fail.append("%s %s=%r expected %r" % (cid, k, cell.get(k), v))
        if cid == "T-CTRL-CANON":
            for k in ("sha256_self", "sha256_truth"):
                if cell.get(k) != CANON_SHA:
                    ctrl_fail.append("%s %s=%s expected baseline %s"
                                     % (cid, k, cell.get(k), CANON_SHA[:12]))
    controls_run = sum(1 for c in cells.values() if c.get("case_group") == "ctrl")
    if controls_run != len(CTRL_EXPECT):
        ctrl_fail.append("controls on disk=%d, expected %d" % (controls_run, len(CTRL_EXPECT)))

    arm_results = arms(schema, sets, req_ids) if args.selftest else []
    arms_bad = [a for a in arm_results if a["verdict"] == "FAIL"]

    if ctrl_fail or arms_bad:
        print("INSTRUMENT-RED")
        for c in ctrl_fail:
            print("   control: %s" % c)
        for a in arms_bad:
            print("   arm FAIL: %s | %s" % (a["arm"], a["detail"]))

    print()
    print("cells_required=%d cells_produced=%d cells_valid=%d blocked=%d extra=%d"
          % (len(req_ids), len(cells), valid, blocked, len(extra_ids)))
    print("cells_void=%d  missing=%d  duplicate_identities=%d  undeclared_files=%d"
          % (len(void), len(missing), len(dupes), len(undeclared_files)))
    for k in missing[:10]:
        print("   MISSING %s" % k)
    for k in extra_ids[:10]:
        print("   EXTRA  %s (marked in the cell, excluded from the contract set)" % k)
    for k, v in list(dupes.items())[:10]:
        print("   DUPLICATE IDENTITY %s held by %s" % (k, v))
    for n in undeclared_files[:10]:
        print("   FILE NOT A DECLARED CELL %s" % n)
    for name, errs in void[:12]:
        print("   VOID %s" % name)
        for e in (errs if isinstance(errs, list) else [errs])[:4]:
            print("        - %s" % e)

    null_read = sum(1 for c in cells.values() if c.get("read_result") is None)
    na = sum(1 for c in cells.values() if c.get("read_result") == "not_applicable")
    print("read_result_not_applicable=%d read_result_null=%d (rev4 word used; null would be VOID)"
          % (na, null_read))
    co = [c["case_id"] for c in cells.values() if c.get("coexistence")]
    print("t09_coexistence_leg_cells=%s coexist=%s"
          % (co, [c["coexistence"]["coexist"] for c in cells.values() if c.get("coexistence")]))
    kind = {}
    for name, w in warns:
        kind[w.split(":")[0] + ":" + w.split(":")[1][:14]] = kind.get(w.split(":")[0], 0) + 1
    print("observations=%d" % len(warns))
    for k, v in sorted(kind.items()):
        print("   %-34s %d cells" % (k, v))
    lens = sorted([c for c in cells.values() if c.get("case_group") == "len"],
                  key=lambda c: (c["case_id"], c["base_len"], c["path_form"]))
    print("t_len_cells=%d" % len(lens))
    for c in lens:
        ns = str(c.get("name_source") or "")
        print("   %s base=%-4s %-8s name_source=%3d chars all-61=%-5s len_triple=%-15s "
              "len_ceiling=%-5s conclusive=%-5s code=%-13s tiers=%d extra=%s"
              % (c["case_id"], c["base_len"], c["path_form"], len(ns) // 2,
                 (ns == (c.get("len_fill_unit_hex") or "61") * (c["base_len"] or 0)) if ns else None,
                 c.get("len_triple"), c.get("len_ceiling"),
                 c.get("len_ceiling_conclusive"), c.get("len_ceiling_boundary_code"),
                 len(c.get("tier_point_attempts") or []), c.get("extra")))
    req_len = [c for c in lens if not c.get("extra")]
    print("   required_length_cells=%d of 12 name_source_is_the_passed_bytes=%s "
          "len_triple_is_the_name=%s len_ceiling_on_all=%s"
          % (len(req_len),
             all(c.get("name_source") == (c.get("len_fill_unit_hex") or "61") * c["base_len"]
                 for c in req_len),
             all(list(c.get("len_triple") or []) == [c["base_len"]] * 3 for c in req_len),
             all(isinstance(c.get("len_ceiling"), int) for c in req_len)))
    t18 = {c["base_len"]: c["len_ceiling"] for c in lens if c["case_id"] == "T18"}
    print("   T18_component_boundary_by_base=%s all_255=%s" % (t18, all(v == 255 for v in t18.values())))
    if args.selftest:
        print("arms_run=%d arms_pass=%d"
              % (len(arm_results), len([a for a in arm_results if a["verdict"] == "PASS"])))
        for a in arm_results:
            print("   %-66s %s  %s" % (a["arm"][:66], a["verdict"], a["detail"]))
    print("controls=%s" % ("RED" if ctrl_fail else "GREEN(%d)" % controls_run))
    if ctrl_fail or arms_bad:
        return 2
    if missing or dupes or undeclared_files:
        return 3
    if void:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
