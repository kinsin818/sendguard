# S02 python port -- self-check, contract rev7 (final tonight)

## SG-F1 re-stamp (ticket `docs/tickets/SG-F1-python-restamp.md`, executed 13:0x-13:2x +0800)

Race guard ran first and passed: `git status --porcelain -uall --
results/python.windows.x64` was empty, and the newest mtime in the directory was
08:26:18 -- before the 13:0x dispatch -- so no other writer held the surface.

What was done is a re-stamp by re-emission: the same cells, emitted again by the
same harness, which already reads `spec/cases.yaml` from the committed blob face
(`git cat-file blob HEAD:spec/cases.yaml` = `8650a1863578`, 11347 bytes, equal to
`spec/cells-required.json`'s `spec_blob_sha256`). No recording logic was changed
and `impl/python/` was not edited at all for this ticket.

Proof it is a re-stamp and not a re-answer, computed per cell against the
pre-ticket commit rather than asserted:

* **verdict fields changed: 0** across all 123 records, comparing
  `os_legality_verdict, mechanism_class, phantom, roundtrip_ok, name_mutated,
  enum_to_stat_agrees, len_triple, bytes_written, bytes_on_disk, name_landed_as,
  create_result, error_stage, read_result, same_name_hits, delivered_nothing,
  name_source, len_ceiling, run_status, extra` old vs new;
* the only differences outside the stamp fields are `scratch_dir` / `leg_dir` (a
  fresh uuid directory per cell, as the contract requires), `win32_fullpath`
  (which embeds that path), and one `entry_spread.elapsed_ms_child` of 3 ms
  becoming 2 ms;
* **records gone: 0** -- 123 before, 123 after, and every one of the 123 resolved
  in the pre-ticket commit, so nothing was wiped rebuilding in place;
* fingerprints now: 50 records carry the current `8650a186…`, 73 carry
  `a7f9a57df1…` (the extra cells -- the 48 frozen-grid points, the two base-13
  bisections and the 11 superseded renames -- which the gate does not compare, so
  they are outside criterion 1 by the leg's own definition); zero records now
  carry the stale `b1eb629c…`.

Criteria as run, with the line each command printed and its real exit code
(`rc` taken from the process, not from a pipeline):

| # | command | rc | line |
|---|---|---|---|
| 2 | `python ci/equality.py` | 1 | `OUTCOME=RED verdict_disagreements=54 ... unpinned_input=0 cells_excluded=0 required_cells_missing=0` |
| 1 | `python ci/spec_drift.py` | 0 | `wrote docs/spec-drift.md bytes=1761 compared=264 current=264 older=0 unstamped=0 older_unresolvable=0 affected_by_delta=0` / `OUTCOME=CLEAN drift_reached_compared_cells=0 (older fingerprints disclosed above, 0 records)` |
| 3 | `python ci/validate_cells.py` | 0 | `wrote docs/cell-validation.md bytes=2536 invalid=0 missing_faces=0 ...` |
| 4 | `python ci/gap_report.py` | 0 | `wrote docs/GAP.md bytes=1354 ports=6 total_missing=0` and `## python - matched 44/44, missing 0, outside-list 0, extra-flagged 75` |
| 5 | `git status --porcelain -uall -- results/python.windows.x64` | 0 | (empty) |

Criterion 2 held exactly at 54 -- it did not move in either direction, so there is
no finding to escalate: the re-stamp changed no answer, which is the same
conclusion `ci/spec_drift.py` reaches from the other side (the delta between
`b1eb629c` and HEAD touches only `T17`/`T18`, and `affected_by_delta=0`).

Two readings worth recording rather than smoothing: `ci/gap_report.py` prints
`total_missing=0` and then the line
`**total missing cells across ports with a face = 0**; declared ports without a
face = 1 (node)`, so criterion 4's "all six ports" is five ports with a face plus
node with none; and `ci/validate_cells.py` reports
`verdict_fields_not_required=9 verdict_fields_undocumented=4
cells_omitting_a_compared_field=371` alongside its `invalid=0` -- those are the
round-9 proposal items, out of scope here and untouched.

Scope of this ticket's writes: `results/python.windows.x64/` (50 cells rewritten,
0 deleted) and this file. The derived faces `docs/spec-drift.md`,
`docs/cell-validation.md`, `docs/GAP.md` and
`evidence/S02/equality-verdict.json` moved only because the criteria commands
regenerated them; none was edited by hand, and none is staged in my commit.

## Rev7 headline (unchanged by the re-stamp)

```
len_cells=12/12 name_source_is_the_passed_bytes=yes len_triple_is_the_name=yes
ceiling_field=len_ceiling controls_pass=true
cells_required=44 cells_matched=44 blocked=0 extra=75   (123 files, 123 valid / 0 void under both rulers)
```

Rev7 is the last contract change tonight, and this section is the only one it
invalidated: the twelve length cells. **Landed late -- the host clock read 07:57
when the focused re-run started and ~08:10 when both rulers came back clean, so
the 07:30 deadline was missed by this seat.** The prior rev6 state of the corpus
was already published and is unchanged except for those twelve files plus the five
controls, which were re-measured alongside them to keep `controls_pass` a fresh
reading rather than a carried-over one.

## 0rev7. The twelve length cells, re-recorded under the pin

`len_fill` is read from `git cat-file blob HEAD:spec/cases.yaml` and the driver
refuses to run if the unit is not exactly one code unit or `applies_to` is not
`[T17, T18]`:

```
unit_hex=61  unit_codepoint=U+0061  applies_to=[T17, T18]
name_source_rule="name_source is the hex of the component that was actually passed to the API, not a label"
```

What changed in my records, rule by rule:

1. **`name_source` is now the bytes handed to the API.** The component is `a`
   repeated `base_len` times, nothing appended, so the hex is `61` x `base_len` =
   156 / 240 / 400 characters for 78 / 120 / 200. Before this round my cell
   carried a uuid-seeded component (`f64c93203nnn...` in the notice's table) --
   real bytes, but not a comparable input. Verified on the published files:
   `name_source_is_pinned_filler=true` and `len(name_source) == 2*base_len` in
   12/12.
2. **`len_triple` is the three widths of that name and nothing else**: flat
   `{code_points, utf16_code_units, utf8_bytes}`, and all three equal `base_len`
   in 12/12, as the notice predicts for a single-unit filler. My earlier shape was
   the nested `{requested, landed}` pair -- one of the three quantities the notice
   found being called "length". The landed name's widths are still published, in
   `name_landed_triple`.
3. **The ceiling moved to its own field.** `len_ceiling` / `len_ceiling_rejected`
   carry what the bisection converged to, measured at a recorded holder depth
   (`holder_dir_len`, `bisect_holder_dir_len`) in a sibling fresh directory so no
   step can collide with the pinned name.

| base_len | plain: pinned component lands? | plain `len_ceiling` | extended: lands? | extended `len_ceiling` |
|---|---|---|---|---|
| 78 | yes | 194 (195 refused) | yes | 255 (256 refused) |
| 120 | yes | 194 | yes | 255 |
| 200 | **no** (`err_at_syscall`, `read_result: not_applicable`) | 194 | yes | 255 |

Twelve cells, `run_status: measured`, no rung unreachable so no blocked cell was
needed. In all twelve, `ceiling_agrees_with_pinned_probe` is true: the pinned
component lands exactly when its length is at or below the converged ceiling. At
holder depth 64 the plain-face ceiling is 194, so the 200-unit pinned component
does **not** land on the plain face for either trap -- that is the honest answer to
the question as pinned, not a failure of the cell.

**One thing this pin does not settle, stated rather than worked around.** With
`base_len` now naming the *component* length, the plain-face answer depends on the
depth of the directory the port happened to create the file in (ceiling =
`259 - holder - 1` = 194 at my holder depth 64; 180 at depth 78), and holder depth
is not an identity dimension in the manifest. Two ports that both obey rev7
exactly can therefore answer `ok` and `err_at_syscall` for the same cell -- and
`bytes_written` / `bytes_on_disk` / `name_landed_as` are VERDICT fields under rev6,
so that difference is judged, not excused. `len_ceiling` makes the difference
*detectable*, which is an improvement, but if the length comparison is meant to
close, the holder depth needs pinning too (or `len_ceiling - (259 - holder - 1)`
compared instead of the create verdict). I did not change the identity shape to
work around it.

Also unchanged and still standing from the rev6 section: `run_status`'s
`measured`/`blocked` words are in no closed set (canonical section 1 lists only
valid/void/instrument_red); the T-API group remains the one live digest collision
by design; and `len_triple` is compared byte-for-byte across ports while its
*shape* is still unpinned (flat dict here, `[n,n,n]` or nested there), which is the
same class of defect rev6 folded for `name_encoding`.

Extras: 75 records stay `extra: true` exactly where they were -- the 48 grid cells
of the frozen G1-G4 ladder (uuid-seeded components, `instrument_base_noncompliant`
where they reached base 13 through a drive-root anchor) and the two old base-13
bisections. My grid cells are *not* re-recorded under `len_fill`, so their
`name_source`/`len_triple` describe what they measured, not the pinned family.

## 0. The three rev6 actions, as measured

detail: 123 cell files published, 123 valid / 0 void under **both** rulers (this
seat's `sg_selfcheck.py`, and the shipped `spec/validate.py` at
`summary: 123 valid / 0 void (of 123)`, exit 0); python's 4 T-API rows 4/4; 0
control mismatches; 0 hangs; 0 cells that could not run. Not
`INSTRUMENT-RED`. Self-test: `selftest_arms=29 passed=29 failed=0`.

HEAD at measurement time: `f15b399`. Manifest matched: the committed blob
`3742747dd412e8a9` of `spec/cells-required.json` (44 rows + 26 T-API rows, of
which 4 are python's). Nothing was committed, pushed, tagged or deleted by this
seat; no tracked file was modified; nothing was written outside
`impl/python/`, `results/python.windows.x64/` and this file.

## 0. The three rev6 actions, as measured

**(1) The five control cells were re-run against the pinned `control_samples`.**
Names and the payload are parsed at run time from
`git cat-file blob HEAD:spec/cases.yaml`; the driver refuses to run if any cell
lacks a valid `sample_hex`/`payload_hex`, if the five payloads differ from each
other, or if the pinned payload does not reproduce the sealed baseline digest
`c9fe45b2...`. The assertions that ran:

```
all_five_present=true  one_payload_for_all_five=true  hex_decodes_losslessly=true
payload_sha_matches_sealed_baseline=true  nametoollong_component_len=256
canon_name_is_pinned_not_transcribed=true
pinned_payload_equals_baseline_script_payload=true
```

`T-CTRL-CANON` now asks the pinned question `63616e6f6e2d636865636b2e747874`
(`canon-check.txt`) instead of `canon-python.txt`, which my port had taken from
`harness/ctrl-baseline.mjs`. That was my contribution to the hole rev6 closed:
four cells ids, four spellings, two payloads hashed under one id. The CANON cell
now reports `sha256_self == sha256_truth == c9fe45b2...`, and the ASCII cell
28 written / 28 on disk / read `ok` / `legal`, matching the S00 baseline line for
line. Cells that fail at the create still answer `read_result: not_applicable`
with `read_skipped_reason`, which is the same statement the baseline makes by
leaving those columns empty -- my ruler used to read an empty baseline column as
"the cell must not carry a value" and cried INSTRUMENT-RED over that; an arm now
holds both directions of that rule.

**(2) The five blind cells are `blind/B1..B5` and they are now matched.** They
were already published with the right identity; what made them "missing" is
section 3, defect R-1 -- they were flagged `extra` against the manifest this seat
had loaded at the time (33 rows, no blind rows), and `ci/equality.py`'s
`discover()` drops an extra cell *before* it is keyed. Re-reconciled against the
44-row manifest, `extra` is false on all five and `gap_report`'s own path matches
them.

**(3) The twelve `len` rung cells.** `len/T17` and `len/T18` at
`base_len` in {78, 120, 200} x `path_form` in {plain, extended}, identity exactly
`{base_len, path_form}` (my companion cells previously carried a third declared
dimension `probe`, which is why the opposite-face answers existed but did not
count). Every one carries `len_triple` and the bisection bracket (11 steps, each
step its own child process, `timed_out` recorded per step):

| base | plain face: largest component | total path | extended face: largest component |
|---|---|---|---|
| 78 | 180 (181 refused) | 259 | 255 (256 refused) |
| 120 | 138 (139 refused) | 259 | 255 (256 refused) |
| 200 | 58 (59 refused) | 259 | 255 (256 refused) |

Both traps, both faces. That is gate.md section 5's regime model satisfied exactly
at every rung: `longpath_mechanism = none` gives `259 - base_len - 1`, and
`prefix_rewrite` gives the volume's `max_component` 255 regardless of depth --
which is precisely why the zero-tolerance law could not stay a gate condition.
No rung was unreachable, so no `run_status: blocked` cell was needed; the blocked
path is nevertheless implemented and was exercised deliberately against an
identity no plan item produces, emitting `blocked_command`, `blocked_exit_code`
and one attempted fix.

## 1. The rev3/rev4 round (numbers superseded by section 0; kept for provenance)

**Rev3/rev4 fields.** Every cell carries `length_unit = code_points` (python's

`len(str)` counts code points, and every length reported here comes from it),
`name_encoding = hex_raw_bytes` (how the record spells the name bytes), and
`verdict_via` -- `win32` on 108 cells (`kernel32.GetFileAttributesW` through
ctypes, extended prefix, parser bypassed) and `none` on 3, where no tool was
reached at all (two zip-extract legs and the embedded-U+0000 control). The old
`utf16_code_units` value is gone from `name_encoding`; the utf16 and utf8 counts
are still published beside the length in `len_triple`.

**(2) Reconciled against the manifest.** All 37 rows python owes (33 shared + 4
python T-API) are produced: `required_missing=0`, `extra_mislabelled=0`, and the
extras are marked on all 74. Two identity reshapes were needed because rev3 puts
the varying dimension where the gate can read it: member cells moved into the
case id (`trap/T09-m1`, `T09-m2`, `T14-m1..m3`, `T19-m1,m2`, `sub_identity {}`,
with the 0-based position in the frozen `sample_hex_list` kept as data), and
T-API rows carry `sub_identity {}` separated by `api_entry`. The six required
`len` cells are new bisections at the ladder rungs {78, 120, 200}, plus six
companion cells on the opposite face -- which is what makes the regime model in
section 5 below checkable.

61 records from the rev2 run were **migrated in place** rather than re-measured
(`rev3_migrated: true` with per-record notes naming every field added), and the 11
whose identity rev3 renamed are marked `superseded_by` pointing at the new file.
Nothing was deleted: this port contains no deletion logic (M19), and dropping a
published measurement to tidy a count would be the same act with better wording.

**(3) Re-run and reported** in the notice's shape (top of this file).

**Rev4 closed the two gaps I reported against rev3**, and I re-emitted for them.
The fifth `read_result` word is now used on all 43 cells whose read leg could not
run, each with the `read_skipped_reason` rev4 demands: 25 "nothing landed because
the create failed" (`FileNotFoundError`, `OSError` EINVAL, or the U+0000
`ValueError`) and 18 reserved-device-name cells refused by the red line. Absence
of `read_result` is now a defect in both directions: my ruler flags
`not_applicable` without a reason, and also a reason attached to a cell that
claims `read_result=ok`.

## 2. Rulers and arms

| ruler | source | result |
|---|---|---|
| `impl/python/sg_selfcheck.py` | blob faces of schema.json, canonical.md, cells-required.json; 29-arm self-test | 123 valid / 0 void, 44/44 required matched + 4/4 T-API, controls 5/5 |
| `spec/validate.py` (shipped) | disk, closed sets aligned with schema.json by rev4/rev6 | `123 valid / 0 void`, exit 0 |
| `ci/equality.py`'s own keying, executed from its blob face (the path `ci/gap_report.py` takes) | gate's rules, not my copy of them | `matched=44/44 missing=0 outside_list=0 duplicate_keys=0` |

Self-test: `selftest_arms=29 passed=29 failed=0`, green and red side. Three arms
exist because the ruler was wrong before they were written -- each error would have
produced a confident false verdict rather than a message:

* the canonical-set parser keyed its sets by **section number**, so the closed-word
  check was silently checking nothing;
* the red-line rule flagged *any* `read_result` on a reserved-name cell, which after
  rev4 would have called all 18 legitimate `not_applicable` cells a breach;
* and, this round, my control-cell comparison read the baseline's empty
  `read_result` column as "the cell must carry no value", so rev4's honest
  `not_applicable` was reported as a control failure -- an INSTRUMENT-RED over a
  run whose controls all passed. It now treats an empty baseline column and
  `not_applicable` + reason as the same statement, with arms in both directions.

One of my own measurements also had to be thrown out: the digest-collision count
I reported last round (20 keys) did not skip `extra` cells before keying, which
`discover()` does. Re-measured the way the gate does it: 48 live cells, 45 keys,
1 colliding. Publishing the stale figure would have invented a defect.

Sealed hashes: `frozen_hash_claims=8 verified=8 mismatched=0`. The blind-map seal
I reported broken under rev2 is fixed upstream and verified here.

Independent manifest check (not a copy of `ci/gen_cells_required.py`): I re-derive
the required set from the committed faces -- member counts off the frozen hex
lists, `len` for T17/T18 per canonical section 2, the rung ladder times both path
forms, the five blind cells from `evidence/S00/blind-map.json` -- and compare it to
the published manifest: `manifest_rows=44 derived_rows=44 only_in_manifest=0
only_in_cases_yaml=0`. Under rev3 this comparison failed (the committed generator
derived 20 rows, all `trap`, no members); `b0a2dc3` fixed it, and this round it
again caught a real drift in my own derivation when the manifest grew blind cells
and the second path form.

## 3. Where the contract and the gate still disagree

**Resolved by rev6, kept here because the earlier round reported them open:** the
two rulers disagreeing on 100% of cells (C-3 in the rev4 numbering -- validate.py
now carries `length_unit`/`hex_*` and `typescript`), the missing fifth
`read_result` word, T-API invariance being called an instrument failure, and
extras being compared at all (they are skipped now). Measured on the current
commit: `live(after extra skipped)=48 gate_keys=45 colliding_keys=1`.

### New in this round

**R-1 -- an `extra` flag on a required cell is a deletion, and nothing in the
contract says so.** `ci/equality.py:234` drops a cell whose `extra` is true before
`key_of()` ever sees it; `ci/gap_report.py` then reports that identity as MISSING.
Five ports, including this one, were caught by exactly that: python had published
`blind/B1..B5` and both faces of six rungs, and the gap read "missing 11". The
flag is the only mechanism a port has for honouring "keep extras, mark them", so
a port that obeys the notice while reconciling against a manifest that is one
revision behind silently loses cells. Two cheap fixes, either is enough: have
`gap_report` print `required_but_flagged_extra` as its own loud state, or have the
notice say that a cell matching a required row must never be flagged extra
whatever manifest the port loaded. My ruler now measures the count directly
(`required_but_flagged_extra=0` here) rather than trusting the label.

**R-2 -- `run_status: blocked` uses words that are not in the closed set.**
NOTICE-rev6 asks for `run_status: blocked`; `spec/canonical.md` section 1 defines
only `valid` / `void` / `instrument_red`, and its line 1 voids a cell whose status
word is outside that file. I emitted the field as asked (`run_status` on all 123
cells: `measured` or `blocked`), and recorded the vocabulary gap instead of either
dropping the field or quietly inventing a third canonical word. Same class as my
earlier `verdict_via`/`length_unit`/`name_encoding` note: canonical.md still has
no section for any of the four, so the file that claims supremacy over status
words does not contain half of them.

**R-3 -- the T-API group is the one digest collision left among live cells, and it
is the point of those cells.** `('tapi','T-API',())` holds 4 cells with 2 digests.
`key_of()` excludes `api_entry` by design, the manifest separates those rows by
`api_entry`, and rev6's PROBE split removes `create_result`/`error_stage`/
`read_result` from the comparison -- but `bytes_written` is a VERDICT field, and
`os.mkdir` legitimately writes nothing where `open_wb` writes 28. So a group whose
whole purpose is "this language does not agree with itself" will always look like
a collision to the ambiguity leg. Suggested wording: `tapi` cells are keyed by
`api_entry`, or they are exempted from the multi-entry refusal and reported as
`entry_spread` -- which is what cell-identity section 2 already says they are.

**R-4 -- base 13 is still not reachable by a compliant instrument on this box.**
gate.md section 5 now permits base 13 "as extra", reachable "inside a copy through
a mapped drive (`subst`)". Creating a drive map is a machine-level change, not
something a probe seat should do unasked, so my 48 grid cells at base 13 remain
what they are: real measurements, taken earlier under a drive-root directory, now
labelled `instrument_base_noncompliant` against cell-identity section 6, kept as
extras, and used for nothing in the rung coverage above.

## 4. Where the contract and the gate disagreed (rev4 round, for provenance)

**C-1 -- "extra cells do not enter the equality digest" is not true of the
committed gate.** NOTICE-rev3 promises it; `ci/equality.py` at HEAD has no
`extra` test. It is in the working tree, uncommitted (`if c.get("extra") is True:`
at line 154 of the file on disk, alongside new code that reads
`spec/cells-required.json`) -- so the promise is currently a pending edit, not a
property. Measured with the gate's **own committed** keying and digest, executed
from the blob face rather than transcribed: `gate_keys=108
colliding_keys=1 required_identity_involved=1`. My replica of the rule agrees
(`colliding_keys=1`), which is the point of keeping a replica.

**C-2 -- the one collision is the T-API group, and the manifest itself causes it.**
`('tapi','T-API',(('path_form','plain'),))` holds 4 cells with 2 digests. Two
things produce that: the required list distinguishes the four python T-API rows
only by `api_entry`, which `key_of()` deliberately excludes; and a cell whose
declared `sub_identity` is empty makes the gate fall back to `SUB_FIELDS`, which
rev4 grew to include `path_form` -- a behavioural field. So four different answers
share one key and the gate's own rule ("refuse to collapse entries that disagree")
fires. A port cannot fix this by adding a dimension to `sub_identity`, because the
manifest states `{}` for those rows. Either the manifest gives T-API rows a
declared dimension, or the gate keeps `api_entry` out of the fallback for them.

**C-3 -- `verdict_via` is required in prose and in my gate, not in schema.json.**
Its description says "rev3 required"; `required[]` (lines 8-26) does not list it,
so a strict jsonschema pass accepts a cell with no `verdict_via`. An arm says so
explicitly (`red: verdict_via absent from schema.json required[]`). Related:
cell-identity section 6 enumerates `win32|dotnet|cmd|posix` while schema.json adds
`none`; I use `none` for 3 cells and consider a fourth word for "not asked" the
cleaner fix, but the two files must agree on which it is. canonical.md still has
no section for `name_encoding`, `length_unit` or `verdict_via` (my ruler prints
that every run), while its line 1 says any word outside that file voids the cell;
rev4 aligned `validate.py` and `schema.json` with each other, which is what made
the two rulers agree, but the canonical sentence is still unqualified.

**C-4 -- the manifest on disk is ahead of the manifest in HEAD.** The working copy
of `spec/cells-required.json` has **44 rows**: the 5 blind samples became required,
and the `len` rows are keyed `base_len + path_form` (12 rows instead of 6). Both
sets of cells are already measured and published here -- my blind cells exist, and
I ran both faces at all three rungs -- so this is an identity-shape flip, not new
work: under the committed list my required-face `len` cells match and the
companion face is `extra`; under the working-copy list it would be the reverse and
the blind cells would stop being extra. I coded to the committed, hash-locked face
and flag the divergence instead of guessing which side of a moving file to obey.
Say the word when it is committed and the flip is one field.

**C-5 -- FROZEN's G1-G4 grid still pins `base_len 13`; rev4's gate.md section 5
now says 13 is "permitted as extra" reachable through a `subst` mapped drive, and
cell-identity section 6 forbids creating directories at a drive root.** My 48
grid cells from the rev2 run reached base 13 by a drive-root anchor, so each now
carries `instrument_base_noncompliant` quoting the sentence, kept as a labelled
extra, and none of them is used to claim the ladder. The 12 rung cells (6 required
+ 6 companions) were measured under the documented `%TEMP%\sendguard-run` root with
no drive-root directory anywhere.

## 5. Measurements that matter (python, this box)

* **Rev4's regime model is satisfied exactly, at every rung, both traps.** With
  `longpath_mechanism=none` the largest component is `259 - base_len - 1`: base 78
  -> 180, 120 -> 138, 200 -> 58. With `prefix_rewrite` it is 255 at every base,
  256 refused. All 12 cells, eleven bisection steps each, every step its own child
  process, zero deviation between the two models' predictions.
* **The "boundary code" in gate.md section 5 is not observable from a python
  create, and I did not invent it.** At the plain-face boundary python reports
  `FileNotFoundError` with `errno=2` and **`winerror` unset**; under `\\?\` at 256
  it reports `OSError` `errno=22` (EINVAL), also with `winerror` unset. The 123
  that gate.md expects arrives only from a *different* API --
  `GetFileAttributesW`, which is exactly what `verdict_via` was added to separate.
  So the cells carry `error_type`, `error_errno` and `error_winerror: null` as
  measured, and `os_legality_detail.winerror: 123` from the probe that can see it.
  A port that printed "3" and "123" in the create fields would be reporting a code
  its own language never returned.
* **A "success" that delivers nothing: 7 live cells** (`T01`, `T02`, `T10`, `T11`,
  `T14-m2`, and the `open_wb` and `pathlib.write_bytes` T-API rows) --
  `create_result: ok`, `bytes_written: 28`, zero entries in the directory, and the
  OS says the name is legal. 10 records if the superseded duplicates are counted.
* **Python's pinned entries disagree with each other in 25 live cells**: `os.mkdir`
  24, `os.rename` 5, and `pathlib.write_bytes` **0** -- nowhere in this set did it
  differ from `open_wb`. Under rev4's amended T-API clause this is data, not an
  instrument failure.
* **Trailing dot/space stripped before the filesystem** (`T04`, `T05` only:
  `747261696c2e` -> `7472616c`, 6 code points -> 5; `GetFullPathNameW` already
  returns the stripped form). **NFC and NFD coexist**: one directory, 1 entry after
  `T09-m1`, 2 after `T09-m2`, each found by its own exact spelling.
* **ZIP bit 11 round-trips**: ASCII entry `flag_bits=0`, emoji entry `flag_bits=2048`;
  both extractors recover 2 entries byte-identically. `packer_version` /
  `extractor_version` are recorded for the packer/extractor cells; for the required
  `trap/T16` cell the zip side is recorded as `zip_packer` / `zip_extractor`
  *instead of* `packer` / `extractor`, because rev4 made those two names
  identity-bearing for the gate and using them there would have moved a required
  cell to a different key than the manifest states.
* 68 cells read back byte-identically (`sha256_self == sha256_truth` in every cell
  where a read happened); 0 hangs; 0 cells could not run.

## 6. Machine facts recorded in every cell

`C:\Python314\python.exe` 3.14.7 (resolved `sys.executable`; `C:\Windows\py.exe`
and the App Execution Aliases on this PATH were not used; CI pins 3.13, so a CI
run is a different interpreter), Windows 10.0.19041 AMD64, `LongPathsEnabled = 0`
(re-read from HKLM at run time, agreeing with the S00 env facts),
`max_component` 255 on both volumes, 8.3 creation enabled on C: / disabled on D:,
`unicodedata 16.0.0`, locale `('Chinese (Simplified)_China','936')` with
`utf8_mode=0`, console handle 0. `python.exe`'s manifest declares `longPathAware`
and plain paths over 259 still fail -- measured at all three rungs -- because the
registry switch is 0. `spec_sha256` comes from
`git cat-file blob HEAD:spec/cases.yaml` (`a7f9a57d...`, 8075 bytes, blob equals
disk); the manifest blob this run matched is `779b6ce3...`, the value FROZEN locks
(the `fe2d0824` revision it replaced landed minutes earlier, also committed).

## 7. Independence and red lines, re-verified

No other lane's `impl/` and no port's `results/` was read; `spec/expectations.sealed.md`
was not opened; `ci/equality.py` was read (it is the contract's consumer) and its
keying is *executed from the committed blob* inside my ruler rather than run
end-to-end, because running the gate reads every port's `results/`. Every probe is
one child process (`subprocess.run(argv list, shell=False, timeout=5.0)`), rc
checked before output is used, partial child records salvaged, an unreached phase
recorded as `hang` and never retried; a crash gets exactly one re-spawn, recorded in
`child_reruns`. Reserved device names are created and listed only -- no content
open, and their attribute query goes through the extended prefix so it cannot reach
the device namespace either. No deletion logic exists anywhere in this port; scratch
dirs accumulate under `%TEMP%\sendguard-run\`; every cell carries
`cleanup_attempted: false`. One fresh uuid directory per cell, verified empty before
use; the single documented sharing is the T09 coexistence probe (one directory, two
member cells, each carrying its own `pre_existing_entries` 0 and 1). Names are
decoded at run time from committed hex -- including the control names, which are
hex in my source and whose 256-unit component is built from a repeat count read out
of `harness/ctrl-baseline.mjs`. Verified by scanning, not asserted: no plaintext
sample name appears in any of the 111 records or any file this seat wrote. Zero
third-party dependencies. Writes stayed inside `impl/python/`,
`results/python.windows.x64/` and this file.

## 8. Not completed, and why

1. `cross_reader` with a second language -- the CI crossread job is Node<->Python
   and other lanes' results are forbidden here, so only intra-port two-view
   evidence is published (`path_view` vs `dir_view`, `enum_to_stat_agrees`,
   `phantom`).
2. The aggregate file -- `ci/export_aggregate.py` still does not exist in `ci/`
   (blobhash, equality, evidence_table, gen_cells_required, lint, selftest), and
   `ci/` is outside my write scope. 111 authoritative per-cell files are published;
   no aggregate was hand-written.
3. `attribution_layer` is provisional by construction: the tree's first pass needs
   "varies across OS", unobservable from one port on one OS. Every cell names the
   pending axis in `attribution_layer_basis`. Over the 100 live records: L1 18,
   L2 20, L3_interaction 62 (every `len` cell); over the 37 required cells L1 16,
   L2 15, L3_interaction 6.
4. T19's case locale is ja-JP; this box is zh-CN/cp936 and a probe cannot switch
   machine locale, so both are recorded rather than one being faked.
5. T07/T08/T09 are `applicable: [macos, ubuntu]` on a Windows box. They were run
   anyway and each record carries `spec_provenance.applicable`, because a silent
   drop loses the comparison and the answer is still a fact about this box.

## 9. Files written by this seat

`impl/python/sg_run.py` (runner, rev3/rev4 reconciliation, migration),
`impl/python/sg_probe.py`, `impl/python/sg_probe_zip.py`,
`impl/python/sg_selfcheck.py` (29 arms), `impl/python/sg_prereq.py`,
`impl/python/sg_run_log.txt`, `sg_selfcheck_log.txt`, `sg_validate_py_log.txt`,
`sg_run_summary.json`, `results/python.windows.x64/*.json` (111 cell files),
and this report. Instrument dumps sit under `impl/` because the only evidence path
this seat may write is this single file, while cell-identity section 3 says dumps
belong in `evidence/` -- noted, not resolved by me.
