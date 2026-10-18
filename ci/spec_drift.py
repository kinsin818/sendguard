"""Does the spec fingerprint a compared cell carries actually change the question that cell was asked?

Run:  python ci/spec_drift.py            # writes docs/spec-drift.md
      python ci/spec_drift.py --selftest # 15 arms, both edges

Why this leg exists. Measured 2026-10-11 12:40 over the canonical faces: the cells the equality gate compares
are stamped with more than one `spec/cases.yaml` fingerprint - most carry the current one (8650a186) while one
port's trap / blind / T-API cells carry the previous one (b1eb629c, the face committed at 05:05, before the
06:11 re-seal that added `len_fill`). Nothing in the pipeline had looked at that field, so "one frozen spec"
was being asserted from the manifest header instead of checked against the records. The exact counts are this
leg's output, not its docstring.

Which records are compared is read out of the gate's own artifact (`compared_records`), not re-derived here: a
first cut of this leg counted 291 records against the gate's 264 cells, because choosing which of a port's
duplicate representations stands for a cell is the gate's rule, and a second implementation of that rule is
the two-rulers defect this project keeps catching in itself. The digest recipe is likewise single-sourced from
`ci/blobhash.py` (over the committed blob face, never the checkout).

What the leg decides, per older fingerprint:

1. locate the commit whose `spec/cases.yaml` blob hashes to it;
2. diff that face against HEAD's and collect every case id the delta touches - ids named literally on a line
   that differs, plus ids named by an `applies_to:` list in a block that appeared or vanished;
3. intersect with the ids of the cells recorded under that older fingerprint.

Empty intersection => the drift is disclosed as harmless *by measurement*. Non-empty => those cells were asked
a different question than the one they are compared against, and the leg exits 1 so the refusal lands in the
pipeline rather than in prose. A missing artifact, an unstamped record, a digest no committed face produces, or
a crash exits 3 - instrument failure is never a measurement, and rc=1 belongs to "a cell must be re-run".
"""
import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import blobhash  # noqa: E402  - the repository's one digest recipe, over the committed blob face

SPEC_FILE = "spec/cases.yaml"
VPATH = os.path.join(REPO, "evidence", "judgement", "equality-verdict.json")
CASE_ID_RE = re.compile(r"\b(T\d{2}(?:-m\d+)?|B\d|T-CTRL-[A-Z]+|T-API)\b")


def face(commit):
    """The committed bytes of spec/cases.yaml at `commit`, or None if git cannot produce them.

    `blobhash.blob` raises SystemExit on a missing face; that is a measurement problem, not an answer, so it
    is converted here rather than allowed to reach the top-level wrapper as a bare exit.
    """
    try:
        return blobhash.blob(SPEC_FILE, commit)
    except SystemExit:
        return None
    except Exception:
        return None


def digest_of(commit):
    b = face(commit)
    return None if b is None else hashlib.sha256(b).hexdigest()


def run_git(args):
    p = subprocess.run(["git", "-C", REPO] + args, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return p.returncode, p.stdout or "", p.stderr or ""


def spec_versions():
    """[(digest, commit, byte_size)] for every committed face of spec/cases.yaml, newest first, deduped."""
    rc, out, _ = run_git(["log", "--format=%H", "--", SPEC_FILE])
    if rc != 0:
        return None
    seen, rows = set(), []
    for h in out.split():
        b = face(h)
        if b is None:
            return None
        d = hashlib.sha256(b).hexdigest()
        if d in seen:
            continue
        seen.add(d)
        _, size, _ = run_git(["cat-file", "-s", "%s:%s" % (h, SPEC_FILE)])
        rows.append((d, h, (size or "").strip()))
    return rows


def enclosing_id(lines, index):
    """The case id a line belongs to: the nearest preceding `id:` in the same block.

    Found while writing arm A3, which failed against the first version of this function: a spec case is a
    block, so a change to `name:` two lines under `- id: T01` changes T01's question while naming no id on
    the changed line. Reading only the changed line is under-inclusion, which is the direction that lets a
    changed question pass as the same question.
    """
    for i in range(index, -1, -1):
        m = re.search(r"^\s*(?:-\s*)?id:\s*([A-Za-z0-9_.-]+)", lines[i])
        if m:
            return m.group(1)
        if re.match(r"^[^ \t-]", lines[i]):      # a new top-level key ends any case block
            return None
    return None


def changed_ranges(old_lines, new_lines):
    """Index ranges that differ, on both sides - positions matter, so a Counter diff is not enough."""
    import difflib
    out = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, old_lines, new_lines).get_opcodes():
        if tag == "equal":
            continue
        out.append((i1, i2, j1, j2))
    return out


