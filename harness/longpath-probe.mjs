// SENDGUARD S00 longpath 2x2 sub-experiment (Node probe).
// Grid: LongPathsEnabled {0,1} x path_form {plain, extended(\\?\)}
// Goal: classify this machine's longpath_mechanism: manifest | prefix_rewrite | none | unknown.
// Plain path must exceed 260 chars to force the long-path question.
// Usage: node longpath-probe.mjs
import { writeFileSync, mkdirSync, rmSync, statSync } from "fs";
import { execFileSync } from "child_process";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const BASE = path.join(__dirname, "..", "evidence", "S00", "_longrun");
const DEEP = path.join(
  BASE,
  "0123456789abcdef0123456789abcdef",
  "0123456789abcdef0123456789abcdef",
  "0123456789abcdef0123456789abcdef",
  "0123456789abcdef0123456789abcdef",
  "0123456789abcdef0123456789abcdef",
  "0123456789abcdef0123456789abcdef",
  "0123456789abcdef0123456789abcdef",
  "0123456789abcdef0123456789abcdef"
); // 8 x 32-char components -> plain target > 260 chars
const NAME = "report-2026.txt";
const PLAIN = path.join(DEEP, NAME);
const EXT = "\\\\?\\" + path.join(DEEP, NAME);

function readLPE() {
  const out = execFileSync("reg", ["query", "HKLM\\SYSTEM\\CurrentControlSet\\Control\\FileSystem", "/v", "LongPathsEnabled"], { encoding: "utf8" });
  const m = out.match(/LongPathsEnabled\s+REG_DWORD\s+0x([0-9a-f]+)/i);
  return m ? parseInt(m[1], 16) : null;
}

function tryWrite(p) {
  mkdirSync(path.dirname(p), { recursive: true });
  try {
    writeFileSync(p, "x");
    const st = statSync(p);
    return { result: "ok", size: st.size, mechanism_hint: "created" };
  } catch (e) {
    return { result: "err", code: e && e.code ? String(e.code) : "unknown", mechanism_hint: "rejected" };
  }
}

function rowsFor(lpe) {
  const plain = tryWrite(PLAIN);
  rmSync(BASE, { recursive: true, force: true });
  const ext = tryWrite(EXT);
  rmSync(BASE, { recursive: true, force: true });
  return { lpe, plain, ext };
}

function classify(lpe, plain, ext) {
  // plain created under LPE=0 => the language/API rewrote the path itself (prefix-rewrite)
  if (lpe === 0) {
    if (plain.result === "ok" && ext.result === "ok") return "prefix_rewrite (lang auto-prefix under LPE=0)";
    if (plain.result === "err" && ext.result === "ok") return "none (plain blocked; extended works)";
    if (plain.result === "err" && ext.result === "err") return "none (both blocked)";
  }
  if (lpe === 1) {
    if (plain.result === "ok") return "manifest (OS long path enabled; plain works)";
    if (plain.result === "err" && ext.result === "ok") return "manifest-partial (LPE=1 but plain blocked; extended works)";
  }
  return "unknown";
}

const lpeNow = readLPE();
const r0 = rowsFor(lpeNow);
const out = [];
out.push("# SENDGUARD S00 longpath 2x2 sub-experiment (Node probe)");
out.push("");
out.push(`- date: ${new Date().toISOString()}`);
out.push(`- LongPathsEnabled (before): ${lpeNow}`);
out.push(`- plain target: ${PLAIN} (len=${PLAIN.length})`);
out.push(`- extended target: ${EXT} (len=${EXT.length})`);
out.push("");
out.push(`## Cell A: LongPathsEnabled=${lpeNow} x plain`);
out.push("");
out.push(`- result: ${r0.plain.result}${r0.plain.code ? " / " + r0.plain.code : ""}`);
out.push("");
out.push(`## Cell B: LongPathsEnabled=${lpeNow} x extended (\\\\?\\)`);
out.push("");
out.push(`- result: ${r0.ext.result}${r0.ext.code ? " / " + r0.ext.code : ""}`);
out.push("");
out.push(`## Mechanism classification (LPE=${lpeNow})`);
out.push("");
out.push(`- ${classify(lpeNow, r0.plain, r0.ext)}`);
out.push("");
out.push("_Switch-cell results (LPE=1) appended when the registry can be toggled; otherwise this machine's LPE is read-only in this session._");
console.log(out.join("\n"));
