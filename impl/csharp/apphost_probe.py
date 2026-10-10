#!/usr/bin/env python3
r"""SENDGUARD S02 C# port - host-manifest discriminator (evidence-level, not a matrix cell).

Question: a plain path past the legacy 259 wall succeeded under `dotnet exec`. Was that the
HOST's manifest (env-facts byte-scanned longPathAware=true inside dotnet.exe) or the runtime
rewriting the path itself? The published apphost carries its own manifest, so it can answer
the question - `dotnet.exe` cannot.

Two arms, because a leg that has only ever been seen passing proves nothing:
  short point  - component 10 in a short dir    -> both hosts must report ok (green arm)
  long  point  - component 250 in a 13-char dir -> total 264, past the legacy wall

Writes its own report to D:\sg-cs-scratch\apphost-probe.json. Opens no reserved device.
"""
import io
import json
import os
import subprocess
import sys
import uuid

DOTNET = r"C:\Program Files\dotnet\dotnet.exe"
PUB_DIR = r"D:\sg-cs-scratch\pub"
APPHOST = os.path.join(PUB_DIR, "SendGuardProbe.exe")
DLL = os.path.join(PUB_DIR, "SendGuardProbe.dll")
SCRATCH = r"D:\sg-cs-scratch\cells"
REPORT = r"D:\sg-cs-scratch\apphost-probe.json"
TIMEOUT_S = 5.0


def manifest_scan(path):
    """Byte scan for the ASCII token, same method env-facts used, same disclaimer."""
    with open(path, "rb") as f:
        raw = f.read()
    return {"path": path, "bytes_scanned": len(raw),
            "token": "longPathAware", "hit_count": raw.count(b"longPathAware"),
            "found": raw.count(b"longPathAware") > 0,
            "method": "byte-scan of raw executable bytes; NOT a PE manifest parse"}


def run(host_argv, comp_len, out):
    cell = os.path.join(SCRATCH, "h" + uuid.uuid4().hex[:12])
    os.makedirs(cell, exist_ok=True)
    report = os.path.join(SCRATCH, os.path.basename(cell) + ".json")
    argv = list(host_argv) + ["--mode", "point", "--dir", cell, "--shape", "comp",
                              "--comp-len", str(comp_len), "--fill", "q", "--entry",
                              "File.WriteAllBytes", "--form", "plain", "--legality", "0",
                              "--payload", "canon", "--report", report]
    t0 = subprocess.list2cmdline(argv)
    timed_out = False
    rc = None
    try:
        p = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=TIMEOUT_S)
        rc = p.returncode
    except subprocess.TimeoutExpired:
        timed_out = True
    rep = None
    if os.path.isfile(report):
        with io.open(report, encoding="utf-8") as f:
            rep = json.load(f)
    att = ((rep or {}).get("attempts") or [{}])[0]
    landed = ((rep or {}).get("path_view_after_create") or {}).get("target_dir") or []
    return {"argv": t0, "rc": rc, "timed_out": timed_out, "dir_len": len(cell),
            "component_len": comp_len, "total_path_len": len(cell) + 1 + comp_len,
            "create_result": att.get("create_result"), "error_stage": att.get("error_stage"),
            "error_code": att.get("error_code"),
            "error_message": (att.get("error_message") or "")[:200],
            "entries_landed": [(r["name_hex"], r["size"]) for r in landed],
            "report_present": rep is not None}


def main():
    out = {"dotnet_used": DOTNET, "apphost": APPHOST if os.path.isfile(APPHOST) else None,
           "apphost_present": os.path.isfile(APPHOST), "LongPathsEnabled": None}
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"SYSTEM\CurrentControlSet\Control\FileSystem") as k:
            out["LongPathsEnabled"] = int(winreg.QueryValueEx(k, "LongPathsEnabled")[0])
    except Exception as e:
        out["registry_error"] = "%s: %s" % (type(e).__name__, str(e)[:120])

    for p in (DOTNET, APPHOST):
        if os.path.isfile(p):
            out.setdefault("manifest_scan", []).append(manifest_scan(p))

    hosts = {"dotnet_exec": [DOTNET, "exec", DLL], "published_apphost": [APPHOST]}
    points = {"short": 10, "long_past_259": 250}
    rows = {}
    for hname, argv in hosts.items():
        if hname == "published_apphost" and not os.path.isfile(APPHOST):
            rows[hname] = {"skipped": "apphost not built"}
            continue
        rows[hname] = {pn: run(argv, pl, out) for pn, pl in points.items()}
    out["runs"] = rows

    # the two-arm verdict
    def ok(r):
        return r.get("create_result") == "ok"
    verdict = {}
    for hname, r in rows.items():
        if "skipped" in r:
            verdict[hname] = "SKIPPED"
            continue
        arms = {"short_ok": ok(r["short"]), "long_ok": ok(r["long_past_259"])}
        verdict[hname] = ("long-path-capable" if arms["short_ok"] and arms["long_ok"]
                          else "no-long-path" if arms["short_ok"] and not arms["long_ok"]
                          else "INSTRUMENT-PROBLEM: green arm (short) did not pass")
    out["arms"] = {h: {"short": ok(r["short"]), "long": ok(r["long_past_259"])}
                   for h, r in rows.items() if "skipped" not in r}
    out["verdict"] = verdict
    with io.open(REPORT, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, indent=2, sort_keys=True, ensure_ascii=True)
        f.write("\n")
    print(json.dumps({"verdict": verdict, "arms": out["arms"],
                      "manifest": [{k: m[k] for k in ("path", "hit_count", "found")}
                                   for m in out.get("manifest_scan", [])],
                      "LongPathsEnabled": out["LongPathsEnabled"]}, indent=1))
    bad = [h for h, v in verdict.items() if v.startswith("INSTRUMENT-PROBLEM")]
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
