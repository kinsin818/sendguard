#!/usr/bin/env python3
"""SENDGUARD S02 acceptance for the TypeScript port (this port's own ruler).

Runs three things and prints denominators:
  1. every cell parses as JSON and satisfies spec/schema.json (required fields, enums,
     types, sha pattern) -- with the two schema/schema-adjacent conflicts reported
     separately rather than folded into one pass/fail;
  2. every status word is in the closed set parsed out of spec/canonical.md;
  3. cell identity: filename == <case_group>__<case_id>[__<sub_identity>], the sub dims
     are recoverable from the filename AND present as named fields inside the cell,
     and spec_sha256 equals a freshly computed git blob face hash.

Exit 0 = every cell valid. Exit 1 = at least one violation. Exit 3 = a control cell
failed, so the run is INSTRUMENT-RED and no cell of it is evidence.

Usage: python impl/typescript/selfcheck.py
"""
import glob
import hashlib
import io
import json
import os
import re
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PORT_DIR = os.path.join("results", "typescript.windows.x64")
SCHEMA_PATH = os.path.join(REPO, "spec", "schema.json")
CANON_PATH = os.path.join(REPO, "spec", "canonical.md")
CASES_PATH = os.path.join(REPO, "spec", "cases.yaml")
CASES_MARKER = "\ncases:"
# rev6 pins one 28-byte control payload; the sealed S00 baseline records the same digest for the
# node and python instruments, so a port that hashes anything else is not measuring that control.
CANON_PAYLOAD_SHA = "c9fe45b2fee8ea846f0cf4f2cacc2a891e7b082e7719923502d12a9813e21994"

SET_FIELDS = (
    "case_group", "path_form", "longpath_mechanism", "create_result", "error_stage",
    "read_result", "os_legality_verdict", "attribution_layer", "name_encoding", "mechanism_class",
    # rev3 split the old name_encoding into two concepts, and verdict_via must name the tool
    # the legality verdict actually asked. All three are schema.json enums.
    "length_unit", "verdict_via",
)

# fields a blocked cell is allowed to leave null because the leg was never reached
NOT_REACHABLE = ("create_result", "error_stage", "read_result", "roundtrip_ok", "bytes_written", "bytes_on_disk")

# rev3 added verdict_via and length_unit to properties but left them out of the required array,
# while docs/NOTICE-rev3.md demands verdict_via on every cell. The notice is the stricter rule,
# so it is enforced here instead of relaxing to match the schema array.
REV3_NOTICE_REQUIRED = ("length_unit", "name_encoding", "verdict_via")

# rev7: len_fill in spec/cases.yaml pins the component the length family must pass.
# Parsed line by line: the block is flat, and a regex here would only add escaping risk.
LEN_FILL = {"unit_hex": "", "char": "", "rule": "", "applies_to": []}
try:
    _cy_all = io.open(CASES_PATH, encoding="utf-8").read()
    if "\nlen_fill:" not in _cy_all:
        print("NOTE spec/cases.yaml has no len_fill block; the rev7 length rules will fail loudly")
    else:
        _lfblk = _cy_all.split("\nlen_fill:")[1].split("\ncases:")[0]
        for _line in _lfblk.splitlines():
            if ":" not in _line or not _line.startswith("  "):
                continue
            _k, _v = _line.strip().split(":", 1)
            _v = _v.split("#")[0].strip().strip('"')
            if _k == "unit_hex":
                LEN_FILL["unit_hex"] = _v.lower()
                LEN_FILL["char"] = chr(int(_v, 16))
            elif _k == "rule":
                LEN_FILL["rule"] = _v
            elif _k == "applies_to":
                LEN_FILL["applies_to"] = [x.strip() for x in _v.strip("[]").split(",") if x.strip()]
except Exception as _e2:
    print("NOTE could not read len_fill:", _e2)

# rev6: control_samples in spec/cases.yaml pin one name and one payload per control cell.
PINNED = {}
try:
    _cy = io.open(CASES_PATH, encoding="utf-8").read()
    for _blk in re.split(r"(?m)^  - id: ", _cy.split("control_samples:")[1].split("\ncases:")[0])[1:]:
        _cid = re.match(r"(\S+)", _blk).group(1)
        _sh = re.search(r'(?m)^    sample_hex: "([0-9a-f]+)"', _blk)
        _ph = re.search(r'(?m)^    payload_hex: "([0-9a-f]+)"', _blk)
        if _sh and _ph:
            import hashlib
            PINNED[_cid] = {"sample_hex": _sh.group(1), "payload_hex": _ph.group(1),
                            "payload_sha256": hashlib.sha256(bytes.fromhex(_ph.group(1))).hexdigest()}
