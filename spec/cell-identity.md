# Cell identity and storage authority (contract patch 1)

Status: adds sentences the frozen spec never had. It does **not** edit `spec/cases.yaml`, `spec/gate.md` or
`spec/canonical.md`; those are re-sealed in one deliberate revision once the sealed expectation table is
filed, because a lock must move once, not while someone is reading it.

Why this file exists: `ci/equality.py` was pointed at the three ports already in the repo and returned
`NOT-COMPARABLE`. Measured reasons, all of them missing sentences rather than bad ports:

| measured | meaning |
|---|---|
| cross-port key intersection = **0** | the cell identity in use (language × entry × trap) cannot be compared across ports, because `api_entry` is a language-specific string |
| **21** cells hold several entries that disagree with each other | "what did Go answer for T01" currently has no single answer |
| **48** length cells collide on an unrecorded dimension | the root depth lives in the filename and not in the cell |
| python 117 / node 36 / go 27 distinct cells | the three ports did not run the same question set |
| 5 non-cell JSON files inside `results/` | a loader that skips unrecognised files makes a broken run look clean |

## 1. The equality key

A cell's identity for cross-port comparison is:

```
(case_group, case_id, sub_identity)
```

- `api_entry` is **not** part of it. It stays in the record as data — the T-API sub-cells exist precisely to
  show that one language does not agree with itself, and that is a finding, not a comparison key.
- `sub_identity` is an ordered, named set of extra dimensions, and it is **required** whenever a case is run
  more than once per port. Declared values:
  - `len` group: `base_len` (integer, the length of the directory path with no trailing separator)
  - cross-reader work: `builder`, `reader`
  - zip round-trip: `packer`, `extractor`
- A dimension that varies must appear as a named field inside the cell. Encoding it only in the filename is
  not identity — that is what produced the 48 collisions above.

## 2. Primary entry per (port, trap)

The equality digest uses the **primary** entry. Every other entry for the same cell is kept, published, and
reported as `entry_spread`, but it does not enter the digest.

| port | primary entry | why |
|---|---|---|
| python | `open_wb` | create-and-write with content is what a deliverer actually does |
| node | `writeFileSync` | same |
| typescript | `writeFileSync` | same runtime; the port is written in TypeScript, evidence says `TypeScript (Node runtime)` |
| go | `os.Create` | same |
| java | `Files.write` | one-step NIO write; `File` variants are kept as `entry_spread` |
| csharp | `File.WriteAllBytes` | one-step write |
| rust | `File::create` + write | same |

A port that cannot run its primary entry records `blocked` for that cell with the command and its exit code.
It may not silently substitute another entry, and it may not mark the cell passed.

## 3. Storage authority

- Authoritative: one file per cell, `results/<lang>.<os>.<arch>/<case_group>__<case_id>[__<sub>].json`.
- Derived: the aggregate `results/<lang>.<os>.<runtime_version>.json` is **generated** by
  `ci/export_aggregate.py` from the per-cell files. Nobody hand-writes it, and `ci/equality.py` re-derives it
  and refuses if the stored aggregate disagrees with the cells it claims to summarise.
- `results/` may contain nothing but cell files. Instrument dumps, manifests, phantom exports and audit
  captures move to `evidence/`. A file in `results/` that is not a cell is a defect the gate reports, not
  one it skips.

## 4. Denominator rule

The gate compares question sets before it compares answers. Two ports with different cell sets produce
`NOT-COMPARABLE` naming both directions of difference; it never compares the intersection and reports the
result as agreement. This is the specific way the old criterion let the project look finished while three
ports had answered three different questionnaires.

## 5. What this patch does not decide

- The `expectation: null` policy in the shipped spec stays (the divergence appendix needs it unpolluted).
  The independent expectation lives in `spec/expectations.sealed.md`, hashed at seal time, opened only after
  the port digests are in.
- Whether a given machine's answer depends on hardware (a reserved name with a device behind it) or on
  policy (`LongPathsEnabled`) is an environment fact, recorded per run, never folded into a verdict.
## 6. Addendum from the outside referee (2026-10-11, `evidence/freeze/referee-windows.md`)

Two sentences this contract was missing, added because the referee measured their absence:

- **`os_legality_verdict` must be accompanied by `verdict_via`** ∈ {`win32`, `dotnet`, `cmd`, `posix`}.
  Measured on one machine: `.NET`/PowerShell strip a trailing U+00A0 while `cmd` preserves it, and `cmd`
  does not reject `a"b.txt` / `a:b.txt` at all - it silently creates `ab.txt` and `a`. There is no
  tool-independent answer to "is this name legal", so a verdict without the name of the tool asked is not
  comparable and the cell is `void`.
