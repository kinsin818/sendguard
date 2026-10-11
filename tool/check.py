#!/usr/bin/env python3
"""SENDGUARD name pre-flight check (S10 tool seat).

    python tool/check.py <folder> [--target windows|macos|ubuntu|all]
    python tool/check.py --name "CON.txt"          # ask this machine, right now
    python tool/check.py --control T-CTRL-ASCII    # ask about a pinned control sample

Folder mode prints a risk statement per (name, target) for the names in a folder.
Name mode prints the verdict block: what Windows did to that name today, in the
field names and spellings `ci/equality.py` uses, so a report and the gate cannot
disagree about what one cell means.

Stdlib only; it does not import or call any of the six language ports.

Vocabulary is taken from spec/canonical.md (closed sets) and the rule set from
spec/cases.yaml (frozen traps).  A line whose `os_legality_verdict` is `unknown`
means "this project has no measurement cell for it", NOT "nothing is known":
the prose then states what the public specification says instead.  A field the
probe could not obtain prints NOT-RECORDED, which is spec/cell-identity.md 9.1's
word for an absence; it is never filled in by guess.

Safety: folder mode never opens, reads, writes or stats a scanned name; it only
enumerates.  Name mode does create a file, in a fresh scratch directory outside
the repository, inside a child process with an external 5 s timeout, and it
NEVER reads back the contents of a reserved device name (CON/NUL/AUX/COM1..9/
LPT1..9) because that can block.  It has no deletion logic (M19): every name
probe leaves its scratch directory behind and says so.

Exit codes: 0 = no risk | 1 = risk found | 2 = could not run the scan/probe
            3 = bad usage | 4 = this tool crashed.
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
import unicodedata

EXIT_NO_RISK = 0
EXIT_RISK = 1
EXIT_SCAN_FAILED = 2
EXIT_USAGE = 3
# A Python crash also exits 1, which is this program's "risk found" code.  Every
# run therefore goes through run(), which turns a crash into 4 and prints it.
EXIT_INTERNAL = 4

# spec/canonical.md section 10 - closed set, no additions here.
MECHANISM_CLASSES = (
    "reserved_device_name", "path_preprocessing_policy", "illegal_char_filter",
    "component_length_limit", "unicode_normalization", "case_folding",
    "control_char_handling", "bidi_handling", "zero_width_handling",
    "zip_roundtrip", "os_legality", "unknown",
)
# spec/canonical.md section 6 - closed set.
LEGALITY_WORDS = ("legal", "illegal", "unknown")

TARGETS = ("windows", "macos", "ubuntu")

# --- rev6 field classes, copied from ci/equality.py:30-68 (read-only mirror) ---
# VERDICT = the checker's answer about the name; six ports must agree on these bytes.
# PROBE   = what this language's own standard library did; allowed to differ, published as the matrix.
VERDICT_FIELDS = ("os_legality_verdict", "mechanism_class", "phantom", "roundtrip_ok",
                  "name_mutated", "enum_to_stat_agrees", "len_triple",
                  "bytes_written", "bytes_on_disk", "name_landed_as")
PROBE_FIELDS = ("create_result", "error_stage", "error_code", "error_message", "read_result",
                "longpath_mechanism", "deps_direct", "deps_total")
COMPARABILITY_FIELDS = ("path_form", "verdict_via")
# spec/canonical.md 2..: `verdict_via` is not in the closed sets file but is required by
# spec/cell-identity.md section 6, with values {win32, dotnet, cmd, posix}.
VERDICT_VIA_VALUES = ("win32", "dotnet", "cmd", "posix")
NOT_RECORDED = "NOT-RECORDED"        # section 9.1's word for an absence; never a value
PROBE_TIMEOUT_S = 5                  # spec/gate.md section 10
CANON_PAYLOAD = "SENDGUARD-CANON-PAYLOAD-2026"   # 28 bytes, sha256 c9fe45b2... (spec/cases.yaml)
HEXISH = re.compile(r"^(?:[0-9a-fA-F]{2})+$")

# MS Learn "Naming Files, Paths, and Namespaces", the spec_source named by the
# reserved_device_name traps in spec/cases.yaml.
WIN_RESERVED = (
    "CON", "PRN", "AUX", "NUL",
    *["COM%d" % i for i in range(1, 10)],
    *["LPT%d" % i for i in range(1, 10)],
)
# canonical.md section 10 lists CONIN$ under reserved_device_name; no trap in
# cases.yaml covers it, so rules that use it are reported as unbacked.
WIN_RESERVED_UNBACKED_EXTRA = ("CONIN$", "CONOUT$")
WIN_ILLEGAL_CHARS = '<>:"|?*'
C0_CONTROL = [chr(c) for c in range(0x00, 0x20)]
BIDI_STARTS = [(0x202A, 0x202E), (0x2066, 0x2069)]
ZERO_WIDTH = (0x200B, 0x200C, 0x200D, 0xFEFF)
# Whitespace that is NOT the ASCII space/dot the two measured traps cover.
NEAR_MISS_SPACE = {0x00A0: "U+00A0 NO-BREAK SPACE", 0x3000: "U+3000 IDEOGRAPHIC SPACE",
                   0x2007: "U+2007 FIGURE SPACE", 0x202F: "U+202F NARROW NBSP",
                   0x2028: "U+2028 LINE SEPARATOR", 0x2029: "U+2029 PARAGRAPH SEPARATOR"}

# Measured on this repository's only measured host (see results/python/windows).
WIN_COMPONENT_LEN_EXTENDED = 255   # T18-extended boundary_component_len
POSIX_NAME_MAX_BYTES = 255         # public spec for APFS/ext4; no cell here measures it
WIN_PLAIN_PATH_LEN = 260           # classic plain-form budget; T18-plain found
                                   # the component boundary at 177 because the
                                   # harness directory itself was 71 long.
LEN_NEAR_BAND = 220


# --------------------------------------------------------------------------- #
# frozen spec readers (dependency-free subset parse; do not reuse a port's code)
# --------------------------------------------------------------------------- #
def _strip_comment(line):
    out, quoted, esc = [], False, False
    for ch in line:
        if esc:
            out.append(ch)
            esc = False
            continue
        if ch == "\\":
            out.append(ch)
            esc = True
            continue
        if ch == '"':
            quoted = not quoted
            out.append(ch)
            continue
        if ch == "#" and not quoted:
            break
        out.append(ch)
    return "".join(out)


def spec_identity(root):
    """(freeze_revision, sha256 of cases.yaml, the hash FROZEN.md publishes, match?).

    Printed in every report so a reader can tell which freeze the answers came from.
    """
    path = os.path.join(root, "spec", "cases.yaml")
    raw = _read_bytes(path)
    if raw is None:
        return None, None, None, None
    import hashlib
    text = raw.decode("utf-8", "replace")
    rev = re.search(r"^freeze_revision:\s*(\S+)", text, re.M)
    actual = hashlib.sha256(raw).hexdigest()
    declared = None
    frozen = _read_text(os.path.join(root, "spec", "FROZEN.md"))
    if frozen:
        m = re.search(r"spec/cases.yaml\s*\|\s*([0-9a-f]{64})", frozen)
        declared = m.group(1) if m else None
    return (rev.group(1) if rev else "?"), actual, declared, (actual == declared if declared else None)


def load_cases(yaml_path):
    """-> list of {id, hexes, category, applicable} from the frozen cases.yaml.

    Reads ONLY the `cases:` section. The rev6 `control_samples:` section uses the same
    two-space `- id:` shape; before this was sliced the control cells were parsed as
    traps with category `unknown`, which inflated the trap count and let
    mechanism_class=unknown claim control cells as its evidence.
    """
    text = _read_text(yaml_path)
    if text is None:
        return []
    body = "\n".join(_strip_comment(l) for l in text.splitlines())
    sec = re.search(r"^cases:\n(.*?)(?=^\S|\Z)", body, re.S | re.M)
    if not sec:
        return []
    body = sec.group(1)
    cases = []
    for m in re.finditer(r"  - id:\s*(\S+)(.*?)(?=\n  - id:|\Z)", body, re.S):
        cid, block = m.group(1).strip(), m.group(2)
        hexes = []
        one = re.search(r'sample_hex:\s*"([0-9a-fA-F]+)"', block)
        if one:
            hexes.append(one.group(1).lower())
        many = re.search(r"sample_hex_list:\s*\n((?:\s*-\s*\"[0-9a-fA-F]+\".*\n?)+)", block)
        if many:
            hexes += [h.lower() for h in re.findall(r'"([0-9a-fA-F]+)"', many.group(1))]
        cat = re.search(r"category:\s*(\S+)", block)
        app = re.search(r"applicable:\s*\[([^\]]*)\]", block)
        cases.append({
            "id": cid,
            "hexes": hexes,
            "category": cat.group(1) if cat else "unknown",
            "applicable": [a.strip() for a in app.group(1).split(",")] if app else [],
        })
    return cases


# spec/cell-identity.md 9.5 and ci/equality.py:186 RE_CANON_FACE: only a `<port>.<os>.<arch>`
# directory is read.  Everything else on disk in results/ is an earlier contract revision or a
# different naming rule; the gate names it and refuses to compare it, so this reader must not fold
# it into a denominator either -- otherwise the report says seven ports and docs/equality output
# says six.  The pattern below is the gate's, copied deliberately.
RE_CANON_FACE = re.compile(r"^([a-z]+)\.(windows|macos|ubuntu)\.(x64|arm64)$")


def load_measured_cells(results_dir):
    """-> ({os: {case_id: {"ports": set, "vias": set}}}, [(excluded_face, cell_records)]).

    A rule is 'backed' for a target only if a canonical face left a cell for it here.  Nothing is
    assumed about operating systems with no cells (README section 2), and no cell is treated as
    agreed truth: the equality gate decides that, not this reader.
    """
    import glob
    measured, excluded = {}, []
    if not os.path.isdir(results_dir):
        return measured, excluded
    for entry in sorted(os.listdir(results_dir)):
        full = os.path.join(results_dir, entry)
        if entry == "phantom.json":        # the gate skips this one by name; so does this reader
            continue
        m = RE_CANON_FACE.match(entry)
        if not m or not os.path.isdir(full):
            if os.path.isdir(full):
                n = len(glob.glob(os.path.join(full, "**", "*.json"), recursive=True))
            elif full.endswith(".json"):
                n = 1
            else:
                n = 0
            excluded.append((entry, n))
            continue
        port = m.group(1)
        for path in sorted(glob.glob(os.path.join(full, "**", "*.json"), recursive=True)):
            data = _read_json(path)
            if data is None:
                continue
            for cell in (data if isinstance(data, list) else [data]):
                if not isinstance(cell, dict):
                    continue
                cid, osname = cell.get("case_id"), cell.get("os")
                if not (isinstance(cid, str) and isinstance(osname, str)):
                    continue
                slot = measured.setdefault(osname.lower(), {}).setdefault(
                    cid, {"ports": set(), "vias": set()})
                slot["ports"].add(port)
                via = cell.get("verdict_via")
                if isinstance(via, str) and via not in ("", "none"):
                    slot["vias"].add(via)
    return measured, excluded


def decode_case_samples(cases):
    """-> {trap_id: [(name, category)]}; hex-only per N12, never read from disk."""
    out = {}
    for case in cases:
        names = []
        for hx in case["hexes"]:
            try:
                names.append(bytes.fromhex(hx).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                names.append(None)
        out[case["id"]] = [(n, case["category"]) for n in names]
    return out


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #
def _read_bytes(path):
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except OSError:
        return None


def _read_text(path):
    raw = _read_bytes(path)
    if raw is None:
        return None
    return raw.decode("utf-8", "replace")


def _read_json(path):
    raw = _read_bytes(path)
    if raw is None:
        return None
    try:
        return json.loads(raw.decode("utf-8", "replace"))
    except ValueError:
        return None


def escape_name(name):
    """ASCII-escape everything non-ASCII, invisible, or edge-adjacent.

    Deliberate: printing a bidi or zero-width name verbatim into a cp936 console
    would corrupt the rest of the report line, and a report the reader cannot
    trust is worse than no report.  Leading/trailing spaces are escaped too, so
    'trailsp ' does not read as 'trailsp' plus the field separator.
    """
    out = []
    for i, ch in enumerate(name):
        cp = ord(ch)
        edge = i == 0 or i == len(name) - 1
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif cp == 0x20 and not edge:
            out.append(" ")
        elif cp < 0x20 or cp == 0x7F:
            out.append("\\x%02x" % cp)
        elif cp == 0x20:
            out.append("\\x20")
        elif 0x20 < cp < 0x7F:
            out.append(ch)
        elif cp <= 0xFFFF:
            out.append("\\u%04x" % cp)
        else:
            out.append("\\U%08x" % cp)
    return "".join(out)


def ascii_safe(text):
    """Drop any localised bytes: a zh-CN build returns Chinese strerror text."""
    cleaned = (text or "").encode("ascii", "replace").decode("ascii")
    if not cleaned.strip("?!.,:; "):
        return None
    return cleaned


def errno_note(exc):
    """English-safe description of an enumeration failure, never localised mojibake."""
    note = ascii_safe(exc.strerror)
    if note is None:
        note = "message suppressed (localised on this build)"
    return "errno=%s %s" % (exc.errno, note)


def escape_path(path):
    """Like escape_name but leaves path separators alone: the root is not a suspect."""
    out = []
    for ch in path:
        cp = ord(ch)
        if ch == "/" or ch == "\\":
            out.append(ch)
        elif 0x20 < cp < 0x7F:
            out.append(ch)
        elif cp <= 0xFFFF:
            out.append("\\u%04x" % cp)
        else:
            out.append("\\U%08x" % cp)
    return "".join(out)


class Backing(object):
    """Which frozen traps have result cells on disk for one target, and how deep."""

    __slots__ = ("ids", "ports", "cells", "vias")

    def __init__(self, ids, ports, cells, vias=None):
        self.ids = ids
        self.ports = ports
        self.cells = cells
        self.vias = vias or []

    def __bool__(self):
        return bool(self.ids)

    def label(self):
        if not self.ids:
            return "none"
        shown = self.ids[:5]
        text = ",".join(shown)
        if len(self.ids) > len(shown):
            text += "(+%d traps)" % (len(self.ids) - len(shown))
        return "%s [%d cells, %d ports]" % (text, self.cells, len(self.ports) or 0)


def utf16_units(name):
    return sum(2 if ord(c) > 0xFFFF else 1 for c in name)


def units(name):
    return len(name), utf16_units(name), len(name.encode("utf-8"))


def stem_of(name):
    return name.split(".", 1)[0]


def has_range(cp, ranges):
    return any(lo <= cp <= hi for lo, hi in ranges)


def win_strip(name):
    """What the measured path_preprocessing_policy traps landed as (T04/T05)."""
    return name.rstrip(". ")


def find_char_class_hits(name):
    bidi = [escape_name(c) for c in name if has_range(ord(c), BIDI_STARTS)]
    zw = [escape_name(c) for c in name if ord(c) in ZERO_WIDTH]
    ctrl = [escape_name(c) for c in name if ord(c) < 0x20]
    return bidi, zw, ctrl


def repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# --------------------------------------------------------------------------- #
# canonical spellings, mirrored from ci/equality.py (canon_name / canon_triple)
# --------------------------------------------------------------------------- #
# Foldered here so a report line and the equality gate read one name, one triple
# the same way.  The algorithm is the gate's, copied deliberately and kept
# behaviour-identical including the case this tool disagrees with the gate about
# (see tool_spelling_defect_note): a name that is itself a hex-digit string gets
# decoded as if it were an encoding.  Diverging quietly is the failure mode.
def canon_name(value):
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
    for dec in ("utf-16-le", "utf-8"):
        if dec == "utf-16-le" and not (len(raw) % 2 == 0 and len(raw) >= 4
                                       and raw[1::2] == b"\x00" * (len(raw) // 2)):
            continue
        try:
            text = raw.decode(dec)
        except (UnicodeDecodeError, ValueError):
            continue
        return ("h", text.encode("utf-8", "surrogatepass").hex())
    return ("r", raw.hex())


def canon_triple(code_points, utf16_units_, utf8_bytes_):
    """The one token the gate folds its four spellings onto: `<cp>/<u16>/<bytes>`."""
    return "%d/%d/%d" % (code_points, utf16_units_, utf8_bytes_)


def tool_spelling_defect_note(name):
    """Return a warning when the gate's fold cannot round-trip this name."""
    if not name:
        return None
    if HEXISH.match(name) and len(name) >= 6:
        form, token = canon_name(name)
        own = name.encode("utf-8", "surrogatepass").hex()
        if token != own:
            return ("the gate's canon_name reads this name as if it were a hex ENCODING of other bytes: "
                    "canon_name(%r) -> (%s, %s), while the name's own UTF-8 bytes are %s. A report and the "
                    "gate therefore do NOT mean the same thing by this token, and no port can fix that by "
                    "re-spelling its field." % (name, form, token, own))
    return None


