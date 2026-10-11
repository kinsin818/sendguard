# Status - the numbers, generated

From `evidence/S02/equality-verdict.json`, written by `ci/equality.py` at 2026-10-11T11:26:25+0800; this file is written by `ci/status_brief.py` at 2026-10-11T11:26:25+0800. Any other document quoting these counts is stale by construction - re-run the two commands instead of trusting the prose.

| quantity | value |
|---|---|
| required cells in the contract | 44 |
| cells run by every port | 44 |
| cells the gate compared | 44 |
| cells with no verdict conflict | 24 |
| conflicting verdict facts | 54 (over 20 cells) |
| probe cells differing (the matrix, not a failure) | 29 |
| cells excluded for different input bytes | 0 |
| cells excluded for a different path form | 0 |
| cells with a legality-field abstention | 13 |
| names matched across encodings | 12 |
| prefix-shaped name records (flagged, not deleted) | 2 |
| outcome | RED |

## Cells with a verdict conflict (20)

- `ctrl/T-CTRL-CANON` - mechanism_class
- `ctrl/T-CTRL-ILLEGAL-CHAR` - mechanism_class
- `ctrl/T-CTRL-NAMETOOLONG` - mechanism_class
- `ctrl/T-CTRL-PARSE` - mechanism_class
- `len/T17[base_len=120,path_form=extended]` - roundtrip_ok
- `len/T17[base_len=200,path_form=extended]` - enum_to_stat_agrees, phantom, roundtrip_ok
- `len/T17[base_len=78,path_form=extended]` - roundtrip_ok
- `len/T18[base_len=120,path_form=extended]` - roundtrip_ok
- `len/T18[base_len=200,path_form=extended]` - enum_to_stat_agrees, phantom, roundtrip_ok
- `len/T18[base_len=78,path_form=extended]` - roundtrip_ok
- `trap/T01` - bytes_on_disk, bytes_written, os_legality_verdict, phantom
- `trap/T02` - bytes_on_disk, bytes_written, os_legality_verdict, phantom
- `trap/T04` - bytes_on_disk, enum_to_stat_agrees, len_triple, name_landed_as, name_mutated, os_legality_verdict, roundtrip_ok
- `trap/T05` - bytes_on_disk, enum_to_stat_agrees, len_triple, name_landed_as, name_mutated, os_legality_verdict, roundtrip_ok
- `trap/T10` - bytes_on_disk, bytes_written, os_legality_verdict, phantom
- `trap/T11` - bytes_on_disk, bytes_written, os_legality_verdict, phantom
- `trap/T14-m1` - bytes_on_disk, os_legality_verdict
- `trap/T14-m2` - bytes_on_disk, bytes_written, os_legality_verdict, phantom
- `trap/T14-m3` - bytes_on_disk, os_legality_verdict
- `trap/T16` - bytes_on_disk, bytes_written

## Field abstentions (a port asked the legality question somewhere else) (13)

- `ctrl/T-CTRL-PARSE` - java
- `len/T17[base_len=120,path_form=extended]` - typescript
- `len/T17[base_len=120,path_form=plain]` - typescript
- `len/T17[base_len=200,path_form=extended]` - typescript
- `len/T17[base_len=200,path_form=plain]` - typescript
- `len/T17[base_len=78,path_form=extended]` - typescript
- `len/T17[base_len=78,path_form=plain]` - typescript
- `len/T18[base_len=120,path_form=extended]` - typescript
- `len/T18[base_len=120,path_form=plain]` - typescript
- `len/T18[base_len=200,path_form=extended]` - typescript
- `len/T18[base_len=200,path_form=plain]` - typescript
- `len/T18[base_len=78,path_form=extended]` - typescript
- `len/T18[base_len=78,path_form=plain]` - typescript

## What PASS would require

Every required cell compared, no port disagreeing on any verdict field, and no field abstained or unpinned. The gate refuses to report PASS on the intersection: a cell one port did not answer is a gap, and a cell whose ports asked different layers is not a result.

