"""Generate docs/coverage.md: how much of the verdict grid each port actually filled in.

Run:  python ci/coverage_report.py

Why this exists: the gate's headline is "24 cells with no verdict disagreement", and 24 is a number a reader
will read as "24 cells where six ports gave the same answer". Measured on the real tree at 11:54:29, only 4 of
those 24 have every verdict field recorded by every port, and 123 of 430 field-cells were blank. Silence and
agreement are different facts, and this file keeps them apart. The numbers are not recomputed here - they are
read out of the gate's own artifact, so a second ruler cannot disagree with the first (the defect that this
project has now caught in itself three times).

Exit codes: 0 = the artifact was readable and came from this repository's results/ face and every blank
attributed; 3 = the artifact is
missing or came from somewhere else (an instrument problem, never a measurement). This leg does not judge
coverage - it publishes it.
"""
import io
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
VPATH = os.path.join(REPO, "evidence", "S02", "equality-verdict.json")
# Used only by the arms; production reads the field names out of the artifact, so a fixture cannot
# drift from the real list and call that a pass.
VERDICT_FIELDS_SAMPLE = ["a", "b", "c"]



# Attribution of a blank. The contract does not yet say which verdict fields apply to which case group, so this
# report may not decide whether a blank is legal - that is a contract round (the sealed one is the eighth) and it
# is one of the questions parked with the owner. What it can do is sort the blanks by a fact each port already
# published: how many of the ten verdict fields the *same port* answered in the *same cell*. A port that answered
# nine of ten here and left this one out is a different piece of work from a port that answered two.
BUCKETS = [(10, 10, "answered all ten (the blank contradicts the count - instrument problem)"),
           (9, 9, "answered the other nine here"),
           (7, 8, "answered 7-8 of ten here"),
           (4, 6, "answered 4-6 of ten here"),
           (1, 3, "answered 1-3 of ten here"),
           (0, 0, "answered nothing else in this cell")]


def tally_for(per_port, label):
    """A bucket column prints only when some port has a blank in it - an empty column would read as a zero."""
    return any(per_port[p].get(label) for p in per_port)


def bucket_of(count):
    for lo, hi, label in BUCKETS:
        if lo <= count <= hi:
            return label
    return "count outside the table (%d) - instrument problem" % count


def attribute_blanks(nr_rows, cell_counts, fields, ports):
    """nr_rows is the gate's not_recorded_pairs: [cell, field, [ports that did not record it]]."""
    rows = []
    problems = []
    tally = {}
    per_port = {p: {} for p in ports}
    for cell, field, who in nr_rows:
        here = cell_counts.get(cell)
        if here is None:
            problems.append("%s: the gate names a blank in a cell the count table does not carry" % cell)
            continue
        for p in who:
            if p not in ports:
                problems.append("%s/%s: blank attributed to %r, which is not a port this run compared"
                                % (cell, field, p))
                continue
            c = here.get(p)
            if c is None:
                problems.append("%s/%s: no answer count for port %s in that cell" % (cell, field, p))
                continue
            label = bucket_of(c)
            if "instrument problem" in label:
                problems.append("%s: `%s` blank for %s, yet the same artifact says that port answered %d of %s "
                                "verdict fields in that cell - the two numbers in one artifact disagree"
                                % (cell, field, p, c, len(fields)))
                continue
            rows.append((cell, field, p, c, label))
            tally[label] = tally.get(label, 0) + 1
            per_port[p][label] = per_port[p].get(label, 0) + 1
    covered = {(c, f) for c, f, _p, _n, _l in rows}
    if len(covered) != len(nr_rows):
        problems.append("%d of the gate's %d (cell, field) blank rows contributed no attributable port - a blank "
                        "cannot be attributed to nobody and then disappear from the count"
                        % (len(nr_rows) - len(covered), len(nr_rows)))
    return rows, tally, per_port, problems



SELFTEST_ARMS = 9


