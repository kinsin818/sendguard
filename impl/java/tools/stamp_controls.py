#!/usr/bin/env python3
"""Stamp `control_pass` onto this port's five control cells, judged from the readings ALREADY on the
disk. Ticket SG-F2 part 2.

No child process and no re-measurement: for each `ctrl` cell this tool takes the recorded fields,
runs the criterion impl/java/tools/selfcheck.py already prints (the table quoted from
evidence/S00-ctrl-baseline.md), and writes the verdict plus the command that reproduces the
judgement. Without --apply it changes nothing.

Why it exists: docs/acceptance-S02.md reads `pass (1/5 stamped)` for java while every other port
reads 5/5. Four cells carry no calibration result, so this port's own instrument claim cannot be
read back by a stranger.

Exit codes - a number outside this set is an instrument failure, never a measurement:
    0  every control judged and, with --apply, every passing cell stamped
    1  at least one control does NOT satisfy its criterion (a finding: the stamp says false)
    3  refused: stale cell, face this tool did not write, unpinned input, non-ctrl cell, no such file

The refusal paths are exercised by --selftest, which must see each one fire AND must see the pass
path able to say yes.
"""
import argparse
import contextlib
import datetime
import glob
import hashlib
import io
import json
import os
import re
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(PORT))
RESULTS = os.path.join(REPO, "results", "java.windows.x64")
SCRATCH = "D:\\s\\"
TOOL = "impl/java/tools/stamp_controls.py"
COMMAND = "python " + TOOL
CONTROL_IDS = ["T-CTRL-ASCII", "T-CTRL-PARSE", "T-CTRL-ILLEGAL-CHAR",
               "T-CTRL-NAMETOOLONG", "T-CTRL-CANON"]

# Which half of a quoted expectation this port cannot surface, and what it surfaced instead. Naming
# the gap is the point; smoothing it over would make the stamp a claim the cell cannot support.
PARTIAL_NOTES = {
    "T-CTRL-ILLEGAL-CHAR":
        "the expectation names winerror=123 and this port cannot surface a winerror at all: Java "
        "exposes no accessor for it, measured by reflection at impl/java/src/CellProbe.java:711 "
        "winErrorOf(), whose result is printed in the sibling control cell "
        "ctrl__T-CTRL-NAMETOOLONG.json as winerror=null(unavailable: "
        "NoSuchMethodException: java.nio.file.FileSystemException.getWinError()). That tag is NOT in "
        "this cell, because this cell's entry refused at parse and never raised a "
        "FileSystemException. What this port does surface is the OS refusing the same name once the "
        "language path parser is bypassed - os_legality_probe.instrument "
        "= java.io.FileOutputStream(java.io.File(String)) with the \\\\?\\ prefix answered "
        "create_result=err_at_syscall, error_class=java.io.FileNotFoundException, "
        "landed_by_enumeration=false, and that is the source of os_legality_verdict=illegal. The "
        "halves the criterion tests hold; the winerror half is recorded as unobservable, not counted.",
    "T-CTRL-PARSE":
        "the expectation's second half is cross-port ('all 6 langs MUST be err-at-parse'); this tool "
        "can only judge this port's own record, where create_result=err_at_parse and "
        "error_stage=parse hold. The cross-port half belongs to ci/equality.py, not to a stamp this "
        "window is entitled to give.",
    "T-CTRL-NAMETOOLONG":
        "error_stage reads 'fs' where the S00 node-table layer said 'syscall'; the criterion accepts "
        "either because both mean the call reached the filesystem, and the difference is this port's "
        "exception taxonomy (java.nio.file.FileSystemException), reported rather than smoothed.",
}


def now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S +0800")


def canonical_bytes(rec):
    return (json.dumps(rec, ensure_ascii=True, indent=1, sort_keys=False) + "\n").encode("utf-8")


def load_pins_and_criteria():
    """The pins and the criteria come from impl/java/tools/selfcheck.py, so this tool has no second
    copy of either - a duplicated criterion is a criterion nobody is bound to."""
    sys.dont_write_bytecode = True   # importing the self-check must not leave a __pycache__ face
    sys.path.insert(0, HERE)
    import selfcheck as S
    return S.pinned_controls(), S.CONTROL_CRITERIA