# --------------------------------------------------------------------------- #
# the rule engine
# --------------------------------------------------------------------------- #
class Finding(object):
    """One risk statement. The verdict fields come first because they are the answer;
    the evidence (which cells back it, which layer was asked) follows, per rev6."""

    __slots__ = ("rel", "name_hex", "target", "mechanism_class", "verdict", "verdict_via",
                 "backed", "detail", "path_form")

    def __init__(self, rel, target, mechanism_class, verdict, backed, detail, path_form=None,
                 verdict_via=None, name_hex=None):
        assert mechanism_class in MECHANISM_CLASSES, mechanism_class
        assert verdict in LEGALITY_WORDS, verdict
        self.rel = escape_name(rel)
        self.name_hex = name_hex
        self.target = target
        self.mechanism_class = mechanism_class
        self.verdict = verdict
        self.verdict_via = verdict_via or NOT_RECORDED
        if isinstance(backed, Backing):
            self.backed = backed
            if verdict_via is None and backed.vias:
                self.verdict_via = ",".join(backed.vias)
        else:
            ids = list(backed)
            self.backed = Backing(ids, [], len(ids))
        self.detail = detail
        self.path_form = path_form

    def line(self):
        extra = "  path_form=%s" % self.path_form if self.path_form else ""
        return ("%s  name_hex=%s  target=%s  VERDICT os_legality_verdict=%s mechanism_class=%s "
                "verdict_via=%s%s  EVIDENCE backed_by=%s" % (
                    self.rel, self.name_hex or NOT_RECORDED, self.target, self.verdict,
                    self.mechanism_class, self.verdict_via, extra, self.backed.label()))