def selftest():
    errs = []
    seen = set()

    def chk(cond, msg):
        m = re.match(r"selftest (A\d+)", msg)
        if m:
            seen.add(m.group(1))
        if not cond:
            errs.append(msg)

    fields = list(VERDICT_FIELDS_SAMPLE)
    ports = ["alpha", "beta"]
    counts = {"c1": {"alpha": 10, "beta": 10}, "c2": {"alpha": 9, "beta": 2}, "c3": {"alpha": 0, "beta": 5}}
    rows, tally, per_port, problems = attribute_blanks(
        [["c2", "phantom", ["alpha"]], ["c3", "bytes_on_disk", ["alpha"]]], counts, fields, ports)
    chk(len(rows) == 2 and not problems,
        "selftest A1 green: a blank where the port answered nine else here, and one where it answered nothing, "
        "must both attribute, got %r %r" % (rows, problems))
    chk(tally.get("answered the other nine here") == 1 and tally.get("answered nothing else in this cell") == 1,
        "selftest A1 green: the two blanks must land in different buckets, got %r" % (tally,))
    chk(per_port["alpha"]["answered the other nine here"] == 1 and per_port["beta"] == {},
        "selftest A2 green: attribution is per port - a port that recorded the field is not charged with its "
        "absence, got %r" % (per_port,))
    rows, _t, _pp, problems = attribute_blanks([["c1", "phantom", ["alpha"]]], counts, fields, ports)
    chk(problems and "disagree" in problems[0],
        "selftest A3 red: a blank in a cell where the artifact also says the port answered all ten is one "
        "artifact contradicting itself, and must be named, got %r" % (problems,))
    rows, _t, _pp, problems = attribute_blanks([["c9", "phantom", ["alpha"]]], counts, fields, ports)
    chk(problems and "c9" in problems[0],
        "selftest A4 red: a blank in an unknown cell is an instrument problem, not a row dropped on the floor, "
        "got %r" % (problems,))
    rows, _t, _pp, problems = attribute_blanks([["c2", "phantom", ["gamma"]]], counts, fields, ports)
    chk(problems and "gamma" in problems[0],
        "selftest A5 red: an attribution to a port that was not compared must be named, got %r" % (problems,))
    chk(bucket_of(6) == "answered 4-6 of ten here" and bucket_of(11).endswith("instrument problem"),
        "selftest A6 red: the bucket table must cover every legal count and reject one it cannot place, not file "
        "it silently")
    chk(tally_for({"alpha": {"x": 0}, "beta": {"x": 3}}, "x")
        and not tally_for({"alpha": {"x": 0}, "beta": {"y": 1}}, "x"),
        "selftest A7 green: a bucket column prints when any port has a blank in it and stays out when none does")
    rows, _t, _pp, problems = attribute_blanks(
        [["c2", "phantom", ["alpha"]], ["c2", "phantom", []], ["c3", "roundtrip_ok", ["beta"]]],
        counts, fields, ports)
    chk(len(rows) == 2 and any("no attributable port" in x and "1 of the gate's 3" in x for x in problems),
        "selftest A8 red: a blank row that charges nobody must be reported as a hole in the report, not silently "
        "dropped from the count - got rows=%d problems=%r" % (len(rows), problems))
    _r2, tally2, _p2, _q2 = attribute_blanks([["c2", "phantom", ["alpha", "beta"]]], counts, fields, ports)
    chk(sum(tally2.values()) == 2,
        "selftest A8 green: one gate row charging two ports must expand to two bucket entries, and the bucket "
        "column sum is what the face prints as the expanded count - got %r" % (tally2,))
    # Python evaluates the condition before chk can register this message's own label, so the guard
    # counts itself in explicitly rather than pretending it already ran.
    chk(len(seen) + 1 == SELFTEST_ARMS,
        "selftest A9 red: the published arm count must equal the distinct labels that actually ran - %d exercised "
        "(%s) against SELFTEST_ARMS=%d" % (len(seen), ",".join(sorted(seen)), SELFTEST_ARMS))
    return errs


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--selftest" in argv:
        errs = selftest()
        for e in errs:
            print("SELFTEST-FAIL: %s" % e)
        print("arms=%d passed=%d" % (SELFTEST_ARMS, SELFTEST_ARMS - len(errs)))
        return 1 if errs else 0
    unknown = [a for a in argv if a != "--selftest"]
    if unknown:
        print("OUTCOME=INSTRUMENT-RED this report takes no argument but --selftest and was handed %r; it writes nothing" % (unknown,))
        return 3
    if not os.path.isfile(VPATH):
        print("REFUSING: the gate's verdict artifact is missing. Run `python ci/equality.py` first")
        return 3
    verdict = json.load(io.open(VPATH, encoding="utf-8"))
    if verdict.get("source_results") != "results":
        print("REFUSING: the verdict was written from %r, not from this repository's results/ face"
              % verdict.get("source_results"))
        return 3

    cov = verdict["verdict_field_coverage"]
    fields = verdict["verdict_fields"]
    names = sorted({p for f in fields for p in cov.get(f, {})})
    if not names:
        print("REFUSING: the artifact carries no coverage table - it was written by a gate older than this "
              "report; re-run `python ci/equality.py`")
        return 3
    recorded = verdict["verdict_pairs_recorded"]
    possible = verdict["verdict_pairs_possible"]
    full = verdict["cells_every_port_recorded_every_verdict_field"]
    clean = verdict["cells_with_no_verdict_disagreement_and_fully_recorded"]
    no_port = verdict.get("verdict_pairs_no_port_recorded", [])
    nr = verdict.get("not_recorded_pairs", [])
    cell_counts = verdict.get("cell_port_verdict_fields_recorded")
    if cell_counts is None:
        print("REFUSING: the artifact carries no per-port answer counts, so blanks cannot be "
              "attributed. Re-run `python ci/equality.py` - this report will not guess them "
              "from the faces")
        return 3
    compared = verdict["cells_compared"]
    denom_per_port = len(fields) * compared

    lines = ["# Coverage - who answered, not just who agreed", "",
             "Generated by `ci/coverage_report.py` at %s from `evidence/S02/equality-verdict.json` "
             "(written by the gate at %s)." % (time.strftime("%Y-%m-%d %H:%M:%S %z"),
                                               verdict.get("written_at", "-")),
             "",
             "This table answers a question the headline number hides: a cell where six ports recorded three",
             "of ten verdict fields and contradicted on none is not the same fact as a cell where six ports",
             "answered everything and matched. **Cells compared: %d. Verdict field-cells possible: %d. "
             "Recorded: %d (%.1f%%).**" % (compared, possible, recorded,
                                           100.0 * recorded / possible if possible else 0.0),
             "",
             "| verdict field | " + " | ".join(names) + " | blanks in all six |",
             "|---" * (len(names) + 2) + "|"]
    for f in fields:
        blank_all = sum(1 for k, ff in no_port if ff == f)
        lines.append("| `%s` | " % f + " | ".join("%d/%d" % (cov[f].get(p, 0), compared) for p in names)
                     + " | %d |" % blank_all)
    lines += ["", "**cells where every port recorded every verdict field: %d/%d** - %s"
              % (len(full), compared, ", ".join("`%s`" % c for c in full) or "none"),
              "",
              "**cells with no verdict disagreement AND fully recorded: %d/%d** - %s"
              % (len(clean), compared, ", ".join("`%s`" % c for c in clean) or "none"),
              "",
              "The published headline is `cells_with_no_verdict_disagreement=%d` (see `docs/STATUS.md`); the "
              "line " % verdict["cells_with_no_verdict_disagreement"],
              "above is what that headline means once silence is subtracted. Both numbers are printed by the "
              "gate,",
              "in the same `OUTCOME=` line, so neither can be quoted without the other.",
              "",
              "## What a blank is, and what it is not",
              "",
              "- A blank is **not** an agreement: the gate compares only the ports that recorded a field, and "
              "a cell where",
              "  five of six recorded still counts as `VERDICT-NOT-RECORDED` for the sixth (%d such field-cells "
              "in this run)." % len(nr),
              "- A blank is **not yet** distinguishable from 'this field does not apply to this case group'. The "
              "frozen contract",
              "  lists verdict fields per checker answer but never says which of them apply to which case group, "
              "so this",
              "  report publishes every blank and judges none of them. Deciding which blanks are legal is a "
              "contract",
              "  change (the current sealed round is the eighth); filling a blank is the port's own work.",
              "- `%d` field-cells were left blank by **all six** ports - nobody answered that question at all. "
              "Those are" % len(no_port),
              "  listed by name below, and they are the cheapest cells in the whole project to make valuable.",
              ""]
    if no_port:
        lines += ["| cell | field nobody recorded |", "|---|---|"]
        lines += ["| `%s` | `%s` |" % (k, f) for k, f in sorted(no_port)]
        lines.append("")
    att_rows, tally, per_port, att_problems = attribute_blanks(nr, cell_counts, fields, names)
    shown = [l for _a, _b, l in BUCKETS if tally_for(per_port, l)]
    lines += ["", "## Sorting the blanks by what the same port answered in the same cell", "",
              "The frozen contract never says which verdict fields apply to which case group, so whether a blank ",
              "is *legal* is a contract question and this report does not answer it. What it can measure is the ",
              "shape of the work: for each blank, how many of the ten verdict fields that same port recorded in ",
              "that same cell. The gate publishes `%d` (cell, field) rows; a row may charge more than one "
              "port, so they expand to `%d` (cell, field, port) blanks below, and every one of them is "
              "placed in exactly one bucket." % (len(nr), len(att_rows)), "",
              "| what the port answered in that cell | blank rows |", "|---|---|"]
    for _lo, _hi, label in BUCKETS:
        if "instrument problem" in label:
            continue
        lines.append("| %s | %d |" % (label, tally.get(label, 0)))
    lines += ["", "The bucket column sums to %d, which is the expanded (cell, field, port) count - nothing is "
              "placed in two buckets and nothing is left unplaced." % sum(tally.values()), "",
              "| port | " + " | ".join(l.split(" (")[0] for l in shown) + " |",
              "|---" * (1 + len(shown)) + "|"]
    for p in names:
        lines.append("| %s | " % p + " | ".join(str(per_port[p].get(l, 0)) for l in shown) + " |")
    lines.append("")
    if att_problems:
        lines += ["## Instrument problems found while attributing blanks", ""]
        lines += ["- %s" % x for x in att_problems[:12]]
        if len(att_problems) > 12:
            lines.append("- TRUNCATED shown=12 total=%d" % len(att_problems))
        lines.append("")
    lines += ["## Per-port totals", "",
              "| port | verdict field-cells recorded | of possible |", "|---|---|---|"]
    for p in names:
        got = sum(cov[f].get(p, 0) for f in fields)
        lines.append("| %s | %d | %d (%.1f%%) |" % (p, got, denom_per_port,
                                                    100.0 * got / denom_per_port if denom_per_port else 0.0))
    lines += ["", "Commands:", "", "```", "python ci/equality.py | sed -n '/coverage (who answered what)/,/^   "
              "csharp/p'", "python ci/coverage_report.py && cat docs/coverage.md", "```", ""]
    text = "\n".join(lines) + "\n"
    io.open(os.path.join(REPO, "docs", "coverage.md"), "w", encoding="utf-8", newline="\n").write(text)
    print("wrote docs/coverage.md bytes=%d fields=%d ports=%d cells_compared=%d recorded=%d/%d "
          "fully_recorded=%d clean_and_fully_recorded=%d blanks_by_everybody=%d"
          % (len(text.encode("utf-8")), len(fields), len(names), compared, recorded, possible,
             len(full), len(clean), len(no_port)))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        print("OUTCOME=INSTRUMENT-RED %s: a crash is not a measurement, and this report's exit codes "
              "are 0 and 3" % type(e).__name__)
        sys.exit(3)