def judge_canon(cell):
    """T-CTRL-CANON's expectation is 'identical canonical bytes'. selfcheck's lambda for this id
    reads control_pass - the very field being stamped - which is circular, so re-derive the verdict
    from the sha strings the cell recorded instead."""
    a = cell.get("canon_sha256_primary")
    b = cell.get("canon_sha256_second_instrument")
    p = cell.get("canon_payload_sha256")
    agree = bool(a) and a == b and (p is None or p == a)
    sealed = "c9fe45b2fee8ea846f0cf4f2cacc2a891e7b082e7719923502d12a9813e21994"
    return agree, ("sha256_primary=%s second_instrument=%s payload=%s instruments_identical=%s "
                   "equals_sealed_s00_baseline=%s" % (str(a)[:12] + "...", str(b)[:12] + "...",
                                                      str(p)[:12] + "...", agree, p == sealed))


def judge(cid, cell, criteria):
    if cid not in criteria:
        return None, "no criterion quoted for this id in the self-check table", None
    crit = criteria[cid]
    if cid == "T-CTRL-CANON":
        holds, obs = judge_canon(cell)
        return holds, obs, crit["expectation"]
    holds, obs = crit["check"](cell)
    return bool(holds), obs, crit["expectation"]


def process(path, apply_write, sha_blob, pins, criteria):
    fn = os.path.basename(path)
    raw = open(path, "rb").read()
    try:
        cell = json.loads(raw.decode("utf-8"))
    except Exception as e:
        return refuse("UNREADABLE_CELL", "%s: %s" % (type(e).__name__, e))
    cid = cell.get("case_id")
    if cell.get("case_group") != "ctrl":
        return refuse("NOT_CONTROL", "%s has case_group=%r; this tool stamps control cells only"
                      % (fn, cell.get("case_group")))
    if cell.get("language") != "java" or cell.get("os") != "windows":
        return refuse("WRONG_PORT_FACE", "%s claims language=%r os=%r"
                      % (fn, cell.get("language"), cell.get("os")))
    if cell.get("spec_sha256") != sha_blob:
        return refuse("STALE_CELL", "%s cites spec_sha256=%s while the committed blob face is %s; "
                                    "stamping a stale reading would certify an answer to a question "
                                    "the spec no longer asks"
                      % (fn, cell.get("spec_sha256"), sha_blob))
    if raw != canonical_bytes(cell):
        return refuse("NON_CANONICAL_FACE",
                      "%s is not byte-identical to json.dumps(rec, ensure_ascii=True, indent=1, "
                      "sort_keys=False); this tool writes with the driver's own serialisation and "
                      "will not reformat a face it did not produce (on_disk=%d B canonical=%d B)"
                      % (fn, len(raw), len(canonical_bytes(cell))))
    pin = pins.get(cid)
    if pin and pin[0] and cell.get("name_source") != pin[0]:
        return refuse("UNPINNED_INPUT", "%s carries name_source=%r where spec/cases.yaml "
                      "control_samples pins %r" % (fn, cell.get("name_source"), pin[0]))
    holds, obs, rule = judge(cid, cell, criteria)
    if holds is None:
        return refuse("UNJUDGEABLE", "%s: %s" % (fn, obs))
    if holds is False and cell.get("control_pass") is True:
        return refuse("STAMP_CONTRADICTS_RECORDING",
                      "%s already claims control_pass=true, but its own recorded fields do not "
                      "satisfy the criterion (%s). This tool will not flip a verdict that is already "
                      "on the face; the contradiction is the finding and it goes in the report."
                      % (fn, obs))
    added = {
        "control_pass": bool(holds),
        "control_pass_rule": rule,
        "control_pass_observed": obs,
        "control_pass_command": COMMAND + (" --apply" if apply_write else ""),
        "control_pass_tool": TOOL,
        "control_pass_basis": "judged from the fields this cell already recorded; no child process "
                              "was started and no measurement was re-taken for this stamp",
        "control_pass_spec_sha256_face": "committed blob face HEAD:spec/cases.yaml",
    }
    if PARTIAL_NOTES.get(cid):
        added["control_pass_partial"] = PARTIAL_NOTES[cid]
    if not cell.get("control_pass_stamped_at"):
        added["control_pass_stamped_at"] = now()
    merged = dict(cell)
    merged.update(added)
    for k, v in cell.items():
        if merged.get(k) != v:
            return refuse("FIELD_MOVED", "%s: stamping would move %r from %r to %r"
                          % (fn, k, v, merged.get(k)))
    print("JUDGE %-22s %-4s control_pass=%-5s was_already_stamped=%s | %s"
          % (cid, "PASS" if holds else "FAIL", holds, "control_pass" in cell, obs))
    rc = 0 if holds else 1
    if apply_write:
        data = canonical_bytes(merged)
        io.open(path, "wb").write(data)
        back = json.loads(io.open(path, encoding="utf-8").read())
        if back.get("control_pass") != holds:
            print("STAMP-VERIFY-FAIL %s" % fn)
            return 3
        if len(back) != len(merged):
            print("STAMP-SIZE-FAIL %s wrote=%d read_back=%d" % (fn, len(merged), len(back)))
            return 3
        if canonical_bytes(back) != data:
            print("STAMP-ROUNDTRIP-FAIL %s" % fn)
            return 3
        print("STAMPED %-22s %d->%d B keys=%d" % (cid, len(raw), len(data), len(back)))
    return rc


