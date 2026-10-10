#!/usr/bin/env python3
# SENDGUARD Node<->Python cross-reader (independent Python runtime).
# Reads a Node-written file by its NON-PREFIXED path. A reserved-device name
# (e.g. CON.txt) opened non-prefixed resolves to the console device and HANGS;
# the orchestration shell wraps this call in `timeout 5` and records 'hang'.
# Usage: python py-reader.py <dir> <name_utf8_hex>
import sys, os, json, hashlib

def main():
    d, h = sys.argv[1], sys.argv[2]
    name = bytes.fromhex(h).decode("utf-8")
    p = os.path.join(d, name)
    res = {"found": False, "size": None, "read_result": "eof", "error_code": None}
    try:
        st = os.stat(p)
        res["found"] = True
        if os.path.isfile(p):
            with open(p, "rb") as f:
                b = f.read()
            res["size"] = len(b)
            res["sha256"] = hashlib.sha256(b).hexdigest()
            res["read_result"] = "ok" if b else "eof"
        else:
            res["read_result"] = "eof"
    except Exception as e:
        ec = getattr(e, "winerror", None)
        res["error_code"] = ("winerror:%s" % ec) if ec is not None else type(e).__name__
        res["read_result"] = "err6"
    sys.stdout.write(json.dumps(res))

if __name__ == "__main__":
    main()