def touched_case_ids(old_text, new_text):
    """Case ids the delta between two spec faces reaches.

    Wide on purpose: for every differing line this takes the id written literally on it, the id of the block
    that contains it on each side, and any `applies_to:` list on it. Over-inclusion flags a cell for
    re-running when the delta may not really have reached it, which is the safe direction.
    """
    old_lines, new_lines = old_text.splitlines(), new_text.splitlines()
    ids = set()
    for i1, i2, j1, j2 in changed_ranges(old_lines, new_lines):
        for side, lo, hi in ((old_lines, i1, i2), (new_lines, j1, j2)):
            for n in range(lo, hi):
                line = side[n]
                if not line.strip():
                    continue
                ids.update(CASE_ID_RE.findall(line))
                for block in re.findall(r"applies_to:\s*\[([^\]]*)\]", line):
                    ids.update(x for x in re.findall(r"[A-Za-z0-9_.-]+", block))
                eid = enclosing_id(side, n)
                if eid:
                    ids.update(CASE_ID_RE.findall(eid) or [eid])
    return ids


def compared_records():
    """[(port, cell_key, digest)] from the gate's own artifact - this leg does not re-select cells."""
    if not os.path.isfile(VPATH):
        return None, "no verdict artifact; run `python ci/equality.py` first"
    v = json.load(io.open(VPATH, encoding="utf-8"))
    if v.get("source_results") != "results":
        return None, "verdict came from %r, not this repository's results/ face" % v.get("source_results")
    rows = v.get("compared_records")
    if rows is None:
        return None, ("the artifact predates `compared_records`; re-run `python ci/equality.py` so this leg "
                      "reads the gate's selection instead of inventing a second one")
    return [(p, k, d) for p, k, d in rows], None


def text_face(commit):
    b = face(commit)
    return None if b is None else b.decode("utf-8", errors="replace")


def assess(rows, versions, current_digest, head_face, reader=None):
    """[(digest, holders, touched_ids_or_None, affected_holders)] for every non-current fingerprint.

    `reader` exists so the arms can feed this function two synthetic spec faces; without it the leg reads the
    repository's own history. A leg whose fixtures cannot reach the same code path the real run uses is not
    tested, it is decorated.
    """
    reader = reader or text_face
    out = []
    texts = {}
    for dig in sorted({r[2] for r in rows}):
        if dig == current_digest:
            continue
        holders = [(p, k) for p, k, d in rows if d == dig]
        commit = next((v[1] for v in versions if v[0] == dig), None)
        if commit is None:
            out.append((dig, holders, None, None))
            continue
        if dig not in texts:
            texts[dig] = reader(commit)
        old = texts.get(dig)
        if old is None or head_face is None:
            out.append((dig, holders, None, None))
            continue
        touched = touched_case_ids(old, head_face)
        affected = [(p, k) for p, k in holders if set(CASE_ID_RE.findall(k)) & touched]
        out.append((dig, holders, sorted(touched), affected))
    return out


