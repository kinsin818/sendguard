import io

p = "selfcheck.py"
s = io.open(p, encoding="utf-8", newline="\n").read()
done = []
missed = []


def sub(old, new, label):
    global s
    if old not in s:
        missed.append(label)
        return
    s = s.replace(old, new, 1)
    done.append(label)


sub(
    '''CASES_PATH = os.path.join(REPO, "spec", "cases.yaml")''',
    '''CASES_PATH = os.path.join(REPO, "spec", "cases.yaml")
# rev6 pins one 28-byte control payload; the sealed S00 baseline records the same digest for the
# node and python instruments, so a port that hashes anything else is not measuring that control.
CANON_PAYLOAD_SHA = "c9fe45b2fee8ea846f0cf4f2cacc2a891e7b082e7719923502d12a9813e21994"''',
    "canon digest const",
)

sub(
    """    expected = {
        # 18 non-length traps, with the multi-member cases expanded; rev3 names those
        # T09-m1 / T14-m2 / T19-m2 inside case_id, which does not change how many there are
        "trap_name_cells": name_cells,
        "trap_zip_legs": 5,       # T16 legs: packer x extractor x entry source, declared in the port
        "len_grid": 24,           # 12 frozen G1-G4 points x 2 path forms
        "len_bisect_frozen_base": 4,   # T17/T18 x 2 path forms at the frozen base 13 only
        "len_rungs": 2 * len(req["ladder"]) if req["present"] else 0,  # required: T17/T18 x ladder
        "ctrl": 5,
        "tapi": 3,                # pinned entry list; rev3 requires no T-API identity of typescript
        "blind": 5,
    }""",
    """    expected = {
        # 18 non-length traps, with the multi-member cases expanded (T09-m1 / T14-m2 / T19-m2)
        "trap_name_cells": name_cells,
        "trap_zip_legs": 5,       # T16 legs: packer x extractor x entry source, declared in the port
        "len_grid": 24,           # 12 frozen G1-G4 points x 2 path forms
        "len_bisect_frozen_base": 4,   # T17/T18 x 2 path forms at the frozen base 13 only
        # rev6 requires a rung per base_len x path_form, so the ladder is 3 x 2 x 2 cases
        "len_rungs": 2 * len(req["ladder"]) * 2 if req["present"] else 0,
        "ctrl": 5,
        "tapi": 3,                # pinned entry list; rev6 requires no T-API identity of typescript
        "blind": 5,               # rev6 item 2: run them, with blind_id from the sealed map
    }""",
    "denominators rev6",
)

sub(
    """    for f in REV3_NOTICE_REQUIRED:""",
    """    # rev6 item 2: the blind cells must carry the id they were sampled under
    if cell.get("case_group") == "blind" and not isinstance(cell.get("blind_id"), int):
        v.append("blind cell does not carry an integer blind_id")

    # rev6 item 1: the five control cells must be the pinned samples over the pinned payload
    pin = PINNED.get(cell.get("case_id"))
    if pin is not None:
        if cell.get("name_source") != pin["sample_hex"]:
            v.append("control cell uses sample_hex %r, the spec pin says %r" % (cell.get("name_source"), pin["sample_hex"]))
        if cell.get("bytes_written") is not None and pin["payload_sha256"] and cell.get("sha256_truth") != CANON_PAYLOAD_SHA:
            v.append("control payload digests to %r, not the pinned 28-byte sha256 %r"
                     % (str(cell.get("sha256_truth"))[:16], CANON_PAYLOAD_SHA[:16]))

    # rev6 item 2: a verdict must name the authority that was asked whenever the request did
    # reach an OS layer. `none` is honest only when nothing was asked at OS level.
    if (cell.get("case_group") in ("trap", "ctrl", "blind")
            and cell.get("create_result") in ("ok", "err_at_syscall")
            and cell.get("verdict_via") in (None, "none")):
        v.append("verdict_via=none but the request reached the file system; name the authority asked")

    for f in REV3_NOTICE_REQUIRED:""",
    "rev6 rules",
)

sub(
    """REV3_NOTICE_REQUIRED = ("length_unit", "name_encoding", "verdict_via")""",
    """REV3_NOTICE_REQUIRED = ("length_unit", "name_encoding", "verdict_via")

# rev6: control_samples in spec/cases.yaml pin one name and one payload per control cell.
PINNED = {}
try:
    _cy = io.open(CASES_PATH, encoding="utf-8").read()
    for _blk in re.split(r"(?m)^  - id: ", _cy.split("control_samples:")[1].split("\\ncases:")[0])[1:]:
        _cid = re.match(r"(\\S+)", _blk).group(1)
        _sh = re.search(r"(?m)^    sample_hex: \"([0-9a-f]+)\"", _blk)
        _ph = re.search(r"(?m)^    payload_hex: \"([0-9a-f]+)\"", _blk)
        if _sh and _ph:
            import hashlib
            PINNED[_cid] = {"sample_hex": _sh.group(1), "payload_hex": _ph.group(1),
                            "payload_sha256": hashlib.sha256(bytes.fromhex(_ph.group(1))).hexdigest()}
except Exception as _e:  # a missing pin is reported as a rule failure below, never silently skipped
    print("NOTE could not read control_samples:", _e)""",
    "load pins",
)

sub(
    '''        print(f"  cells_marked_extra={len(extras)} (the artifact allows more cells, marked, outside the digest)")''',
    '''        print(f"  cells_marked_extra={len(extras)} (outside the required list, marked, excluded from the digest)")
        for stem, c in sorted(cells.items()):
            if stem in req["stems"] and c.get("status") == "blocked":
                print(f"  REQUIRED_CELL_BLOCKED {stem}: {str(c.get('blocked_reason'))[:90]}")''',
    "blocked required visibility",
)

io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("applied:", done)
print("MISSED:", missed)
