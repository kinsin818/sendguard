# SENDGUARD

**SENDGUARD** is a reproducible, measurable experiment: the same 20 trap
filenames, implemented with the same cleaning engine in **6 programming
languages** on **3 operating systems**, with a full CI matrix, independent
audit instrumentation, and a per-language long-path / name-semantics report.
It ships with a double-click **sender-side file checker** (体检器) that tells
you, before you send an email or a zip: *will the recipient's OS even let this
file exist?*

> "Whether a filename can be stored depends on three unrelated things:
> the language you count it with, the directory level you put it in, and the
> OS of the person who receives it."
> "No single language's default length API is correct on both platforms."

## Why this exists

Freelancers and small teams lose real money on the silent failure class:
a file that is created fine on your machine, then vanishes, renames itself,
or becomes unreadable on the client's OS. The failure is *not* in the file.
It is in the **name semantics** — reserved device names (`CON.txt`,
`NUL.tar.gz`), trailing dots/spaces, NFC/NFD coexistence, bidi/zero-width
characters, and the 260-char legacy path wall. Most AI "cleaning" tools
never test this layer. SENDGUARD measures it, publishes the matrix, and
wraps the result into a checker anyone can double-click.

## Status

| Stage | State |
|---|---|
| S00 | **DONE** — repo scaffold, spec (schema/canonical/validate), audit instrumentation (Go + PowerShell cross-check), CI matrix (3 OS, frozen images), control-cell baseline, longpath 2x2 probe, env metadata, toolchain table, predictions archive |
| S01–S10 | planned (see docs/) |

This repository is open for review **before** the full measurement run:
spec and harness are public; corpus entries live as hex only, never as
real filesystem names (a forbidden-name sample is never materialized as a
real file).

## Layout

```
spec/        schema.json (cell schema) + canonical.md (closed status words) + validate.py
harness/     audit.go (independent Go enumerator) + audit.ps1 (PowerShell cross-check)
             ctrl-baseline.mjs + longpath-probe.mjs (S00 probes)
impl/        node python go java csharp rust  (the six measured implementations)
ci/          lint.py (runs-on whitelist / tracked-name legality / BOM check)
.github/     workflows/matrix.yml (windows-2025, macos-15, ubuntu-24.04, frozen)
evidence/    S00 outputs: toolchain.txt, env-windows.json, ctrl-baseline.md,
             longpath-probe.md, predictions.md, quota record, blind-map.json
results/     measurement output (populated from S02)
docs/        roles, stage plans, whitepaper drafts
backlog/     new trap candidates (the 20 frozen traps never expand here)
```

## CI

Three OS runs on **standard frozen images only** (no `*-latest`, no larger
runners). Each matrix job probes the environment, builds the audit
instrument, validates its JSON, and runs the 3-piece lint with red/green
fixtures. A `crossread` job gates Node<->Python interop (the headline
mechanism_class testbed).

## License

**TBD — provisional statement.** The intended license is
AGPL-3.0 / MPL-2.0 (dual or layered, decided before S06). Until then this
statement in the README is the placeholder; the full license file is
replaced before any external release. Source is public; the *trap corpus*
(exact sample set) is published as hex and stays reproducible, never as
executable files.

## Contact / provenance

- Author: Sam Jin (kinsin818). Built with a multi-agent pipeline;
  every measurement artifact carries the exact toolchain path+version that
  produced it (see evidence/S00/toolchain.txt). Failures and corrections are
  recorded openly — see docs/journey.md (planned) which keeps a
  "failures & change-of-mind" section.
