#!/usr/bin/env python3
"""Two-sided self-test for the sendguard gates.

A gate that has only ever been seen refusing is not proven to work, and a gate that can only pass is worse.
Every arm here asserts a specific exit code, and the set includes at least one arm that must PASS. If a gate
were hard-wired to green, the red arms catch it; if it were hard-wired to red, the green arm catches it.

Usage:  python ci/selftest.py --scratch-root <dir>
The scratch root is required: an instrument may not choose its own landing place, and it may not create
anything at a drive root.
"""
import hashlib
import io
import re
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
GATE = os.path.join(HERE, "equality.py")

BEHAV = dict(case_group="trap", create_result="ok", error_stage="null", os_legality_verdict="legal",
             read_result="ok", path_form="plain", longpath_mechanism="none", length_unit="code_points",
             name_encoding="hex_raw_bytes", name_source="61.6263", bytes_written=3, bytes_on_disk=3,
             roundtrip_ok=True, enum_to_stat_agrees=True, control_pass=True, instrument_red=False,
             deps_direct=0, deps_total=0, mechanism_class="illegal_char_filter",
             name_landed_as="61.6263", name_mutated=False, phantom=False,
             len_triple={"cp": 3, "utf16": 3, "bytes": 3})


def cell(case="T03", **over):
    c = dict(BEHAV)
    c["case_id"] = case
    c["api_entry"] = "primary"
    c["language"] = "?"
    c["os"] = "windows"
    c.update(over)
    return c


def write_results(root, ports):
    """ports: {port: [cell,...]} -> results/<port>.windows.x64/*.json"""
    d = os.path.join(root, "results")
    for port, cells in ports.items():
        pdir = os.path.join(d, "%s.windows.x64" % port)
        os.makedirs(pdir, exist_ok=True)
        for c in cells:
            # the filename must carry the same sub_identity the cell does, otherwise two
            # legitimate cells overwrite each other on disk - the exact defect the gate reports
            sub = "__b%d" % c["base_len"] if c.get("base_len") is not None else ""
            io.open(os.path.join(pdir, "%s__%s%s.json" % (c["case_group"], c["case_id"], sub)),
                    "w", encoding="utf-8", newline="\n").write(
                json.dumps(c, ensure_ascii=False, sort_keys=True, indent=1) + "\n")
    return d


def base_two():
    a = [cell("T03"), cell("T01", create_result="err_at_syscall", error_stage="syscall",
                os_legality_verdict="illegal", mechanism_class="reserved_device_name")]
    b = [dict(x, language="beta") for x in a]
    return {"alpha": a, "beta": b}


ARMS = []


def arm(name, expect, ports, note="", expect_contains=""):
    ARMS.append((name, expect, ports, note, expect_contains))


def write_manifest(dir_, ports, extra_required=(), forbid_required=()):
    """A fixture's question set, written the way the contract writes the real one.

    The gate now reports INCOMPLETE when the required list is not covered, so an arm that wants to prove
    the gate can say YES has to supply the list its own cells answer -- otherwise the arm would be
    measuring coverage, not comparison. `extra_required` adds ids no cell carries (the missing-cell arm),
    `forbid_required` removes ids so a spelling fold is tested against a list the port did not satisfy.
    """
    sys.path.insert(0, HERE)
    import equality
    cells, prim = [], {}
    seen = set()
    for port, lst in ports.items():
        prim[port] = "primary"
        for c in lst:
            k = equality.key_of(c)
            if k in seen:
                continue
            seen.add(k)
            cells.append({"case_group": k[0], "case_id": k[1],
                          "sub_identity": dict(k[2]), "api_entry_per_port": {port: "primary"}})
    for gid in extra_required:
        g, cid = gid.split("/", 1)
        cells.append({"case_group": g, "case_id": cid, "sub_identity": {}})
    for gid in forbid_required:
        g, cid = gid.split("/", 1)
        cells = [c for c in cells if not (c["case_group"] == g and c["case_id"] == cid)]
    p = os.path.join(dir_, "cells-required.json")
    io.open(p, "w", encoding="utf-8", newline="\n").write(
        json.dumps({"required_cells": cells, "primary_entry_per_port": prim},
                   ensure_ascii=False, sort_keys=True, indent=1) + "\n")
    return p