class Engine(object):
    def __init__(self, measured, cases):
        # measured: {os: set(case_id)}. Rules name the traps that back them; a
        # trap with no result cell on a target makes the rule unbacked there.
        self.measured = measured
        self.case_by_id = {c["id"]: c for c in cases}
        self.category_ids = {}
        for c in cases:
            self.category_ids.setdefault(c["category"], []).append(c["id"])

    def backing(self, target, trap_ids):
        """-> Backing: which of these traps have result cells on disk for this target.

        Matches members too: trap T14 is measured as cells T14a/T14b/T14c, and the
        canonical rev6 spelling of a member is `T14-m1`; both are accepted here
        because this reads whatever the port filed under.
        """
        have = self.measured.get(target, {})
        ids, ports, cells, vias = [], set(), 0, set()
        for tid in trap_ids:
            matched = [cid for cid in have if cid == tid or cid.startswith(tid)]
            if matched:
                ids.append(tid)
                cells += len(matched)
                for cid in matched:
                    ports |= have[cid]["ports"]
                    vias |= have[cid]["vias"]
        return Backing(ids, sorted(ports), cells, sorted(vias))

    def verdict_via_for(self, target, trap_ids):
        """The tool the recorded cells actually asked, or NOT-RECORDED (never guessed)."""
        vias = self.backing(target, trap_ids).vias
        return ",".join(vias) if vias else NOT_RECORDED

    def verdict_for(self, target, trap_ids, measured_verdict):
        """Use the measured word when this project has a cell, else `unknown`."""
        b = self.backing(target, trap_ids)
        return (measured_verdict if b else "unknown"), b

    # ---- per-name rules, windows -------------------------------------------- #
    def windows_rules(self, rel, name, parent_rel, total_path_len):
        out = []
        st = stem_of(name).upper()

        if st in WIN_RESERVED:
            v, b = self.verdict_for("windows", self.category_ids.get("reserved_device_name", []), "illegal")
            out.append(Finding(rel, "windows", "reserved_device_name", v, b,
                               "illegal on windows. Measured behaviour is worse than an error: the write can "
                               "report success and leave no file at all (phantom cells T01/T02/T10/T11), and "
                               "`cmd copy src CON` exits 0 having written to the console device. Expect the "
                               "recipient to see nothing, not a failure."))
        elif st in WIN_RESERVED_UNBACKED_EXTRA:
            out.append(Finding(rel, "windows", "reserved_device_name", "unknown", [],
                               "same family as the measured reserved names, but no frozen trap covers this "
                               "spelling (canonical.md section 10 lists it as an example only), so this is "
                               "unverified."))

        bad = sorted({c for c in name if c in WIN_ILLEGAL_CHARS})
        if bad:
            v, b = self.verdict_for("windows", self.category_ids.get("illegal_char_filter", []), "illegal")
            out.append(Finding(rel, "windows", "illegal_char_filter", v, b,
                               "rejected by windows: %s (bytes %s). Nothing downstream can rescue it; rename "
                               "before sending." % (" ".join(escape_name(c) for c in bad),
                                                    " ".join("%02x" % ord(c) for c in bad))))

        ctrl = [c for c in name if ord(c) < 0x20]
        if ctrl:
            v, b = self.verdict_for("windows", self.category_ids.get("control_char_handling", []), "illegal")
            out.append(Finding(rel, "windows", "control_char_handling", v, b,
                               "contains control character(s) %s; measured illegal on windows (T15, "
                               "err_at_syscall)." % " ".join("\\x%02x" % ord(c) for c in ctrl)))

        stripped = win_strip(name)
        if stripped != name and stripped != "":
            v, b = self.verdict_for("windows", self.category_ids.get("path_preprocessing_policy", []), "legal")
            ok = bool(b)
            out.append(Finding(rel, "windows", "path_preprocessing_policy", v, b,
                               ("will probably be renamed to %s on the recipient's machine" % escape_name(stripped))
                               if ok else
                               "same shape as the measured stripping traps, but this exact trailing sequence has "
                               "no cell of its own; treat the target name as unknown"))

        trail_ws = [c for c in name if ord(c) in NEAR_MISS_SPACE]
        if trail_ws and (name[-1] == "\u00a0" or name[-1] == "\u3000" or ord(name[-1]) in NEAR_MISS_SPACE):
            out.append(Finding(rel, "windows", "path_preprocessing_policy", "unknown", [],
                               "ends in %s, which is whitespace to a human and is NOT the trailing ASCII space "
                               "or dot that this project measured (T04/T05). No cell covers it, so whether "
                               "anything strips or renames it is unknown here." %
                               NEAR_MISS_SPACE.get(ord(name[-1]), "invisible whitespace")))

        bidi, zw, _ = find_char_class_hits(name)
        if bidi:
            v, b = self.verdict_for("windows", self.category_ids.get("bidi_handling", []), "legal")
            out.append(Finding(rel, "windows", "bidi_handling", v, b,
                                "contains bidi format character(s) %s. Measured: lands on disk unchanged, so it "
                                "is not broken - but the display order of this name is not the order of its "
                                "characters, so the recipient cannot reliably retype or match it." %
                                " ".join(bidi)))
        if zw:
            v, b = self.verdict_for("windows", self.category_ids.get("zero_width_handling", []), "legal")
            out.append(Finding(rel, "windows", "zero_width_handling", v, b,
                               "contains zero-width character(s) %s. Measured: lands unchanged (T13); the risk "
                               "is that two names look identical to the reader and are not the same file." %
                               " ".join(zw)))

        if name.startswith("-"):
            v, b = self.verdict_for("windows", self.category_ids.get("unknown", []), "legal")
            out.append(Finding(rel, "windows", "unknown", v, b,
                               "legal on the filesystem (measured T20) and this tool cannot verdict it, because "
                               "the damage happens one layer up: a name that looks like a command-line flag is "
                               "eaten by any script that passes the folder to another program. Kept as "
                               "mechanism_class=unknown, which is what the frozen table calls it."))

        out.extend(self.length_rules(rel, name, parent_rel, total_path_len, "windows"))
        return out

    # ---- per-name rules, macos / ubuntu ------------------------------------- #
    def unix_like_rules(self, rel, name, parent_rel, total_path_len, target):
        out = []
        assert target in ("macos", "ubuntu")
        # No cell for either target (README section 2), so every verdict here is
        # unknown and the prose carries the public-spec answer.
        cps, u16, ub = units(name)

        if target == "macos" and ":" in name:
            out.append(Finding(rel, target, "illegal_char_filter", "unknown", [],
                               "a colon in a macOS name is shown as a slash by Finder. This project has no "
                               "macOS cell, so the verdict is unknown; the public spec is the only source."))
        if target == "macos" and unicodedata.is_normalized("NFC", name) and any(ord(c) > 127 for c in name):
            nfd = unicodedata.normalize("NFD", name)
            if nfd != name:
                out.append(Finding(rel, target, "unicode_normalization", "unknown", [],
                                   "will probably be renamed to %s on the recipient's machine: macOS has long "
                                   "stored filenames decomposed (NFD), and this name is composed (NFC). Unknown "
                                   "here because no macOS cell was measured - the rewritten form is computed "
                                   "from Unicode data, not observed. bytes=%d" % (escape_name(nfd), len(nfd.encode("utf-8")))))
        if name.startswith("."):
            out.append(Finding(rel, target, "path_preprocessing_policy", "unknown", [],
                               "leading dot: hidden in Finder (macos) and in a plain `ls` (ubuntu). Legal, "
                               "invisible - the recipient may conclude the send failed."))
        if not unicodedata.is_normalized("NFC", name):
            nfc = unicodedata.normalize("NFC", name)
            out.append(Finding(rel, target, "unicode_normalization", "unknown", [],
                               "not in NFC form; its NFC equivalent would be %s (%s). On %s the two are "
                               "different byte sequences and can sit in the same folder looking like one file. "
                               "No %s cell was measured, so this is unverified." % (
                                   escape_name(nfc), "NFC", target, target)))
        if ub > POSIX_NAME_MAX_BYTES:
            out.append(Finding(rel, target, "component_length_limit", "unknown", [],
                               "%d UTF-8 bytes in one component; the public limit for APFS and ext4 is 255 bytes. "
                               "No %s cell exists in this repository, so this is the public spec talking, not a "
                               "measurement." % (ub, target)))
        out.extend(self.length_rules(rel, name, parent_rel, total_path_len, target))
        return out

    # ---- length rules ------------------------------------------------------- #
    def length_rules(self, rel, name, parent_rel, total_path_len, target):
        out = []
        cps, u16, ub = units(name)
        worst = max(cps, u16, ub)
        unit_note = ("code points=%d, UTF-16 units=%d, UTF-8 bytes=%d" % (cps, u16, ub))

        if target == "windows":
            if worst > WIN_COMPONENT_LEN_EXTENDED:
                v, b = self.verdict_for("windows", ["T18-extended", "T-CTRL-NAMETOOLONG"], "illegal")
                out.append(Finding(rel, target, "component_length_limit", v, b,
                                   "too long for one component in any path form (%s; the measured boundary with "
                                   "the extended prefix is 255)." % unit_note, path_form="extended"))
            elif worst >= LEN_NEAR_BAND:
                v, b = self.verdict_for("windows", ["T18-extended"], "legal")
                if cps == ub == u16:
                    unit_clause = "All three counting units agree for this name, so its own length is not " \
                                  "unit-sensitive; it simply has only %d units of room." % (
                                      WIN_COMPONENT_LEN_EXTENDED - worst)
                else:
                    unit_clause = "It has only %d units of room, and the units disagree by %d, so which layer's " \
                                  "counting decides the outcome is a measured divergence, not a guess " \
                                  "(spec/roles.md groups the six ports into three counting units)." % (
                                      WIN_COMPONENT_LEN_EXTENDED - worst, abs(cps - ub))
                out.append(Finding(rel, target, "component_length_limit", v, b,
                                   "fits the 255-unit measured boundary. %s" % unit_clause,
                                   path_form="extended"))
            if total_path_len > WIN_PLAIN_PATH_LEN:
                v, b = self.verdict_for("windows", ["T18-plain", "T-CTRL-NAMETOOLONG"], "illegal")
                out.append(Finding(rel, target, "component_length_limit", v, b,
                                   "the whole path is %d characters here and the plain form runs out around 260 "
                                   "- measured, not folklore: in T18-plain the component itself topped out at 177 "
                                   "because the directory in front of it was 71. So this is a path budget, not a "
                                   "name limit: the same file passes or fails depending on where the recipient "
                                   "unpacks it." % total_path_len, path_form="plain"))
                cells = self.backing(target, ["T18-extended"])
                out.append(Finding(rel, target, "component_length_limit", "legal", cells,
                                   "the same path does exist with the extended prefix or a long-path-aware "
                                   "manifest - that only helps programs that opted in, and you cannot make the "
                                   "recipient's Explorer, browser or mail client opt in.", path_form="extended"))
            elif total_path_len >= LEN_NEAR_BAND:
                v, b = self.verdict_for("windows", ["T18-plain"], "legal")
                out.append(Finding(rel, target, "component_length_limit", v, b,
                                   "the path is already %d characters at THIS location and the recipient's own "
                                   "folder adds to it. Nothing is wrong yet; the send is what uses up the rest."
                                   % total_path_len, path_form="plain"))
        else:
            if ub > WIN_COMPONENT_LEN_EXTENDED:
                out.append(Finding(rel, target, "component_length_limit", "unknown", [],
                                   "%d UTF-8 bytes in one component; the public limit for APFS and ext4 is 255 "
                                   "bytes. No %s cell exists in this repository, so this is the public spec "
                                   "talking, not a measurement." % (ub, target)))
            if total_path_len > 4096:
                out.append(Finding(rel, target, "component_length_limit", "unknown", [],
                                   "full path %d bytes; public PATH_MAX is 4096. Unmeasured here." % total_path_len,
                                   path_form="plain"))
        return out

    def rules_for(self, rel, name, parent_rel, total_path_len, targets):
        out = []
        for t in targets:
            if t == "windows":
                out.extend(self.windows_rules(rel, name, parent_rel, total_path_len))
            else:
                out.extend(self.unix_like_rules(rel, name, parent_rel, total_path_len, t))
        hx = canon_name(name)[1]
        for f in out:
            f.name_hex = hx
        return out


