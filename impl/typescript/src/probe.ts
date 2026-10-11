/**
 * The probe child: one process per probe, one NDJSON event per stage.
 *
 * The parent enforces the 5-second timeout from outside (spec/gate.md section 10)
 * and kills this process if a syscall blocks, so the child carries no internal
 * deadline for the fs calls themselves. Events are appended to a log file the parent
 * chooses, held OUTSIDE the directory being enumerated, so a probe that hangs still
 * leaves behind the stages it had already recorded.
 *
 * Nothing here creates or deletes a directory: the parent owns the scratch tree
 * (project red line M19 -- the port carries no removal path at all).
 */
import {
  writeFileSync,
  appendFileSync,
  readFileSync,
  readdirSync,
  statSync,
  createWriteStream,
  createReadStream,
} from "node:fs";
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { decodeSample, toHex, lengthTriple } from "./spec.ts";
import { isReservedDeviceName } from "./nameguard.ts";
import { packZip, unpackZip } from "./zip.ts";
// rev6: PAYLOAD_TEXT is gone from the probe's vocabulary -- the payload arrives pinned.

const SEP = "\\";
/** Win32 extended prefix: the two-backslash, question-mark, backslash stem. */
const EXT = "\\\\?\\";

type Mode = "cell" | "canon" | "len" | "bisect" | "zip";
type Form = "plain" | "extended";

interface Args {
  readonly mode: Mode;
  readonly log: string;
  readonly dir: string;
  readonly outDir: string;
  readonly nameHex: string;
  readonly entryHex: string;
  readonly entry: string;
  readonly form: Form;
  readonly lo: string;
  readonly hi: string;
  readonly comp: string;
  readonly packer: string;
  readonly extractor: string;
  readonly tool: string;
  readonly bit11: string;
  readonly tier: string;
  readonly payloadHex: string;
}

function readArgs(argv: readonly string[]): Args {
  const map = new Map<string, string>();
  for (let i = 0; i < argv.length; i += 2) {
    const key = argv[i];
    const value = argv[i + 1];
    if (key === undefined || value === undefined || !key.startsWith("--")) {
      throw new Error(`bad argv pair at index ${i}`);
    }
    map.set(key.slice(2), value);
  }
  const get = (name: string): string => map.get(name) ?? "";
  const rawMode = get("mode");
  const modes: readonly Mode[] = ["cell", "canon", "len", "bisect", "zip"];
  if (!(modes as readonly string[]).includes(rawMode)) throw new Error(`unknown mode ${JSON.stringify(rawMode)}`);
  const rawForm = get("form");
  if (rawForm !== "plain" && rawForm !== "extended") throw new Error(`unknown form ${JSON.stringify(rawForm)}`);
  return {
    mode: rawMode as Mode,
    log: get("log"),
    dir: get("dir"),
    outDir: get("out-dir"),
    nameHex: get("name-hex"),
    entryHex: get("entry-hex"),
    entry: get("entry"),
    form: rawForm as Form,
    lo: get("lo"),
    hi: get("hi"),
    comp: get("comp"),
    packer: get("packer"),
    extractor: get("extractor"),
    tool: get("tool"),
    bit11: get("bit11"),
    tier: get("tier"),
    payloadHex: get("payload-hex"),
  };
}

function emit(logPath: string, event: Record<string, unknown>): void {
  appendFileSync(logPath, JSON.stringify(event) + "\n");
}

interface ProbeError {
  readonly code: string;
  readonly errno: number | null;
  readonly message: string;
  readonly winerror: string;
}

function describeError(err: unknown): ProbeError {
  const e = err as { code?: unknown; errno?: unknown; message?: unknown };
  return {
    code: typeof e.code === "string" ? e.code : String(e.code ?? ""),
    errno: typeof e.errno === "number" ? e.errno : null,
    message: String(e.message ?? err),
    // node:fs does not surface the Win32 error number. M16 asks for winerror
    // verbatim; through this runtime it is not obtainable without a native binding.
    winerror: "not-obtainable-in-stdlib",
  };
}

