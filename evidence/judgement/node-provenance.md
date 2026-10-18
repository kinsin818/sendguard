# S02 — Node port provenance and reproduction report

Author: the maintainer. Date of run: 2026-10-11 (host clock, `date` rc=0). Scope: provenance + reproduction only; nothing in `D:\local-dir` was created, modified, moved, or deleted; nothing was pushed.

Verdict: **DOES_NOT_REPRODUCE (0 of 36 case cells match the committed record; pre-merge stage alone matched 1 of 36).** The committed results are more likely wrong (they are a crashed-run record written by an *earlier, different* code state than the recovered files), not the recovered code — corroborated by the fact that the recovered code independently re-produces, 33/36 cells, the lane's own later results that exist only as *uncommitted* files in the read-only tree (§5a).

---

## 1. Inventory (all commands run 2026-10-11; rc noted)

`git -C D:\local-dir status --porcelain -uall -- impl/node` → 7 lines, all `??` (rc=0).
`git -C D:\local-dir ls-files impl/node` → empty (rc=0). `git log --oneline -- impl/node` in both `D:\local-dir` and the clone → empty (rc=0). The Node implementation was never committed. No stashes, no other branches (`git stash list` empty, `git branch -a` = main + origin/main; rc=0).

Files under `D:\local-dir\impl\node` (`stat -c '%n|%s|%y'`, rc=0):

| file | bytes | mtime (local +0800) | sha256 |
|---|---:|---|---|
| cmp.mjs | 761 | 2026-10-10 22:30:50 | b70eb225814a618a8cdfb53c1f0336ec11cc1eeecf70762f03862a7214d6deec |
| debug.mjs | 857 | 2026-10-10 22:42:33 | 274a56a45835441c434dfb20bd73cff26b8bce5b789b16d55f612e4d0dca9171 |
| main.mjs | 34181 | 2026-10-10 23:50:09 | a24a4b764f09c1a33a2d85c9cdf3af6741dcc650923c5d2b3648a0ee67b21c34 |
| merge-truth.mjs | 8890 | 2026-10-10 23:50:33 | c990e4ce80d5b1f4c794e4a11600bd01f7de804ee5fd4e869e1aff0e5e1c2f4f |
| probe.mjs | 6253 | 2026-10-10 22:28:11 | 9421a9ca9ff9eb34b60d14fc89e002d5ec41b0f35c076e5e0965a7122de07951 |
| py-reader.py | 1238 | 2026-10-10 23:01:13 | 4c07e9519cc291e031bc7dbce22c8edce8d49dbe83c176f81435b2fee8ff5aa1 |
| run-passes.py | 3772 | 2026-10-10 23:34:51 | c17aa60e03d78bbf991a03f1571ae08e9938f3ba38155242104b04ebc5512b8b |

Total: 7 files, 55,952 bytes.

## 2. Byte-for-byte copy + verification

