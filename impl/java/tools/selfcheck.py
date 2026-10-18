#!/usr/bin/env python3
"""SENDGUARD java port self-check (my own script, stdlib only).

Four jobs the runner cannot do for itself:
  1. derive the expected cell denominator from the frozen artifacts (cases.yaml, the
     FROZEN.md grid, blind-map.json) instead of trusting the runner's plan;
  2. validate every cell against spec/schema.json and the closed word sets parsed out
     of spec/canonical.md - top level AND nested member/entry_spread records, because
     a bad word hidden in a nested record is still a bad word;
  3. assert each record's shape claims about itself (an unattempted read may not be
     written in the same voice as a measurement);
  4. judge the 5 control cells against evidence/ctrl-baseline.md, the only allowed
     source of control expectations. That file's table is a NODE measurement on the S00
     machine; its "expectation:" sentences are the criteria, so every control is reported
     on both layers and only the expectation layer can raise INSTRUMENT-RED.

Usage:
    python impl/java/tools/selfcheck.py
    python impl/java/tools/selfcheck.py --selftest     # red/green arms for this gate
Exit 0 = every cell valid and every control expectation satisfied.
Exit 1 = at least one VOID cell or a denominator mismatch.
Exit 2 = a control expectation mismatches -> INSTRUMENT-RED, the round is not evidence.
Exit 3 = this script could not load its inputs (never reportable as a measurement).
"""
import glob
import hashlib
import io
import json
import os
import re
import ast
import subprocess
import sys
import tempfile


def hx4(s):
    return s.encode("utf-8").hex()

# The console on this host is cp936: printing a combining mark or a localized Windows error
# string would raise and hide the finding. The file faces are ASCII-safe already; this only
# protects the terminal, and never changes what is written to disk.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(PORT))
RESULTS = os.path.join(REPO, "results", "java.windows.x64")
SPEC = os.path.join(REPO, "spec")
BASELINE = os.path.join(REPO, "evidence", "ctrl-baseline.md")
SET_FIELDS = ("create_result", "read_result", "error_stage", "os_legality_verdict",
              "path_form", "longpath_mechanism", "case_group", "attribution_layer")
NESTED_STATUS_FIELDS = ("create_result", "read_result", "error_stage", "os_legality_verdict")
PRIMARY = "Files.write"
CELL_KEYS = re.compile(r"^(trap|ctrl|tapi|blind|len)__([A-Za-z0-9._-]+?)"
                       r"((?:__[A-Za-z0-9._-]+)*)\.json$")


def sub_parts(tail):
    """The sub slots of a cell filename; rev6 rungs carry two of them (base_len, path_form)."""
    return [x for x in tail.split("__") if x] if tail else []
INSTRUMENT_ARTIFACTS = [r"^sgsrc-[0-9a-f-]{36}\.tmp$", r"^preflight-base\.txt$",
                        r"^mp0123456789abcdef[0-9a-f]*\.$"]

# rev3 note: the pre-rev3 schema demanded format_version as the string "1" while every port
# writes the integer 1, which voided 100% of cells. docs/NOTICE-rev3.md records that as the
# contract owner's bug and schema.json now accepts both, so nothing is reported-not-void here
# any more; the selftest keeps an arm for both accepted shapes.

# Criteria quoted from evidence/ctrl-baseline.md. The expectation layer decides PASS/FAIL;
# the table layer is node's observation on the S00 machine and is only reported as a
# comparison - importing it as a mandate would grade one port against another port.
CONTROL_CRITERIA = {
    "T-CTRL-NAMETOOLONG": {
        "expectation": "fail on all 3 OS after reaching FS (err_at_syscall, not parse)",
        "check": lambda c: (c.get("create_result") == "err_at_syscall"
                            and c.get("error_stage") in ("syscall", "fs"),
                            "create_result=%r error_stage=%r"
                            % (c.get("create_result"), c.get("error_stage"))),
        "red": {"create_result": "ok", "error_stage": "null"},
        "table": {"create_result": "err_at_syscall", "error_stage": "syscall"},
    },
    "T-CTRL-ASCII": {
        "expectation": "ok on all languages/OS",
        "check": lambda c: (c.get("create_result") == "ok", "create_result=%r" % c.get("create_result")),
        "red": {"create_result": "err_at_syscall"},
        "table": {"create_result": "ok", "bytes_written": 28, "bytes_on_disk": 28,
                  "read_result": "ok", "roundtrip_ok": True},
    },
    "T-CTRL-ILLEGAL-CHAR": {
        "expectation": "Windows illegal (winerror=123) / POSIX creatable, paired with "
                       "os_legality_verdict",
        "check": lambda c: (c.get("create_result") != "ok"
                            and c.get("os_legality_verdict") == "illegal",
                            "create_result=%r os_legality_verdict=%r"
                            % (c.get("create_result"), c.get("os_legality_verdict"))),
        "red": {"create_result": "ok", "os_legality_verdict": "legal"},
        "table": {"create_result": "err_at_syscall", "error_stage": "syscall"},
    },
    "T-CTRL-PARSE": {
        "expectation": "may reject before syscall, but all 6 langs MUST be err-at-parse",
        "check": lambda c: (c.get("create_result") == "err_at_parse"
                            and c.get("error_stage") == "parse",
                            "create_result=%r error_stage=%r"
                            % (c.get("create_result"), c.get("error_stage"))),
        "red": {"create_result": "err_at_syscall", "error_stage": "fs"},
        "table": {"create_result": "err_at_parse", "error_stage": "parse",
                  "error_code": "ERR_INVALID_ARG_VALUE"},
    },
    "T-CTRL-CANON": {
        "expectation": "identical canonical bytes; else INSTRUMENT-RED",
        "check": lambda c: (c.get("control_pass") is True,
                            "control_pass=%r instruments_agree=%r"
                            % (c.get("control_pass"), c.get("canon_instruments_agree"))),
        "red": {"control_pass": False},
        "table": {"roundtrip_ok": True},
    },
}


def words_in(block):
    """Closed-set words from one canonical.md section.

    In a table the word is the FIRST column; taking every backtick would also capture field names
    the prose mentions (rev4's read_result row says "Requires `read_skipped_reason`", which is a
    field, not a verdict). Prose sections (path_form, longpath_mechanism, error_stage,
    attribution_layer) list words inline, so there the whole block is scanned. ci/equality.py
    scans every backtick in both shapes: it picks up noise AND gets an EMPTY set for
    attribution_layer (L1/L2/L3 are uppercase), which silently skips that field.
    """
    rows = re.findall(r"(?m)^\|\s*`([A-Za-z0-9_]+)`\s*\|", block)
    if rows:
        return set(rows)
    return set(re.findall(r"`([A-Za-z0-9_]+)`", block))


CASES_TEXT = None