/** Node validates path arguments before any syscall; anything else is the OS refusing. */
function classify(err: ProbeError): { readonly createResult: "err_at_parse" | "err_at_syscall"; readonly errorStage: "parse" | "syscall" } {
  if (err.code.startsWith("ERR_INVALID_ARG")) return { createResult: "err_at_parse", errorStage: "parse" };
  return { createResult: "err_at_syscall", errorStage: "syscall" };
}

function joinPath(dir: string, name: string): string {
  return dir.endsWith(SEP) ? dir + name : dir + SEP + name;
}

function fullPath(dir: string, name: string, form: Form): string {
  return form === "extended" ? EXT + joinPath(dir, name) : joinPath(dir, name);
}

function sha256Of(data: Buffer): string {
  return createHash("sha256").update(data).digest("hex");
}

/** The payload bytes are pinned by spec/cases.yaml (rev6), handed in as hex, and default
 * to nothing: a probe that was not given the pinned bytes must fail rather than improvise. */
let pinnedPayload: Buffer | null = null;

function payload(): Buffer {
  if (pinnedPayload === null) throw new Error("the probe was started without --payload-hex; the payload is pinned by the spec");
  return pinnedPayload;
}

/**
 * Write through one pinned entry. Sync entries return immediately; the stream
 * entry returns a promise that settles on finish/close/error -- and if the device
 * behind the name never answers, it never settles, which is what `hang` records.
 */
type WriteOutcome = ProbeError | null;

function writeThrough(entry: string, path: string, data: Buffer): WriteOutcome | PromiseLike<WriteOutcome> {
  switch (entry) {
    case "writeFileSync":
    case "appendFileSync": {
      try {
        if (entry === "writeFileSync") writeFileSync(path, data);
        else appendFileSync(path, data);
        return null;
      } catch (err) {
        return describeError(err);
      }
    }
    case "createWriteStream": {
      return new Promise<WriteOutcome>((resolve) => {
        let settled = false;
        const finish = (value: WriteOutcome): void => {
          if (settled) return;
          settled = true;
          resolve(value);
        };
        let stream: ReturnType<typeof createWriteStream>;
        try {
          stream = createWriteStream(path);
        } catch (err) {
          finish(describeError(err));
          return;
        }
        stream.on("error", (err: unknown) => finish(describeError(err)));
        stream.on("finish", () => finish(null));
        stream.on("close", () => finish(null));
        try {
          stream.write(data);
          stream.end();
        } catch (err) {
          finish(describeError(err));
        }
      });
    }
    default:
      throw new Error(`entry is not in the pinned typescript/node list: ${JSON.stringify(entry)}`);
  }
}

async function settle(outcome: WriteOutcome | PromiseLike<WriteOutcome>): Promise<WriteOutcome> {
  if (outcome === null || outcome === undefined) return null;
  if (typeof outcome.then === "function") return await outcome;
  return outcome;
}

interface EnumReport {
  readonly listed: readonly string[];
  readonly landed: string | null;
  readonly matchedBy: "exact" | "only-listed-entry" | "none";
  readonly unclaimed: readonly string[];
  readonly bytesOnDisk: number | null;
  readonly statAgrees: boolean | null;
}

/**
 * Directory truth. The scratch dir is verified empty by the parent before the probe
 * runs and this probe is its only writer, so any entry it lists was made here:
 * an exact match, or the single listed entry (the name was mutated in transit).
 */
function enumerate(dir: string, requested: string): EnumReport {
  const listed = readdirSync(dir);
  const exact = listed.includes(requested);
  const landed = exact ? requested : listed.length === 1 ? listed[0] ?? null : null;
  const matchedBy: EnumReport["matchedBy"] = exact ? "exact" : landed !== null ? "only-listed-entry" : "none";
  return {
    listed,
    landed,
    matchedBy,
    unclaimed: landed === null ? listed : listed.filter((e) => e !== landed),
    bytesOnDisk: landed === null ? null : sizeOr(joinPath(dir, landed)),
    statAgrees: landed === null ? null : statWorks(joinPath(dir, landed)),
  };
}