# --------------------------------------------------------------------------- #
# name probe: ask this machine about one name, right now
# --------------------------------------------------------------------------- #
# The create/enumerate/read attempt runs in a CHILD PROCESS behind an external
# timeout, because a reserved device name can block (spec/gate.md 10: 5 s ->
# `hang`).  The parent decides whether a read is allowed at all; the driver is
# told "do not read" for reserved names, so the safety rule has exactly one home.
PROBE_DRIVER = r"""
import hashlib, json, os, sys
d, h, ph, may_read, ext = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4] == "1", sys.argv[5] == "1"
name = bytes.fromhex(h).decode("utf-8")
payload = bytes.fromhex(ph)
BS = chr(92)
p = os.path.join(d, name)
if ext:
    p = BS + BS + "?" + BS + os.path.abspath(p)
res = {"create_result": None, "error_stage": None, "error_code": None, "error_message": None,
       "bytes_written": None, "entries": [], "path_view": None,
       "read_result": None, "read_bytes": None, "read_sha256": None, "read_skipped_reason": None}
try:
    with open(p, "wb") as f:
        f.write(payload)
    res["create_result"] = "ok"
    res["bytes_written"] = len(payload)
except ValueError as e:
    res.update(create_result="err_at_parse", error_stage="parse", error_code=type(e).__name__,
               error_message=str(e)[:200])
except OSError as e:
    ec = getattr(e, "winerror", None)
    res.update(create_result="err_at_syscall", error_stage="syscall",
               error_code=("winerror:%s" % ec) if ec is not None else type(e).__name__,
               error_message=str(e)[:200])
except Exception as e:
    res.update(create_result="err_at_syscall", error_stage="syscall", error_code=type(e).__name__,
               error_message=str(e)[:200])
for e in os.scandir(d):
    try:
        size = None if e.is_dir() else e.stat().st_size
    except OSError:
        size = None
    res["entries"].append({"h": e.name.encode("utf-8", "surrogatepass").hex(),
                           "s": size, "d": bool(e.is_dir())})
if "\x00" not in name:
    try:
        res["path_view"] = bool(os.path.lexists(p))
    except OSError:
        res["path_view"] = None
if may_read:
    landed = [x for x in res["entries"] if x["h"] == h and not x["d"]]
    if not landed:
        want_size = len(payload)
        same = [x for x in res["entries"] if not x["d"] and x["s"] == want_size]
        if len(same) == 1:
            # the requested name did not survive; what did survive is a different name, and
            # reading IT is safe (it is not a device) and is what `roundtrip_ok` means here.
            landed = same
            res["read_landed_under"] = same[0]["h"]
    if not landed:
        res["read_result"] = None
        res["read_skipped_reason"] = "nothing landed under this name or a payload-sized name"
    else:
        rn = bytes.fromhex(landed[0]["h"]).decode("utf-8", "replace")
        rp = os.path.join(d, rn)
        if res.get("read_landed_under"):
            rp = os.path.join(d, rn)
        try:
            with open(rp, "rb") as f:
                blob = f.read()
            res["read_result"] = "ok" if blob else "eof"
            res["read_bytes"] = len(blob)
            res["read_sha256"] = hashlib.sha256(blob).hexdigest()
        except OSError as e:
            ec = getattr(e, "winerror", None)
            res["read_result"] = "err6" if ec == 6 else "eof"
            res["read_skipped_reason"] = "%s" % (str(e)[:120])
else:
    res["read_skipped_reason"] = ("reserved device name: reading its contents can block, and this tool "
                                  "is told never to read one")
sys.stdout.write(json.dumps(res, ensure_ascii=True))
"""


def is_reserved_device(name):
    return stem_of(name).upper() in WIN_RESERVED


def scratch_root():
    base = os.environ.get("SENDGUARD_TOOL_RUN_ROOT")
    if not base:
        import tempfile
        base = os.path.join(tempfile.gettempdir(), "sendguard-tool")
    d = os.path.join(base, "probe-" + uuid4_hex())
    os.makedirs(d)
    return d


def uuid4_hex():
    import uuid
    return uuid.uuid4().hex


def true_hex(name):
    """The name's own UTF-8 bytes. NOT the same thing as canon_name()'s token, which
    reads a name made of hex digits as if it were an encoding of other bytes.  The
    driver is sent this; the token is only for display and for matching cells."""
    return name.encode("utf-8", "surrogatepass").hex()


def probe_name(name, payload_hex, extended=False, timeout=PROBE_TIMEOUT_S):
    """Create/enumerate/(maybe)read in a child process; return the raw readings."""
    import subprocess
    scratch = scratch_root()
    reserved = is_reserved_device(name)
    args = [sys.executable, "-c", PROBE_DRIVER, scratch, true_hex(name), payload_hex,
            "0" if reserved else "1", "1" if extended else "0"]
    t0 = time.time()
    cp = None
    try:
        cp = subprocess.run(args, capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL)
        raw = cp.stdout.decode("utf-8", "replace")
        hung = False
    except subprocess.TimeoutExpired:
        raw, hung = "", True
    elapsed_ms = int((time.time() - t0) * 1000)
    obs, err = (None), ""
    if not hung:
        try:
            obs = json.loads(raw)
        except ValueError:
            obs = None
            err = cp.stderr.decode("utf-8", "replace")
    else:
        err = cp.stderr.decode("utf-8", "replace") if cp and cp.stderr else ""
    if obs is None:
        obs = {"create_result": "hang" if hung else None, "error_stage": None, "error_code": None,
               "error_message": "child produced no parseable record (rc=%s)"
                                % (None if hung else cp.returncode),
               "bytes_written": None, "entries": [], "path_view": None, "read_result": None,
               "read_bytes": None, "read_sha256": None,
               "read_skipped_reason": "instrument produced no record -- this is a tool failure, not a "
                                      "measurement of the name"}
        obs["_child_stderr"] = ("child stderr: " + err.strip().replace("\r\n", " | ")[:400]) if err.strip() else None
    obs["_scratch"] = scratch
    obs["_elapsed_ms"] = elapsed_ms
    obs["_timeout_s"] = timeout
    obs["_hung"] = hung
    obs["_read_forbidden"] = reserved
    obs.setdefault("_child_stderr", None)
    return obs