def load_canonical():
    text = io.open(os.path.join(SPEC, "canonical.md"), encoding="utf-8").read()
    sets = {}
    for m in re.finditer(r"(?m)^## \d+\. ([a-z_]+)[^\n]*$", text):
        field = m.group(1)
        if field not in SET_FIELDS:
            continue
        nxt = text.find("\n## ", m.end())
        block = text[m.end():nxt if nxt > 0 else len(text)]
        sets[field] = words_in(block)
    mech = text.find("## 10. mechanism_class")
    sets["mechanism_class"] = words_in(text[mech:]) if mech >= 0 else set()
    for f, got in sorted(sets.items()):
        if not got:
            raise RuntimeError("canonical.md yielded an EMPTY closed set for %s "
                               "(a silent skip is how a dead ruler looks green)" % f)
    if len(sets["mechanism_class"]) < 10:
        raise RuntimeError("mechanism_class closed set too small: %s" % sorted(sets["mechanism_class"]))
    return sets


def load_validate_sets():
    """spec/validate.py holds the second ruler. Parsed, never imported: importing would write
    __pycache__ outside this window's allowed paths."""
    src = io.open(os.path.join(SPEC, "validate.py"), encoding="utf-8").read()
    m = re.search(r"(?ms)^CLOSED_SETS = (\{.*?^\})", src)
    if not m:
        raise RuntimeError("could not find CLOSED_SETS in spec/validate.py")
    d = ast.literal_eval(m.group(1))
    return {k: set(v) for k, v in d.items()}


def rulers_agree(sets, schema, vsets):
    """rev4 exists because schema.json and validate.py disagreed; this window refuses to pick
    a side, so it checks the rulers against each other before checking cells against them."""
    props = schema["properties"]
    bad = []
    shared = [f for f in SET_FIELDS if "enum" in props.get(f, {})]
    for f in shared:
        if sets.get(f) and set(props[f]["enum"]) != sets[f]:
            bad.append("canonical.md vs schema.json on %s: %s vs %s"
                       % (f, sorted(sets[f]), sorted(props[f]["enum"])))
    for f, v in sorted(vsets.items()):
        if f in props and isinstance(props[f].get("enum"), list) and set(props[f]["enum"]) != v:
            bad.append("validate.py vs schema.json on %s: %s vs %s"
                       % (f, sorted(v), sorted(props[f]["enum"])))
        if f in sets and sets[f] and sets[f] != v:
            bad.append("canonical.md vs validate.py on %s: %s vs %s"
                       % (f, sorted(sets[f]), sorted(v)))
    for f in ("name_encoding", "length_unit", "verdict_via"):
        if f in props and f not in vsets and f not in sets and f != "verdict_via":
            bad.append("%s has a closed set in schema.json but in neither validate.py nor "
                       "canonical.md" % f)
    return bad


def lock_faces():
    """spec/FROZEN.md publishes sha256 per locked file; compare against the committed blob face."""
    fz = io.open(os.path.join(SPEC, "FROZEN.md"), encoding="utf-8").read()
    rows = re.findall(r"\|\s*(spec/[A-Za-z._-]+|evidence/[A-Za-z._/ -]+\.json)\s*\|\s*([0-9a-f]{64})\s*\|",
                      fz)
    bad = []
    for rel, want in rows:
        r = subprocess.run(["git", "-C", REPO, "cat-file", "blob", "HEAD:" + rel], capture_output=True)
        if r.returncode != 0:
            bad.append("%s: not in HEAD (rc=%s)" % (rel, r.returncode))
            continue
        got = hashlib.sha256(r.stdout).hexdigest()
        if got != want:
            bad.append("%s: FROZEN.md says %s, committed blob face is %s" % (rel, want[:16], got[:16]))
    return {"checked": len(rows), "mismatches": bad}


def pinned_controls():
    """rev6 control_samples: the five control cells are only the same question if the input
    bytes are the same bytes, so the spec now pins them. Read from the committed blob face."""
    r = subprocess.run(["git", "-C", REPO, "cat-file", "blob", "HEAD:spec/cases.yaml"],
                       capture_output=True)
    if r.returncode != 0:
        raise RuntimeError("cannot read cases.yaml from HEAD")
    text = r.stdout.decode("utf-8")
    NL = chr(10)
    blk = re.search("(?m)^control_samples:" + NL + "(.*?)(?:" + NL + "# |" + NL + "cases:)",
                    text, re.DOTALL)
    out = {}
    for b in re.split(r"(?m)^  - id: ", blk.group(1) if blk else "")[1:]:
        cid = b.splitlines()[0].strip()
        sh = re.search(r'sample_hex: "([0-9a-f]+)"', b)
        ph = re.search(r'payload_hex: "([0-9a-f]+)"', b)
        if sh and ph:
            out[cid] = (sh.group(1), ph.group(1))
    if len(out) != 5:
        raise RuntimeError("expected 5 pinned control_samples, found %d" % len(out))
    return out


def load_schema():
    schema = json.loads(io.open(os.path.join(SPEC, "schema.json"), encoding="utf-8").read())
    if len(schema["required"]) != 17:
        raise RuntimeError("schema.json required list changed: %d" % len(schema["required"]))
    return schema