- **`len` cells use the base ladder {78, 120, 200}**, not {13, 60, 120, 200}. The short rungs are
  unreachable under the rule that an instrument may not create directories at a drive root; the shortest
  legal base measured here is ~78 characters. Each cell still records its own `base_len` rather than
  assuming a canonical root length.

Zip cells must carry `packer` and `extractor` with versions. That was already required by section 1 and is
now demonstrably not ceremony: `Compress-Archive` sets the UTF-8 flag (bit 11) while `bsdtar` does not and
stores names in CP936, so two archives made on the same machine differ in portability.

## 7. Every digest in this repository is a blob-face digest

`git cat-file blob HEAD:<path>` is the only authoritative byte source for a hash. A digest computed from a
checked-out file is not comparable between machines, because checkout may rewrite bytes (measured here:
384 of 388 files differed before `-text` was pinned). Use `ci/blobhash.py`; do not hand-hash.

Two independent defects of this class were found in one night - the generated evidence table, and the
sealed expectation table's binding line - which is why this is a rule and a helper, not a correction.

## 8. Final identity and comparison-set rule (rev5)

- The comparison set **is** `spec/cells-required.json`. The gate compares exactly those cells; anything a
  port emits outside the list is published and counted, never compared. This removes the last way a port
  can be "right on its own terms" and still not line up with the others.
- `sub_identity` is an object holding exactly the applicable dimensions. For `len` cells the dimensions are
  `base_len` and `path_form` (plain and extended are two separate measurements). For every other group
  `sub_identity` is `{}` - `path_form` there is a behaviour field, not identity.
- Blind cells are named `B1`..`B5`, taken from `blind_id` in `evidence/freeze/blind-map.json`. No port invents
  its own blind spelling.
- `tapi` cells are per-language by construction (the pinned entries are different strings), so they are
  **excluded from the equality digest** and reported separately as the instrument self-check. They are
  still required, and `gate.md` section 2 governs what their results mean.

## 9. rev6 - what may differ, and what the gate folds before it judges

Two rules were added after the rev5 run, both from measurements in that run rather than from argument.

**9.1 Representations are folded; absences are not.** Four ports recorded one control cell identically
(create ok, 28 written, 28 on disk, read ok, legal, same payload digest `c9fe45b2...`) and the gate still
called it a disagreement, because the landed name was written as hex by two ports and as text by two,
the length triple as a dict by one, as `15/15/15` by another, as `[15,15,15]` by a third, and omitted by
a fourth. `ci/equality.py` now canonicalises those forms (`canon_name`, `canon_triple`) and nothing else:
a field a port did not record stays `NOT-RECORDED`, which is a completeness finding, never an answer.
`name_encoding` and `length_unit` left the compared field set for the same reason - they say how a value
was written down. `control_pass` and `instrument_red` left it too: they are health declarations and the
health leg already reads them, so comparing them again turned "this port does not stamp control_pass on a
trap cell" into a disagreement about that trap cell.

**9.2 Spelling drift is folded only where the record says which cell it is.** Measured drift:
`B1` / `BLIND-1` / `T-BLIND-1` for one blind sample; `T09a` / `T09-m1` for one member of a
`sample_hex_list`; `T17-GRID-B120-L137` for one rung point of `T17`. The folder is in
`canonical_case_id` and it refuses to guess:

- a bare family id (`T09`, no member) is **not** folded into `T09-m1` - the record does not say which
  member it measured, and folding it would be the gate inventing data;
- a grid id folds only when the base length written inside the id equals the cell's own `base_len`;
  an id that contradicts its own payload stays outside the list.

**9.3 Two classes of field, because a port answers two questions.** `VERDICT_FIELDS` are the checker's
answer about the name - is it creatable, by which mechanism, did the name survive, how many bytes are on
the disk, what does the directory enumerate - and six independent implementations of one spec must give
the same bytes there. `PROBE_FIELDS` are what this language's own standard library did
(`create_result`, `error_stage`, `read_result`, `longpath_mechanism`, `deps_*`), and those are *allowed*
to differ: they are the matrix and the appendix. Six ports reporting the same verdict for what `go`
`os.Create` returns would be the suspicious result, not the good one. A run is `RED` only on a
`VERDICT_FIELDS` disagreement; probe spread is counted and published.

**9.4 Cells that are not the same question are named, not judged.** If two ports recorded different
`path_form` or different `verdict_via` for one cell, they asked different layers different questions; the
cell goes to the `incomparable` list. If the pinned input bytes themselves differ (`name_source`), the cell
goes to `unpinned_input`. Measured in the rev5 run: 5 cells had unpinned inputs (two ports embedded their
own language name in the `T-CTRL-CANON` sample, one used a different NUL sample, one a different filler for
`T-CTRL-NAMETOOLONG`) and 7 differed by `verdict_via`.

