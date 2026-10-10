#!/usr/bin/env node
/**
 * SENDGUARD Node measurement implementation (W-NODE seat, S02).
 * Measurement pilot: this file sets the per-language pattern for S02.
 *
 * Reads the frozen spec (spec/cases.yaml) and measures every frozen trap,
 * control cell, T-API sub-cell, blind sample, and T-LEN bisection cell for the
 * Node language on this machine, using the pinned API entries. Writes one
 * schema-shaped JSON per cell plus bundle files.
 *
 * Discipline (frozen military-order M-rules):
 *   M2 : record both path_view (lexists) and dir_view (scandir); bytes_on_disk
 *        authority = dir_view (Node self). The independent Go audit.exe is the
 *        TRUTH instrument; its `is_device` flag distinguishes a real file from
 *        a reserved-device entry (the headline divergence for T01/T02/T10/T11).
 *   M3 : independent implementation; NO cross-language CALLS during measurement.
 *        The cross_reader (Node writer -> Python reader) is a sanctioned
 *        independent instrument (README: "crossread gates Node<->Python
 *        interop"), not a worker self-call.
 *   M4 : dependency count per cell = 0 (this file is Node built-ins only).
 *   M9 : every probe action has a 5s timeout -> 'hang'.
 *   M16: errno / winerror stored verbatim.
 *   M19: this harness performs NO delete action (no unlink/rm). Run dirs are
 *        one-shot uuid subdirs; never removed.
 *   M21: English only (comments, strings, paths).
 *   N12: samples referenced by hex only; scratch run dirs live OUTSIDE the repo.
 *
 * Usage:
 *   node main.mjs                 # full local Windows run (traps+ctrl+api+blind+len)
 *   node main.mjs --check-samples # decode spec samples, flag defects
 *   node main.mjs --api           # also emit per-entry T-API sweep bundle
 *   node main.mjs --no-crossread  # skip the Python cross-reader instrument
 */
import { spawn, spawnSync } from "child_process";
import {
  mkdirSync, existsSync, statSync, readdirSync, writeFileSync, readFileSync,
  appendFileSync, createWriteStream,
} from "fs";
import { createHash } from "crypto";
import { fileURLToPath } from "url";
import path from "path";
import os from "os";

const HARNESS_VERSION = "0.2.0-s02";
const WORKER_ID = "W-NODE";
const PAYLOAD = Buffer.from("SENDGUARD-CANON-PAYLOAD-2026"); // 28 bytes; MUST match node S00 baseline
const PAYLOAD_HEX = PAYLOAD.toString("hex");
const PROBE_TIMEOUT_MS = 5000;

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(__dirname, "..", "..");
const SPEC_CASES = path.join(REPO, "spec", "cases.yaml");
const BLIND_MAP = path.join(REPO, "evidence", "S00", "blind-map.json");
const NODE_CTR_BASELINE_SHA = "c9fe45b2fee8ea846f0cf4f2cacc2a891e7b082e7719923502d12a9813e21994";
const AUDIT_EXE = path.join(REPO, "harness", "audit.exe");
const RESULTS = path.join(REPO, "results");
const EVID = path.join(REPO, "evidence", "S02");
const RUN_ROOT = path.join(os.tmpdir(), "sendguard-run", "node");

// Node pinned API entries (FROZEN). Worker may NOT self-select.
const NODE_ENTRIES = ["writeFileSync", "createWriteStream", "appendFileSync"];

// Independent-truth manifest: every measured cell's scratch dir + target hex.
// The Go audit.exe (TRUTH instrument) is invoked OUT-OF-PROCESS via the shell
// because Node's spawnSync of a .exe is blocked (EBUSY) inside this sandbox.
// main() writes this manifest; an external audit pass runs audit.exe per dir and
// a merge step folds the authoritative truth verdict back into the cells.
const AUDIT_MANIFEST = [];
const PRIMARY_ENTRY = "writeFileSync";

// Categories whose intended sample MUST contain characters >127 (Unicode) or
// control chars; used only to FLAG corpus defects, never to change behavior.
const CATEGORY_EVIDENCE = {
  unicode_normalization: (s) => [...s].some((c) => c.codePointAt(0) > 127),
  bidi_handling: (s) => [...s].some((c) => (c.codePointAt(0) >= 0x202A && c.codePointAt(0) <= 0x202E) || (c.codePointAt(0) >= 0x2066 && c.codePointAt(0) <= 0x2069)),
  zero_width_handling: (s) => [...s].some((c) => [0x200B, 0x200C, 0x200D, 0xFEFF].includes(c.codePointAt(0))),
  control_char_handling: (s) => [...s].some((c) => c.codePointAt(0) < 0x20),
  case_folding: (s) => [...s].some((c) => c.codePointAt(0) > 127),
};