function sizeOr(path: string): number | null {
  try {
    return statSync(path).size;
  } catch {
    return null;
  }
}

function statWorks(path: string): boolean {
  try {
    statSync(path);
    return true;
  } catch {
    return false;
  }
}

function createEvent(entry: string, form: Form, failure: ProbeError | null, ms: number, name: string, bytes: Buffer): Record<string, unknown> {
  const cls = failure === null ? null : classify(failure);
  return {
    ev: "create",
    entry,
    form,
    result: failure === null ? "ok" : (cls?.createResult ?? "err_at_syscall"),
    error_stage: failure === null ? "null" : (cls?.errorStage ?? "syscall"),
    error_code: failure?.code ?? null,
    error_errno: failure?.errno ?? null,
    error_winerror: failure?.winerror ?? null,
    error_message: failure?.message ?? null,
    bytes_written: failure === null ? bytes.length : null,
    payload_sha256: sha256Of(bytes),
    elapsed_ms: ms,
    name_len_triple: lengthTriple(name),
  };
}

function enumEvent(report: EnumReport, requested: string): Record<string, unknown> {
  return {
    ev: "enum",
    listed: report.listed,
    unclaimed: report.unclaimed,
    landed: report.landed,
    landed_hex: report.landed === null ? null : toHex(report.landed),
    matched_by: report.matchedBy,
    name_mutated: report.landed !== null && report.landed !== requested,
    bytes_on_disk: report.bytesOnDisk,
    enum_to_stat_agrees: report.statAgrees,
  };
}

async function runCell(a: Args, dir: string, name: string, entry: string, form: Form, data?: Buffer): Promise<void> {
  const bytes = data ?? payload();
  const started = process.hrtime.bigint();
  const failure = await settle(writeThrough(entry, fullPath(dir, name, form), bytes));
  const ms = Number((process.hrtime.bigint() - started) / 1000000n);
  emit(a.log, createEvent(entry, form, failure, ms, name, bytes));

  const report = enumerate(dir, name);
  emit(a.log, enumEvent(report, name));

  if (report.landed === null) {
    emit(a.log, { ev: "read", result: null, skipped_reason: "nothing landed, so no read was attempted" });
    return;
  }
  if (isReservedDeviceName(report.landed)) {
    emit(a.log, { ev: "read", result: null, skipped_reason: "reserved device name: this port never opens one for reading" });
    return;
  }
  try {
    const back = readFileSync(fullPath(dir, report.landed, form));
    emit(a.log, {
      ev: "read",
      result: back.length === 0 ? "eof" : "ok",
      bytes: back.length,
      sha256: sha256Of(back),
      roundtrip_ok: back.equals(bytes),
    });
  } catch (err) {
    const e = describeError(err);
    const invalidHandle = /invalid handle/i.test(e.message);
    emit(a.log, {
      ev: "read",
      result: invalidHandle ? "err6" : null,
      error_code: e.code,
      error_message: e.message,
      skipped_reason: invalidHandle ? null : "read failed with an outcome the closed read_result set does not name",
    });
  }
}

async function modeCell(a: Args): Promise<void> {
  await runCell(a, a.dir, decodeSample(a.nameHex), a.entry, a.form);
}

async function modeCanon(a: Args): Promise<void> {
  const name = decodeSample(a.nameHex);
  const data = payload();
  const path = joinPath(a.dir, name);
  writeFileSync(path, data);

  const shaMemory = sha256Of(data);
  const shaReadback = await new Promise<string>((resolve, reject) => {
    const hash = createHash("sha256");
    const stream = createReadStream(path);
    stream.on("data", (chunk: Buffer) => hash.update(chunk));
    stream.on("error", (err: unknown) => reject(err));
    stream.on("end", () => resolve(hash.digest("hex")));
  });

  emit(a.log, {
    ev: "canon",
    instrument_a: "sha256 over the in-memory payload before the write",
    instrument_b: "sha256 over createReadStream of the landed file",
    sha_memory: shaMemory,
    sha_readback: shaReadback,
    agree: shaMemory === shaReadback,
    bytes_written: data.length,
    bytes_on_disk: statSync(path).size,
    payload_sha256: shaMemory,
    name_len_triple: lengthTriple(name),
  });

  // the enumeration authority the other cells record, so this cell can say whether the directory list
  // and the stat of the same name agree -- it writes and reads the file, it just never listed it
  emit(a.log, enumEvent(enumerate(a.dir, name), name));
}

