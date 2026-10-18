# SENDGUARD S00 — outside referee: Windows file-name behaviour, measured

Independent of the spec work. No project code was read or run (nothing from
`impl/`, `results/`, `ci/`, `docs/`). Every observation was produced by the
machine's own tools and its own directory enumeration. Companion machine-readable
file: `referee-windows.json` (168 records).

## Environment (each value captured with its own exit code)

- OS: Microsoft Windows 10 Pro, build **10.0.19041.208**, **AMD64**, 64-bit.
- Scratch volume `D:` filesystem: **NTFS**.
- `LongPathsEnabled` (HKLM...\FileSystem): **0** (long paths DISABLED).
- Locale / UI culture: **zh-CN**. Active console code page (`chcp`): **936**. NLS ACP = **936**, OEMCP = **936**, MACCP = 10008. Console output encoding = **gb2312**.
- PowerShell **5.1.19041.1**; `git` **2.53.0.windows.2**; `tar`: **GNU tar 1.35** (Git Bash `/usr/bin/tar`) AND **bsdtar 3.3.2 / libarchive 3.3.2** (`C:\Windows\System32\tar.exe`) — two different tar engines; Python 3.14.7 used only to build this JSON and to parse archive header bytes.

Method note: every CREATE attempt for reserved / illegal / trailing names ran inside
a `Start-Job` child process with an externally enforced **8 s** timeout, so a
device-open that would block can never hang this controller. Listing was done with
`Get-ChildItem`, `cmd dir`, and `System.IO.Directory` / Python `os` (NTFS wide
enumeration). On-disk names are reported as **UTF-16LE hex**, never as typed.
Non-ASCII names were built from explicit code points.

## Item 1 — reserved device names

Names: `CON`, `CON.txt`, `NUL.tar.gz`, `COM1.log`, `PRN`, `AUX.log`, `LPT9`.
Tools that try to create them in a normal directory: `New-Item -ItemType File`,
`Copy-Item`, `cmd copy`, `cmd echo>` redirection.

**No tool creates them as a normal file.** After all attempts the directory held
only the source file — `Get-ChildItem` and `cmd dir` listed **nothing** of the
reserved names. Details:

- `New-Item`/`Copy-Item` (.NET/PowerShell): reject with a real error. PowerShell
  recognises the device names and throws (`NotSupportedException`, or
  `CopyError` "…because the target represents a reserved device name"); `PRN`/`LPT9`
  fail as `NewItemIOError`.
- `cmd copy src CON` reports **"copied 1 file"** and exits **0** — but it wrote to
  the **console device**, not a file. `NUL.tar.gz`/`COM1.log`/`AUX.log`/`CON.txt`
  likewise exit 0 with no file. `PRN`/`LPT9` copy exit **1** ("0 files") because no
  such writable device is present.
- `cmd echo x> CON` etc. exit 0 (redirect to the device), no file created.

**Open/hang:** none was attempted. Because creation never produced a real file,
there was nothing to open; per the safety rule no reserved-name handle was ever
opened or read. Outcome `hang`: **0 occurrences.**

## Item 2 — illegal characters

Names: `a<b.txt`, `a|b.txt`, `a?b.txt`, `a*b.txt`, `a"b.txt`, `a:b.txt`.

