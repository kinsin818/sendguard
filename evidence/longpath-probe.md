# SENDGUARD longpath 2x2 sub-experiment (Node probe)

- date: 2026-10-10T12:55:09.790Z
- LongPathsEnabled (before): 0
- plain target: D:\local-dir\evidence\000\_longrun\0123456789abcdef0123456789abcdef\0123456789abcdef0123456789abcdef\0123456789abcdef0123456789abcdef\0123456789abcdef0123456789abcdef\0123456789abcdef0123456789abcdef\0123456789abcdef0123456789abcdef\0123456789abcdef0123456789abcdef\0123456789abcdef0123456789abcdef\report-2026.txt (len=314)
- extended target: \\?\D:\local-dir\evidence\000\_longrun\0123456789abcdef0123456789abcdef\0123456789abcdef0123456789abcdef\0123456789abcdef0123456789abcdef\0123456789abcdef0123456789abcdef\0123456789abcdef0123456789abcdef\0123456789abcdef0123456789abcdef\0123456789abcdef0123456789abcdef\0123456789abcdef0123456789abcdef\report-2026.txt (len=318)

## Cell A: LongPathsEnabled=0 x plain

- result: ok

## Cell B: LongPathsEnabled=0 x extended (\\?\)

- result: ok

## Mechanism classification (LPE=0)

- prefix_rewrite (lang auto-prefix under LPE=0)

_Switch-cell results (LPE=1) appended when the registry can be toggled; otherwise this machine's LPE is read-only in this session._
