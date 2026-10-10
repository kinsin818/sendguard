#!/usr/bin/env python3
"""envfacts.py -- one re-runnable collector for machine facts that six language
ports must agree on.

Single file, standard library only. Prints one JSON object to stdout and writes
the same JSON to the output path given as the only positional argument
(UTF-8, no BOM, LF line endings).

Collected:
  - OS name/version/build, CPU architecture, locale, console code pages
  - per volume: filesystem name, max_component (GetVolumeInformationW via
    ctypes), volume serial, drive-type (fixed/ram/removable/...) if told
  - registry LongPathsEnabled (HKLM\\SYSTEM\\CurrentControlSet\\Control\\FileSystem);
    "absent" and "a value" are reported as different facts
  - 8.3 short-name generation state per volume via fsutil (list form, no shell);
    if the command needs elevation, "needs-elevation" is recorded, never a guess
  - every runtime candidate on PATH (node, python, go, java, dotnet, rustc,
    tsc): RESOLVED executable path (all of them, not just the first), version
    string from running it, and a byte-scan of that executable for the manifest
    token b"longPathAware" (byte scan, NOT a PE manifest parse)
  - Unicode data version where the runtime exposes one
    (unicodedata.unidata_version); plus a probe set of characters whose
    normalisation behaviour changed across Unicode versions, recorded as "probed"

Honesty rules baked in:
  - every external command runs in list form; rc is checked before output is used
  - rc==0 with empty output is recorded as a contradiction, not as success
  - anything not obtainable here is recorded as "not-obtainable-here"
  - every list carries its own denominator (volumes_scanned, runtimes_found, ...)
"""

import argparse
import json
import locale
import os
import platform
import re
import string
import subprocess
import sys
import unicodedata

IS_WINDOWS = os.name == "nt"
MANIFEST_TOKEN = b"longPathAware"
EXCERPT_PAD = 36  # ASCII-safe excerpt window around a manifest-token hit
RUNTIME_NAMES = ["node", "python", "go", "java", "dotnet", "rustc", "tsc"]

# name -> (argv-after-resolved-exe, stream that carries the version)
VERSION_CMDS = {
    "node": (["--version"], "stdout"),
    "python": (["--version"], "combined"),
    "go": (["version"], "stdout"),
    "java": (["-version"], "combined"),  # java prints version to stderr
    "dotnet": (["--version"], "stdout"),
    "rustc": (["--version"], "stdout"),
    "tsc": (["--version"], "combined"),
}

NOT_OBTAINABLE = "not-obtainable-here"


# ---------------------------------------------------------------- helpers ----

def ascii_safe_excerpt(raw):
    """Replace every non-printable ASCII byte/char with '.', keep real text.

    Accepts bytes or str; with str, any character outside printable ASCII is
    dropped to '.' the same way a raw byte would be.
    """
    if isinstance(raw, str):
        raw = raw.encode("utf-8", errors="replace")
    return "".join(chr(b) if 32 <= b <= 0x7E else "." for b in raw)


def decode_command_output(raw_bytes):
    """Decode command output bytes: utf-8 first, then locale, then cp936/gbk,
    then latin-1 as a never-failing last resort. Returns (text, encoding_used).
    Localized Windows tool output (e.g. fsutil on cp936) must not be mangled
    into replacement characters -- the numeric state in the text is the fact."""
    if raw_bytes is None:
        return "", "none"
    candidates = ["utf-8", locale.getpreferredencoding(False), "cp936", "gbk"]
    tried = set()
    for enc in candidates:
        if not enc or enc in tried:
            continue
        tried.add(enc)
        try:
            return raw_bytes.decode(enc), enc
        except (UnicodeDecodeError, LookupError):
            continue
    return raw_bytes.decode("latin-1", errors="replace"), "latin-1-fallback"