def verdict_from_observation(name, obs, payload_hex):
    """Fill the VERDICT_FIELDS from the observation. Absence stays NOT-RECORDED."""
    want_hex = true_hex(name)
    entries = obs.get("entries") or []
    exact = [e for e in entries if e["h"] == want_hex and not e["d"]]
    payload_sha = hashlib.sha256(bytes.fromhex(payload_hex)).hexdigest()
    landed_other = [e for e in entries
                    if not e["d"] and e["h"] != want_hex and e.get("sha") == payload_sha]
    # the driver does not hash every file (it would read contents, which is forbidden
    # for device names), so 'landed under another name' is decided by size match plus
    # the requested name being absent.
    if not exact:
        same_size = [e for e in entries
                     if not e["d"] and e["h"] != want_hex and e["s"] == len(bytes.fromhex(payload_hex))]
        landed_other = same_size
    present = bool(exact)
    mutated = (not present) and bool(landed_other)
    create = obs.get("create_result")
    phantom = bool(create == "ok" and not present and not mutated)

    if create in ("err_at_syscall",):
        legality = "illegal"
        crit = "syscall refused and no directory entry exists"
    elif create == "err_at_parse":
        legality = "unknown"
        crit = "the language refused before the OS was asked, so the OS was never asked"
    elif create == "hang" or create is None:
        legality = "unknown"
        crit = "the probe did not complete, so nothing was learned"
    elif present:
        legality = "legal"
        crit = "a directory entry with this exact name exists after the attempt"
    elif mutated:
        legality = "legal"
        crit = "something landed under a different name; the name did not survive intact"
    else:
        legality = "illegal"
        crit = ("the call reported success but no directory entry exists (and nothing landed under another "
                "name), so this name cannot exist here")
    landed_hex = (exact[0]["h"] if exact else (landed_other[0]["h"] if landed_other else None))
    on_disk = (exact[0]["s"] if exact else (landed_other[0]["s"] if landed_other else None))
    roundtrip = NOT_RECORDED
    if obs.get("read_sha256"):
        roundtrip = "true" if obs["read_sha256"] == payload_sha else "false"
    read_result = obs.get("read_result") or NOT_RECORDED
    out = {
        "os_legality_verdict": legality,
        "criterion": crit,
        "mechanism_class": None,          # filled by the rule engine, or `unknown`
        "phantom": "true" if phantom else "false",
        "roundtrip_ok": roundtrip,
        "name_mutated": "true" if mutated else "false",
        "enum_to_stat_agrees": ("NOT-RECORDED" if obs.get("path_view") is None
                                else ("true" if bool(obs["path_view"]) == present else "false")),
        "len_triple": canon_triple(*units(name)),
        "bytes_written": ("NOT-RECORDED" if obs.get("bytes_written") is None
                          else str(obs["bytes_written"])),
        "bytes_on_disk": "NOT-RECORDED" if on_disk is None else str(on_disk),
        "name_landed_as": landed_hex or NOT_RECORDED,
        "read_result": read_result,
        "read_skip_reason": obs.get("read_skipped_reason"),
        "read_landed_under": obs.get("read_landed_under"),
        "requested_hex": want_hex,
        "requested_hex_canon_token": canon_name(name)[1],
        "requested_escaped": escape_name(name),
    }
    return out


def committed_cells_for(results_dir, name_hexes, faces_only=True):
    """Every canonical-face cell asked about these exact input bytes.

    Both the name's own UTF-8 hex and the gate's canon token are accepted, because for
    a name that is itself a hex-digit string the two are different strings (see
    tool_spelling_defect_note) and neither is the 'wrong' one to match on.
    """
    want = set(h for h in name_hexes if h)
    hits = []
    if not os.path.isdir(results_dir):
        return hits
    for face in sorted(os.listdir(results_dir)):
        fd = os.path.join(results_dir, face)
        if not os.path.isdir(fd):
            continue
        if faces_only and face.count(".") != 2:
            continue
        for fn in sorted(os.listdir(fd)):
            if not fn.endswith(".json"):
                continue
            d = _read_json(os.path.join(fd, fn))
            if not isinstance(d, dict) or "case_id" not in d:
                continue
            src = str(d.get("name_source") or "").lower()
            if src in want or (canon_name(src)[1] or "") in want:
                hits.append((face, d))
    return hits


def load_control_samples(yaml_path):
    """rev6 pinned control samples: -> [{id, sample_hex, payload_hex}]."""
    text = _read_text(yaml_path)
    if text is None:
        return []
    body = "\n".join(_strip_comment(l) for l in text.splitlines())
    m = re.search(r"^control_samples:\n(.*?)(?=^\S|\Z)", body, re.S | re.M)
    if not m:
        return []
    out = []
    for blk in re.finditer(r"  - id:\s*(\S+)(.*?)(?=\n  - id:|\Z)", m.group(1), re.S):
        cid, inner = blk.group(1), blk.group(2)
        sh = re.search(r'sample_hex:\s*"([0-9a-fA-F]+)"', inner)
        ph = re.search(r'payload_hex:\s*"([0-9a-fA-F]+)"', inner)
        out.append({"id": cid,
                    "sample_hex": sh.group(1).lower() if sh else None,
                    "payload_hex": ph.group(1).lower() if ph else None})
    return out


def print_verdict_block(name, engine, results_dir, extended, payload_hex, spec_info, excluded):
    rev, actual, declared, matches = spec_info
    obs = probe_name(name, payload_hex, extended=extended)
    v = verdict_from_observation(name, obs, payload_hex)
    rule_findings = engine.rules_for(name, name, ".", len(name), ["windows"])
    mech = rule_findings[0].mechanism_class if rule_findings else None
    if v["os_legality_verdict"] == "illegal" and mech is None:
        mech = "unknown"
    if mech is None:
        mech = "os_legality" if v["os_legality_verdict"] == "legal" else "unknown"
    v["mechanism_class"] = mech

    print("SENDGUARD name verdict block - one name, asked on this machine, right now")
    print("name: %s" % v["requested_escaped"])
    print("requested_hex=%s  path_form=%s  os=%s  python=%s" % (
        v["requested_hex"], "extended" if extended else "plain", sys.platform, sys.version.split()[0]))
    if v["requested_hex_canon_token"] != v["requested_hex"]:
        print("requested_hex_canon_token=%s  <- the gate's canon_name token for this name is NOT its own "
              "UTF-8 bytes: it read the name as if it were a hex encoding of other bytes. This tool sends "
              "the real bytes to the probe and shows both here rather than picking one." % (
                  v["requested_hex_canon_token"]))
    print("rules: spec/cases.yaml freeze_revision=%s sha256=%s" % (rev, (actual or "?")[:12]))
    print_excluded_faces(excluded)
    defect = tool_spelling_defect_note(name)
    if defect:
        print("SPELLING WARNING (this tool and the gate can disagree about the token below): %s" % defect)
    print("")
    print("VERDICT  (the answer about this name; these are ci/equality.py's VERDICT_FIELDS)")
    print("  os_legality_verdict=%s  mechanism_class=%s  verdict_via=win32" % (
        v["os_legality_verdict"], v["mechanism_class"]))
    print("  criterion_for_that_word=%s" % v["criterion"])
    print("  phantom=%s  name_mutated=%s  enum_to_stat_agrees=%s  roundtrip_ok=%s" % (
        v["phantom"], v["name_mutated"], v["enum_to_stat_agrees"], v["roundtrip_ok"]))
    print("  len_triple=%s  bytes_written=%s  bytes_on_disk=%s  name_landed_as=%s" % (
        v["len_triple"], v["bytes_written"], v["bytes_on_disk"], v["name_landed_as"]))
    if v["name_landed_as"] != NOT_RECORDED:
        landed = bytes.fromhex(v["name_landed_as"]).decode("utf-8", "replace")
        print("  name_landed_as read back as: %s   (requested was %s)" % (
            escape_name(landed), v["requested_escaped"]))
    if v.get("read_landed_under"):
        print("  roundtrip_ok was measured on %s: the payload survived under THAT name, not the one you "
              "asked about. That is a different fact from 'the name round-tripped'." % escape_name(
                  bytes.fromhex(v["read_landed_under"]).decode("utf-8", "replace")))
    print("")
    print("PROBE  (what this language's standard library did; PROBE_FIELDS - allowed to differ between ports, "
          "and NOT the answer about your name)")
    print("  create_result=%s  error_stage=%s  read_result=%s  longpath_mechanism=%s" % (
        obs.get("create_result") or NOT_RECORDED, obs.get("error_stage") or NOT_RECORDED,
        v["read_result"], "prefix_rewrite" if extended else "none"))
    print("  deps_direct=0  deps_total=0  elapsed_ms=%s  external_timeout_s=%s  hung=%s" % (
        obs.get("_elapsed_ms"), obs.get("_timeout_s"), obs.get("_hung")))
    if obs.get("error_code") or obs.get("error_message"):
        print("  error_code=%s  error_message=%s" % (
            obs.get("error_code"), ascii_safe(obs.get("error_message"))))
    if v["read_skip_reason"]:
        print("  read_result=%s because %s" % (v["read_result"], v["read_skip_reason"]))
    if obs.get("_child_stderr"):
        print("  INSTRUMENT FAILURE, witnessed: %s" % obs["_child_stderr"])
    print("  api_entry=open_wb (the entry spec/FROZEN.md pins for python). No case_group is claimed: this is "
          "a tool probe, not a matrix cell.")
    print("")
    print("FROZEN-RULE ANSWER (computed before the machine was asked; the folder report prints this class)")
    if rule_findings:
        for f in rule_findings:
            print("  %s" % f.line())
            print("      risk: %s" % f.detail)
    else:
        print("  no rule fired: the frozen rule set has nothing to say about this name on windows")
    disagree = []
    if rule_findings:
        rv = rule_findings[0].verdict
        if rv != v["os_legality_verdict"]:
            if rv == "unknown":
                disagree.append("the frozen rules had no cell for this name (os_legality_verdict=unknown) and "
                                "this machine answered %s: new information, not a contradiction (%s)" % (
                                    v["os_legality_verdict"], v["criterion"]))
            else:
                disagree.append("rule says os_legality_verdict=%s, this machine says %s (%s)" % (
                    rv, v["os_legality_verdict"], v["criterion"]))
        if rule_findings[0].mechanism_class != v["mechanism_class"]:
            disagree.append("rule says mechanism_class=%s, probe filed %s" % (
                rule_findings[0].mechanism_class, v["mechanism_class"]))
    print("")
    print("RULE vs MACHINE: %s" % ("agree" if not disagree else "SEE BELOW"))
    if disagree and all(x.startswith("the frozen rules had no cell") for x in disagree):
        print("  (rulebook silent; the machine spoke)")
    for d in disagree:
        print("  %s" % d)
    if v["os_legality_verdict"] == "legal" and v["name_mutated"] == "true":
        print("  note: legal is not the same as intact. The name is permitted; what landed is a different "
              "name. Read this line before telling a client the send was clean.")
    if v["phantom"] == "true":
        print("  note: the write reported success and the directory holds nothing. Nothing downstream will "
              "tell you this happened.")
    print("")
    cells = committed_cells_for(results_dir, [v["requested_hex"], v["requested_hex_canon_token"]])
    print("COMMITTED CELLS ASKED ABOUT THESE EXACT INPUT BYTES (canonical faces only, cell-identity 9.5)")
    if not cells:
        print("  none on disk")
    for face, d in cells[:8]:
        print("  face=%s case_id=%s case_group=%s os_legality_verdict=%s mechanism_class=%s phantom=%s "
              "name_landed_as=%s bytes_on_disk=%s read_result=%s verdict_via=%s path_form=%s" % (
                  face, d.get("case_id"), d.get("case_group"), d.get("os_legality_verdict"),
                  d.get("mechanism_class"), d.get("phantom"), d.get("name_landed_as"),
                  d.get("bytes_on_disk"), d.get("read_result"), d.get("verdict_via"), d.get("path_form")))
        for fld in ("os_legality_verdict", "phantom", "name_mutated", "bytes_written"):
            theirs = d.get(fld)
            if theirs is None:
                continue
            t = "true" if theirs is True else ("false" if theirs is False else str(theirs))
            if t != v[fld]:
                print("    VERDICT-DISAGREE %s: cell=%s vs this tool=%s" % (fld, t, v[fld]))
    if len(cells) > 8:
        print("  TRUNCATED shown=8 total=%d" % len(cells))
    print("")
    print("SCRATCH left behind: %s" % escape_path(obs["_scratch"]))
    print("  no deletion logic (M19): every name probe leaves one directory holding the file it created.")
    risky = (v["os_legality_verdict"] != "legal" or v["name_mutated"] == "true"
             or v["phantom"] == "true" or bool(rule_findings))
    return EXIT_RISK if risky else EXIT_NO_RISK