- **PowerShell (`New-Item -Path`, `Copy-Item -LiteralPath`) rejects every one** with
  "Illegal characters in path" (`:` specifically → "The given path is not in the
  correct format"), and produces **no** filesystem side effect.
- **cmd does NOT cleanly reject; it fabricates stray files** from its own quote /
  colon / wildcard parsing (attributed by per-attempt directory diff, on-disk names
  confirmed as UTF-16LE hex):
  - `a"b.txt` via `echo>` → creates **`ab.txt`** (cmd silently drops the embedded quote), exit 0.
  - `a:b.txt` via `echo>` → creates **`a`** (cmd truncates the name at the colon), exit 0.
  - `a?b.txt` via `copy` → creates **`asb.txt`** (the `?` is treated as a wildcard that matched the source name), exit 0.
  - `a*b.txt` via `copy` → creates **`asrctext.txtb.txt`** (the `*` glob-expanded against the source file name), exit 0.
  - `<`, `|`, `?`, `*` via `echo>` → exit 1, no file.
- Stray files (`a`, `ab.txt`, `asb.txt`, `asrctext.txtb.txt`) were **not deleted**
  (safety rule; scratch left in place). No `cleanup_failed` because no deletion was
  attempted.

## Item 3 — trailing dot / space, and Unicode near-misses

Isolated cell per (tool, name). On-disk name as UTF-16LE hex:

- `trail.` → lands as **`trail`** (ASCII trailing **dot stripped**) by all four tools.
- `trailsp ` → lands as **`trailsp`** (ASCII trailing **space stripped**) by all four tools.
- `trailNBSP` + **U+00A0**: **DIVERGES by tool.**
  - PowerShell `New-Item` and `Copy-Item` (i.e. .NET path normalisation) → land as **`trailNBSP`** — the trailing **NBSP is STRIPPED** (`a0 00` absent).
  - `cmd` (`echo>` and `copy`) → land as **`trailNBSP` + U+00A0** — **NBSP PRESERVED** (`… 50 00 a0 00`).
- `trailFull` + **U+3000** (ideographic space): **preserved by all four** (`… 6c 00 00 30`).

So the common rule "Windows trims trailing dots and spaces" is incomplete for this
machine: .NET additionally trims **U+00A0**, the Win32/cmd parser does not, and
**neither** trims **U+3000**. Two tools asked to create the *same* logical name
produce *two different files* on the same NTFS directory.

## Item 4 — length limits (measured, not assumed)

Normal (non-`\\?\`) paths, base absolute length buckets; longest single component
found by binary search:

| base_len | max component (each of New-Item / Copy-Item / cmd) | total at max | total at first fail |
|---|---|---|---|
| 78  | 180 | 259 | **260** |
| 120 | 138 | 259 | **260** |
| 200 | 58  | 259 | **260** |

- All three tools succeed at total **259** and **fail at total 260** — the MAX_PATH
  260 boundary is **confirmed** (usable 259 + implicit terminator). The base
  targets **13 and 60 were unreachable**: the shortest permitted base is the scratch
  root (~53 chars) because drive roots and locations outside the scratch are
  forbidden; measured bases were 78/120/200.
- The **per-component 255 limit is never observable on normal paths here** — the 260
  total cap binds first (max component = 259 − base_len, always well under 255).
- Failure message is a generic **"path not found"** (`.NET`) / cmd exit 1, *not* an
  explicit "too long" diagnostic.

Extended `\\?\` paths (reach the real ceilings):

- **Per-component**: 255 succeeds, **256 fails with Win32 code 123 =
  ERROR_INVALID_NAME** (both Win32 `CreateFileW` and `.NET File.Create`). So 255
  UTF-16 units per component is **confirmed** and it is a hard per-segment cap.
- **Total**: Win32 `CreateFileW` last success ≈ **32627**, fails ≈ **32874**; .NET
  `File.Create` ≈ **32628 / 32875** → the ~**32767** long-path total.
- **cmd with `\\?\`**: last success **8035**, fails **8291** → cmd's **own command-line
  buffer (~8191)** caps it far below 32767 even when `\\?\` is used. cmd cannot reach
  the long-path ceiling that the OS and .NET can.

## Item 5 — zip / tar round-trip

Source (created with explicit code points; confirmed on disk): **`报告.txt`**
(CJK), **`café.txt`** (U+00E9), `plain.txt`.

Producers and what they stored (name bytes parsed from the header, general-purpose
bit 11 = UTF-8 flag):

- **Compress-Archive** (PowerShell / .NET `System.IO.Compression`): stores non-ASCII
  names as **UTF-8 bytes** and **SETS bit 11** (`flag=0800`) — e.g. `报告.txt` as
  `e6 8a a5 e5 91 8a 2e …`; `café.txt` as `… 63 c3 a9 …`. ASCII `plain.txt` has bit 11
  clear (correct). So on this build Compress-Archive **does** honour the UTF-8 flag.
- **bsdtar → .zip** (`tar.exe -a -c -f`): stores non-ASCII names as **GBK / CP936
  bytes** and **does NOT set bit 11** (`flag=0008` — that is bit 3, a data descriptor,
  not UTF-8): `café.txt` as `… 66 a8 a6 …` (a8 a6 = é in CP936), `报告.txt` as
  `b1 a8 b8 e6` (CP936). A reader that assumes cp437/UTF-8 for bit-11-clear names
  gets mojibake on any non-GBK machine.
- **GNU tar → .tar** and **bsdtar → .tar**: both stored the raw name bytes as
  **UTF-8** (`c3 a9`, `e6 8a a5 …`). bsdtar additionally emitted `./PaxHeader/…` pax
  extended headers.

Extractors and the name that actually landed (UTF-16LE hex), by (archive → extractor):

| archive | Expand-Archive | bsdtar | GNU tar |
|---|---|---|---|
| zip_ca.zip (Compress-Archive, bit11 set) | correct | correct | **rc=2 — cannot read zip** |
| z_bsd.zip (bsdtar, bit11 clear, GBK) | correct* | correct | n/a |
| t_gnu.tar (UTF-8, no pax) | n/a | **MANGLED** | correct |
| t_bsd.tar (UTF-8 + pax path) | n/a | correct | correct |

\* "correct" here is self-consistent *because this machine's code page is GBK*:
Expand-Archive decodes bit-11-clear names using CP936, which matches what bsdtar
wrote. On a machine with a different code page that same archive would mojibake.

**The headline failure:** `t_gnu.tar` (member names are UTF-8 bytes, no pax `path`
record) extracted by **bsdtar** produced `caf茅.txt` (hex `… 66 05 83 …`, i.e. the
UTF-8 bytes `c3 a9` re-read as GBK → 茅) and `鎶ュ憡.txt` for `报告.txt`. GNU tar
extracting the same archive was correct. bsdtar falls back to the **system code page**
for tar names unless a pax header marks them, so a UTF-8 tar written by GNU tar is
corrupted by bsdtar on a GBK host.

## Item 6 — case-only pairs

- `New-Item Report.txt` then `New-Item report.txt`: second call **fails — "file
  already exists"**. Only `Report.txt` remains; the original casing is **preserved**,
  not overwritten. The pair cannot coexist.
- After creating `Report.txt`, `File.Exists` is true for `report.txt`,
  `Report.txt`, and `REPORT.txt` (existence is case-insensitive).
- `cmd copy → notes.TXT` then `cmd copy → notes.txt`: both exit 0, only `notes.TXT`
  present (again first casing preserved, second treated as the same file).
- `fsutil file queryCaseSensitiveInfo <dir>`: reports per-directory case sensitivity
  **disabled** — the NTFS default (case-preserving, case-insensitive).

## Contradictions of the "commonly documented numbers"

- **260 (MAX_PATH):** *confirmed* for normal paths on this config (fail exactly at
  total 260), but the effective **per-component** result differs — with LongPathsEnabled=0
  the 260 total always binds before the 255 component cap, so 255 is unobservable via
  normal paths.
- **255 (per component):** *confirmed*, but only reachable via `\\?\`; hard-fails at
  256 with Win32 123. cmd cannot create names anywhere near it.
- **bit 11 (UTF-8 flag):** the assumption that "zips carry names as UTF-8 with bit 11"
  is **wrong for bsdtar** — it writes code-page (GBK) bytes with bit 11 clear, while
  Compress-Archive writes UTF-8 with bit 11 set. Two "standard" zip producers on the
  same machine emit archives that are not equally portable.
- **Trailing whitespace trimming:** the usual "trims trailing . and space" is
  contradicted — .NET additionally trims **U+00A0** while cmd preserves it; neither
  trims **U+3000**. Same requested name → two different files.
- **Illegal characters "are rejected":** true for PowerShell/.NET, **false for cmd**,
  which instead silently creates mangled stray files (`a"b.txt`→`ab.txt`,
  `a:b.txt`→`a`, `a*b.txt`→`asrctext.txtb.txt`).

## What could not be done, and why

- Base-length buckets **13 and 60** for item 4 were **not reachable**: the shortest
  legal base is the scratch root (~53 chars); drive roots and paths outside
  `D:\work\referee-scratch\…` are forbidden by the task. Measured bases were
  78/120/200 instead.
- **GNU tar could not extract a `.zip`** (returns "does not look like a tar archive",
  rc=2) — recorded as an unavailable extractor for that format, not guessed around.
- The **`\\?\` extended total ceiling** was located by growing 255-char segments, so it
  is reported to ~256-char granularity (win32 ~32627→32874, cmd 8035→8291), not a
  single-char boundary; cmd's ~8191 buffer is the binding limit for cmd.
- **No reserved-name file was ever opened**, so no `hang` outcome could occur (0).
  **No cleanup** was performed on any item-1/2/3 artifact, so no `cleanup_failed`
  arose; the scratch directory is left intact, strays included.
