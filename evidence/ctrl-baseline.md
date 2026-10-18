# SENDGUARD Control-Cell Baseline (measured on this machine)

- date: 2026-10-10T12:53:47.806Z
- os: win32 / node v22.23.2
- run dir: D:\local-dir\evidence\000\_ctrlrun
- baseline is the ONLY allowed source of control expectations; hand-written expectations forbidden

| cell | create_result | error_stage | error_code | bytes_written | bytes_on_disk | read_result | roundtrip_ok | sha256_on_disk |
|---|---|---|---|---|---|---|---|---|
| T-CTRL-NAMETOOLONG | err_at_syscall | syscall | ENOENT | null | null | null | null | null |
| T-CTRL-ASCII | ok | null | null | 28 | 28 | ok | true | c9fe45b2fee8ea846f0cf4f2cacc2a891e7b082e7719923502d12a9813e21994 |
| T-CTRL-ILLEGAL-CHAR | err_at_syscall | syscall | ENOENT | null | null | null | null | null |
| T-CTRL-PARSE | err_at_parse | parse | ERR_INVALID_ARG_VALUE | null | null | null | null | null |
| T-CTRL-CANON | (canonical) | - | - | - | - | - | true | node=c9fe45b2fee8ea846f0cf4f2cacc2a891e7b082e7719923502d12a9813e21994 python=c9fe45b2fee8ea846f0cf4f2cacc2a891e7b082e7719923502d12a9813e21994 |

## Interpretation

- **T-CTRL-NAMETOOLONG** (component 256 code units): create_result=err_at_syscall, error_stage=syscall — expectation per julying: fail on all 3 OS **after reaching FS** (err_at_syscall, not parse).
- **T-CTRL-ASCII** (report-2026.txt): create_result=ok — expectation: ok on all languages/OS.
- **T-CTRL-ILLEGAL-CHAR** (a<b.txt): create_result=err_at_syscall, error_code=ENOENT — expectation: Windows illegal (winerror=123) / POSIX creatable, paired with os_legality_verdict.
- **T-CTRL-PARSE** (embedded U+0000): create_result=err_at_parse, error_stage=parse — expectation: may reject before syscall, but all 6 langs MUST be err-at-parse; else that lang's harness is reworked.
- **T-CTRL-CANON**: node=c9fe45b2fee8ea846f0cf4f2cacc2a891e7b082e7719923502d12a9813e21994 python=c9fe45b2fee8ea846f0cf4f2cacc2a891e7b082e7719923502d12a9813e21994, agree=true — expectation: identical canonical bytes; else INSTRUMENT-RED.