def scan(folder, max_entries):
    """-> (entries, errors). entries = list of (rel, name, parent_rel, depth)."""
    entries, errors = [], []
    root = os.path.abspath(folder)
    entries.append((".", os.path.basename(root) or root, "", 0))
    stack = [(root, ".", 0)]
    while stack:
        path, rel, depth = stack.pop()
        if depth > 60:
            errors.append("depth stopped at %s" % rel)
            continue
        try:
            it = os.scandir(path)
        except OSError as exc:
            # strerror is localised on a zh-CN build; keep the report ASCII (M21).
            errors.append("cannot enumerate %s  %s" % (
                escape_name(rel) or ".", errno_note(exc)))
            continue
        with it:
            for dentry in it:
                if len(entries) >= max_entries:
                    errors.append("stopped at --max-entries=%d" % max_entries)
                    return entries, errors
                name = dentry.name
                child_rel = (rel + "/" + name) if rel else name
                is_dir = False
                try:
                    # is_dir() reads the enumeration's cached attributes on
                    # Windows; it does not reopen the file.
                    is_dir = dentry.is_dir()
                except OSError as exc:
                    errors.append("cannot classify %s  %s" % (
                        escape_name(child_rel), errno_note(exc)))
                entries.append((child_rel, name, rel, depth + 1))
                if is_dir:
                    stack.append((dentry.path, child_rel, depth + 1))
    return entries, errors


def collision_findings(entries, engine, targets):
    """Same-directory twins that differ only by case / normalisation / width.

    A single name cannot show these; they need the whole folder.  The frozen
    table measures one name per cell, so no cell in this repository covers the
    collision itself - every line here says so in its own prose.
    """
    out = []
    by_parent = {}
    for rel, name, parent, _depth in entries:
        by_parent.setdefault(parent, []).append((rel, name))
    kinds = (
        ("casefold", lambda n: n.casefold(), "case_folding",
         "differ only by letter case",
         "A case-insensitive volume - the default on windows and on APFS - cannot hold both, so the recipient "
         "gets one file where you sent two, and nothing fails at the moment of loss.",
         {"windows": "legal", "macos": "unknown", "ubuntu": "legal"}),
        ("NFC", lambda n: unicodedata.normalize("NFC", n), "unicode_normalization",
         "are the same text in two normalisation forms (composed and decomposed)",
         "Both can sit in the same folder on NTFS and ext4 - in this folder they do - but a layer that "
         "normalises on the way out (a zip writer, Finder, a web upload) decides that one of them IS the other, "
         "and the recipient ends up with one name where you had two.",
         {"windows": "unknown", "macos": "unknown", "ubuntu": "unknown"}),
        ("NFKC", lambda n: unicodedata.normalize("NFKC", n), "case_folding",
         "fold to the same text once width and compatibility forms are normalised "
         "(full-width vs half-width, compatibility jamo vs Hangul initial)",
         "A layer that folds width and compatibility forms treats them as one name, so a search, an automatic "
         "rename or a de-duplication step can collapse the two. Whether the client's layer does that is not "
         "measured in this repository.",
         {"windows": "legal", "macos": "unknown", "ubuntu": "unknown"}),
    )
    for parent, group in sorted(by_parent.items()):
        if len(group) < 2:
            continue
        reported = set()
        for _kind, fold, cls, phrase, outcome, tv in kinds:
            buckets = {}
            for _rel, name in group:
                buckets.setdefault(fold(name), []).append(name)
            for twins in buckets.values():
                distinct = sorted(set(twins))
                if len(distinct) < 2:
                    continue
                pair = tuple(distinct)
                if pair in reported:
                    continue
                reported.add(pair)
                names = ", ".join(escape_name(n) for n in pair)
                where = escape_path(parent) or "(root of the folder)"
                detail = ("these %d names in %s %s: %s. %s No single cell in spec/cases.yaml covers a pair: the "
                          "frozen table measures one name per cell, so the traps in backed_by only establish "
                          "that each name by itself is legal."
                          % (len(pair), where, phrase, names, outcome))
                for t in targets:
                    b = engine.backing(t, engine.category_ids.get(cls, []))
                    verdict = tv[t] if b else "unknown"
                    f = Finding(parent + " [pair]", t, cls, verdict, b, detail)
                    f.name_hex = "|".join(canon_name(n)[1] or "?" for n in pair)
                    out.append(f)
    return out


# --------------------------------------------------------------------------- #
# report
# --------------------------------------------------------------------------- #
def print_excluded_faces(excluded):
    """The gate's own wording, so the two documents read as one rule."""
    if not excluded:
        print("non_canonical_faces_excluded=0 (every face in results/ matched <port>.<os>.<arch>)")
        return
    print("== non-canonical faces excluded (naming rule: <port>.<os>.<arch>)")
    for e, n in excluded:
        print("   %-32s %d cell records" % (e, n))
    print("   excluded_faces=%d  These faces are on disk, published, and not compared; they were produced "
          "under an earlier contract revision or a different naming rule. This tool counts ports only over "
          "the canonical faces, so its denominator is the gate's." % len(excluded))