Copied (unmodified) to `D:\work\session-token\evidence\recovered\node-uncommitted\` (`cp -p`, rc=0). `sha256sum -c` of the source hashes against the copies: **all 7 OK, rc=0**. Source and copy hashes are identical (table above). No file was edited.

## 3. What the port does (read, not modified)

- `main.mjs` (v0.2.0-s02, worker W-NODE): dependency-free regex reader of `spec/cases.yaml`; for each trap/ctrl/blind cell it writes a 28-byte payload (`SENDGUARD-CANON-PAYLOAD-2026`) into a one-shot uuid subdir of `%TEMP%\sendguard-run\node\<case_id>\<32hex>` via one of the three pinned entries (`writeFileSync`, `createWriteStream`, `appendFileSync`; primary `writeFileSync`), then self-enumerates the dir (scandir+stat+sha256), tries to invoke `harness/audit.exe` in-process, reads the file back, and emits one schema-shaped JSON per cell into `results/node/windows/` plus a bundle `results/node.windows.<node-version>.json` and `results/node/phantom.windows.json`.
- Cell naming: `case_id` = trap id with a/b/… suffix when a case has multiple `sample_hex_list` entries (T09a, T14a…), `B<blind_id>` for blind samples, `T-CTRL-*` for controls, `T17/T18-{plain,extended}` for length bisection, `<id>@<entry>` for the T-API sweep (`--api`, writes `results/node/api/`, which is absent from the committed record).
- Field parity vs the other committed ports: the node cells carry all `spec/schema.json` required fields (validated: missing = 0, rc=0). vs the Python cells node additionally carries `cross_reader` and `len_triple`, and lacks `name_landed_as`, `name_mutated`, `phantom` (pre-merge), `control_expected`.
- Two out-of-process passes fold independent instruments back in: `run-passes.py` (Go `audit.exe` truth + `py-reader.py` Python cross-reader, each dir-timeboxed) and `merge-truth.mjs` (rewrites cells in place with truth verdicts, recomputes device/phantom, rewrites the bundle).

## 4. Reproduction attempt (all outputs under `D:\work\node-repro\`)

Setup: scratch tree `node-repro\run\{impl/node, spec, evidence/freeze, harness}` built from the recovered copies + the clone's frozen `spec/cases.yaml` (rev2) + clone `evidence/freeze/blind-map.json`, `env-windows.json`; copies hash-verified against source (rc=0). Node resolved executable: `C:\Program Files\nodejs\node.exe` (`where node.exe`, rc=0), v24.15.0 (committed bundle meta: node 22.22.2). `audit.exe` was **not committed anywhere**; the copy used was taken (read-only) from `D:\local-dir\harness\audit.exe`, untracked, 2,896,896 bytes, sha256 dca3681f9920251da45213b50c9d4bd5a1744306df8e14479c4b88e675415ae1.

- `timeout 240 node main.mjs` → **rc=0** (log `node-repro\main-run.log`): "cells written: 36 {trap:22, ctrl:5, len:4, blind:5, … device_findings:0, phantom:0}", 38 files in `run/results/node/windows/`. No hang despite device-named samples: on this host Node's write created a *real* 28-byte `CON.txt` in the run dir (dir listing, names/sizes only — no device-named file content was ever opened).
- `python impl/node/run-passes.py` → **rc=0** (log `passes.log`): "audit pass: 31 dirs -> 31 lines, device entries seen: 7", "pyreader pass: 26 entries -> 26 lines, hangs: 0".
- `timeout 120 node merge-truth.mjs` → **rc=0** (`merge.log`): "merged windows: 36 api: 0 … device_findings:7, phantom:9". Reproduced device findings: T01, T02, T10, T11, T14a/b/c (`truth_is_device=true`, verdict `illegal`), matching the "headline divergence" the code comments and the Python port (T01 verdict `illegal`) claim.
- Per-case comparison vs the 36 committed case cells, excluding volatile fields (`started_at`, `elapsed_ms`, `os_version`, `error_message`, env node-version strings): **identical 0, differs 36, not produced 0, crashed 0.** Before the merge pass, exactly 1 cell (T-CTRL-CANON) matched the committed record byte-for-field; after merge it differs by the added `phantom:false`.
- Bundle: committed `node.windows.22.22.2.json` holds 36 cells (rc=0 on read); reproducible code emits the same 36 cell ids. The aggregate + 4 `_` support files complete the 41 committed files.
- Cleanup: scratch `node-repro\` intentionally retained as evidence; the harness's own run dirs under `%TEMP%\sendguard-run\node` (112 dirs incl. pre-existing ones from the original lane) were left in place per the code's project rule no-delete discipline; not-obtainable: none.

## 5. Where it differs (headline facts, from the diff above)

1. **All 31 committed measurement cells record a crash, not a measurement**: `create_result:"err_at_syscall"`, `error_code:"unknown"`, `error_message:"fs is not defined"`, `os_version:""`, `instrument_red:true`, `sha256_self` = hash of `[]`. The recovered `main.mjs` contains **no bare `fs.` reference at all** (grep: the only hit is the string literal `"fs.scandir+fs.statSync"`; rc=0) — this code cannot emit "fs is not defined". The committed cells were produced by an earlier, broken revision of the harness whose source is now lost (no branches/stashes contain it).
2. **Committed controls are self-failing**: T-CTRL-ASCII and T-CTRL-PARSE carry `control_pass:false` in the record itself; the recovered code passes both on this host (ASCII ok; PARSE correctly `err_at_parse`/`ERR_INVALID_ARG_VALUE`).
3. **The committed truth chain is broken**: `_audit-manifest.json` run_dirs vs `_audit-truth.ndjson` dirs — **0 of 31 overlap**; the truth file contains **0 directory entries in total**; timestamps show truth captured 22:43–22:49, cells generated 23:01 (temp-dir mtimes). `_pyreader-results.ndjson` was never committed, and every committed cell still carries `cross_reader.read_result:"pending"`. `instrument_red:true` proves merge-truth never ran over the committed cells.
4. **T17/T18 committed cells lack `boundary_len` entirely** — a fourth code state again; and the recovered bisection is itself broken (see §6), returning the search bounds 400/4000/8000 as "boundaries".

## 5a. Third face: the original tree's *uncommitted* later results (pre-existing, verified read-only)

`git -C D:\local-dir status --porcelain` (rc=0) shows `M` on all 41 committed result files — these modifications **pre-existed this ticket** (file mtimes 2026-10-10 23:52:24, i.e. the stopped lane re-ran the fixed code in place at local 23:51, after committing nothing). That later working-tree face (`D:\local-dir\results\node\windows\*.json`, started_at 2026-10-10T15:51:05Z) holds sane cells (T01: create ok, `truth_is_device:true`, verdict illegal, instrument_red false). Comparing that face to my independent reproduction: **33 of 36 case cells identical, 3 differ only in `error_code` (wt `EPERM` vs repro `ENOENT` on T03/T15/T-CTRL-ILLEGAL-CHAR — an environment/sandbox difference), plus `phantom.windows.json` differing because the wt run included `--api` cells.** So the recovered code is self-consistent and stable across runs; it simply is not the code state that produced the committed record. Consequence: the *final* Node results exist nowhere in the public record either — only as uncommitted files one `git checkout` away from deletion inside `D:\local-dir`.

## 6. Reasons the recovered code's committed results (and any future results) should not be trusted without care

- `merge-truth.mjs` unconditionally forces `instrument_conflict=false` and `instrument_red=false` on every merged cell (its SHIM_NOTE says conflicts are "not asserted in-sandbox") — a conflict-suppression by design.
- `T-CTRL-CANON` is synthetic: `sha256_truth` is a hardcoded constant (the S00 baseline sha), `control_pass` compares the self-sha against that constant, `bytes_on_disk` is self-declared; no instrument backs it.
- `lenTrial` (T17/T18) builds a long path but then creates `report-2026.txt` in `path.dirname` of an unrelated short dir — the bisection never exercises the length; boundaries equal the search hi value. Do not trust any port's T-LEN cells produced by this code.
- `truthEnum`'s in-process device inference (`is_device` approximated as "empty sha + size 0", since audit.go at this revision "does NOT yet emit an explicit is_device flag") is heuristic; the out-of-process copy of audit.exe *did* emit `is_device` (7 entries), i.e. binary and committed source (`harness/audit.go`) are not the same instrument generation.
- Machine-specific hardcoded paths (`.workbuddy` python, temp dirs, bundle keyed on local node version) and no in-process timeout on create/read — on a host where a plain read of a device name blocks, `main.mjs` would hang (its own comments assume it won't).
- The 41 committed files were folded into commit `986a01a`, a commit whose message describes the **W-GO** worker, not W-NODE — the node results landed under another lane's commit with no node-run narrative.

## 7. Verdict and what would settle it

**DOES_NOT_REPRODUCE.** The recovered code runs cleanly end-to-end (rc=0 for all three passes) but 0/36 cells equal the committed record. The committed results, not the recovered code, are the wrong artifact: they are the output of a superseded broken revision (the "fs is not defined" ReferenceError cannot come from the recovered files), generated before the truth instrument ever worked, with failing controls and a truth chain that matches zero run dirs. The recovered code is corroborated instead by §5a — it independently re-produces the lane's own later, uncommitted 23:51 results at 33/36 cells. Evidence that would settle it: (a) the lost earlier `main.mjs` revision — not obtainable from git here (no branch/stash; `not-obtainable`), so the claim rests on the grep above; (b) a canonical re-run of the recovered 3-pass pipeline on a Node 22.22.2 Windows runner with `audit.exe` built from the committed `harness/audit.go`, then cross-checked against the Python/Go committed cells (the repro already agrees with Python's T01 `illegal` verdict and finds device cells T01/T02/T10/T11 + T14a/b/c); (c) re-running `run-passes.py` + `merge-truth.mjs` over fresh manifests so truth dirs match cell dirs, which the committed record never achieved; (d) the `EPERM`-vs-`ENOENT` trio (T03/T15/T-CTRL-ILLEGAL-CHAR) needs a clean non-sandboxed runner to say which error identity is authoritative.