def selftest():
    errs = []

    def chk(cond, msg):
        if not cond:
            errs.append(msg)

    old = "cases:\n  - id: T01\n    name: CON.txt\n  - id: T04\n    name: trail.\n"
    new = old + "len_fill:\n  applies_to: [T17, T18]\n  unit_hex: \"61\"\n"
    t = touched_case_ids(old, new)
    chk("T17" in t and "T18" in t,
        "selftest A1 red: an added block with applies_to must name the cases it governs, got %r" % (t,))
    chk("T01" not in t and "T04" not in t,
        "selftest A2 green: an unchanged line must not put its case id into the delta")
    t2 = touched_case_ids(old, old.replace("name: CON.txt", "name: CON"))
    chk("T01" in t2 and "T17" not in t2,
        "selftest A3 red: a changed case must be caught and its neighbours left alone")
    chk(touched_case_ids(old, old) == set(), "selftest A4 green: identical faces touch nothing")

    rows = [("python", "trap/T01", "a" * 64), ("python", "len/T17[base_len=78,path_form=plain]", "b" * 64)]
    res = assess(rows, [("z" * 64, "HEAD")], "c" * 64, old)
    chk(len(res) == 2, "selftest A5 red: every non-current fingerprint is assessed, not just the first")
    chk(all(r[2] is None and r[3] is None for r in res),
        "selftest A6 red: a digest no committed face produces is instrument-blocked, never a clean answer")
    res = assess([("python", "trap/T01", "d" * 64)], [("d" * 64, "HEAD")], "c" * 64, old,
                 reader=lambda c: old)
    chk(res and res[0][2] == [] and res[0][3] == [],
        "selftest A7 green: a face identical to HEAD touches no case id, so nothing is flagged")
    changed = old.replace("    name: CON.txt", "    name: CON")
    res = assess([("python", "trap/T01", "e" * 64), ("python", "trap/T04", "e" * 64)],
                 [("e" * 64, "HEAD")], "c" * 64, changed, reader=lambda c: old)
    chk(res and sorted(res[0][3]) == [("python", "trap/T01")],
        "selftest A8 red: a delta that rewrites T01's case must flag exactly that cell and leave T04 alone, "
        "got %r" % (res[0][3] if res else None,))
    chk(assess([("go", "trap/T01", "c" * 64)], [("c" * 64, "HEAD")], "c" * 64, old) == [],
        "selftest A9 green: records on the current fingerprint produce no drift row at all")

    rc, _out, _err = run_git(["rev-parse", "--git-dir"])
    chk(rc == 0, "selftest A10 green: git must be reachable or this leg means nothing (rc=%d)" % rc)
    chk(face("definitely-not-a-commit-xyz") is None and digest_of("definitely-not-a-commit-xyz") is None,
        "selftest A11 red: an unknown commit yields no digest, not the digest of an empty file")
    v = spec_versions()
    chk(v is not None and len(v) >= 1 and all(len(d) == 64 for d, _, _ in v),
        "selftest A12 green: the version table parses (%s faces)" % (len(v) if v else "None"))
    cur = json.load(io.open(os.path.join(REPO, "spec", "cells-required.json"), encoding="utf-8"))["spec_blob_sha256"]
    chk(any(d == cur for d, _, _ in (v or [])),
        "selftest A13 red: the manifest's current digest must be one of the committed faces, or the manifest "
        "itself is stale")
    found = CASE_ID_RE.findall("trap/T14-m1 blind/B3 ctrl T-CTRL-PARSE tapi T-API")
    chk(found == ["T14-m1", "B3", "T-CTRL-PARSE", "T-API"],
        "selftest A14 green: the id pattern reads a member id whole, plus blind, control and tapi ids, got %r"
        % (found,))
    chk(CASE_ID_RE.findall("len/T17[base_len=78,path_form=plain]") == ["T17"]
        and CASE_ID_RE.findall("trap/T09-m2[member=2]") == ["T09-m2"],
        "selftest A15 green: a cell key in the gate's own format yields its case id, member included")
    return errs


