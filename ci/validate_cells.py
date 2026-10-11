"""Validate every cell on every canonical face against the frozen `spec/schema.json`, with an outside ruler.

Run:  python ci/validate_cells.py            # prints and writes docs/cell-validation.md
      python ci/validate_cells.py --quiet     # only the summary lines
      python ci/validate_cells.py --selftest  # 24 arms: it must refuse, and it must be able to say yes

This leg takes no output path on purpose: it always writes the repository's own face, and any other
argument is refused (rc=3) rather than ignored. Measured on 2026-10-11 11:46: the seat passed
`--out-dir <scratch>` believing it was reading the ruler without writing, and it wrote anyway while
reporting rc=0 - which is the silent-acceptance shape this project keeps having to relearn.

Why this leg exists: until now the only numbers about *cell validity* came from each port's own
self-check script - a port grading its own homework, which is how the '31 instrument-red cells' run nearly
passed once. `spec/validate.py` checks the specification, not the results. This file checks the results
against `spec/schema.json` (required fields, enums, types) and prints the count next to the count each
window reported for itself.

Exit codes: 0 = every cell on every face validates (or all arms pass); 1 = at least one cell does not, or a
self-test arm failed; 3 = a face is missing, unreadable, or the leg was called with an argument it does not
implement (an instrument problem, never a measurement).
"""
import collections
import glob
import io
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SCHEMA = os.path.join(REPO, "spec", "schema.json")
PORTS = ["csharp", "go", "java", "python", "rust", "typescript"]
KNOWN_ARGS = ("--quiet", "--selftest")
SAMPLE_LIMIT = 6

sys.path.insert(0, HERE)
import equality  # noqa: E402  - the gate's own VERDICT_FIELDS, so this ruler has no second copy


def cells_in(face):
    for f in sorted(glob.glob(os.path.join(face, "**", "*.json"), recursive=True)):
        try:
            doc = json.loads(io.open(f, encoding="utf-8").read())
        except (OSError, ValueError) as e:
            yield f, None, "unreadable: %s" % str(e)[:60]
            continue
        rows = doc.get("cells") if isinstance(doc, dict) and isinstance(doc.get("cells"), list) else [doc]
        for c in rows:
            yield f, c, None


def check(cell, schema):
    """returns a list of problems for one cell"""
    if not isinstance(cell, dict):
        return ["not an object"]
    props = schema["properties"]
    out = []
    for f in schema["required"]:
        v = cell.get(f)
        if v is None or v == "":
            out.append("missing required %s" % f)
    for f, v in cell.items():
        spec = props.get(f)
        if not spec:
            continue
        enum = spec.get("enum")
        if enum is not None and v not in enum:
            out.append("%s=%r not in the frozen enum" % (f, v))
        t = spec.get("type")
        if t == "boolean" and not isinstance(v, bool):
            out.append("%s should be boolean, got %s" % (f, type(v).__name__))
        elif t == "integer" and isinstance(v, float):
            out.append("%s should be integer, got float %r" % (f, v))
    return out


def parse_args(argv):
    """This leg implements one flag. Anything else is reported as unknown, never ignored.

    Measured 2026-10-11 11:46: the seat called this leg with `--out-dir <scratch>` intending to read the
    ruler without writing, and got rc=0 plus a rewritten `docs/cell-validation.md`. A leg that swallows an
    argument it has never implemented describes its own interface as bigger than it is.
    """
    return [a for a in argv if a not in KNOWN_ARGS], ("--quiet" in argv)


def port_lines(port, n, ok, rep, problems, quiet):
    """One port's lines: the count row, a self-report disagreement, and attributed sample problems."""
    out = ["| %s | %d | %d | %d | %s |" % (port, n, ok, len(problems), rep)]
    if rep != "-" and ok != int(rep):
        out.append("  - SELF-REPORT-DISAGREES: `%s` publishes cells_valid=%s, the outside ruler reads "
                   "%d valid of %d cells (%+d)" % (port, rep, ok, n, ok - int(rep)))
    if not quiet:
        shown = problems[:SAMPLE_LIMIT]
        if shown:
            out.append("  - shown=%d total=%d%s" % (len(shown), len(problems),
                       " TRUNCATED" if len(problems) > len(shown) else ""))
        for fn, p in shown:
            out.append("  - `%s` [port=%s]: %s" % (fn, port, "; ".join(p[:3])))
    return out