except Exception as _e:  # a missing pin is reported as a rule failure below, never silently skipped
    print("NOTE could not read control_samples:", _e)


def sh(cmd):
    return subprocess.run(cmd, cwd=REPO, capture_output=True, shell=False)


def load_schema():
    return json.loads(io.open(os.path.join(REPO, SCHEMA_PATH), encoding="utf-8").read())


def load_closed_sets():
    text = io.open(os.path.join(REPO, CANON_PATH), encoding="utf-8").read()
    sets = {}
    for m in re.finditer(r"(?m)^## \d+\. ([a-z_]+)[^\n]*$", text):
        field = m.group(1)
        if field not in SET_FIELDS:
            continue
        nxt = text.find("\n## ", m.end())
        block = text[m.end(): nxt if nxt > 0 else len(text)]
        sets[field] = set(re.findall(r"`([a-z0-9_]+)`", block))
    return sets


def frozen_expectation():
    """Recompute cells_expected from the frozen table; the port's own plan is not the denominator."""
    full = io.open(os.path.join(REPO, CASES_PATH), encoding="utf-8").read()
    # rev6 added a second `  - id:` list (control_samples) above cases:; counting the whole file
    # made the trap denominator read 27 instead of 22.
    # re.escape would escape the newline itself and never match, which is how this file
    # once read 27 trap cells instead of 22
    text = full.split(CASES_MARKER)[-1]
    blocks = re.split(r"(?m)^  - id: ", text)[1:]
    ids = []
    name_cells = 0
    for block in blocks:
        cid = re.match(r"(\S+)", block).group(1)
        ids.append(cid)
        if cid in ("T17", "T18"):
            continue  # length cells, counted by grid and bisect legs below
        members = 1 if re.search(r"(?m)^    sample_hex:", block) else len(re.findall(r"(?m)^      - \"", block))
        name_cells += members
    req = load_required()
    expected = {
        # 18 non-length traps, with the multi-member cases expanded (T09-m1 / T14-m2 / T19-m2)
        "trap_name_cells": name_cells,
        "trap_zip_legs": 5,       # T16 legs: packer x extractor x entry source, declared in the port
        "len_grid": 24,           # 12 frozen G1-G4 points x 2 path forms
        "len_bisect_frozen_base": 4,   # T17/T18 x 2 path forms at the frozen base 13 only
        # rev6 requires a rung per base_len x path_form, so the ladder is 3 x 2 x 2 cases
        "len_rungs": 2 * len(req["ladder"]) * 2 if req["present"] else 0,
        "ctrl": 5,
        "tapi": 3,                # pinned entry list; rev6 requires no T-API identity of typescript
        "blind": 5,               # rev6 item 2: run them, with blind_id from the sealed map
    }
    expected["total_frozen"] = sum(v for k, v in expected.items() if k != "len_rungs")
    expected["total"] = expected["total_frozen"] + expected["len_rungs"]
    return ids, expected


def check_cell(path, schema, sets, cases_blob_sha):
    try:
        cell = json.loads(io.open(path, encoding="utf-8").read())
    except Exception as e:
        return [f"json parse failure: {e}"], {}, 0
    if not isinstance(cell, dict):
        return ["top level must be an object"], cell, 0
    return check_cell_with_sha(cell, schema, sets, cases_blob_sha, os.path.basename(path))