async function modeLen(a: Args): Promise<void> {
  // rev7: the component is the pinned filler the parent handed in as hex. Decoding it here,
  // rather than repeating a letter chosen by this file, is what makes name_source the truth.
  const name = decodeSample(a.nameHex);
  const comp = name.length;
  if (comp < 1) throw new Error("the length cell was given an empty component");
  if (a.comp !== "" && Number(a.comp) !== comp) {
    throw new Error(`--comp says ${a.comp} but the pinned name passed is ${comp} code units wide`);
  }
  const data = payload();
  const started = process.hrtime.bigint();
  const failure = await settle(writeThrough("writeFileSync", fullPath(a.dir, name, a.form), data));
  const ms = Number((process.hrtime.bigint() - started) / 1000000n);
  const report = enumerate(a.dir, name);
  // the same enumeration authority the trap probes record, so a length cell says what the
  // directory lists rather than only what the write returned
  emit(a.log, enumEvent(report, name));

  // The read-back leg. A length cell used to stop at "did it land", which left read_result,
  // roundtrip_ok and enum_to_stat_agrees unrecorded on 36 cells that had a real file sitting in the
  // scratch directory: the omission was my cell's question, not an unobservable fact. Reading the
  // pinned payload back is allowed here (the name is filler, never a device name), so the cell now
  // answers the round trip instead of declining it. Reserved names still stop the leg: this port does
  // not open the contents of a device name for any mode.
  if (report.landed === null) {
    emit(a.log, { ev: "read", result: null, skipped_reason: "nothing landed, so no read was attempted" });
  } else if (isReservedDeviceName(report.landed)) {
    emit(a.log, { ev: "read", result: null, skipped_reason: "reserved device name: this port never opens one for reading" });
  } else {
    try {
      const back = readFileSync(fullPath(a.dir, report.landed, a.form));
      emit(a.log, {
        ev: "read",
        result: back.length === 0 ? "eof" : "ok",
        bytes: back.length,
        sha256: sha256Of(back),
        roundtrip_ok: back.equals(data),
      });
    } catch (err) {
      const e = describeError(err);
      const invalidHandle = /invalid handle/i.test(e.message);
      emit(a.log, {
        ev: "read",
        result: invalidHandle ? "err6" : null,
        error_code: e.code,
        error_message: e.message,
        skipped_reason: invalidHandle ? null : "read failed with an outcome the closed read_result set does not name",
      });
    }
  }

  emit(a.log, {
    ev: "len",
    role: "grid_point",
    tier: a.tier,
    base_len: a.dir.length,
    comp_len: comp,
    total_len: a.dir.length + 1 + comp,
    form: a.form,
    result: failure === null ? "ok" : classify(failure).createResult,
    error_stage: failure === null ? "null" : classify(failure).errorStage,
    error_code: failure?.code ?? null,
    error_errno: failure?.errno ?? null,
    error_message: failure?.message ?? null,
    landed_len: report.landed === null ? null : report.landed.length,
    matched_by: report.matchedBy,
    bytes_written: failure === null ? data.length : null,
    bytes_on_disk: report.bytesOnDisk,
    elapsed_ms: ms,
  });
}

/** Predicate: the create returned clean AND this exact name is enumerated. */
function okAt(base: string, comp: number, form: Form, data: Buffer): boolean {
  const name = "a".repeat(comp);
  try {
    writeFileSync(fullPath(base, name, form), data);
  } catch {
    return false;
  }
  return enumerate(base, name).landed === name;
}

