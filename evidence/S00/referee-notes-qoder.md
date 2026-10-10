# Referee merge note — what the outside measurements change

Merged by: Qoder seat (single writer for `evidence/S00/`). 2026-10-11 01:5x +0800.
Source: the referee window's own scratch tree, 168 observation records, copied in unmodified.
The referee window deliberately did not write into this surface because it was being written in
parallel — that is the correct collision behaviour, and it is recorded here because it is also the
behaviour the project's own race rules demand.

## Two claims of mine that the measurements kill

1. **I said trailing NBSP survives because the Windows stripping set is ASCII-only.** Wrong as stated.
   Measured: `.NET`/PowerShell **do strip a trailing U+00A0**, while `cmd` **preserves it** — the same
   requested name lands as two different files in the same NTFS directory depending on which tool asked.
   U+3000 is stripped by neither. So the stripping set is **per-API, not per-OS**. That is a better
   finding than mine was, and it is the same shape as the reserved-name story: the question "who strips
   what" has no OS-level answer.
2. **I specified verification cells at base depth 13.** Not buildable under our own rule that an
   instrument may not create directories at a drive root. The shortest legal base measured here is ~78
   characters. Consequence: the per-component 255 limit stays unobservable on normal paths by an even
   wider margin than I calculated, and the base ladder becomes {78, 120, 200}.

## What the referee confirmed of my earlier reasoning

- Normal paths: success at total 259, failure at 260, reported as generic "path not found" (code 3) —
  matching the regime split in the second-round addendum.
- With `\?\`: 255 succeeds, **256 fails with code 123 (ERROR_INVALID_NAME)** — exactly the boundary-code
  difference predicted (3 on the plain face, 123 on the extended face).
- `cmd` is capped at ~8191 by its own command-line buffer even with `\?\`, so a shell-based expectation
  of the 32k long-path ceiling is wrong about the shell, not about the OS.

## New material, not predicted by anyone

- **`Compress-Archive` sets the UTF-8 flag (bit 11); `bsdtar` does not, and writes names in CP936.** Two
  archives produced on one machine have different portability. This is the owner's headline pain
  ("Mac 压缩包 Windows 乱码") reproduced with a named producer and no macOS required — and the honest
  version of it: the producer's choice, not the operating system, decides whether the name survives.
- **`bsdtar` on this host mangles UTF-8 member names from a GNU-made tar** (`报告.txt` → mojibake) while
  GNU tar reads the same archive correctly. Same file, same machine, different tool, different name.
- **`cmd` does not reject illegal characters, it fabricates different files**: `a"b.txt` → `ab.txt`,
  `a:b.txt` → `a`, and wildcard-looking names matched against the source so `copy` produced stray files
  named after the *source*. Silent renaming where an error was owed.
- **`cmd copy … CON` reports "copied 1 file" with exit 0 while writing to the console device.** A tool
  that says it stored a file and stored nothing.
- Case-only pairs cannot coexist here (per-directory case sensitivity disabled on the volume); the second
  creation errors "already exists" and the first casing is preserved.

## Contract deltas this forces (applied to `spec/cell-identity.md` by the seat)

1. `os_legality_verdict` must be accompanied by **`verdict_via`** — which API was asked
   (`win32` / `dotnet` / `cmd` / `posix`). There is no tool-independent answer to "is this name legal",
   and a cell that omits it is not comparable.
2. Zip cells must carry `packer` **and** `extractor` with versions in `sub_identity` (already required by
   the identity rule; the referee shows why it is not ceremony).
3. Base-depth ladder for `len` cells: `{78, 120, 200}` plus whatever a CI workspace happens to be, and the
   cell must record `base_len` rather than assume a canonical root length.

## Honest limits of this leg

- Zero `hang` outcomes, because no reserved-name file was ever created through a normal path — so this
  leg says nothing about the hang question; that stays with the ports and the console-state cells.
- Extended-prefix ceilings located only to ~256-character granularity, not single-character precision.
- Windows only. The macOS and Linux rows of the same referee table are still owed by CI.
