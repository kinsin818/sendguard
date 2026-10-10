# SENDGUARD S00 Predictions (isolated archive)

Prediction table is ISOLATED: it never enters the data flow, never gates any
judgment, and is NOT an expectation source. The ONLY expectation source for
control cells is `evidence/S00-ctrl-baseline.md`. Where we guessed wrong and
measurement said otherwise, that gap is whitepaper gold ("we predicted X, the
matrix shows Y").

Archived: 2026-10-10 (S00, pre-S01).

## Direction-of-travel guesses (coarse, non-gating)

| cell | coarse pre-guess | note |
|---|---|---|
| T01 CON.txt | Windows behavior device-dependent, NOT恒真 | N11: only CON/AUX/NUL/COM1 exist=True on this box |
| T02 NUL.tar.gz | same class as T01; extension does not save it | - |
| T03 a<b.txt | Win illegal / POSIX creatable | ctrl ILLEGAL-CHAR |
| T04 trail. | per-language stripping divergence | T-DOTSP family, mechanism_class=path_preprocessing_policy |
| T05 trailsp␣ | same family | - |
| T06 emoji | NFC/NFD shape depends on source encoding | - |
| T07 NFD | differs from T08 NFC on macOS | - |
| T08 NFC | differs from T07 | - |
| T09 NFC+NFD coexist | headline cell; language/FS dependent | - |
| T10 CON | reserved device, no extension | - |
| T11 COM1.log | reserved device with extension | - |
| T12 bidi U+202E | visual vs stored order divergence | - |
| T13 zero-width U+200B | likely stored fine, display confusion | - |
| T14 PRN/AUX.log/LPT9 | device table; may differ from T01 set | - |
| T15 control chars U+0000-1F | parse-stage rejection likely | ctrl PARSE family |
| T16 zip bit-11 roundtrip | zip toolchain dependent | - |
| T17 T-LEN-PATH | Windows 260 legacy vs LongPaths; LPE matters | longpath probe: Node auto-prefix |
| T18 T-LEN-COMP | max_component=255 on NTFS | measured 255 via GetVolumeInformationW |
| T19 full/half width + Hangul jamo | encoding width semantics | - |
| T20 --force.txt | looks like a flag, is a filename | - |

## Measured facts this round (S00, Windows, 2026-10-10)

- max_component = 255 (NTFS, GetVolumeInformationW)
- LongPathsEnabled = 0; 8dot3name registry state = 2 (per-volume default)
- longpath 2x2: LPE=0 -> plain 314-char path CREATED by Node (prefix-rewrite);
  LPE=1 -> plain created (manifest path). Node auto-prefix confirmed.
- Node reports ENOENT for a<b.txt (not WinError 123) - language self-report
  cannot fill os_legality_verdict; OS-direct question required.
- ctrl baseline: NAMETOOLONG=err_at_syscall(ENOENT), ASCII=ok,
  ILLEGAL-CHAR=err_at_syscall(ENOENT), PARSE=err_at_parse(ERR_INVALID_ARG_VALUE),
  CANON node==python sha256.