def print_report(root, targets, entries, errors, findings, engine, measured, spec_info, excluded):
    esc_root = escape_path(os.path.abspath(root))
    rev, actual, declared, matches = spec_info
    print("SENDGUARD name pre-flight - risk statements, not errors")
    print("scanned_folder: %s" % esc_root)
    print("targets: %s" % " ".join(targets))
    print("rules: spec/cases.yaml traps=%d freeze_revision=%s sha256=%s" % (
        len(engine.case_by_id), rev, (actual or "?")[:12]))
    if declared:
        print("  spec hash vs spec/FROZEN.md publication: %s" % (
            "matches" if matches else "DOES NOT MATCH - this tool is reading a spec the freeze does not name"))
    print("  words: spec/canonical.md closed sets (mechanism_class section 10, os_legality_verdict section 6)")
    for t in TARGETS:
        cells = measured.get(t, {})
        ports = sorted({p for slot in cells.values() for p in slot["ports"]})
        if cells:
            print("measured_cells: target=%s cells=%d ports=%s" % (t, len(cells), ",".join(ports) or "-"))
        else:
            print("measured_cells: target=%s cells=0 -> every verdict for this target is `unknown`: this "
                  "project has no cell for it. The prose still says what the public spec says, and that is not "
                  "measurement." % t)
    ports = sorted({p for cells in measured.values() for slot in cells.values() for p in slot["ports"]})
    print("ports_counted=%d faces=%s (canonical faces only)" % (len(ports), ",".join(ports) or "-"))
    print_excluded_faces(excluded)
    print("field classes (spec/cell-identity.md 9.3): each line prints VERDICT first - os_legality_verdict, "
          "mechanism_class, verdict_via - then EVIDENCE (which cells back it). Probe-class fields "
          "(create_result, error_stage, read_result, deps_*) are not printed here at all: they are what one "
          "language's stdlib did, not the answer about your name.")
    print("evidence_caveat: `backed_by` names result cells that exist on disk. Their existence is not the same "
          "as agreement - see the equality verdict in docs/evidence.md, which is produced by ci/equality.py, not "
          "by this tool.")
    print("")

    if not entries[1:]:
        print("nothing to report: the folder holds no entries (the folder itself was counted, excluded from findings).")
    if findings:
        print("FINDINGS (%d lines, %d entries involved)" % (
            len(findings), len({f.rel for f in findings})))
        for f in findings:
            print("  %s" % f.line())
            print("      risk: %s" % f.detail)
    else:
        print("FINDINGS: none. Every enumerated name was legal on every target asked, or was not checked for a "
              "reason listed in LIMITS below.")
    print("")

    risky = {f.rel for f in findings}
    checked = [e for e in entries if e[0] != "."]
    print("DENOMINATORS")
    print("  entries_enumerated=%d  entries_checked=%d  entries_with_risk=%d  entries_clean=%d" % (
        len(entries), len(checked), len(risky), len(checked) - len(risky)))
    print("  findings=%d  findings_by_target=%s" % (
        len(findings), " ".join("%s=%d" % (t, sum(1 for f in findings if f.target == t)) for t in targets)))
    backed = sum(1 for f in findings if f.backed)
    print("  findings_backed_by_a_measurement_cell=%d  findings_unverified(os_legality_verdict=unknown)=%d" % (
        backed, sum(1 for f in findings if f.verdict == "unknown")))
    print("")

    print("LIMITS - read these before telling a client the folder is clean")
    ambiguous = [n for (_r, n, _p, _d) in entries[1:]
                 if canon_name(n)[1] != true_hex(n)]
    if ambiguous:
        print("  %d of the %d enumerated names are made only of hex digits (e.g. %s), so ci/equality.py's "
              "canon_name reads them as an ENCODING of other bytes: the token this report prints for them is "
              "not their own UTF-8 bytes. `check.py --name NAME` prints both and warns." % (
                  len(ambiguous), len(entries) - 1, escape_name(ambiguous[0])[:24]))
    print("  not covered by this tool: mechanism_class=zip_roundtrip. It needs the archive's header flag bits, "
          "which a folder listing does not carry. A .zip in this folder may still unpack into a broken name.")
    print("  not covered: this tool reads names as the filesystem reports them. It cannot see what a browser, "
          "cloud drive or mail gateway renames on the way out; that layer is not measured in this repository "
          "(README section 2).")
    print("  not covered: exFAT/FAT32 volumes, mobile storage, and whether the recipient has long paths enabled "
          "- both are per-machine, and the 260 figure in this report is the classic plain-form budget.")
    print("  length verdicts use the path AT THIS LOCATION. Deeper unpacking changes the answer.")
    if errors:
        for e in errors:
            print("  enumeration problem: %s" % e)
    print("")
    print("exit_code meaning: 0=no risk 1=risk found 2=scan failed 3=bad usage 4=this tool crashed")


def run(argv):
    """Exit codes are kept apart from a crash on purpose: a traceback also exits 1,
    which is this tool's 'risk found' code.  Without this guard a bug in the tool
    would read as 'the folder has risky names' to any script using the code."""
    try:
        return main(argv)
    except SystemExit:
        raise
    except BaseException:
        import traceback
        traceback.print_exc()
        sys.stderr.write("SENDGUARD check.py crashed; this is not a verdict about your folder.\n")
        return EXIT_INTERNAL


# --------------------------------------------------------------------------- #
# --selftest-spec: does the engine flag the frozen traps it claims to?
# --------------------------------------------------------------------------- #
def selftest_spec(engine, cases, targets, spec_info):
    rev, actual, declared, matches = spec_info
    samples = decode_case_samples(cases)
    print("SENDGUARD spec self-test: every frozen sample in spec/cases.yaml, through the same rules,")
    print("against a synthetic root of 40 characters. This is not a disk test - no sample is materialised (N12).")
    print("rules: spec/cases.yaml freeze_revision=%s sha256=%s" % (rev, (actual or "?")[:12]))
    print("")
    flagged = []
    not_flagged = []
    undecodable = []
    for case in cases:
        cid = case["id"]
        for name, category in samples.get(cid, []):
            if name is None:
                undecodable.append((cid, category))
                continue
            rel = escape_name(name)
            fs = engine.rules_for(rel, name, "", 40 + len(name), list(targets))
            if fs:
                flagged.append((cid, category))
                for f in fs[:3]:
                    print("  %-6s %-30s -> %s  %s" % (cid, rel, f.mechanism_class, f.verdict))
            else:
                not_flagged.append((cid, category, rel))
        if not samples.get(cid):
            undecodable.append((cid, case["category"]))
    print("")
    print("DENOMINATORS (counting samples, not traps: T09/T14/T19 carry several members)")
    print("  traps_in_spec=%d  samples_decoded=%d  samples_not_decodable=%d" % (
        len(cases), len(flagged) + len(not_flagged), len(undecodable)))
    print("  samples_flagged=%d  samples_not_flagged=%d" % (len(flagged), len(not_flagged)))
    covered = {c for c, _ in flagged}
    print("  traps_with_at_least_one_flagged_sample=%d  traps_without=%d" % (
        len(covered), len(cases) - len(covered)))
    print("  target=%s (one target here; a name legal on this OS can be a finding on another)" % targets[0])
    for cid, category in undecodable:
        print("  NOT DECODABLE %s (category=%s) - sample_hex is a label, not UTF-8 hex" % (cid, category))
    for cid, category, why in not_flagged:
        print("  NOT FLAGGED %s (category=%s) %s" % (cid, category, why))
    print("")
    print("Why the not-flagged list is not something to tune away:")
    print("  zip_roundtrip                       - needs the archive's header flag bits; no name in the")
    print("                                        file is wrong, so a folder scan cannot answer it.")
    print("  unicode_normalization, case_folding - measured legal and landed unchanged (T06-T09, T19a/T19b),")
    print("                                        so one such name carries no risk by itself. They become")
    print("                                        reportable as a pair, which is what collision_findings()")
    print("                                        does on a real folder; on a clean folder they stay")
    print("                                        silent on purpose.")
    print("A checker that flagged every frozen trap for a clean folder would be a false-positive machine.")
    return 0 if flagged else 1


# Expectations below are QUOTED from evidence/S00-ctrl-baseline.md, which FROZEN.md names as the only
# allowed source of control expectations.  Nothing here is an expectation this tool invented.  The
# columns compared are probe-class fields on purpose: a control cell calibrates the ruler (spec/gate.md
# section 8), so what it pins is what the runtime did -- not the answer about a name.
CTRL_BASELINE = {
    "T-CTRL-ASCII": {"create_result": "ok", "error_stage": None,
                     "bytes_written": "28", "bytes_on_disk": "28", "roundtrip_ok": "true"},
    "T-CTRL-ILLEGAL-CHAR": {"create_result": "err_at_syscall", "error_stage": "syscall"},
    "T-CTRL-PARSE": {"create_result": "err_at_parse", "error_stage": "parse"},
    "T-CTRL-NAMETOOLONG": {"create_result": "err_at_syscall", "error_stage": "syscall"},
    "T-CTRL-CANON": {"roundtrip_ok": "true"},
}
BASELINE_PAYLOAD_SHA = "c9fe45b2fee8ea846f0cf4f2cacc2a891e7b082e7719923502d12a9813e21994"