**9.5 Only the canonical face of a port is read**: `results/<port>.<os>.<arch>/`. Measured: `results/`
held `python`, `python.windows.x64` and `python.windows.3.14.7.json` at once - different contract
revisions of one port. Folding them inflates a denominator with cells produced under another schema;
splitting them reads one port as two disagreeing ports. Non-canonical faces are printed by name and count
and excluded.
**9.6 A prefix-shaped landed name is flagged, never deleted.** Tried first as a deletion rule and rejected
in the same hour: on `trail.` and `trailsp ` the landed name genuinely IS a prefix of the input (Windows
drops the trailing character), which is the project's best finding; on `report-2026.txt` three ports
recorded a name cut at a display width while their own record said `name_mutated=false`, which is a
self-contradictory record. From the hex alone the two are indistinguishable, so `ci/equality.py` prints
`PREFIX-SHAPED` naming the ports and leaves the disagreement standing. A rule that cannot tell a finding
from an artefact must not be allowed to choose which one to delete.

**9.7 Three quantities, one name.** The frozen spec's `sample_hex` for T17/T18 was prose
(`T-LEN-PATH (length bisection, G1-G4)`), and the rev6 run showed what that allows: one port recorded that
prose as the name it created (and a length triple of 48/48/48, the length of the prose), one recorded `a`
repeated, one a `0123456789abcdef` cycle, one an alphanumeric run padded with `n`, one `t.bin` with a
code-point count of 32739, and one the two characters `61` where a byte was meant. The triples were not
different spellings of one number but three different quantities: the width of the requested name, the
width of the landed name, and the ceiling a bisection converged on.

So: `name_source` is the hex of the bytes passed to the API; `len_triple` is the three widths of that name
and nothing else; the converged ceiling is `len_ceiling`, a separate field. `spec/cases.yaml` now pins
`len_fill` (one code unit `U+0061`, repeated to `base_len`) so the twelve required length cells ask one
question. Multi-byte tiers (emoji, CJK) remain valid as `extra` cells - the width disagreement is the
subject, it is just not this comparison.

**9.8 Comparability is a property of a field, not of a cell - with one exception.** Measured in the rev7
run: 11 of the 13 cells the gate excluded were excluded because ONE port records `verdict_via: none` while
the other five asked Win32. The rule at the time dropped the whole cell, so five ports' `bytes_on_disk`,
enumerated name, length triple and roundtrip answer disappeared because of a field they had never claimed.
Now:

- `path_form` differs -> the **cell** is excluded. A plain path and a Windows extended-length path (`\\?\`
  prefix) are two questions about the namespace, and no field of them is comparable.
- `verdict_via` differs -> only `os_legality_verdict` is dropped, and only for the ports whose channel is
  the minority. With no majority channel at all the field is dropped for everybody on that cell, which is
  printed as an abstention rather than silently compared against the first value seen.
- An abstaining port is never counted as `NOT-RECORDED`: it recorded, it just asked somewhere else.

Two arms hold this on both sides: `channel-difference-does-not-turn-the-run-red` (a channel difference
alone cannot make the run RED, and cannot erase the other fields) and
`channel-abstention-still-sees-other-fields` (with the legality field abstained, a one-byte conflict on
the same cell is still RED). The field-level rule is not a licence to stop looking.

**9.9 A name is compared by what it could mean, not by one guessed spelling.** Measured in the rev7 run:
the length cells' component is `a` repeated, and **a run of the letter `a` is itself valid hex**. A
canonicaliser with the rule "if it looks like hex, decode it" therefore read the two ports that wrote the
name as text as three bytes of 0xAA - not valid UTF-8 - kept them as raw bytes, and reported the same name
as a disagreement against the four ports that wrote hex. That is the same class of defect as 9.1, found in
the corner the first fix could not see.

So `canonical_case_id`/`canon_name` still produce one token per record (used for printing and for digests),
but **agreement on a name field is set intersection over the forms a value could have**: the literal
string's UTF-8 hex, the hex decoded as UTF-8, the hex decoded as UTF-16LE, and the raw bytes. Two ports
agree about a name when their form sets intersect. When that is what rescued a cell - i.e. the naive
spelling comparison would have called it a disagreement - the gate prints
`NAME-CROSS-FORM-AGREE` naming the ports, so the rescue is visible rather than a silent widening of the
rule. Genuinely different names have disjoint sets and stay RED; two arms prove both edges
(`same-name-two-encodings-agree`, `different-names-still-red`).
