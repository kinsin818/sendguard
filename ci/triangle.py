#!/usr/bin/env python3
"""Three-way cross-check: ports vs the sealed expectation vs the machine's own tools.

Why this exists: six ports agreeing proves they are consistent, not that they are right. The sealed
expectation table was written by a window that read no implementation and ran no port, so a shared
misreading of the spec shows up as ports-vs-expectation disagreement. The referee file records what the
OS's own tools did, which is nobody's code but the OS vendor's.

Exit codes:
  0  every port is comparable and no cell is agreed-by-all-yet-contradicted-by-the-expectation
  1  at least one collective misreading exists (all live ports agree with each other and disagree with
     the sealed expectation) - this is the finding, not a build failure
  3  not enough data to run the check (fewer than two live ports, or the expectation table unparsed)
"""
import glob
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import equality

WORDS = {
    "create_result": ["ok", "err_at_parse", "err_at_syscall", "hang"],
    "read_result": ["ok", "eof", "err6", "hang"],
    "os_legality_verdict": ["legal", "illegal", "unknown"],
    "path_form": ["plain", "extended"],
}
FIELDS = ["create_result", "read_result", "os_legality_verdict", "path_form"]


def parse_expectations(path):
    """-> {(case_id, os): {field: allowed-set, 'confidence': str, 'name_landed_as': str}}"""
    if not os.path.isfile(path):
        return {}, "missing " + path
    text = io.open(path, encoding="utf-8").read()
    exp = {}
    case = None
    last_row = None
    for line in text.splitlines():
        m = re.match(r"^### (T[0-9]{2}|T-CTRL-[A-Z]+|B[0-9]+)\b", line)
        if m:
            case = m.group(1)
            last_row = None
            continue
        if case is None:
            continue
        m = re.match(r"^-\s+(windows|macos|ubuntu)\s*\|(.*)$", line)
        if not m:
            continue
        osname, body = m.group(1), m.group(2)
        if re.search(r"same as (macos|windows|ubuntu)", body):
            src = re.search(r"same as (macos|windows|ubuntu)", body).group(1)
            if (case, src) in exp:
                exp[(case, osname)] = dict(exp[(case, src)])
            continue
        row = {}
        for f in FIELDS:
            mm = re.search(r"\b%s:\s*([^|\n]+)" % f, body)
            if mm:
                allowed = [w for w in WORDS[f] if re.search(r"\b%s\b" % w, mm.group(1))]
                if allowed:
                    row[f] = set(allowed)
        mm = re.search(r"bytes_on_disk:\s*([^|\n]+)", body)
        if mm:
            v = mm.group(1).strip()
            row["bytes_on_disk"] = "null" if v.startswith("null") else ("eq_written" if "==" in v else v)
        mm = re.search(r"name_landed_as:\s*([0-9a-fA-F]{2,}|null)", body)
        if mm:
            row["name_landed_as"] = mm.group(1).lower()
        mm = re.search(r"confidence:\s*(high|medium|low)", body)
        row["confidence"] = mm.group(1) if mm else "unmarked"
        exp[(case, osname)] = row
        last_row = (case, osname)
    return exp, None


def load_ports():
    ports = {}
    for entry in sorted(os.listdir(os.path.join(REPO, "results"))):
        full = os.path.join(REPO, "results", entry)
        if not os.path.isdir(full) or not re.match(r"^[a-z]+\.windows\.", entry):
            continue
        port = entry.split(".")[0]
        cells = {}
        for f in sorted(glob.glob(os.path.join(full, "**", "*.json"), recursive=True)):
            try:
                c = json.loads(io.open(f, encoding="utf-8").read())
            except ValueError:
                continue
            if not isinstance(c, dict) or not c.get("case_id"):
                continue
            if c.get("instrument_red") is True or c.get("control_pass") is False:
                continue
            k = equality.key_of(c)
            cells.setdefault(k, []).append(c)
        if cells:
            ports[port] = cells
    return ports


def primary(cells, port):
    prim = json.load(io.open(os.path.join(REPO, "spec", "cells-required.json"),
                             encoding="utf-8"))["primary_entry_per_port"].get(port)
    out = {}
    for k, lst in cells.items():
        pick = next((c for c in lst if c.get("api_entry") == prim), lst[0])
        out[k[1]] = pick
    return out


def main():
    exp, err = parse_expectations(os.path.join(REPO, "spec", "expectations.sealed.md"))
    if err or not exp:
        print("OUTCOME=NO-DATA reason=%s" % (err or "no rows parsed"))
        return 3
    ports = load_ports()
    if len(ports) < 2:
        print("OUTCOME=NO-DATA live_ports=%d" % len(ports))
        return 3
    print("expectation rows=%d  live ports=%d (%s)"
          % (len(exp), len(ports), " ".join(sorted(ports))))

    per_port = {}
    for port, cells in sorted(ports.items()):
        prim = primary(cells, port)
        agree = miss = bad = lowskip = 0
        details = []
        for (case, osn), row in sorted(exp.items()):
            if osn != "windows":
                continue
            c = prim.get(case)
            if c is None:
                miss += 1
                continue
            if row.get("confidence") == "low":
                lowskip += 1
                continue
            for f in FIELDS:
                want = row.get(f)
                got = c.get(f)
                if want is None or got is None:
                    continue
                if isinstance(want, set):
                    ok = got in want
                else:
                    ok = True
                if not ok:
                    bad += 1
                    details.append((case, f, sorted(want), got))
                else:
                    agree += 1
        per_port[port] = (agree, bad, miss, lowskip, details)
        print("  %-11s fields_agree=%-4d fields_disagree=%-3d cells_absent=%-3d low_conf_skipped=%d"
              % (port, agree, bad, miss, lowskip))

    # the finding only this file can produce: all ports agree with each other and all disagree
    # with the sealed expectation, in the same way
    by_cf = {}
    for port in per_port:
        for (case, field, want, got) in per_port[port][4]:
            by_cf.setdefault((case, field), {})[port] = got
    collective = [(cf, vals) for cf, vals in sorted(by_cf.items())
                  if len(vals) == len(per_port) and len(set(vals.values())) == 1]
    print("collective_misreadings=%d  (every live port disagrees with the sealed expectation the same way)"
          % len(collective))
    for (case, field), vals in collective[:12]:
        w = exp.get((case, "windows"), {}).get(field)
        print("   %s %s: expectation=%s but all %d ports say %s"
              % (case, field, sorted(w) if isinstance(w, set) else w, len(vals),
                 sorted(set(vals.values()))[0]))

    # referee cross-check: where the machine's own tools contradict the sealed expectation
    ref = os.path.join(REPO, "evidence", "freeze", "referee-windows.json")
    if os.path.isfile(ref):
        d = json.load(io.open(ref, encoding="utf-8"))
        obs = d.get("observations", [])
        nb = [o for o in obs if "NBSP" in str(o.get("requested_shown", "")) or "NBSP" in str(o.get("id", ""))]
        print("referee records=%d; trailing-NBSP records=%d" % (len(obs), len(nb)))
        for o in nb[:4]:
            print("   %s tool=%s outcome=%s ondisk=%s"
                  % (o.get("id"), o.get("tool"), o.get("outcome"),
                     str(o.get("ondisk_name_codepoints") or o.get("ondisk_hex") or "")[:40]))
    print("OUTCOME=%s" % ("COLLECTIVE-MISREADING" if collective else "CLEAN"))
    return 1 if collective else 0


if __name__ == "__main__":
    sys.exit(main())