def expected_denominator():
    """The required list is spec/cells-required.json, read from the committed blob face."""
    rel = "spec/cells-required.json"
    r = subprocess.run(["git", "-C", REPO, "cat-file", "blob", "HEAD:" + rel], capture_output=True)
    if r.returncode != 0:
        raise RuntimeError("cannot read %s from HEAD (rc=%s)" % (rel, r.returncode))
    sha_list = hashlib.sha256(r.stdout).hexdigest()
    req = json.loads(r.stdout.decode("utf-8"))
    disk = io.open(os.path.join(REPO, rel), "rb").read()
    face = {"blob": sha_list, "worktree": hashlib.sha256(disk).hexdigest()}
    if face["worktree"] != sha_list:
        # the committed face is the locked artifact (spec/FROZEN.md cites it and ci hashes blob
        # faces, not checkouts), so this port derives from it and reports the dirty checkout.
        print("WARN_DIRTY_CHECKOUT %s working tree %s != committed blob %s; deriving from the "
              "committed face" % (rel, face["worktree"][:16], sha_list[:16]))
    # the list cites the cases.yaml blob it was generated from; re-verify that citation
    c = subprocess.run(["git", "-C", REPO, "cat-file", "blob", "HEAD:spec/cases.yaml"],
                       capture_output=True)
    sha_cases = hashlib.sha256(c.stdout).hexdigest()
    if req.get("spec_blob_sha256") != sha_cases:
        raise RuntimeError("required list cites cases.yaml %s but the committed blob is %s"
                           % (req.get("spec_blob_sha256"), sha_cases))
    text = io.open(os.path.join(SPEC, "cases.yaml"), encoding="utf-8").read()
    java_entries = None
    mam = re.search(r"(?m)^api_entry:\n((?:  \w+:.*\n)+)", text)
    for line in (mam.group(1).splitlines() if mam else []):
        k, v = line.split(":", 1)
        if k.strip() == "java":
            java_entries = [x.strip() for x in v.strip().strip("[]").split(",")]
    exp = {}
    for rc in req["required_cells"]:
        d = rc["sub_identity"]
        parts = (["base_len-%s" % d["base_len"], d["path_form"]] if "base_len" in d
                 else ([] if not d else [["%s-%s" % kv for kv in sorted(d.items())]]))
        fname = "%s__%s%s.json" % (rc["case_group"], rc["case_id"],
                                   ("".join("__" + x for x in parts)))
        exp[fname] = (rc["case_group"], rc["case_id"], tuple(parts))
    for t in req["tapi_cells_per_language"]:
        if t["language"] != "java":
            continue
        exp["tapi__%s__%s.json" % (t["case_id"], t["api_entry"])] = (
            "tapi", t["case_id"], (t["api_entry"],))
    detail = {"required_cells": len(req["required_cells"]),
              "java_tapi_cells": len([t for t in req["tapi_cells_per_language"]
                                      if t["language"] == "java"]),
              "base_len_ladder": "+".join(str(b) for b in req["base_len_ladder"]),
              "required_list_sha256": sha_list,
              "member_split_ids": sorted(k for k in exp if "-m" in k)}
    detail["required_list_faces"] = "blob %s / worktree %s %s" % (
        sha_list[:16], face["worktree"][:16], "(equal)" if face["worktree"] == sha_list else "(DIFFERS)")
    return exp, detail


def spec_sha_blob():
    r = subprocess.run(["git", "-C", REPO, "cat-file", "blob", "HEAD:spec/cases.yaml"],
                       capture_output=True)
    if r.returncode != 0:
        return None, r.returncode
    return hashlib.sha256(r.stdout).hexdigest(), 0


# ------------------------------------------------------------------ checking
def walk_status_words(node, path, sets, errs):
    if isinstance(node, dict):
        for k, v in node.items():
            if k in NESTED_STATUS_FIELDS and isinstance(v, str) and sets.get(k):
                if v not in sets[k]:
                    errs.append("nested %s.%s=%r outside closed set %s" % (path, k, v, sorted(sets[k])))
            walk_status_words(v, "%s.%s" % (path, k), sets, errs)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            walk_status_words(v, "%s[%d]" % (path, i), sets, errs)


def type_check(obj, schema, errs, conflicts):
    props = schema["properties"]
    for f in schema["required"]:
        if f not in obj:
            errs.append("missing required field: %s" % f)
    for f, spec in props.items():
        if f not in obj:
            continue
        v = obj[f]
        t = spec.get("type")
        if t is not None:
            kinds = t if isinstance(t, list) else [t]
            ok = (("string" in kinds and isinstance(v, str))
                  or ("integer" in kinds and isinstance(v, int) and not isinstance(v, bool))
                  or ("boolean" in kinds and isinstance(v, bool))
                  or ("object" in kinds and isinstance(v, dict))
                  or ("array" in kinds and isinstance(v, list))
                  or ("null" in kinds and v is None))
            if not ok:
                errs.append("field %s=%r is not of declared type %s" % (f, v, t))
        if "const" in spec and v != spec["const"]:
            errs.append("field %s=%r != const %r" % (f, v, spec["const"]))
        if "enum" in spec and v not in spec["enum"]:
            errs.append("field %s=%r not in schema enum %s" % (f, v, spec["enum"]))
        if isinstance(v, int) and not isinstance(v, bool) and spec.get("minimum") is not None:
            if v < spec["minimum"]:
                errs.append("field %s=%r below minimum %s" % (f, v, spec["minimum"]))
        if spec.get("pattern") and isinstance(v, str) and not re.match(spec["pattern"], v):
            errs.append("field %s does not match pattern %s" % (f, spec["pattern"]))


def shape_claims(obj, errs):
    cr, rr, ra = obj.get("create_result"), obj.get("read_result"), obj.get("read_attempted")
    if ra is False:
        if rr != "not_applicable":
            errs.append("read_attempted=false but read_result=%r (rev4 gives not_applicable "
                        "exactly for a read that did not happen)" % rr)
        if not obj.get("read_skipped_reason"):
            errs.append("read_result=not_applicable without read_skipped_reason "
                        "(schema.json rev4 requires it whenever the word is used)")
        if obj.get("roundtrip_ok") is not False:
            errs.append("read_attempted=false but roundtrip_ok is not false")
        if obj.get("sha256_truth") is not None:
            errs.append("read_attempted=false but sha256_truth is filled")
    if rr == "not_applicable" and ra is not False:
        errs.append("read_result=not_applicable but read_attempted is %r, not false" % ra)
    if rr == "eof" and ra is False:
        errs.append("read_result=eof with no attempted read: eof claims bytes came back empty")
    if ra is True and rr == "ok":
        if not obj.get("sha256_truth"):
            errs.append("read_result=ok with no sha256_truth")
        if obj.get("bytes_on_disk") is None:
            errs.append("read_result=ok with no bytes_on_disk")
    if cr == "err_at_parse" and obj.get("error_stage") != "parse":
        errs.append("create_result=err_at_parse but error_stage=%r" % obj.get("error_stage"))
    if cr == "err_at_syscall" and obj.get("error_stage") not in ("syscall", "fs"):
        errs.append("create_result=err_at_syscall but error_stage=%r" % obj.get("error_stage"))
    if cr == "err_at_syscall" and not obj.get("error_message"):
        errs.append("create_result=err_at_syscall with no verbatim error_message")
    if cr == "ok" and obj.get("bytes_written") is None:
        errs.append("create_result=ok but bytes_written null")
    if obj.get("os_legality_verdict") == "legal":
        pr = obj.get("os_legality_probe") or {}
        if not pr.get("landed_by_enumeration"):
            errs.append("os_legality_verdict=legal without the extended leg landing a name")
    rs = obj.get("run_status")
    if rs not in (None, "ok", "blocked"):
        errs.append("run_status=%r outside the rev6 values" % rs)
    if bool(obj.get("blocked")) != (rs == "blocked"):
        errs.append("blocked=%r disagrees with run_status=%r (rev6 names the field run_status)"
                    % (obj.get("blocked"), rs))
    if obj.get("blocked"):
        for f in ("blocked_command", "blocked_exit_code", "attempted_fix"):
            if f not in obj:
                errs.append("blocked cell missing %s" % f)
    if obj.get("instrument_red") is True:
        errs.append("cell self-declares instrument_red")
    if obj.get("phantom") is True and obj.get("bytes_on_disk") not in (None, 0):
        errs.append("phantom=true but bytes_on_disk=%r" % obj.get("bytes_on_disk"))
    if obj.get("case_group") == "len":
        if obj.get("base_len") is None:
            errs.append("len cell does not carry base_len (cell-identity 1 requires it as a field)")
        if not isinstance(obj.get("grades"), list) or len(obj["grades"]) < 3:
            errs.append("len cell carries fewer than the 3 frozen grid points")
        if obj.get("breakpoint_rule") is None:
            errs.append("len cell does not say which grade the top level describes")


