#!/usr/bin/env python3
# SENDGUARD Node S02 out-of-process instrument passes (W-NODE seat).
# Drives the two INDEPENDENT instruments via the shell (Node spawnSync of .exe
# is blocked with EBUSY inside this sandbox, so Node cannot launch them itself):
#   1) audit.exe  -> results/node/windows/_audit-truth.ndjson   (TRUTH instrument)
#   2) py-reader  -> results/node/windows/_pyreader-results.ndjson (cross-reader)
# Reads the manifests that main.mjs --api wrote, writes NDJSON keyed for merge.
import json, os, subprocess, sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WOUT = os.path.join(REPO, "results", "node", "windows")
AUDIT_EXE = os.path.join(REPO, "harness", "audit.exe")
PYREADER = os.path.join(REPO, "impl", "node", "py-reader.py")

# python runtime: prefer managed 3.13, then PATH python3/python
for cand in [
    r"C:\Users\Administrator\.workbuddy\binaries\python\versions\3.13.12\python.exe",
    "python3", "python",
]:
    try:
        cp = subprocess.run([cand, "--version"], capture_output=True, text=True, timeout=10)
        if "Python" in (cp.stdout + cp.stderr):
            PYBIN = cand
            break
    except Exception:
        continue
else:
    PYBIN = "python"
print("python bin:", PYBIN)


def run_audit():
    man = json.load(open(os.path.join(WOUT, "_audit-manifest.json")))
    out = []
    n_device = 0
    for e in man["entries"]:
        d = e["run_dir"]
        cid = e["case_id"]
        entries = []
        go_version = None
        try:
            cp = subprocess.run([AUDIT_EXE, d], capture_output=True, text=True, timeout=30)
            if cp.returncode == 0 and cp.stdout.strip():
                obj = json.loads(cp.stdout)
                entries = obj.get("entries") or []
                go_version = obj.get("go_version")
            else:
                sys.stderr.write(f"audit NONZERO/EMPTY {cid} {d}: rc={cp.returncode} out={cp.stdout[:200]!r} err={cp.stderr[:200]!r}\n")
        except Exception as ex:
            sys.stderr.write(f"audit FAIL {cid} {d}: {ex}\n")
        out.append({"dir": d, "case_id": cid, "go_version": go_version, "entries": entries})
        for en in entries:
            if en.get("is_device"):
                n_device += 1
    with open(os.path.join(WOUT, "_audit-truth.ndjson"), "w", encoding="utf-8") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"audit pass: {len(man['entries'])} dirs -> {len(out)} lines, device entries seen: {n_device}")


def run_pyreader():
    man = json.load(open(os.path.join(WOUT, "_pyreader-manifest.json")))
    out = []
    n_hang = 0
    for e in man["entries"]:
        d = e["run_dir"]
        hexv = e["name_hex"]
        cid = e["case_id"]
        try:
            cp = subprocess.run([PYBIN, PYREADER, d, hexv], capture_output=True, text=True, timeout=8)
            if cp.returncode == 0:
                res = json.loads(cp.stdout)
            else:
                res = {"found": False, "size": None, "read_result": "err6", "error_code": f"rc={cp.returncode}"}
        except subprocess.TimeoutExpired:
            res = {"found": False, "size": None, "read_result": "hang", "error_code": "timeout5"}
            n_hang += 1
        except Exception as ex:
            res = {"found": False, "size": None, "read_result": "err6", "error_code": str(ex)}
        res["case_id"] = cid
        out.append(res)
    with open(os.path.join(WOUT, "_pyreader-results.ndjson"), "w", encoding="utf-8") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"pyreader pass: {len(man['entries'])} entries -> {len(out)} lines, hangs: {n_hang}")


if __name__ == "__main__":
    run_audit()
    run_pyreader()