class CommandRunner:
    """Run list-form commands, check rc before touching output, and count."""

    def __init__(self):
        self.commands_run = 0
        self.command_failures = 0
        self.contradictions = 0

    def run(self, argv, timeout=60):
        """Return a dict record; never raises on command failure."""
        self.commands_run += 1
        rec = {"argv": argv}
        try:
            proc = subprocess.run(
                argv,
                shell=False,
                capture_output=True,
                timeout=timeout,
            )
        except FileNotFoundError:
            rec.update(rc=None, error="executable-not-found", status="failed")
            self.command_failures += 1
            return rec
        except (OSError, subprocess.TimeoutExpired) as exc:
            rec.update(rc=None, error=str(exc), status="failed")
            self.command_failures += 1
            return rec
        stdout, enc_out = decode_command_output(proc.stdout)
        stderr, enc_err = decode_command_output(proc.stderr)
        stdout = stdout.strip()
        stderr = stderr.strip()
        rec["rc"] = proc.returncode
        rec["stdout"] = stdout
        rec["stderr"] = stderr
        rec["decoded_as"] = {"stdout": enc_out, "stderr": enc_err}
        if proc.returncode != 0:
            self.command_failures += 1
            lowered = (stdout + " " + stderr).lower()
            access_like = ("access is denied" in lowered
                           or "access denied" in lowered
                           or "elevation" in lowered
                           or "requires elevation" in lowered
                           or "administrator" in lowered)
            rec["status"] = "needs-elevation" if access_like else "failed"
        elif not stdout and not stderr:
            # rc=0 with no output is a contradiction, not a pass
            self.contradictions += 1
            rec["status"] = "contradiction-rc0-no-output"
        else:
            rec["status"] = "ok"
        return rec


# ------------------------------------------------------------------ os ----

def collect_os(runner):
    out = {}
    out["system"] = platform.system()
    out["release"] = platform.release()
    out["version"] = platform.version()
    if IS_WINDOWS:
        try:
            wsv = sys.getwindowsversion()
            out["build"] = wsv.build
            out["service_pack"] = wsv.service_pack or None
            out["platform_name"] = platform.platform()
        except OSError as exc:
            out["build"] = {"status": "error", "detail": str(exc)}
    else:
        out["build"] = {"status": NOT_OBTAINABLE}
    out["cpu_architecture"] = {
        "platform_machine": platform.machine(),
        "PROCESSOR_ARCHITECTURE": os.environ.get("PROCESSOR_ARCHITECTURE"),
        "ENVIRON_ARCHITEW6432": os.environ.get("PROCESSOR_ARCHITEW6432"),
    }
    try:
        out["locale"] = {
            "getlocale": list(locale.getlocale()),
            "getdefaultlocale_env": os.environ.get("LC_ALL")
            or os.environ.get("LANG"),
            "preferred_encoding": locale.getpreferredencoding(False),
            "utf8_mode_enabled": bool(getattr(sys.flags, "utf_mode", 0)),
        }
    except (ValueError, OSError) as exc:
        out["locale"] = {"status": "error", "detail": str(exc)}
    if IS_WINDOWS:
        import ctypes
        k32 = ctypes.windll.kernel32
        cp_in = k32.GetConsoleCP()
        cp_out = k32.GetConsoleOutputCP()
        # rc discipline: 0 is a documented failure sentinel for these APIs
        out["console_code_page"] = {
            "input": cp_in if cp_in != 0 else "api-returned-0-failure",
            "output": cp_out if cp_out != 0 else "api-returned-0-failure",
            "method": "kernel32.GetConsoleCP/GetConsoleOutputCP via ctypes",
        }
        if cp_in == 0 or cp_out == 0:
            out["console_code_page"]["last_error"] = ctypes.GetLastError()
    else:
        out["console_code_page"] = {"status": NOT_OBTAINABLE}
    out["self_interpreter"] = {
        "resolved_executable": os.path.realpath(sys.executable),
        "python_version": platform.python_version(),
        "argv0": sys.argv[0] if sys.argv else None,
    }
    return out


# -------------------------------------------------------------- volumes ----

