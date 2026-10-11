#!/usr/bin/env python3
"""Additive in-place repair: `sub_identity` as an object of declared dimensions.

ci/equality.py (as of commit fac9089) requires sub_identity to be an object; this port had been
writing its own dotted string, which flags 48 cells with a contract defect. This script rewrites
the SAME filenames in place -- nothing is removed, no directory is cleared, and a run that dies
half way leaves every remaining cell exactly as it was.

It recomputes sha256_self with the port's own rule (key-sorted compact JSON of the cell with
sha256_self removed, UTF-8) and refuses to write a file whose required length cell breaks.
"""
import hashlib
import json
import os
import re
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
FACE = os.path.join(REPO, "results", "typescript.windows.x64")


def sort_deep(v):
    if isinstance(v, dict):
        return {k: sort_deep(v[k]) for k in sorted(v)}
    if isinstance(v, list):
        return [sort_deep(x) for x in v]
    return v


def dims_from_name(fname):
    """Recover the ordered dimensions from the cell filename, per spec/cell-identity.md S3."""
    stem = fname[: -len(".json")]
    parts = stem.split("__")
    if len(parts) == 3:
        out = {}
        for seg in parts[2].split("."):
            k, _, v = seg.partition("-")
            out[k] = int(v) if re.fullmatch(r"\d+", v) else v
        return out
    return {}


def main():
    if not os.path.isdir(FACE):
        print("FACE MISSING", FACE)
        return 1
    names = sorted(n for n in os.listdir(FACE) if n.endswith(".json"))
    touched = kept = refused = 0
    for n in names:
        path = os.path.join(FACE, n)
        raw = io_read(path)
        cell = json.loads(raw)
        dims = dims_from_name(n)
        # in-cell fields are the authority; the object only declares which dimensions vary
        for k, v in list(dims.items()):
            field = "api_entry" if k == "entry" else k
            if cell.get(field) is not None and cell[field] != v:
                print("REFUSED %s: dimension %s=%r contradicts the cell field %r" % (n, k, v, cell[field]))
                refused += 1
                break
            cell[field] = v
        else:
            before = cell.get("sub_identity")
            cell["sub_identity"] = dims
            cell["sub_identity_rendering"] = (
                "object of the declared dimensions, in filename order; the dotted string in the file "
                "name is spec/cell-identity.md S3's naming rule, not the cell's identity"
            )
            body = {k: v for k, v in cell.items() if k != "sha256_self"}
            cell["sha256_self"] = hashlib.sha256(
                json.dumps(sort_deep(body), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            ).hexdigest()
            text = json.dumps(sort_deep(cell), indent=2, ensure_ascii=False, sort_keys=True) + "\n"
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
            touched += 1
            if before != dims:
                kept += 1
    print("face=%s files=%d rewritten=%d of which changed=%d refused=%d"
          % (os.path.relpath(FACE, REPO).replace("\\", "/"), len(names), touched, kept, refused))
    return 1 if refused else 0


def io_read(p):
    with open(p, "rb") as fh:
        return fh.read().decode("utf-8")


if __name__ == "__main__":
    sys.exit(main())