def claim_accounting(obj, errs):
    """gate.md 8: every entry in an observed directory must be claimed by this cell."""
    known = set()
    for h in str(obj.get("name_source") or "").split(","):
        if re.fullmatch(r"[0-9a-f]+", h or ""):
            try:
                known.add(bytes.fromhex(h).decode("utf-8"))
            except Exception:
                pass
    for m in obj.get("members") or []:
        for key in ("name", "name_landed_as"):
            if m.get(key):
                known.add(m[key])
        for a in m.get("appeared_names") or []:
            if a.get("name_hex"):
                try:
                    known.add(bytes.fromhex(a["name_hex"]).decode("utf-8"))
                except Exception:
                    pass
    for s in obj.get("entry_spread") or []:
        rec = s.get("record") or {}
        if rec.get("name_landed_as"):
            known.add(rec["name_landed_as"])
    # a member cell shares its directory with the other members of the same frozen case (that is
    # the point of T09); those siblings are claimed here by name, not left as unaccounted entries
    for sib in obj.get("sibling_members_in_same_directory") or []:
        if sib.get("name_hex"):
            try:
                known.add(bytes.fromhex(sib["name_hex"]).decode("utf-8"))
            except Exception:
                pass
    for h in obj.get("aggregate_cell_of_members") or []:
        try:
            known.add(bytes.fromhex(h).decode("utf-8"))
        except Exception:
            pass
    if (obj.get("zip_leg") or {}).get("zip_file"):
        known.add(obj["zip_leg"]["zip_file"])
    for n in (obj.get("mechanism_preflight") or {}).get("dir_names_landed") or []:
        known.add(n)
    unclaimed = []
    for m in obj.get("members") or []:
        for l in m.get("landed") or []:
            n = l.get("name")
            if n is None or n in known:
                continue
            if any(re.match(p, n) for p in INSTRUMENT_ARTIFACTS):
                continue
            if obj.get("case_group") == "len" and re.match(r"^0123456789abcdef+$", n):
                continue
            unclaimed.append(n[:48])
    if unclaimed:
        errs.append("unclaimed extra entries in the observed directory: %r "
                    "(gate.md 8 makes this an INSTRUMENT-RED source)" % unclaimed[:4])


