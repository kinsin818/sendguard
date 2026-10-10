#!/usr/bin/env python3
"""sendguard equality gate.

Claim under test: one frozen spec, N ports, byte-identical behaviour.

Exit codes:
  0  all ports agree on the behavioural digest, denominators matched, no ambiguity
  1  ports disagree (named cells, named fields)
  3  not comparable (denominators differ / a cell has several entries and no primary is pinned /
     a status word is outside the closed set) -- refusing to compare is a result, not a failure
  4  the gate could not load its inputs (never reportable as a measurement)

Cell identity for the equality claim is (case_group, case_id). `api_entry` is deliberately NOT part of
that identity: it is a language-specific name, so including it makes cross-port comparison impossible by
construction (measured: three ports, intersection of keys = 0). When a port emits several entries for one
cell, the port must declare which one is its primary; until the spec pins that, the gate refuses to pick.

Deliberate exclusions from the digest, because "identical" means identical behaviour, not identical prose:
  - raw error codes and messages (123 vs ENOENT is data, kept verbatim in the files, not a verdict);
  - environment facts (os_version, arch, locale, timings, worker identity, harness version).
"""
import glob
import hashlib
import io
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(REPO, "results")
CANON = os.path.join(REPO, "spec", "canonical.md")

EXCLUDE_REASON = "identity/environment/prose"
BEHAVIOUR = [
    "case_group", "create_result", "error_stage", "os_legality_verdict", "read_result",
    "path_form", "longpath_mechanism", "name_encoding", "name_source", "name_landed_as",
    "name_mutated", "roundtrip_ok", "enum_to_stat_agrees", "bytes_written", "bytes_on_disk",
    "phantom", "control_pass", "instrument_red", "deps_direct", "deps_total",
    "mechanism_class", "len_triple",
]
SET_FIELDS = ("create_result", "read_result", "error_stage", "os_legality_verdict",
              "path_form", "longpath_mechanism", "case_group", "attribution_layer")


def load_closed_sets():
    if not os.path.isfile(CANON):
        return None, "spec/canonical.md missing"
    text = io.open(CANON, encoding="utf-8").read()
    sets = {}
    for m in re.finditer(r"(?m)^## \d+\. ([a-z_]+)[^\n]*$", text):
        field = m.group(1)
        if field not in SET_FIELDS:
            continue
        nxt = text.find("\n## ", m.end())
        block = text[m.end(): nxt if nxt > 0 else len(text)]
        sets[field] = set(re.findall(r"`([a-z0-9_]+)`", block))
    return sets, None


def load_cells(path):
    try:
        doc = json.loads(io.open(path, encoding="utf-8").read())
    except (OSError, ValueError) as e:
        return None, "unreadable %s: %s" % (path, str(e)[:80])
    cells = doc.get("cells") if isinstance(doc, dict) else None
    if cells is None:
        cells = [doc]
    out = []
    for c in cells:
        if not isinstance(c, dict) or not c.get("case_id"):
            return None, "malformed cell in %s" % path
        out.append(c)
    return out, None


def discover():
    """port -> {(group, case_id): [cells]} keyed by api_entry.

    Each cell currently exists in two representations (an aggregate per-port file and one file per cell).
    Duplicates are collapsed by (group, case_id, api_entry), and the two representations are cross-checked:
    if the aggregate and the per-cell file disagree, that is a defect worth naming, not a detail.
    """
    if not os.path.isdir(RESULTS):
        return {}, {}, ["results/ missing"], []
    ports, files_seen, problems, xcheck = {}, {}, [], []
    seen = {}
    for entry in sorted(os.listdir(RESULTS)):
        full = os.path.join(RESULTS, entry)
        if entry == "phantom.json":
            continue
        if os.path.isfile(full) and entry.endswith(".json"):
            found, shape = [full], "aggregate"
        elif os.path.isdir(full):
            found = sorted(glob.glob(os.path.join(full, "**", "*.json"), recursive=True))
            shape = "per-cell"
        else:
            continue
        port = re.split(r"[._]", entry, maxsplit=1)[0]
        for f in found:
            cells, err = load_cells(f)
            if err:
                problems.append(err)
                continue
            files_seen[port] = files_seen.get(port, 0) + len(cells)
            for c in cells:
                if not c.get("case_group"):
                    problems.append("%s: cell with empty case_group in %s" % (port, os.path.basename(f)))
                    continue
                key = (c["case_group"], c["case_id"])
                ident = (port, key, str(c.get("api_entry")))
                d = digest(c)[0]
                if ident in seen:
                    prev_d, prev_shape = seen[ident]
                    if prev_d != d:
                        xcheck.append("%s %s/%s: %s vs %s representations disagree"
                                      % (port, key[0], key[1], prev_shape, shape))
                    continue
                seen[ident] = (d, shape)
                ports.setdefault(port, {}).setdefault(key, []).append(c)
    return ports, files_seen, problems, xcheck