def selftest_controls(engine, samples, root, spec_info, extended):
    rev, actual, declared, matches = spec_info
    results = []
    for sample in samples:
        cid = sample["id"]
        if not sample["sample_hex"]:
            results.append((cid, None, None, "NO PINNED SAMPLE BYTES in spec/cases.yaml"))
            continue
        name = bytes.fromhex(sample["sample_hex"]).decode("utf-8")
        payload_hex = sample["payload_hex"]
        obs = probe_name(name, payload_hex, extended=extended)
        v = verdict_from_observation(name, obs, payload_hex)
        rule_findings = engine.rules_for(name, name, ".", len(name), ["windows"])
        bad = []
        expect = CTRL_BASELINE.get(cid, {})
        got = {"create_result": obs.get("create_result"),
               "error_stage": obs.get("error_stage") or None,
               "bytes_written": v["bytes_written"], "bytes_on_disk": v["bytes_on_disk"],
               "roundtrip_ok": v["roundtrip_ok"]}
        for fld, want in expect.items():
            have = got.get(fld)
            if fld == "error_stage" and want is None:
                have = None if have in (None, "null") else have
            if str(have) != str(want):
                bad.append("%s: baseline=%s this run=%s" % (fld, want, have))
        sha = obs.get("read_sha256")
        if sha and sha != BASELINE_PAYLOAD_SHA:
            bad.append("payload sha256 != the sealed digest")
        results.append((cid, name, (obs, v, rule_findings), "; ".join(bad)))

    mismatch = [r for r in results if r[3]]
    print("SENDGUARD control-cell self-test -- the five pinned samples, asked once on this machine")
    print("INSTRUMENT-RED" if mismatch else "CONTROLS-OK")
    print("   (evidence/S00-ctrl-baseline.md is the only allowed source of control expectations; the "
          "comparison columns are probe-class fields because a control cell calibrates the ruler, "
          "spec/gate.md section 8)")
    print("rules: spec/cases.yaml freeze_revision=%s sha256=%s  path_form=%s" % (
        rev, (actual or "?")[:12], "extended" if extended else "plain"))
    print("")
    for cid, name, data, bad in results:
        print("%-22s %s" % (cid, ("BASELINE MISMATCH: " + bad) if bad else "matches baseline"))
        if data is None:
            continue
        obs, v, rule_findings = data
        print("  name=%s  requested_hex=%s  len_triple=%s" % (
            v["requested_escaped"], v["requested_hex"], v["len_triple"]))
        print("  VERDICT os_legality_verdict=%s mechanism_class=%s phantom=%s name_mutated=%s "
              "roundtrip_ok=%s bytes_written=%s bytes_on_disk=%s name_landed_as=%s verdict_via=win32" % (
                  v["os_legality_verdict"],
                  (rule_findings[0].mechanism_class if rule_findings else "unknown"),
                  v["phantom"], v["name_mutated"], v["roundtrip_ok"], v["bytes_written"],
                  v["bytes_on_disk"], v["name_landed_as"]))
        print("  PROBE create_result=%s error_stage=%s error_code=%s read_result=%s elapsed_ms=%s" % (
            obs.get("create_result"), obs.get("error_stage"), obs.get("error_code"),
            v["read_result"], obs.get("_elapsed_ms")))
        if v["read_skip_reason"]:
            print("  read_result=%s because %s" % (v["read_result"], v["read_skip_reason"]))
        if obs.get("_child_stderr"):
            print("  INSTRUMENT FAILURE, witnessed: %s" % obs["_child_stderr"])
    print("")
    print("DENOMINATORS")
    print("  controls_pinned_in_spec=%d  controls_probed=%d  controls_match_baseline=%d  "
          "controls_mismatch=%d" % (len(samples), len(results), len(results) - len(mismatch), len(mismatch)))
    print("  external_timeout_s=%d per cell; every cell left its scratch directory behind (M19, no deletion)"
          % PROBE_TIMEOUT_S)
    return EXIT_RISK if mismatch else EXIT_NO_RISK


# --------------------------------------------------------------------------- #
def parse_targets(value):
    if value == "all":
        return list(TARGETS)
    if value == "macos":
        return ["macos"]
    if value == "ubuntu":
        return ["ubuntu"]
    if value == "linux":  # accepted spelling, same frozen word as cases.yaml
        return ["ubuntu"]
    if value == "windows":
        return ["windows"]
    raise argparse.ArgumentTypeError("target must be windows|macos|ubuntu|linux|all")


def main(argv=None):
    class CheckArgumentParser(argparse.ArgumentParser):
        """argparse consumes a name beginning with a dash as an option, so
        `check.py --force.txt` cannot work. Say what does instead of printing usage."""

        def error(self, message):
            if "--force" in " ".join(sys.argv[1:]) or message.startswith("unrecognized arguments: -"):
                self.print_usage(sys.stderr)
                sys.stderr.write(
                    "hint: a file name that begins with a dash cannot be a bare argument. Pass it as "
                    "--name=NAME (with the equals sign), after `--`, or as --name-hex <utf8hex>.\n")
                sys.exit(EXIT_USAGE)
            super(CheckArgumentParser, self).error(message)

    ap = CheckArgumentParser(prog="check.py", description=__doc__.splitlines()[2])
    ap.add_argument("folder", nargs="?", help="folder to check (not read, only enumerated); a bare name "
                                              "that is not a path is probed as one file name")
    ap.add_argument("--name", help="one file name: ask this machine and print the verdict block")
    ap.add_argument("--name-hex", help="the same, as UTF-8 hex (how spec/cases.yaml pins samples), for names "
                                       "the shell cannot carry")
    ap.add_argument("--controls", action="store_true",
                    help="probe the five pinned control_samples in spec/cases.yaml against the sealed "
                         "control baseline in evidence/S00-ctrl-baseline.md")
    ap.add_argument("--extended", action="store_true",
                    help="ask through the \\\\?\\ prefix (path_form=extended) instead of the plain form")
    ap.add_argument("--target", default="all", type=parse_targets,
                    help="where the folder is going; default = all three (wherever it is going)")
    ap.add_argument("--max-entries", type=int, default=20000)
    ap.add_argument("--selftest-spec", action="store_true",
                    help="run the frozen cases.yaml samples through the rules and report which ones are flagged")
    args = ap.parse_args(argv)

    root = repo_root()
    cases = load_cases(os.path.join(root, "spec", "cases.yaml"))
    if not cases:
        sys.stderr.write("could not read spec/cases.yaml next to this tool (looked in %s)\n"
                         % os.path.join(root, "spec"))
        return EXIT_SCAN_FAILED
    measured, excluded = load_measured_cells(os.path.join(root, "results"))
    engine = Engine(measured, cases)
    info = spec_identity(root)
    samples = load_control_samples(os.path.join(root, "spec", "cases.yaml"))
    payload_hex = samples[0]["payload_hex"] if samples and samples[0]["payload_hex"] else \
        CANON_PAYLOAD.encode("utf-8").hex()

    if args.selftest_spec:
        return selftest_spec(engine, cases, ["windows"], info)
    if args.controls:
        return selftest_controls(engine, samples, root, info, args.extended)

    probe_name_value = None
    if args.name is not None:
        probe_name_value = args.name
    elif args.name_hex is not None:
        try:
            probe_name_value = bytes.fromhex(args.name_hex).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            sys.stderr.write("--name-hex must be UTF-8 hex (an even number of hex digits)\n")
            return EXIT_USAGE
    elif args.folder is not None and not looks_like_path(args.folder):
        # drag-one-argument front: an existing folder is a folder, a bare token is a name
        probe_name_value = args.folder

    if probe_name_value is not None:
        return print_verdict_block(probe_name_value, engine, os.path.join(root, "results"),
                                   args.extended, payload_hex, info, excluded)

    if not args.folder:
        sys.stderr.write("usage: python tool/check.py <folder|--name NAME|--name-hex HEX|--controls> "
                         "[--target windows|macos|ubuntu|all]\n")
        return EXIT_USAGE
    if os.path.isfile(args.folder):
        # one file dragged onto the launcher: its name is the question, its folder is not the subject
        print("(the argument is a file, so this is the verdict on its name alone: %s; pass the folder to "
              "check every name in it)" % escape_name(os.path.basename(args.folder)))
        return print_verdict_block(os.path.basename(args.folder), engine, os.path.join(root, "results"),
                                   args.extended, payload_hex, info, excluded)
    if not os.path.isdir(args.folder):
        # A path the plain form cannot address (CON.txt, an orphan trailing-dot name) is not
        # "unreachable": it is the finding.  Split the argument by hand -- os.path.abspath is
        # NOT safe to use here: measured on this box, abspath('<dir>\\CON.txt') returns
        # '\\\\.\\CON', i.e. it hands the argument to the console device namespace.
        BS = chr(92)
        raw = str(args.folder)
        cut = max(raw.rfind(BS), raw.rfind("/"))
        parent, leaf = (raw[:cut] or "."), raw[cut + 1:]
        rewrote = os.path.abspath(raw)
        note = ""
        if rewrote != os.path.abspath(parent) + BS + leaf:
            note = (" python's own path canonicalisation turned your argument into %s, which is the device "
                    "namespace, not a file in that folder." % escape_path(rewrote))
        listed, why = [], None
        try:
            with os.scandir(parent) as it:
                listed = [e.name for e in it]
        except OSError as exc:
            why = errno_note(exc)
        if leaf in listed:
            print("(the directory lists %s, but the path you gave cannot address it through the plain form "
                  "- that is itself the risk; below is the verdict on the name).%s" % (
                      escape_name(leaf), note))
            return print_verdict_block(leaf, engine, os.path.join(root, "results"),
                                       args.extended, payload_hex, info, excluded)
        if why:
            print("could not enumerate the parent of the argument you gave: %s" % why)
        sys.stderr.write("not a folder, or not reachable: %s\n" % escape_name(raw))
        return EXIT_SCAN_FAILED

    entries, errors = scan(args.folder, args.max_entries)
    targets = args.target
    findings = []
    root_len = len(os.path.abspath(args.folder))
    for rel, name, parent, _depth in entries:
        if rel == ".":
            continue
        total = root_len + len(rel) + 1
        findings.extend(engine.rules_for(rel, name, parent, total, targets))
    findings.extend(collision_findings(entries, engine, targets))
    print_report(args.folder, targets, entries, errors, findings, engine, measured, info, excluded)
    return EXIT_RISK if findings else EXIT_NO_RISK


def looks_like_path(token):
    """True when the argument could be meant as a location, so a typo is never
    turned into a file the tool creates on disk."""
    BS = chr(92)
    return (BS in token or "/" in token or token in (".", "..")
            or (len(token) > 1 and token[1] == ":") or token.startswith("\\\\"))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.exit(run(sys.argv[1:]))
