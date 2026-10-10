#!/usr/bin/env python3
"""The one way this repository computes a digest: over the committed blob face.

Why: `core.autocrlf` and editor policies can make a checked-out file differ from the bytes in the commit
(measured: 384 of 388 files differed before `.gitattributes` pinned `-text`). A digest taken from a working
tree file therefore cannot be compared between machines, and two independent defects in this project came
from exactly that. Hash the commit, or say you are hashing the working tree - never silently.
"""
import hashlib
import subprocess
import sys


def blob(path, rev="HEAD"):
    r = subprocess.run(["git", "cat-file", "blob", "%s:%s" % (rev, path)],
                       capture_output=True, shell=False)
    if r.returncode != 0:
        raise SystemExit("cannot read %s:%s (rc=%d): %s" % (rev, path, r.returncode, r.stderr[:200]))
    return r.stdout


def main(argv):
    if len(argv) < 2:
        print("usage: python ci/blobhash.py <repo-relative-path> [rev]")
        return 4
    rev = argv[2] if len(argv) > 2 else "HEAD"
    b = blob(argv[1], rev)
    print(hashlib.sha256(b).hexdigest())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
