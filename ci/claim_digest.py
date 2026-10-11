"""Every number quoted in the live prose faces, checked against the thing that measures it.

Run:  python ci/claim_digest.py --scratch-root ../sg-claims [--quick]

Why this leg exists. On 2026-10-11 this seat published four stale numbers in documents that were otherwise
correct: a README that said `lint 18` after the suite had grown to 24, a paragraph that said the parity leg has 8
arms the same afternoon it gained four more, a sentence calling 121 the expanded blank count while the table
beside it summed to 258, and a commit-ahead count that expired at the next commit. Each sentence was true when it
was written, and nothing re-read it afterwards. That is the most ordinary failure in a documentation-heavy
delivery and the first one a reader finds.

What it checks, and what it refuses to claim:
  - kind `gate`    - a quoted number must equal the gate artifact's value right now;
  - kind `arms`    - an arm count in prose must equal what that suite prints when run with --selftest, asked of
                     the suite rather than read out of a constant that can drift from its own labels;
  - kind `parity`  - the number of faces the cold-clone leg compares, derived from `refresh_all.GEN`;
  - kind `history` - a quote that is *about a past reading* (the morning clone read 0 where the working copy read
                     4) is asserted to still contain its historical number and is NOT compared with live values.
                     Excluded with the reason printed, because a gate that flags those lines is a gate that gets
                     ignored - and this repository has already been warned that a blanket clause reading its own
                     text is unsatisfiable.
  - Coverage is published, not assumed: every `arms=<N>` and every known-gate-key quote in the scanned faces is
    counted, and the ones the table does not reach are reported as `not_reached_by_table=` instead of passing
    quietly. A table with no coverage number is the same silence this project spent all day subtracting.

Exit codes: 0 = every declared claim agrees with its source; 1 = a quote is stale or its anchor vanished;
3 = instrument failure (missing artifact, missing face, a suite that prints no arm count, an unusable scratch
root) - a claim that could not be measured is never a pass.
"""
import argparse
import io
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
VPATH = os.path.join(REPO, "evidence", "S02", "equality-verdict.json")

# A closed list, so an auditor can see which tree the claims were checked in. Generated faces are NOT in it: they
# are produced from the artifact and cannot be stale, and scanning them would flag the gate's own output.
LIVE_FACES = ["README.md", "docs/claim-boundary.md", "docs/whitepaper.md"]
GENERATED_FACES = ["docs/STATUS.md", "docs/coverage.md", "docs/evidence.md", "docs/delivery-form.md",
                  "docs/matrix.md", "docs/spec-drift.md", "docs/cell-validation.md", "docs/expected-summary.md",
                  "docs/acceptance-S02.md", "docs/GAP.md", "docs/tapi.md"]

# (id, face, regex with one group, kind, source)
CLAIMS = [
    ("readme-arms-selftest", "README.md", r"self-test (\d+) arms", "arms", "ci/selftest.py"),
    ("readme-arms-lint", "README.md", r", lint (\d+),", "arms", "ci/lint.py"),
    ("readme-arms-conformance", "README.md", r"cell conformance (\d+),", "arms", "ci/validate_cells.py"),
    ("readme-arms-specdrift", "README.md", r"spec-drift (\d+),", "arms", "ci/spec_drift.py"),
    ("readme-arms-delivery", "README.md", r"delivery\s*\n?\s*form (\d+)", "arms", "ci/delivery_form.py"),
    ("readme-arms-coverage", "README.md", r"runs its own (\d+) arms", "arms", "ci/coverage_report.py"),
    ("readme-arms-parity", "README.md", r"own arms are (\d+), both-sided", "arms", "ci/clone_parity.py"),
    ("readme-parity-faces", "README.md", r"faces_compared=(\d+)", "parity", "refresh_all.GEN"),
    ("boundary-blank-rows", "docs/claim-boundary.md", r"(\d+) field-cells blank in at least one port",
     "gate", "verdict_not_recorded_pairs"),
    ("boundary-fully-recorded", "docs/claim-boundary.md", r"only (\d+) of the 24 have every one",
     "gate", "cells_fully_count"),
    ("wp-arms-delivery", "docs/whitepaper.md", r"arms=(\d+) passed=\d+", "arms", "ci/delivery_form.py"),
    ("wp-blank-rows", "docs/whitepaper.md", r"verdict_not_recorded_pairs=(\d+)", "gate",
     "verdict_not_recorded_pairs"),
    ("wp-fully-recorded", "docs/whitepaper.md", r"cells_fully_recorded_and_identical=(\d+)", "gate",
     "cells_fully_count"),
    ("boundary-historical-zero", "docs/claim-boundary.md",
     r"cold clone read `cells_fully_recorded_and_identical=(\d+)`", "history",
     "the morning clone reading of a lane's faces before they landed - a record, not a live claim"),
]