def check_cell(path, sets, schema, exp, sha_blob, pins=None):
    fn = os.path.basename(path)
    raw = io.open(path, "rb").read()
    errs, conflicts = [], []
    if raw[:3] == b"\xef\xbb\xbf":
        errs.append("UTF-8 BOM present (ci/lint piece 3 fails this)")
    non_ascii = sum(1 for b in raw if b > 0x7f)
    if non_ascii:
        errs.append("%d non-ASCII bytes: the cell face is not encoding-unambiguous" % non_ascii)
    m = CELL_KEYS.match(fn)
    if not m:
        errs.append("filename does not carry (case_group, case_id[, sub]) identity")
    try:
        obj = json.loads(raw.decode("utf-8"))
    except Exception as e:
        return None, ["json parse failure: %s" % e], conflicts
    if not isinstance(obj, dict):
        return None, ["top level must be one cell object, not an aggregate"], conflicts
    if "cells" in obj:
        errs.append("per-cell file must not hold a cells[] aggregate")
    type_check(obj, schema, errs, conflicts)
    for f in SET_FIELDS:
        if obj.get(f) is not None and sets.get(f) and obj[f] not in sets[f]:
            errs.append("unknown status word %s=%r (closed set %s)" % (f, obj[f], sorted(sets[f])))
    if obj.get("mechanism_class") and obj["mechanism_class"] not in sets["mechanism_class"]:
        errs.append("unknown mechanism_class=%r" % obj["mechanism_class"])
    walk_status_words(obj, "", sets, errs)
    shape_claims(obj, errs)
    claim_accounting(obj, errs)
    want = exp.get(fn)
    if want and m and (m.group(1), m.group(2), tuple(sub_parts(m.group(3)))) != want:
        errs.append("filename identity %s/%s/%s is not the expected cell %s/%s/%s"
                    % (m.group(1), m.group(2), sub_parts(m.group(3)), want[0], want[1],
                       list(want[2])))
    if m and obj.get("case_group") != m.group(1):
        errs.append("cell case_group=%r but filename says %r" % (obj.get("case_group"), m.group(1)))
    if m and obj.get("case_id") != m.group(2):
        errs.append("cell case_id=%r but filename says %r" % (obj.get("case_id"), m.group(2)))
    if obj.get("spec_sha256") != sha_blob:
        errs.append("spec_sha256=%r != committed blob face %r" % (obj.get("spec_sha256"), sha_blob))
    if obj.get("language") != "java":
        errs.append("cell claims language=%r" % obj.get("language"))
    if obj.get("os") != "windows":
        errs.append("cell claims os=%r" % obj.get("os"))
    if pins and obj.get("case_group") == "ctrl":
        pin = pins.get(obj.get("case_id"))
        if pin is None:
            errs.append("control cell %s has no pinned sample in spec/cases.yaml"
                        % obj.get("case_id"))
        else:
            want_hex, want_payload = pin
            if obj.get("name_source") != want_hex:
                errs.append("UNPINNED_INPUT control cell %s carries name_source=%r where "
                            "spec/cases.yaml control_samples pins %r"
                            % (obj.get("case_id"), obj.get("name_source"), want_hex))
            sha_pin = hashlib.sha256(bytes.fromhex(want_payload)).hexdigest()
            seen = [v for v in (obj.get("sha256_self"), obj.get("canon_payload_sha256")) if v]
            if seen and sha_pin not in seen:
                errs.append("control cell %s wrote a payload whose sha256 is %s, not the pinned "
                            "%s" % (obj.get("case_id"), seen[0], sha_pin))
    if obj.get("case_group") == "blind" and not obj.get("extra"):
        want = re.findall(r"B(\d+)$", str(obj.get("case_id")))
        if not want:
            errs.append("blind cell id %r is not the rev6 form B<n>" % obj.get("case_id"))
        elif str(obj.get("blind_id")) != want[0]:
            errs.append("blind cell %s carries blind_id=%r, not %s"
                        % (obj.get("case_id"), obj.get("blind_id"), want[0]))
    is_io_spread = (obj.get("case_group") == "len" and obj.get("extra") is True
                    and (obj.get("sub_identity") or {}).get("builder"))
    if obj.get("api_entry") != PRIMARY and obj.get("case_group") != "tapi":
        if not obj.get("extra"):
            # a REQUIRED cell of this port must answer through its primary entry: cell-identity.md
            # section 2 forbids silently substituting another entry and passing
            errs.append("primary entry of this port must be %r, cell carries %r"
                        % (PRIMARY, obj.get("api_entry")))
        elif is_io_spread and (obj.get("sub_identity") or {}).get("builder") != obj.get("api_entry"):
            errs.append("extra length cell publishes entry %r while its declared `builder` "
                        "dimension says %r: the varying dimension must be a named field and it "
                        "must agree with the field the record answers through "
                        "(spec/cell-identity.md section 1)"
                        % (obj.get("api_entry"), (obj.get("sub_identity") or {}).get("builder")))
    if is_io_spread:
        # F2 part 1 arms: this cell exists to publish a second instrument, so it must say which
        # call answered, must not smuggle a random name into the pinned length family, and must name
        # the required cell it is paired with - otherwise it is a duplicate with extra steps.
        if "String" not in str(obj.get("instrument_face") or ""):
            errs.append("java.io spread cell carries no instrument_face naming the String-form call "
                        "(%r)" % obj.get("instrument_face"))
        if not obj.get("points_column_note"):
            errs.append("SPREAD_NOTE_MISSING: the points[] columns mean something different in a "
                        "one-instrument cell, and the cell must say so")
        pair = obj.get("spread_pair") or {}
        if not pair.get("paired_cell"):
            errs.append("java.io spread cell names no paired required rung cell")
        elif not os.path.isfile(os.path.join(RESULTS, str(pair.get("paired_cell")))):
            errs.append("spread_pair.paired_cell=%r is not a file in this face"
                        % pair.get("paired_cell"))
        elif pair.get("paired_cell_api_entry") != PRIMARY:
            errs.append("the paired cell of a java.io spread cell must be the %r cell, found %r"
                        % (PRIMARY, pair.get("paired_cell_api_entry")))
        if (obj.get("len_ceiling") or {}).get("measured_through_this_cells_entry") \
                != obj.get("api_entry"):
            errs.append("len_ceiling.measured_through_this_cells_entry=%r disagrees with api_entry=%r"
                        % ((obj.get("len_ceiling") or {}).get("measured_through_this_cells_entry"),
                           obj.get("api_entry")))
    # --- contract rev3 fields -------------------------------------------------
    for f in ("length_unit", "name_encoding", "verdict_via"):
        if f not in obj:
            # the notice requires verdict_via; schema.json still lists only 17 required
            # fields, so the stricter reading (the notice) is what this gate enforces.
            errs.append("rev3 field %s absent (docs/NOTICE-rev3.md requires it on every cell "
                        "that carries os_legality_verdict)" % f)
    if "os_legality_verdict" in obj and "verdict_via" not in obj:
        errs.append("cell carries os_legality_verdict without naming the tool asked")
    if obj.get("verdict_via") == "none" and obj.get("os_legality_verdict") != "unknown":
        errs.append("verdict_via=none but os_legality_verdict=%r (no tool was asked, so no "
                    "verdict may be claimed)" % obj.get("os_legality_verdict"))
    # F2 criterion 4: the 17-vs-21 flip is only checkable by a stranger if every cell names the
    # JVM that answered it. A blocked cell never started a JVM, so it is exempt on its face.
    if not obj.get("blocked"):
        if not (obj.get("jvm_self_report") or {}).get("java_version"):
            errs.append("SELF_REPORT_MISSING: no jvm_self_report.java_version, so a reader cannot "
                        "tell which JDK this cell answered")
        if not (obj.get("toolchain") or {}).get("java"):
            errs.append("TOOLCHAIN_MISSING: no toolchain.java path, so a reader cannot tell which "
                        "binary on this host ran the child")
    if obj.get("case_group") == "len" and (not obj.get("extra") or is_io_spread):
        # rev7: the length family finally has bytes. The cell's name is the pinned filler
        # unit repeated base_len times, its triple is THAT name's width, and the ceiling the
        # bisection converged on is a separate quantity in its own field.
        dims = obj.get("sub_identity") or {}
        bl = dims.get("base_len")
        pin = re.search(r'unit_hex: "([0-9a-f]+)"', CASES_TEXT or "")
        if bl and pin:
            want_hex = pin.group(1) * int(bl)
            if obj.get("name_source") != want_hex:
                errs.append("UNPINNED_INPUT len cell %s carries name_source=%r, not the rev7 "
                            "pinned filler (%s units of unit_hex %s)"
                            % (obj.get("case_id"), (obj.get("name_source") or "")[:24] + "...",
                               bl, pin.group(1)))
        tri = obj.get("len_triple") or {}
        if bl and set(tri.values()) != {int(bl)}:
            errs.append("len_triple=%r is not the pinned component's three widths (all %s) - "
                        "rev7: if they differ you are counting something else, say so"
                        % (tri, bl))
        if not obj.get("len_ceiling"):
            errs.append("len cell carries no len_ceiling (rev7 keeps the converged ceiling out of "
                        "len_triple, in its own field)")
    if obj.get("case_group") == "len":
        sub_base = re.findall(r"base_len-(\d+)", fn)
        sid = obj.get("sub_identity") or {}
        if sub_base and sid.get("base_len") != int(sub_base[0]):
            errs.append("filename rung base_len-%s disagrees with sub_identity %r"
                        % (sub_base[0], sid))
        if obj.get("base_len") is not None and sid.get("base_len") != obj.get("base_len"):
            errs.append("base_len=%r disagrees with sub_identity.base_len=%r"
                        % (obj.get("base_len"), sid.get("base_len")))
    # --- required vs extra ----------------------------------------------------
    if m:
        tailp = sub_parts(m.group(3))
        sid = obj.get("sub_identity")
        if sid is None and tailp:
            errs.append("filename carries sub slots %s but the cell declares no sub_identity"
                        % tailp)
        if isinstance(sid, dict):
            for p in tailp:
                if p.startswith("base_len-"):
                    if sid.get("base_len") is None or ("base_len-%s" % sid["base_len"]) != p:
                        errs.append("filename rung %s disagrees with sub_identity %r" % (p, sid))
                elif p in ("plain", "extended"):
                    if sid.get("path_form") != p or obj.get("path_form") != p:
                        errs.append("filename form %s disagrees with sub_identity %r and "
                                    "path_form %r" % (p, sid, obj.get("path_form")))
                elif p.startswith("builder-"):
                    want_b = p[len("builder-"):]
                    if sid.get("builder") != want_b or obj.get("api_entry") != want_b:
                        errs.append("filename slot %s disagrees with sub_identity.builder=%r and "
                                    "api_entry=%r" % (p, sid.get("builder"), obj.get("api_entry")))
                elif p.startswith("T-") or p.startswith("G"):
                    pass
        if is_io_spread and not any(str(p).startswith("builder-") for p in tailp):
            # the required rung cell already owns the shorter filename; a spread cell that left the
            # instrument out of its name would be sitting on top of a compared record
            errs.append("java.io spread cell does not carry its builder dimension in the filename, "
                        "so it would collide with the required rung cell for the same identity")
    is_required = fn in exp
    if is_required and obj.get("extra"):
        errs.append("cell is in spec/cells-required.json but marks itself extra")
    if not is_required and not obj.get("extra"):
        errs.append("cell %s is not in spec/cells-required.json and is not marked extra "
                    "(an unmarked extra cell silently joins the digest)" % fn)
    if obj.get("extra") and not obj.get("extra_reason"):
        errs.append("extra cell without extra_reason: nothing says why it exists")
    return obj, errs, conflicts


