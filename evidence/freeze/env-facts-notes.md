# env-facts notes — S00 (Windows local run)

Artifact: `evidence/freeze/env-facts-windows-local.json`
Collector: `harness/envfacts.py` (stdlib-only, re-runnable: `python harness/envfacts.py <out.json>`)
Run host: Windows 10 build 19041, AMD64, collected with Python 3.14.7 (`C:\Python314\python.exe`).

## The 5 facts in the output that most affect whether two ports can be expected to agree

1. **Long paths are NOT system-enabled, but some binaries opt in individually.**
   Registry `LongPathsEnabled` is *present* with value `0` (REG_DWORD) — that is a
   different fact from the value being absent, and the JSON records which one it is.
   Both volumes report `max_component = 255`. Yet the byte scan finds the
   `longPathAware` manifest token inside `python.exe` and both `dotnet.exe`
   binaries. So on this same machine the long-path behaviour of a report writer
   depends on *which binary* runs it, not only on the registry. Any equality
   claim between ports must fix (registry state, per-binary manifest state)
   together. Note the disclaimer that is carried in the JSON: the token check is
   a raw byte scan, **not** a PE manifest parse — it proves the string is in the
   file, not that the loader honours it.

2. **The process sees code page 936 and locale Chinese (Simplified)_China, with UTF-8 mode off.**
   `GetConsoleCP`/`GetConsoleOutputCP` both return 936; `locale.getpreferredencoding`
   is `cp936`. This already bit the harness during development: `fsutil` emits
   localized GBK text, and a naive UTF-8 decode produced replacement characters
   from a *successful* (rc=0) command. Ports that capture tool output must agree
   on the decoding path or they will not be byte-identical. The JSON records the
   encoding each command output was decoded as.

3. **8.3 short-name generation differs between the two volumes on the same box.**
   `C:\` → enabled, `D:\` → disabled (parsed from the language-independent state
   numbers in `fsutil 8dot3name query`, global registry state is `per-volume`).
   Short-name aliases therefore exist on one project volume and not the other; a
   path round-trip or case/length assertion can pass on D and fail on C. No
   elevation was needed to read this here.

4. **More than one real binary answers the same name on PATH.**
   7 names were searched, 6 found, **9 candidate paths in total, 9 distinct
   resolved executables**. Two names are multi-valued: `java` resolves to 3
   different binaries (Adoptium JDK 17, Adoptium JDK 21, an old Oracle JRE 1.8
   in `Program Files (x86)`) and `dotnet` to 2 (`Program Files` vs
   `Program Files (x86)`). The version probe runs only the *first* PATH hit —
   what a given shell executes is pure PATH-order accident. Byte-identical
   reports require pinning the **resolved path**, which is why the collector
   records every hit per name, not just the first.

5. **Unicode data version: known for Python, unknown for the others.**
   `unicodedata.unidata_version = 16.0.0` for the running interpreter. The probe
   set (`U+1C90`, exists only from Unicode 11.0; `U+32FF SQUARE ERA NAME REIWA`,
   exists only from 13.0; `U+10D0` control) is recorded as `probed` and is
   consistent with 16.0.0. Node/Go/Java/.NET/Rust do not expose a Unicode data
   version through any version command, so their versions are
   `not-obtainable-here` from this collector (see below) — a port pair could
   silently differ here (e.g. NFC/NFD sets between ICU versions in Node vs
   Rust's `unicode-normalization`).

## What the script could not obtain (recorded, not faked)

- **`tsc`**: 0 candidates on PATH — recorded as `candidates_found: 0`,
  `version_probe.status: no-candidate`. not-obtainable-here.
- **Unicode data version for node/go/java/dotnet/rustc**: no version command
  surfaces it; requires an in-language probe program per runtime. Recorded as
  `not-obtainable-here` per key in `unicode_data`.
- **rustc's true version string**: `~/.cargo/bin/rustc.exe` resolves (realpath)
  to `rustup.exe` (rustup shim), so running it yields `rustup 1.29.0
  (28d1352db 2026-03-05)`, which does **not** pin the compiler that would be
  selected for a given toolchain file. The JSON keeps both the resolved path and
  this string; a `rustc -VV`-grade fact is not-obtainable-here through the shim.
- **Java version for the 2 non-first candidates**: by design only the first PATH
  hit is executed; the other two paths are recorded but never run. Their version
  strings are not-obtainable-here *in this artifact*.
- **Physical bus (SATA vs USB) of "fixed" volumes**: `GetDriveTypeW` classifies
  drive *type* (here both volumes: `fixed`), not transport. Distinguishing a
  USB-attached fixed disk needs storage enums beyond stdlib scope; recorded as
  the drive-type class with an explicit note that it is not bus proof.
- **`java -version`, and the two older JDKs' behaviour**: the first candidate's
  version string was captured from stderr (rc=0); that is all the artifact
  claims.

## Discipline notes (visible in the JSON itself)

- Every command ran in argv-list form with `shell=False`; `rc` is checked before
  any output is used. This run: `commands_run: 9`, `command_failures: 0`,
  `contradictions_rc0_no_output: 0`.
- fsutil emits a localized "错误: 系统找不到指定的路径" preamble *even when the
  query succeeds with rc=0* (it then falls back to the GUID path and answers).
  The per-volume records keep `preamble_error_line_present: true` so a later
  reader sees the anomaly instead of a cleaned-up lie.
- Denominators: `volumes_scanned: 2`, `runtime_names_searched: 7`,
  `runtimes_found: 6`, `candidates_total: 9`, `distinct_executables_scanned: 9`,
  `bytes_scanned: 118,969,616`, `probes_run: 3`.
- Output file: valid UTF-8, no BOM, LF endings, byte-identical to stdout
  (verified by MD5 comparison in the run session).