def refuse(why, detail):
    print("REFUSED %s | %s" % (why, detail))
    return 3


def cap(fn, *args, **kw):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = fn(*args, **kw)
    return rc, buf.getvalue()


def selftest(criteria):
    """Red and green arms. Fixtures go to a fresh scratch dir outside the repo; nothing in results/
    is written by this path, and there is no deletion logic so the dir is left where it is."""
    import uuid
    sha_blob = committed_sha()
    pins, _ = load_pins_and_criteria()
    real = {}
    for cid in CONTROL_IDS:
        real[cid] = json.loads(io.open(os.path.join(RESULTS, "ctrl__%s.json" % cid),
                                       encoding="utf-8").read())
    d = os.path.join(SCRATCH.rstrip("\\"), hashlib.md5(os.urandom(8)).hexdigest()[:6],
                     "stamp-selftest-" + uuid.uuid4().hex[:8])
    os.makedirs(d)
    arms, problems = [0], []

    def fixture(cid, mut=None, tag=None):
        rec = json.loads(json.dumps(real[cid]))
        for k, v in (mut or {}).items():
            if v == "__drop__":
                rec.pop(k, None)
            else:
                rec[k] = v
        fn = "ctrl__%s%s.json" % (cid, ("-" + tag) if tag else "")
        p = os.path.join(d, fn)
        io.open(p, "wb").write(canonical_bytes(rec))
        return p

    def arm(label, path, want_rc, want_word=None):
        arms[0] += 1
        rc, text = cap(process, path, False, sha_blob, pins, criteria)
        ok = (rc == want_rc) and (want_word is None or want_word in text)
        if not ok:
            problems.append("%s: rc=%s want=%s word=%r in_output=%s | %s"
                            % (label, rc, want_rc, want_word, want_word in text if want_word else "-",
                               text.strip().splitlines()[:1]))
        print("  arm %-32s rc=%s want=%-2s %s%s"
              % (label, rc, want_rc, "OK" if ok else "PROBLEM",
                 (" refused=" + want_word) if want_word else ""))

    # green: the canon verdict must be re-derivable from the recorded shas, not read off the field
    holds, obs = judge_canon(real["T-CTRL-CANON"])
    if holds is not True:
        problems.append("green canon re-derivation failed: %s" % obs)
    print("  arm %-32s holds=%s %s | %s" % ("green-canon-rederived-not-circular", holds,
                                            "OK" if holds else "PROBLEM", obs))
    # red: same cell with one sha moved and NO stamp on it yet -> the criterion fails (rc=1) and the
    # stamp says false; a failing control must never be able to buy a true
    arm("red-canon-sha-mismatch",
        fixture("T-CTRL-CANON", {"canon_sha256_second_instrument": "0" * 64,
                                 "control_pass": "__drop__"}, "red"), 1, "FAIL")
    # red: the same mismatch on a cell that ALREADY claims true -> refused, not silently rewritten
    arm("red-stamp-contradicts-recording",
        fixture("T-CTRL-CANON", {"canon_sha256_second_instrument": "0" * 64}, "red2"), 3,
        "STAMP_CONTRADICTS_RECORDING")
    # red: a control whose own criterion fails must cost rc=1, not a friendly true
    arm("red-failing-criterion",
        fixture("T-CTRL-ASCII", {"create_result": "err_at_syscall"}, "red"), 1)
    # red: citing a spec face that is not the committed one
    arm("red-stale-cell", fixture("T-CTRL-PARSE", {"spec_sha256": "f" * 64}, "red"), 3, "STALE_CELL")
    # red: a trap cell smuggled in under a ctrl filename
    trap = json.loads(io.open(os.path.join(RESULTS, "trap__T01.json"), encoding="utf-8").read())
    p = os.path.join(d, "ctrl__T-CTRL-SMUGGLED.json")
    io.open(p, "wb").write(canonical_bytes(trap))
    arm("red-non-control-cell", p, 3, "NOT_CONTROL")
    # red: the pinned input bytes were swapped
    arm("red-unpinned-input",
        fixture("T-CTRL-ILLEGAL-CHAR", {"name_source": "00"}, "red"), 3, "UNPINNED_INPUT")
    # red: a hand-formatted face is refused instead of silently reformatted
    rec = json.loads(json.dumps(real["T-CTRL-NAMETOOLONG"]))
    p = os.path.join(d, "ctrl__T-CTRL-HANDFORMATTED.json")
    io.open(p, "w", encoding="utf-8").write(json.dumps(rec, indent=2) + "\n")
    arm("red-hand-formatted-face", p, 3, "NON_CANONICAL_FACE")
    # green: apply, twice, byte-identical, and no recorded field moves
    gp = fixture("T-CTRL-NAMETOOLONG")
    arms[0] += 1
    rc_a, _ = cap(process, gp, True, sha_blob, pins, criteria)
    b1 = open(gp, "rb").read()
    rc_b, _ = cap(process, gp, True, sha_blob, pins, criteria)
    b2 = open(gp, "rb").read()
    back = json.loads(b2.decode("utf-8"))
    moved = [k for k, v in real["T-CTRL-NAMETOOLONG"].items()
             if k != "control_pass" and back.get(k) != v]
    ok = rc_a == 0 and rc_b == 0 and b1 == b2 and back.get("control_pass") is True and not moved
    if not ok:
        problems.append("green apply idempotence: rc_a=%s rc_b=%s bytes_equal=%s pass=%s moved=%s"
                        % (rc_a, rc_b, b1 == b2, back.get("control_pass"), moved))
    print("  arm %-32s rc=%s/%s bytes_equal=%s control_pass=%s moved=%d %s"
          % ("green-apply-idempotent", rc_a, rc_b, b1 == b2, back.get("control_pass"),
             len(moved), "OK" if ok else "PROBLEM"))
    print("arms_checked=%d problems=%d fixtures=%s" % (arms[0], len(problems), d))
    for x in problems:
        print("PROBLEM %s" % x)
    return 1 if problems else 0