GATE_KEYS = ["verdict_disagreements", "verdict_not_recorded_pairs", "required_cells_missing",
             "cells_fully_recorded_and_identical",
             "cells_compared", "channel_abstentions", "probe_cells_differing", "truncated_values",
             "unpinned_input", "cells_excluded"]


def validate_scratch(raw):
    if not raw:
        return None, "no --scratch-root given; the suites write fixtures and the caller names the place"
    p = os.path.abspath(raw)
    if len(p) == 3 and p[1:2] == ":":
        return None, "--scratch-root %s is a drive root" % raw
    np = os.path.normpath(p)
    if np == os.path.normpath(REPO) or np.startswith(os.path.normpath(REPO) + os.sep):
        return None, "--scratch-root %s is inside the repository, where fixtures would become faces" % raw
    return p, ""


def artifact_values(path):
    """The gate's own numbers, plus the two derived counts the prose quotes."""
    doc = json.load(io.open(path, encoding="utf-8"))
    if doc.get("source_results") != "results":
        return None, "artifact was written from %r, not this repository's results/ face" % doc.get("source_results")
    vals = {}
    for k, v in doc.items():
        if isinstance(v, bool):
            continue
        if isinstance(v, int):
            vals[k] = v
        elif isinstance(v, list):
            # several of the gate's quantities are published as the list itself; the count the prose quotes is
            # its length, and reading the wrong one would quote a number that never appeared anywhere
            vals[k] = len(v)
    for key in ("verdict_disagreements", "verdict_not_recorded_pairs", "cells_compared"):
        if key not in vals:
            return None, "artifact does not carry `%s`, so a quote of it cannot be checked" % key
    full = doc.get("cells_every_port_recorded_every_verdict_field")
    if full is None:
        return None, "artifact carries no fully-recorded cell list, so `cells_fully_count` cannot be derived"
    vals["cells_fully_count"] = len(full)
    import refresh_all
    vals["refresh_all.GEN"] = len(refresh_all.GEN) + 1  # + the verdict artifact the clone leg also compares
    return vals, ""


