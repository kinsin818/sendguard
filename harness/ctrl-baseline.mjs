// SENDGUARD S00 control-cell baseline probe (Node side).
// Reads the five control cells on THIS machine and prints a markdown baseline.
// The baseline file is the ONLY allowed source of control expectations.
// Expectations are MEASURED, not hand-written (julying discipline).
// Node side drives create attempts; CANON second arm is a Python child process.
// Usage: node ctrl-baseline.mjs > evidence/ctrl-baseline.md
import { writeFileSync, readFileSync, statSync, mkdirSync, rmSync, readdirSync } from "fs";
import { createHash } from "crypto";
import { execFileSync } from "child_process";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const RUN = path.join(__dirname, "..", "evidence", "freeze", "_ctrlrun");
const PAYLOAD = Buffer.from("SENDGUARD-CANON-PAYLOAD-2026");

function sha256(buf) {
  return createHash("sha256").update(buf).digest("hex");
}
function utf8hex(s) {
  return Buffer.from(s, "utf8").toString("hex");
}
function codepoints(s) {
  return [...s].map((c) => c.codePointAt(0).toString(16).padStart(4, "0")).join("");
}
function classify(e) {
  // Node-internal errors (ERR_*) are parse-stage; system codes are syscall-stage.
  const code = e && e.code ? String(e.code) : "unknown";
  if (code.startsWith("ERR_")) return { stage: "parse", code };
  return { stage: "syscall", code };
}

mkdirSync(RUN, { recursive: true });

const cells = [];
function attempt(id, name, bytes) {
  const p = path.join(RUN, name);
  const row = {
    id,
    name_codepoints: codepoints(name),
    name_utf8_hex: utf8hex(name),
    create_result: null,
    error_stage: null,
    error_code: null,
    bytes_written: null,
    bytes_on_disk: null,
    read_result: null,
    roundtrip_ok: null,
    sha256_on_disk: null,
  };
  try {
    writeFileSync(p, bytes);
    row.create_result = "ok";
    row.bytes_written = bytes.length;
    const st = statSync(p);
    row.bytes_on_disk = st.size;
    row.sha256_on_disk = sha256(readFileSync(p));
    try {
      const rb = readFileSync(p);
      row.read_result = "ok";
      row.roundtrip_ok = rb.equals(bytes);
    } catch (e2) {
      row.read_result = classify(e2).stage === "parse" ? "parse_err" : "syscall_err";
    }
  } catch (e) {
    const c = classify(e);
    row.create_result = c.stage === "parse" ? "err_at_parse" : "err_at_syscall";
    row.error_stage = c.stage;
    row.error_code = c.code;
  }
  cells.push(row);
  return row;
}

// --- Five control cells ---
attempt("T-CTRL-NAMETOOLONG", "a".repeat(256), PAYLOAD); // component 256 code units; NTFS max_component=255
attempt("T-CTRL-ASCII", "report-2026.txt", PAYLOAD);
attempt("T-CTRL-ILLEGAL-CHAR", "a<b.txt", PAYLOAD);
attempt("T-CTRL-PARSE", "nul\u0000byte.txt", PAYLOAD); // embedded U+0000

// T-CTRL-CANON: two languages, same payload -> canonical bytes must match.
const nodePath = path.join(RUN, "canon-node.txt");
writeFileSync(nodePath, PAYLOAD);
const py = process.env.PYTHON || "python";
const pyScript = `
import hashlib, pathlib, sys
p = pathlib.Path(r"${path.join(RUN, "canon-python.txt").replace(/\\/g, "\\\\")}")
p.write_bytes(b"SENDGUARD-CANON-PAYLOAD-2026")
print(hashlib.sha256(p.read_bytes()).hexdigest())
`;
const pyOut = execFileSync(py, ["-c", pyScript], { encoding: "utf8" }).trim();
const canonNode = sha256(PAYLOAD);
const canonPy = pyOut;
cells.push({
  id: "T-CTRL-CANON",
  node_sha256: canonNode,
  python_sha256: canonPy,
  canonical_bytes_agree: canonNode === canonPy,
  note: "same payload written by node and python; sha256 must match",
});

// --- Output markdown ---
const lines = [];
lines.push("# SENDGUARD Control-Cell Baseline (measured on this machine)");
lines.push("");
lines.push(`- date: ${new Date().toISOString()}`);
lines.push(`- os: ${process.platform} / node ${process.version}`);
lines.push(`- run dir: ${RUN}`);
lines.push(`- baseline is the ONLY allowed source of control expectations; hand-written expectations forbidden`);
lines.push("");
lines.push("| cell | create_result | error_stage | error_code | bytes_written | bytes_on_disk | read_result | roundtrip_ok | sha256_on_disk |");
lines.push("|---|---|---|---|---|---|---|---|---|");
for (const c of cells) {
  if (c.id === "T-CTRL-CANON") {
    lines.push(
      `| ${c.id} | (canonical) | - | - | - | - | - | ${c.canonical_bytes_agree} | node=${c.node_sha256} python=${c.python_sha256} |`
    );
    continue;
  }
  lines.push(
    `| ${c.id} | ${c.create_result} | ${c.error_stage} | ${c.error_code} | ${c.bytes_written} | ${c.bytes_on_disk} | ${c.read_result} | ${c.roundtrip_ok} | ${c.sha256_on_disk} |`
  );
}
lines.push("");
lines.push("## Interpretation");
lines.push("");
for (const c of cells) {
  if (c.id === "T-CTRL-NAMETOOLONG") {
    lines.push(`- **${c.id}** (component 256 code units): create_result=${c.create_result}, error_stage=${c.error_stage} — expectation per julying: fail on all 3 OS **after reaching FS** (err_at_syscall, not parse).`);
  }
  if (c.id === "T-CTRL-ASCII") {
    lines.push(`- **${c.id}** (report-2026.txt): create_result=${c.create_result} — expectation: ok on all languages/OS.`);
  }
  if (c.id === "T-CTRL-ILLEGAL-CHAR") {
    lines.push(`- **${c.id}** (a<b.txt): create_result=${c.create_result}, error_code=${c.error_code} — expectation: Windows illegal (winerror=123) / POSIX creatable, paired with os_legality_verdict.`);
  }
  if (c.id === "T-CTRL-PARSE") {
    lines.push(`- **${c.id}** (embedded U+0000): create_result=${c.create_result}, error_stage=${c.error_stage} — expectation: may reject before syscall, but all 6 langs MUST be err-at-parse; else that lang's harness is reworked.`);
  }
  if (c.id === "T-CTRL-CANON") {
    lines.push(`- **${c.id}**: node=${c.node_sha256} python=${c.python_sha256}, agree=${c.canonical_bytes_agree} — expectation: identical canonical bytes; else INSTRUMENT-RED.`);
  }
}
lines.push("");
console.log(lines.join("\n"));

// cleanup run dir
rmSync(RUN, { recursive: true, force: true });
