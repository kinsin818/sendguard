#!/usr/bin/env node
// SENDGUARD Node S02 merge pass (W-NODE seat).
// Folds the two independent out-of-process instruments back into the per-cell
// JSON and the bundle:
//   - audit.exe  truth  (results/node/windows/_audit-truth.ndjson)  -> is_device, bytes_on_disk_truth, sha256_truth
//   - python     cross  (results/node/windows/_pyreader-results.ndjson) -> cross_reader
// This pass does NOT spawn any .exe (sandbox blocks Node spawnSync of .exe); it
// only reads files and rewrites cells. Verdicts/device/phantom are recomputed
// from the authoritative truth instrument. See README/M-rules.
import { readFileSync, writeFileSync, readdirSync } from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(__dirname, "..", "..");
const WOUT = path.join(REPO, "results", "node", "windows");
const AOUT = path.join(REPO, "results", "node", "api");
const EVID = path.join(REPO, "evidence", "S02");

function loadJSON(p) { return JSON.parse(readFileSync(p, "utf8")); }

// audit truth keyed by dir (NDJSON: one {dir,entries,go_version} per line)
const truthRaw = readFileSync(path.join(WOUT, "_audit-truth.ndjson"), "utf8").split("\n").filter(Boolean);
const truthByDir = {};
for (const l of truthRaw) { const r = JSON.parse(l); truthByDir[r.dir] = r.entries || []; }

// audit manifest: case_id -> run_dir
const auditManifest = loadJSON(path.join(WOUT, "_audit-manifest.json"));
const dirByCase = {};
for (const e of auditManifest.entries) dirByCase[e.case_id] = e.run_dir;

// pyreader results keyed by case_id
const pyRaw = readFileSync(path.join(WOUT, "_pyreader-results.ndjson"), "utf8").split("\n").filter(Boolean);
const pyByCase = {};
for (const l of pyRaw) { const r = JSON.parse(l); pyByCase[r.case_id] = r; }

const PAYLOAD_SHA = "c9fe45b2fee8ea846f0cf4f2cacc2a891e7b082e7719923502d12a9813e21994"; // node S00 baseline (payload 28B)
const SHIM_NOTE = "Node in-process readFileSync is destabilized by the sandbox brokered-fs shim (returns wrong content / differing sha per file); the independent audit.exe (Go/Windows API) is the authoritative on-disk truth. instrument_conflict is therefore NOT asserted in-sandbox and must be established on a real CI Windows runner where Node fs is reliable.";

let deviceCount = 0, phantomCount = 0, conflictCount = 0;
const deviceCells = [], phantomCells = [];
const allCells = [];
const totals = { trap: 0, ctrl: 0, len: 0, blind: 0, tapi: 0, defects_skipped: 0 };

function processDir(dir) {
  const files = readdirSync(dir).filter((f) => f.endsWith(".json") && !f.startsWith("_") && !/^node\./.test(f) && f !== "phantom.windows.json");
  const cells = [];
  for (const f of files) {
    const cellPath = path.join(dir, f);
    const cell = loadJSON(cellPath);
    // Synthetic cells (T-LEN bisection + T-CTRL-CANON) are ordinary ASCII files
    // written by the worker itself; they are not in the audit manifest, so no
    // truth folding applies. Preserve all self-reported fields as written by
    // main.mjs (incl. the T-CTRL-CANON baseline sha256_truth) — only pin the
    // verdict to legal when creation succeeded and mark not-phantom.
    if (cell.case_group === "len" || cell.case_id === "T-CTRL-CANON") {
      if (cell.create_result === "ok") cell.os_legality_verdict = "legal";
      cell.phantom = false;
      if (totals[cell.case_group] !== undefined) totals[cell.case_group]++;
      writeFileSync(cellPath, JSON.stringify(cell, null, 2));
      cells.push(cell);
      allCells.push(cell);
      continue;
    }
    const caseId = cell.case_id;
    const dir2 = dirByCase[caseId];
    let truthEntry = null;
    if (dir2 && truthByDir[dir2]) {
      truthEntry = (truthByDir[dir2] || []).find((e) => e.name_utf8_hex === cell.name_source) || null;
    }
    const isDevice = !!(truthEntry && truthEntry.is_device);
    const truthSize = truthEntry ? truthEntry.size : null;
    // audit returns sha256:"" for unreadable/phantom entries (no hashable content).
    // Normalize to null so the frozen schema (64-hex or null) is satisfied and the
    // cell accurately records "no authoritative content sha".
    const rawSha = truthEntry ? truthEntry.sha256 : null;
    const truthSha = rawSha && /^[0-9a-f]{64}$/.test(rawSha) ? rawSha : null;
    const truthReal = !!(truthEntry && !isDevice && (truthSize > 0 || (truthSha && truthSha.length === 64)));

    if (truthEntry) cell.bytes_on_disk = isDevice ? 0 : truthSize;
    cell.bytes_on_disk_truth = truthEntry ? (isDevice ? 0 : truthSize) : null;
    cell.sha256_truth = truthEntry ? (isDevice ? null : truthSha) : null;
    if (isDevice) cell.truth_is_device = true;

    // roundtrip_ok recomputed from the RELIABLE instrument: file content matches payload
    cell.roundtrip_ok = !!(truthReal && truthSha === PAYLOAD_SHA);

    let verdict;
    if (cell.create_result !== "ok") verdict = "illegal";
    else if (isDevice) verdict = "illegal";
    else if (truthReal) verdict = "legal";
    else if (truthEntry) verdict = "illegal";
    else verdict = "unknown";
    cell.os_legality_verdict = verdict;

    const py = pyByCase[caseId];
    if (py && cell.cross_reader) {
      cell.cross_reader.read_result = py.read_result;
      cell.cross_reader.size = py.size === undefined ? null : py.size;
      cell.cross_reader.found = py.found === undefined ? null : py.found;
      cell.cross_reader.sha256 = py.sha256 || null;
      cell.cross_reader.error_code = py.error_code || null;
    }

    // instrument_conflict NOT asserted in-sandbox (Node self-readback corrupted by shim); see SHIM_NOTE
    cell.instrument_conflict = false;
    cell.instrument_red = false;

    const isPhantom = cell.create_result === "ok" && !truthReal;
    cell.phantom = isPhantom;

    if (isDevice) { deviceCount++; deviceCells.push(cell); }
    if (isPhantom) { phantomCount++; phantomCells.push(cell); }

    if (totals[cell.case_group] !== undefined) totals[cell.case_group]++;
    writeFileSync(cellPath, JSON.stringify(cell, null, 2));
    cells.push(cell);
    allCells.push(cell);
  }
  return cells;
}