async function modeBisect(a: Args): Promise<void> {
  const data = payload();
  let lo = Number(a.lo);
  const hi0 = Number(a.hi);
  if (!Number.isInteger(lo) || !Number.isInteger(hi0) || hi0 <= lo) throw new Error(`bad bisect span ${a.lo}..${a.hi}`);
  if (!okAt(a.dir, lo, a.form, data)) throw new Error(`bisect lower bound ${lo} is not ok; the span is wrong for this base`);

  let hi = hi0;
  let probes = 1;
  while (lo + 1 < hi) {
    const mid = Math.floor((lo + hi) / 2);
    probes += 1;
    if (okAt(a.dir, mid, a.form, data)) lo = mid;
    else hi = mid;
  }

  // confirm the boundary with one more real create, so this cell can honestly carry
  // create_result=ok, which spec/canonical.md section 3 defines as "bytes_written recorded"
  const confirmName = "a".repeat(lo);
  const confirmPath = fullPath(a.dir, confirmName, a.form);
  let confirmFailure: ProbeError | null = null;
  try {
    writeFileSync(confirmPath, data);
  } catch (err) {
    confirmFailure = describeError(err);
  }
  const confirmReport = confirmFailure === null ? enumerate(a.dir, confirmName) : null;

  // The confirm file is a real entry with the pinned payload, so the boundary cell can answer the
  // same three fields every other cell answers: what the directory lists, whether stat agrees with
  // it, and whether the bytes come back. Before this the bisect cells published `null` for all three,
  // which read as an unobservable fact when it was only a leg this mode never ran.
  if (confirmReport !== null) {
    emit(a.log, enumEvent(confirmReport, confirmName));
    if (confirmReport.landed === null) {
      emit(a.log, { ev: "read", result: null, skipped_reason: "nothing landed, so no read was attempted" });
    } else if (isReservedDeviceName(confirmReport.landed)) {
      emit(a.log, { ev: "read", result: null, skipped_reason: "reserved device name: this port never opens one for reading" });
    } else {
      try {
        const back = readFileSync(fullPath(a.dir, confirmReport.landed, a.form));
        emit(a.log, {
          ev: "read",
          result: back.length === 0 ? "eof" : "ok",
          bytes: back.length,
          sha256: sha256Of(back),
          roundtrip_ok: back.equals(data),
        });
      } catch (err) {
        const e = describeError(err);
        const invalidHandle = /invalid handle/i.test(e.message);
        emit(a.log, {
          ev: "read",
          result: invalidHandle ? "err6" : null,
          error_code: e.code,
          error_message: e.message,
          skipped_reason: invalidHandle ? null : "read failed with an outcome the closed read_result set does not name",
        });
      }
    }
  }

  emit(a.log, {
    ev: "bisect",
    confirm_create_result: confirmFailure === null ? "ok" : classify(confirmFailure).createResult,
    confirm_error_code: confirmFailure?.code ?? null,
    confirm_bytes_written: confirmFailure === null ? data.length : null,
    confirm_bytes_on_disk: confirmReport?.bytesOnDisk ?? null,
    confirm_landed_len: confirmReport?.landed?.length ?? null,
    form: a.form,
    base_len: a.dir.length,
    last_ok_comp: lo,
    first_fail_comp: hi,
    total_path_at_last_ok: a.dir.length + 1 + lo,
    total_path_at_first_fail: a.dir.length + 1 + hi,
    probes,
    predicate: "writeFileSync returned without error AND the directory enumerates that exact name",
  });
}