def dispatch(argv):
    """('refuse', unknown) | ('selftest',) | ('run', quiet). No token is accepted and then ignored."""
    unknown, quiet = parse_args(argv)
    if unknown:
        return "refuse", unknown
    return ("selftest",) if "--selftest" in argv else ("run", quiet)


CONTROL_FIELD = "control_pass"
CONTROL_EVIDENCE_FIELD = "control_pass_evidence"


def stamp_census(cells):
    """Control cells that carry a self-check result, and how many of them say where it came from.

    A calibration stamp is a claim about the instrument, so the census separates three states and reports them
    apart: stamped with an evidence pointer, stamped without one, and never stamped. `True` with no provenance
    is the case a reviewer cannot re-check, which is why it is not folded into the first bucket.
    """
    out = {"stamped_with_evidence": 0, "stamped_no_evidence": 0, "unstamped": 0}
    for c in cells:
        if not isinstance(c, dict) or c.get("case_group") != "ctrl":
            continue
        if c.get(CONTROL_FIELD) is None:
            out["unstamped"] += 1
        elif c.get(CONTROL_EVIDENCE_FIELD):
            out["stamped_with_evidence"] += 1
        else:
            out["stamped_no_evidence"] += 1
    return out


APPLICABILITY_FIELD = "spec_applicable_on_windows"


def applicability_counts(cells):
    """How many cells *declare* whether this Windows-shaped question applies on this OS, per port.

    The field exists in the frozen schema and is read by no leg; measuring who writes it is the precondition
    for the round-9 applicability decision (`docs/NOTICE-rev9-proposal.md`). A `None`/absent value is
    **absence of a claim**, which is a different thing from `False` - the same distinction this project keeps
    making about blanks.
    """
    out = {"true": 0, "false": 0, "absent": 0}
    for c in cells:
        if not isinstance(c, dict) or APPLICABILITY_FIELD not in c:
            out["absent"] += 1
            continue
        v = c.get(APPLICABILITY_FIELD)
        if v is None:
            out["absent"] += 1
        elif v is True:
            out["true"] += 1
        elif v is False:
            out["false"] += 1
        else:
            out["absent"] += 1
    return out


def verdict_field_gap(schema):
    """Which verdict fields the gate compares that the frozen schema does not require, or never documents.

    The two lists are the project's two rulers over one object, and they were allowed to drift: reading at
    12:06, 9 of the 10 fields `ci/equality.py` calls a verdict are absent from `spec/schema.json`'s
    `required`, and 4 of those are absent from its `properties` too. That is how a tree can be 0-invalid and
    121-blank in the same minute, both numbers correct. Naming the gap is this ruler's job; closing it is a
    contract change and the owner's word.
    """
    sys.path.insert(0, HERE)
    import equality  # the same list the gate judges with - not a second copy of it
    req = set(schema["required"])
    props = set(schema["properties"])
    return ([f for f in equality.VERDICT_FIELDS if f not in req],
            [f for f in equality.VERDICT_FIELDS if f not in props])


def omission_lines(omissions, ports_seen, gap_fields):
    """Per-port count of cells that omit each verdict field the schema does not insist on."""
    if not gap_fields:
        return []
    out = ["", "## Verdict fields the schema does not require", "",
           "The gate compares the fields below as a port's *answer*; the schema lets a port leave them out, "
           "so a",
           "cell can be **conforming and silent** at the same time. Both readings in this file are true at "
           "once.", "",
           "| field | " + " | ".join(ports_seen) + " |", "|---" * (len(ports_seen) + 1) + "|"]
    for f in gap_fields:
        out.append("| `%s` | " % f + " | ".join(str(omissions.get((p, f), 0)) for p in ports_seen) + " |")
    total = sum(omissions.get((p, f), 0) for p in ports_seen for f in gap_fields)
    out += ["", "**cells omitting a compared verdict field: %d (across %d ports, %d fields)**"
            % (total, len(ports_seen), len(gap_fields)), ""]
    return out


