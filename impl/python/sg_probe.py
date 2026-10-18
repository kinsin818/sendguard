#!/usr/bin/env python3
"""SENDGUARD S02 python port -- probe child (one create leg, one fresh dir).

Called by sg_run.py as a child process:

    python sg_probe.py --task <taskfile.json> --out <outfile.json>

Sentences this file implements:
  * names arrive as UTF-8 hex and are decoded here -- no name is ever taken
    from prose (N12), and none is written back as prose;
  * a reserved device name is CREATED and LISTED only; its contents are never
    opened, and even its attribute query goes through the extended prefix so it
    cannot resolve into the device namespace (red line from the order);
  * bytes_on_disk authority is dir_view, taken out of the enumeration record
    itself (DirEntry.stat(follow_symlinks=False) does not address the path, so
    it cannot hit a device either);
  * no deletion anywhere (red line project rule);
  * the in-progress record is appended to the accumulator and flushed BEFORE
    and AFTER every phase that could block, so the parent's externally enforced
    5-second timeout still yields the create-side measurement and can name the
    phase that was never reached;
  * stdlib only, ASCII source, UTF-8-without-BOM output.
"""
import argparse
import ctypes
import hashlib
import json
import os
import pathlib
import stat as statmod
import sys
import time
from ctypes import wintypes

EXT = "\\\\?\\"          # the two-character \\?\ prefix, written as a Python literal
INVALID_ATTR = 0xFFFFFFFF
FILE_ATTRIBUTE_DIRECTORY = 0x10

ERROR_FILE_NOT_FOUND = 2
ERROR_PATH_NOT_FOUND = 3
ERROR_ACCESS_DENIED = 5
ERROR_INVALID_HANDLE = 6
ERROR_INVALID_NAME = 123
ERROR_INVALID_PARAMETER = 87
ERROR_BAD_PATHNAME = 161
ERROR_FILENAME_EXCED_RANGE = 206
ERROR_DIR_NAME_INVALID = 344

# Not an answer about the name's legality: the probe itself was refused.
NON_VERDICT = {ERROR_PATH_NOT_FOUND, ERROR_ACCESS_DENIED, ERROR_INVALID_PARAMETER,
               ERROR_INVALID_HANDLE, ERROR_BAD_PATHNAME}
# The namespace takes this name; there is simply no entry under it.
LEGAL_ABSENT = {ERROR_FILE_NOT_FOUND, ERROR_FILENAME_EXCED_RANGE, ERROR_DIR_NAME_INVALID}

_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_get_attrs = _k32.GetFileAttributesW
_get_attrs.argtypes = [wintypes.LPCWSTR]
_get_attrs.restype = wintypes.DWORD
_full_path = _k32.GetFullPathNameW
_full_path.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_wchar_p,
                       ctypes.POINTER(wintypes.LPCWSTR)]
_full_path.restype = wintypes.DWORD


def hexs(text):
    return text.encode("utf-8").hex()


def triple(text):
    if text is None:
        return None
    return {"code_points": len(text),
            "utf16_code_units": len(text.encode("utf-16-le")) // 2,
            "utf8_bytes": len(text.encode("utf-8"))}


def flush(path, acc, phase):
    doc = {"phase": phase, "results": acc}
    with open(path, "wb") as fh:
        fh.write(json.dumps(doc, ensure_ascii=True, sort_keys=True).encode("utf-8"))


def classify(exc):
    """parse = the language refused before the syscall; syscall = the OS answered."""
    tname = type(exc).__name__
    werr = getattr(exc, "winerror", None)
    eno = getattr(exc, "errno", None)
    if isinstance(exc, OSError):
        return ("syscall", tname, eno, werr, getattr(exc, "strerror", None))
    return ("parse", tname, None, None, str(exc)[:200])


def dir_view(d):
    """Enumeration only -- FindFirstFile record, never an open of an entry."""
    entries, raw = [], []
    with os.scandir(d) as it:
        for e in it:
            raw.append(e.name)
            row = {"name_hex": hexs(e.name)}
            try:
                st = e.stat(follow_symlinks=False)
                row["size"] = st.st_size
                row["is_dir"] = bool(statmod.S_ISDIR(st.st_mode))
            except OSError as exc:
                _s, tname, eno, werr, _se = classify(exc)
                row["size"] = None
                row["is_dir"] = None
                row["stat_error"] = {"type": tname, "errno": eno, "winerror": werr}
            entries.append(row)
    return raw, entries


