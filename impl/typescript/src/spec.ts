/**
 * Reader for the frozen case table.
 *
 * Samples are decoded from spec/cases.yaml at runtime (hex in, name out). No
 * forbidden name is transcribed into this file or into any committed artifact.
 *
 * The reader is deliberately narrow: it understands only the shape spec/cases.yaml
 * actually has (two-space list items, four-space keys, six-space nested list items),
 * and it refuses the whole file on any surprise instead of skipping a bad record.
 * A silent skip would let a broken run look clean -- the defect named in
 * spec/cell-identity.md S1.
 */
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
import { FROZEN_TRAP_IDS, LEN_CASE_MARKERS } from "./constants.ts";

export const REPO_ROOT = resolve(import.meta.dirname, "..", "..", "..");

export interface FrozenCase {
  readonly id: string;
  readonly samplesHex: readonly string[];
  readonly category: string;
  readonly locale: string;
  readonly applicable: readonly string[];
  readonly expectationNull: boolean;
}

/** rev6 pins the five control samples and one 28-byte payload for every port. */
export interface ControlSample {
  readonly id: string;
  readonly sampleHex: string;
  readonly payloadHex: string;
  readonly expectationNull: boolean;
}

/** spec/cases.yaml `len_fill` (rev7): the pinned component for the length family. */
export interface LenFill {
  readonly unitHex: string;
  readonly rule: string;
  readonly appliesTo: readonly string[];
  readonly nameSourceRule: string;
}

export interface FrozenSpec {
  readonly formatVersion: number;
  readonly lenFill: LenFill;
  readonly controlSamples: readonly ControlSample[];
  readonly canonPayloadSha256: string;
  readonly freezeRevision: number;
  readonly cases: readonly FrozenCase[];
  readonly controlCells: readonly string[];
  readonly entries: readonly string[];
  readonly casesBlobSha256: string;
  readonly canonicalBlobSha256: string;
  readonly schemaBlobSha256: string;
  readonly identityBlobSha256: string;
  readonly frozenLockedHash: string | null;
}

export class SpecError extends Error {}

const HEX_RE = /^[0-9a-f]+$/;

/** Value text after stripping an inline `# comment` that sits outside quotes. */
function unquote(value: string): string {
  const trimmed = value.trim();
  if (trimmed.startsWith('"')) {
    const close = trimmed.indexOf('"', 1);
    if (close < 0) throw new SpecError(`unterminated quote in: ${trimmed}`);
    return trimmed.slice(1, close);
  }
  const hash = trimmed.indexOf("#");
  return (hash >= 0 ? trimmed.slice(0, hash) : trimmed).trim();
}

function inlineList(value: string): readonly string[] {
  const inner = value.trim().replace(/^\[/, "").replace(/\]$/, "");
  if (inner.trim() === "") return [];
  return inner
    .split(",")
    .map((part) => part.trim())
    .filter((part) => part !== "");
}

interface DraftCase {
  id: string;
  samplesHex: string[];
  category: string;
  locale: string;
  applicable: readonly string[];
  expectationSeen: boolean;
  expectationNull: boolean;
}

interface Parsed {
  formatVersion: number;
  freezeRevision: number;
  controlCells: string[];
  controlSamples: ControlSample[];
  entries: Record<string, readonly string[]>;
  cases: DraftCase[];
}