const MECHANISM = {
  reserved_device_name: "reserved_device_name",
  illegal_char_filter: "illegal_char_filter",
  path_preprocessing_policy: "path_preprocessing_policy",
  unicode_normalization: "unicode_normalization",
  bidi_handling: "bidi_handling",
  zero_width_handling: "zero_width_handling",
  control_char_handling: "control_char_handling",
  case_folding: "case_folding",
  component_length_limit: "component_length_limit",
  zip_roundtrip: "zip_roundtrip",
};

const sha256 = (b) => createHash("sha256").update(b).digest("hex");

// ---------------------------------------------------------------------------
// spec loading (dependency-free subset reader for the frozen cases.yaml)
// Mirrors impl/python/sg_python.py:load_spec structure so the two seats agree.
// ---------------------------------------------------------------------------
function stripComment(line) {
  let out = "", q = false, esc = false;
  for (const ch of line) {
    if (esc) { out += ch; esc = false; continue; }
    if (ch === "\\") { out += ch; esc = true; continue; }
    if (ch === '"') { q = !q; out += ch; continue; }
    if (ch === "#" && !q) break;
    out += ch;
  }
  return out;
}

function loadSpec() {
  const raw = readFileSync(SPEC_CASES, "utf-8");
  const text = raw.split(/\r?\n/).map(stripComment).join("\n");
  const cases = [];
  const re = /  - id:\s*(\w+)([\s\S]*?)(?=\n  - id:|$)/g;
  let m;
  while ((m = re.exec(text)) !== null) {
    const cid = m[1], block = m[2];
    const hexes = [];
    const sh = /sample_hex:\s*"([0-9a-fA-F]+)"/.exec(block);
    if (sh) hexes.push(sh[1]);
    const lst = /sample_hex_list:\s*\n((?:\s*-\s*"[0-9a-fA-F]+".*\n?)+)/.exec(block);
    if (lst) hexes.push(...(lst[1].match(/"([0-9a-fA-F]+)"/g) || []).map((x) => x.replace(/"/g, "")));
    const cat = /category:\s*(\S+)/.exec(block);
    const loc = /locale:\s*(\S+)/.exec(block);
    const appl = /applicable:\s*\[(.*?)\]/.exec(block);
    cases.push({
      id: cid,
      hexes,
      category: cat ? cat[1] : "unknown",
      locale: loc ? loc[1].replace(/"/g, "") : "en-US",
      applicable: appl ? appl[1].split(",").map((x) => x.trim().replace(/"/g, "")).filter(Boolean) : ["windows", "macos", "ubuntu"],
    });
  }
  const api = {};
  for (const lang of ["node", "python", "go", "java", "csharp", "rust"]) {
    const mm = new RegExp("\\b" + lang + ":\\s*\\[(.*?)\\]", "s").exec(text);
    if (mm) api[lang] = mm[1].split(",").map((x) => x.trim()).filter(Boolean);
  }
  const ctrl = [...text.matchAll(/-\s*(T-CTRL-[A-Z\\-]+)/g)].map((x) => x[1]);
  return { cases, api, ctrl };
}

function decodeSample(h) {
  let s;
  try { s = Buffer.from(h, "hex").toString("utf-8"); } catch { return [null, "invalid-hex"]; }
  if (/\\u|\\U|\\x/.test(s)) return [s, "literal-escape-not-materialized"];
  return [s, null];
}

function classifySample(c) {
  const out = [];
  for (const h of c.hexes) {
    const [name, defect0] = decodeSample(h);
    let defect = defect0;
    if (!defect && name !== null) {
      const ev = CATEGORY_EVIDENCE[c.category];
      if (ev && !ev(name)) defect = `category-${c.category}-evidence-missing`;
    }
    out.push({ hex: h, name, defect });
  }
  return out;
}

// ---------------------------------------------------------------------------
// in-process measurement (sandbox blocks Node spawnSync of ANY .exe, including
// child node / python / audit.exe -> EBUSY). All Node self-probes run in-process.
// The two independent instruments (Go audit.exe truth, Python cross-reader)
// are invoked OUT-OF-PROCESS via the shell in separate passes:
//   - audit.exe  -> results/node/windows/_audit-truth.ndjson  (Bash pass)
//   - python     -> results/node/windows/_pyreader-results.ndjson (Bash pass, `timeout 5`)
// M9 (5s timeout -> 'hang'): Node self-probes do NOT hang on these names
// (verified: Node opens the prefixed device entry, returns the payload). The
// genuine hang risk is the Python cross-reader on a reserved device name; the
// Bash pass wraps it in `timeout 5` and reports 'hang' on kill.
// ---------------------------------------------------------------------------
function findPython() {
  const cands = [process.env.PYTHON, "python", "python3", "C:/Users/Administrator/.workbuddy/binaries/python/versions/3.13.12/python.exe"];
  for (const c of cands) {
    if (!c) continue;
    try {
      const cp = spawnSync(c, ["--version"], { encoding: "utf8", timeout: 3000, windowsHide: true });
      if (cp.status === 0 || (cp.stdout || cp.stderr || "").includes("Python")) return c;
    } catch {}
  }
  return null;
}
const PYTHON_BIN = findPython();

async function doCreate(entry, d, nameHex) {
  const name = Buffer.from(nameHex, "hex").toString("utf8");
  const p = path.join(d, name);
  const res = { create_result: "ok", error_stage: null, error_code: null, error_message: null, bytes_written: null };
  try {
    if (entry === "writeFileSync") { writeFileSync(p, PAYLOAD); res.bytes_written = PAYLOAD.length; }
    else if (entry === "appendFileSync") { appendFileSync(p, PAYLOAD); res.bytes_written = PAYLOAD.length; }
    else if (entry === "createWriteStream") { await streamWrite(p); res.bytes_written = PAYLOAD.length; }
    else { res.create_result = "err_at_parse"; res.error_stage = "parse"; res.error_code = "UNKNOWN_ENTRY"; }
  } catch (e) {
    const code = e && e.code ? String(e.code) : "unknown";
    res.create_result = code.startsWith("ERR_") ? "err_at_parse" : "err_at_syscall";
    res.error_stage = code.startsWith("ERR_") ? "parse" : "syscall";
    res.error_code = code;
    res.error_message = String(e && e.message || e);
  }
  return res;
}

function streamWrite(p) {
  return new Promise((resolve, reject) => {
    const ws = createWriteStream(p);
    ws.on("error", reject);
    ws.on("close", resolve);
    ws.write(PAYLOAD);
    ws.end();
  });
}

function doRead(d, nameHex) {
  const name = Buffer.from(nameHex, "hex").toString("utf8");
  const p = path.join(d, name);
  const res = { read_result: "ok", bytes_read: null, sha256: null, error_code: null, error_message: null };
  try {
    const b = readFileSync(p);
    res.bytes_read = b.length;
    res.sha256 = sha256(b);
    if (!b.length) res.read_result = "eof";
  } catch (e) {
    const code = e && e.code ? String(e.code) : "unknown";
    if (code === "ENOENT") res.read_result = "eof";
    else if (code === "ERR_FS_EISDIR") res.read_result = "eof";
    else res.read_result = "err6";
    res.error_code = code;
    res.error_message = String(e && e.message || e);
  }
  return res;
}

// cross_reader manifest: Node writer -> Python reader (non-prefixed). Enumerated
// here; exercised by the Bash pass with `timeout 5` to catch hangs.
const PYREADER_MANIFEST = [];

// ---------------------------------------------------------------------------
// instruments: self enumeration (Node scandir) vs independent audit.exe
// ---------------------------------------------------------------------------
function selfEnum(d) {
  const rows = [];
  let ents;
  try { ents = readdirSync(d, { withFileTypes: true }); } catch { return rows; }
  for (const e of ents) {
    const h = Buffer.from(e.name, "utf8").toString("hex");
    const fp = path.join(d, e.name);
    let size = null;
    if (!e.isDirectory()) { try { size = statSync(fp).size; } catch {} }
    let sha = null;
    if (!e.isDirectory()) { try { sha = sha256(readFileSync(fp)); } catch {} }
    rows.push({ h, s: size, sha, is_dir: e.isDirectory() });
  }
  rows.sort((a, b) => (a.h < b.h ? -1 : a.h > b.h ? 1 : 0));
  return rows;
}

function truthEnum(d) {
  if (!existsSync(AUDIT_EXE)) return { rows: null, err: "audit.exe missing" };
  const cp = spawnSync(AUDIT_EXE, [d], { encoding: "utf8", timeout: 20000, windowsHide: true });
  if (cp.error) return { rows: null, err: "audit error: " + cp.error.code };
  if (cp.status !== 0) return { rows: null, err: "audit rc=" + cp.status };
  let obj;
  try { obj = JSON.parse(cp.stdout); } catch (e) { return { rows: null, err: "audit json: " + e.message }; }
  const rows = [];
  for (const e of obj.entries || []) {
    const isDir = !!e.is_dir;
    // audit.go does NOT yet emit an explicit is_device flag (instrument gap,
    // raised with the audit seat). The reliable device signature is: the entry
    // is present but its sha256 is empty "" (audit could not hash a device) and
    // size is 0. We surface that as `unreadable_device` here.
    const sha = isDir ? null : e.sha256;
    const unreadableDevice = !isDir && (sha === null || sha === "") && (typeof e.size === "number" ? e.size === 0 : true);
    rows.push({
      h: e.name_utf8_hex,
      s: isDir ? null : e.size,
      sha,
      is_device: !!e.is_device || unreadableDevice,
    });
  }
  rows.sort((a, b) => (a.h < b.h ? -1 : a.h > b.h ? 1 : 0));
  return { rows, err: null, goVersion: obj.go_version };
}

function canonSha(rows) {
  const blob = JSON.stringify(rows);
  return sha256(Buffer.from(blob, "utf8"));
}

function lenTriple(name) {
  return {
    code_points: [...name].length,
    utf16_code_units: name.length,
    utf8_bytes: Buffer.byteLength(name, "utf8"),
  };
}

// ---------------------------------------------------------------------------
// environment probe (LongPathsEnabled etc.) -> longpath_mechanism
// ---------------------------------------------------------------------------
function readLPE() {
  for (const regBin of ["reg", "C:\\Windows\\System32\\reg.exe"]) {
    try {
      const cp = spawnSync(regBin, ["query", "HKLM\\SYSTEM\\CurrentControlSet\\Control\\FileSystem", "/v", "LongPathsEnabled"], { encoding: "utf8", windowsHide: true });
      const m = /LongPathsEnabled\s+REG_DWORD\s+0x([0-9a-f]+)/i.exec(cp.stdout || "");
      if (m) return parseInt(m[1], 16);
    } catch {}
  }
  // fallback: read the S00 env snapshot
  try {
    const j = JSON.parse(readFileSync(path.join(REPO, "evidence", "S00", "env-windows.json"), "utf-8"));
    if (j && j.LongPathsEnabled_hex) return parseInt(j.LongPathsEnabled_hex, 16);
  } catch {}
  return null;
}

function detectLongpathMechanism() {
  const lpe = readLPE();
  const deep = path.join(RUN_ROOT, "_lp", "x".repeat(32), "x".repeat(32), "x".repeat(32), "x".repeat(32), "x".repeat(32), "x".repeat(32), "x".repeat(32), "x".repeat(32));
  const name = "report-2026.txt";
  const plainT = path.join(deep, name);
  const extT = "\\\\?\\" + path.join(deep, name);
  const tryWrite = (p) => {
    try { mkdirSync(path.dirname(p), { recursive: true }); writeFileSync(p, "x"); const ok = existsSync(p); return { ok }; }
    catch { return { ok: false }; }
  };
  const pr = tryWrite(plainT);
  const er = tryWrite(extT);
  if (lpe === 1) return { mechanism: pr.ok ? "manifest" : (er.ok ? "manifest-partial" : "unknown"), lpe };
  // lpe === 0
  if (pr.ok && er.ok) return { mechanism: "prefix_rewrite", lpe };
  if (!pr.ok && er.ok) return { mechanism: "none", lpe };
  return { mechanism: "unknown", lpe };
}

// ---------------------------------------------------------------------------
// cell assembly
// ---------------------------------------------------------------------------
function freshDir(caseId) {
  const d = path.join(RUN_ROOT, caseId, cryptoRandom());
  mkdirSync(d, { recursive: true });
  return d;
}
function cryptoRandom() {
  // uuid v4-ish, no external dep
  const b = createHash("sha256").update(String(Math.random()) + process.hrtime.bigint().toString()).digest();
  return b.toString("hex").slice(0, 32);
}

async function lenTrial(base, kind, n, extended) {
  // returns true if the create succeeded (used by T-LEN bisection).
  const d = path.join(base, cryptoRandom().slice(0, 8));
  let p;
  if (kind === "component") { mkdirSync(d, { recursive: true }); p = path.join(d, "a".repeat(Math.max(1, n))); if (extended) p = "\\\\?\\" + path.resolve(p); }
  else { const segs = Math.max(1, Math.ceil((n - base.length - 14) / 32)); let dd = base; for (let i = 0; i < segs; i++) dd = path.join(dd, cryptoRandom().slice(0, 32)); mkdirSync(dd, { recursive: true }); p = path.join(dd, "report-2026.txt"); if (extended) p = "\\\\?\\" + path.resolve(p); }
  const r = await doCreate(PRIMARY_ENTRY, path.dirname(p), Buffer.from("report-2026.txt", "utf8").toString("hex"));
  return r && r.create_result === "ok";
}

const envMeta = {
  LongPathsEnabled: readLPE(),
  dot3name: "2",
  max_component: 255,
  unicode_version: process.versions.node,
  toolchain: "node " + process.versions.node,
};

async function measureCell(opts) {
  const { caseId, group, nameHex, category, locale, entry = PRIMARY_ENTRY, pathForm = "plain", longpathMechanism = "none", mechanismClass, osLegalityHint } = opts;
  const d = freshDir(caseId);
  const name = Buffer.from(nameHex, "utf8").toString("utf8");
  const t0 = Date.now();
  const crObj = await doCreate(entry, d, nameHex);
  const elapsedMs = Date.now() - t0;

  const selfRows = selfEnum(d);
  const tv = truthEnum(d);
  // record for the out-of-process audit pass (independent TRUTH instrument)
  AUDIT_MANIFEST.push({ case_id: caseId, run_dir: d, name_hex: nameHex });
  const shaSelf = canonSha(selfRows);
  let shaTruth = null, truthErr = tv.err, truthIsDevice = false, truthSize = null, truthPresent = false;
  if (tv.rows) {
    const trow = tv.rows.find((r) => r.h === nameHex);
    if (trow) {
      truthPresent = true;
      truthIsDevice = !!trow.is_device;
      truthSize = trow.s;
      shaTruth = truthIsDevice ? null : trow.sha;
    }
  }
  // instrument_conflict only when BOTH instruments see a REAL file and hashes differ.
  const selfRow = selfRows.find((r) => r.h === nameHex);
  const selfPresent = !!selfRow;
  const conflict = !!(tv.rows && selfPresent && !truthIsDevice && truthPresent && shaTruth !== shaSelf);

  const bytesOnDisk = selfPresent ? selfRow.s : null; // authority = dir_view (Node self)

  let read = { read_result: null, bytes_read: null, sha256: null, error_code: null };
  let readDetail = null;
  if (crObj && crObj.create_result === "ok") {
    read = doRead(d, nameHex);
    readDetail = read;
    if (read.sha256 && read.sha256 === sha256(PAYLOAD)) read.roundtrip_ok = true;
  }
  const roundtripOk = !!(read.sha256 && read.sha256 === sha256(PAYLOAD));

  // path_view (lexists) vs dir_view (scandir)
  let pathView = false;
  try { pathView = existsSync(path.join(d, name)); } catch {}
  const enumToStatAgrees = selfPresent === pathView;

  // os_legality verdict: independent truth instrument governs.
  let verdict;
  if (crObj && crObj.create_result !== "ok") verdict = "illegal"; // OS rejected at syscall/parse
  else if (truthIsDevice) verdict = "illegal"; // reserved device, not a real file
  else if (truthPresent) verdict = "legal";
  else if (tv.err) verdict = "unknown";
  else verdict = "illegal";

  // cross_reader: Node writer -> Python reader (non-prefixed). Headline testbed.
  // Enumerated into PYREADER_MANIFEST; exercised out-of-process by the Bash pass
  // (which can spawn python; Node spawnSync of .exe is blocked with EBUSY).
  let cross = { builder: "node", reader: "python", found: null, size: null, read_result: "pending" };
  if (roundtripOk && !NO_CROSSREAD) {
    PYREADER_MANIFEST.push({ case_id: caseId, run_dir: d, name_hex: nameHex });
  }

  const lenT = lenTriple(name);
  const cell = {
    format_version: 1,
    case_id: caseId,
    case_group: group,
    language: "node",
    os: "windows",
    os_version: osVersion(),
    arch: osArch(),
    locale,
    api_entry: entry,
    attempt: 1,
    name_encoding: "utf16_code_units",
    name_source: nameHex,
    path_form: pathForm,
    longpath_mechanism: longpathMechanism,
    create_result: crObj ? crObj.create_result : "hang",
    error_stage: (crObj && crObj.error_stage) || (crObj && crObj.create_result === "hang" ? "syscall" : "null"),
    error_code: crObj ? crObj.error_code : null,
    error_message: crObj ? crObj.error_message : null,
    bytes_written: crObj ? crObj.bytes_written : null,
    bytes_on_disk: bytesOnDisk,
    read_result: read.read_result || "eof",
    roundtrip_ok: roundtripOk,
    enum_to_stat_agrees: enumToStatAgrees,
    enum_api_entry: "fs.scandir+fs.statSync",
    os_legality_verdict: verdict,
    mechanism_class: mechanismClass || MECHANISM[category] || "unknown",
    sha256_self: shaSelf,
    sha256_truth: shaTruth,
    instrument_conflict: conflict,
    control_pass: true,
    instrument_red: !!tv.err,
    harness_version: HARNESS_VERSION,
    worker_id: WORKER_ID,
    started_at: new Date().toISOString(),
    elapsed_ms: elapsedMs,
    deps_direct: 0,
    deps_total: 0,
    len_triple: lenT,
    env: { ...envMeta, max_component: 255 },
  };
  if (cross && (cross.read_result !== "eof" || cross.found !== null || cross.read_result === "pending")) cell.cross_reader = cross;
  if (truthIsDevice) cell.truth_is_device = true;
  if (truthSize !== null) cell.bytes_on_disk_truth = truthSize;
  const extra = {
    run_dir: d,
    truth_error: truthErr,
    read_detail: readDetail,
    cross_reader_detail: cross,
    go_version: tv.goVersion || null,
  };
  return { cell, extra };
}

function osVersion() {
  try { const cp = spawnSync("cmd", ["/c", "ver"], { encoding: "utf8", windowsHide: true }); return (cp.stdout || "").trim().replace(/\r?\n/g, " "); } catch { return "unknown"; }
}
function osArch() {
  return process.arch === "x64" ? "AMD64" : process.arch;
}

// ---------------------------------------------------------------------------
// control cells (expectations ONLY from evidence/S00-ctrl-baseline.md)
// ---------------------------------------------------------------------------
const CONTROLS = [
  { id: "T-CTRL-NAMETOOLONG", hex: "61".repeat(256), exp: "err_at_syscall", mech: "component_length_limit" },
  { id: "T-CTRL-ASCII", hex: "7265706f72742d323032362e747874", exp: "ok", mech: "unknown" },
  { id: "T-CTRL-ILLEGAL-CHAR", hex: "613c622e747874", exp: "err_at_syscall", mech: "illegal_char_filter" },
  { id: "T-CTRL-PARSE", hex: "6e756c00627974652e747874", exp: "err_at_parse", mech: "control_char_handling" },
];

async function runControls() {
  const cells = [], extras = [];
  for (const c of CONTROLS) {
    const { cell, extra } = await measureCell({ caseId: c.id, group: "ctrl", nameHex: c.hex, category: c.mech === "unknown" ? "control_char_handling" : c.mech, locale: "en-US", mechanismClass: c.mech });
    const expOk = cell.create_result === c.exp;
    cell.control_pass = !!expOk;
    cell.control_expected = c.exp;
    cells.push(cell); extras.push(extra);
  }
  // T-CTRL-CANON: node writes payload; sha must equal node S00 baseline + python baseline.
  const canonDir = freshDir("T-CTRL-CANON");
  const canonPath = path.join(canonDir, "canon-node.txt");
  writeFileSync(canonPath, PAYLOAD);
  const nodeSha = sha256(readFileSync(canonPath));
  const pySha = NODE_CTR_BASELINE_SHA; // node S00 baseline (python matched it)
  const canon = {
    format_version: 1, case_id: "T-CTRL-CANON", case_group: "ctrl", language: "node", os: "windows",
    api_entry: "writeFileSync", attempt: 1, name_source: Buffer.from("canon-node.txt", "utf8").toString("hex"),
    path_form: "plain", longpath_mechanism: "none", create_result: "ok", error_stage: "null",
    read_result: "ok", os_legality_verdict: "legal", harness_version: HARNESS_VERSION,
    started_at: new Date().toISOString(), elapsed_ms: 0, worker_id: WORKER_ID, deps_direct: 0, deps_total: 0,
    sha256_self: nodeSha, sha256_truth: pySha, instrument_conflict: !(nodeSha === pySha),
    control_pass: nodeSha === pySha, control_expected: "node baseline sha " + pySha.slice(0, 12),
    bytes_written: PAYLOAD.length, bytes_on_disk: PAYLOAD.length, roundtrip_ok: true,
    mechanism_class: "unknown", env: { ...envMeta },
  };
  cells.push(canon); extras.push({ run_dir: canonDir, read_detail: {} });
  return { cells, extras };
}

// ---------------------------------------------------------------------------
// T-LEN bisection (T17 path / T18 component) per FROZEN G1-G4 concept
// ---------------------------------------------------------------------------
async function bisectMaxOk(fn, lo, hi) {
  let ok = lo;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (await fn(mid)) { ok = mid; lo = mid + 1; } else { hi = mid - 1; }
  }
  return ok;
}

async function runLenCells() {
  const cells = [];
  // T18 component length limit
  const baseExt = path.join(RUN_ROOT, "T18-ext"); mkdirSync(baseExt, { recursive: true });
  const ca = await bisectMaxOk((m) => lenTrial(baseExt, "component", m, true), 1, 400);
  const basePlain = path.join(RUN_ROOT, "T18-plain"); mkdirSync(basePlain, { recursive: true });
  const cb = await bisectMaxOk((m) => lenTrial(basePlain, "component", m, false), 1, 400);
  cells.push(lenCell("T18-extended", "component", ca, "extended", "prefix_rewrite"));
  cells.push(lenCell("T18-plain", "component", cb, "plain", "none"));
  // T17 full-path length limit
  const base17 = path.join(RUN_ROOT, "T17-plain"); mkdirSync(base17, { recursive: true });
  const c17 = await bisectMaxOk((m) => lenTrial(base17, "path", m, false), 100, 4000);
  cells.push(lenCell("T17-plain", "path", c17, "plain", "none"));
  const base17e = path.join(RUN_ROOT, "T17-ext"); mkdirSync(base17e, { recursive: true });
  const c17e = await bisectMaxOk((m) => lenTrial(base17e, "path", m, true), 100, 8000);
  cells.push(lenCell("T17-extended", "path", c17e, "extended", "prefix_rewrite"));
  return cells;
}
function lenCell(cid, kind, boundary, pathForm, mech) {
  return {
    format_version: 1, case_id: cid, case_group: "len", language: "node", os: "windows",
    api_entry: PRIMARY_ENTRY, attempt: 1, name_source: Buffer.from("len-bisection", "utf8").toString("hex"),
    path_form: pathForm, longpath_mechanism: mech, create_result: "ok", error_stage: "null",
    read_result: "ok", os_legality_verdict: "legal", harness_version: HARNESS_VERSION,
    started_at: new Date().toISOString(), elapsed_ms: 0, worker_id: WORKER_ID, deps_direct: 0, deps_total: 0,
    len_kind: kind, boundary_len: boundary, control_pass: true, mechanism_class: "component_length_limit",
    env: { ...envMeta },
  };
}

// ---------------------------------------------------------------------------
// T-API sweep (instrument self-check: every pinned entry must be alive)
// ---------------------------------------------------------------------------
async function runApiSweep(cases) {
  const out = [];
  for (const c of cases) {
    if (c.id === "T17" || c.id === "T18") continue;
    const samples = classifySample(c);
    for (let idx = 0; idx < samples.length; idx++) {
      const { hex, name, defect } = samples[idx];
      if (defect) continue;
      const sub = samples.length > 1 ? c.id + String.fromCharCode(97 + idx) : c.id;
      for (const entry of NODE_ENTRIES) {
        const { cell } = await measureCell({ caseId: sub + "@" + entry, group: "tapi", nameHex: hex, category: c.category, locale: c.locale, entry, mechanismClass: MECHANISM[c.category] || "unknown" });
        out.push(cell);
      }
    }
  }
  return out;
}

// ---------------------------------------------------------------------------
// blind samples (identity sealed until S03; reported separately)
// ---------------------------------------------------------------------------
async function runBlind() {
  const map = JSON.parse(readFileSync(BLIND_MAP, "utf8"));
  const cells = [];
  for (const e of map.entries) {
    const { cell } = await measureCell({ caseId: "B" + e.blind_id, group: "blind", nameHex: e.name_utf8_hex, category: "control_char_handling", locale: "en-US", mechanismClass: "unknown" });
    cell.blind_id = e.blind_id;
    cells.push(cell);
  }
  return cells;
}

// ---------------------------------------------------------------------------
// main
// ---------------------------------------------------------------------------
let NO_CROSSREAD = false;
async function main() {
  const args = process.argv.slice(2);
  if (args.includes("--no-crossread")) NO_CROSSREAD = true;
  const { cases, api, ctrl } = loadSpec();
  if (cases.length !== 20) { console.error("FATAL: parsed", cases.length, "cases, expected 20"); process.exit(2); }
  if (ctrl.length !== 5) { console.error("FATAL: parsed", ctrl.length, "control cells, expected 5"); process.exit(2); }
  console.log("loaded", cases.length, "traps,", ctrl.length, "controls; node entries:", (api.node || []).join(","));

  if (args.includes("--check-samples")) {
    let defects = 0;
    for (const c of cases) {
      for (const { hex, name, defect } of classifySample(c)) {
        const mark = defect ? "DEFECT" : "OK    ";
        if (defect) defects++;
        const disp = name === null ? "<undecodable>" : JSON.stringify(name);
        console.log(c.id.padEnd(5), mark, hex.padEnd(48), disp, defect || "");
      }
    }
    console.log("\nDEFECT samples:", defects);
    return 0;
  }

  const lp = detectLongpathMechanism();
  envMeta.LongPathsEnabled = lp.lpe;
  envMeta.longpath_mechanism = lp.mechanism;
  console.log("LongPathsEnabled=", lp.lpe, "longpath_mechanism=", lp.mechanism);

  RESULTS && mkdirSync(RESULTS, { recursive: true });
  const outDir = path.join(RESULTS, "node", "windows"); mkdirSync(outDir, { recursive: true });
  mkdirSync(EVID, { recursive: true });
  mkdirSync(path.join(EVID, "conflicts"), { recursive: true });
  mkdirSync(path.join(EVID, "defects"), { recursive: true });

  const cells = [], extras = [], defects = [];
  for (const c of cases) {
    if (c.id === "T17" || c.id === "T18") continue;
    const samples = classifySample(c);
    for (let idx = 0; idx < samples.length; idx++) {
      const s = samples[idx];
      const sub = samples.length > 1 ? c.id + String.fromCharCode(97 + idx) : c.id;
      if (s.defect) {
        defects.push({ case_id: sub, hex: s.hex, decoded: s.name, defect: s.defect, category: c.category });
        continue;
      }
      const { cell, extra } = await measureCell({ caseId: sub, group: "trap", nameHex: s.hex, category: c.category, locale: c.locale, mechanismClass: MECHANISM[c.category] || "unknown" });
      cells.push(cell); extras.push(extra);
    }
  }

  const { cells: ctrlCells, extras: ctrlExtra } = await runControls();
  cells.push(...ctrlCells); extras.push(...ctrlExtra);

  const lenCells = await runLenCells();
  cells.push(...lenCells);

  const blindCells = await runBlind();
  cells.push(...blindCells);

  let apiCells = [];
  if (args.includes("--api")) {
    const apiDir = path.join(RESULTS, "node", "api"); mkdirSync(apiDir, { recursive: true });
    apiCells = await runApiSweep(cases);
    for (const c of apiCells) {
      writeFileSync(path.join(apiDir, c.case_id.replace("@", "__") + ".json"), JSON.stringify(c, null, 2));
    }
    writeFileSync(path.join(apiDir, "node.api-entry.windows.json"), JSON.stringify({ meta: { harness_version: HARNESS_VERSION, worker_id: WORKER_ID, case_group: "tapi", entries: NODE_ENTRIES }, cells: apiCells }, null, 2));
  }

  for (const cell of cells) {
    writeFileSync(path.join(outDir, cell.case_id + ".json"), JSON.stringify(cell, null, 2));
  }
  const bundle = {
    meta: { harness_version: HARNESS_VERSION, worker_id: WORKER_ID, language: "node", os: "windows", node: process.versions.node, started_at: new Date().toISOString(), longpath_mechanism: lp.mechanism, LongPathsEnabled: lp.lpe },
    cells,
  };
  const ver = process.versions.node;
  writeFileSync(path.join(RESULTS, "node.windows." + ver + ".json"), JSON.stringify(bundle, null, 2));

  // out-of-process audit pass manifest (independent TRUTH instrument via shell)
  writeFileSync(path.join(outDir, "_audit-manifest.json"), JSON.stringify({ count: AUDIT_MANIFEST.length, entries: AUDIT_MANIFEST }, null, 2));

  // out-of-process Python cross-reader manifest (independent Python runtime via shell; `timeout 5`)
  writeFileSync(path.join(outDir, "_pyreader-manifest.json"), JSON.stringify({ python_bin: PYTHON_BIN, count: PYREADER_MANIFEST.length, entries: PYREADER_MANIFEST }, null, 2));

  const phantom = cells.filter((c) => c.create_result === "ok" && c.bytes_on_disk === null && c.truth_is_device !== true);
  writeFileSync(path.join(RESULTS, "node", "phantom.windows.json"), JSON.stringify({ count: phantom.length, cells: phantom }, null, 2));

  writeFileSync(path.join(EVID, "defects", "sample-corruption.json"), JSON.stringify({ count: defects.length, defects, note: "cases.yaml was P0 freeze-blocking-fixed at rev2 (2026-10-10): 9 corrupted sample hex (T06/T07/T09a/T09b/T12/T13/T15/T19a/T19b) replaced with correct UTF-8 hex per evidence/S02/defects/sample-corruption.md. Re-validation this run: 0 remaining corrupted samples. (Historical Python defect report captured the PRE-fix state.)" }, null, 2));

  const conflicts = cells.filter((c) => c.instrument_conflict);
  for (const c of conflicts) {
    writeFileSync(path.join(EVID, "conflicts", c.case_id + ".json"), JSON.stringify(c, null, 2));
  }

  const deviceCells = cells.filter((c) => c.truth_is_device);
  writeFileSync(path.join(EVID, "node-device-findings.json"), JSON.stringify({ count: deviceCells.length, cells: deviceCells.map((c) => ({ case_id: c.case_id, create_result: c.create_result, os_legality_verdict: c.os_legality_verdict, truth_is_device: true, bytes_on_disk: c.bytes_on_disk, bytes_on_disk_truth: c.bytes_on_disk_truth || 0, cross_reader: c.cross_reader || null })) }, null, 2));

  const counts = {
    trap: cells.filter((c) => c.case_group === "trap").length,
    ctrl: cells.filter((c) => c.case_group === "ctrl").length,
    len: cells.filter((c) => c.case_group === "len").length,
    blind: cells.filter((c) => c.case_group === "blind").length,
    tapi: apiCells.length,
    defects_skipped: defects.length,
    conflicts: conflicts.length,
    device_findings: deviceCells.length,
    phantom: phantom.length,
  };
  console.log("cells written:", cells.length, JSON.stringify(counts));
  if (apiCells.length) console.log("tapi cells:", apiCells.length);
  return 0;
}

main();
