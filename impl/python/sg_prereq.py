#!/usr/bin/env python3
"""SENDGUARD S02 python port - prerequisite recon (run by the parent local only).

Checks, before any cell is planned:
  1. the control payload provenance (sha256 must equal evidence/ctrl-baseline.md)
  2. which scratch roots are writable and how short a directory path can be built
     (the frozen G1/G3 grid asks for base_len == 13, which the documented
     %TEMP%\\sendguard-run root cannot reach)
  3. the interpreter identity actually executed

ASCII source, stdlib only, no deletion anywhere (red line project rule).
"""
import hashlib
import os
import re
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> int:
    out = []
    out.append("python_executable=%s" % sys.executable)
    out.append("python_version=%s" % sys.version.split()[0])
    out.append("platform=%s" % sys.platform)
    out.append("cwd=%s" % os.getcwd())
    out.append("repo=%s" % REPO)

    baseline = os.path.join(REPO, "evidence", "ctrl-baseline.md")
    txt = open(baseline, "rb").read().decode("utf-8")
    m = re.search(r"c9fe[0-9a-f]{60}", txt)
    out.append("baseline_sha_token_found=%s" % bool(m))
    for n in (15, 16, 62, 63, 64, 65):
        hits = re.findall(r"[0-9a-f]{%d}" % n, txt)
        if hits:
            out.append("hex_runs_len_%d=%d sample=%s" % (n, len(hits), hits[0]))
    payload = b"SENDGUARD-CANON-PAYLOAD-2026"
    out.append("payload_len=%d" % len(payload))
    out.append("payload_sha=%s" % hashlib.sha256(payload).hexdigest())
    out.append("payload_matches_baseline=%s" % (hashlib.sha256(payload).hexdigest() == m.group(0)))

    temp_root = os.path.join(tempfile.gettempdir(), "sendguard-run")
    out.append("documented_temp_root_len=%d" % len(temp_root))
    for cand in ["C:\\", "D:\\", tempfile.gettempdir()]:
        d = cand if cand.endswith("\\") else os.path.join(cand, "sendguard-run")
        d = os.path.join(d, "sg-prereq")
        try:
            os.makedirs(d, exist_ok=True)
            probe = os.path.join(d, "w.txt")
            with open(probe, "wb") as fh:
                fh.write(b"w")
            out.append("WRITABLE len=%d path=%s" % (len(d), d))
        except Exception as e:
            out.append("NOT-WRITABLE path=%r %s winerror=%s" % (d, type(e).__name__, getattr(e, "winerror", None)))
    out.append("min_component_probe: max name len at short root")
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
