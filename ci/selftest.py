#!/usr/bin/env python3
"""Two-sided self-test for the sendguard gates.

A gate that has only ever been seen refusing is not proven to work, and a gate that can only pass is worse.
Every arm here asserts a specific exit code, and the set includes at least one arm that must PASS. If a gate
were hard-wired to green, the red arms catch it; if it were hard-wired to red, the green arm catches it.

Usage:  python ci/selftest.py --scratch-root <dir>
The scratch root is required: an instrument may not choose its own landing place, and it may not create
anything at a drive root.
"""
import io
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


def arm(name, expect, ports, note=""):
    ARMS.append((name, expect, ports, note))


def run_gate(results_dir):
    r = subprocess.run([sys.executable, GATE, "--results-dir", results_dir],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       cwd=REPO, shell=False)
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
    p = base_two(); p["beta"][1]["create_result"] = "ok"
    arm("red-verdict-flip", 1, p, "ok vs err_at_syscall on the same cell must be red")

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

    passed = failed = 0
    for name, expect, ports, note in ARMS:
        adir = os.path.join(root, name)
        os.makedirs(adir, exist_ok=True)
        rd = write_results(adir, ports)
        rc, out = run_gate(rd)
        ok = (rc == expect)
        passed += ok
        failed += (not ok)
        print("  %-28s expect_rc=%d got_rc=%-3d %s   %s" % (name, expect, rc, "OK" if ok else "FAIL", note))
        if not ok:
            for line in out.strip().splitlines()[-6:]:
                print("        | " + line[:150])
    print("arms=%d passed=%d failed=%d" % (len(ARMS), passed, failed))
    print("OUTCOME=%s" % ("PASS" if failed == 0 else "FAIL"))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