function parseCases(text: string): Parsed {
  const lines = text.split(/\r?\n/);
  const out: Parsed = {
    formatVersion: Number.NaN,
    freezeRevision: Number.NaN,
    controlCells: [],
    controlSamples: [],
    entries: {},
    cases: [],
  };
  let section: "none" | "api_entry" | "control_cells" | "control_samples" | "cases" = "none";
  let sample: { id?: string; sampleHex?: string; payloadHex?: string; expectationSeen: boolean; expectationNull: boolean } | null = null;
  const flushSample = (): void => {
    if (sample === null) return;
    if (sample.id === undefined || sample.sampleHex === undefined || sample.payloadHex === undefined) {
      throw new SpecError("control_samples entry is incomplete");
    }
    out.controlSamples.push({
      id: sample.id,
      sampleHex: sample.sampleHex,
      payloadHex: sample.payloadHex,
      expectationNull: sample.expectationSeen && sample.expectationNull,
    });
    sample = null;
  };
  let draft: DraftCase | null = null;
  let pendingHexList = false;

  const flush = (): void => {
    if (draft !== null) out.cases.push(draft);
    draft = null;
    pendingHexList = false;
  };

  for (const line of lines) {
    const stripped = line.replace(/\s+$/, "");
    if (stripped === "" || /^\s*#/.test(stripped)) continue;

    const top = /^([a-z_][a-z_0-9]*):\s*(.*)$/.exec(stripped);
    if (top !== null) {
      flush();
      flushSample();
      const key = top[1] as string;
      const value = top[2] as string;
      if (key === "format_version") out.formatVersion = Number(unquote(value));
      else if (key === "freeze_revision") out.freezeRevision = Number(unquote(value));
      else if (key === "api_entry" || key === "control_cells" || key === "cases") {
        section = key as "api_entry" | "control_cells" | "cases";
      } else if (key === "control_samples") {
        section = "control_samples";
      } else section = "none";
      continue;
    }

    if (section === "cases") {
      const item = /^  - id:\s*(\S+)\s*$/.exec(stripped);
      if (item !== null) {
        flush();
        draft = {
          id: item[1] as string,
          samplesHex: [],
          category: "",
          locale: "",
          applicable: [],
          expectationSeen: false,
          expectationNull: false,
        };
        continue;
      }
      const nested = /^      - (.+)$/.exec(stripped);
      if (nested !== null && draft !== null && pendingHexList) {
        draft.samplesHex.push(unquote(nested[1] as string));
        continue;
      }
      const field = /^    ([a-z_0-9]+):\s*(.*)$/.exec(stripped);
      if (field !== null && draft !== null) {
        const key = field[1] as string;
        const value = field[2] as string;
        pendingHexList = false;
        if (key === "sample_hex") draft.samplesHex = [unquote(value)];
        else if (key === "sample_hex_list") pendingHexList = true;
        else if (key === "category") draft.category = unquote(value);
        else if (key === "locale") draft.locale = unquote(value);
        else if (key === "applicable") draft.applicable = inlineList(value);
        else if (key === "expectation") {
          draft.expectationSeen = true;
          draft.expectationNull = unquote(value) === "null";
        }
        continue;
      }
    }

    if (section === "control_samples") {
      const item = /^  - id: (\S+)\s*$/.exec(stripped);
      if (item !== null) {
        flushSample();
        sample = { id: item[1] as string, expectationSeen: false, expectationNull: false };
        continue;
      }
      const field = /^    ([a-z_0-9]+):\s*(.*)$/.exec(stripped);
      if (field !== null && sample !== null) {
        const key = field[1] as string;
        const value = field[2] as string;
        if (key === "sample_hex") sample.sampleHex = unquote(value);
        else if (key === "payload_hex") sample.payloadHex = unquote(value);
        else if (key === "expectation") {
          sample.expectationSeen = true;
          sample.expectationNull = unquote(value) === "null";
        }
        continue;
      }
    }

    if (section === "control_cells") {
      const item = /^  - (.+)$/.exec(stripped);
      if (item !== null) {
        out.controlCells.push(unquote(item[1] as string));
        continue;
      }
    }

    if (section === "api_entry") {
      const field = /^  ([a-z_0-9]+):\s*(.*)$/.exec(stripped);
      if (field !== null) {
        out.entries[field[1] as string] = inlineList(field[2] as string);
        continue;
      }
    }
  }
  flush();
  flushSample();
  return out;
}

/** sha256 of the committed blob face, not of the working-tree copy. */
function blobSha256(repo: string, gitPath: string): string {
  const bytes = execFileSync("git", ["-C", repo, "cat-file", "blob", `HEAD:${gitPath}`], { encoding: "buffer" });
  return createHash("sha256").update(bytes).digest("hex");
}

/** `lockedPath` is the repo-relative path exactly as spec/FROZEN.md prints it in its lock table. */
export function lockedHashInFrozenMd(repo: string, lockedPath: string): string | null {
  let text: string;
  try {
    text = readFileSync(resolve(repo, "spec", "FROZEN.md"), "utf8");
  } catch {
    return null;
  }
  const m = new RegExp(`^\\|\\s*${lockedPath}\\s*\\|\\s*([0-9a-f]{64})\\s*\\|`, "m").exec(text);
  return m === null ? null : (m[1] as string);
}

export function decodeSample(hex: string): string {
  if (!HEX_RE.test(hex) || hex.length % 2 !== 0) {
    throw new SpecError(`sample is not lowercase even-length UTF-8 hex: ${JSON.stringify(hex.slice(0, 24))}`);
  }
  return Buffer.from(hex, "hex").toString("utf8");
}

export function toHex(name: string): string {
  return Buffer.from(name, "utf8").toString("hex");
}

/** The three counting units gate.md S3 type IV names: [code points, utf16 units, utf8 bytes]. */
export function lengthTriple(name: string): readonly [number, number, number] {
  return [
    Array.from(name).length,
    name.length,
    Buffer.byteLength(name, "utf8"),
  ] as const;
}

/** Parse the `len_fill` block. Rev7 pinned it after six ports had filed six different names. */
function parseLenFill(text: string): LenFill {
  const head = text.indexOf("\nlen_fill:");
  if (head < 0) throw new SpecError("rev7 pins a len_fill block in spec/cases.yaml; none found -- refusing to invent a filler");
  const rest = text.slice(head + 1);
  const stop = rest.search(/\n(?=[a-z_]+:)/);
  const block = stop < 0 ? rest : rest.slice(0, stop);
  const get = (key: string): string => {
    const m = new RegExp(`^  ${key}:\\s*(.*)$`, "m").exec(block);
    if (m === null) throw new SpecError(`len_fill is missing ${key}`);
    return unquote(m[1] as string);
  };
  const unitHex = get("unit_hex");
  if (!/^[0-9a-f]{2}$/.test(unitHex)) throw new SpecError(`len_fill.unit_hex must be one code unit in hex, got ${JSON.stringify(unitHex)}`);
  const appliesTo = get("applies_to")
    .replace(/^\[|\]$/g, "")
    .split(",")
    .map((x) => x.trim())
    .filter((x) => x !== "");
  if (appliesTo.join(",") !== "T17,T18") throw new SpecError(`len_fill.applies_to expected T17,T18, got ${appliesTo.join(",")}`);
  return { unitHex, rule: get("rule"), appliesTo, nameSourceRule: get("name_source_rule") };
}

export function loadFrozenSpec(): FrozenSpec {
  const text = readFileSync(resolve(REPO_ROOT, "spec", "cases.yaml"), "utf8");
  const parsed = parseCases(text);
  const lenFill = parseLenFill(text);

  if (parsed.formatVersion !== 1) throw new SpecError(`format_version expected 1, got ${parsed.formatVersion}`);
  if (parsed.freezeRevision !== 2) throw new SpecError(`freeze_revision expected 2, got ${parsed.freezeRevision}`);
  if (parsed.cases.length !== 20) throw new SpecError(`expected 20 frozen cases, parsed ${parsed.cases.length}`);
  if (parsed.cases.map((c) => c.id).join(",") !== FROZEN_TRAP_IDS.join(",")) {
    throw new SpecError("parsed ids are not the 20 frozen trap ids in order");
  }
  if (parsed.controlCells.length !== 5) throw new SpecError(`expected 5 control cells, got ${parsed.controlCells.length}`);
  if (parsed.controlSamples.length !== 5) throw new SpecError(`rev6 pins 5 control samples, parsed ${parsed.controlSamples.length}`);
  const payloadHexes = new Set(parsed.controlSamples.map((c) => c.payloadHex));
  if (payloadHexes.size !== 1) throw new SpecError(`the control payload is pinned once; parsed ${payloadHexes.size} distinct payload_hex values`);
  const payloadBytes = Buffer.from([...payloadHexes][0] as string, "hex");
  if (payloadBytes.length !== 28) throw new SpecError(`pinned control payload must be 28 bytes, got ${payloadBytes.length}`);
  for (const c of parsed.controlSamples) {
    if (!c.expectationNull) throw new SpecError(`control sample ${c.id} carries a non-null expectation`);
    const nm = decodeSample(c.sampleHex);
    if (nm.includes("/") || nm.includes("\\")) throw new SpecError(`control sample ${c.id} is not a single component`);
  }
  const canonPayloadSha = createHash("sha256").update(payloadBytes).digest("hex");

  const nodeEntries = parsed.entries["node"] ?? [];
  if (nodeEntries.join(",") !== "writeFileSync,createWriteStream,appendFileSync") {
    throw new SpecError(`node pinned entry list drifted: ${JSON.stringify(nodeEntries)}`);
  }

  for (const c of parsed.cases) {
    if (!c.expectationNull) throw new SpecError(`case ${c.id} carries a non-null expectation`);
    if (c.samplesHex.length === 0) throw new SpecError(`case ${c.id} carries no sample`);
    const marker = LEN_CASE_MARKERS[c.id];
    if (marker !== undefined) {
      if (c.samplesHex.length !== 1 || c.samplesHex[0] !== marker) {
        throw new SpecError(`len case ${c.id} marker drifted from the frozen table`);
      }
      continue;
    }
    for (const hex of c.samplesHex) {
      const name = decodeSample(hex);
      if (name.includes("/") || name.includes("\\") || name.includes("\u0000")) {
        throw new SpecError(`case ${c.id} sample is not a single safe component`);
      }
    }
  }

  const casesBlob = blobSha256(REPO_ROOT, "spec/cases.yaml");
  const locked = lockedHashInFrozenMd(REPO_ROOT, "spec/cases.yaml");
  if (locked !== null && locked !== casesBlob) {
    throw new SpecError(`spec/cases.yaml blob face ${casesBlob} != FROZEN.md locked hash ${locked}`);
  }

  return {
    formatVersion: parsed.formatVersion,
    freezeRevision: parsed.freezeRevision,
    lenFill,
    controlSamples: parsed.controlSamples,
    canonPayloadSha256: canonPayloadSha,
    cases: parsed.cases,
    controlCells: parsed.controlCells,
    entries: nodeEntries,
    casesBlobSha256: casesBlob,
    canonicalBlobSha256: blobSha256(REPO_ROOT, "spec/canonical.md"),
    schemaBlobSha256: blobSha256(REPO_ROOT, "spec/schema.json"),
    identityBlobSha256: blobSha256(REPO_ROOT, "spec/cell-identity.md"),
    frozenLockedHash: locked,
  };
}
