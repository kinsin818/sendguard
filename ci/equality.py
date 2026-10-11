#!/usr/bin/env python3
"""sendguard equality gate.

Claim under test: one frozen spec, N ports, byte-identical behaviour.

Exit codes:
  0  every required cell was run by every port and all ports agree on the behavioural digest
  1  ports disagree (named cells, named fields)
  3  not comparable (no cell was run by every port / a port has no canonical face / a cell has several
     entries and no primary is pinned / a status word is outside the closed set) OR INCOMPLETE (the ports
     that did answer agree on every shared cell, but the required list is not covered) -- both are results,
     neither is a pass
  4  the gate could not load its inputs (never reportable as a measurement)

Cell identity for the equality claim is (case_group, canonical case_id, declared sub-identity). `api_entry`
is deliberately NOT part of that identity: it is a language-specific name, so including it makes cross-port
comparison impossible by construction (measured: three ports, intersection of keys = 0). When a port emits
several entries for one cell, the contract pins which one is its primary; until it does, the gate refuses
to pick. Case-id spellings the six ports invented are folded by `canonical_case_id`, which never guesses:
see `spec/cell-identity.md` section 8 for the rules and for what stays outside the list.

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
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(REPO, "results")
# written out rather than typed inline: a literal backslash in a source line has been the cause
# of two broken instruments in this repository tonight
NL = chr(10)
BSLASH = chr(92)
FWD = "/"


def rel(path):
    r"""A path relative to the repository, or the absolute path if it is not under it.

    Measured: the fixtures live wherever the caller put the scratch root, which was `C:\Users\...\Temp`
    while the repository is on `D:`. `os.path.relpath` raises across drives, and a gate that crashes is
    reported by the harness as rc=1 - which reads exactly like the gate refusing a bad run. The instrument
    has to survive a foreign scratch root or it turns a tool failure into a fake measurement.
    """
    try:
        return os.path.relpath(path, REPO).replace(BSLASH, FWD)
    except ValueError:
        return str(path)
CANON = os.path.join(REPO, "spec", "canonical.md")
# a fixture may bring its own question set; the shipped default is the committed manifest
REQUIRED = os.environ.get("SG_REQUIRED_CELLS") or os.path.join(REPO, "spec", "cells-required.json")

EXCLUDE_REASON = "identity/environment/prose"
BEHAVIOUR = [
    "case_group", "create_result", "error_stage", "os_legality_verdict", "read_result",
    "path_form", "longpath_mechanism", "name_source", "name_landed_as",
    "name_mutated", "roundtrip_ok", "enum_to_stat_agrees", "bytes_written", "bytes_on_disk",
    "phantom", "deps_direct", "deps_total", "mechanism_class", "len_triple",
]
# `name_encoding` and `length_unit` were in this list until rev6 and are out on purpose: they record how a
# port wrote a value down, not what it measured. Measured in the rev5 run, they turned four ports that had
# recorded the same control cell identically (ok / 28 / 28 / read ok / legal, same payload digest) into a
# reported "disagreement".
# `control_pass` and `instrument_red` left this list in rev6 too: they are health declarations, and the
# health leg above already reads them. Comparing them as behaviour turned a port that does not stamp
# control_pass onto a trap cell into a "disagreement" about that trap cell.

# The claim under test decides which of these fields may differ. A port answers two different questions
# with one record:
#   VERDICT  -- is this name creatable here, by which mechanism, and did the name survive? This is the
#               checker's answer, and six independent implementations of one spec must give the same bytes.
#   PROBE    -- what did *this language's* standard library do when asked? That is allowed to differ --
#               it is the matrix, it is the appendix, and six ports agreeing about what Go's os.Create
#               returns would be the suspicious outcome, not the good one.
# Classifying them together as "behaviour" is what made the gate call 29/29 cells a failure.
VERDICT_FIELDS = ["os_legality_verdict", "mechanism_class", "phantom", "roundtrip_ok",
                  "name_mutated", "enum_to_stat_agrees", "len_triple",
                  "bytes_written", "bytes_on_disk", "name_landed_as"]
PROBE_FIELDS = [f for f in BEHAVIOUR if f not in VERDICT_FIELDS
                and f not in ("case_group", "name_source", "path_form")]
CELL_LEVEL_FIELDS = ("path_form",)                         # a different question entirely
FIELD_LEVEL_FIELDS = {"verdict_via": "os_legality_verdict"}  # a different channel for one field only
# `case_group` and `name_source` are identity, not answers: the group is in the cell key and the source
# name is the pinned input. `path_form` and `verdict_via` name the question a port actually asked (plain
# path vs `\\?\`, Win32 vs the .NET or POSIX layer), so a difference there does not make two ports
# disagree -- it makes their answers about different things, and the gate says so instead of judging it. Asking ports to agree about them twice would only add noise.
SET_FIELDS = ("create_result", "read_result", "error_stage", "os_legality_verdict",
              "path_form", "longpath_mechanism", "case_group", "attribution_layer")

# per spec/cell-identity.md section 1: a cell that is run more than once must carry the varying
# dimension as a named field, and that field is part of the identity. Filenames are not identity.
SUB_FIELDS = ("base_len", "builder", "reader", "packer", "extractor")
# path_form is an identity dimension for `len` cells only (plain and extended are two measurements);
# elsewhere it is a behaviour field and putting it in the key would split identical cells (rev5).


def sub_identity(cell):
    """Declared by the cell when it knows better than this list; otherwise fall back to the known
    dimensions. A port that adds a dimension must be able to say so, or its cells collide."""
    # dimensions are a closed list; a port may not invent its own identity shape, because two ports
    # encoding the same dimension differently silently become two different cells
    declared = cell.get("sub_identity")
    extra = {}
    if isinstance(declared, dict):
        extra = {k: v for k, v in declared.items() if v is not None}
    elif declared not in (None, "", {}, []):
        cell.setdefault("_contract_defects", []).append(
            "sub_identity must be an object of the declared dimensions, got %s" % type(declared).__name__)
    fields = list(SUB_FIELDS)
    if cell.get("case_group") == "len":
        fields.append("path_form")
    vals = {}
    for f in fields:
        if cell.get(f) is not None:
            vals[f] = cell[f]
    for f, v in extra.items():
        if f in fields:
            vals[f] = v
    parts = sorted(vals.items())
    _ = parts  # keep the shape of the loop below unchanged
    return tuple((k, v if not isinstance(v, dict) else json.dumps(v, sort_keys=True))
                 for k, v in parts)


RE_MEMBER = re.compile(r"^(T\d{2})[-_]?([a-h])$")
RE_BLIND = re.compile(r"^(?:BLIND[-_]|T-BLIND[-_]|B)(\d{1,2})$")
RE_GRID = re.compile(r"^(T1[78])[-_](?:GRID[-_])?(?:PLAIN[-_]|EXTENDED[-_])?B(\d{1,3})[-_]L(\d{1,3})$")


def canonical_case_id(cell):
    """Fold the spellings six ports invented for the same question onto the id the frozen spec prints.

    Measured drift (rev5 run, not hypothetical): the same blind sample was published as `B1`,
    `BLIND-1` and `T-BLIND-1`; the same `sample_hex_list` member as `T09a` and `T09-m1`; a length rung
    point as `T17-GRID-B120-L137`. Left unfolded these read as "cell missing", which is a naming
    artefact, not a measurement.

    This refuses to guess. A bare family id (`T09`, no member) stays as it is: the record does not say
    which member it measured, so matching it to `T09-m1` would be the gate inventing data. A grid id is
    only folded when the base length written in the id equals the cell's own `base_len` -- an id that
    contradicts its own payload is left outside the list.
    """
    raw = cell.get("case_id")
    if not isinstance(raw, str):
        return raw
    if cell.get("case_group") == "blind":
        m = RE_BLIND.match(raw)
        if m:
            return "B%d" % int(m.group(1))
        return raw
    m = RE_MEMBER.match(raw)
    if m:
        return "%s-m%d" % (m.group(1), ord(m.group(2)) - ord("a") + 1)
    m = RE_GRID.match(raw)
    if m and str(m.group(2)) == str(cell.get("base_len")):
        return m.group(1)
    return raw


def key_of(cell):
    return (cell.get("case_group") or "?", canonical_case_id(cell), sub_identity(cell))


def fmt(k):
    g, c, s = k
    return "%s/%s%s" % (g, c, ("[" + ",".join("%s=%s" % p for p in s) + "]") if s else "")


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


RE_CANON_FACE = re.compile(r"^([a-z]+)\.(windows|macos|ubuntu)\.(x64|arm64)$")


def discover():
    """port -> {(group, case_id): [cells]} keyed by api_entry.

    Only the canonical face of a port is read: `<port>.<os>.<arch>`, the naming this repository pinned in
    `spec/cell-identity.md`. Measured reason (rev5 run): `results/` carried `python`, `python.windows.x64`,
    `results/node` and `node.windows.22.22.2.json` at once -- old and new contract revisions of the same
    port. Merging them inflates one port's denominator with cells produced under a different schema, and
    splitting them reads one port as two disagreeing ports. Either way the denominator stops meaning
    "the cells this port ran under the frozen spec", so a non-canonical face is named and excluded, not
    folded in.

    Within the canonical face each cell exists in two representations (an aggregate file and one file per
    cell); duplicates collapse by (port, key, api_entry) and the two representations are cross-checked --
    if they disagree that is a defect worth naming, not a detail.
    """
    if not os.path.isdir(RESULTS):
        return {}, {}, ["results/ missing"], [], []
    ports, files_seen, problems, xcheck, skipped = {}, {}, [], [], []
    extra_count = {}
    seen = {}
    for entry in sorted(os.listdir(RESULTS)):
        full = os.path.join(RESULTS, entry)
        if entry == "phantom.json":
            continue
        m = RE_CANON_FACE.match(entry)
        if not m or not os.path.isdir(full):
            n = 0
            if os.path.isdir(full):
                n = len(glob.glob(os.path.join(full, "**", "*.json"), recursive=True))
            elif full.endswith(".json"):
                n = 1
            skipped.append((entry, n))
            continue
        port = m.group(1)
        found = sorted(glob.glob(os.path.join(full, "**", "*.json"), recursive=True))
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
                if c.get("extra") is True:      # promised by NOTICE-rev3, implemented now:
                    extra_count[port] = extra_count.get(port, 0) + 1
                    continue                    # an extra cell is published, never compared
                key = key_of(c)
                ident = (port, key, str(c.get("api_entry")))
                d = digest(c)[0]
                if ident in seen:
                    prev = seen[ident]
                    if prev[0] != d:
                        xcheck.append("%s %s: two files of the same port disagree (%s vs %s)"
                                      % (port, fmt(key), os.path.basename(prev[2]),
                                         os.path.basename(f)))
                    continue
                seen[ident] = (d, "per-cell", f)
                ports.setdefault(port, {}).setdefault(key, []).append(c)
    ports["_extra_counts"] = extra_count
    return ports, files_seen, problems, xcheck, skipped


def digest(cell):
    sub = {k: cell.get(k, "<absent>") for k in BEHAVIOUR}
    blob = json.dumps(sub, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest(), sub


# ---------------------------------------------------------------- representation -> canonical value
# Measured in the rev5 run: four ports recorded the same control cell correctly and identically
# (create ok, 28 written, 28 on disk, read ok, legal, same payload digest) and the gate still called it
# a disagreement, because one port wrote the landed name as hex (`7265706f72742d323032362e747874`),
# another as text (`report-2026.txt`), one wrote the length triple as a dict, another as "15/15/15",
# and one left it out. Those are representations of one fact, not facts in conflict -- and a gate that
# reports them as conflict would bury the ones that are real. Canonicalisation is therefore done here,
# once, and it never invents a value: a field a port did not record stays NOT-RECORDED.

NAMEISH = ("name_source", "name_landed_as", "requested_name")
HEXISH = re.compile(r"^(?:[0-9a-fA-F]{2})+$")


def canon_name(value):
    """Fold hex-encoded and literal spellings of one name onto the same token.

    Returns ('h', utf8hex) when the bytes decode to text the gate can name unambiguously,
    ('r', rawhex) when they are raw bytes that do not decode (a name a port could not losslessly
    represent -- that is data, and it must stay visible), or ('x', None) when there is no value.
    """
    if value is None or value == "":
        return ("x", None)
    s = value if isinstance(value, str) else str(value)
    raw = None
    if HEXISH.match(s) and len(s) >= 6:
        try:
            raw = bytes.fromhex(s)
        except ValueError:
            raw = None
    if raw is None:
        try:
            return ("h", s.encode("utf-8", "surrogatepass").hex())
        except Exception:
            return ("r", s.encode("utf-8", "replace").hex())
    # hex payload: try the two encodings the spec allows, and the utf-16le ASCII shape, and utf-8
    for dec, form in (("utf-16-le", None), ("utf-8", None)):
        if dec == "utf-16-le" and not (len(raw) % 2 == 0 and len(raw) >= 4 and raw[1::2] == b"\x00" * (len(raw) // 2)):
            continue
        try:
            text = raw.decode(dec)
        except (UnicodeDecodeError, ValueError):
            continue
        if form is None:
            form = dec
        return ("h", text.encode("utf-8", "surrogatepass").hex())
    return ("r", raw.hex())


def name_forms(value):
    """Every meaning a recorded name could have, as a set of 'form:hex' tokens.

    A port that writes `616161...` and a port that writes `aaaaaa...` are describing one name; a port that
    writes `aaaaaa...` for a name that is really the bytes 0x61 0x61 has to be allowed to say so. The set is
    the honest representation, and agreement is set intersection - not a guess about which spelling is
    'the' canonical one.
    """
    if value is None or value == "":
        return frozenset()
    s = value if isinstance(value, str) else str(value)
    forms = set()
    try:
        forms.add("lit:" + s.encode("utf-8", "surrogatepass").hex())
    except Exception:
        pass
    if HEXISH.match(s) and len(s) >= 2 and len(s) % 2 == 0:
        try:
            raw = bytes.fromhex(s)
        except ValueError:
            raw = None
        if raw is not None:
            forms.add("raw:" + raw.hex())
            for codec in ("utf-8", "utf-16-le", "gbk", "cp437"):
                try:
                    text = raw.decode(codec)
                except (UnicodeDecodeError, ValueError, LookupError):
                    continue
                if codec in ("utf-8", "utf-16-le"):
                    forms.add("lit:" + text.encode("utf-8", "surrogatepass").hex())
                else:
                    forms.add("%s:%s" % (codec.replace("-", "_"), raw.hex()))
    return frozenset(forms)


TRIPLE_KEYS = (("code_points", "cp", "codepoint", "code_points"),
               ("utf16_code_units", "utf16", "utf16_code_units", "u16"),
               ("utf8_bytes", "bytes", "utf8_bytes", "b"))


def _pick(d, names):
    for n in names:
        if n in d:
            return d[n]
    return None


def raw_name_value(field, cell):
    """The value exactly as the port wrote it, following the four aliases one fact was filed under."""
    if field == "name_landed_as":
        for alt in LANDED_ALIASES:
            if cell.get(alt) not in (None, ""):
                return cell[alt]
        return None
    return cell.get(field)


def canon_triple(value):
    """`{code_points:15,utf16_code_units:15,utf8_bytes:15}`, `15/15/15`, `[15,15,15]` and
    `{requested:{...},landed:{...}}` are four spellings of one measurement (measured, rev5 run);
    `None` is not a fifth spelling, it is an absence, and it stays NOT-RECORDED."""
    if value is None:
        return None
    if isinstance(value, dict):
        direct = [_pick(value, k) for k in TRIPLE_KEYS]
        if all(d is not None for d in direct):
            return ("t", "/".join(str(d) for d in direct))
        nested = [_pick(value, ("requested", "requested_name", "asked")),
                  _pick(value, ("landed", "landed_name", "on_disk"))]
        found = set()
        for sub in nested:
            if isinstance(sub, dict):
                parts = [_pick(sub, k) for k in TRIPLE_KEYS]
                if all(p is not None for p in parts):
                    found.add("/".join(str(p) for p in parts))
            elif isinstance(sub, (list, tuple)) and len(sub) == 3:
                found.add("/".join(str(x) for x in sub))
            elif isinstance(sub, str) and re.fullmatch(r"\d+/\d+/\d+", sub):
                found.add(sub)
        if len(found) == 1:
            return ("t", found.pop())
        if len(found) > 1:
            # a port that measured two different triples for one name recorded two facts; keep both,
            # sorted, so another port with one of them is not silently judged equal
            return ("t2", "|".join(sorted(found)))
        return ("raw", json.dumps(value, sort_keys=True))
    if isinstance(value, (list, tuple)):
        if len(value) == 3 and all(isinstance(x, int) for x in value):
            return ("t", "/".join(str(x) for x in value))
        return ("raw", json.dumps(list(value), sort_keys=True))
    if isinstance(value, str):
        m = re.fullmatch(r"\s*(\d+)\s*/\s*(\d+)\s*/\s*(\d+)\s*", value)
        if m:
            return ("t", "/".join(m.groups()))
        return ("raw", value)
    return ("raw", json.dumps(value, sort_keys=True))


LANDED_ALIASES = ("name_landed_as", "name_landed_as_hex", "path_view_landed_as", "landed_name")


def canon_value(field, cell):
    if field in NAMEISH:
        if field == "name_landed_as":
            for alt in LANDED_ALIASES:          # five ports filed the same fact under four names
                if cell.get(alt) not in (None, ""):
                    return canon_name(cell[alt])
            return ABSENT
        return canon_name(cell.get(field))
    if field == "len_triple":
        return canon_triple(cell.get(field))
    if field not in cell:
        return ABSENT
    v = cell[field]
    if isinstance(v, bool):
        return ("b", v)
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return ("n", int(v) if float(v).is_integer() else v)
    if isinstance(v, str):
        return ("s", v.strip() if field != "error_stage" else v.strip().lower().replace("-", "_"))
    if v is None:
        return ("null", None)
    return ("j", json.dumps(v, sort_keys=True, ensure_ascii=False))


ABSENT = ("absent", None)


def main(argv):
    if "--results-dir" in argv:
        i = argv.index("--results-dir")
        globals()["RESULTS"] = os.path.abspath(argv[i + 1])
    globals()["CANON"] = os.environ.get("SG_CANON", CANON)

    sets, err = load_closed_sets()
    if err:
        print("OUTCOME=VOID reason=%s" % err)
        return 4
    ports, files_seen, problems, xcheck, skipped = discover()
    extras = ports.pop("_extra_counts", {})
    declared = sorted(json.load(io.open(REQUIRED, encoding="utf-8"))["primary_entry_per_port"])
    empty = [d for d in declared if d not in ports or not ports.get(d)]
    if empty:
        print("== declared ports with no readable canonical face")
        for d in empty:
            print("   FACE-MISSING %s - spec/cells-required.json declares a primary entry for this port,"
                  % d)
            print("        so the contract expects it; its absence is reported here rather than the port"
                  " list quietly shrinking to the ports that did answer.")
    for p in problems[:8]:
        print("LOAD-PROBLEM %s" % p)
    if skipped:
        print("== non-canonical faces excluded (naming rule: <port>.<os>.<arch>)")
        for e, n in skipped:
            print("   %-30s %d cell records" % (e, n))
        print("   excluded_faces=%d  These faces are on disk, published, and not compared;"
              " they were produced under an earlier contract revision or a different naming rule."
              % len(skipped))
    if len(ports) < 2:
        print("OUTCOME=NOT-COMPARABLE ports_found=%d (need >=2)" % len(ports))
        return 3

    # the required list defines the comparison set; cells outside it are counted, not compared
    man = json.load(io.open(REQUIRED, encoding="utf-8"))
    req_keys = set()
    for r in man["required_cells"]:
        si = tuple(sorted((r.get("sub_identity") or {}).items()))
        req_keys.add((r["case_group"], r["case_id"], si))
    not_required = {}
    tapi_cells = {}
    for n in list(ports):
        keep = {}
        for k, lst in ports[n].items():
            if k[0] == "tapi":
                tapi_cells.setdefault(n, []).append(k)
                continue
            if k not in req_keys:
                not_required[n] = not_required.get(n, 0) + 1
                continue
            keep[k] = lst
        ports[n] = keep
    print("== denominators (distinct cells after collapsing duplicate representations)")
    if extras:
        print("   excluded as extra: %s" % " ".join("%s=%d" % kv for kv in sorted(extras.items())))
    if not_required:
        print("   outside the required list (counted, not compared): %s"
              % " ".join("%s=%d" % kv for kv in sorted(not_required.items())))
    if tapi_cells:
        print("   tapi cells held out of the digest (per-language by construction): %s"
              % " ".join("%s=%d" % (k, len(v)) for k, v in sorted(tapi_cells.items())))
    for n in sorted(ports):
        print("   %-8s cells=%-4d read from %d cell records" % (n, len(ports[n]), files_seen.get(n, 0)))

    # A record that declares its own failure is not a measurement. Checking this before denominators,
    # because a run that is 62/72 self-declared red must not be allowed to reach a comparison at all.
    CRASH = re.compile(r"is not defined|ReferenceError|TypeError|SyntaxError|Cannot find (module|name)", re.I)
    dead = []
    print("== self-declared health per port")
    for n in sorted(ports):
        red = crash = cp_false = no_truth = 0
        for key, lst in ports[n].items():
            for c in lst:
                if c.get("instrument_red") is True or c.get("instrument_conflict") is True:
                    red += 1
                if c.get("control_pass") is False:
                    cp_false += 1
                if CRASH.search(str(c.get("error_message") or "")):
                    crash += 1
                if c.get("create_result") == "ok" and c.get("bytes_on_disk") is None:
                    no_truth += 1
        print("   %-8s instrument_red_or_conflict=%-3d control_pass_false=%-3d "
              "runtime_crash_text_in_error_message=%-3d create_ok_without_disk_truth=%d"
              % (n, red, cp_false, crash, no_truth))
        if red or cp_false or crash:
            dead.append((n, red, cp_false, crash))
    for n, red, cp_false, crash in dead:
        print("   PORT %s is INSTRUMENT-RED (%d red-flagged, %d failed controls, %d crash records) "
              "-> excluded from comparison; its cells are not evidence" % (n, red, cp_false, crash))
    live = [n for n in sorted(ports) if n not in {d[0] for d in dead}]
    if len(live) < 2:
        print("OUTCOME=NOT-COMPARABLE reason=self_declared_instrument_red live_ports=%d "
              "(a run that marks itself red may not be compared, only reported)" % len(live))
        return 3
    for n in [d[0] for d in dead]:
        ports.pop(n, None)
        files_seen.pop(n, None)
    print("   comparing only the live ports: %s" % " ".join(sorted(ports)))
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
        print("   %s %s %s=%r not in %s" % (n, fmt(key), f, v, sorted(sets[f])[:6]))

    # the contract pins one primary entry per (port, trap); the rest is entry_spread - data, not a
    # comparison blocker. Only a cell with no primary entry is genuinely ambiguous.
    prim = json.load(io.open(REQUIRED,
                             encoding="utf-8"))["primary_entry_per_port"]
    print("== multi-entry cells (entry_spread, primary chosen per contract)")
    spread = 0
    spread_disagree = 0
    no_primary = []
    for n, cells in sorted(ports.items()):
        want = prim.get(n)
        for key, lst in sorted(cells.items()):
            if len(lst) > 1:
                spread += 1
                if len({digest(c)[0] for c in lst}) > 1:
                    spread_disagree += 1
                if not any(str(c.get("api_entry")) == want for c in lst):
                    no_primary.append((n, fmt(key), want))
    print("   cells_with_multiple_entries=%d  of_which_spread_disagrees=%d  cells_missing_primary=%d"
          % (spread, spread_disagree, len(no_primary)))
    for n, k, want in no_primary[:8]:
        print("   %s %s has no cell with api_entry=%r -> cannot pick the port's answer" % (n, k, want))

    flat, blocked = {}, []
    for n, cells in ports.items():
        want = prim.get(n)
        flat[n] = {}
        for key, lst in cells.items():
            pick = [c for c in lst if str(c.get("api_entry")) == want]
            if len(pick) == 1:
                flat[n][key] = pick[0]
            elif len(lst) == 1:
                flat[n][key] = lst[0]
            else:
                blocked.append((n, key))
    if bad:
        print("OUTCOME=NOT-COMPARABLE reason=status_words_outside_closed_set")
        return 3
    if blocked:
        print("OUTCOME=NOT-COMPARABLE reason=no_primary_entry_for_multi_entry_cells cells=%d ports=%s"
              % (len(blocked), sorted({b[0] for b in blocked})))
        return 3
    if not flat:
        print("OUTCOME=NOT-COMPARABLE reason=no_required_cell_was_run "
              "(every cell on disk is outside the required list, so the ports answered no shared"
              " question -- the keys, not the answers, are the problem)")
        return 3

    names = sorted(flat)
    all_keys = set()
    for n in names:
        all_keys |= set(flat[n])
    shared = set(flat[names[0]])
    for n in names[1:]:
        shared &= set(flat[n])
    req_short = {n: sorted(req_keys - set(flat[n])) for n in names}
    short_total = sum(len(v) for v in req_short.values())
    print("== coverage of the required list (44 cells define the question set)")
    print("   cells_run_by_every_port=%d  cells_anywhere=%d  required_cells_missing=%d"
          % (len(shared), len(all_keys), short_total))
    for n in names:
        if req_short[n]:
            print("   %-11s missing %d: %s" % (n, len(req_short[n]),
                  ", ".join(fmt(k) for k in req_short[n][:6])
                  + ("" if len(req_short[n]) <= 6 else " ...(+%d)" % (len(req_short[n]) - 6))))
    if not shared:
        print("OUTCOME=NOT-COMPARABLE reason=no_cell_was_run_by_every_port "
              "(there is no question all the ports answered, so there is nothing to compare)")
        return 3
    if short_total:
        print("   the comparison below runs on the %d cells every port answered; a cell a port did not"
              % len(shared))
        print("   answer is reported as missing, never as agreement.")

    cmp = {n: {k: flat[n][k] for k in shared} for n in names}

    def recorded(field, cell):
        v = canon_value(field, cell)
        if v == ABSENT or v == ("x", None) or v == ("null", None):
            return None            # a JSON null is a port saying "no value", not a fifth answer
        return v

    def pinned_input(port, k):
        c = cmp[port][k]
        return canon_name(c.get("name_source") or c.get("requested_name") or c.get("name_landed_as"))

    def compare(fields, cell):
        """returns (agree, values) per field over the ports that recorded it"""
        out = {}
        for f in fields:
            vs = {n: recorded(f, cell[n]) for n in names}
            rec = {n: v for n, v in vs.items() if v is not None}
            out[f] = rec
        return out

    # ---- same question, same input: a cell whose input differs between ports is not comparable at all
    unpinned = []
    for k in sorted(shared):
        forms = {}
        for n in names:
            c = cmp[n][k]
            raw = c.get("name_source") or c.get("requested_name") or c.get("name_landed_as")
            forms[n] = canon_name(raw)
        kinds = {f for f in forms.values() if f[0] != "x"}
        if len(kinds) > 1:
            unpinned.append((k, forms))
    print("== input pinning (the frozen sample must be the same bytes in every port)")
    print("   cells_with_different_inputs=%d" % len(unpinned))
    for k, forms in unpinned[:8]:
        print("   %s | %s" % (fmt(k),
              " ".join("%s=%s" % (n, (forms[n][1] or "-")[:22]) for n in names)))
    if unpinned:
        print("   these cells are excluded from the agreement count: comparing two different questions and")
        print("   calling the difference a port's behaviour would be the gate manufacturing a finding.")

    unpinned_keys = {k for k, _ in unpinned}
    # ---- a port that addressed the path in a different form asked a different question (the cell is out);
    # a port that reached the legality verdict through a different *channel* loses only that field, because
    # the rest of its record still describes the same bytes on the same disk.
    asked = {}
    for k in sorted(shared):
        if k in unpinned_keys:
            continue
        vs = {}
        for f in tuple(CELL_LEVEL_FIELDS) + tuple(FIELD_LEVEL_FIELDS):
            vs[f] = {n: recorded(f, cmp[n][k]) for n in names}
        asked[k] = vs
    incomparable = sorted(k for k in asked
                          if any(len({str(v) for v in vs.values() if v is not None}) > 1
                                 for f, vs in asked[k].items() if f in CELL_LEVEL_FIELDS))
    abstain = {}
    for k in asked:
        for src, gated in FIELD_LEVEL_FIELDS.items():
            vals = {n: v for n, v in asked[k][src].items() if v is not None}
            if len({str(v) for v in vals.values()}) <= 1:
                continue
            counts = {}
            for v in vals.values():
                counts[str(v)] = counts.get(str(v), 0) + 1
            majority = max(counts, key=lambda x: counts[x])
            if counts[majority] * 2 <= len(vals):
                # no majority channel: the field is not comparable for anybody on this cell, and picking
                # the first value as "the" channel would be the gate inventing a convention
                abstain.setdefault(k, {}).setdefault(gated, set()).update(vals)
            else:
                abstain.setdefault(k, {}).setdefault(gated, set()).update(
                    n for n, v in vals.items() if str(v) != majority)
    print("== cells and fields the ports did not ask the same way")
    print("   cells_excluded_whole(path_form differs)=%d/%d" % (len(incomparable), len(asked)))
    for k in incomparable[:8]:
        for f in CELL_LEVEL_FIELDS:
            vals = {n: v for n, v in asked[k][f].items() if v is not None}
            if len({str(v) for v in vals.values()}) > 1:
                print("   %s %s -> %s" % (fmt(k), f,
                      " ".join("%s=%s" % (n, str(v)[1:-1])[:20] for n, v in sorted(vals.items()))))
    print("   cells_with_a_field_dropped_for_some_ports(channel differs)=%d" % len(abstain))
    for k in sorted(abstain)[:6]:
        for gated, who in sorted(abstain[k].items()):
            print("   %s %s not compared for %s (their other verdict fields still are)"
                  % (fmt(k), gated, ",".join(sorted(who))))

    skip = unpinned_keys | set(incomparable)
    cells_live = [k for k in sorted(shared) if k not in skip]

    def truncation(k, f, rec):
        """Which ports wrote a landed name that is a strict prefix of the pinned input.

        Printed as a note, never used to delete a value. Measured in the rev6 run: three ports recorded the
        landed name of `report-2026.txt` as the hex of `report-2026`, and `invoice_FINAL_2026.xls` as the hex
        of `invoice_FIN` - a fixed-width cut - while the same record said `name_mutated=false`. Two other
        ports wrote the whole name as text.

        The same shape also occurs for a true reason: on `trail.` and `trailsp ` Windows really drops the
        trailing character, so the honest landed name IS a prefix. From the recorded bytes the two cases are
        indistinguishable, so this function no longer removes anything from the comparison - it names the
        rows a reader should check against the port's own length fields, and the disagreement stands whether
        or not the check clears it. A rule that cannot tell a finding from an artefact must not be allowed
        to choose which one to delete.
        """
        if f not in NAMEISH:
            return set()
        want = {n: pinned_input(n, k) for n in rec}
        bad = set()
        for n, v in rec.items():
            src = want.get(n)
            if v[0] != "h" or not v[1] or src[0] not in ("h", "r") or not src[1]:
                continue
            if v[1] == src[1][:len(v[1])] and len(v[1]) < len(src[1]) and len(v[1]) % 2 == 0:
                bad.add(n)
        return bad

    def sweep(fields):
        dis, nr, agree, trunc, absn, multiform = [], [], 0, [], [], []
        for k in cells_live:
            for f, rec in compare(fields, {n: cmp[n][k] for n in names}).items():
                if not rec:
                    continue
                drop = abstain.get(k, {}).get(f, set())
                if drop:
                    absn.append((k, f, sorted(drop)))
                    rec = {n: v for n, v in rec.items() if n not in drop}
                    if not rec:
                        continue
                cut = truncation(k, f, rec)
                if cut:
                    trunc.append((k, f, sorted(cut)))
                # an abstaining port is not a port that failed to record: it asked a different channel,
                # and counting it in `not_recorded` would double-report the same fact under two words
                expected = set(names) - abstain.get(k, {}).get(f, set())
                if f in NAMEISH:
                    # forms come from the RAW recorded value, not from canon_value's answer: the whole
                    # point is that two ports' raw spellings can mean the same name even when the single
                    # token each one canonicalises to differs
                    sets = {n: name_forms(raw_name_value(f, cmp[n][k])) for n in rec}
                    sets = {n: (s if s else frozenset({str(rec[n])})) for n, s in sets.items()}
                    common = set.intersection(*[set(s) for s in sets.values()]) if sets else set()
                    # only report a cross-form match when the naive spelling comparison would have called
                    # it a disagreement: every hex-encoded value has several forms by construction, and
                    # printing all of them would bury the cases this rule actually rescues
                    naive_disagree = len({str(v) for v in rec.values()}) > 1
                    if naive_disagree and common:
                        multiform.append((k, f, sorted(rec)))
                    if not common:
                        dis.append((k, f, rec))
                        continue
                    if len(sets) >= len(expected):
                        agree += 1
                        continue
                    nr.append((k, f, sorted(expected - set(sets))))
                    continue
                if len({str(v) for v in rec.values()}) > 1:
                    dis.append((k, f, rec))
                elif len(rec) >= len(expected) or (expected and set(rec) >= expected):
                    agree += 1
                else:
                    nr.append((k, f, sorted(expected - set(rec))))
        return dis, nr, agree, trunc, absn, multiform

    vdis, vnr, vagree, vtrunc, vabs, vmulti = sweep(VERDICT_FIELDS)
    pdis, pnr, pagree, ptrunc, pabs, pmulti = sweep(PROBE_FIELDS)

    print("== verdict equality (the claim under test: six independent ports, same checker answer)")
    print("   cells_compared=%d fields=%d fact_cells=%d agree=%d disagree=%d not_recorded=%d "
          "truncated_value=%d channel_abstentions=%d name_cross_form_agreements=%d"
          % (len(cells_live), len(VERDICT_FIELDS), vagree + len(vdis) + len(vnr), vagree,
             len(vdis), len(vnr), len(vtrunc), len(vabs), len(vmulti)))
    for k, f, who in vmulti[:6]:
        print("   NAME-CROSS-FORM-AGREE %s %s: these ports wrote the same name in different encodings "
              "(hex vs literal); they agree by shared meaning, and the gate says so out loud: %s"
              % (fmt(k), f, ",".join(who)))
    for k, f, who in vtrunc[:8]:
        print("   PREFIX-SHAPED %s %s by %s - check each against that port's own length fields:"
              % (fmt(k), f, ",".join(who)))
        print("        a trailing character the OS dropped is a finding; a hex string cut at a display"
              " width is a record that contradicts its own name_mutated flag")
    for k, f, rec in vdis[:20]:
        parts = sorted({"%s:%s" % (n, str(v)[1:-1])[:26] for n, v in rec.items()})
        print("   VERDICT-DISAGREE %s %s -> %s" % (fmt(k), f, " | ".join(parts)))
    for k, f, who in vnr[:12]:
        print("   VERDICT-NOT-RECORDED %s %s by %s" % (fmt(k), f, ",".join(who)))

    print("== probe spread (published, not judged: what each language's own standard library did)")
    print("   fields=%d agree=%d differ=%d not_recorded=%d"
          % (len(PROBE_FIELDS), pagree, len(pdis), len(pnr)))
    for k, f, rec in pdis[:8]:
        parts = sorted({"%s:%s" % (n, str(v)[1:-1])[:24] for n, v in rec.items()})
        print("   %s %s -> %s" % (fmt(k), f, " | ".join(parts)))

    identical_cells = [k for k in cells_live if not any(dk == k for dk, _, _ in vdis)]
    clean_cells = [k for k in identical_cells if not any(nk == k for nk, _, _ in vnr)]

    # ---- coverage, printed because a blank is not an agreement. Measured on the real tree at 11:54:
    # 24 cells carried no verdict disagreement, but only 4 of them had every verdict field recorded by
    # every port, and 123 of 430 field-cells were blank. A headline that counts the 24 without the 4 is a
    # count of cells nobody contradicted, not of cells everybody answered.
    field_cov = {f: {n: 0 for n in names} for f in VERDICT_FIELDS}
    cells_all_recorded = []
    cell_recs = {}
    all_blank = []
    cell_port_recorded = {}
    for k in cells_live:
        recs = cell_recs[k] = compare(VERDICT_FIELDS, {n: cmp[n][k] for n in names})
        for f in VERDICT_FIELDS:
            for n in recs.get(f, {}):
                field_cov[f][n] += 1
            if not recs.get(f):
                all_blank.append((k, f))
        cell_port_recorded[fmt(k)] = {p: 0 for p in names}
        for n in names:
            cell_port_recorded[fmt(k)][n] = sum(1 for f in VERDICT_FIELDS if n in recs.get(f, {}))
        if all(len(recs.get(f, {})) >= len(names) for f in VERDICT_FIELDS):
            cells_all_recorded.append(k)
    cov_pairs = sum(c for f in field_cov.values() for c in f.values())
    cov_possible = len(VERDICT_FIELDS) * len(names) * len(cells_live)
    print("== coverage (who answered what)")
    print("   verdict_pairs_recorded=%d/%d (%.1f%%) cells_every_port_recorded_every_verdict_field=%d/%d "
          "pairs_no_port_recorded=%d"
          % (cov_pairs, cov_possible, 100.0 * cov_pairs / cov_possible if cov_possible else 0.0,
             len(cells_all_recorded), len(cells_live), len(all_blank)))
    print("   a blank is a different fact from a disagreement, and from 'not applicable': this contract does "
          "not")
    print("   yet say which verdict fields apply to which case group, so the gate reports every blank and "
          "judges none")
    print("   of them. `docs/coverage.md` is the table; filling a blank is a port's work, defining which "
          "blanks")
    print("   are legal is a contract change.")
    for f in VERDICT_FIELDS:
        print("     %-22s %s" % (f, "  ".join("%s=%d" % (n, field_cov[f][n]) for n in names)))

    for n in names:
        joined = "\n".join("%s %s" % (fmt(k), digest(cmp[n][k])[0]) for k in sorted(identical_cells))
        d = hashlib.sha256(joined.encode("utf-8")).hexdigest()
        print("   %-11s digest_over_no-disagreement_cells=%s cells=%d" % (n, d[:16], len(identical_cells)))
    print("   cells_with_no_verdict_disagreement=%d/%d  of_which_fully_recorded=%d"
          % (len(identical_cells), len(cells_live), len(clean_cells)))

    # One word, computed once, used by both the artifact and the exit branch. Found while sabotage-testing
    # the coverage arms: these were two separate expressions, so editing only one left the artifact saying
    # PASS while the process exited 3 - the two-rulers defect this project keeps catching in other people's
    # tools, reproduced inside the gate itself.
    outcome_word = ("RED" if vdis else
                    "INCOMPLETE" if (short_total or vnr or unpinned or incomparable or vabs or all_blank)
                    else "PASS")

    verdict = {
        "cells_required": len(req_keys),
        "cells_run_by_every_port": len(shared),
        "cells_compared": len(cells_live),
        "outcome": outcome_word,
        "verdict_disagreements": len(vdis),
        "cells_with_no_verdict_disagreement": len(identical_cells),
        "verdict_not_recorded_pairs": len(vnr),
        "verdict_pairs_recorded": cov_pairs,
        "verdict_pairs_possible": cov_possible,
        "cells_every_port_recorded_every_verdict_field": [fmt(k) for k in cells_all_recorded],
        "cells_with_no_verdict_disagreement_and_fully_recorded": [fmt(k) for k in clean_cells],
        "verdict_field_coverage": {f: {n: field_cov[f][n] for n in names} for f in VERDICT_FIELDS},
        "verdict_pairs_no_port_recorded": [[fmt(k), f] for k, f in all_blank],
        # how many of the ten verdict fields each port answered in each compared cell - the
        # gate counts this so the coverage report does not have to re-read the faces and become a
        # second ruler (docs/FINDINGS-rev6.md M6 item 2 is what happens when it does).
        "cell_port_verdict_fields_recorded": cell_port_recorded,
        "not_recorded_pairs": [[fmt(k), f, sorted(w)] for k, f, w in vnr],
        "probe_cells_differing": len({k for k, _, _ in pdis}),
        "unpinned_input": [fmt(k) for k, _ in unpinned],
        "cells_excluded": [fmt(k) for k in incomparable],
        "channel_abstentions": [[fmt(k), f, sorted(w)] for k, fs in sorted(abstain.items())
                                 for f, w in sorted(fs.items())],
        "name_cross_form_agreements": [[fmt(k), f, sorted(w)] for k, f, w in vmulti],
        "prefix_shaped_records": [[fmt(k), f, sorted(w)] for k, f, w in vtrunc],
        "disagreements": [[fmt(k), f,
                          sorted("%s=%s" % (n, str(v)[1:-1])[:40] for n, v in sorted(rec.items()))]
                          for k, f, rec in vdis],
        "verdict_fields": VERDICT_FIELDS,
        "probe_fields": PROBE_FIELDS,
        # The records the gate actually compared, with the spec fingerprint each was stamped with. Emitted
        # here rather than recomputed by ci/spec_drift.py: a second implementation of "which record of this
        # port's represents this cell" is the two-rulers defect this project has now caught in itself three
        # times, and ci/spec_drift.py refused to guess (it counted 291 records against the gate's 264 cells).
        "compared_records": sorted(
            [n, fmt(k), str(flat[n][k].get("spec_sha256")
                             or (flat[n][k].get("provenance") or {}).get("spec_sha256") or "ABSENT")]
            for n in names for k in cells_live),
    }
    # The artifact path is an argument, not a constant. Measured reason: ci/selftest.py runs this gate
    # against small fixture trees, and with a hardcoded path each fixture run overwrote the real verdict
    # in evidence/S02/ - so docs/matrix.md, which reads that file, was judging a fixture for a while.
    # A test that writes into the evidence face is a defect even when the test itself passes.
    vpath = os.environ.get("SG_VERDICT_OUT") or os.path.join(
        REPO, "evidence", "S02", "equality-verdict.json")
    verdict["source_results"] = rel(RESULTS)
    verdict["source_required_list"] = rel(REQUIRED)
    verdict["written_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    io.open(vpath, "w", encoding="utf-8", newline=NL).write(
        json.dumps(verdict, ensure_ascii=False, sort_keys=True, indent=1) + NL)
    print("wrote %s outcome=%s" % (rel(vpath), verdict["outcome"]))

    if outcome_word == "RED":
        print("OUTCOME=RED verdict_disagreements=%d verdict_identical_cells=%d/%d "
              "cells_fully_recorded_and_identical=%d verdict_not_recorded_pairs=%d "
              "verdict_pairs_recorded=%d/%d "
              "probe_cells_differing=%d unpinned_input=%d cells_excluded=%d channel_abstentions=%d "
              "truncated_values=%d required_cells_missing=%d"
              % (len(vdis), len(identical_cells), len(cells_live), len(clean_cells), len(vnr),
                 cov_pairs, cov_possible,
                 len({k for k, _, _ in pdis}),
                 len(unpinned), len(incomparable), len(vabs) + len(pabs),
                 len(vtrunc) + len(ptrunc), short_total))
        return 1
    if outcome_word == "INCOMPLETE":
        print("OUTCOME=INCOMPLETE verdict_identical_cells=%d/%d required_cells_missing=%d unpinned_input=%d "
              "cells_excluded=%d channel_abstentions=%d verdict_not_recorded=%d pairs_no_port_recorded=%d "
              "cells_fully_recorded_and_identical=%d truncated_values=%d"
              % (len(identical_cells), len(cells_live), short_total, len(unpinned),
                 len(incomparable), len(vabs) + len(pabs), len(vnr), len(all_blank), len(clean_cells),
                 len(vtrunc) + len(ptrunc)))
        print("   No port disagrees with another on any checker verdict this gate could compare. What is")
        print("   missing is a cell, a pinned input, or a recorded verdict -- and a missing measurement is")
        print("   not agreement.")
        return 3
    print("OUTCOME=PASS digests_equal=%d/%d cells_compared=%d verdict_facts=%d "
          "probe_cells_differing=%d required_cells=%d verdict_pairs_recorded=%d/%d pairs_no_port_recorded=%d"
          % (len(names), len(names), len(cells_live), vagree,
             len({k for k, _, _ in pdis}), len(req_keys), cov_pairs, cov_possible, len(all_blank)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