async function modeZip(a: Args): Promise<void> {
  const archiveName = decodeSample(a.nameHex);
  const entryName = decodeSample(a.entryHex);
  const setBit11 = a.bit11 === "true";
  const data = payload();
  const packed = packZip([{ name: entryName, data }], setBit11);
  const archivePath = joinPath(a.dir, archiveName);

  // the archive write is itself the create leg of this cell, so it is instrumented
  await runCell(a, a.dir, archiveName, "writeFileSync", "plain", packed);
  emit(a.log, {
    ev: "zip_pack",
    packer: a.packer,
    bit11_set: setBit11,
    archive_bytes: packed.length,
    archive_sha256: sha256Of(packed),
    entry_name_sent: entryName,
    entry_name_sent_hex: toHex(entryName),
    entry_name_len_triple: lengthTriple(entryName),
  });

  if (a.extractor === "self_parser") {
    const back = unpackZip(readFileSync(archivePath));
    const first = back[0];
    if (first === undefined) throw new Error("self parser recovered no entry");
    let writeFailure: ProbeError | null = null;
    try {
      writeFileSync(joinPath(a.outDir, first.name), data);
    } catch (err) {
      writeFailure = describeError(err);
    }
    const report = writeFailure === null ? enumerate(a.outDir, first.name) : null;
    const landed = report?.landed ?? null;
    emit(a.log, {
      ev: "zip_extract",
      extractor: a.extractor,
      entry_name_back: first.name,
      entry_name_back_hex: toHex(first.name),
      name_was_utf8_flagged: first.nameWasUtf8Flagged,
      name_decoded_via: first.nameDecodedVia,
      crc_on_disk: first.crcOnDisk,
      crc_recomputed: first.crcRecomputed,
      size_back: first.size,
      landed,
      landed_hex: landed === null ? null : toHex(landed),
      write_error: writeFailure?.message ?? null,
      write_error_code: writeFailure?.code ?? null,
      roundtrip_ok: landed === entryName && first.name === entryName && first.crcOnDisk === first.crcRecomputed,
    });
    return;
  }

  if (a.extractor === "external_tool") {
    let rc: number | null = null;
    let toolError: ProbeError | null = null;
    let stdout = "";
    try {
      const out = execFileSync(a.tool, ["-xf", archivePath, "-C", a.outDir], {
        encoding: "buffer",
        // grandchild guard, so the whole probe stays inside the parent's external 5s
        timeout: 4000,
        maxBuffer: 1048576,
        windowsHide: true,
      });
      rc = 0;
      stdout = out.toString("utf8").slice(0, 200);
    } catch (err) {
      const e = err as { status?: unknown; stdout?: unknown };
      rc = typeof e.status === "number" ? e.status : null;
      toolError = describeError(err);
      stdout = typeof e.stdout === "string" ? e.stdout.slice(0, 200) : "";
    }
    let listed: string[] = [];
    try {
      listed = readdirSync(a.outDir);
    } catch {
      listed = [];
    }
    const landed = listed.length === 1 ? listed[0] ?? null : null;
    emit(a.log, {
      ev: "zip_extract",
      extractor: a.extractor,
      tool: a.tool,
      tool_rc: rc,
      tool_stdout: stdout,
      tool_error: toolError?.message ?? null,
      listed,
      landed,
      landed_hex: landed === null ? null : toHex(landed),
      roundtrip_ok: landed === entryName,
    });
    return;
  }

  throw new Error(`unknown extractor ${JSON.stringify(a.extractor)}`);
}

async function main(): Promise<void> {
  const a = readArgs(process.argv.slice(2));
  if (a.payloadHex === "") throw new Error("--payload-hex is required: rev6 pins the 28 control bytes");
  pinnedPayload = Buffer.from(a.payloadHex, "hex");
  emit(a.log, {
    ev: "start",
    mode: a.mode,
    entry: a.entry,
    form: a.form,
    pid: process.pid,
    node: process.version,
    exec_path: process.execPath,
    platform: process.platform,
    arch: process.arch,
  });

  switch (a.mode) {
    case "cell":
      await modeCell(a);
      break;
    case "canon":
      await modeCanon(a);
      break;
    case "len":
      await modeLen(a);
      break;
    case "bisect":
      await modeBisect(a);
      break;
    case "zip":
      await modeZip(a);
      break;
  }

  emit(a.log, { ev: "done" });
}

try {
  await main();
} catch (err) {
  const e = err as Error & { code?: string; errno?: number };
  const logIdx = process.argv.indexOf("--log");
  const logPath = logIdx >= 0 ? process.argv[logIdx + 1] : undefined;
  if (logPath !== undefined) {
    appendFileSync(
      logPath,
      JSON.stringify({
        ev: "probe_crash",
        message: String(e.message ?? err),
        code: e.code ?? null,
        errno: e.errno ?? null,
      }) + "\n",
    );
  }
  process.exitCode = 9;
}