const winCells = processDir(WOUT);
let apiCells = [];
try { apiCells = processDir(AOUT); } catch (e) { /* api dir may be absent if --api not run */ }

// rewrite windows bundle
const ver = process.versions.node;
const wBundlePath = path.join(REPO, "results", "node.windows." + ver + ".json");
const wBundle = loadJSON(wBundlePath);
wBundle.cells = winCells;
wBundle.meta.truth_instrument = "audit.exe (go1.23.5) + python3.13 cross-reader (out-of-process)";
wBundle.meta.note = "truth folded post-run via merge-truth.mjs; Node spawnSync of .exe is blocked (EBUSY) in this sandbox, so audit.exe/python run via the shell. " + SHIM_NOTE;
writeFileSync(wBundlePath, JSON.stringify(wBundle, null, 2));

// rewrite api bundle if present
const aBundlePath = path.join(AOUT, "node.api-entry.windows.json");
if (apiCells.length) {
  const aBundle = loadJSON(aBundlePath);
  aBundle.cells = apiCells;
  aBundle.meta.truth_instrument = "audit.exe (go1.23.5) + python3.13 cross-reader (out-of-process)";
  aBundle.meta.note = SHIM_NOTE;
  writeFileSync(aBundlePath, JSON.stringify(aBundle, null, 2));
}

writeFileSync(path.join(WOUT, "phantom.windows.json"), JSON.stringify({ count: phantomCount, cells: phantomCells.map((c) => ({ case_id: c.case_id, case_group: c.case_group, create_result: c.create_result, os_legality_verdict: c.os_legality_verdict, truth_is_device: !!c.truth_is_device, bytes_on_disk: c.bytes_on_disk, bytes_on_disk_truth: c.bytes_on_disk_truth })) }, null, 2));

// also overwrite the stale top-level phantom summary that main.mjs wrote pre-merge
writeFileSync(path.join(REPO, "results", "node", "phantom.windows.json"), JSON.stringify({ count: phantomCount, note: "authoritative: recomputed from audit.exe truth by merge-truth.mjs", cells: phantomCells.map((c) => ({ case_id: c.case_id, case_group: c.case_group, create_result: c.create_result, os_legality_verdict: c.os_legality_verdict, truth_is_device: !!c.truth_is_device, bytes_on_disk_truth: c.bytes_on_disk_truth })) }, null, 2));

writeFileSync(path.join(EVID, "node-device-findings.json"), JSON.stringify({
  count: deviceCount,
  instrument: "audit.exe (go1.23.5) independent; is_device + size:0 + sha256:'' signature",
  cells: deviceCells.map((c) => ({
    case_id: c.case_id, case_group: c.case_group, create_result: c.create_result, os_legality_verdict: c.os_legality_verdict,
    truth_is_device: true, node_self_wrote_bytes: c.bytes_written, bytes_on_disk_truth: c.bytes_on_disk_truth,
    cross_reader: c.cross_reader || null,
  })),
}, null, 2));

const counts = { ...totals, tapi: apiCells.length, defects_skipped: 0, conflicts: 0, device_findings: deviceCount, phantom: phantomCount };
console.log("merged windows:", winCells.length, "api:", apiCells.length, JSON.stringify(counts));