DRIVE_TYPES = {
    0: ("unknown", "the API returned 0 (failure)"),
    1: ("no-root-dir", "path is not a root directory of a drive"),
    2: ("removable", "GetDriveTypeW: removable media"),
    3: ("fixed", "GetDriveTypeW: fixed (local) disk"),
    4: ("remote", "GetDriveTypeW: network/remote"),
    5: ("cdrom", "GetDriveTypeW: CD-ROM"),
    6: ("ram-disk", "GetDriveTypeW: RAM disk"),
    7: ("ramdisk-legacy", "GetDriveTypeW: legacy RAM disk"),
}


def collect_volumes(runner):
    volumes = []
    denom = {"volumes_scanned": 0, "api_failures": 0}
    if not IS_WINDOWS:
        denom["status"] = NOT_OBTAINABLE
        return volumes, denom
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.windll.kernel32
    k32.GetVolumeInformationW.argtypes = [
        wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.DWORD), wintypes.LPWSTR, wintypes.DWORD,
    ]
    k32.GetVolumeInformationW.restype = wintypes.BOOL
    k32.GetLogicalDrives.restype = wintypes.DWORD
    k32.GetDriveTypeW.argtypes = [wintypes.LPCWSTR]
    k32.GetDriveTypeW.restype = wintypes.UINT

    bitmask = k32.GetLogicalDrives()
    if bitmask == 0:
        denom["status"] = "GetLogicalDrives-returned-0"
        denom["last_error"] = ctypes.GetLastError()
        return volumes, denom
    for idx, letter in enumerate(string.ascii_uppercase):
        if not (bitmask >> idx) & 1:
            continue
        root = letter + ":\\"
        vol_buf = ctypes.create_unicode_buffer(261)
        fs_buf = ctypes.create_unicode_buffer(261)
        serial = wintypes.DWORD()
        max_comp = wintypes.DWORD()
        flags = wintypes.DWORD()
        ok = k32.GetVolumeInformationW(
            root, vol_buf, 261, ctypes.byref(serial),
            ctypes.byref(max_comp), ctypes.byref(flags), fs_buf, 261)
        denom["volumes_scanned"] += 1
        rec = {"root": root}
        if ok:
            rec["filesystem_name"] = fs_buf.value
            rec["volume_label"] = vol_buf.value
            rec["volume_serial"] = serial.value
            rec["max_component"] = max_comp.value
            rec["volume_flags"] = flags.value
            rec["method"] = "kernel32.GetVolumeInformationW via ctypes"
        else:
            err = ctypes.GetLastError()
            denom["api_failures"] += 1
            rec["status"] = "GetVolumeInformationW-failed"
            rec["winerror"] = err
        dtype = k32.GetDriveTypeW(root)
        name, note = DRIVE_TYPES.get(dtype, ("other", "code %d" % dtype))
        rec["drive_type"] = {
            "code": dtype,
            "class": name,
            "note": note,
            "method": "kernel32.GetDriveTypeW via ctypes",
        }
        volumes.append(rec)
    return volumes, denom


# -------------------------------------------------------------- registry ----

def collect_longpaths_registry():
    if not IS_WINDOWS:
        return {"status": NOT_OBTAINABLE,
                "key": "HKLM\\SYSTEM\\CurrentControlSet\\Control\\FileSystem",
                "value_name": "LongPathsEnabled"}
    import winreg
    key_path = r"SYSTEM\CurrentControlSet\Control\FileSystem"
    rec = {"hive": "HKLM", "key": "HKLM\\SYSTEM\\CurrentControlSet\\Control\\FileSystem",
           "value_name": "LongPathsEnabled"}
    try:
        hkey = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path,
                              0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY)
    except OSError as exc:
        rec["status"] = "key-open-failed"
        rec["winerror"] = getattr(exc, "winerror", None)
        rec["detail"] = str(exc)
        return rec
    try:
        try:
            value, typereg = winreg.QueryValueEx(hkey, "LongPathsEnabled")
        except FileNotFoundError:
            # the value genuinely does not exist -- different fact from value=0
            rec["status"] = "absent"
            rec["value"] = None
            rec["interpretation"] = ("LongPathsEnabled value is ABSENT, which "
                                     "is not the same as value 0 present")
            return rec
        type_names = {1: "REG_SZ", 4: "REG_DWORD"}
        rec["status"] = "present"
        rec["value"] = value
        rec["value_type"] = type_names.get(typereg, "REG_%d" % typereg)
    except OSError as exc:
        rec["status"] = "query-failed"
        rec["winerror"] = getattr(exc, "winerror", None)
        rec["detail"] = str(exc)
    finally:
        winreg.CloseKey(hkey)
    return rec


