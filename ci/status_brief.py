"""Generate docs/STATUS.md - the one screen of numbers every other document should quote from.

Run:  python ci/status_brief.py

Written because three hand-typed documents in this repository went stale within one hour of each other as
the comparison rules improved. Prose should carry findings and commands; counts belong here, and here they
come from the same verdict artifact the gate emits.
"""
import io
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
VPATH = os.path.join(REPO, "evidence", "S02", "equality-verdict.json")


def main():
    if not os.path.isfile(VPATH):
        print("REFUSING: no verdict artifact; run `python ci/equality.py` first")
        return 3
    v = json.load(io.open(VPATH, encoding="utf-8"))
    if v.get("source_results") != "results":
        print("REFUSING: verdict came from %r, not this repository's results/ face" % v.get("source_results"))
        return 3
    man = json.load(io.open(os.path.join(REPO, "spec", "cells-required.json"), encoding="utf-8"))
    req_total = len(man["required_cells"])
    conflict_cells = sorted({c[0] for c in v["disagreements"]})
    abstain_cells = sorted({c[0] for c in v["channel_abstentions"]})
    cross_cells = sorted({c[0] for c in v["name_cross_form_agreements"]})
    prefix_cells = sorted({c[0] for c in v["prefix_shaped_records"]})
    # the clean set is derived, never remembered: required cells the gate compared and found no conflict in
    compared = v["cells_compared"]
    lines = ["# Status - the numbers, generated", "",
             "From `evidence/S02/equality-verdict.json`, written by `ci/equality.py` at %s; this file is "
             "written by `ci/status_brief.py` at %s. Any other document quoting these counts is stale by "
             "construction - re-run the two commands instead of trusting the prose."
             % (v.get("written_at", "(no timestamp in the artifact)"),
                time.strftime("%Y-%m-%dT%H:%M:%S%z")),
             "",
             "| quantity | value |",
             "|---|---|",
             "| required cells in the contract | %d |" % req_total,
             "| cells run by every port | %d |" % v["cells_run_by_every_port"],
             "| cells the gate compared | %d |" % compared,
             "| cells with no verdict conflict | %d |" % v["cells_with_no_verdict_disagreement"],
             "| conflicting verdict facts | %d (over %d cells) |" % (len(v["disagreements"]), len(conflict_cells)),
             "| probe cells differing (the matrix, not a failure) | %d |" % v["probe_cells_differing"],
             "| cells excluded for different input bytes | %d |" % len(v["unpinned_input"]),
             "| cells excluded for a different path form | %d |" % len(v["cells_excluded"]),
             "| cells with a legality-field abstention | %d |" % len(abstain_cells),
             "| names matched across encodings | %d |" % len(cross_cells),
             "| prefix-shaped name records (flagged, not deleted) | %d |" % len(prefix_cells),
             "| outcome | %s |" % v["outcome"],
             "",
             "## Cells with a verdict conflict (%d)" % len(conflict_cells),
             ""]
    for k in conflict_cells:
        fields = sorted({c[1] for c in v["disagreements"] if c[0] == k})
        lines.append("- `%s` - %s" % (k, ", ".join(fields)))
    lines += ["", "## Field abstentions (a port asked the legality question somewhere else) (%d)"
              % len(abstain_cells), ""]
    for k in abstain_cells:
        who = sorted({p for c in v["channel_abstentions"] if c[0] == k for p in c[2]})
        lines.append("- `%s` - %s" % (k, ", ".join(who)))
    lines += ["", "## What PASS would require", "",
              "Every required cell compared, no port disagreeing on any verdict field, and no field "
              "abstained or unpinned. The gate refuses to report PASS on the intersection: a cell one port "
              "did not answer is a gap, and a cell whose ports asked different layers is not a result.", ""]
    text = "\n".join(lines) + "\n"
    io.open(os.path.join(REPO, "docs", "STATUS.md"), "w", encoding="utf-8", newline="\n").write(text)
    print("wrote docs/STATUS.md bytes=%d conflicts=%d clean=%d/%d abstain=%d"
          % (len(text.encode("utf-8")), len(v["disagreements"]),
             v["cells_with_no_verdict_disagreement"], compared, len(abstain_cells)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