def suite_arms(script, scratch):
    """Ask the suite how many arms it has, by running it."""
    args = [sys.executable, os.path.join(REPO, script), "--selftest"]
    if script.endswith("selftest.py"):
        args += ["--scratch-root", scratch]
    if script.endswith("lint.py"):
        args += ["--repo-root", REPO]
    p = subprocess.run(args, cwd=REPO, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", shell=False)
    for line in (p.stdout or "").splitlines():
        m = re.search(r"arms=(\d+)", line)
        if m:
            return int(m.group(1)), ""
    return None, "%s printed no `arms=` line (rc=%d), so its count cannot be checked" % (script, p.returncode)


def read_faces(faces):
    texts, missing = {}, []
    for face in faces:
        p = os.path.join(REPO, face.replace("/", os.sep))
        if not os.path.isfile(p):
            missing.append(face)
            continue
        texts[face] = io.open(p, encoding="utf-8", newline="\n").read()
    return texts, missing


def check_claims(values, arms_cache, texts):
    """The production check. `texts` is the in-memory face table so the arms can drive this same function.

    Returns (checked, excluded, findings, instrument, spans) where `spans` is the (face, start, end) of every
    sentence a claim anchored to - coverage is measured against those spans, because subtracting the number of
    claims from the number of quotes counted two different things and called the difference coverage.
    """
    checked, excluded, findings, instrument, spans = 0, 0, [], [], []
    for cid, face, pat, kind, src in CLAIMS:
        text = texts.get(face)
        if text is None:
            instrument.append("%s: the face %s this claim lives in was not readable" % (cid, face))
            continue
        m = re.search(pat, text)
        if not m:
            findings.append("%s: the sentence this claim anchors to is GONE from %s (pattern %r) - a quote that "
                            "vanishes is stale in the worse direction, because nobody is left contradicting it"
                            % (cid, face, pat))
            continue
        spans.append((face, m.start(1), m.end(1)))
        got = int(m.group(1))
        if kind == "history":
            excluded += 1
            continue
        if kind == "arms":
            if src not in arms_cache:
                n, why = suite_arms(src, arms_cache.get("__scratch__"))
                if n is None:
                    instrument.append("%s: %s" % (cid, why))
                    continue
                arms_cache[src] = n
            want = arms_cache[src]
        else:
            want = values.get(src)
            if want is None:
                instrument.append("%s: nothing in the measured sources carries `%s`" % (cid, src))
                continue
        checked += 1
        if got != want:
            findings.append("%s: %s quotes `%s` as %d and the source says %d" % (cid, face, src, got, want))
    return checked, excluded, findings, instrument, spans


QUOTE_PATTERNS = [r"arms[= ](\d+)", r"(\d+) arms"] + [k + r"=(\d+)" for k in GATE_KEYS]


def quote_coverage(texts, spans):
    """How many number-quotes the scanned faces carry, and how many of them no claim reaches.

    Both `arms=7` and `21 arms` are counted because the prose uses both orders, and a coverage count that missed
    one of them would quietly report a smaller denominator than the documents actually carry.
    """
    hit = 0
    unreached = 0
    examples = []
    for face, text in texts.items():
        covered = [(a, b) for f, a, b in spans if f == face]
        for pat in QUOTE_PATTERNS:
            for m in re.finditer(pat, text):
                hit += 1
                if any(a <= m.start(1) < b or a < m.end(1) <= b or (m.start(1) <= a and b <= m.end(1))
                       for a, b in covered):
                    continue
                unreached += 1
                line = text[:m.start()].count("\n") + 1
                excerpt = text.splitlines()[line - 1].strip()[:90]
                examples.append("%s:%d %s" % (face, line, excerpt))
    return hit, unreached, examples


SELFTEST_ARMS = 6


def selftest():
    errs = []

    def chk(cond, msg):
        if not cond:
            errs.append(msg)

    values = {"verdict_not_recorded_pairs": 121, "cells_fully_count": 4, "refresh_all.GEN": 12}
    saved = list(CLAIMS)
    try:
        CLAIMS[:] = [("t", "x.md", r"arms are (\d+)", "arms", "ci/x.py")]
        c, ex, f, i, _sp = check_claims(values, {"__scratch__": "s", "ci/x.py": 7}, {"x.md": "own arms are 7"})
        chk(c == 1 and not f and not i,
            "selftest A1 green: a quote equal to its suite's count must verify, got %r" % ((c, ex, f, i),))
        CLAIMS[:] = [("t", "x.md", r"arms are (\d+)", "arms", "ci/x.py")]
        _c, _e, f2, _i, _sp = check_claims(values, {"__scratch__": "s", "ci/x.py": 12},
                                          {"x.md": "own arms are 7"})
        chk(len(f2) == 1 and "7" in f2[0] and "12" in f2[0],
            "selftest A2 red: a quote of 7 where the suite now prints 12 must name both numbers, got %r" % (f2,))
        CLAIMS[:] = [("t", "x.md", r"arms are (\d+)", "arms", "ci/x.py")]
        _c, _e, f3, _i, _sp = check_claims(values, {"__scratch__": "s"}, {"x.md": "no such sentence anymore"})
        chk(len(f3) == 1 and "GONE" in f3[0],
            "selftest A3 red: a vanished anchor is a finding, never a silent pass, got %r" % (f3,))
        CLAIMS[:] = [("t", "x.md", r"clone read `k=(\d+)`", "history", "a past reading")]
        _c, e4, f4, _i, _sp = check_claims({"k": 4}, {"__scratch__": "s"}, {"x.md": "clone read `k=0`"})
        chk(e4 == 1 and not f4,
            "selftest A4 green: a declared historical quote is excluded with its reason and not compared to the "
            "live value (which here is 4 while the record says 0), got excluded=%d findings=%r" % (e4, f4))
        CLAIMS[:] = [("t", "x.md", r"arms are (\d+)", "arms", "ci/silent.py")]
        def silent(script, scratch):
            return None, "%s printed no `arms=` line (rc=0), so its count cannot be checked" % script
        real = globals()["suite_arms"]
        globals()["suite_arms"] = silent
        try:
            _c, _e, _f, i5, _sp = check_claims(values, {"__scratch__": "s"}, {"x.md": "arms are 3"})
        finally:
            globals()["suite_arms"] = real
        chk(len(i5) == 1 and "arms=" in i5[0],
            "selftest A5 red: a suite that prints no arm count is an instrument failure, not a zero, got %r"
            % (i5,))
    finally:
        CLAIMS[:] = saved
    for bad in ("", "D:\\", os.path.join(REPO, "ci")):
        chk(validate_scratch(bad)[0] is None,
            "selftest A6 red: refused scratch root %r" % (bad,))
    good, _w = validate_scratch(os.path.join(os.environ.get("TEMP", "/tmp"), "sg-claims"))
    chk(good is not None, "selftest A6 green: a caller-named directory outside the repository is accepted")
    text = "self-test 21 arms, cells_compared=44 and verdict_disagreements=54"
    CLAIMS[:] = [("c1", "x.md", r"self-test (\d+) arms", "gate", "cells_compared"),
                 ("c2", "x.md", r"cells_compared=(\d+)", "gate", "cells_compared")]
    _c, _e, _f, _i, sp = check_claims(values, {"__scratch__": "s"}, {"x.md": text})
    total, unreached, _ex = quote_coverage({"x.md": text}, sp)
    chk(total == 3 and unreached == 1,
        "selftest A6 green: coverage counts every quote the face carries in either word order (`21 arms` and the "
        "two `key=` quotes) and must name the one no claim reaches, got total=%d unreached=%d" % (total,
                                                                                                  unreached))
    return errs


def main(argv=None):
    ap = argparse.ArgumentParser(description="check the numbers quoted in the live prose faces")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--scratch-root", default=None)
    ap.add_argument("--quick", action="store_true",
                    help="skip running the suites; arm-count claims are then reported as unchecked")
    ns = ap.parse_args(argv)
    if ns.selftest:
        errs = selftest()
        for e in errs:
            print("SELFTEST-FAIL: %s" % e)
        print("arms=%d passed=%d" % (SELFTEST_ARMS, SELFTEST_ARMS - len(errs)))
        return 1 if errs else 0

    scratch, why = validate_scratch(ns.scratch_root)
    if not scratch:
        print("OUTCOME=INSTRUMENT-RED %s" % why)
        return 3
    if not os.path.isfile(VPATH):
        print("OUTCOME=INSTRUMENT-RED no gate artifact at %s - run `python ci/equality.py` first" % VPATH)
        return 3
    values, why = artifact_values(VPATH)
    if values is None:
        print("OUTCOME=INSTRUMENT-RED %s" % why)
        return 3

    arms_cache = {"__scratch__": scratch}
    if ns.quick:
        skipped = len([c for c in CLAIMS if c[3] == "arms"])
        print("quick| %d arm-count claims left unchecked (mode --quick); run without it before publishing prose"
              % skipped)
        CLAIMS[:] = [c for c in CLAIMS if c[3] != "arms"]

    texts, missing = read_faces(LIVE_FACES)
    instrument = ["live face %s is missing" % m for m in missing]
    checked, excluded, findings, instr2, spans = check_claims(values, arms_cache, texts)
    instrument += instr2
    total, unreached, examples = quote_coverage(texts, spans)

    for x in instrument:
        print("  instrument| %s" % x)
    for f in findings:
        print("  stale| %s" % f)
    for e in examples[:8]:
        print("  unreached| %s" % e)
    if len(examples) > 8:
        print("  unreached| TRUNCATED shown=8 total=%d" % len(examples))
    print("claims=%d verified=%d history_excluded=%d quotes_in_faces=%d not_reached_by_table=%d faces=%s "
          "generated_excluded=%d"
          % (len(CLAIMS), checked, excluded, total, unreached, ",".join(sorted(texts)), len(GENERATED_FACES)))
    if instrument:
        print("OUTCOME=INSTRUMENT-RED a claim that could not be measured is not a pass")
        return 3
    if findings:
        print("OUTCOME=RED stale_claims=%d" % len(findings))
        return 1
    # a partial check must not read as a pass: quick mode skips the arm counts, and says so on the verdict line
    print("OUTCOME=CLEAN stale_claims=0 coverage=%s"
          % ("partial(arm-count-claims-unchecked)" if ns.quick else "full"))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        print("OUTCOME=INSTRUMENT-RED %s: a crash is not a measurement" % type(e).__name__)
        sys.exit(3)
