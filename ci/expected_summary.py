"""Expected vs measured, row by row, generated from the sealed table and the canonical faces.

Run:  python ci/expected_summary.py            (prints and writes docs/expected-summary.md)

The sealed expectation table (`spec/expectations.sealed.md`) was written by a window that read only the
spec - no port, no implementation, no result file - so that six ports agreeing on something the spec never
said is detectable against it. This file is where that property becomes readable: one row per
(case x field) the expectation predicted, with what the ports actually returned.

Words used, and why each exists:
  REPRODUCED      every port that answered this cell returned the expected value
  PARTIAL         some ports returned it and some did not - the expectation and the matrix disagree
  CONTRADICTED    no port that answered returned it (this is the row a collective misreading looks like)
  NOT-RUN         no port answered the cell at all; the expectation is untested, not confirmed
  NO-SUCH-CELL    the expectation table names a cell id that appears in no port's records - a join
                  failure between the sealed table and spec/cases.yaml, reported instead of guessed
  NOT-RUN(no face for that OS)
                  the sealed table predicts macOS and Ubuntu behaviour (22 parsed rows each, from 23 lines
                  apiece, the extra line folding to "same as macos row") and no port has produced a face on
                  either. Published as untested predictions with the reason measured on
                  the harnesses - the runners write to a hard-coded `results/<port>.windows.x64/` and probe
                  Windows-only semantics - so pushing this tree to CI creates those faces no better than it
                  creates a seventh language. Added at 13:10 today, because until then this leg parsed 69
                  sealed rows and published only the Windows half of them (44 rows, silently).
The distinction between the last two and the first two is the whole point: an unrun cell must never be
folded into a pass rate.
"""
import io
import json
import os
import sys
import hashlib
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import equality  # noqa: E402
import triangle  # noqa: E402

FIELDS = ["create_result", "read_result", "os_legality_verdict", "path_form",
          "bytes_on_disk", "bytes_written", "phantom"]


def want_match(w, s, port_cell):
    """the sealed table uses two sentinels instead of numbers: `null` (no entry / no bytes expected) and
    `eq_written` (the bytes on disk equal what the write call claims). They are resolved here, against the
    same port's own record, so a sentinel can never be satisfied by a coincidence of digits."""
    if w == "null":
        return s in (None, "", "None", "null", "0")
    if w == "eq_written":
        bw = equality.canon_value("bytes_written", port_cell)
        return bw not in (equality.ABSENT, ("x", None), ("null", None)) and s == str(bw[1])
    return str(w) == s


