import { readFileSync } from "fs";
const raw = readFileSync("D:/sendguard/spec/cases.yaml", "utf-8");
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
const text = raw.split(/\r?\n/).map(stripComment).join("\n");
const re = /  - id:\s*(\w+)([\s\S]*?)(?=\n  - id:|$)/g;
let m, ids = [];
while ((m = re.exec(text)) !== null) ids.push(m[1]);
console.log("matched count:", ids.length);
console.log("ids:", ids.join(","));
const r2 = /  - id:\s*(\S+)/g; let x, all = [];
while ((x = r2.exec(text)) !== null) all.push(x[1]);
console.log("all - id: lines:", all.length, all.join(","));