def committed_sha():
    r = subprocess.run(["git", "-C", REPO, "cat-file", "blob", "HEAD:spec/cases.yaml"],
                       capture_output=True)
    if r.returncode != 0:
        raise RuntimeError("cannot read the committed spec face: "
                           + r.stderr.decode("utf-8", "replace")[:200])
    return hashlib.sha256(r.stdout).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--cell")
    a = ap.parse_args()
    pins, criteria = load_pins_and_criteria()
    if a.selftest:
        return selftest(criteria)
    sha_blob = committed_sha()
    ids = [a.cell] if a.cell else CONTROL_IDS
    rc = 0
    for cid in ids:
        t = os.path.join(RESULTS, "ctrl__%s.json" % cid)
        if not os.path.isfile(t):
            print("NO_SUCH_CELL %s" % t)
            return 3
        r = process(t, a.apply, sha_blob, pins, criteria)
        if r == 3:
            return 3
        rc = rc or r
    judged = set("ctrl__%s.json" % c for c in ids)
    on_disk = set(os.path.basename(x) for x in glob.glob(os.path.join(RESULTS, "ctrl__*.json")))
    other = sorted(on_disk - judged)
    if other:
        print("NOTE ctrl-named files this run does not judge: %s" % ",".join(other))
    print("spec_face=%s apply=%s targets=%d stamped_true=%s rc=%d"
          % (sha_blob[:12], a.apply, len(ids), "see JUDGE lines", rc))
    return rc


if __name__ == "__main__":
    sys.exit(main())