def digest(cell):
    sub = {k: cell.get(k, "<absent>") for k in BEHAVIOUR}
    blob = json.dumps(sub, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest(), sub


def main(argv):
    if "--results-dir" in argv:
        i = argv.index("--results-dir")
        globals()["RESULTS"] = os.path.abspath(argv[i + 1])
    globals()["CANON"] = os.environ.get("SG_CANON", CANON)

    sets, err = load_closed_sets()
    if err:
        print("OUTCOME=VOID reason=%s" % err)
        return 4
    ports, files_seen, problems, xcheck = discover()
    for p in problems[:8]:
        print("LOAD-PROBLEM %s" % p)
    if len(ports) < 2:
        print("OUTCOME=NOT-COMPARABLE ports_found=%d (need >=2)" % len(ports))
        return 3

    print("== denominators (distinct cells after collapsing duplicate representations)")
    for n in sorted(ports):
        print("   %-8s cells=%-4d read from %d cell records" % (n, len(ports[n]), files_seen.get(n, 0)))
    print("== the two stored representations of the same cell")
    print("   disagreements=%d" % len(xcheck))
    for line in xcheck[:10]:
        print("   %s" % line)

    print("== closed-set violations")
    bad = []
    for n, cells in sorted(ports.items()):
        for key, lst in sorted(cells.items()):
            for c in lst:
                for f in SET_FIELDS:
                    v = c.get(f)
                    if v is None or f not in sets or not sets[f]:
                        continue
                    if v not in sets[f]:
                        bad.append((n, key, f, v))
    print("   violations=%d" % len(bad))
    for n, key, f, v in bad[:10]:
        print("   %s %s %s=%r not in %s" % (n, "/".join(map(str, key)), f, v, sorted(sets[f])[:6]))

    print("== multi-entry cells (primary not pinned)")
    amb = []
    for n, cells in sorted(ports.items()):
        for key, lst in sorted(cells.items()):
            if len(lst) > 1:
                entries = sorted({str(c.get("api_entry")) for c in lst})
                digests = {digest(c)[0] for c in lst}
                amb.append((n, key, entries, len(digests)))
    print("   cells_with_multiple_entries=%d" % len(amb))
    for n, key, entries, nd in amb[:8]:
        print("   %s %s -> %d entries (%s), %d distinct digests"
              % (n, "/".join(map(str, key)), len(entries), ", ".join(entries)[:60], nd))
    same_only = [a for a in amb if a[3] == 1]
    real_amb = [a for a in amb if a[3] > 1]
    if real_amb:
        print("   OUTCOME blocked: %d cells hold several entries that DISAGREE with each other; "
              "the spec must pin one primary entry per port before cross-port equality means anything"
              % len(real_amb))

    # collapse entries that agree; refuse to collapse entries that disagree
    flat, blocked = {}, []
    for n, cells in ports.items():
        flat[n] = {}
        for key, lst in cells.items():
            ds = {digest(c)[0] for c in lst}
            if len(ds) == 1:
                flat[n][key] = lst[0]
            else:
                blocked.append((n, key))
    if bad:
        print("OUTCOME=NOT-COMPARABLE reason=status_words_outside_closed_set")
        return 3
    if blocked:
        print("OUTCOME=NOT-COMPARABLE reason=ambiguous_entries cells=%d ports=%s"
              % (len(blocked), sorted({b[0] for b in blocked})))
        return 3

    names = sorted(flat)
    ref = names[0]
    ref_keys = set(flat[ref])
    denom_ok = True
    for n in names[1:]:
        ks = set(flat[n])
        if ks != ref_keys:
            denom_ok = False
            print("DENOMINATOR_MISMATCH %s vs %s: only_in_%s=%d only_in_%s=%d shared=%d"
                  % (n, ref, n, len(ks - ref_keys), ref, len(ref_keys - ks), len(ks & ref_keys)))
            for k in sorted(list(ks - ref_keys))[:6]:
                print("     only in %s: %s" % (n, "/".join(map(str, k))))
            for k in sorted(list(ref_keys - ks))[:6]:
                print("     only in %s: %s" % (ref, "/".join(map(str, k))))
    if not denom_ok:
        print("OUTCOME=NOT-COMPARABLE reason=denominators_differ "
              "(comparing different question sets and calling it agreement is what this gate exists to refuse)")
        return 3

    missing = [(n, f) for n in names for f in BEHAVIOUR
               if not any(f in c for c in flat[n].values())]
    if missing:
        print("fields_never_emitted_by_a_port=%d" % len(missing))
        for n, f in missing[:12]:
            print("   port %s never emits %r" % (n, f))
        print("OUTCOME=NOT-COMPARABLE reason=ports_do_not_emit_the_same_fields")
        return 3

    per_port, subs = {}, {}
    for n in names:
        subs[n] = {k: digest(c)[1] for k, c in flat[n].items()}
        joined = "\n".join("%s %s" % ("/".join(map(str, k)), digest(flat[n][k])[0]) for k in sorted(flat[n]))
        per_port[n] = hashlib.sha256(joined.encode("utf-8")).hexdigest()
        print("   %-8s whole_run_digest=%s cells=%d" % (n, per_port[n][:16], len(flat[n])))
    if len(set(per_port.values())) == 1:
        print("OUTCOME=PASS digests_equal=%d/%d" % (len(names), len(names)))
        return 0
    disagree = [k for k in sorted(flat[ref]) if len({digest(flat[n][k])[0] for n in names}) > 1]
    print("OUTCOME=RED disagreeing_cells=%d/%d" % (len(disagree), len(flat[ref])))
    for k in disagree[:15]:
        diffs = []
        for f, v in subs[ref][k].items():
            for n in names[1:]:
                if subs[n][k].get(f) != v:
                    diffs.append("%s %s:%r vs %s:%r" % (f, ref, v, n, subs[n][k].get(f)))
        print("   %s | %s" % ("/".join(map(str, k)), "; ".join(diffs[:3]) or "digest differs"))
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