def do_create(entry, target, payload):
    """bytes_written, or None when the entry writes no content."""
    if entry == "open_wb":
        with open(target, "wb") as fh:
            fh.write(payload)
        return len(payload)
    if entry == "pathlib.write_bytes":
        pathlib.Path(target).write_bytes(payload)
        return len(payload)
    if entry == "os.mkdir":
        os.mkdir(target)
        return None
    if entry == "os.rename":
        src = os.path.join(os.path.dirname(target),
                           "sgsrc-%d.bin" % (int(time.time() * 1000) % 1000000,))
        with open(src, "wb") as fh:
            fh.write(payload)
        os.rename(src, target)
        return len(payload)
    raise ValueError("unknown_entry:%s" % entry)


def attributes(dir_path, name, face):
    if "\x00" in name:
        # LPCWSTR ends at the first U+0000: querying anyway would answer about
        # a DIFFERENT (truncated) name and print a false verdict.
        return {"face": "none", "exists": None, "winerror": None, "is_dir": None,
                "attributes": None,
                "skipped": "embedded-U+0000: the wide-string API cannot carry this name"}
    p = os.path.join(dir_path, name)
    if face == "extended":
        p = EXT + p
    rc = _get_attrs(p)
    if rc == INVALID_ATTR:
        return {"face": face, "exists": None, "winerror": ctypes.get_last_error(),
                "is_dir": None, "attributes": None}
    return {"face": face, "exists": True, "winerror": None,
            "is_dir": bool(rc & FILE_ATTRIBUTE_DIRECTORY), "attributes": int(rc)}


def os_legality(dir_path, name):
    """Ask the OS directly, with the Win32 parser bypassed."""
    if "\x00" in name:
        return "unknown", {"probe": "none",
                           "outcome": "embedded-U+0000: not expressible in a Win32 name "
                                      "argument, so the OS was not asked"}
    d = attributes(dir_path, name, "extended")
    detail = {"probe": "GetFileAttributesW(\\\\?\\\\<dir>\\\\<name>)",
              "winerror": d["winerror"], "attributes": d["attributes"]}
    if d["exists"] is True:
        detail["outcome"] = "entry-present-in-namespace"
        return "legal", detail
    if d["winerror"] in LEGAL_ABSENT:
        detail["outcome"] = "name-accepted-no-entry-present"
        return "legal", detail
    if d["winerror"] == ERROR_INVALID_NAME:
        detail["outcome"] = "namespace-rejects-name"
        return "illegal", detail
    if d["winerror"] in NON_VERDICT:
        detail["outcome"] = "probe-refused-not-a-verdict"
        return "unknown", detail
    detail["outcome"] = "unmapped-code"
    return "unknown", detail


def win32_fullpath(dir_path, name):
    if "\x00" in name:
        return {"ok": False, "skipped": "embedded-U+0000: GetFullPathNameW would truncate"}
    buf = ctypes.create_unicode_buffer(8192)
    rc = _full_path(os.path.join(dir_path, name), 8192, buf, None)
    if rc == 0:
        return {"ok": False, "winerror": ctypes.get_last_error()}
    if rc > 8192:
        return {"ok": False, "winerror": 0, "note": "buffer-too-small", "needed": rc}
    return {"ok": True, "reported_hex": hexs(buf.value)}


def zip_report(target, expect_hex_list, entry_payload):
    """Re-open the artifact as an archive and report what the reader sees.

    T16's mechanism_class is zip bit 11, so the record needs the flag bits and
    the decoded entry names as the reader returns them -- names as hex only.
    entry_payload is the bytes stored INSIDE each entry, which is not the same
    thing as the artifact the create leg wrote.
    """
    import zipfile
    out = {"reader": "zipfile.ZipFile", "entries": [], "namelist_error": None}
    try:
        with zipfile.ZipFile(target) as zf:
            bad = zf.testzip()
            out["testzip_first_bad"] = bad
            for info in zf.infolist():
                row = {"name_hex": hexs(info.filename),
                       "flag_bits": info.flag_bits,
                       "bit11_utf8_name": bool(info.flag_bits & 0x800),
                       "create_system": info.create_system,
                       "compress_type": info.compress_type,
                       "file_size": info.file_size}
                try:
                    data = zf.read(info.filename)
                    row["read_ok"] = True
                    row["bytes_read"] = len(data)
                    row["bytes_match_payload"] = (data == entry_payload)
                except OSError as exc:
                    _s, tname, eno, werr, _se = classify(exc)
                    row["read_ok"] = False
                    row["read_error"] = {"type": tname, "errno": eno, "winerror": werr}
                except Exception as exc:
                    # Not an answer about the archive -- a defect in this reader.
                    # It must not be filed as a measurement.
                    row["read_ok"] = None
                    row["instrument_error"] = {"type": type(exc).__name__,
                                               "repr": str(exc)[:160]}
                out["entries"].append(row)
            out["namelist"] = [hexs(n) for n in zf.namelist()]
        out["expected_entry_hex_list"] = list(expect_hex_list)
        out["entry_names_match_expected"] = ([e["name_hex"] for e in out["entries"]]
                                             == list(expect_hex_list))
    except Exception as exc:
        _s, tname, eno, werr, serr = classify(exc)
        out["namelist_error"] = {"type": tname, "errno": eno, "winerror": werr, "strerror": serr}
    return out


