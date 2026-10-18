# S02 defect report — frozen sample corruption (P0, freeze-blocking)

- date: 2026-10-10
- found by: W-PY (Python local), first run of `impl/python/sg_python.py`
- object: `spec/cases.yaml` (frozen_at 2026-10-10, T01–T20)
- severity: **P0 / freeze-blocking** — the frozen samples do not carry the intended bytes
- status: **RESOLVED in freeze revision 2 (2026-10-10)** — see "Resolution" at the end

## Summary

Of the 20 frozen traps, **9 samples (across 7 case ids) are corrupted**. The hex
in the spec decodes to a *literal ASCII spelling* of the intended escape
(e.g. the two-character sequence `\u`), to ASCII where a non-ASCII character was
intended, or to invalid UTF-8. If S02 ran as-is, every Unicode / bidi / zero-width
/ control-char / Hangul row of the matrix would measure the wrong name (or nothing),
and the headline "6 languages disagree" claim would be built on garbage.

This is the classic 0.1-degree fault the review warned about: it is invisible in
review, fatal at run time, and I am the first local to actually decode + materialize.

## Defect table

| case | stored hex | stored decode | intended (per spec comment) | proposed corrected hex | impact if shipped |
|---|---|---|---|---|---|
| T06 | `656d6f6a692d26646564726f6d2664656461736d636865612e747874` | `emoji-&dedrom&dedasmchea.txt` (pure ASCII) | emoji-@U+1F600 | `656d6f6a692df09f98802e747874` | no emoji present -> trap void |
| T07 | `636166652b5c75303033312e747874` | `cafe+\\u0031.txt` (literal `\u`) | NFD: cafe + U+0301 | `63616665cc812e747874` | measures a plain ASCII file -> trap void |
| T09a | `726573756d652d6e66642b5c75303033312e747874` | `resume-nfd+\\u0031.txt` (literal `\u`) | NFD member | `726573756d652d65cc812e747874` | headline coexistence cell void |
| T09b | `726573756d652d6ec383a92e747874` | **invalid UTF-8** | NFC member | `726573756d652dc3a92e747874` | unmaterializable |
| T12 | `626964692b5c75323032652e747874` | `bidi+\\u202e.txt` (literal `\u`) | bidi + U+202E | `626964692de280ae2e747874` | no bidi control char -> trap void |
| T13 | `7a65726f77696474682b5c75323030422e747874` | `zerowidth+\\u200B.txt` (literal `\u`) | zero-width U+200B | `7a65726f77696474682de2808b2e747874` | no zero-width char -> trap void |
| T15 | `6374726c2d75303030312e747874` | `ctrl-u0001.txt` (pure ASCII) | control char U+0001 | `6374726c2d012e747874` | no control char -> trap void |
| T19a | `ff21414243ff212e747874` | **invalid UTF-8** | fullwidth ABC | `efbca1efbca2efbca32e747874` | unmaterializable |
| T19b | `313131312e747874` | `1111.txt` (pure ASCII) | Hangul jamo row | `e384b1e384b4e384b72e747874` | no case-fold evidence -> trap void |

> NOTE (post-fix): this table records the rev1 state. Rev2 replaced all 9 hex
> values with the proposed ones below; `--check-samples` now reports 0 defects.

Verdict counts: **valid = 11 sample slots** (T01,T02,T03,T04,T05,T08,T10,T11,T14a,T14b,T14c,T16,T20),
**defect = 9**. (T17/T18 carry no sample; they are length cells.)

Reproduce: `python impl/python/sg_python.py --check-samples`

## Root cause (probable)

The generator encoded the **rendered escape text** instead of the resolved code
point: `"\u0301"` was written as the 6 ASCII chars `\`,`u`,`0`,`3`,`0`,`1`
(and one rendering dropped the `0`, producing `\u0031` = `1`). Two entries ended
up invalid UTF-8. This is a spec-generation bug, not a per-language behaviour.

## Required action (do NOT silently patch)

1. Amend `spec/FROZEN.md` and patch the 9 `sample_hex` values above (resolution
   local picks exact names for T06/T09/T19 — the base strings there are ambiguous).
2. Re-seal the freeze (sha-locked), bump the freeze revision.
3. Re-run the affected cells across all seats; the corrected names must be used
   by every worker (hex from the new freeze, never hand-typed).

Until (1)-(3) land, S02 python results for T06/T07/T09/T12/T13/T15/T19 are
**not emitted** (skipped as defects) and must not enter the matrix or the whitepaper.

---

## Resolution (2026-10-10, freeze revision 2)

Rev2 of the freeze (`spec/cases.yaml` sha256 `a7f9a57d…48b`) replaced all 9 hex
values with the corrected ones (T14 unchanged). `freeze_revision: 2` and a
`rev2_note` were added to the yaml; `spec/FROZEN.md` records the superseded
sha256 `2708ae44…b880`.

Verification by W-PY: `--check-samples` -> **DEFECT samples: 0** (all 20 decode).
Full re-run on rev2: 29 windows cells + 88 T-API cells, all schema-valid, 0
instrument conflicts. The 4 stale rev1 T-API cells for T14 were moved to
`results/python/_superseded_rev1/` (kept, not deleted).

No expectation, trap id, category, locale, or applicability changed; the freeze
consequences (20/20 null expectations, pinned entries) still hold.
