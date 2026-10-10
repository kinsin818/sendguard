#!/usr/bin/env python3
"""Generate spec/cells-required.json from the committed spec face.

Deterministic on purpose: the only inputs are `git cat-file blob HEAD:spec/cases.yaml` and the constants
below, and no timestamp is written into the output. If this file and the committed manifest ever disagree,
the manifest is wrong - run this and look.
"""
import hashlib
import io
import json
import os
import re
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BASES = [78, 120, 200]          # reachable root depths; see cell-identity.md section 6
PRIMARY = {
    "python": "open_wb",
    "node": "writeFileSync",
    "typescript": "writeFileSync",
    "go": "os.Create",
    "java": "Files.write",
    "csharp": "File.WriteAllBytes",
    "rust": "std::fs::File::create",
}


def blob(path):
    r = subprocess.run(["git", "cat-file", "blob", "HEAD:" + path], cwd=REPO,
                       capture_output=True, shell=False)
    if r.returncode != 0:
        raise SystemExit("cannot read the committed face of %s (rc=%d): %s"
                         % (path, r.returncode, r.stderr[:200]))
    return r.stdout


def parse(text):
    """cases.yaml shape (rev2/rev3): api_entry map, control_cells list, cases list whose
    member cells are declared as sample_hex_list with >1 entry."""
    ctrl = []
    entries = {}
    cases = []
    section = None
    cur = None
    for line in text.splitlines():
        if re.match(r"^api_entry:", line):
            section = "api"; continue
        if re.match(r"^control_cells:", line):
            section = "ctrl"; continue
        if re.match(r"^cases:", line):
            section = "cases"; continue
        if re.match(r"^[a-z_]+:", line):
            section = None
        if section == "api":
            m = re.match(r"^\s+(\w+):\s*\[(.*)\]\s*$", line)
            if m:
                entries[m.group(1)] = [x.strip() for x in m.group(2).split(",")]
            continue
        if section == "ctrl":
            m = re.match(r"^\s+-\s+(\S+)\s*$", line)
            if m:
                ctrl.append(m.group(1))
            continue
        if section == "cases":
            m = re.match(r"^\s+-\s+id:\s*(\S+)\s*$", line)
            if m:
                cur = {"id": m.group(1), "group": "trap", "hex": 0}
                cases.append(cur)
                continue
            if cur is None:
                continue
            g = re.match(r"^\s+case_group:\s*(\w+)\s*$", line)
            if g:
                cur["group"] = g.group(1)
            elif re.match(r"^\s+-\s+\"[0-9a-fA-F]{2,}\"\s*(#.*)?$", line):
                cur["hex"] += 1
            elif re.match(r"^\s+sample_hex:\s*\"", line):
                cur["hex"] = max(cur["hex"], 1)
    return ctrl, entries, cases


def build():
    raw = blob("spec/cases.yaml")
    spec_sha = hashlib.sha256(raw).hexdigest()
    text = raw.decode("utf-8")
    ctrl, entries, cases = parse(text)
    if not cases:
        raise SystemExit("parsed zero cases - the generator is wrong, fix it before publishing a manifest")

    req = []
    for c in cases:
        cid = c["id"]
        grp = "len" if cid in ("T17", "T18") else c["group"]
        if grp == "len":
            for b in BASES:
                req.append({"case_group": "len", "case_id": cid, "sub_identity": {"base_len": b}})
        elif c["hex"] > 1:
            for k in range(1, c["hex"] + 1):
                req.append({"case_group": grp, "case_id": "%s-m%d" % (cid, k), "sub_identity": {}})
        else:
            req.append({"case_group": grp, "case_id": cid, "sub_identity": {}})
    for name in ctrl:
        req.append({"case_group": "ctrl", "case_id": name, "sub_identity": {}})

    tapi = [{"case_group": "tapi", "case_id": "T-API", "language": lang, "api_entry": e,
             "sub_identity": {}}
            for lang in sorted(entries) for e in entries[lang]]

    seen = set()
    uniq = []
    for r in sorted(req, key=lambda x: (x["case_group"], x["case_id"])):
        k = json.dumps(r, sort_keys=True)
        if k in seen:
            continue
        seen.add(k)
        uniq.append(r)

    return {
        "generated_by": "ci/gen_cells_required.py - derived from the committed spec face; deterministic, "
                        "no timestamp in the output so the file can be byte-compared against a re-run",
        "spec_blob_sha256": spec_sha,
        "withdraws": "the first version of this file (generated 03:4x from a mis-parse that saw only the "
                     "20 traps) is void; any port that used it must re-derive from this one",
        "note": "A port must emit exactly these cells. Missing => status blocked with command, exit code "
                "and one attempted fix. Extra => allowed, marked extra, excluded from the equality digest.",
        "primary_entry_per_port": PRIMARY,
        "base_len_ladder": BASES,
        "required_cells": uniq,
        "tapi_cells_per_language": sorted(tapi, key=lambda r: (r["language"], r["api_entry"])),
    }


def main():
    doc = build()
    out = json.dumps(doc, ensure_ascii=False, indent=1) + "\n"
    path = os.path.join(REPO, "spec", "cells-required.json")
    old = io.open(path, encoding="utf-8").read() if os.path.isfile(path) else None
    if "--check" in sys.argv:
        if old is None:
            print("CHECK FAIL: manifest absent"); return 1
        same = old == out
        print("CHECK determinism: committed manifest == regenerated bytes -> %s (%d vs %d)"
              % ("IDENTICAL" if same else "DIFFERS", len(old.encode()), len(out.encode())))
        if not same:
            a = json.loads(old); b = json.loads(out)
            ka = {(r["case_group"], r["case_id"]) for r in a["required_cells"]}
            kb = {(r["case_group"], r["case_id"]) for r in b["required_cells"]}
            print("   only in committed: %s" % sorted(ka - kb)[:8])
            print("   only in regenerated: %s" % sorted(kb - ka)[:8])
        return 0 if same else 1
    io.open(path, "w", encoding="utf-8", newline="\n").write(out)
    print("wrote spec/cells-required.json required=%d tapi=%d spec_sha=%s"
          % (len(doc["required_cells"]), len(doc["tapi_cells_per_language"]),
             doc["spec_blob_sha256"][:12]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