def probe_one(dir_path, name, task, acc, names_before):
    entry = task["entry"]
    payload = bytes.fromhex(task["payload_hex"])
    reserved = bool(task["reserved"])
    face = task["path_form"]
    target = os.path.join(dir_path, name)
    if face == "extended":
        target = EXT + target
    out = task["out"]
    idx = task["_idx"]

    r = {"member_index": idx, "requested_name_hex": hexs(name),
         "requested_triple": triple(name), "path_form_face_used": face,
         "phases_reached": ["start"],
         "create_result": None, "error_stage": None, "error_type": None,
         "error_errno": None, "error_winerror": None, "error_strerror": None,
         "bytes_written": None, "dir_view": None, "dir_view_count": None,
         "residual_src_entries": None, "name_landed_as_hex": None,
         "name_landed_is_dir": None, "bytes_on_disk": None, "name_mutated": None,
         "same_name_hits": None, "landed_triple": None, "landed_linkage": None,
         "new_entries_hex": None, "path_view": None,
         "enum_to_stat_agrees": None, "phantom": None, "delivered_nothing": None,
         "read_result": None, "bytes_read": None, "roundtrip_ok": None,
         "sha256_self": None, "sha256_truth": None, "read_attempt_outcome": None,
         "read_blocked_reason": None, "os_legality_verdict": None,
         "os_legality_detail": None, "win32_fullpath": None}
    acc.append(r)
    t0 = time.monotonic()

    # ---- create ---------------------------------------------------------
    try:
        r["bytes_written"] = do_create(entry, target, payload)
        r["create_result"] = "ok"
        if r["bytes_written"] is not None:
            r["sha256_self"] = hashlib.sha256(payload).hexdigest()
    except Exception as exc:
        stage, tname, eno, werr, serr = classify(exc)
        r["create_result"] = "err_at_parse" if stage == "parse" else "err_at_syscall"
        r["error_stage"] = stage
        r["error_type"], r["error_errno"], r["error_winerror"] = tname, eno, werr
        r["error_strerror"] = serr
        r["error_message_redacted"] = "%s -- path and name redacted, never materialised" % tname
    r["phases_reached"].append("created")
    flush(out, acc, "created:%d" % idx)

    # ---- dir_view (list; always safe) ------------------------------------
    raw, entries = [], []
    try:
        raw, entries = dir_view(dir_path)
        r["dir_view"] = entries
        r["dir_view_count"] = len(raw)
        r["residual_src_entries"] = len([n for n in raw if n.startswith("sgsrc-")])
    except Exception as exc:
        stage, tname, eno, werr, serr = classify(exc)
        r["dir_view_error"] = {"type": tname, "errno": eno, "winerror": werr, "strerror": serr}
    r["phases_reached"].append("dir_view")
    flush(out, acc, "dir_view:%d" % idx)

    # ---- which enumeration entry is THIS artifact? ----------------------
    # DirEntry.stat() on this box reports st_ino == 0 for every entry, so the
    # file index cannot link the requested path to an entry. The linkage used
    # here is differential: entries that were not in the directory before the
    # create. Exact-name match wins when it exists (no mutation).
    hits = [n for n in raw if n == name]
    r["same_name_hits"] = len(hits)
    new_names = [n for n in raw if n not in names_before]
    r["new_entries_hex"] = [hexs(n) for n in new_names]
    # Scaffolding (the source file an os.rename leg needs) is never an artifact
    # of this cell, and a create that FAILED lands nothing -- crediting either
    # one would report bytes_on_disk for a file that does not exist under the
    # requested name.
    real_new = [n for n in new_names if not n.startswith("sgsrc-")]
    r["residual_src_new_entries"] = len(new_names) - len(real_new)
    landed, linkage = None, "none"
    if hits:
        landed, linkage = hits[0], "exact-name"
    elif r["create_result"] == "ok" and len(real_new) == 1:
        landed, linkage = real_new[0], "differential-single-new-entry"
    elif r["create_result"] == "ok" and len(real_new) > 1:
        linkage = "ambiguous(%d-new-entries)" % len(real_new)
    elif r["create_result"] != "ok" and real_new:
        linkage = "excluded-create-did-not-succeed(%d-new)" % len(real_new)
    r["landed_linkage"] = linkage
    by_hex = {e["name_hex"]: e for e in entries}
    if landed is not None:
        r["name_landed_as_hex"] = hexs(landed)
        r["landed_triple"] = triple(landed)
        r["name_mutated"] = (landed != name)
        row = by_hex.get(hexs(landed), {})
        r["name_landed_is_dir"] = row.get("is_dir")
        r["bytes_on_disk"] = row.get("size")
    else:
        r["name_mutated"] = None
        r["bytes_on_disk"] = None
    if r["create_result"] == "ok":
        r["delivered_nothing"] = (landed is None)

    # ---- path_view (attributes; extended face for reserved names) --------
    pv_face = "extended" if reserved else "plain"
    r["path_view"] = attributes(dir_path, name, pv_face)
    if reserved:
        r["path_view"]["note"] = ("plain face not queried: the parser resolves this "
                                  "name into the device namespace (red line)")
    dv_has = landed is not None
    if r["path_view"].get("skipped"):
        r["enum_to_stat_agrees"] = None
        r["phantom"] = None
        r["path_view_note"] = "two-view comparison not run: the path was never addressed"
    else:
        pv_exists = r["path_view"]["exists"] is True
        r["enum_to_stat_agrees"] = (dv_has == pv_exists)
        r["phantom"] = (dv_has != pv_exists)
    r["phases_reached"].append("path_view")
    flush(out, acc, "path_view:%d" % idx)

    # ---- win32 parser rewriting (string API, opens nothing) --------------
    r["win32_fullpath"] = ({"ok": False, "skipped": "reserved_device_name_plain_face"}
                           if reserved else win32_fullpath(dir_path, name))

    # ---- read (contents) ------------------------------------------------
    if reserved:
        r["read_blocked_reason"] = "red_line_no_content_open_for_reserved_device_name"
    elif r["name_landed_is_dir"] is True:
        r["read_blocked_reason"] = "artifact-is-a-directory-no-bytes-to-read"
        try:
            listing, _ = dir_view(os.path.join(dir_path, name))
            r["artifact_dir_listing_count"] = len(listing)
        except Exception as exc:
            _s, tname, eno, werr, _se = classify(exc)
            r["artifact_dir_listing_error"] = {"type": tname, "errno": eno, "winerror": werr}
    else:
        try:
            with open(target, "rb") as fh:
                data = fh.read()
            r["read_result"] = "ok" if len(data) > 0 else "eof"
            r["bytes_read"] = len(data)
            r["sha256_truth"] = hashlib.sha256(data).hexdigest()
            r["roundtrip_ok"] = (data == payload)
        except Exception as exc:
            _s, tname, eno, werr, serr = classify(exc)
            r["read_attempt_outcome"] = {"type": tname, "errno": eno, "winerror": werr,
                                         "strerror": serr}
            if werr == ERROR_INVALID_HANDLE:
                r["read_result"] = "err6"
            else:
                r["read_blocked_reason"] = "no-artifact-or-os-refused-read:%s(winerror=%s)" % (tname, werr)
    r["phases_reached"].append("read")
    flush(out, acc, "read:%d" % idx)

    if task.get("zip_report") and r["read_result"] in ("ok", "eof"):
        entry_payload = bytes.fromhex(task.get("zip_content_hex") or task["payload_hex"])
        r["zip_report"] = zip_report(target, task.get("zip_expect_entry_hex", []), entry_payload)
        if any(e.get("instrument_error") for e in r["zip_report"].get("entries", [])):
            r["instrument_conflict"] = True
            r["instrument_conflict_reason"] = "zip_report raised a non-OSError: the reader is broken, the archive was not asked"
        r["phases_reached"].append("zip_report")
        flush(out, acc, "zip_report:%d" % idx)

    verdict, detail = os_legality(dir_path, name)
    r["os_legality_verdict"], r["os_legality_detail"] = verdict, detail
    r["path_len_triple_requested"] = triple(target)
    r["elapsed_ms_child"] = int((time.monotonic() - t0) * 1000)
    r["phases_reached"].append("done")
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    task = json.loads(open(a.task, "rb").read().decode("utf-8"))
    task["out"] = a.out
    acc = []
    flush(a.out, acc, "loaded")
    for idx, hx in enumerate(task["name_hex_list"]):
        task["_idx"] = idx
        name = bytes.fromhex(hx).decode("utf-8")
        try:
            names_before = set(dir_view(task["dir"])[0])
        except Exception:
            names_before = set()
        try:
            r = probe_one(task["dir"], name, task, acc, names_before)
            r["pre_existing_entries"] = len(names_before)
            if idx == 0:
                r["scratch_empty_at_first_use"] = (len(names_before) == 0)
        except Exception as exc:
            acc.append({"member_index": idx, "requested_name_hex": hx,
                        "pre_existing_entries": len(names_before),
                        "probe_crashed": True, "error_type": type(exc).__name__,
                        "error_repr": str(exc)[:200]})
        flush(a.out, acc, "probed:%d" % idx)
    flush(a.out, acc, "done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