def control_report(cells, lines):
    fails = []
    for cid, crit in CONTROL_CRITERIA.items():
        c = cells.get(cid)
        if c is None:
            fails.append("%s: control cell absent (the ruler is unverified)" % cid)
            lines.append("%-22s ABSENT  expectation: %s" % (cid, crit["expectation"]))
            continue
        ok, observed = crit["check"](c)
        diffs = ["cell says %s=%r, S00 table said %r" % (k, c.get(k), v)
                 for k, v in crit["table"].items() if c.get(k) != v]
        lines.append("%-22s %-4s expectation(baseline): %s | observed: %s"
                     % (cid, "PASS" if ok else "FAIL", crit["expectation"], observed))
        lines.append("%-22s      node-table layer (reported, not a mandate): %s"
                     % (cid, "; ".join(diffs) if diffs else "this port agrees with the S00 table"))
        if not ok:
            fails.append("%s: %s (observed %s)" % (cid, crit["expectation"], observed))
    return fails


# ------------------------------------------------------------------ self-test
def selftest(sets, schema, exp, sha_blob, pins):
    """A gate that has only ever refused is not proven to work: green and red arms."""
    src = os.path.join(RESULTS, "trap__T04.json")
    if not os.path.isfile(src):
        print("selftest SKIPPED (no trap__T04.json to use as the green base)")
        return 0
    base = json.loads(io.open(src, encoding="utf-8").read())
    problems = []
    arms = 0
    with tempfile.TemporaryDirectory() as td:
        def write(cell=None, name="trap__T04.json", raw=None, cell_json=None):
            p = os.path.join(td, name)
            data = raw if raw is not None else \
                (json.dumps(cell if cell is not None else cell_json, ensure_ascii=True) + "\n").encode("ascii")
            io.open(p, "wb").write(data)
            return p
        obj, errs, conf = check_cell(write(cell_json=base), sets, schema, exp, sha_blob)
        arms += 1
        if errs:
            problems.append("GREEN arm failed: %s" % errs[:3])
        if conf:
            problems.append("GREEN arm raised contract conflicts under rev3: %r" % conf)

        def mut(**kw):
            c = json.loads(json.dumps(base))
            for k, v in kw.items():
                if v == "__del__":
                    c.pop(k, None)
                else:
                    c[k] = v
            return c

        # rev3 accepts format_version as 1 or "1"; both must pass, a third value must not
        obj, errs, conf = check_cell(write(cell_json=mut(format_version="1")),
                                     sets, schema, exp, sha_blob)
        arms += 1
        if errs:
            problems.append("rev3 GREEN arm (format_version as string) failed: %s" % errs[:3])
        obj, errs, conf = check_cell(write(cell_json=mut(format_version=2)),
                                     sets, schema, exp, sha_blob)
        arms += 1
        if not any("enum" in e for e in errs):
            problems.append("format_version=2 not refused by the rev3 enum")
        reds = [
            ("unknown status word", mut(create_result="answered_cute"), "closed set"),
            ("missing required field", mut(api_entry="__del__"), "missing required field"),
            ("spec hash drift", mut(spec_sha256="0" * 64), "spec_sha256"),
            ("unattempted read claimed ok", mut(read_attempted=False, read_result="ok"),
             "read_attempted=false"),
            ("unattempted read claimed eof", mut(read_result="eof"), "eof with no attempted read"),
            ("not_applicable without a reason", mut(read_skipped_reason="__del__"),
             "read_skipped_reason"),
            ("not_applicable with attempted true", mut(read_attempted=True),
             "read_attempted is True"),
            ("blocked without command/fix", mut(blocked=True), "blocked cell missing"),
            ("unclaimed entry in dir", None, "unclaimed extra"),
            ("wrong path_form word", mut(path_form="extended-ish"), "closed set"),
            ("elapsed_ms negative", mut(elapsed_ms=-5), "below minimum"),
            ("rev3 verdict_via missing", mut(verdict_via="__del__"), "verdict_via"),
            ("rev3 verdict_via outside enum", mut(verdict_via="powershell"), "schema enum"),
            ("rev3 length_unit missing", mut(length_unit="__del__"), "length_unit"),
            ("rev3 name_encoding old value", mut(name_encoding="utf16_code_units"), "schema enum"),
            ("verdict_via none with a verdict", mut(verdict_via="none"), "no tool was asked"),
            ("required cell marking itself extra", mut(extra=True, extra_reason="x"),
             "marks itself extra"),
            ("run_status disagreeing with blocked", mut(run_status="ok", blocked=True),
             "disagrees with run_status"),
            ("extra cell without a reason", mut(extra=True), "extra_reason"),
        ]
        for name, cell, needle in reds:
            if cell is None:
                cell = json.loads(json.dumps(base))
                cell["members"][0]["landed"] = [{"name": "someone-elses-file.txt", "size": 1}]
            obj, errs, conf = check_cell(write(cell_json=cell), sets, schema, exp, sha_blob)
            arms += 1
            if not any(needle in e for e in errs):
                problems.append("RED arm %s not caught: %s" % (name, errs[:3]))
        # rev7 arms: a length cell that kept a label as its name_source, or that put the
        # converged ceiling into len_triple, or that dropped len_ceiling, must be refused
        rung = None
        for cand in glob.glob(os.path.join(RESULTS, "len__T17__base_len-*__plain.json")):
            rung = json.loads(io.open(cand, encoding="utf-8").read())
            break
        if rung is None:
            problems.append("no rev7 rung cell on disk to test the length arms")
        else:
            bl = rung["sub_identity"]["base_len"]
            for name, mut2, needle in (
                    ("label instead of bytes", {"name_source": hx4("T-LEN-PATH")}, "UNPINNED_INPUT"),
                    ("ceiling mixed into the triple", {"len_triple": {"code_points": 255,
                                                                      "utf16_code_units": 255,
                                                                      "utf8_bytes": 255}},
                     "not the pinned component"),
                    ("no ceiling recorded", {"len_ceiling": "__del__"}, "len_ceiling")):
                c2 = json.loads(json.dumps(rung))
                for k, v in mut2.items():
                    if v == "__del__":
                        c2.pop(k, None)
                    else:
                        c2[k] = v
                nm = "len__T17__base_len-%s__plain.json" % bl
                obj, errs, conf = check_cell(write(c2, name=nm), sets, schema, exp, sha_blob, pins)
                arms += 1
                if not any(needle in e for e in errs):
                    problems.append("RED rev7 arm %s not caught: %s" % (name, errs[:2]))
            good_tail = "61" * bl
            obj, errs, conf = check_cell(write(rung, name="len__T17__base_len-%s__plain.json" % bl),
                                        sets, schema, exp, sha_blob, pins)
            arms += 1
            if any("UNPINNED_INPUT" in e or "len_triple" in e or "len_ceiling" in e for e in errs):
                problems.append("rev7 GREEN rung arm refused: %s" % errs[:3])
        # F2 arms: a java.io spread cell is a second instrument on a pinned rung. Every field that
        # makes it readable has to be shown able to refuse, and the cell itself has to pass.
        io_name, io_base = None, None
        for cand in sorted(glob.glob(os.path.join(RESULTS, "len__*__builder-*.json"))):
            io_name, io_base = os.path.basename(cand), json.loads(io.open(cand, encoding="utf-8").read())
            break
        if io_base is None:
            problems.append("no java.io spread cell on disk to test the F2 arms")
        else:
            obj, errs, conf = check_cell(write(io_base, name=io_name), sets, schema, exp,
                                         sha_blob, pins)
            arms += 1
            if errs:
                problems.append("GREEN java.io spread arm refused: %s" % errs[:3])

            def iomut(**kw):
                c = json.loads(json.dumps(io_base))
                for k, v in kw.items():
                    if v == "__del__":
                        c.pop(k, None)
                    elif isinstance(v, tuple):     # (path, key, value) inside a nested dict
                        c[v[0]][v[1]] = v[2]
                    else:
                        c[k] = v
                return c
            ioreds = [
                ("no points-column note", iomut(points_column_note="__del__"),
                 "SPREAD_NOTE_MISSING"),
                ("builder dimension disagreeing with api_entry",
                 iomut(sub_identity=dict(io_base["sub_identity"], builder=PRIMARY)), "disagrees with"),
                ("no paired rung named", iomut(spread_pair="__del__"), "names no paired"),
                ("a random name in the pinned family", iomut(name_source=hx4("t.bin")),
                 "UNPINNED_INPUT"),
                ("ceiling key pointing at another entry",
                 iomut(len_ceiling=("len_ceiling", "measured_through_this_cells_entry", PRIMARY)),
                 "measured_through_this_cells_entry"),
                ("no jvm self report", iomut(jvm_self_report="__del__"), "SELF_REPORT_MISSING"),
                ("no toolchain path", iomut(toolchain="__del__"), "TOOLCHAIN_MISSING"),
            ]
            for name, cell, needle in ioreds:
                obj, errs, conf = check_cell(write(cell, name=io_name), sets, schema, exp,
                                             sha_blob, pins)
                arms += 1
                if not any(needle in e for e in errs):
                    problems.append("RED F2 arm %s not caught: %s" % (name, errs[:2]))
            # a spread cell that dropped its instrument slot from the filename would sit on top of
            # the required rung record
            obj, errs, conf = check_cell(write(io_base, name="len__T17__base_len-78__plain.json"),
                                         sets, schema, exp, sha_blob, pins)
            arms += 1
            if not any("builder dimension" in e or "marks itself extra" in e for e in errs):
                problems.append("RED F2 arm filename-without-builder not caught: %s" % errs[:2])
            # a REQUIRED cell may never answer through a substituted entry
            obj, errs, conf = check_cell(write(mut(api_entry="FileOutputStream.write"),
                                                name="trap__T04.json"), sets, schema, exp, sha_blob)
            arms += 1
            if not any("primary entry of this port" in e for e in errs):
                problems.append("RED F2 arm required-cell-entry-substitution not caught: %s"
                                % errs[:2])
        # rev6 arms on their own bases: a control cell that ignored the pinned sample,
        # and a blind cell whose id does not carry the blind_id the map gives
        ctrl_base = None
        for f in glob.glob(os.path.join(RESULTS, "ctrl__T-CTRL-ASCII.json")):
            ctrl_base = json.loads(io.open(f, encoding="utf-8").read())
        if ctrl_base is None:
            problems.append("no control cell on disk to test the pinned-input arm")
        else:
            bad = dict(list(ctrl_base.items()) + [("name_source", "00")])
            obj, errs, conf = check_cell(write(bad, name="ctrl__T-CTRL-ASCII.json"), sets, schema,
                                         exp, sha_blob, pins)
            arms += 1
            if not any("UNPINNED_INPUT" in e for e in errs):
                problems.append("RED arm unpinned control input not caught: %s" % errs[:3])
            good = dict(list(ctrl_base.items()) +
                        [("name_source", pins["T-CTRL-ASCII"][0])])
            obj, errs, conf = check_cell(write(good, name="ctrl__T-CTRL-ASCII.json"), sets, schema,
                                         exp, sha_blob, pins)
            arms += 1
            if any("UNPINNED_INPUT" in e for e in errs):
                problems.append("pinned control input refused: %s" % errs[:3])
        # an unmarked extra cell: same content, a filename the required list does not know
        unmarked = json.loads(json.dumps(base))
        unmarked["case_id"] = "T99"
        obj, errs, conf = check_cell(write(unmarked, name="trap__T99.json"), sets, schema, exp, sha_blob)
        arms += 1
        if not any("not marked extra" in e for e in errs):
            problems.append("RED arm unmarked-extra not caught: %s" % errs[:3])
        # a marked extra cell in the same unknown slot is exactly what rev3 allows: kept, flagged,
        # reasoned, and excluded from the digest - so it must pass, not be invented-blocked
        marked = json.loads(json.dumps(unmarked))
        marked["extra"] = True
        marked["extra_reason"] = "arm: this identity is not in the required list"
        obj, errs, conf = check_cell(write(marked, name="trap__T99.json"), sets, schema, exp, sha_blob)
        arms += 1
        if errs:
            problems.append("marked-extra arm rejected (rev3 allows extras): %s" % errs[:3])
        obj, errs, conf = check_cell(write(cell_json=mut(format_version=1)), sets, schema, exp, sha_blob)
        arms += 1
        if errs:
            problems.append("rev3 integer format_version should pass, got %s" % errs[:2])
        obj, errs, conf = check_cell(write(base, name="trap__T99.json"), sets, schema, exp, sha_blob)
        arms += 1
        if not any("filename" in e for e in errs):
            problems.append("RED arm unknown-filename not caught: %s" % errs[:3])
        raw = b"\xef\xbb\xbf" + (json.dumps(base, ensure_ascii=True) + "\n").encode("ascii")
        obj, errs, conf = check_cell(write(raw=raw), sets, schema, exp, sha_blob)
        arms += 1
        if not any("BOM" in e for e in errs):
            problems.append("RED arm BOM not caught: %s" % errs[:3])
        raw = (json.dumps(base, ensure_ascii=False) + "\n").encode("utf-8").replace(
            b"trail", b"tr\xc3\xa4il")
        obj, errs, conf = check_cell(write(raw=raw), sets, schema, exp, sha_blob)
        arms += 1
        if not any("non-ASCII" in e for e in errs):
            problems.append("RED arm non-ASCII face not caught: %s" % errs[:3])
    for cid, crit in CONTROL_CRITERIA.items():
        ok, obs = crit["check"](crit["red"])
        arms += 1
        if ok:
            problems.append("control judge for %s accepts its own red fixture (%s)" % (cid, obs))
        real = os.path.join(RESULTS, "ctrl__%s.json" % cid)
        if os.path.isfile(real):
            c = json.loads(io.open(real, encoding="utf-8").read())
            ok2, obs = crit["check"](c)
            if not ok2:
                problems.append("control %s refuses its own measured cell (%s)" % (cid, obs))
    print("selftest arms_checked=%d problems=%d" % (arms, len(problems)))
    for p in problems:
        print("   SELFTEST-FAIL %s" % p)
    return 1 if problems else 0