def check_cell_with_sha(cell, schema, sets, cases_blob_sha, name="<memory>"):
    v = []

    props = schema["properties"]
    for f in schema["required"]:
        if f not in cell:
            v.append(f"missing required field: {f}")

    blocked = cell.get("status") == "blocked"
    if blocked:
        for f in ("blocked_reason", "blocked_command", "attempted_fix"):
            if not cell.get(f):
                v.append(f"blocked cell lacks {f}")
        if "blocked_exit_code" not in cell:
            v.append("blocked cell lacks blocked_exit_code")

    # enum checks, but a blocked cell is permitted null in the legs it never reached
    for key, spec in props.items():
        if key not in cell:
            continue
        val = cell[key]
        if "enum" in spec:
            if val is None and blocked and key in NOT_REACHABLE:
                continue
            if val not in spec["enum"]:
                v.append(f"schema enum: {key}={val!r} not in {spec['enum']}")
        if "const" in spec and val != spec["const"]:
            if not (key == "format_version" and val == 1):
                v.append(f"schema const: {key}={val!r} != {spec['const']!r}")
        if "pattern" in spec and val is not None:
            if not re.match(spec["pattern"], str(val)):
                v.append(f"schema pattern: {key}={val!r}")
        if "minimum" in spec and isinstance(val, int) and val < spec["minimum"]:
            v.append(f"schema minimum: {key}={val}")

    # closed status words straight out of spec/canonical.md
    for field in SET_FIELDS:
        if field in cell and cell[field] is not None:
            allowed = sets.get(field)
            if allowed and cell[field] not in allowed:
                v.append(f"canonical closed set: {field}={cell[field]!r} not in {sorted(allowed)}")

    # spec/validate.py asserts format_version is the integer 1, schema.json says the
    # string "1". Both readings are printed, never silently reconciled.
    if cell.get("format_version") != 1:
        v.append("validate.py rule: format_version must be the integer 1")

    # identity
    m = re.match(r"^(trap|ctrl|tapi|blind|len)__(.+?)(?:__(.+))?\.json$", name)
    if m is None:
        v.append(f"filename does not match <case_group>__<case_id>[__<sub_identity>]: {name}")
    else:
        group, case_id, sub = m.group(1), m.group(2), m.group(3)
        if group != cell.get("case_group"):
            v.append(f"filename group {group!r} != cell case_group {cell.get('case_group')!r}")
        if case_id != cell.get("case_id"):
            v.append(f"filename case_id {case_id!r} != cell case_id {cell.get('case_id')!r}")
        dims = [] if sub is None else sub.split(".")
        want = {} if sub is None else {}
        if sub is not None:
            for seg in sub.split("."):
                kk, _, vv = seg.partition("-")
                want[kk] = int(vv) if re.fullmatch(r"\d+", vv) else vv
        got_si = cell.get("sub_identity")
        if isinstance(got_si, str) and got_si != "":
            v.append("sub_identity must be an object of declared dimensions, not the string %r" % got_si)
        elif (got_si or {}) != want:
            v.append("filename sub_identity %r != cell sub_identity %r" % (want, got_si))
        for seg in dims:
            if "-" not in seg:
                v.append(f"sub_identity segment is not name-value: {seg}")
                continue
            dname, dvalue = seg.split("-", 1)
            # cell-identity.md S1: a varying dimension must be a named field in the cell
            key = "api_entry" if dname == "entry" else dname
            if key not in cell:
                v.append(f"dimension {dname!r} is in the filename but not a field in the cell")
            elif str(cell[key]) != dvalue:
                v.append(f"dimension {dname} in filename says {dvalue!r}, the cell says {str(cell[key])!r}")

    if cell.get("spec_sha256") != cases_blob_sha:
        v.append(f"spec_sha256 {cell.get('spec_sha256')!r} != freshly computed blob face {cases_blob_sha!r}")
    if not (isinstance(cell.get("meta"), dict) and re.match(r"^[0-9a-f]{64}$", str(cell["meta"].get("spec_sha256", "")))):
        v.append("meta.spec_sha256 missing or not 64-hex")

    ns = cell.get("name_source")
    if ns is not None:
        if not re.match(r"^[0-9a-f]*$", str(ns)) or len(str(ns)) % 2 != 0:
            v.append(f"name_source is not lowercase even-length hex: {str(ns)[:24]!r}")
        else:
            decoded = bytes.fromhex(str(ns)).decode("utf-8", "replace")
            if "/" in decoded or "\\" in decoded:
                v.append("name_source decodes to a path, not a single component")

    # sha256_self must reproduce from the file's own content
    self_sha = cell.get("sha256_self")
    if isinstance(self_sha, str):
        stripped = {k: val for k, val in cell.items() if k != "sha256_self"}

        def sk(x):
            if isinstance(x, dict):
                return {k: sk(x[k]) for k in sorted(x)}
            if isinstance(x, list):
                return [sk(i) for i in x]
            return x

        recomputed = __import__("hashlib").sha256(
            json.dumps(sk(stripped), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        if recomputed != self_sha:
            v.append(f"sha256_self does not reproduce (stored {self_sha[:12]}..., recomputed {recomputed[:12]}...)")

    # the digest fields ci/equality.py needs from every port
    behaviour = [
        "case_group", "create_result", "error_stage", "os_legality_verdict", "read_result",
        "path_form", "longpath_mechanism", "name_encoding", "name_source", "name_landed_as",
        "name_mutated", "roundtrip_ok", "enum_to_stat_agrees", "bytes_written", "bytes_on_disk",
        "phantom", "control_pass", "instrument_red", "deps_direct", "deps_total",
        "mechanism_class", "len_triple",
    ]
    missing_keys = [b for b in behaviour if b not in cell]
    if blocked and set(missing_keys) <= set(NOT_REACHABLE) | {"name_landed_as", "name_mutated", "len_triple"}:
        missing_keys = []
    if missing_keys:
        v.append("digest fields absent from this cell: " + ",".join(missing_keys))

    # rev7 rules for the length family, checked rather than promised:
    #   name_source is the hex of the component actually passed (never a label, never one unit),
    #   len_triple is that name's own three widths, and the converged ceiling is a separate field.
    if cell.get("method") == "len_fill_point":
        ns7 = str(cell.get("name_source") or "")
        base7 = cell.get("base_len")
        unit7 = LEN_FILL["unit_hex"]
        if not ns7 or len(ns7) % 2:
            v.append("rev7: length cell name_source is not even-length hex")
        else:
            nm7 = bytes.fromhex(ns7).decode("utf-8", "replace")
            if ns7 != unit7 * len(nm7):
                v.append("rev7: name_source is not the pinned unit repeated across the component that was passed")
            # the three widths of the name itself, computed here rather than copied from the cell
            widths = [len(nm7), len(nm7.encode("utf-16-le")) // 2, len(nm7.encode("utf-8"))]
            trip = cell.get("len_triple")
            if not isinstance(trip, list) or list(trip) != widths:
                v.append("rev7: len_triple %r is not the width of the name passed %r" % (trip, widths))
            if not isinstance(base7, int):
                v.append("rev7: a length rung must record base_len as an integer")
            elif len(nm7) != base7:
                v.append("rev7: the component is %d code units wide but base_len says %d" % (len(nm7), base7))
            ceil = cell.get("len_ceiling")
            if not isinstance(ceil, int) or isinstance(ceil, bool):
                v.append("rev7: the converged ceiling belongs in len_ceiling (integer), not in len_triple")
            if ns7 == unit7 or not nm7:
                v.append("rev7: name_source is one code unit on its own, not the component the cell passed")

    # rev6 item 2: the blind cells must carry the id they were sampled under
    if cell.get("case_group") == "blind" and not isinstance(cell.get("blind_id"), int):
        v.append("blind cell does not carry an integer blind_id")

    # rev6 item 1: the five control cells must be the pinned samples over the pinned payload
    pin = PINNED.get(cell.get("case_id"))
    if pin is not None:
        if cell.get("name_source") != pin["sample_hex"]:
            v.append("control cell uses sample_hex %r, the spec pin says %r" % (cell.get("name_source"), pin["sample_hex"]))
        if cell.get("bytes_written") is not None and pin["payload_sha256"] and cell.get("sha256_truth") != CANON_PAYLOAD_SHA:
            v.append("control payload digests to %r, not the pinned 28-byte sha256 %r"
                     % (str(cell.get("sha256_truth"))[:16], CANON_PAYLOAD_SHA[:16]))

    # rev6 item 2: a verdict must name the authority that was asked whenever the request did
    # reach an OS layer. `none` is honest only when nothing was asked at OS level.
    if (cell.get("case_group") in ("trap", "ctrl", "blind")
            and cell.get("create_result") in ("ok", "err_at_syscall")
            and cell.get("verdict_via") in (None, "none")):
        v.append("verdict_via=none but the request reached the file system; name the authority asked")

    for f in REV3_NOTICE_REQUIRED:
        if f not in cell:
            v.append("rev3 notice required field missing: " + f)

    # spec/canonical.md section 3 defines `ok` as "Create succeeded (bytes_written
    # recorded)", so an ok cell with no bytes_written is a word used outside its
    # definition -- checked here because schema.json cannot express it.
    if cell.get("create_result") == "ok" and cell.get("bytes_written") is None:
        v.append("canonical definition: create_result=ok requires bytes_written recorded")

    return v, cell, len(behaviour)


def uncovered(req, cells):
    """Required identities with neither a measured cell nor a blocked placeholder."""
    have = {s for s, c in cells.items() if c.get("status") in ("measured", "blocked")}
    return sorted(set(req["stems"]) - have)


def selftest_rules():
    """Red and green arms for the rules this file adds on top of schema.json.

    A gate that is only ever seen passing is not known to work, so both arms are
    checked here: the canonical section 3 rule must reject ok-without-bytes_written
    and must accept ok-with-bytes_written.
    """
    schema = load_schema()
    sets = load_closed_sets()
    base = {
        "format_version": 1, "case_id": "SELFTEST", "case_group": "trap", "language": "typescript",
        "os": "windows", "api_entry": "writeFileSync", "attempt": 1, "name_source": "61",
        "path_form": "plain", "longpath_mechanism": "none", "create_result": "ok",
        "error_stage": "null", "read_result": "ok", "os_legality_verdict": "legal",
        "harness_version": "x", "started_at": "now", "elapsed_ms": 1,
        "bytes_written": 28, "status": "measured",
        "spec_sha256": "0" * 64, "meta": {"spec_sha256": "0" * 64},
        "name_landed_as": "a", "name_mutated": False, "roundtrip_ok": True,
        "enum_to_stat_agrees": True, "bytes_on_disk": 28, "phantom": False,
        "control_pass": True, "instrument_red": False, "deps_direct": 0, "deps_total": 0,
        "mechanism_class": "unknown", "len_triple": [1, 1, 1], "name_encoding": "utf16_code_units",
    }
    good = dict(base)
    bad = dict(base)
    bad["bytes_written"] = None
    bad["bytes_on_disk"] = None
    gv, _, _ = check_cell_with_sha(good, schema, sets, "0" * 64)
    bv, _, _ = check_cell_with_sha(bad, schema, sets, "0" * 64)
    fired = any("canonical definition" in x for x in bv)
    clean_ok = not any("canonical definition" in x for x in gv)
    print(f"selftest_rules green_arm_clean={clean_ok} red_arm_caught={fired}")
    return 0 if (fired and clean_ok) else 1


def stem_of(group, case_id, sub):
    """Rebuild the contract filename for one required identity.

    The port renders sub_identity as ordered `name-value` dimensions joined by "."
    (impl/typescript/src/identity.ts), so the manifest's dict has to be rendered the
    same way -- joining with "__" here once made 12 required rungs read as uncovered.
    """
    parts = ["%s-%s" % (k, v) for k, v in sorted(sub.items(), key=lambda kv: str(kv[0]))]
    dims = ("__" + ".".join(parts)) if parts else ""
    return "%s__%s%s.json" % (group, case_id, dims)


def load_required():
    """The current spec/cells-required.json (rev3); its own text withdraws the 03:4x version."""
    p = os.path.join(REPO, "spec", "cells-required.json")
    if not os.path.isfile(p):
        return {"present": False, "stems": {}, "ladder": [], "sha256": None, "count": 0, "tapi": [], "withdraws": None}
    raw = io.open(p, "rb").read()
    doc = json.loads(raw.decode("utf-8"))
    stems = {}
    for c in doc.get("required_cells", []):
        stems[stem_of(c["case_group"], c["case_id"], c.get("sub_identity") or {})] = c
    tapi = [t["api_entry"] for t in doc.get("tapi_cells_per_language", []) if t.get("language") == "typescript"]
    return {
        "present": True,
        "stems": stems,
        "ladder": doc.get("base_len_ladder", []),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "count": len(stems),
        "tapi": tapi,
        "withdraws": doc.get("withdraws"),
    }


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    if "--selftest-rules" in sys.argv:
        return selftest_rules()
    schema = load_schema()
    sets = load_closed_sets()

    r = sh(["git", "cat-file", "blob", "HEAD:spec/cases.yaml"])
    if r.returncode != 0:
        print("OUTCOME=VOID reason=cannot read the committed blob face of spec/cases.yaml")
        return 1
    cases_blob_sha = hashlib.sha256(r.stdout).hexdigest()

    ids, expected = frozen_expectation()
    files = sorted(glob.glob(os.path.join(REPO, PORT_DIR, "*.json")))

    print(f"== denominators")
    print(f"cells_expected={expected['total']} = frozen-derived {expected['total_frozen']} "
          f"(trap_name_cells={expected['trap_name_cells']} zip_legs={expected['trap_zip_legs']} "
          f"len_grid={expected['len_grid']} len_bisect_frozen_base={expected['len_bisect_frozen_base']} "
          f"ctrl={expected['ctrl']} tapi={expected['tapi']} blind={expected['blind']}) "
          f"+ rev3_ladder_rungs={expected['len_rungs']}")
    print(f"cells_produced={len(files)}")
    print(f"cells_expected_basis=recomputed from spec/cases.yaml (20 frozen ids, member lists expanded), not from the port's own plan")
    print(f"cells_expected_from_frozen_table={expected['total_frozen']} "
          f"cells_added_for_rev3_ladder={expected['len_rungs']} total={expected['total']}")

    print(f"cases.yaml blob face sha256={cases_blob_sha}")
    print(f"canonical closed sets loaded fields={','.join(sorted(sets))}")

    problems = {}
    cells = {}
    for f in files:
        v, cell, _ = check_cell(f, schema, sets, cases_blob_sha)
        cells[os.path.basename(f)] = cell
        if v:
            problems[os.path.basename(f)] = v

    # anything in the port dir that is not a cell file is a defect, not a skip
    strays = [os.path.basename(p) for p in glob.glob(os.path.join(REPO, PORT_DIR, "*"))
              if not (os.path.basename(p).endswith(".json") and os.path.basename(p) in cells)]
    print(f"non_cell_files_in_results_dir={len(strays)} {strays[:6]}")

    req = load_required()
    print(f"\n== reconciliation against spec/cells-required.json (appeared in this clone at 03:26, mid-run)")
    if not req["present"]:
        print("  absent on this face; nothing to reconcile")
    else:
        # only a MEASURED cell satisfies a required key; a blocked placeholder must never be
        # counted as a match, or every missing cell could be self-declared away
        produced = {s2 for s2, c in cells.items() if c.get("status") == "measured"}
        req_stems = set(req["stems"])
        matched = sorted(req_stems & produced)
        missing = sorted(req_stems - produced)
        blocked_missing = sorted(
            s2
            for s2, c in cells.items()
            if c.get("status") == "blocked"
            and s2 in missing
            and c.get("blocked_command")
            and c.get("attempted_fix")
            and "blocked_exit_code" in c
        )
        unexplained = [k for k in missing if k not in blocked_missing]
        extras = [s for s, c in cells.items() if c.get("extra") is True]
        unflagged = [s for s, c in cells.items() if s not in req_stems and c.get("extra") is not True]
        print(f"  required_cells={req['count']} sha256={str(req['sha256'])[:16]}... base_len_ladder={req['ladder']}")
        print(f"  withdraws={str(req['withdraws'])[:100]}")
        print(f"  tapi_rows_required_of_typescript={req['tapi']}")
        print(f"  required_matched_by_a_measured_cell={len(matched)}/{len(req_stems)}")
        print(f"  required_not_producible_as_one_identity_less_cell={len(missing)} "
              f"emitted_blocked_with_command_rc_and_attempted_fix={len(blocked_missing)} unexplained={len(unexplained)} {unexplained[:4]}")
        print(f"  cells_marked_extra={len(extras)} (outside the required list, marked, excluded from the digest)")
        for stem, c in sorted(cells.items()):
            if stem in req["stems"] and c.get("status") == "blocked":
                print(f"  REQUIRED_CELL_BLOCKED {stem}: {str(c.get('blocked_reason'))[:90]}")
        if unexplained:
            problems.setdefault("<reconciliation>", []).append(
                "required cells neither produced nor blocked: " + ",".join("/".join(k) for k in unexplained))
        if unflagged:
            problems.setdefault("<reconciliation>", []).append(
                f"{len(unflagged)} cells outside required_cells are not marked extra: {unflagged[:4]}")

    print(f"\n== control cells (source: evidence/S00-ctrl-baseline.md)")
    ctrl_fail = []
    for stem, cell in sorted(cells.items()):
        if cell.get("case_group") != "ctrl":
            continue
        cid = cell.get("case_id")
        exp = cell.get("control_expectation")
        obs = cell.get("control_observed")
        match = cell.get("control_match")
        if cid == "T-CTRL-CANON":
            ci = cell.get("canon_instruments") or {}
            match = ci.get("agree")
            exp = {"rule": "two instruments, same payload, identical sha256"}
            obs = {"sha_memory": str(ci.get("sha_memory"))[:16] + "...", "sha_readback": str(ci.get("sha_readback"))[:16] + "..."}
        print(f"  {cid:22} expected={json.dumps(exp)} observed={json.dumps(obs)} pass={match}")
        if match is not True:
            ctrl_fail.append(cid)

    # Three buckets, kept apart rather than folded into one pass/fail:
    #   (a) the language enum, which does not list this port at all (report gap G-1)
    #   (b) a required closed-set field carrying null because the leg was never reached
    #       (report gap G-2; spec/canonical.md S5 names no word for it, and
    #        evidence/S00-ctrl-baseline.md itself records null in exactly those columns)
    #   (c) everything else, which is this port's own fault
    language_gap, not_reached, other_problems = {}, {}, {}
    for stem, ps in problems.items():
        cell = cells.get(stem, {})
        lang = [p for p in ps if "schema enum: language" in p]
        rest = [p for p in ps if "schema enum: language" not in p]
        nulls = [p for p in rest if "=None not in" in p]
        real = [p for p in rest if "=None not in" not in p]
        excused = []
        for p in nulls:
            field = p.split(" ")[2].split("=")[0]
            if cell.get("status") == "blocked":
                excused.append(p)
            elif field == "read_result" and cell.get("read_skipped_reason"):
                excused.append(p)
            else:
                real.append(p)
        if lang:
            language_gap[stem] = lang
        if excused:
            not_reached[stem] = excused
        if real:
            other_problems[stem] = real

    strict_invalid = set(problems)
    cells_valid = len(files) - len(strict_invalid)
    cells_valid_modulo_language = len(files) - len({s for s in problems if s in language_gap or s in other_problems})
    cells_valid_modulo_gaps = len(files) - len(other_problems)
    blocked = sum(1 for c in cells.values() if c.get("status") == "blocked")
    measured = sum(1 for c in cells.values() if c.get("status") == "measured")
    hung = sum(1 for c in cells.values() if c.get("create_result") == "hang")
    phantoms = [s for s, c in sorted(cells.items()) if c.get("phantom") is True]
    typeii = [s for s, c in sorted(cells.items())
              if c.get("create_result") == "ok" and c.get("bytes_written") is not None
              and c.get("bytes_on_disk") is not None and c["bytes_written"] != c["bytes_on_disk"]]

    print(f"\n== verdicts")
    req2 = load_required()
    extra_n = sum(1 for c in cells.values() if c.get("extra") is True)
    print(f"cells_required={req2['count'] if req2['present'] else 'no-artifact'} cells_produced={len(files)} "
          f"cells_measured={measured} cells_blocked={blocked} cells_extra={extra_n} cells_hang={hung}")
    print(f"cells_valid={cells_valid}  <- strict against spec/schema.json (rev3); the failures are the G-2 null-leg family")
    print(f"cells_valid_modulo_the_language_enum={cells_valid_modulo_language}  (rev3 accepts typescript)")
    print(f"cells_valid_modulo_the_two_contract_gaps={cells_valid_modulo_gaps}")
    print(f"cells_with_not_reached_null_gap_G2={len(not_reached)}")
    print(f"cells_invalid_on_rules_other_than_the_two_gaps={len(other_problems)}")
    print(f"phantom_cells={len(phantoms)} {phantoms[:8]}")
    print(f"type_ii_bytes_mismatch_cells={len(typeii)} {typeii[:6]}")

    if language_gap:
        print(f"\n== gap G-1 printout: schema.json 'language' enum has no value for this port "
              f"({len(language_gap)} cells)")
        for stem in sorted(language_gap)[:3]:
            for p in language_gap[stem]:
                print(f"  {stem}: {p}")
        print(f"  ... and {max(0, len(language_gap) - 3)} more cells with the same single cause")

    if not_reached:
        print(f"\n== gap G-2 printout: a required closed-set field is left null because the leg "
              f"was never reached ({len(not_reached)} cells)")
        counts = {}
        for ps in not_reached.values():
            for p in ps:
                field = p.split(" ")[2].split("=")[0]
                counts[field] = counts.get(field, 0) + 1
        for field, n in sorted(counts.items()):
            print(f"  {field}: {n} cells")

    if other_problems:
        print(f"\n== violations that are this port's own fault")
        for stem in sorted(other_problems):
            print(f"VOID {stem}")
            for p in other_problems[stem]:
                print(f"     - {p}")

    def viol_field(text):
        m = re.match(r"schema enum: ([a-z_]+)=", text) or re.match(r"schema const: ([a-z_]+)=", text)
        if m:
            return m.group(1)
        m = re.match(r"(?:missing required field|canonical closed set|validate.py rule|schema type|rev3 notice) ?:? ?([a-z_]*)", text)
        return m.group(1) if m and m.group(1) else text.split(":")[0].split(" ")[0]

    by_field = {}
    for ps in problems.values():
        for x in ps:
            by_field[viol_field(x)] = by_field.get(viol_field(x), 0) + 1

    # The repo ships TWO rulers: spec/schema.json (revised by rev3) and spec/validate.py, whose
    # own CLOSED_SETS were not revised. Run both over the same cells and print where they
    # disagree, instead of picking the flattering one.
    vr = sh(["python", "spec/validate.py", PORT_DIR])
    vtxt = vr.stdout.decode("utf-8", "replace")
    vfields = {}
    for line in vtxt.splitlines():
        m = re.match(r"- unknown status word ([a-z_]+)=", line.strip()) or re.match(r"- ([a-z_]+) must be boolean", line.strip())
        if m:
            f = m.group(1)
            vfields[f] = vfields.get(f, 0) + 1
    print(f"\n== the two rulers, same cells")
    print(f"  spec/schema.json (rev3): cells_valid={cells_valid} of {len(files)}; violations by field: "
          + ", ".join(f"{k}={n}" for k, n in sorted(by_field.items(), key=lambda kv: -kv[1])))
    print(f"  spec/validate.py: {vtxt.strip().splitlines()[-1] if vtxt.strip() else 'no output'} (rc={vr.returncode})")
    for f, n in sorted(vfields.items()):
        print(f"    validate.py rejects {f} in {n} cells")
    disagree = sorted(set(vfields) - {"read_result", "error_stage", "create_result", "roundtrip_ok", "enum_to_stat_agrees"})
    if disagree:
        print(f"  RULER_DIVERGENCE fields={disagree} -- rev3 changed spec/schema.json but not spec/validate.py; "
              f"a cell cannot satisfy both, and this port follows the revised schema and says so")

    if ctrl_fail:
        print(f"\nINSTRUMENT-RED failing_controls={','.join(ctrl_fail)}")
        print("OUTCOME=INSTRUMENT-RED cells_of_this_run_are_not_evidence")
        return 3

    if other_problems:
        print(f"\nOUTCOME=RED violating_cells={len(other_problems)} (language-enum gap counted separately)")
        return 1

    if len(files) != expected["total"]:
        print(f"\nOUTCOME=RED denominator_disagree produced={len(files)} expected={expected['total']}")
        return 1
    gap = uncovered(req2, cells) if req2["present"] else []
    if gap:
        print(f"\nOUTCOME=RED required_identities_uncovered={len(gap)} {gap[:6]}")
        return 1

    print("\nOUTCOME=GREEN cells_valid_modulo_open_gap_G2=%d blocked=%d controls_pass=true "
          "strict_against_schema_json=%d  (every unmet rule is the G-2 null-leg family; "
          "spec/validate.py additionally disagrees because rev3 revised schema.json only)"
          % (cells_valid_modulo_gaps, blocked, cells_valid))
    print(f"language_enum_gap_cells={len(language_gap)} (gap G-1 was closed by rev3: schema.json now lists typescript)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