def selftest():
    """Red/green arms for this ruler, including the proof that refusing does not write."""
    errs = []

    def chk(cond, msg):
        if not cond:
            errs.append(msg)

    u, q = parse_args(["--quiet"])
    chk(u == [] and q is True, "selftest A1 green: --quiet should be known and set quiet")
    u, q = parse_args([])
    chk(u == [] and q is False, "selftest A2 green: bare call should be accepted")
    u, _ = parse_args(["--out-dir", "x", "--selftest-x"])
    chk(u == ["--out-dir", "x", "--selftest-x"], "selftest A3 red: unknown tokens must be named, got %r" % (u,))

    probs = [("c%d.json", ["missing required read_result"]) for _ in range(8)]
    ls = port_lines("go", 10, 2, "-", probs, False)
    chk(any(l.startswith("  - shown=6 total=8 TRUNCATED") for l in ls),
        "selftest A4 red: a truncated sample must print its denominator: %r" % (ls[1:3],))
    chk(all("[port=go]" in l for l in ls if l.startswith("  - `")),
        "selftest A5 red: every sample line must name its port - an unattributed list under a table "
        "reads as the last port's")
    ls = port_lines("go", 10, 8, "-", probs[:2], False)
    chk(any(l == "  - shown=2 total=2" for l in ls) and not any("TRUNCATED" in l for l in ls),
        "selftest A6 green: two of two must not claim truncation")
    ls = port_lines("go", 10, 10, "-", [], False)
    chk(not any("shown=" in l for l in ls), "selftest A7 green: no problems must print no sample denominator")
    ls = port_lines("go", 10, 2, "-", probs, True)
    chk(len(ls) == 1 and ls[0].startswith("| go |"), "selftest A8 green: --quiet keeps the row, drops samples")

    chk(any("SELF-REPORT-DISAGREES" in l and "(+2)" in l
            for l in port_lines("java", 9, 5, "3", [], False)),
        "selftest A9 red: a self-report below the ruler must be named with its signed gap")
    chk(not any("SELF-REPORT" in l for l in port_lines("java", 9, 5, "5", [], False)),
        "selftest A10 green: agreement must not cry disagreement")
    chk(not any("SELF-REPORT" in l for l in port_lines("java", 9, 5, "-", [], False)),
        "selftest A11 green: 'no self-report published' is not a disagreement")

    doc = os.path.join(REPO, "docs", "cell-validation.md")
    before = io.open(doc, "rb").read() if os.path.isfile(doc) else None
    p = subprocess.run([sys.executable, os.path.abspath(__file__), "--out-dir", "zz"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=REPO)
    chk(p.returncode == 3, "selftest A12 red: an unknown argument must exit 3 (instrument), got %d"
        % p.returncode)
    if before is not None and os.path.isfile(doc):
        chk(io.open(doc, "rb").read() == before,
            "selftest A13 red: refusing must not also write the face")
    chk(dispatch(["--selftest", "--out-dir", "zz"]) == ("refuse", ["--out-dir", "zz"]),
        "selftest A14 red: junk alongside --selftest is still junk")
    chk(dispatch(["--selftest"]) == ("selftest",) and dispatch(["--quiet"]) == ("run", True)
        and dispatch([]) == ("run", False),
        "selftest A15 green: the three real modes must route correctly")

    fake = {"required": ["os_legality_verdict"], "properties": {"mechanism_class": {}}}
    gap_req, gap_doc = verdict_field_gap(fake)
    chk("os_legality_verdict" not in gap_req,
        "selftest A16 green: a verdict field the schema requires is not a gap")
    chk("mechanism_class" in gap_req and "roundtrip_ok" in gap_req,
        "selftest A17 red: compared-but-optional fields must be named, got %r" % (gap_req,))
    chk("phantom" in gap_doc and "len_triple" in gap_doc,
        "selftest A18 red: a verdict field the schema never documents must be called out separately")
    s = stamp_census([{"case_group": "ctrl", CONTROL_FIELD: True, CONTROL_EVIDENCE_FIELD: "python x.py"},
                      {"case_group": "ctrl", CONTROL_FIELD: True},
                      {"case_group": "ctrl", CONTROL_FIELD: False},
                      {"case_group": "ctrl"},
                      {"case_group": "trap", CONTROL_FIELD: True}])
    chk(s == {"stamped_with_evidence": 1, "stamped_no_evidence": 2, "unstamped": 1},
        "selftest A23 red: a control stamped without a source is its own bucket, never counted as verified "
        "and never counted as unstamped, got %r" % (s,))
    chk(stamp_census([{"case_group": "trap", CONTROL_FIELD: True}]) ==
        {"stamped_with_evidence": 0, "stamped_no_evidence": 0, "unstamped": 0},
        "selftest A24 green: non-control cells are not in a control census")
    a = applicability_counts([{APPLICABILITY_FIELD: True}, {APPLICABILITY_FIELD: False},
                              {"case_id": "T01"}, {APPLICABILITY_FIELD: None}])
    chk(a == {"true": 1, "false": 1, "absent": 2},
        "selftest A21 green: true, false, absent and null are four different facts and must count apart, "
        "got %r" % (a,))
    chk(applicability_counts([{"case_id": "T01"}])["false"] == 0
        and applicability_counts([{APPLICABILITY_FIELD: "yes"}])["absent"] == 1,
        "selftest A22 red: an undeclared or non-boolean value must never be read as a declaration, got %r"
        % (applicability_counts([{APPLICABILITY_FIELD: "yes"}]),))
    ls = omission_lines({("go", "roundtrip_ok"): 3}, ["csharp", "go"], ["roundtrip_ok"])
    chk(any("| `roundtrip_ok` | 0 | 3 |" in l for l in ls)
        and any("cells omitting a compared verdict field: 3" in l for l in ls),
        "selftest A19 red: an omission must be counted per port with its total, got %r" % (ls[-2:],))
    chk(omission_lines({}, ["go"], []) == [],
        "selftest A20 green: no gap means no table, not a table of nothing")
    return errs


def main():
    mode = dispatch(sys.argv[1:])
    if mode[0] == "refuse":
        print("OUTCOME=VOID unknown argument(s): %s" % ", ".join(mode[1]))
        print("usage: python ci/validate_cells.py [--quiet | --selftest]")
        print("this leg always writes docs/cell-validation.md and accepts no output path - refusing is the "
              "only honest answer to a caller that thinks it redirected the face")
        return 3
    if mode[0] == "selftest":
        errs = selftest()
        for e in errs:
            print("SELFTEST-FAIL: %s" % e)
        print("arms=24 passed=%d" % (24 - len(errs)))
        return 1 if errs else 0
    quiet = mode[1]
    if not os.path.isfile(SCHEMA):
        print("OUTCOME=VOID schema missing")
        return 3
    schema = json.load(io.open(SCHEMA, encoding="utf-8"))
    strict = schema.get("additionalProperties")
    gap_required, gap_documented = verdict_field_gap(schema)
    gap_fields = [f for f in equality.VERDICT_FIELDS if f in gap_required]
    omissions = collections.defaultdict(int)
    lines = ["# Cell validation, by an outside ruler", "",
             "Generated by `ci/validate_cells.py` at %s against `spec/schema.json` "
             "(%d required fields, %d documented properties, additionalProperties=%s)."
             % (time.strftime("%Y-%m-%d %H:%M:%S %z"), len(schema["required"]),
                len(schema["properties"]), strict),
             "",
             "Each port's own self-check reports a validity count for itself. This table is the same "
             "question asked by a ruler that the port does not own.",
             "",
             "| port | cells read | valid | invalid | self-reported (its own script) |",
             "|---|---|---|---|---|"]
    total_bad = 0
    missing_faces = []
    appl = {}
    stamps = {}
    for port in PORTS:
        face = os.path.join(REPO, "results", "%s.windows.x64" % port)
        if not os.path.isdir(face):
            missing_faces.append(port)
            lines.append("| %s | - | - | - | FACE-MISSING |" % port)
            continue
        n = ok = 0
        problems = []
        port_cells = []
        for f, cell, err in cells_in(face):
            if err:
                problems.append((os.path.basename(f), [err]))
                n += 1
                continue
            n += 1
            if isinstance(cell, dict):
                port_cells.append(cell)
                for gf in gap_fields:
                    if gf not in cell:
                        omissions[(port, gf)] += 1
            p = check(cell, schema)
            if p:
                problems.append((os.path.basename(f), p))
            else:
                ok += 1
        total_bad += len(problems)
        rep = "-"
        sc = os.path.join(REPO, "evidence", "S02", "%s-selfcheck.md" % port)
        if os.path.isfile(sc):
            t = io.open(sc, encoding="utf-8", errors="replace").read()
            m = re.search(r"cells_valid[= ]+(\d+)", t)
            if m:
                rep = m.group(1)
        lines += port_lines(port, n, ok, rep, problems, quiet)
        appl[port] = applicability_counts(port_cells)
        stamps[port] = stamp_census(port_cells)
    lines += ["", "**invalid cells across the six faces: %d**" % total_bad, ""]
    lines += omission_lines(omissions, [p for p in PORTS if os.path.isdir(
        os.path.join(REPO, "results", "%s.windows.x64" % p))], gap_fields)
    lines += ["", "## Control-cell stamps and whether they say where they came from", "",
              "| port | ctrl cells | stamped with an evidence pointer | stamped, no pointer | no stamp |",
              "|---|---|---|---|---|"]
    for p in PORTS:
        s = stamps.get(p, {"stamped_with_evidence": 0, "stamped_no_evidence": 0, "unstamped": 0})
        lines.append("| %s | %d | %d | %d | %d |"
                     % (p, s["stamped_with_evidence"] + s["stamped_no_evidence"] + s["unstamped"],
                        s["stamped_with_evidence"], s["stamped_no_evidence"], s["unstamped"]))
    naked = [p for p in PORTS if stamps.get(p, {}).get("stamped_no_evidence", 0) > 0]
    lines += ["", "**ports holding a control stamp with no recorded source: %s** (a stamp is a claim about the "
              "instrument; without a pointer a reviewer cannot re-check it)"
              % (", ".join("`%s`" % p for p in naked) or "none"), ""]

    declared = [p for p in PORTS if appl.get(p, {}).get("true", 0) + appl.get(p, {}).get("false", 0) > 0]
    lines += ["", "## Who declares whether a question applies on this OS", "",
              "`spec/schema.json` documents `spec_applicable_on_windows` and no leg reads it. The counts "
              "below are what a contract round has to work from: a `false` is a port saying \"this trap is "
              "Windows semantics, the POSIX answer is a different question\", while `absent` is silence "
              "about it - not a denial.", "",
              "| port | true | false | absent (no claim made) |", "|---|---|---|---|"]
    for p in PORTS:
        a = appl.get(p, {"true": 0, "false": 0, "absent": 0})
        lines.append("| %s | %d | %d | %d |" % (p, a["true"], a["false"], a["absent"]))
    lines += ["", "**ports that ever declare applicability: %s** (of %d)"
              % (", ".join("`%s`" % p for p in declared) or "none", len(PORTS)),
              "A convention kept by one port is not a contract. Either the field gains a rule (who must write "
              "it, on which case groups) or it should be dropped rather than left as one lane's habit.", ""]
    if gap_documented:
        lines.append("Verdict fields the gate compares that `spec/schema.json` does not even document: %s. "
                     "They are legal extras today and unverifiable requirements tomorrow."
                     % ", ".join("`%s`" % f for f in gap_documented))
        lines.append("")
    if missing_faces:
        lines.append("Faces not readable: %s" % ", ".join(missing_faces))
        lines.append("")
    lines += ["## What this does and does not say", "",
              "- it says a cell carries the fields the frozen contract requires, with values inside the "
              "frozen enums. It does **not** say the cell is *true* - that is the sealed expectation "
              "table's question (`docs/expected-summary.md`) and the gate's (`docs/STATUS.md`);",
              "- documented properties are checked; undocumented extra fields are **allowed** "
              "(additionalProperties=%s) because a port that records how it measured something is doing the "
              "right thing, and a rule that punished that would be a rule against evidence;" % strict,
              "- where this table and a port's own self-check disagree, this table is the one a stranger "
              "can reproduce, and the disagreement belongs in the acceptance sheet, not in a footnote.", ""]
    text = "\n".join(lines) + "\n"
    io.open(os.path.join(REPO, "docs", "cell-validation.md"), "w", encoding="utf-8", newline="\n").write(text)
    omit_total = sum(omissions.values())
    print("wrote docs/cell-validation.md bytes=%d invalid=%d missing_faces=%d "
          "verdict_fields_not_required=%d verdict_fields_undocumented=%d cells_omitting_a_compared_field=%d"
          % (len(text.encode("utf-8")), total_bad, len(missing_faces), len(gap_fields),
             len(gap_documented), omit_total))
    if missing_faces:
        return 3
    return 1 if total_bad else 0


if __name__ == "__main__":
    try:
        rc = main()
    except Exception as e:
        # rc=1 is this leg's word for "a cell does not conform". A crash must not be allowed to borrow it -
        # measured 2026-10-11 12:09, when a KeyError in the omission counter exited 1 and ci/refresh_all.py
        # lists 1 among the acceptable readings, so the tool failure would have been filed as a result.
        import traceback
        traceback.print_exc()
        print("OUTCOME=INSTRUMENT-RED %s: a crash is not a measurement" % type(e).__name__)
        sys.exit(3)
    sys.exit(rc)