def run_gate(results_dir, manifest=None):
    env = dict(os.environ)
    if manifest:
        env["SG_REQUIRED_CELLS"] = manifest
    r = subprocess.run([sys.executable, GATE, "--results-dir", results_dir],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       cwd=REPO, shell=False, env=env)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def main(argv):
    if "--scratch-root" not in argv:
        print("REFUSING: --scratch-root is required (an instrument does not pick its own landing place)")
        return 4
    root = os.path.abspath(argv[argv.index("--scratch-root") + 1])
    if os.path.dirname(root) == root or root in ("D:\\", "C:\\", "D:/", "C:/"):
        print("REFUSING: scratch root is a drive root: %s" % root)
        return 4
    os.makedirs(root, exist_ok=True)
    print("scratch_root=%s  clock=%s" % (root, time.strftime("%Y-%m-%d %H:%M:%S %z")))

    # 1. the gate must be able to PASS
    arm("green-identical", 0, base_two(), "two ports agreeing must return 0 - a gate that cannot say yes is dead")

    # 2. a one-byte difference in one behaviour field must be caught
    p = base_two(); p["beta"][0]["bytes_on_disk"] = 4
    arm("red-one-byte", 1, p, "single-byte difference in bytes_on_disk must turn the run red")

    # 3. a different verdict on the same cell must be caught
    p = base_two(); p["alpha"][1]["os_legality_verdict"] = "legal"
    arm("red-verdict-flip", 1, p, "legal vs illegal for the same name must be red")

    # 3b. a different *probe answer* must NOT be red: six languages asking one OS differently is the
    # matrix, not a failure, and a gate that calls it a failure buries the divergences worth shipping.
    p = base_two(); p["beta"][1]["create_result"] = "err_at_syscall"
    p["beta"][1]["error_stage"] = "syscall"
    arm("probe-difference-is-data", 0, p,
        "create_result alone must be published as spread, not judged as a broken claim")

    # 4. missing cell => refuse to compare, never compare the intersection
    p = base_two(); p["beta"] = p["beta"][:1]
    arm("deny-denominator", 3, p, "different cell sets are not comparable")

    # 5. a port that marks itself red is excluded, and with 2 ports that means no comparison
    p = base_two(); p["beta"][0]["instrument_red"] = True
    arm("deny-self-red", 3, p, "self-declared instrument_red may not enter a comparison")

    # 6. a status word outside the closed set voids the run
    p = base_two(); p["beta"][0]["read_result"] = "maybe_ok"
    arm("deny-closed-set", 3, p, "invented status word must be refused, not normalised")

    # 7. crash text where a verdict belongs is not a measurement
    p = base_two(); p["beta"][0]["error_message"] = "fs is not defined"
    arm("deny-crash-as-measurement", 3, p, "a runtime crash record must not be compared as data")

    # 8. sub_identity: two length cells differing only by base_len must not collide, and must agree
    p = base_two()
    # the same case_id at two base depths is two cells; both ports must emit both, and the
    # fixture writes them to two distinct filenames so neither overwrites the other
    for port in ("alpha", "beta"):
        p[port] += [cell("T17", case_group="len", base_len=78, bytes_on_disk=None),
                    cell("T17", case_group="len", base_len=200, bytes_on_disk=None)]
    arm("sub-identity-separates", 0, p, "same case_id at different base_len are different cells")

    # 9. a failed control cell blocks the port
    p = base_two(); p["beta"][0]["control_pass"] = False
    arm("deny-failed-control", 3, p, "a port that fails its own control is not evidence")

    # 10. spelling drift is folded, but never guessed at. Measured in the rev5 run: one port wrote the
    # blind sample as BLIND-1, another T-BLIND-1, the list says B1; one wrote T09a where the list says
    # T09-m1. A gate that cannot see through that reports work that was done as work that is missing.
    p = {"alpha": [cell("T09-m1", case_group="trap", member_index=1),
                   cell("B1", case_group="blind")],
         "beta": [cell("T09a", case_group="trap", member_index=1),
                  cell("T-BLIND-1", case_group="blind")]}
    arm("alias-folds-spelling-drift", 0, p,
        "T09a / T-BLIND-1 are the same questions as T09-m1 / B1 -- fold them and say yes",
        expect_contains="OUTCOME=PASS")

    # 11. ...and a bare family id is NOT a member: the record does not say which sample it measured, so
    # folding it would be the gate inventing data to make a number look better.
    p = {"alpha": [cell("T09", case_group="trap")], "beta": [cell("T09", case_group="trap")]}
    arm("alias-refuses-to-guess-member", 3, p,
        "bare T09 must not be folded into T09-m1", expect_contains="trap/T09-m1")

    # 12. a port that reached its legality verdict through a different channel loses THAT field only.
    # Measured reason: 11 of 13 excluded cells were excluded because one port records verdict_via='none',
    # and the whole cell - bytes on disk, the enumerated name, everything - went with it.
    p = base_two()
    p["alpha"][0]["verdict_via"] = "win32"
    p["beta"][0]["verdict_via"] = "none"
    p["beta"][0]["os_legality_verdict"] = "legal"
    arm("channel-difference-does-not-turn-the-run-red", 3, p,
        "differing verdict_via must drop one field, not the cell, and must not be called a disagreement",
        expect_contains="disagree=0")

    # 13. ...and a real conflict on another field in that same cell is still RED: the field-level rule
    # must not become a licence to ignore bytes on disk.
    p = base_two()
    p["alpha"][0]["verdict_via"] = "win32"
    p["beta"][0]["verdict_via"] = "none"
    p["beta"][0]["os_legality_verdict"] = "illegal"
    p["beta"][0]["bytes_on_disk"] = 99
    arm("channel-abstention-still-sees-other-fields", 1, p,
        "with the legality field abstained, a one-byte conflict on the same cell must still be red")

    passed = failed = 0
    total = len(ARMS)
    for name, expect, ports, note, want in ARMS:
        adir = os.path.join(root, name)
        os.makedirs(adir, exist_ok=True)
        rd = write_results(adir, ports)
        man = write_manifest(adir, ports,
                             extra_required=(["trap/T09-m1"] if want == "trap/T09-m1" else []))
        rc, out = run_gate(rd, man)
        hit = (rc == expect) and (not want or want in out)
        passed += hit
        failed += (not hit)
        print("  %-28s expect_rc=%d got_rc=%-3d %s   %s"
              % (name, expect, rc, "OK" if hit else "FAIL", note))
        if not hit:
            for line in out.strip().splitlines()[-6:]:
                print("        | " + line[:150])
            if want and want not in out:
                print("        | expected to find %r in the gate's own output" % want)
    # the lock table must describe the committed bytes AND the checkout; if these ever differ,
    # a digest quoted anywhere in this repo has become unverifiable by a stranger
    locks = {}
    fz = io.open(os.path.join(REPO, "spec", "FROZEN.md"), encoding="utf-8").read()
    for m in re.finditer(r"(?m)^\|\s*(spec/[A-Za-z0-9_.\-]+)\s*\|\s*([0-9a-f]{64})\s*\|", fz):
        locks[m.group(1)] = m.group(2)
    lock_bad = []
    for name, want in sorted(locks.items()):
        b = subprocess.run(["git", "cat-file", "blob", "HEAD:" + name], cwd=REPO,
                           capture_output=True, shell=False)
        blob_sha = hashlib.sha256(b.stdout).hexdigest() if b.returncode == 0 else ""
        path = os.path.join(REPO, name.replace("/", os.sep))
        disk_sha = hashlib.sha256(io.open(path, "rb").read()).hexdigest() if os.path.isfile(path) else ""
        if blob_sha != want or disk_sha != want:
            lock_bad.append("%s(blob=%s,disk=%s)" % (name, blob_sha[:6], disk_sha[:6]))
    lok = bool(locks) and not lock_bad
    total += 1
    passed += lok
    failed += (not lok)
    print("  %-28s rows=%-3d %s   locked files match both the committed blob and the checkout%s"
          % ("lock-table-faces", len(locks), "OK" if lok else "FAIL",
             "" if lok else "  -> " + "; ".join(lock_bad[:5])))

    # the published required-cell list must be reproducible from its generator, or the contract is
    # folklore: this arm exists because the two had already drifted apart once
    g = subprocess.run([sys.executable, os.path.join(HERE, "gen_cells_required.py"), "--check"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       cwd=REPO, shell=False)
    gok = g.returncode == 0
    total += 1
    passed += gok
    failed += (not gok)
    print("  %-28s expect_rc=0 got_rc=%-3d %s   committed manifest == regenerated bytes"
          % ("generator-determinism", g.returncode, "OK" if gok else "FAIL"))
    if not gok:
        for line in (g.stdout or "").strip().splitlines()[-6:]:
            print("        | " + line[:150])
    print("arms=%d passed=%d failed=%d" % (total, passed, failed))
    print("OUTCOME=%s" % ("PASS" if failed == 0 else "FAIL"))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