# ------------------------------------------------------------------ 8.3 ----

GLOBAL_83_STATES = {
    0: "enabled-on-all-volumes",
    1: "disabled-on-all-volumes",
    2: "per-volume",
    3: "no-local-drives",
}
VOLUME_83_FLAGS = {0: "enabled", 1: "disabled"}


def _state_numbers(text):
    """Extract `: <N> (` state numbers from localized fsutil output.

    The numeric state is the language-independent fact; the parenthetical
    description changes with the console locale, so we parse the number.
    """
    return [int(m) for m in re.findall(r"[:：]\s*(\d+)\s*[(（]", text)]


def collect_83_state(volumes, runner):
    per_volume = []
    denom = {"commands_run_for_83": 0, "ok": 0,
             "needs_elevation": 0, "failed": 0}
    if not IS_WINDOWS:
        denom["status"] = NOT_OBTAINABLE
        return per_volume, denom
    # Global behavior query first (registry-backed, readable unelevated here)
    grec = runner.run(["fsutil", "behavior", "query", "Disable8dot3"])
    denom["commands_run_for_83"] += 1
    global_outcome = _interpret_83(grec)
    global_state = {
        "status": global_outcome["status"],
        "argv": grec["argv"],
        "rc": grec.get("rc"),
        "decoded_text": (grec.get("stdout") or grec.get("stderr") or ""),
        "numbers": _state_numbers(grec.get("stdout") or ""),
    }
    if global_state["numbers"]:
        code = global_state["numbers"][0]
        global_state["global_registry_state"] = GLOBAL_83_STATES.get(
            code, "unknown-code-%d" % code)
    for vol in volumes:
        root = vol["root"]
        vrec = {"volume": root,
                "global_disable8dot3": global_state.get(
                    "global_registry_state", global_state["status"])}
        if global_state["status"] != "ok":
            vrec.update(global_outcome)
            vrec["note"] = ("per-volume query not separately run because the "
                            "global query already failed; status inherited, "
                            "not guessed")
            if global_state["status"] == "needs-elevation":
                denom["needs_elevation"] += 1
            else:
                denom["failed"] += 1
            per_volume.append(vrec)
            continue
        rec = runner.run(["fsutil", "8dot3name", "query", root])
        denom["commands_run_for_83"] += 1
        state = _interpret_83(rec)
        vrec["command"] = rec["argv"]
        vrec["rc"] = rec.get("rc")
        decoded = rec.get("stdout") or rec.get("stderr") or ""
        vrec["decoded_text"] = decoded
        vrec["decoded_as"] = rec.get("decoded_as", {}).get("stdout")
        vrec["ascii_safe_excerpt"] = ascii_safe_excerpt(decoded[:400])
        numbers = _state_numbers(decoded)
        vrec["state_numbers"] = numbers
        vrec["status"] = state["status"]
        if state["status"] == "ok":
            if numbers:
                vrec["short_name_generation"] = VOLUME_83_FLAGS.get(
                    numbers[0], "unknown-code-%d" % numbers[0])
            else:
                vrec["short_name_generation"] = (
                    "rc=0 but no state number parsed -- contradiction")
            # a localized "Error:" preamble can coexist with rc=0; keep it
            # visible instead of silent
            vrec["preamble_error_line_present"] = bool(
                re.match(r"^(?:error|错误)", decoded.strip(), re.IGNORECASE))
            denom["ok"] += 1
        elif state["status"] == "needs-elevation":
            denom["needs_elevation"] += 1
        else:
            denom["failed"] += 1
        per_volume.append(vrec)
    return per_volume, denom


