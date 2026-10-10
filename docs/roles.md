# SENDGUARD role assignment table (per 2nd-round final arbitration B14)

Frozen at S00. Instrument author must NEVER be the measured language
(M10/M17: worker and instrument share zero code; auditor never audits own cells).

| Seat | Language / role | Assignment | Notes |
|---|---|---|---|
| W-NODE | node | 小工 | measurement pilot (first implementation, sets the pattern) |
| W-PY | python | **小侠** (B14 swap) | headline cell compares Node vs Python; the two must NOT come from one hand |
| W-GO | go | 千问 | — |
| W-JAVA | java | 小侠 | — |
| W-CS | csharp | 老马 | seat fill (final arbitration) |
| W-RUST | rust | **小工** (B14 swap) | after the swap every seat still holds exactly 2 languages |
| audit (S03/S09) | independent external model instances x2 | — | no self-signed PASS (M17); never audits own seat |
| taking data (S00/S04/S05/S08) | 老马 | — | — |
| journey.md | 小工 (main writer) + 小侠 (co-sign) | — | "failures & change-of-mind" >= 1/4 of the doc, each with original output attached |
| tables B/C | 小工 | — | — |
| whitepaper final pass | 老马 | S09 | — |

## Six-language semantic groups (frozen)

| group | languages | name-counting unit |
|---|---|---|
| UTF-16 code units | node, java, csharp | 3 |
| code points | python | 1 |
| UTF-8 bytes | go, rust | 2 |

S07 gate: each group needs >= 1 language proven; M11: all six done is the
red line.
