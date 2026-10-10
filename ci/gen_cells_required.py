import io, os, json, subprocess, hashlib, time, re

REPO = r"D:\sendguard-work\seat-qoder"
os.chdir(REPO)

def run(*a):
    r = subprocess.run(list(a), cwd=REPO, capture_output=True, shell=False)
    return r.returncode, r.stdout.decode("utf-8", "replace")

rc, txt = run("git", "cat-file", "blob", "HEAD:spec/cases.yaml")
assert rc == 0 and txt, "cannot read the committed spec face (rc=%d)" % rc
spec_sha = hashlib.sha256(txt.encode("utf-8")).hexdigest()

# derive, do not hand-type: walk the yaml and collect case entries
cases = []
cur = None
in_members = False
for line in txt.splitlines():
    m = re.match(r"^\s*-\s+id:\s*([A-Za-z0-9_\-]+)\s*$", line)
    if m:
        cur = {"id": m.group(1), "members": [], "group": None}
        cases.append(cur)
        in_members = False
        continue
    if cur is None:
        continue
    g = re.match(r"^\s+case_group:\s*([a-z]+)\s*$", line)
    if g:
        cur["group"] = g.group(1)
        continue
    mm = re.match(r"^\s*-\s*([A-Za-z0-9_\-]+)\s*$", line)
    if mm and (line.startswith("      ") or line.startswith("    -")):
        cur["members"].append(mm.group(1))
        continue

groups = {}
for c in cases:
    groups.setdefault(c["group"] or "?", []).append(c)

BASES = [78, 120, 200]          # per cell-identity.md section 6 addendum
PRIMARY = {"python": "open_wb", "node": "writeFileSync", "typescript": "writeFileSync",
           "go": "os.Create", "java": "Files.write", "csharp": "File.WriteAllBytes",
           "rust": "File::create"}
PORTS = ["python", "go", "java", "csharp", "rust", "typescript"]

required = []
for c in cases:
    cid = c["id"]
    grp = c["group"] or "trap"
    members = c["members"]
    if grp == "len":
        for b in BASES:
            required.append({"case_group": grp, "case_id": cid, "sub_identity": {"base_len": b}})
    elif members:
        for m in members:
            required.append({"case_group": grp, "case_id": "%s-%s" % (cid, m),
                             "sub_identity": {}})
    else:
        required.append({"case_group": grp, "case_id": cid, "sub_identity": {}})

def key_of(r):
    s = r["sub_identity"]
    return (r["case_group"], r["case_id"]) + tuple(sorted(s.items()))

uniq = {}
for r in required:
    uniq[key_of(r)] = r

doc = {
    "generated_at": time.strftime("%Y-%m-%d %H:%M:%S %z"),
    "generated_by": "ci/gen_cells_required.py (derived from the committed spec face; not hand-typed)",
    "spec_blob_sha256": spec_sha,
    "note": "A port must emit exactly these cells. Fewer => each missing cell needs status blocked "
            "with command, exit code and one attempted fix. More => allowed but must be marked extra "
            "and does not enter the equality digest.",
    "ports": PORTS,
    "primary_entry_per_port": PRIMARY,
    "base_len_ladder": BASES,
    "required_cells": sorted(uniq.values(), key=lambda r: (r["case_group"], r["case_id"])),
}
io.open(os.path.join("spec", "cells-required.json"), "w", encoding="utf-8", newline="\n").write(
    json.dumps(doc, ensure_ascii=False, indent=1) + "\n")

print("spec cases parsed=%d groups=%s" % (len(cases), {k: len(v) for k, v in sorted(groups.items())}))
print("required_cells=%d  per_port=%d (T-API entry variants are per-port, listed separately)"
      % (len(uniq), len(uniq)))
print("spec_blob_sha256=%s" % spec_sha[:16])
for k in list(sorted(uniq))[:6]:
    print("   ", k)
print("... groups present:", sorted({r["case_group"] for r in uniq.values()}))