# ---------------------------------------------------------------------- main
def main():
    argv = sys.argv[1:]
    results_dir = RESULTS
    if "--results-dir" in argv:
        results_dir = os.path.abspath(argv[argv.index("--results-dir") + 1])
    try:
        sets = load_canonical()
        pins = pinned_controls()
        globals()["CASES_TEXT"] = io.open(os.path.join(SPEC, "cases.yaml"), encoding="utf-8").read()
        schema = load_schema()
        vsets = load_validate_sets()
        drift = rulers_agree(sets, schema, vsets)
        if drift:
            print("INSTRUMENT-RED the frozen rulers disagree, so no cell can satisfy both:")
            for d in drift:
                print("   RULER-DRIFT %s" % d)
            print("this window reports it and does not pick a side (see rev4)")
            return 3
        print("rulers agree: canonical.md == schema.json == validate.py on %s"
              % ", ".join(sorted(k for k in vsets if k in sets or "enum" in str(schema["properties"].get(k)))))
        faces = lock_faces()
        print("FROZEN.md lock faces checked against the committed blob: %d, mismatches=%d"
              % (faces["checked"], len(faces["mismatches"])))
        for b in faces["mismatches"]:
            print("   LOCK-FACE %s" % b)
        exp, detail = expected_denominator()
        sha_blob, rc = spec_sha_blob()
        if not io.open(BASELINE, encoding="utf-8").read():
            raise RuntimeError("control baseline is empty")
    except Exception as e:
        print("INSTRUMENT-RED self-check could not load its inputs: %s: %s" % (type(e).__name__, e))
        return 3
    if rc != 0 or not sha_blob:
        print("INSTRUMENT-RED cannot read HEAD:spec/cases.yaml (rc=%s)" % rc)
        return 3
    if "--selftest" in argv:
        return selftest(sets, schema, exp, sha_blob, pins)
    if not os.path.isdir(results_dir):
        print("INSTRUMENT-RED no results dir at %s" % results_dir)
        return 3

    print("closed sets from canonical.md: %s"
          % ", ".join("%s=%d" % (k, len(sets[k])) for k in sorted(sets)))
    print("spec_sha256(committed blob face of spec/cases.yaml)=%s" % sha_blob)
    files = sorted(os.path.basename(p) for p in glob.glob(os.path.join(results_dir, "*.json")))
    others = sorted(os.path.basename(p) for p in glob.glob(os.path.join(results_dir, "*"))
                    if not p.endswith(".json"))
    print("required list (blob face): %s"
          % ", ".join("%s=%s" % (k, v) for k, v in sorted(detail.items()) if k != "member_split_ids"))
    print("member-split required ids: %s" % ", ".join(detail["member_split_ids"]))
    extras_present = sorted(f for f in files if f not in exp)
    print("cells_required=%d cells_produced=%d cells_extra_present=%d"
          % (len(exp), len(files), len(extras_present)))

    valid, void, blocked, reported = 0, 0, 0, 0
    cells = {}
    for fn in files:
        obj, errs, conflicts = check_cell(os.path.join(results_dir, fn), sets, schema, exp,
                                                 sha_blob, pins)
        if obj is not None and obj.get("extra"):
            reported += 1
        if obj is not None and obj.get("blocked"):
            blocked += 1
        if errs:
            void += 1
            print("VOID    %s" % fn)
            for e in errs:
                print("        - %s" % e)
        else:
            valid += 1
            print("VALID   %s" % fn)
        if obj is not None:
            cells[obj.get("case_id")] = obj
    print("cells_valid=%d cells_blocked=%d cells_void=%d cells_extra_marked=%d"
          % (valid, blocked, void, reported))

    lines = []
    fails = control_report(cells, lines)
    print("== control cells (source: evidence/ctrl-baseline.md)")
    for line in lines:
        print("   %s" % line)
    missing = sorted(set(exp) - set(files))
    extra = extras_present
    if missing:
        print("MISSING_REQUIRED_CELLS %s" % ",".join(missing))
    if extra:
        # rev3: extra cells are allowed, must be marked (check_cell enforces that) and are
        # excluded from the equality digest - they are not a failure of this run
        print("EXTRA_CELLS (marked, kept, excluded from the digest) %s" % ",".join(extra))
    if others:
        print("NON_CELL_FILES_IN_RESULTS %s" % ",".join(others))
    if fails:
        print("INSTRUMENT-RED control mismatch: %s" % "; ".join(fails))
        print("gate.md 8: the round is re-run, not patched; these cells are not evidence")
        return 2
    print("controls_pass=true")
    if missing or others or void:
        print("OUTCOME=NOT-CLEAN missing=%d non_cell_files=%d void=%d"
              % (len(missing), len(others), void))
        return 1
    print("ALL-VALID cells_required=%d cells_produced=%d cells_valid=%d blocked=%d extra=%d"
          % (len(exp), len(files), valid, blocked, len(extras_present)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