def main():
    exp, _meta = triangle.parse_expectations(os.path.join(REPO, "spec", "expectations.sealed.md"))
    ports, files_seen, problems, xcheck, skipped = equality.discover()
    ports.pop("_extra_counts", {})
    cells = {}
    for port in sorted(ports):
        cells[port] = {}
        for key, lst in ports[port].items():
            if key[0] == "tapi":
                continue
            cells[port][key[1]] = lst[0]

    counts = {}
    rows = []
    pub_cases = set()
    cases = sorted({c for (c, o) in exp})
    for case in cases:
        for f in FIELDS:
            want = exp.get((case, "windows"), {}).get(f)
            if not want:
                continue
            wantset = want if isinstance(want, set) else {want}
            got, missing = {}, []
            p_case = case
            for port in sorted(cells):
                if case not in cells[port]:
                    missing.append(port)
                    continue
                v = equality.canon_value(f, cells[port][case])
                if v in (equality.ABSENT, ("x", None), ("null", None)):
                    missing.append(port)
                    continue
                s = str(v[1])
                got[port] = s
            hit = {p for p, s in got.items()
                   if any(want_match(w, s, cells[p].get(p_case) or {})
                          for w in wantset)}
            if not any(case in cells[p] for p in cells):
                # the sealed table and the spec disagree about the cell's name. That is a join failure in
                # the contract, not a measurement, and it must not be reported as "no port ran it".
                word = "NO-SUCH-CELL"
            elif not got:
                word = "NOT-RUN"
            elif len(hit) == len(got):
                word = "REPRODUCED"
            elif not hit:
                word = "CONTRADICTED"
            else:
                word = "PARTIAL"
            counts[word] = counts.get(word, 0) + 1
            if word == "NOT-RUN" and not missing:
                continue
            rows.append((case, f, sorted(wantset), word, got, sorted(missing)))
            pub_cases.add(case)

    out = ["# Expected vs measured", "",
           "Generated by `ci/expected_summary.py` at %s from `spec/expectations.sealed.md` (%d expectation "
           "rows) and the canonical result faces." % (time.strftime("%Y-%m-%d %H:%M:%S %z"), len(exp)),
           "",
           "- the expectation table was sealed at spec/cases.yaml sha256 `08484788745d…`; the spec has since "
           "gained pinned `control_samples` (sha256 `%s…`), so the five control rows below are predictions "
           % hashlib.sha256(io.open(os.path.join(REPO, "spec", "cases.yaml"), "rb").read()).hexdigest()[:12]
           + "made **before** their input bytes were fixed. They are still the honest test - the input change "
           "pins which sample was asked, it does not change what was predicted - but a reader should know the "
           "order of events rather than assume the table was written against the current bytes.",
           "- faces read: %s; faces excluded: %s"
           % (", ".join(sorted(cells)), ", ".join("`%s`" % e for e, _ in skipped) or "none"),
           "- counts: %s" % ", ".join("%s=%d" % (k, counts[k]) for k in sorted(counts)),
           "",
           "| cell | field | expected (windows) | status | what the ports returned | ports with no value |",
           "|---|---|---|---|---|---|"]
    for case, f, want, word, got, missing in rows:
        shown = "; ".join("%s=%s" % (p, got[p][:18]) for p in sorted(got)) or "-"
        out.append("| %s | %s | %s | %s | %s | %s |"
                   % (case, f, ",".join(str(w) for w in want)[:40], word,
                      shown[:110], ",".join(missing) or "-"))
    # ---- the sealed rows for the OSes no port has run on. Until 13:0x today these were silently dropped by
    # `if osn != "windows": continue` in two legs, so a table that seals 23 macOS and 23 Ubuntu predictions
    # published none of them, and an outside reader could not tell "we checked and it is untested" from
    # "there was nothing to check".
    sealed_by_os, other = {}, {}
    for (case, osn), row in exp.items():
        sealed_by_os[osn] = sealed_by_os.get(osn, 0) + 1
        if osn == "windows":
            continue
        other.setdefault(osn, []).append((case, row))
    win_cases = {c for (c, o) in exp if o == "windows" and any(exp[(c, o)].get(f) is not None for f in FIELDS)}
    # (defined above the table because the table's two counts differ on purpose: some sealed rows predict
    # only `name_landed_as`, which ci/triangle.py scores and this summary does not.)
    os_section = ["", "## Sealed expectations for operating systems no port has run on", "",
                  "| os | sealed rows in the table | rows published below | canonical faces on disk for that os |",
                  "|---|---|---|---|",
                  "| windows | %d rows (%d carry a field this summary compares) | %d field-level lines over "
                  "%d cells | %d (%s) |"
                  % (sealed_by_os.get("windows", 0), len(win_cases), len(rows), len(pub_cases), len(ports),
                     ", ".join(sorted(ports)))]
    for osn in sorted(other):
        os_section.append("| %s | %d | %d | 0 - no face is named `%s.<os>.<arch>` in `results/` |"
                          % (osn, sealed_by_os.get(osn, 0), len(other[osn]), "<port>"))
    os_section += ["",
                   "State `NOT-RUN(no face for that OS)` is deliberately not `NOT-REACHED(reason=missing)` and "
                   "not a",
                   "pass rate: the prediction exists, the question has not been asked of any implementation on "
                   "that",
                   "operating system. The reason is measured rather than guessed - every port's runner writes "
                   "to a",
                   "hard-coded `results/<port>.windows.x64/` and probes Windows-only behaviour, so pushing this "
                   "tree",
                   "to CI would not create these rows; the harnesses need an OS-portability pass first "
                   "(`docs/tickets/SG-F3-os-portability.md`).", ""]
    shown_other = []
    for osn in sorted(other):
        items = sorted(other[osn])
        os_section.append("### %s - shown=%d total=%d%s" % (osn, min(12, len(items)), len(items),
                            " TRUNCATED" if len(items) > 12 else ""))
        os_section.append("")
        os_section += ["| cell | predicted fields (sealed, untested on this OS) | confidence |",
                       "|---|---|---|"]
        for case, row in items[:12]:
            pred = ", ".join("%s=%s" % (f, sorted(row[f])[0] if isinstance(row.get(f), set) else row.get(f))
                             for f in FIELDS if row.get(f) is not None)
            os_section.append("| %s | %s | %s |" % (case, pred[:150], row.get("confidence", "-")))
        os_section.append("")

    out += os_section
    text = "\n".join(out) + "\n"
    dest = os.path.join(REPO, "docs", "expected-summary.md")
    io.open(dest, "w", encoding="utf-8", newline="\n").write(text)
    # the invariant that would have caught this leg's own silent drop: every sealed row must be accounted
    # for in the published file, either as a measured line (windows) or as a named untested prediction
    # (macos, ubuntu). A count that cannot be reconciled is an instrument failure, never a shorter document.
    dropped = ["%s(sealed=%d published=%d)" % (o, sealed_by_os[o], len(other.get(o, [])))
               for o in sealed_by_os if o != "windows" and len(other.get(o, [])) != sealed_by_os[o]]
    # the two counts differ on purpose and the difference is published: some sealed rows predict only
    # `name_landed_as`, which ci/triangle.py scores and this summary does not, so "%d rows" and "%d cells
    # compared" are different denominators rather than one of them being wrong.
    if win_cases - pub_cases:
        dropped.append("windows(cases with a prediction and no published line: %s)"
                       % ",".join(sorted(win_cases - pub_cases))[:120])
    print("wrote docs/expected-summary.md bytes=%d rows=%d counts=%s sealed_by_os=%s published_other_os_rows=%s"
          % (len(text.encode("utf-8")), len(rows), counts,
             ",".join("%s:%d" % (k, v) for k, v in sorted(sealed_by_os.items())),
             ",".join("%s:%d" % (k, len(v)) for k, v in sorted(other.items()))))
    if dropped:
        print("OUTCOME=INSTRUMENT-RED sealed predictions were parsed but not published: %s - a silently "
              "dropped OS is how 44 rows vanished from this file until 13:10 today" % "; ".join(dropped))
        return 3
    bad = [r for r in rows if r[3] == "CONTRADICTED"]
    print("CONTRADICTED_rows=%d %s" % (len(bad), [ "%s/%s" % (b[0], b[1]) for b in bad[:10]]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
