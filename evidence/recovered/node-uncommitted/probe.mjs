// SENDGUARD Node empirical probe (pre-harness verification of headline cells).
// Child receives a single JSON arg: {entry, d, h, ph}. Mirrors final harness.
import { spawn } from "child_process";
import { statSync, readdirSync, existsSync, mkdirSync } from "fs";
import { createHash } from "crypto";
import { fileURLToPath } from "url";
import path from "path";
import os from "os";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const RUN = path.join(os.tmpdir(), "sendguard-probe-node", String(Date.now()));
mkdirSync(RUN, { recursive: true });

const PAYLOAD = Buffer.from("SENDGUARD-CANON-PAYLOAD-2026"); // 28 bytes
const PAYLOAD_HEX = PAYLOAD.toString("hex");
const sha256 = (b) => createHash("sha256").update(b).digest("hex");

const CREATE_DRIVER = `
const { entry, d, h, ph } = JSON.parse(process.env.SG_PARAMS);
const fs = require('fs');
const name = Buffer.from(h, 'hex').toString('utf8');
const p = require('path').join(d, name);
const data = Buffer.from(ph, 'hex');
const res = { create_result: 'ok', error_stage: null, error_code: null, error_message: null, bytes_written: null };
function done() { process.stdout.write(JSON.stringify(res)); }
try {
  if (entry === 'writeFileSync') { fs.writeFileSync(p, data); res.bytes_written = data.length; done(); }
  else if (entry === 'appendFileSync') { fs.appendFileSync(p, data); res.bytes_written = data.length; done(); }
  else if (entry === 'createWriteStream') {
    let finished = false;
    const finish = () => { if (finished) return; finished = true; done(); };
    const ws = fs.createWriteStream(p);
    ws.on('error', (e) => { const code = e && e.code ? String(e.code) : 'unknown'; res.create_result = code.startsWith('ERR_') ? 'err_at_parse' : 'err_at_syscall'; res.error_stage = code.startsWith('ERR_') ? 'parse' : 'syscall'; res.error_code = code; res.error_message = String(e.message||e); finish(); });
    ws.on('close', () => { if (res.create_result === 'ok') res.bytes_written = data.length; finish(); });
    ws.write(data); ws.end();
  } else { res.create_result='err_at_parse'; res.error_stage='parse'; res.error_code='UNKNOWN_ENTRY'; done(); }
} catch (e) {
  const code = e && e.code ? String(e.code) : 'unknown';
  res.create_result = code.startsWith('ERR_') ? 'err_at_parse' : 'err_at_syscall';
  res.error_stage = code.startsWith('ERR_') ? 'parse' : 'syscall';
  res.error_code = code;
  res.error_message = String(e && e.message || e);
  done();
}
`;

const READ_DRIVER = `
const { d, h } = JSON.parse(process.env.SG_PARAMS);
const fs = require('fs');
const name = Buffer.from(h, 'hex').toString('utf8');
const p = require('path').join(d, name);
const res = { read_result: 'ok', bytes_read: null, sha256: null, error_code: null, error_message: null };
try {
  const b = fs.readFileSync(p);
  res.bytes_read = b.length;
  res.sha256 = require('crypto').createHash('sha256').update(b).digest('hex');
  if (!b.length) res.read_result = 'eof';
} catch (e) {
  const code = e && e.code ? String(e.code) : 'unknown';
  if (code === 'ENOENT') res.read_result = 'eof';
  else if (code === 'ERR_FS_EISDIR') res.read_result = 'eof';
  else if (code === 'EPERM' || code === 'EBUSY') res.read_result = 'err6';
  else res.read_result = 'err6';
  res.error_code = code;
  res.error_message = String(e && e.message || e);
}
process.stdout.write(JSON.stringify(res));
`;

function runChild(driver, params, timeoutMs = 5000) {
  return new Promise((resolve) => {
    const child = spawn(process.execPath, ["-e", driver], { windowsHide: true, env: { ...process.env, SG_PARAMS: JSON.stringify(params) } });
    let out = "", err = "";
    const timer = setTimeout(() => { try { child.kill("SIGKILL"); } catch {} resolve({ hung: true, out, err: "timeout" }); }, timeoutMs);
    child.stdout.on("data", (d) => (out += d));
    child.stderr.on("data", (d) => (err += d));
    child.on("close", () => { clearTimeout(timer); resolve({ hung: false, out: out.trim(), err: err.trim() }); });
    child.on("error", (e) => { clearTimeout(timer); resolve({ hung: false, out, err: String(e) }); });
  });
}

function dirView(d) {
  const m = {};
  try {
    for (const e of readdirSync(d, { withFileTypes: true })) {
      const h = Buffer.from(e.name, "utf8").toString("hex");
      let size = null;
      if (!e.isDirectory()) { try { size = statSync(path.join(d, e.name)).size; } catch {} }
      m[h] = size;
    }
  } catch {}
  return m;
}

const TESTS = [
  ["T01", "434f4e2e747874", "CON.txt"],
  ["T02", "4e554c2e7461722e677a", "NUL.tar.gz"],
  ["T03", "613c622e747874", "a<b.txt"],
  ["T10", "434f4e", "CON"],
  ["T11", "434f4d312e6c6f67", "COM1.log"],
  ["NAMETOOLONG", "61".repeat(256), "a*256"],
  ["PARSE", "6e756c00627974652e747874", "nul\\x00byte.txt"],
  ["ASCII", "7265706f72742d323032362e747874", "report-2026.txt"],
  ["T04", "747261696c2e", "trail."],
  ["T05", "747261696c737020", "trailsp "],
];
const ENTRIES = ["writeFileSync", "createWriteStream", "appendFileSync"];

async function main() {
  console.log("RUN=", RUN, "payload_sha=", sha256(PAYLOAD));
  for (const [id, hex, label] of TESTS) {
    const d = path.join(RUN, id, Math.random().toString(36).slice(2));
    mkdirSync(d, { recursive: true });
    const row = { id, label, entries: {} };
    for (const entry of ENTRIES) {
      const cr = await runChild(CREATE_DRIVER, { entry, d, h: hex, ph: PAYLOAD_HEX });
      let crObj = null; try { crObj = JSON.parse(cr.out); } catch { crObj = { parse: "FAIL", raw: cr.out, err: cr.err, hung: cr.hung }; }
      const dv = dirView(d);
      const present = hex in dv;
      const boot = { create: crObj, dir_view: dv, path_view: (()=>{try{return existsSync(path.join(d,Buffer.from(hex,'hex').toString('utf8')))}catch{return false}})(), present_in_dir: present, bytes_on_disk: present ? dv[hex] : null };
      if (crObj && crObj.create_result === "ok") {
        const rd = await runChild(READ_DRIVER, { d, h: hex });
        let rdObj = null; try { rdObj = JSON.parse(rd.out); } catch { rdObj = { parse: "FAIL", raw: rd.out, err: rd.err, hung: rd.hung }; }
        boot.read = rdObj;
      }
      row.entries[entry] = boot;
    }
    console.log("\n=== " + id + " (" + label + ") ===");
    console.log(JSON.stringify(row, null, 2));
  }
}
main();
