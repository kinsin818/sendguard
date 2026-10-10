import fs from "fs";
import path from "path";
const d = "C:\\Users\\Administrator\\AppData\\Local\\Temp\\sg_cmp_real";
fs.mkdirSync(d, { recursive: true });
function test(label, p) {
  try {
    fs.writeFileSync(p, Buffer.from("hello"));
    let size = "?"; try { size = fs.statSync(p).size; } catch (e) { size = "stat-" + e.code; }
    console.log(label, "-> OK exists=", fs.existsSync(p), "size=", size);
  } catch (e) {
    console.log(label, "-> ERR", e.code, e.message ? e.message.slice(0, 60) : "");
  }
}
const p = path.join(d, "CON.txt");
test("plain CON.txt   ", p);
test("extended \\\\?\\ CON.txt", "\\\\?\\" + p);
const q = path.join(d, "a<b.txt");
test("plain a<b.txt   ", q);
const r = path.join(d, "report-2026.txt");
test("plain ASCII     ", r);