def _interpret_83(rec):
    if rec["status"] == "ok":
        return {"status": "ok",
                "detail": ascii_safe_excerpt(
                    (rec.get("stdout") or rec.get("stderr") or "")[:300])}
    if rec["status"] == "needs-elevation":
        return {"status": "needs-elevation",
                "detail": ascii_safe_excerpt(
                    (rec.get("stderr") or rec.get("stdout") or "")[:200])}
    return {"status": rec["status"],
            "detail": ascii_safe_excerpt(
                (rec.get("stderr") or rec.get("stdout") or "")[:200])}


# -------------------------------------------------------------- runtimes ----

def pathext_candidates(name):
    exts = os.environ.get(
        "PATHEXT", ".COM;.EXE;.BAT;.CMD;.VBS;.VBE;.JS;.JSE;.WSF;.WSH;.MSC")
    names = [name]
    for e in exts.split(";"):
        if e:
            names.append(name + e.lower())
            names.append(name + e.upper())
    return names


def find_all_on_path(name):
    """Every PATH hit for `name`, in PATH order, resolved to absolute paths."""
    hits = []
    seen = set()
    path_dirs = [d for d in os.environ.get("PATH", "").split(os.pathsep) if d]
    for d in path_dirs:
        try:
            if not os.path.isdir(d):
                continue
            entries = set(os.listdir(d))
        except OSError:
            continue
        for cand in pathext_candidates(name):
            if cand.lower() in {e.lower() for e in entries}:
                # recover exact casing
                exact = next(e for e in entries if e.lower() == cand.lower())
                full = os.path.realpath(os.path.join(d, exact))
                if full not in seen and os.path.isfile(full):
                    seen.add(full)
                    hits.append(full)
                break  # one hit per directory at most
    return hits


def scan_manifest_token(exe_path):
    """Byte-scan an executable for the manifest token. NOT a PE manifest parse."""
    rec = {
        "path": exe_path,
        "method": ("byte-scan of raw executable bytes for b\""
                   + "longPathAware" + "\"; NOT a PE manifest parse"),
        "found": False,
        "hits": [],
    }
    try:
        size = os.path.getsize(exe_path)
    except OSError as exc:
        rec.update(status="stat-failed", detail=str(exc), bytes_scanned=0)
        return rec
    total = 0
    overlap = len(MANIFEST_TOKEN) - 1
    tail = b""
    tail_start = 0
    try:
        with open(exe_path, "rb") as fh:
            while True:
                chunk = fh.read(1 << 20)
                if not chunk:
                    break
                buf = tail + chunk
                base = tail_start
                start = 0
                while True:
                    i = buf.find(MANIFEST_TOKEN, start)
                    if i < 0:
                        break
                    abs_off = base + i
                    lo = max(0, abs_off - EXCERPT_PAD)
                    # need context after too; read forward generously
                    window = buf[i + len(MANIFEST_TOKEN):
                                i + len(MANIFEST_TOKEN) + EXCERPT_PAD]
                    if len(window) < EXCERPT_PAD:
                        pos = fh.tell()
                        extra = fh.read(EXCERPT_PAD - len(window))
                        fh.seek(pos)
                        window += extra
                    pre = read_back(exe_path, lo, abs_off - lo)
                    rec["hits"].append({
                        "offset": abs_off,
                        "excerpt_ascii_safe": ascii_safe_excerpt(pre)
                        + "[" + ascii_safe_excerpt(
                            buf[i:i + len(MANIFEST_TOKEN)]) + "]"
                        + ascii_safe_excerpt(window),
                    })
                    rec["found"] = True
                    start = i + len(MANIFEST_TOKEN)
                total += len(chunk)
                tail = buf[len(buf) - overlap:] if overlap else b""
                tail_start = base + len(buf) - len(tail)
    except OSError as exc:
        rec.update(status="read-failed", detail=str(exc), bytes_scanned=total)
        return rec
    rec["status"] = "scanned"
    rec["bytes_scanned"] = total
    rec["file_size"] = size
    rec["hit_count"] = len(rec["hits"])
    return rec