def main():
    ap = argparse.ArgumentParser(description="spec fingerprint drift over the cells that are compared")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        errs = selftest()
        for e in errs:
            print("SELFTEST-FAIL: %s" % e)
        print("arms=15 passed=%d" % (15 - len(errs)))
        return 1 if errs else 0

    manifest = json.load(io.open(os.path.join(REPO, "spec", "cells-required.json"), encoding="utf-8"))
    current = manifest["spec_blob_sha256"]
    rows, why = compared_records()
    if why:
        print("OUTCOME=INSTRUMENT-RED %s" % why)
        return 3
    versions = spec_versions()
    if versions is None:
        print("OUTCOME=INSTRUMENT-RED git could not read the %s history - this leg refuses to guess" % SPEC_FILE)
        return 3
    hb = face("HEAD")
    if hb is None:
        print("OUTCOME=INSTRUMENT-RED HEAD carries no %s face" % SPEC_FILE)
        return 3
    head_face = hb.decode("utf-8", errors="replace")
    current_count = sum(1 for r in rows if r[2] == current)
    absent = [r for r in rows if r[2] == "ABSENT"]
    res = assess(rows, versions, current, head_face)
    affected = [(dig, h) for dig, holders, touched, aff in res for h in (aff or [])]
    unresolvable = [dig for dig, holders, touched, aff in res if touched is None]
    older = len(rows) - current_count - len(absent)

    lines = ["# Spec fingerprint drift over the cells that are compared", "",
             "Generated by `ci/spec_drift.py` at %s. The fingerprint is `sha256(git cat-file blob "
             "<commit>:spec/cases.yaml)` - the repository's one digest recipe (`ci/blobhash.py`), which is also "
             "the one the ports stamp their cells with. The list of compared cells is read from "
             "`evidence/judgement/equality-verdict.json`, i.e. from the gate's own selection."
             % time.strftime("%Y-%m-%d %H:%M:%S %z"), "",
             "| quantity | value |", "|---|---|",
             "| cell records the gate compares | %d |" % len(rows),
             "| stamped with the manifest's current fingerprint | %d |" % current_count,
             "| stamped with an older fingerprint | %d |" % older,
             "| stamped with **no** fingerprint | %d |" % len(absent),
             "| distinct older fingerprints | %d |" % len(res),
             "| of those, ones no committed face produces | %d |" % len(unresolvable),
             "| **compared cells whose case id the delta actually touched** | %d |" % len(affected), ""]
    if absent:
        lines += ["**%d compared records carry no `spec_sha256` at all**, which is worse than a stale one: "
                  "there is no claim about the rules they were asked under. Named: %s."
                  % (len(absent), ", ".join("`%s/%s`" % (p, k) for p, k, _ in sorted(absent))), ""]
    lines += ["## Per older fingerprint", ""]
    if not res:
        lines += ["Every compared record carries the current fingerprint. Nothing to assess.", ""]
    for dig, holders, touched, aff in res:
        commit = next((v[1] for v in versions if v[0] == dig), None)
        ports = sorted({h[0] for h in holders})
        lines += ["### `%s` - %d records, held by %s" % (dig[:12], len(holders), ", ".join(ports)), ""]
        if commit is None or touched is None:
            lines += ["**INSTRUMENT-BLOCKED**: no committed `spec/cases.yaml` face produces this digest, so the "
                      "delta cannot be computed. These records are not cleared - treat them as unverified until "
                      "the port re-stamps.**", ""]
            continue
        size = next((v[2] for v in versions if v[0] == dig), "?")
        lines += ["- committed face: `%s` (%s bytes)" % (commit[:7], size),
                  "- case ids the delta between that face and HEAD touches: %s"
                  % (", ".join("`%s`" % x for x in touched) or "(none)"),
                  "- cells recorded under it: %s" % ", ".join(sorted("`%s/%s`" % (p, k) for p, k in holders)),
                  "- **asked a question the delta changed: %d**%s"
                  % (len(aff or []), "" if aff else " - the delta did not reach these cells"), ""]
    lines += ["## What this does and does not license", "",
              "- It licenses this sentence and no stronger: *the compared records that carry an older "
              "fingerprint were asked questions whose spec text is unchanged between that fingerprint and "
              "HEAD.* That is a measurement of the delta, not a promise about the port's harness.",
              "- It does not license comparing a record whose case id the delta touched. Those are named above, "
              "and the leg exits 1 for exactly that case, so the refusal is in the pipeline rather than in "
              "prose.",
              "- It does not repair the habit. A port that does not re-run after a re-seal leaves a tree with "
              "mixed fingerprints; the fix is a re-stamp of the cells the delta touches, which is cheap and is "
              "the port's own work, not this machine's.",
              "- A record with no fingerprint is its own row: absence of a claim is not a claim of agreement, "
              "and this leg does not convert one into the other.", ""]
    text = "\n".join(lines) + "\n"
    io.open(os.path.join(REPO, "docs", "spec-drift.md"), "w", encoding="utf-8", newline="\n").write(text)
    print("wrote docs/spec-drift.md bytes=%d compared=%d current=%d older=%d unstamped=%d "
          "older_unresolvable=%d affected_by_delta=%d"
          % (len(text.encode("utf-8")), len(rows), current_count, older, len(absent),
             len(unresolvable), len(affected)))
    if unresolvable or absent:
        print("OUTCOME=INSTRUMENT-RED unstamped or unresolvable fingerprints: %s"
              % ", ".join(["`%s`" % d[:12] for d in unresolvable]
                          + (["ABSENT x%d" % len(absent)] if absent else [])))
        return 3
    if affected:
        print("OUTCOME=RED cells recorded under an older fingerprint were asked a question the delta changed: %s"
              % ", ".join(sorted("%s/%s" % (p, k) for _, (p, k) in affected)))
        return 1
    print("OUTCOME=CLEAN drift_reached_compared_cells=0 (older fingerprints disclosed above, %d records)"
          % older)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:  # a crash must not read as rc=1 = "a cell must be re-run"
        import traceback
        traceback.print_exc()
        print("OUTCOME=INSTRUMENT-RED %s: a crash is not a measurement" % type(e).__name__)
        sys.exit(3)
