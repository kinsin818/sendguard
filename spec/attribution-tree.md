# SENDGUARD Attribution Tree (locked at S01 freeze)

Decides which layer owns each observed divergence. Read before S03; no
reinterpretation mid-run without a FROZEN.md update.

## 1. The 2x2 variance table (first pass, per cell x api_entry)

Ask two questions and place the cell:

| varies_across_OS | varies_across_lang | verdict |
|---|---|---|
| no  | no  | L1 (environment / filesystem fact) |
| yes | no  | L1 (OS-level policy; same for every language) |
| no  | yes | -> third question (below) |
| yes | yes | -> third question (below) |

## 2. The third question (second pass: isolate language semantics)

Q3: "Can the divergence be eliminated by switching to a DIFFERENT entry of the
SAME language (stdlib)?"
- Yes, same language different entry removes it -> **L2** (stdlib policy of
  that language; still language-visible).
- No, every entry of the language behaves the same -> **L3** (core language
  semantics: counting unit, encoding model, string handling).

If OS also varies AND no same-language entry can remove it ->
**L3_interaction** (L3 interacting with OS policy). Interaction cells are
reported separately and never merged into the main L3 count.

## 3. Cross-reader evidence

cross_reader divergences (builder X / reader Y on the same artifact) fold into
the corresponding cell's main attribution review as THIRD evidence for an
L2/L3 decision. They are not counted as their own layer.

## 4. L3 == 0 consequence

If the main L3 count (interaction cells excluded) is zero, the whitepaper
MUST state verbatim: "six-language necessity is not proven by this matrix",
and the project demotes to a cross-platform delivery cost study.

## 5. Dedup for external divergence count

External divergence counts are deduped by `mechanism_class`
(spec/canonical.md section 10). Example: T01 and T-DOTSP share
`path_preprocessing_policy` and count once externally even if they diverge in
separate cells.

## 6. Hang conflicts

`hang` conflicts are not adjudicated: both recipes run in the same job, both
readings printed as-is (canonical.md section 5).
