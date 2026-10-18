#!/usr/bin/env python3
"""SENDGUARD S02 python port -- zip round-trip child (packer/extractor legs).

    python sg_probe_zip.py --task <taskfile.json> --out <outfile.json>

Task carries: dir (fresh, verified empty by the parent), zip_name_hex,
entry_name_hex_list, payload_hex, extractor ("zipfile" | "shutil").

The archive is written by the primary entry (open-style write_bytes) so this leg
answers the delivery question -- "can the recipient unpack what I packed" --
and the extractor is the only thing that varies. Names are read back as hex;
nothing is deleted (red line project rule); a 5-second timeout is enforced by the parent.
"""
import argparse
import hashlib
import json
import os
import stat as statmod
import time
import zipfile


def hexs(t):
    return t.encode("utf-8").hex()


def dir_view(d):
    entries = []
    with os.scandir(d) as it:
        for e in it:
            row = {"name_hex": hexs(e.name)}
            try:
                st = e.stat(follow_symlinks=False)
                row["size"] = st.st_size
                row["is_dir"] = bool(statmod.S_ISDIR(st.st_mode))
            except OSError as exc:
                row["size"] = None
                row["is_dir"] = None
                row["stat_error"] = {"type": type(exc).__name__,
                                     "winerror": getattr(exc, "winerror", None)}
            entries.append(row)
    return entries


def classify(exc):
    tname = type(exc).__name__
    if isinstance(exc, OSError):
        return ("syscall", tname, getattr(exc, "errno", None),
                getattr(exc, "winerror", None), getattr(exc, "strerror", None))
    return ("parse", tname, None, None, str(exc)[:200])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    task = json.loads(open(a.task, "rb").read().decode("utf-8"))
    d = task["dir"]
    payload = bytes.fromhex(task["payload_hex"])
    entry_names = [bytes.fromhex(h).decode("utf-8") for h in task["entry_name_hex_list"]]
    zip_name = bytes.fromhex(task["zip_name_hex"]).decode("utf-8")
    extractor = task["extractor"]
    t0 = time.monotonic()

    r = {"extractor": extractor, "packer": "zipfile.ZipFile(w)",
         "zip_name_hex": hexs(zip_name),
         "entry_name_hex_list": list(task["entry_name_hex_list"]),
         "phases_reached": ["start"],
         "create_result": None, "error_stage": None, "error_type": None,
         "error_errno": None, "error_winerror": None, "error_strerror": None,
         "bytes_written": None, "zip_entries_written": None,
         "bit11_set_per_entry": None, "read_result": None, "bytes_on_disk": None,
         "name_landed_as_hex": None, "same_name_hits": None, "name_mutated": None,
         "roundtrip_ok": None, "sha256_self": None, "sha256_truth": None,
         "extract_dir_view": None, "extract_error": None, "delivered_nothing": None,
         "phantom": None, "enum_to_stat_agrees": None, "elapsed_ms_child": None}
    doc = {"phase": "start", "results": [r]}

    def flush(phase):
        doc["phase"] = phase
        with open(a.out, "wb") as fh:
            fh.write(json.dumps(doc, ensure_ascii=True, sort_keys=True).encode("utf-8"))

    flush("start")
    r["sha256_self"] = hashlib.sha256(payload).hexdigest()
    zip_path = os.path.join(d, zip_name)
    extract_dir = os.path.join(d, "extracted")

    # ---- pack ----------------------------------------------------------
    try:
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for nm in entry_names:
                zi = zipfile.ZipInfo(nm, date_time=(2026, 10, 11, 12, 0, 0))
                zi.compress_type = zipfile.ZIP_DEFLATED
                zf.writestr(zi, payload)
            r["zip_entries_written"] = len(entry_names)
        with zipfile.ZipFile(zip_path) as zf:
            r["bit11_set_per_entry"] = [{"name_hex": hexs(i.filename),
                                         "flag_bits": i.flag_bits,
                                         "bit11": bool(i.flag_bits & 0x800)}
                                        for i in zf.infolist()]
        r["create_result"] = "ok"
        with open(zip_path, "rb") as fh:
            r["bytes_written"] = len(fh.read())
    except Exception as exc:
        stage, tname, eno, werr, serr = classify(exc)
        r["create_result"] = "err_at_parse" if stage == "parse" else "err_at_syscall"
        r["error_stage"], r["error_type"] = stage, tname
        r["error_errno"], r["error_winerror"], r["error_strerror"] = eno, werr, serr
        r["error_message_redacted"] = "%s -- path and name redacted" % tname
    r["phases_reached"].append("packed")
    flush("packed")

    # ---- extract -------------------------------------------------------
    ok_extract = None
    if r["create_result"] == "ok":
        try:
            os.mkdir(extract_dir)
            if extractor == "zipfile":
                with zipfile.ZipFile(zip_path) as zf:
                    zf.extractall(extract_dir)
            elif extractor == "shutil":
                import shutil
                shutil.unpack_archive(zip_path, extract_dir, "zip")
            else:
                raise ValueError("unknown_extractor:%s" % extractor)
            ok_extract = True
        except Exception as exc:
            ok_extract = False
            _s, tname, eno, werr, serr = classify(exc)
            r["extract_error"] = {"type": tname, "errno": eno, "winerror": werr, "strerror": serr}
    r["phases_reached"].append("extracted")
    flush("extracted")

    # ---- observe -------------------------------------------------------
    try:
        view = dir_view(extract_dir)
        r["extract_dir_view"] = view
        hexes = [v["name_hex"] for v in view]
        expect = list(task["entry_name_hex_list"])
        first = None
        r["same_name_hits"] = len([h for h in hexes if h in expect])
        r["name_landed_as_hex"] = hexes[0] if hexes else None
        r["name_mutated"] = (sorted(hexes) != sorted(expect))
        r["delivered_nothing"] = (ok_extract is True and not hexes)
        if hexes:
            first = os.path.join(extract_dir, bytes.fromhex(hexes[0]).decode("utf-8"))
            try:
                with open(first, "rb") as fh:
                    data = fh.read()
                r["read_result"] = "ok" if len(data) else "eof"
                r["bytes_on_disk"] = len(data)
                r["sha256_truth"] = hashlib.sha256(data).hexdigest()
                r["roundtrip_ok"] = (r["sha256_truth"] == r["sha256_self"]
                                     and sorted(hexes) == sorted(expect))
            except Exception as exc:
                _s, tname, eno, werr, serr = classify(exc)
                r["extract_error"] = dict(r["extract_error"] or {})
                r["read_after_extract_error"] = {"type": tname, "errno": eno, "winerror": werr}
        r["enum_to_stat_agrees"] = (bool(hexes) == (first is not None and os.path.exists(first)))
        r["phantom"] = not r["enum_to_stat_agrees"]
    except Exception as exc:
        _s, tname, eno, werr, serr = classify(exc)
        r["dir_view_error"] = {"type": tname, "errno": eno, "winerror": werr, "strerror": serr}
    r["phases_reached"].append("observed")
    r["elapsed_ms_child"] = int((time.monotonic() - t0) * 1000)
    flush("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