def read_back(path, offset, length):
    if length <= 0:
        return b""
    try:
        with open(path, "rb") as fh:
            fh.seek(offset)
            return fh.read(length)
    except OSError:
        return b"?" * length


def collect_runtimes(runner):
    per_name = {}
    distinct = {}   # resolved path -> record (scanned once per real binary)
    for name in RUNTIME_NAMES:
        hits = find_all_on_path(name)
        entry = {
            "candidates_found": len(hits),
            "resolved_paths": hits,
            "shim_note": ("files with .cmd/.bat extension are batch wrappers; "
                          "a byte-scan of them cannot carry a PE manifest "
                          "token -- this is recorded per file, not assumed"),
        }
        details = []
        for path in hits:
            if path not in distinct:
                ext = os.path.splitext(path)[1].lower()
                kind = ("pe-executable" if ext == ".exe"
                        else "batch-shim" if ext in (".cmd", ".bat", ".vbs")
                        else "other")
                dscan = scan_manifest_token(path)
                dscan["kind_assumed"] = kind
                distinct[path] = dscan
            else:
                dscan = distinct[path]
            details.append({
                "resolved_path": path,
                "manifest_scan_status": dscan["status"],
                "manifest_token_found": dscan["found"],
                "kind": dscan.get("kind_assumed"),
            })
        # version probe via the FIRST PATH hit only (what a shell would run)
        version_rec = {"status": "no-candidate"}
        if hits:
            argv_tail, stream = VERSION_CMDS[name]
            rec = runner.run([hits[0]] + argv_tail)
            version_rec = {
                "argv": rec["argv"],
                "rc": rec.get("rc"),
                "status": rec["status"],
                "stream_used": stream,
            }
            if rec["status"] == "ok":
                parts = [p for p in (rec.get("stdout") or "",
                                     rec.get("stderr") or "") if p.strip()]
                if stream == "stdout":
                    raw = parts[0] if parts else ""
                else:  # combined: prefer whichever stream carried text
                    raw = parts[0] if parts else ""
                lines = [ln for ln in raw.splitlines() if ln.strip()]
                first = lines[0] if lines else ""
                version_rec["version_string"] = first
                version_rec["note"] = ("rc=0 with output; output used only "
                                       "after rc check")
            elif rec["status"] == "contradiction-rc0-no-output":
                version_rec["version_string"] = None
                version_rec["note"] = ("CONTRADICTION: rc=0 but neither "
                                       "stdout nor stderr produced output; "
                                       "no version claimed")
            else:
                version_rec["version_string"] = None
        entry["version_probe"] = version_rec
        entry["per_candidate"] = details
        per_name[name] = entry
    denom = {
        "runtime_names_searched": len(RUNTIME_NAMES),
        "runtimes_found": sum(1 for e in per_name.values()
                              if e["candidates_found"] > 0),
        "candidates_total": sum(e["candidates_found"]
                                for e in per_name.values()),
        "distinct_executables_scanned": len(distinct),
        "executables_scanned": len(distinct),
        "bytes_scanned": sum(d.get("bytes_scanned", 0)
                             for d in distinct.values()),
        "manifest_scan_disclaimer": ("byte-scan for the token string, not a "
                                     "PE manifest parse; batch shims carry no "
                                     "manifest"),
    }
    return per_name, distinct, denom


# --------------------------------------------------------------- unicode ----

def collect_unicode():
    probes = []
    # characters whose normalisation/existence behaviour changed across
    # Unicode data versions; used when no runtime exposes a version number
    probe_defs = [
        ("\u1c90", "GEORGIAN MTAVRULI CAPITAL LETTER AN",
         "code point exists only from Unicode 11.0 (Mtavruli capitals); on "
         "older unicodedata the name lookup raises ValueError; NFC of it is "
         "stable (no decomposition) where present"),
        ("\u32ff", "SQUARE ERA NAME REIWA",
         "the code point itself exists only from Unicode 13.0"),
        ("\u10d0", "GEORGIAN AN",
         "control character, stable across versions"),
    ]
    for ch, name, why in probe_defs:
        try:
            nfc = unicodedata.normalize("NFC", ch)
            decomps = unicodedata.decomposition(ch)
            cat = unicodedata.category(ch)
            try:
                nm = unicodedata.name(ch)
            except ValueError:
                nm = "NO-NAME (absent from this Unicode data version)"
            probes.append({
                "codepoint": "U+%04X" % ord(ch),
                "declared_name": name,
                "actual_name": nm,
                "category": cat,
                "nfc_result": [hex(ord(c)) for c in nfc],
                "decomposition": decomps or None,
                "version_sensitivity": why,
            })
        except (ValueError, TypeError) as exc:
            probes.append({
                "codepoint": "U+%04X" % ord(ch),
                "declared_name": name,
                "status": "probe-failed",
                "detail": str(exc),
            })
    out = {
        "python_unicodedata_version": unicodedata.unidata_version,
        "version_source": "unicodedata.unidata_version (authoritative "
                          "for this interpreter)",
        "probe_status": "probed",
        "probes": probes,
        "probes_run": len(probes),
        "note": ("other runtimes (node/go/java/dotnet/rustc) do not expose a "
                 "Unicode data version through a version command; for them "
                 "the version is not-obtainable-here without an in-language "
                 "probe program"),
    }
    for other in ("node", "go", "java", "dotnet", "rustc"):
        out["other_runtime_" + other + "_unicode_version"] = NOT_OBTAINABLE
    return out


# ------------------------------------------------------------------ main ----

def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Collect machine environment facts as one JSON object.")
    ap.add_argument("output", help="path to write the JSON artifact")
    args = ap.parse_args(argv)

    runner = CommandRunner()
    os_facts = collect_os(runner)
    volumes, vol_denom = collect_volumes(runner)
    longpaths = collect_longpaths_registry()
    short83, d83 = collect_83_state(volumes, runner)
    runtimes, distinct, rt_denom = collect_runtimes(runner)
    unicode_facts = collect_unicode()

    doc = {
        "schema": "envfacts/1",
        "collected_on_host": platform.node(),
        "os": os_facts,
        "volumes": volumes,
        "volumes_denominator": vol_denom,
        "registry_longpaths": longpaths,
        "short_name_83": {
            "per_volume": short83,
            "denominator": d83,
            "policy": ("recorded as needs-elevation when fsutil refuses; "
                       "never guessed"),
        },
        "runtimes": runtimes,
        "runtimes_denominator": rt_denom,
        "manifest_scan": {
            "distinct_executables": [distinct[p] for p in sorted(distinct)],
            "disclaimer": ("this is a byte scan for the ASCII token "
                           "longPathAware across raw file bytes; it is NOT a "
                           "PE manifest parse and cannot prove the loader "
                           "honours the setting"),
            "token": "longPathAware",
            "excerpt_padding_bytes": EXCERPT_PAD,
        },
        "unicode_data": unicode_facts,
        "commands": {
            "commands_run": runner.commands_run,
            "command_failures": runner.command_failures,
            "contradictions_rc0_no_output": runner.contradictions,
            "form": "argv list only, shell=False, rc checked before use",
        },
        "not_obtainable_legend": {
            NOT_OBTAINABLE: ("this host/toolchain could not produce the fact; "
                             "no substitute value was invented"),
        },
    }

    text = json.dumps(doc, indent=2, ensure_ascii=False, sort_keys=True)
    # stdout first, then the artifact; same bytes in both
    try:
        sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    except (AttributeError, OSError):
        pass
    sys.stdout.write(text + "\n")
    with open(args.output, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
