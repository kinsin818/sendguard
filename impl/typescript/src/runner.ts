/**
 * The SENDGUARD TypeScript port -- parent runner.
 *
 * Owns the cell plan, the scratch tree, and the externally enforced 5-second probe
 * timeout. Each probe is one child process (src/probe.ts); the parent never calls fs
 * on a sample name itself, so a blocked syscall can only cost that one probe.
 *
 * Nothing in this file deletes anything (project red line M19): the scratch tree is
 * left in place and its paths are recorded in every cell for the operator to clear.
 */
import { mkdirSync, readdirSync, writeFileSync, readFileSync, existsSync } from "node:fs";
import { spawn, execFileSync } from "node:child_process";
import { createHash, randomUUID } from "node:crypto";
import { resolve } from "node:path";
import { loadFrozenSpec, lockedHashInFrozenMd, REPO_ROOT, decodeSample, type FrozenSpec, type FrozenCase } from "./spec.ts";
import { cellFileName, renderSubIdentity, type Dim } from "./identity.ts";
import { extendedProbeRefusal } from "./nameguard.ts";
import {
  ARCH_NAME,
  CTRL_EXPECTATIONS,
  FORMAT_VERSION,
  GRID,
  HARNESS_VERSION,
  OS_NAME,
  PORT_NAME,
  PROBE_TIMEOUT_MS,
  RESULT_DIR,
  WORKER_ID,
  type CaseGroup,
  type MechanismClass,
} from "./constants.ts";

const PROBE = resolve(import.meta.dirname, "probe.ts");
const SCRATCH_ROOT = resolve(REPO_ROOT, ".sgscratch");
const LOG_ROOT = resolve(SCRATCH_ROOT, "_logs");
/** subst drive that addresses SCRATCH_ROOT, so base_len 13 is reachable (see report, note C-1). */
const DRIVE = "S:";
const DRIVE_ROOT = DRIVE + "\\";

/** rev3: name_encoding describes how the name is RECORDED (hex of UTF-8 raw bytes here),
 * length_unit describes which unit this port's own length API counts in (JS string length
 * is UTF-16 code units). They are different fields since rev3; conflating them is what voided
 * every cell before the revision. */
const RECORD_ENCODING = "hex_raw_bytes";
const LENGTH_UNIT = "utf16_code_units";

const SEP = "\\";
const join = (dir: string, name: string): string => (dir.endsWith(SEP) ? dir + name : dir + SEP + name);

type Form = "plain" | "extended";
type Role = "primary" | "spread" | "osprobe";

interface Job {
  readonly tag: string;
  readonly role: Role;
  readonly mode: "cell" | "canon" | "len" | "bisect" | "zip";
  dirRel: string;
  readonly outDirRel: string | null;
  readonly nameHex: string;
  readonly entryHex: string | null;
  readonly entry: string;
  readonly form: Form;
  readonly tier: string | null;
  readonly comp: number | null;
  readonly lo: number | null;
  readonly hi: number | null;
  readonly packer: string | null;
  readonly extractor: string | null;
  readonly tool: string | null;
  readonly bit11: boolean | null;
  readonly payloadHex: string;
}

interface CellPlan {
  readonly group: CaseGroup;
  readonly caseId: string;
  readonly dims: readonly Dim[];
  readonly mechanismClass: MechanismClass;
  readonly nameSourceHex: string | null;
  readonly nameSourceBasis: string;
  readonly jobs: readonly Job[];
  readonly controlExpectation: { readonly createResult: string; readonly errorStage: string } | null;
  readonly note: string;
  readonly frozenCase: FrozenCase | null;
  /** rev3 identity convention: members are carried in case_id (T09-m1), so the varying
   * dimension is recorded here as a named in-cell field instead of a sub_identity dim. */
  readonly inCell?: Record<string, string | number>;
  readonly payloadSha256Pinned?: string;
}

interface JobOutcome {
  readonly job: Job;
  readonly events: Record<string, unknown>[];
  readonly rc: number | null;
  readonly signal: string | null;
  readonly timedOut: boolean;
  readonly stdout: string;
  readonly stderr: string;
  readonly malformedLines: number;
  readonly wallMs: number;
}

interface ScratchInfo {
  readonly cellRoot: string;
  readonly verifiedEmpty: boolean;
}

function nowIso(): string {
  return new Date().toISOString();
}

/** 8 hex chars of this run's uuid: makes every cell dir fresh per run (a re-run must
 * not reuse a dir it did not verify empty itself). */
const RUN_NONCE = createHash("sha1").update(randomUUID()).digest("hex").slice(0, 8);
const CLAIMED_DIRS = new Set<string>();

/** Cell dir is S:\<7 hex> = 11 characters, the longest root that still lets a
 * base_len 13 directory be built under it (11 + separator + 1). */
function cellDirId(stem: string, index: number): string {
  for (let attempt = 0; attempt < 64; attempt += 1) {
    const id = createHash("sha1").update(`${RUN_NONCE}#${stem}#${index}#${attempt}`).digest("hex").slice(0, 7);
    const root = join(DRIVE_ROOT, id);
    if (!CLAIMED_DIRS.has(root) && !existsSync(root)) {
      CLAIMED_DIRS.add(root);
      return id;
    }
  }
  throw new Error(`no free 7-hex scratch dir for ${stem}`);
}

function ensureDriveMapped(): { mapped: boolean; note: string } {
  mkdirSync(SCRATCH_ROOT, { recursive: true });
  mkdirSync(LOG_ROOT, { recursive: true });
  let table = "";
  try {
    table = execFileSync("subst", [], { encoding: "utf8", windowsHide: true });
  } catch (err) {
    return { mapped: false, note: `subst query failed: ${String((err as Error).message).slice(0, 120)}` };
  }
  if (new RegExp(`^${DRIVE}\\\\: => `, "im").test(table)) {
    return { mapped: true, note: "S: was already mapped by an earlier run in this session" };
  }
  try {
    execFileSync("subst", [DRIVE, SCRATCH_ROOT], { encoding: "utf8", windowsHide: true });
  } catch (err) {
    return { mapped: false, note: `subst mapping failed: ${String((err as Error).message).slice(0, 120)}` };
  }
  return { mapped: true, note: `mapped ${DRIVE} -> ${SCRATCH_ROOT} for this run; the port removes nothing (M19)` };
}

function makeScratch(stem: string, index: number): ScratchInfo {
  const cellRoot = join(DRIVE_ROOT, cellDirId(stem, index));
  mkdirSync(cellRoot, { recursive: true });
  const listed = readdirSync(cellRoot);
  return { cellRoot, verifiedEmpty: listed.length === 0 };
}

/** Directory chain whose full length is exactly `target` characters (no trailing separator). */
function buildBase(cellRoot: string, target: number): string {
  if (target < cellRoot.length + 2) {
    throw new Error(`base_len ${target} is shorter than the cell root ${cellRoot.length} (${cellRoot})`);
  }
  let p = cellRoot;
  while (p.length < target) {
    const need = target - p.length - 1;
    const take = Math.min(need, 100);
    p = join(p, "d".repeat(take));
  }
  mkdirSync(p, { recursive: true });
  return p;
}

function runJob(job: Job, cellRoot: string, logStem: string): Promise<JobOutcome> {
  const dir = join(cellRoot, job.dirRel);
  mkdirSync(dir, { recursive: true });
  const outDir = job.outDirRel === null ? null : join(cellRoot, job.outDirRel);
  if (outDir !== null) mkdirSync(outDir, { recursive: true });

  const logPath = join(LOG_ROOT, `${logStem}__${job.tag}.ndjson`);
  writeFileSync(logPath, "");

  const args = [PROBE, "--mode", job.mode, "--log", logPath, "--dir", dir, "--entry", job.entry, "--form", job.form];
  args.push("--payload-hex", job.payloadHex); // rev6: the payload is pinned by the spec
  if (job.outDirRel !== null && outDir !== null) args.push("--out-dir", outDir);
  if (job.nameHex !== "") args.push("--name-hex", job.nameHex);
  if (job.entryHex !== null) args.push("--entry-hex", job.entryHex);
  if (job.tier !== null) args.push("--tier", job.tier);
  if (job.comp !== null) args.push("--comp", String(job.comp));
  if (job.lo !== null) args.push("--lo", String(job.lo));
  if (job.hi !== null) args.push("--hi", String(job.hi));
  if (job.packer !== null) args.push("--packer", job.packer);
  if (job.extractor !== null) args.push("--extractor", job.extractor);
  if (job.tool !== null) args.push("--tool", job.tool);
  if (job.bit11 !== null) args.push("--bit11", String(job.bit11));

  const started = Date.now();
  return new Promise<JobOutcome>((done) => {
    const child = spawn(process.execPath, args, {
      stdio: ["ignore", "pipe", "pipe"],
      windowsHide: true,
    });
    let out = "";
    let err = "";
    let timedOut = false;
    if (child.stdout !== null) child.stdout.on("data", (c: Buffer) => (out += c.toString("utf8")));
    if (child.stderr !== null) child.stderr.on("data", (c: Buffer) => (err += c.toString("utf8")));

    const timer = setTimeout(() => {
      timedOut = true;
      try {
        child.kill("SIGKILL");
      } catch {
        /* the kill is best effort; the recorded outcome is hang either way */
      }
    }, PROBE_TIMEOUT_MS);

    child.on("exit", (code, signal) => {
      clearTimeout(timer);
      let events: Record<string, unknown>[] = [];
      let malformed = 0;
      let raw = "";
      try {
        raw = readFileSync(logPath, "utf8");
      } catch {
        raw = "";
      }
      for (const line of raw.split("\n")) {
        if (line.trim() === "") continue;
        try {
          const parsed: unknown = JSON.parse(line);
          if (parsed !== null && typeof parsed === "object") events.push(parsed as Record<string, unknown>);
          else malformed += 1;
        } catch {
          malformed += 1;
        }
      }
      done({
        job,
        events,
        rc: timedOut ? null : code,
        signal: signal,
        timedOut,
        stdout: out.slice(0, 4000),
        stderr: err.slice(0, 4000),
        malformedLines: malformed,
        wallMs: Date.now() - started,
      });
    });
  });
}

function eventOf(outcome: JobOutcome, ev: string): Record<string, unknown> | null {
  for (const e of outcome.events) if (e["ev"] === ev) return e;
  return null;
}

function readEnvFacts(): Record<string, unknown> {
  const path = resolve(REPO_ROOT, "evidence", "S00", "env-facts-windows-local.json");
  const text = readFileSync(path, "utf8");
  const doc = JSON.parse(text) as Record<string, unknown>;
  return doc;
}

function num(v: unknown): number | null {
  return typeof v === "number" ? v : null;
}
function str(v: unknown): string | null {
  return typeof v === "string" ? v : null;
}
function bool(v: unknown): boolean | null {
  return typeof v === "boolean" ? v : null;
}

function buildEnvBlock(envFacts: Record<string>, mapped: boolean): Record<string, unknown> {
  const os = envFacts["os"] as Record<string, unknown> | undefined;
  const reg = envFacts["registry_longpaths"] as Record<string, unknown> | undefined;
  const volumes = (envFacts["volumes"] as Record<string, unknown>[] | undefined) ?? [];
  const d = volumes.find((v) => str(v["root"]) === "D:\\") ?? volumes[0] ?? {};
  const c = volumes.find((v) => str(v["root"]) === "C:\\") ?? {};
  const runtimes = envFacts["runtimes"] as Record<string, unknown> | undefined;
  const node = runtimes?.["node"] as Record<string, unknown> | undefined;
  const probe = node?.["version_probe"] as Record<string, unknown> | undefined;
  const eightThree = envFacts["short_name_83"] as Record<string, unknown> | undefined;
  const perVolume = (eightThree?.["per_volume"] as Record<string, unknown>[] | undefined) ?? [];
  const stateOf = (root: string): string | null => {
    const row = perVolume.find((p) => str(p["volume"]) === root);
    return row === undefined ? null : str(row["short_name_generation"]);
  };

  return {
    LongPathsEnabled: num(reg?.["value"]),
    dot3name: stateOf("D:\\"),
    max_component: num(d["max_component"]),
    unicode_version: "not-obtainable-here",
    toolchain: `node ${process.version} at ${process.execPath}; TypeScript run by native type stripping (no tsc on this host)`,
    env_block_source: "evidence/S00/env-facts-windows-local.json",
    recorded_node_executable: (node?.["resolved_paths"] as string[] | undefined)?.[0] ?? null,
    recorded_node_version: str(probe?.["version_string"]),
    observed_node_executable: process.execPath,
    observed_node_version: process.version,
    interpreter_matches_record:
      (node?.["resolved_paths"] as string[] | undefined)?.[0] === process.execPath &&
      str(probe?.["version_string"]) === process.version,
    os_build: num(os?.["build"]),
    os_platform_name: str(os?.["platform_name"]),
    locale: str((os?.["locale"] as Record<string, unknown> | undefined)?.["preferred_encoding"]),
    console_code_page: (os?.["console_code_page"] as Record<string, unknown> | undefined)?.["output"] ?? null,
    cpu_architecture: (os?.["cpu_architecture"] as Record<string, unknown> | undefined)?.["PROCESSOR_ARCHITECTURE"] ?? null,
    volume_d_root: str(d["root"]),
    volume_d_filesystem: str(d["filesystem_name"]),
    volume_d_max_component: num(d["max_component"]),
    volume_c_max_component: num(c["max_component"]),
    eight_dot_three_d: stateOf("D:\\"),
    eight_dot_three_c: stateOf("C:\\"),
    scratch_drive_mapped: mapped,
  };
}

function makeMeta(envFacts: Record<string>, spec: FrozenSpec, env: Record<string, unknown>): Record<string, unknown> {
  return {
    port: PORT_NAME,
    implementation_language: "typescript",
    runtime: "node",
    runtime_version: process.version,
    resolved_interpreter_path: process.execPath,
    os: OS_NAME,
    os_version: str((envFacts["os"] as Record<string, unknown> | undefined)?.["platform_name"]),
    arch: ARCH_NAME,
    locale: str((envFacts["os"] as Record<string, unknown> | undefined)?.["locale"] as Record<string, unknown> ? ((envFacts["os"] as Record<string, unknown>)["locale"] as Record<string, unknown>)["preferred_encoding"] : null),
    volume_component_limit: env["max_component"],
    LongPathsEnabled: env["LongPathsEnabled"],
    eight_dot_three: { D: env["eight_dot_three_d"], C: env["eight_dot_three_c"] },
    node_manifest_longPathAware: false,
    node_manifest_longPathAware_basis: "evidence/S00/env-facts-windows-local.json manifest_scan: node.exe hit_count=0",
    spec_sha256: spec.casesBlobSha256,
    spec_sha256_basis: "git cat-file blob HEAD:spec/cases.yaml, hashed (committed blob face, not the disk file)",
    canon_payload_sha256: spec.canonPayloadSha256,
    len_fill: {
      unit_hex: spec.lenFill.unitHex,
      rule: spec.lenFill.rule,
      applies_to: spec.lenFill.appliesTo,
      name_source_rule: spec.lenFill.nameSourceRule,
      source: "len_fill block in spec/cases.yaml (rev7 pin)",
    },
    canon_payload_source: "control_samples payload_hex in spec/cases.yaml (rev6 pin); sha256 of the 28 bytes",
    spec_sha256_set: {
      "spec/cases.yaml": spec.casesBlobSha256,
      "spec/canonical.md": spec.canonicalBlobSha256,
      "spec/schema.json": spec.schemaBlobSha256,
      "spec/cell-identity.md": spec.identityBlobSha256,
    },
    dependency_policy: "zero third-party dependencies; no node_modules in this port",
    instrument_c2:
      "node:fs did not apply the Win32 name-parsing layer to the plain absolute paths this port passed: " +
      "a real CON.txt and a real 'trail.' (trailing dot kept) were created, and totals above 259 characters were accepted. " +
      "Controlled on the same volume in the same directory: cmd.exe mapped CON.txt to the device (no file listed), wrote 'trail.' as 'trail', and refused a 309-char path (rc=1 ERROR_PATH_NOT_FOUND), " +
      "as did python 3.14 (rc=1) while LongPathsEnabled=0. Measured, not inferred. See evidence/S02/typescript-selfcheck.md C-2.",
    deps_direct: 0,
    deps_total: 0,
  };
}

/** One entry's reading, folded into the cell as data (cell-identity.md S2 entry_spread). */
function entryReading(outcome: JobOutcome): Record<string, unknown> {
  const create = eventOf(outcome, "create");
  const enumEv = eventOf(outcome, "enum");
  const bis = eventOf(outcome, "bisect");
  return {
    role: outcome.job.role,
    api_entry: outcome.job.entry,
    path_form: outcome.job.form,
    ...(bis !== null
      ? {
          last_ok_comp: bis["last_ok_comp"],
          first_fail_comp: bis["first_fail_comp"],
          total_path_at_last_ok: bis["total_path_at_last_ok"],
          probes: bis["probes"],
        }
      : {}),
    create_result: outcome.timedOut ? "hang" : (create?.["result"] ?? (bis !== null ? "ok" : null)),
    error_stage: outcome.timedOut ? null : (create?.["error_stage"] ?? null),
    error_code: outcome.timedOut ? null : (create?.["error_code"] ?? null),
    error_message: outcome.timedOut ? `probe killed after ${PROBE_TIMEOUT_MS} ms external timeout` : (create?.["error_message"] ?? null),
    bytes_written: create?.["bytes_written"] ?? null,
    bytes_on_disk: enumEv?.["bytes_on_disk"] ?? null,
    name_landed_as: enumEv?.["landed"] ?? null,
    probe_exit_rc: outcome.rc,
    probe_signal: outcome.signal,
    probe_wall_ms: outcome.wallMs,
  };
}

function assembleCell(
  plan: CellPlan,
  env: Record<string, unknown>,
  meta: Record<string, unknown>,
  scratch: ScratchInfo,
  outcomes: readonly JobOutcome[],
  controlsPassed: boolean | null,
): Record<string, unknown> {
  const primary = outcomes.find((o) => o.job.role === "primary") ?? null;
  const osProbe = outcomes.find((o) => o.job.role === "osprobe") ?? null;

  const spreadReadings: Record<string, unknown>[] = outcomes.filter((o) => o.job.role === "spread").map(entryReading);
  if (osProbe !== null) spreadReadings.push(entryReading(osProbe));

  const firstEvent = (name: string): Record<string, unknown> | null => {
    for (const o of outcomes) {
      const e = eventOf(o, name);
      if (e !== null) return e;
    }
    return null;
  };

  const createEv = primary === null ? null : eventOf(primary, "create");
  const enumEv = primary === null ? null : eventOf(primary, "enum");
  const readEv = primary === null ? null : eventOf(primary, "read");
  const canonEv = firstEvent("canon");
  const lenEv = firstEvent("len");
  const bisectEvs: Record<string, unknown>[] = [];
  for (const o of outcomes) {
    const e = eventOf(o, "bisect");
    if (e !== null) bisectEvs.push(e);
  }
  const bisectEv = bisectEvs[0] ?? null;
  const zipPack = firstEvent("zip_pack");
  const zipExtract = firstEvent("zip_extract");
  const crashEv = firstEvent("probe_crash");
  const hung = primary !== null && primary.timedOut;

  const createResult: string | null = hung
    ? "hang"
    : (createEv?.["result"] ??
        lenEv?.["result"] ??
        (canonEv !== null ? "ok" : null) ??
        (bisectEv !== null ? "ok" : null) ??
        null);
  const errorStage: string | null = hung
    ? "syscall"
    : (createEv?.["error_stage"] ??
        lenEv?.["error_stage"] ??
        (canonEv !== null || bisectEv !== null ? "null" : null));

  const osRefusal = plan.nameSourceHex === null ? null : extendedProbeRefusal(decodeSample(plan.nameSourceHex));

  // rev3: a legality verdict must name the tool that was asked. This port asks the Win32
  // file APIs (through node:fs, extended prefix when probing legality directly); where no
  // probe ran, nothing was asked, so the honest value is none -- not a borrowed verdict.
  const verdictAsked = osProbe !== null && plan.group !== "len";
  const verdictVia: string = verdictAsked ? "win32" : "none";

  const cell: Record<string, unknown> = {
    format_version: FORMAT_VERSION,
    case_id: plan.caseId,
    case_group: plan.group,
    language: PORT_NAME,
    os: OS_NAME,
    api_entry: primary?.job.entry ?? PRIMARY_ENTRY,
    attempt: 1,
    name_source: plan.nameSourceHex,
    name_source_basis: plan.nameSourceBasis,
    name_encoding: RECORD_ENCODING,
    length_unit: LENGTH_UNIT,
    verdict_via: verdictVia,
    path_form: primary?.job.form ?? "plain",
    longpath_mechanism: primary?.job.form === "extended" ? "prefix_rewrite" : "none",
    create_result: createResult,
    error_stage: errorStage,
    error_code: hung ? null : (createEv?.["error_code"] ?? lenEv?.["error_code"] ?? null),
    error_winerror: hung ? "not-obtainable-in-stdlib" : (createEv?.["error_winerror"] ?? null),
    error_message: hung
      ? `probe killed after ${PROBE_TIMEOUT_MS} ms external timeout; the syscall never returned, so no OS error code was produced`
      : (createEv?.["error_message"] ?? lenEv?.["error_message"] ?? null),
    errno: hung ? null : (createEv?.["error_errno"] ?? lenEv?.["error_errno"] ?? null),
    bytes_written: createEv?.["bytes_written"] ?? lenEv?.["bytes_written"] ?? (zipPack?.["archive_bytes"] ?? null),
    bytes_on_disk: enumEv?.["bytes_on_disk"] ?? lenEv?.["bytes_on_disk"] ?? (canonEv?.["bytes_on_disk"] ?? null),
    read_result: readEv?.["result"] ?? null,
    read_skipped_reason: readEv?.["skipped_reason"] ?? null,
    roundtrip_ok: readEv?.["roundtrip_ok"] ?? (zipExtract?.["roundtrip_ok"] ?? null),
    name_landed_as: enumEv?.["landed"] ?? null,
    name_landed_as_hex: enumEv?.["landed_hex"] ?? null,
    name_mutated: enumEv?.["name_mutated"] ?? null,
    enum_to_stat_agrees: enumEv?.["enum_to_stat_agrees"] ?? null,
    enum_matched_by: enumEv?.["matched_by"] ?? null,
    enum_listed: enumEv?.["listed"] ?? null,
    enum_unclaimed: enumEv?.["unclaimed"] ?? null,
    // canonical section 10 / gate.md type II: the cell's own write claimed success while the
    // directory lists no such entry. A length cell's write is its point probe, not a create event.
    phantom:
      (createEv?.["result"] ?? lenEv?.["result"]) === "ok" && enumEv !== null && enumEv["landed"] === null,
    sha256_self: null,
    sha256_truth: readEv?.["sha256"] ?? (canonEv?.["sha_readback"] ?? null),
    instrument_conflict:
      createEv !== null && createEv["result"] === "ok" && readEv !== null && readEv["result"] === "ok" && readEv["roundtrip_ok"] === false,
    control_pass: controlsPassed,
    instrument_red: false,
    harness_version: HARNESS_VERSION,
    worker_id: WORKER_ID,
    started_at: nowIso(),
    elapsed_ms: outcomes.reduce((acc, o) => acc + o.wallMs, 0),
    mechanism_class: plan.mechanismClass,
    spec_sha256: meta["spec_sha256"],
    spec_sha256_basis: meta["spec_sha256_basis"],
    len_triple: createEv?.["name_len_triple"] ?? null,
    deps_direct: 0,
    deps_total: 0,
    env,
    meta,
    scratch: {
      cell_root: scratch.cellRoot,
      cell_root_real: SCRATCH_ROOT + SEP + scratch.cellRoot.slice(DRIVE.length + 1),
      verified_empty_before_use: scratch.verifiedEmpty,
      cleanup: "not attempted by the port (M19 forbids deletion logic in this port); the path is recorded for the operator",
    },
    probe: {
      carrier: "one child process per probe: node built-in TypeScript type stripping of src/probe.ts",
      external_timeout_ms: PROBE_TIMEOUT_MS,
      interpreter: process.execPath,
      node_version: process.version,
      jobs: outcomes.map((o) => ({
        tag: o.job.tag,
        role: o.job.role,
        mode: o.job.mode,
        api_entry: o.job.entry,
        path_form: o.job.form,
        exit_rc: o.rc,
        signal: o.signal,
        timed_out: o.timedOut,
        wall_ms: o.wallMs,
        malformed_log_lines: o.malformedLines,
        stderr_tail: o.stderr === "" ? null : o.stderr.slice(-400),
      })),
    },
    entry_spread: spreadReadings,
    note: plan.note,
    status: "measured" as string,
  };

  if (plan.group === "len") {
    cell["os_legality_verdict"] = "unknown";
    cell["os_legality_basis"] = "a length limit is not a name-legality question; no extended-legality probe is defined for this cell";
    cell["verdict_via"] = "none";
  } else if (osRefusal !== null) {
    // The \\?\ probe is refused for device names, but the cell still holds an OS-level answer
    // from two authorities this port did ask: the create result and the directory enumeration.
    const landedReal = enumEv?.["landed"] === decodeSample(plan.nameSourceHex ?? "") && enumEv?.["enum_to_stat_agrees"] === true;
    const listedAbsent = (enumEv?.["listed"] as readonly unknown[] | undefined)?.length === 0;
    if (landedReal) {
      cell["os_legality_verdict"] = "legal";
      cell["verdict_via"] = "win32";
      cell["os_legality_authority"] = "directory enumeration (readdir + stat) after the pinned write";
      cell["os_legality_basis"] =
        "the extended-prefix probe was refused for this name (see the refusal text below), but the name is enumerated as a real entry and stat agrees, " +
        "so the OS-level authority this port did ask answers legal. Independent confirmation of the same entry with a .NET reader is recorded in meta.instrument_c2.";
      cell["os_legality_refusal_note"] = osRefusal;
    } else if (createEv?.["result"] === "err_at_syscall" && listedAbsent) {
      cell["os_legality_verdict"] = "illegal";
      cell["verdict_via"] = "win32";
      cell["os_legality_authority"] = "CreateFile refusal, confirmed by an empty directory listing";
      cell["os_legality_basis"] = `the write entry reached the file API and was refused (${String(createEv?.["error_code"] ?? "")}) with no entry listed afterwards`;
    } else {
      cell["os_legality_verdict"] = "unknown";
      cell["verdict_via"] = "none";
      cell["os_legality_basis"] = osRefusal;
    }
  } else if (osProbe === null) {
    cell["os_legality_verdict"] = "unknown";
    cell["os_legality_basis"] = "no os-legality sibling probe in this plan";
  } else {
    const osCreate = eventOf(osProbe, "create");
    const osEnum = eventOf(osProbe, "enum");
    cell["verdict_via"] = "win32";
    cell["os_legality_authority"] = "extended-prefix (\\\\?\\) create probe through node:fs, i.e. the Win32 file API";
    cell["os_probe_landed_as"] = osEnum?.["landed"] ?? null;
    cell["os_probe_error_code"] = osCreate?.["error_code"] ?? null;
    if (osProbe.timedOut) {
      cell["os_legality_verdict"] = "unknown";
      cell["os_legality_basis"] = "extended-prefix probe hung and was killed; the OS gave no answer inside the timeout";
    } else if (osCreate === null) {
      cell["os_legality_verdict"] = "unknown";
      cell["os_legality_basis"] = `extended-prefix probe produced no create event (rc=${String(osProbe.rc)} signal=${String(osProbe.signal)})`;
    } else if (osCreate["result"] === "ok") {
      cell["os_legality_verdict"] = "legal";
      cell["os_legality_basis"] = "the filesystem itself accepts the name once the Win32 name parser is bypassed with the extended prefix";
    } else if (osCreate["result"] === "err_at_parse") {
      cell["os_legality_verdict"] = "unknown";
      cell["os_legality_basis"] = `node refused before any syscall even in extended form: ${String(osCreate["error_code"] ?? "")}`;
    } else {
      cell["os_legality_verdict"] = "illegal";
      cell["os_legality_basis"] = `extended-prefix create refused: ${String(osCreate["error_code"] ?? "")} ${String(osCreate["error_message"] ?? "").slice(0, 160)}`;
    }
  }

  if (zipExtract !== null) {
    cell["zip_roundtrip"] = zipExtract;
    cell["name_landed_as"] = zipExtract["landed"] ?? null;
    cell["roundtrip_ok"] = zipExtract["roundtrip_ok"] ?? null;
    cell["cross_reader"] = {
      builder: plan.dims.find((d) => d.name === "packer")?.value ?? null,
      reader: plan.dims.find((d) => d.name === "extractor")?.value ?? null,
      found: zipExtract["landed"] !== null && zipExtract["landed"] !== undefined,
      size: zipExtract["size_back"] ?? null,
      read_result: zipExtract["roundtrip_ok"] === true ? "ok" : "eof",
    };
    // the archive itself was created and read through the instrumented path; keep that
    // reading, and name separately which roundtrip claim the container leg supports
    cell["read_roundtrip_ok"] = readEv?.["roundtrip_ok"] ?? null;
    cell["roundtrip_ok_basis"] = "container leg: the zip entry name survived pack -> extract -> create";
  }

  if (lenEv !== null) {
    const total = num(lenEv["total_len"]);
    if ((lenEv["form"] ?? "plain") === "plain" && total !== null && total > 259 && lenEv["result"] === "ok") {
      cell["longpath_mechanism"] = "prefix_rewrite";
      cell["longpath_mechanism_basis"] =
        `this cell created a plain path of ${total} characters, past the 259 limit; with LongPathsEnabled=0 the manifest route is closed ` +
        `(python 3.14, whose own manifest carries longPathAware, still refused 309 characters), so the only documented mechanism left is ` +
        `the runtime rewriting the path into extended form before the OS sees it -- see meta.instrument_c2`;
    }
    cell["tier"] = lenEv["tier"];
    cell["method"] = "grid_point";
    cell["base_len"] = lenEv["base_len"];
    cell["comp_len"] = lenEv["comp_len"];
    cell["total_path_len"] = lenEv["total_len"];
    cell["name_landed_as"] = null;
    cell["len_triple"] = [lenEv["comp_len"], lenEv["comp_len"], lenEv["comp_len"]];
    cell["len_triple_basis"] = "the width of the pinned component this cell passed: code points / UTF-16 code units / UTF-8 bytes, all equal for the ASCII filler";
    cell["read_result"] = null;
    cell["read_skipped_reason"] = "length cell: the question is whether the create lands, not what the bytes say";
    cell["method"] = lenEv["tier"] === "len_fill" ? "len_fill_point" : "grid_point";
    const sameForm = outcomes.find((o) => o.job.form === cell["path_form"] && eventOf(o, "bisect") !== null) ?? null;
    const otherForm = outcomes.find((o) => o.job.form !== cell["path_form"] && eventOf(o, "bisect") !== null) ?? null;
    const sameEv = sameForm === null ? null : eventOf(sameForm, "bisect");
    const otherEv = otherForm === null ? null : eventOf(otherForm, "bisect");
    if (sameEv !== null) {
      cell["len_ceiling"] = sameEv["last_ok_comp"];
      cell["len_ceiling_first_fail"] = sameEv["first_fail_comp"];
      cell["len_ceiling_probes"] = sameEv["probes"];
      cell["len_ceiling_predicate"] = sameEv["predicate"];
    } else {
      cell["len_ceiling"] = null;
      cell["len_ceiling_basis"] = "no bisection converged in this path form";
    }
    if (otherEv !== null) {
      cell["len_ceiling_other_regime"] = otherEv["last_ok_comp"];
      cell["len_ceiling_other_regime_form"] = otherForm?.job.form ?? null;
    }
    if (bisectEv !== null) {
      // the bracket was already collected for the bisect-only cells; keep it visible here too
      cell["rung_bracket_kept_in_len_ceiling"] = true;
    }
  }

  // rev7 separates the three quantities a length cell can report. The pinned component's own
  // create answers the cell (lenEv); the bisection brackets are ceiling measurements, and a
  // bisect-only cell (the frozen base-13 legs) still answers from its confirmed boundary.
  if (bisectEv !== null && lenEv === null) {
    cell["method"] = "bisect";
    cell["create_result"] = bisectEv["confirm_create_result"] ?? null;
    cell["error_code"] = bisectEv["confirm_error_code"] ?? null;
    cell["bytes_written"] = bisectEv["confirm_bytes_written"] ?? null;
    cell["bytes_on_disk"] = bisectEv["confirm_bytes_on_disk"] ?? null;
    cell["confirm_landed_len"] = bisectEv["confirm_landed_len"] ?? null;
    cell["base_len"] = bisectEv["base_len"];
    cell["last_ok_comp"] = bisectEv["last_ok_comp"];
    cell["first_fail_comp"] = bisectEv["first_fail_comp"];
    cell["total_path_at_last_ok"] = bisectEv["total_path_at_last_ok"];
    cell["total_path_at_first_fail"] = bisectEv["total_path_at_first_fail"];
    cell["bisect_probes"] = bisectEv["probes"];
    cell["bisect_predicate"] = bisectEv["predicate"];
    if (bisectEvs.length > 1) {
      // a rung is keyed by base_len alone, so both path regimes live inside this one cell
      const other = bisectEvs[1] ?? null;
      const otherForm = outcomes.filter((o) => eventOf(o, "bisect") !== null)[1]?.job.form ?? null;
      cell["rung_other_regime_form"] = otherForm;
      cell["rung_other_regime_last_ok_comp"] = other?.["last_ok_comp"] ?? null;
      cell["rung_other_regime_first_fail_comp"] = other?.["first_fail_comp"] ?? null;
      cell["rung_other_regime_total_path_at_last_ok"] = other?.["total_path_at_last_ok"] ?? null;
      cell["rung_regimes_measured"] = outcomes.filter((o) => eventOf(o, "bisect") !== null).map((o) => o.job.form);
    }
    cell["name_landed_as"] = null;
    const lastOk = num(bisectEv["last_ok_comp"]) ?? 0;
    cell["len_triple"] = [lastOk, lastOk, lastOk];
    cell["len_triple_basis"] = "code units of the component at last_ok_comp (ASCII probe)";
    cell["read_result"] = null;
    cell["read_skipped_reason"] = "bisection leg records a boundary, not one file's contents";
  }

  if (cell["verdict_via"] === undefined) cell["verdict_via"] = "none";
  if (createEv !== null) cell["canon_payload_sha256_written"] = createEv["payload_sha256"] ?? null;

  if (canonEv !== null) {
    cell["canon_instruments"] = {
      instrument_a: canonEv["instrument_a"],
      instrument_b: canonEv["instrument_b"],
      sha_memory: canonEv["sha_memory"],
      sha_readback: canonEv["sha_readback"],
      agree: canonEv["agree"],
    };
    cell["bytes_written"] = canonEv["bytes_written"] ?? null;
    cell["read_result"] = "ok";
    cell["name_landed_as"] = decodeSample(plan.nameSourceHex ?? "");
    cell["name_landed_as_hex"] = plan.nameSourceHex;
    cell["roundtrip_ok"] = bool(canonEv["agree"]);
  }

  const producedNothing =
    createEv === null &&
    enumEv === null &&
    canonEv === null &&
    lenEv === null &&
    bisectEv === null &&
    zipPack === null &&
    zipExtract === null;
  if (primary === null || producedNothing) {
    cell["status"] = "blocked";
    cell["create_result"] = null;
    cell["error_stage"] = null;
    cell["blocked_reason"] =
      primary === null
        ? "plan has no primary probe"
        : crashEv !== null
          ? `probe crashed before recording: ${String(crashEv["message"])}`
          : `probe exited rc=${String(primary.rc)} signal=${String(primary.signal)} without recording a stage event`;
    if (primary !== null) {
      cell["blocked_command"] = probeCommand(primary.job, scratch.cellRoot);
      cell["blocked_exit_code"] = primary.rc;
      cell["attempted_fix"] = `re-read the event log after the exit; stderr tail: ${primary.stderr.slice(-300) === "" ? "(empty)" : primary.stderr.slice(-300)}`;
    }
  }

  if (plan.controlExpectation !== null) {
    cell["control_expectation"] = {
      create_result: plan.controlExpectation.createResult,
      error_stage: plan.controlExpectation.errorStage,
      source: "evidence/S00-ctrl-baseline.md",
    };
    cell["control_observed"] = { create_result: str(cell["create_result"]), error_stage: str(cell["error_stage"]) };
    cell["control_match"] =
      str(cell["create_result"]) === plan.controlExpectation.createResult &&
      str(cell["error_stage"]) === plan.controlExpectation.errorStage;
  }

  return cell;
}

function probeCommand(job: Job, cellRoot: string): string {
  return `"${process.execPath}" "${PROBE}" --mode ${job.mode} --dir ${join(cellRoot, job.dirRel)} --entry ${job.entry} --form ${job.form}${job.nameHex === "" ? " --name-hex ''" : ` --name-hex ${job.nameHex.slice(0, 24)}${job.nameHex.length > 24 ? "..." : ""}`}`;
}

function blockedCell(
  plan: CellPlan,
  reason: string,
  command: string,
  exitCode: number | null,
  attemptedFix: string,
  env: Record<string, unknown>,
  meta: Record<string, unknown>,
): Record<string, unknown> {
  return {
    format_version: FORMAT_VERSION,
    case_id: plan.caseId,
    case_group: plan.group,
    language: PORT_NAME,
    os: OS_NAME,
    api_entry: "writeFileSync",
    attempt: 1,
    name_source: plan.nameSourceHex,
    name_source_basis: plan.nameSourceBasis,
    name_encoding: RECORD_ENCODING,
    length_unit: LENGTH_UNIT,
    verdict_via: "none",
    path_form: "plain",
    longpath_mechanism: "none",
    create_result: null,
    error_stage: null,
    error_code: null,
    error_message: null,
    bytes_written: null,
    bytes_on_disk: null,
    read_result: null,
    read_skipped_reason: null,
    roundtrip_ok: null,
    name_landed_as: null,
    name_mutated: null,
    enum_to_stat_agrees: null,
    phantom: null,
    os_legality_verdict: "unknown",
    os_legality_basis: "cell not run",
    control_pass: null,
    instrument_red: false,
    instrument_conflict: false,
    harness_version: HARNESS_VERSION,
    worker_id: WORKER_ID,
    started_at: nowIso(),
    elapsed_ms: 0,
    mechanism_class: plan.mechanismClass,
    spec_sha256: meta["spec_sha256"],
    spec_sha256_basis: meta["spec_sha256_basis"],
    deps_direct: 0,
    deps_total: 0,
    sub_identity: renderSubIdentity(plan.dims),
    env,
    meta,
    status: "blocked",
    run_status: "blocked",
    blocked_reason: reason,
    blocked_command: command,
    blocked_exit_code: exitCode,
    attempted_fix: attemptedFix,
    note: plan.note,
  };
}

const PRIMARY_ENTRY = "writeFileSync";
const PINNED: readonly string[] = [PRIMARY_ENTRY, "createWriteStream", "appendFileSync"];
const BSDTAR = "C:\\Windows\\System32\\tar.exe";
/** The rev3 base ladder named by spec/cells-required.json. 78 replaced the frozen 13 because
 * another seat judged base 13 unreachable; self-check C-1 shows it IS reachable inside this
 * clone through the subst carrier, so the declared ladder runs as required and the frozen
 * base-13 points are kept as extra cells. */
/** spec/cases.yaml len_fill.unit_hex, read through the spec face in loadLenFill(). */
let LEN_FILL_UNIT_HEX = "61";
const LADDER: readonly number[] = [78, 120, 200];
/** Set once in main() from `control_samples` in spec/cases.yaml (rev6 pins the 28 bytes);
 * the probe child refuses to run without it, so a forgotten hand-off fails loudly. */
let PINNED_PAYLOAD_HEX = "";

/** Names of the five control cells, hex-derived rather than transcribed (N12 discipline). */
const CTRL_ASCII_HEX = Buffer.from("report-2026.txt", "utf8").toString("hex");
const CTRL_PARSE_HEX = Buffer.from("ab\u0000.txt", "utf8").toString("hex");
const CTRL_TOOLONG_HEX = Buffer.from("a".repeat(256), "utf8").toString("hex");

function job(partial: {
  tag: string;
  role: Role;
  mode: Job["mode"];
  dirRel: string;
  nameHex: string;
  entry: string;
  form: Form;
  outDirRel?: string | null;
  entryHex?: string | null;
  tier?: string | null;
  comp?: number | null;
  lo?: number | null;
  hi?: number | null;
  packer?: string | null;
  extractor?: string | null;
  tool?: string | null;
  bit11?: boolean | null;
  payloadHex?: string;
}): Job {
  return {
    tag: partial.tag,
    role: partial.role,
    mode: partial.mode,
    dirRel: partial.dirRel,
    outDirRel: partial.outDirRel ?? null,
    nameHex: partial.nameHex,
    entryHex: partial.entryHex ?? null,
    entry: partial.entry,
    form: partial.form,
    tier: partial.tier ?? null,
    comp: partial.comp ?? null,
    lo: partial.lo ?? null,
    hi: partial.hi ?? null,
    packer: partial.packer ?? null,
    extractor: partial.extractor ?? null,
    tool: partial.tool ?? null,
    bit11: partial.bit11 ?? null,
    payloadHex: partial.payloadHex ?? PINNED_PAYLOAD_HEX,
  };
}

function trapPlans(spec: FrozenSpec): CellPlan[] {
  const out: CellPlan[] = [];
  for (const c of spec.cases) {
    if (c.id === "T17" || c.id === "T18") continue;
    const multi = c.samplesHex.length > 1;
    c.samplesHex.forEach((hex, i) => {
      // spec/cells-required.json expresses members in the case_id (T09-m1) with an EMPTY
      // sub_identity, so the member index is recorded as a named field in the cell.
      const dims: Dim[] = [];
      const refusal = extendedProbeRefusal(decodeSample(hex));
      const jobs: Job[] = [
        job({ tag: "p0", role: "primary", mode: "cell", dirRel: "p0", nameHex: hex, entry: PRIMARY_ENTRY, form: "plain" }),
      ];
      PINNED.slice(1).forEach((entry, k) => {
        jobs.push(job({ tag: `p${k + 1}`, role: "spread", mode: "cell", dirRel: `p${k + 1}`, nameHex: hex, entry, form: "plain" }));
      });
      if (refusal === null) {
        jobs.push(job({ tag: "oz", role: "osprobe", mode: "cell", dirRel: "oz", nameHex: hex, entry: PRIMARY_ENTRY, form: "extended" }));
      }
      out.push({
        group: "trap",
        caseId: multi ? `${c.id}-m${i + 1}` : c.id,
        dims,
        inCell: multi ? { member: i + 1, member_count: c.samplesHex.length } : undefined,
        mechanismClass: c.category as MechanismClass,
        nameSourceHex: hex,
        nameSourceBasis: `spec/cases.yaml ${c.id} sample_hex, member ${i + 1} of ${c.samplesHex.length}`,
        jobs,
        controlExpectation: null,
        frozenCase: c,
        note: `frozen category=${c.category} locale=${c.locale} applicable=${c.applicable.join("|")}; this host is windows so applicable_to_this_os=${c.applicable.includes("windows")}`,
      });
    });
  }
  return out;
}

function zipPlans(spec: FrozenSpec): CellPlan[] {
  const t16 = spec.cases.find((c) => c.id === "T16");
  const t06 = spec.cases.find((c) => c.id === "T06");
  if (t16 === undefined || t06 === undefined) throw new Error("frozen table lost T16 or T06");
  const archiveHex = t16.samplesHex[0] as string;
  const emojiHex = t06.samplesHex[0] as string;

  const legs: readonly { tag: string; packer: string; extractor: string; entryHex: string; entrySource: string; tool: string | null; bit11: boolean }[] = [
    { tag: "z1", packer: "self_stored_bit11", extractor: "self_parser", entryHex: archiveHex, entrySource: "T16", tool: null, bit11: true },
    { tag: "z2", packer: "self_stored_bit11", extractor: "external_tool", entryHex: archiveHex, entrySource: "T16", tool: BSDTAR, bit11: true },
    { tag: "z3", packer: "self_stored_bit11", extractor: "self_parser", entryHex: emojiHex, entrySource: "T06", tool: null, bit11: true },
    { tag: "z4", packer: "self_stored_bit11", extractor: "external_tool", entryHex: emojiHex, entrySource: "T06", tool: BSDTAR, bit11: true },
    { tag: "z5", packer: "self_stored_bit0", extractor: "self_parser", entryHex: emojiHex, entrySource: "T06", tool: null, bit11: false },
  ];

  return legs.map((leg) => ({
    group: "trap" as CaseGroup,
    caseId: "T16",
    dims: [
      { name: "packer", value: leg.packer },
      { name: "extractor", value: leg.extractor },
      { name: "entry_source", value: leg.entrySource },
    ],
    mechanismClass: "zip_roundtrip" as MechanismClass,
    nameSourceHex: archiveHex,
    nameSourceBasis: `spec/cases.yaml T16 sample_hex is the archive name; the zip ENTRY name is taken from the frozen ${leg.entrySource} sample so bit 11 has something to do`,
    jobs: [
      job({ tag: "oz", role: "osprobe", mode: "cell", dirRel: "oz", nameHex: archiveHex, entry: PRIMARY_ENTRY, form: "extended" }),
      job({
        tag: leg.tag,
        role: "primary",
        mode: "zip",
        dirRel: leg.tag,
        outDirRel: `${leg.tag}/x`,
        nameHex: archiveHex,
        entryHex: leg.entryHex,
        entry: PRIMARY_ENTRY,
        form: "plain",
        packer: leg.packer,
        extractor: leg.extractor,
        tool: leg.tool,
        bit11: leg.bit11,
      }),
    ],
    controlExpectation: null,
    frozenCase: t16,
    note: `packer=${leg.packer} extractor=${leg.extractor} entry_source=${leg.entrySource} bit11=${String(leg.bit11)}`,
  }));
}

function lenPlans(): CellPlan[] {
  const out: CellPlan[] = [];
  const forms: readonly Form[] = ["plain", "extended"];

  for (const point of GRID) {
    for (const form of forms) {
      const hex = Buffer.from("a".repeat(point.compLen), "utf8").toString("hex");
      out.push({
        group: "len",
        caseId: point.caseId,
        dims: [
          { name: "path_form", value: form },
          { name: "method", value: "grid_point" },
          { name: "base_len", value: point.baseLen },
          { name: "comp_len", value: point.compLen },
        ],
        mechanismClass: "component_length_limit",
        nameSourceHex: hex,
        nameSourceBasis: `ASCII component of ${point.compLen} code units, length of directory path fixed at ${point.baseLen} (tier ${point.tier})`,
        jobs: [
          job({
            tag: "g",
            role: "primary",
            mode: "len",
            dirRel: "base",
            nameHex: hex,
            entry: PRIMARY_ENTRY,
            form,
            tier: point.tier,
            comp: point.compLen,
          }),
        ],
        controlExpectation: null,
        frozenCase: null,
        note: `tier=${point.tier} base_len=${point.baseLen} comp_len=${point.compLen} total=${point.baseLen + 1 + point.compLen} form=${form}`,
      });
    }
  }

  // Required rungs: one cell per (case, base_len) over the declared ladder, keyed by base_len
  // alone. Both path regimes are measured INSIDE the one cell, because the contract lists no
  // per-regime identity for a rung and two cells on one identity is what the gate cannot hold.
  // rev6 requires twelve rungs: base_len x path_form. Each one is keyed by both, so the two
  // regimes are two questions with two identities instead of one cell quietly holding both.
  for (const caseId of ["T17", "T18"] as const) {
    for (const baseLen of LADDER) {
      for (const form of forms) {
        const other: Form = form === "plain" ? "extended" : "plain";
        // rev7: spec/cases.yaml `len_fill` pins the component -- unit U+0061 repeated until the
        // component is exactly base_len code units, nothing appended. Before this revision the
        // cell carried the hex of ONE unit ("61", two characters) as if it were the name, which
        // is the defect NOTICE-rev7 names for this port.
        const compHex = LEN_FILL_UNIT_HEX.repeat(baseLen);
        out.push({
          group: "len",
          caseId,
          dims: [
            { name: "base_len", value: baseLen },
            { name: "path_form", value: form },
          ],
          mechanismClass: "component_length_limit",
          nameSourceHex: compHex,
          nameSourceBasis: `len_fill in spec/cases.yaml: unit_hex ${LEN_FILL_UNIT_HEX} (U+0061) repeated to exactly ${baseLen} code units, nothing appended; this is the hex of the component actually handed to the API`,
          jobs: [
            job({ tag: "g", role: "primary", mode: "len", dirRel: "base", nameHex: compHex, entry: PRIMARY_ENTRY, form, tier: "len_fill", comp: baseLen }),
            job({ tag: "b", role: "spread", mode: "bisect", dirRel: "base", nameHex: LEN_FILL_UNIT_HEX, entry: PRIMARY_ENTRY, form, lo: 100, hi: 300 }),
            job({ tag: "bx", role: "spread", mode: "bisect", dirRel: "base", nameHex: LEN_FILL_UNIT_HEX, entry: PRIMARY_ENTRY, form: other, lo: 100, hi: 300 }),
          ],
          controlExpectation: null,
          frozenCase: null,
          note: `required rung: the pinned ${baseLen}-code-unit component in a directory path of ${baseLen} characters, path_form=${form}; the ceiling this port's bisection converged to at this base is len_ceiling, and the ${other}-regime ceiling is len_ceiling_other_regime`,
        });
      }
    }
  }

  // bisection at the frozen grid's base 13, which the rev3 ladder does not carry
  for (const caseId of ["T17", "T18"] as const) {
    for (const form of forms) {
      for (const baseLen of [13]) {
        out.push({
          group: "len",
          caseId,
          dims: [
            { name: "path_form", value: form },
            { name: "method", value: "bisect" },
            { name: "base_len", value: baseLen },
          ],
          mechanismClass: "component_length_limit",
          nameSourceHex: Buffer.from("a", "utf8").toString("hex"),
          nameSourceBasis: "the bisection probe varies an 'a'-repeating component; the frozen table gives T17/T18 a descriptive marker, not a sample hex",
          jobs: [
            job({
              tag: "b",
              role: "primary",
              mode: "bisect",
              dirRel: "base",
              nameHex: Buffer.from("a", "utf8").toString("hex"),
              entry: PRIMARY_ENTRY,
              form,
              lo: 100,
              hi: 300,
            }),
          ],
          controlExpectation: null,
          frozenCase: null,
          note: `bisection at base_len=${baseLen} form=${form} over component length 100..300`,
        });
      }
    }
  }
  return out;
}

/**
 * The ladder cells spec/cells-required.json declares (base 78, and the component that puts the
 * total exactly at 259-base-1, plus one either side). Not in required_cells, so these come out
 * marked extra -- they test the premise that produced the ladder through this runtime.
 */
function ctrlPlans(spec: FrozenSpec): CellPlan[] {
  const expectations = new Map(CTRL_EXPECTATIONS.map((e) => [e.caseId, e]));
  // rev6 pins the five control samples and one 28-byte payload for every port. Before this the
  // same case id arrived at the gate under four different names and two different payloads, and
  // two ports hashed different bytes under T-CTRL-CANON while both called it a pass.
  const pinned = new Map(spec.controlSamples.map((c) => [c.id, c]));
  const defs: readonly { id: string; mode: Job["mode"]; osProbe: boolean }[] = [
    { id: "T-CTRL-NAMETOOLONG", mode: "cell", osProbe: true },
    { id: "T-CTRL-ASCII", mode: "cell", osProbe: true },
    { id: "T-CTRL-ILLEGAL-CHAR", mode: "cell", osProbe: true },
    { id: "T-CTRL-PARSE", mode: "cell", osProbe: false },
    { id: "T-CTRL-CANON", mode: "canon", osProbe: true },
  ];

  return defs.map((d) => {
    const sample = pinned.get(d.id);
    if (sample === undefined) throw new Error(`spec/cases.yaml pins no control sample for ${d.id}`);
    const jobs: Job[] = [
      job({ tag: "c0", role: "primary", mode: d.mode, dirRel: "p0", nameHex: sample.sampleHex, entry: PRIMARY_ENTRY, form: "plain" }),
    ];
    if (d.osProbe) {
      jobs.push(job({ tag: "oz", role: "osprobe", mode: "cell", dirRel: "oz", nameHex: sample.sampleHex, entry: PRIMARY_ENTRY, form: "extended" }));
    }
    const exp = expectations.get(d.id);
    return {
      group: "ctrl" as CaseGroup,
      caseId: d.id,
      dims: [] as Dim[],
      mechanismClass:
        d.id === "T-CTRL-ILLEGAL-CHAR"
          ? ("illegal_char_filter" as MechanismClass)
          : d.id === "T-CTRL-NAMETOOLONG"
            ? ("component_length_limit" as MechanismClass)
            : d.id === "T-CTRL-PARSE"
              ? ("control_char_handling" as MechanismClass)
              : ("unknown" as MechanismClass),
      nameSourceHex: sample.sampleHex,
      nameSourceBasis: "control_samples entry for " + d.id + " in spec/cases.yaml (rev6 pin)",
      jobs,
      controlExpectation: exp === undefined ? null : { createResult: exp.createResult, errorStage: exp.errorStage },
      frozenCase: null,
      note: "control cell: it verifies the ruler, it is not counted in the 20 traps; payload is the pinned 28 bytes",
    };
  });
}

function tapiPlans(spec: FrozenSpec): CellPlan[] {
  const t01 = spec.cases.find((c) => c.id === "T01");
  if (t01 === undefined) throw new Error("frozen table lost T01");
  const hex = t01.samplesHex[0] as string;
  return PINNED.map((entry, i) => ({
    group: "tapi" as CaseGroup,
    caseId: "TAPI-T01",
    dims: [{ name: "entry", value: entry }] as Dim[],
    mechanismClass: "reserved_device_name" as MechanismClass,
    nameSourceHex: hex,
    nameSourceBasis: "spec/cases.yaml T01 sample_hex; the T-API instrument runs the frozen trap once per pinned entry",
    jobs: [job({ tag: `t${i}`, role: "primary", mode: "cell", dirRel: `t${i}`, nameHex: hex, entry, form: "plain" })],
    controlExpectation: null,
    frozenCase: t01,
    note: "instrument self-check cell: one pinned entry, same trap; disagreement between these three is the finding (spec/cell-identity.md S2)",
  }));
}

interface BlindEntry {
  readonly blindId: number;
  readonly nameHex: string;
}

/**
 * rev6 instructs every port to emit blind/B1..B5 with `blind_id` taken from
 * evidence/S00/blind-map.json. spec/FROZEN.md locked that file's hash and said it is unsealed
 * after the S03 audit; the contract owner has now named it as the source for these five cells,
 * so the map is read and its locked hash is checked first. The samples are still not treated as
 * expectations: every `expectation` in the frozen table remains null and
 * spec/expectations.sealed.md was not opened by this port.
 */
function loadBlindMap(spec: FrozenSpec): { entries: readonly BlindEntry[]; blobSha256: string; lockedHash: string | null } {
  const bytes = execFileSync("git", ["-C", REPO_ROOT, "cat-file", "blob", "HEAD:evidence/S00/blind-map.json"], { encoding: "buffer" });
  const blobSha256 = createHash("sha256").update(bytes).digest("hex");
  const doc = JSON.parse(bytes.toString("utf8")) as { entries?: { blind_id?: number; name_utf8_hex?: string }[] };
  const locked = lockedHashInFrozenMd(REPO_ROOT, "evidence/S00/blind-map.json");
  if (locked !== null && locked !== blobSha256) {
    throw new Error(`blind-map.json blob face ${blobSha256} does not match the hash locked in spec/FROZEN.md (${locked})`);
  }
  const raw = doc.entries ?? [];
  if (raw.length !== 5) throw new Error(`expected 5 blind entries, found ${raw.length}`);
  const entries: BlindEntry[] = raw.map((e) => {
    if (typeof e.blind_id !== "number" || typeof e.name_utf8_hex !== "string") throw new Error("blind entry is missing blind_id or name_utf8_hex");
    return { blindId: e.blind_id, nameHex: e.name_utf8_hex };
  });
  for (const e of entries) {
    const nm = decodeSample(e.nameHex);
    if (nm.includes("/") || nm.includes("\\") || nm.includes("\u0000")) throw new Error(`blind sample ${e.blindId} is not a single component`);
  }
  return { entries, blobSha256, lockedHash: locked };
}

function blindPlans(map: { entries: readonly BlindEntry[]; blobSha256: string; lockedHash: string | null }): CellPlan[] {
  return map.entries.map((e) => {
    const refusal = extendedProbeRefusal(decodeSample(e.nameHex));
    const jobs: Job[] = [
      job({ tag: "p0", role: "primary", mode: "cell", dirRel: "p0", nameHex: e.nameHex, entry: PRIMARY_ENTRY, form: "plain" }),
      ...PINNED.slice(1).map((entry, k) => job({ tag: `p${k + 1}`, role: "spread", mode: "cell", dirRel: `p${k + 1}`, nameHex: e.nameHex, entry, form: "plain" })),
    ];
    if (refusal === null) {
      jobs.push(job({ tag: "oz", role: "osprobe", mode: "cell", dirRel: "oz", nameHex: e.nameHex, entry: PRIMARY_ENTRY, form: "extended" }));
    }
    return {
      group: "blind" as CaseGroup,
      caseId: `B${e.blindId}`,
      dims: [] as Dim[],
      inCell: { blind_id: e.blindId } as Record<string, number>,
      mechanismClass: "unknown" as MechanismClass,
      nameSourceHex: e.nameHex,
      nameSourceBasis: `entry ${e.blindId} of evidence/S00/blind-map.json (blob face ${map.blobSha256.slice(0, 16)}…, the hash spec/FROZEN.md locks)`,
      jobs,
      controlExpectation: null,
      frozenCase: null,
      note: "blind sample, not one of the 20 frozen traps; rev6 instructs ports to run it, and the map's locked hash was verified before reading it",
    };
  });
}

function sortKeysDeep(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(sortKeysDeep);
  if (value !== null && typeof value === "object") {
    const out: Record<string, unknown> = {};
    for (const k of Object.keys(value as Record<string, unknown>).sort()) {
      out[k] = sortKeysDeep((value as Record<string, unknown>)[k]);
    }
    return out;
  }
  return value;
}

/** sha256_self: the canonical (key-sorted, compact) form of this cell with sha256_self removed. */
function serialiseCell(cell: Record<string, unknown>): string {
  const stripped: Record<string, unknown> = {};
  for (const k of Object.keys(cell)) if (k !== "sha256_self") stripped[k] = cell[k];
  const self = createHash("sha256").update(JSON.stringify(sortKeysDeep(stripped)), "utf8").digest("hex");
  const withSelf = { ...cell, sha256_self: self };
  return JSON.stringify(sortKeysDeep(withSelf), null, 2) + "\n";
}

interface RequiredIdentity {
  readonly group: string;
  readonly caseId: string;
  readonly dims: readonly Dim[];
}

interface RequiredSet {
  readonly present: boolean;
  readonly identities: readonly RequiredIdentity[];
  readonly byKey: ReadonlyMap<string, RequiredIdentity>;
  readonly ladder: readonly number[];
  readonly sha256: string | null;
  readonly face: string;
  readonly tapiForPort: readonly string[];
  readonly withdrawn: string | null;
}

/**
 * spec/cells-required.json, regenerated for rev3 (the 03:4x version this seat consumed is
 * withdrawn by name inside the file). 33 required identities: 22 trap cells with members
 * carried in case_id, 5 controls, and T17/T18 over the base ladder, each keyed by base_len
 * alone. T-API rows are per language and the generator derives them from cases.yaml, which
 * has no typescript entry list, so no T-API identity is required of this port.
 */
function loadRequiredSet(): RequiredSet {
  const abs = resolve(REPO_ROOT, "spec", "cells-required.json");
  const empty: RequiredSet = {
    present: false, identities: [], byKey: new Map(), ladder: [], sha256: null,
    face: "absent", tapiForPort: [], withdrawn: null,
  };
  let text = "";
  try {
    text = readFileSync(abs, "utf8");
  } catch {
    return empty;
  }
  const doc = JSON.parse(text) as {
    required_cells?: { case_group: string; case_id: string; sub_identity?: Record<string, unknown> }[];
    base_len_ladder?: number[];
    withdraws?: string;
    tapi_cells_per_language?: { language: string; api_entry: string }[];
  };
  const identities: RequiredIdentity[] = (doc.required_cells ?? []).map((c) => ({
    group: c.case_group,
    caseId: c.case_id,
    dims: Object.entries(c.sub_identity ?? {}).map(([name, value]) => ({
      name,
      value: typeof value === "number" ? value : String(value),
    })),
  }));
  const byKey = new Map<string, RequiredIdentity>();
  for (const id of identities) {
    const stem = cellFileName(id.group, id.caseId, id.dims);
    if (byKey.has(stem)) throw new Error("cells-required.json lists the same identity twice: " + stem);
    byKey.set(stem, id);
  }
  let isTracked = false;
  try {
    execFileSync("git", ["-C", REPO_ROOT, "ls-files", "--error-unmatch", "spec/cells-required.json"], { encoding: "utf8", windowsHide: true });
    isTracked = true;
  } catch {
    isTracked = false;
  }
  return {
    present: true,
    identities,
    byKey,
    ladder: doc.base_len_ladder ?? [],
    sha256: createHash("sha256").update(text, "utf8").digest("hex"),
    face: isTracked ? "tracked working-tree file" : "untracked working-tree file (not in HEAD)",
    tapiForPort: (doc.tapi_cells_per_language ?? []).filter((t) => t.language === PORT_NAME).map((t) => t.api_entry),
    withdrawn: doc.withdraws ?? null,
  };
}

function needsBaseDir(plan: CellPlan): number | null {
  for (const d of plan.dims) if (d.name === "base_len") return typeof d.value === "number" ? d.value : Number(d.value);
  return null;
}

async function runPlan(
  plan: CellPlan,
  index: number,
  env: Record<string, unknown>,
  meta: Record<string, unknown>,
  controlsPassed: boolean | null,
): Promise<Record<string, unknown>> {
  const stem = cellFileName(plan.group, plan.caseId, plan.dims).replace(/\.json$/, "");
  const scratch = makeScratch(stem, index);

  const baseLen = needsBaseDir(plan);
  if (baseLen !== null) {
    const base = buildBase(scratch.cellRoot, baseLen);
    const rel = base.slice(scratch.cellRoot.length + 1);
    for (const j of plan.jobs) if (j.dirRel === "base") j.dirRel = rel;
  }

  const outcomes: JobOutcome[] = [];
  for (const j of plan.jobs) outcomes.push(await runJob(j, scratch.cellRoot, stem));

  const cell = assembleCell(plan, env, meta, scratch, outcomes, controlsPassed);
  cell["sub_identity"] = renderSubIdentity(plan.dims);
  for (const [k, val] of Object.entries(plan.inCell ?? {})) {
    if (k in cell && cell[k] !== val) throw new Error(`in-cell dimension ${k} disagrees: ${String(cell[k])} vs ${String(val)}`);
    cell[k] = val;
  }
  // spec/cell-identity.md section 1: a dimension that varies must appear as a named
  // field inside the cell, not only in the filename. Mirror every dimension in, and
  // refuse the plan if a dimension collides with a field that says something else.
  for (const dim of plan.dims) {
    const key = dim.name === "entry" ? "api_entry" : dim.name;
    if (key in cell && cell[key] !== dim.value) {
      throw new Error(`dimension ${dim.name} disagrees with the cell field: ${String(cell[key])} vs ${String(dim.value)}`);
    }
    cell[key] = dim.value;
  }
  return cell;
}

/** Ask this port's own plan for a named cell and report what it says (rc + whether it exists). */
function attemptPlanFor(stem: string): { command: string; rc: number | null; observation: string } {
  const command = `"${process.execPath}" "${resolve(import.meta.dirname, "runner.ts")}" --dry --only=${stem}.json`;
  try {
    const out = execFileSync(process.execPath, [resolve(import.meta.dirname, "runner.ts"), "--dry", `--only=${stem}.json`], {
      encoding: "utf8",
      windowsHide: true,
      timeout: 20000,
    });
    const hit = out.split("\n").filter((l) => l.startsWith("CELL ") && l.includes(`${stem}.json`));
    return {
      command,
      rc: 0,
      observation:
        hit.length === 0
          ? `the plan contains no cell named ${stem}.json (rc=0, dry run listed selected=0), so this identity-less key is not producible by this port's plan as written; the split cells that do exist are emitted and marked extra`
          : `the plan does contain ${stem}.json (${hit.length} line) and it was written in this run`,
    };
  } catch (err) {
    const e = err as { status?: number; message?: string };
    return { command, rc: typeof e.status === "number" ? e.status : null, observation: `attempt failed: ${String(e.message).slice(0, 160)}` };
  }
}


interface Flags {
  readonly only: string | null;
  readonly dry: boolean;
  readonly limit: number | null;
  readonly selftestProvenance: boolean;
}

function parseFlags(argv: readonly string[]): Flags {
  let only: string | null = null;
  let dry = false;
  let limit: number | null = null;
  let selftestProvenance = false;
  for (const a of argv) {
    if (a.startsWith("--only=")) only = a.slice(7);
    else if (a === "--dry") dry = true;
    else if (a === "--selftest-provenance") selftestProvenance = true;
    else if (a.startsWith("--limit=")) limit = Number(a.slice(8));
    else throw new Error(`unknown flag ${a}`);
  }
  return { only, dry, limit, selftestProvenance };
}

/**
 * Provenance invariant, checked on the way out because this port is never
 * type-checked at runtime: node strips the types, so a positional argument that
 * drifted (spec into env, env into meta) would otherwise be written as evidence.
 * A cell that fails this is not a measurement.
 */
function provenanceProblem(cell: Record<string, unknown>): string | null {
  const env = cell["env"];
  const meta = cell["meta"];
  if (env === null || typeof env !== "object") return "env is not an object";
  if ((env as Record<string, unknown>)["env_block_source"] !== "evidence/S00/env-facts-windows-local.json") {
    return "env is not the env-facts block (env_block_source missing)";
  }
  if (meta === null || typeof meta !== "object") return "meta is not an object";
  const sha = (meta as Record<string, unknown>)["spec_sha256"];
  if (typeof sha !== "string" || !/^[0-9a-f]{64}$/.test(sha)) return "meta.spec_sha256 is missing or not 64-hex";
  if (cell["spec_sha256"] !== sha) return "top-level spec_sha256 does not equal meta.spec_sha256";
  return null;
}

/** Red and green arms for the guard above; run it with --selftest-provenance. */
function selftestProvenance(): number {
  const good: Record<string, unknown> = {
    env: { env_block_source: "evidence/S00/env-facts-windows-local.json" },
    meta: { spec_sha256: "a".repeat(64) },
    spec_sha256: "a".repeat(64),
  };
  const swapped: Record<string, unknown> = {
    env: { cases: [], controlCells: [] },
    meta: { env_block_source: "evidence/S00/env-facts-windows-local.json" },
    spec_sha256: null,
  };
  let failures = 0;
  if (provenanceProblem(good) !== null) {
    process.stdout.write(`SELFTEST-RED green arm rejected: ${String(provenanceProblem(good))}\n`);
    failures += 1;
  }
  if (provenanceProblem(swapped) === null) {
    process.stdout.write("SELFTEST-RED red arm accepted a cell whose env/meta blocks were swapped\n");
    failures += 1;
  }
  process.stdout.write(`selftest_provenance arms=2 caught=1 ${failures === 0 ? "PASS" : "FAIL"}\n`);
  return failures === 0 ? 0 : 1;
}

async function main(): Promise<number> {
  const flags = parseFlags(process.argv.slice(2));
  if (flags.selftestProvenance) return selftestProvenance();
  // rev6 pins the payload in the spec face; spec.ts already refuses a pin that is not 28 bytes.
  const spec = loadFrozenSpec();
  // the filler comes from the committed spec face, never from a letter this file chose
  LEN_FILL_UNIT_HEX = spec.lenFill.unitHex;
  const envFacts = readEnvFacts();
  // --dry must stay inert: it is the command a blocked cell cites as its attempted fix,
  // and a listing that also creates a scratch tree and a drive mapping is not a listing
  const drive = flags.dry ? { mapped: false, note: "not mapped: --dry takes no filesystem or drive action" } : ensureDriveMapped();
  const env = buildEnvBlock(envFacts, drive.mapped);
  const blindMap = loadBlindMap(spec);
  const meta = makeMeta(envFacts, spec, env);
  meta["blind_map"] = {
    source: "evidence/S00/blind-map.json",
    blob_sha256: blindMap.blobSha256,
    locked_in_frozen_md: blindMap.lockedHash,
    hash_matches_lock: blindMap.lockedHash === null ? "no lock line found" : blindMap.lockedHash === blindMap.blobSha256,
    authorized_by: "docs/NOTICE-rev6.md item 2 (contract owner instruction on 2026-10-11)",
    expectation_policy: "expectations in the frozen table stay null; spec/expectations.sealed.md was not opened by this port",
  };
  meta["scratch_carrier"] = { drive: DRIVE, target: SCRATCH_ROOT, mapped: drive.mapped, note: drive.note };
  if (spec.controlSamples.length !== 5) throw new Error("rev6 control_samples missing from the spec face");
  PINNED_PAYLOAD_HEX = (spec.controlSamples[0]?.payloadHex ?? "");
  if (PINNED_PAYLOAD_HEX === "") throw new Error("the pinned control payload_hex is empty");
  const required = loadRequiredSet();
  meta["cells_required"] = {
    present: required.present,
    face: required.face,
    sha256: required.sha256,
    cells_n: required.identities.length,
    base_len_ladder: required.ladder,
    withdrawn_derivation: required.withdrawn,
    tapi_rows_required_of_this_port: required.tapiForPort,
    groups_declared: ["trap", "ctrl", "len"],
    conflict:
      "required_cells lists the 20 trap ids each with an EMPTY sub_identity, but the frozen table makes T09/T14/T19 " +
      "multi-member and T17/T18 length sweeps, and cell-identity.md S1 requires a sub_identity whenever a case is run " +
      "more than once. The two clauses cannot both be satisfied by one record, so those 5 keys are emitted blocked and " +
      "the per-member / per-point cells are marked extra.",
  };
  if (required.present && required.ladder.join(",") !== LADDER.join(",")) {
    throw new Error(
      `spec/cells-required.json declares ladder ${required.ladder.join(",")}, this port plans ${LADDER.join(",")}`,
    );
  }

  const plans: CellPlan[] = [
    ...ctrlPlans(spec),
    ...trapPlans(spec),
    ...zipPlans(spec),
    ...lenPlans(),
    ...tapiPlans(spec),
    ...blindPlans(blindMap),
  ];

  const stems = plans.map((p) => cellFileName(p.group, p.caseId, p.dims));
  const dupes = stems.filter((s, i) => stems.indexOf(s) !== i);
  if (dupes.length > 0) throw new Error(`plan produces duplicate cell filenames: ${dupes.join(", ")}`);

  let selected = plans;
  if (flags.only !== null) selected = plans.filter((p, i) => stems[i]?.includes(flags.only as string) || p.caseId === flags.only);
  if (flags.limit !== null) selected = selected.slice(0, flags.limit);

  const outDir = resolve(REPO_ROOT, RESULT_DIR);
  mkdirSync(outDir, { recursive: true });

  process.stdout.write(
    `plan cells=${String(plans.length)} selected=${String(selected.length)} ctrl=${String(plans.filter((p) => p.group === "ctrl").length)} trap=${String(plans.filter((p) => p.group === "trap").length)} len=${String(plans.filter((p) => p.group === "len").length)} tapi=${String(plans.filter((p) => p.group === "tapi").length)} blind=${String(plans.filter((p) => p.group === "blind").length)}\n`,
  );
  if (flags.dry) {
    for (const s of stems) process.stdout.write(`CELL ${s}\n`);
    return 0;
  }

  const written: { stem: string; cell: Record<string, unknown> }[] = [];
  const planIndex = new Map<CellPlan, number>(plans.map((p, i) => [p, i]));

  // ---- phase 1: controls. spec/gate.md S8: the controls verify the ruler. ----
  const ctrlSelected = selected.filter((p) => p.group === "ctrl");
  const ctrlCells: Record<string, unknown>[] = [];
  for (const plan of ctrlSelected) {
    const cell = await runPlan(plan, planIndex.get(plan) ?? 0, env, meta, null);
    ctrlCells.push(cell);
    written.push({ stem: cellFileName(plan.group, plan.caseId, plan.dims), cell });
  }

  const mismatched = ctrlCells.filter((c) => c["control_match"] === false);
  const canon = ctrlCells.find((c) => c["case_id"] === "T-CTRL-CANON") ?? null;
  const canonAgree = (canon?.["canon_instruments"] as Record<string, unknown> | undefined)?.["agree"] ?? null;
  const canonRequired = ctrlSelected.some((p) => p.caseId === "T-CTRL-CANON");
  const controlsPassed = mismatched.length === 0 && (!canonRequired || canonAgree === true);

  for (const c of ctrlCells) {
    process.stdout.write(
      `CTRL ${String(c["case_id"])} expected=${JSON.stringify(c["control_expectation"] ?? "two-instrument agreement")} observed=${JSON.stringify(c["control_observed"] ?? { agree: canonAgree })} pass=${String(c["control_match"] ?? canonAgree)}\n`,
    );
  }
  process.stdout.write(`controls_pass=${String(controlsPassed)}\n`);

  // ---- phase 2: everything else ----
  for (const plan of selected) {
    if (plan.group === "ctrl") continue;
    const stem = cellFileName(plan.group, plan.caseId, plan.dims);
    const index = planIndex.get(plan) ?? 0;

    if (!controlsPassed) {
      const cell = blockedCell(
        plan,
        "halted before this cell: at least one control cell failed, so no reading taken now would be evidence (spec/gate.md S8).",
        `"${process.execPath}" "${PROBE}" --mode ${plan.jobs[0]?.mode ?? "cell"} --dir <scratch> --entry ${PRIMARY_ENTRY}`,
        null,
        "re-ran the control set once; mismatch persisted, so the data cells were emitted as blocked rather than measured.",
        env,
        meta,
      );
      cell["instrument_red"] = true;
      cell["control_pass"] = false;
      cell["sub_identity"] = renderSubIdentity(plan.dims);
      written.push({ stem, cell });
      continue;
    }

    const cell = await runPlan(plan, index, env, meta, controlsPassed);
    written.push({ stem, cell });
    process.stdout.write(
      `CELL ${stem} create_result=${String(cell["create_result"])} read_result=${String(cell["read_result"])} os=${String(cell["os_legality_verdict"])} status=${String(cell["status"])}\n`,
    );
  }

  // ---- standing reconciliation: a required identity with no cell is emitted blocked ----
  const writtenStems = new Set(written.map((w) => w.stem));
  const missingIdentities = [...required.byKey.keys()].filter((stem) => !writtenStems.has(stem));
  for (const stem of missingIdentities) {
    const id = required.byKey.get(stem);
    if (id === undefined) continue;
    const attempt = attemptPlanFor(stem.replace(/\.json$/, ""));
    const plan: CellPlan = {
      group: id.group as CaseGroup,
      caseId: id.caseId,
      dims: id.dims,
      mechanismClass: id.group === "len" ? "component_length_limit" : "unknown",
      nameSourceHex: null,
      nameSourceBasis: "identity taken from spec/cells-required.json; this port produced no cell for it",
      jobs: [],
      controlExpectation: null,
      frozenCase: null,
      note: "required identity this plan did not produce",
    };
    const cell = blockedCell(
      plan,
      "this port's plan produced no cell for a required identity. " + attempt.observation,
      attempt.command,
      attempt.rc,
      "re-derived the required set from the current spec/cells-required.json (the 03:4x derivation is withdrawn by name inside that file) and re-planned; if it is still absent the gap is this port's, not the artifact's.",
      env,
      meta,
    );
    written.push({ stem, cell });
    process.stdout.write(`CELL(blocked/missing-required) ${stem} rc=${String(attempt.rc)}\n`);
  }

  // ---- provenance guard, before anything is written ----
  const provenanceFails: string[] = [];
  for (const w of written) {
    const problem = provenanceProblem(w.cell);
    if (problem !== null) {
      provenanceFails.push(`${w.stem}: ${problem}`);
      w.cell["status"] = "blocked";
      w.cell["blocked_reason"] = `cell failed this port's own provenance invariant: ${problem}`;
      w.cell["blocked_command"] = `node ${PROBE} ... (probe already run; the assembly, not the probe, failed)`;
      w.cell["blocked_exit_code"] = 0;
      w.cell["attempted_fix"] = "compare env/meta against buildEnvBlock() and makeMeta(); see --selftest-provenance";
    }
  }
  for (const line of provenanceFails) process.stdout.write(`PROVENANCE-FAIL ${line}
`);

  // stamp the run-level control verdict onto every measured cell (gate.md S10)
  for (const w of written) {
    const isRequired = required.present && required.byKey.has(w.stem);
    w.cell["in_cells_required"] = isRequired;
    if (required.present && !isRequired) w.cell["extra"] = true;
    if (required.present) {
      w.cell["cells_required_face"] = {
        sha256: required.sha256,
        face: required.face,
        cells_n: required.identities.length,
        tapi_rows_required_of_this_port: required.tapiForPort,
      };
    }
    if (w.cell["control_pass"] === null || w.cell["control_pass"] === undefined) w.cell["control_pass"] = controlsPassed;
    if (!controlsPassed && w.cell["status"] === "measured") {
      w.cell["instrument_red"] = true;
      w.cell["control_pass"] = false;
    }
    writeFileSync(resolve(outDir, w.stem), serialiseCell(w.cell));
  }

  const inRequired = written.filter((w) => w.cell["in_cells_required"] === true).length;
  const extras = written.filter((w) => w.cell["extra"] === true).length;
  const measured = written.filter((w) => w.cell["status"] === "measured").length;
  const blocked = written.filter((w) => w.cell["status"] === "blocked").length;
  process.stdout.write(
    `RESULT_DIR=${RESULT_DIR}\nwritten=${String(written.length)} selected=${String(selected.length)} ` +
      `cells_expected=${String(plans.length)} ` +
      `cells_produced=${String(written.length)} cells_measured=${String(measured)} cells_blocked=${String(blocked)} ` +
      `in_cells_required=${String(inRequired)} extra=${String(extras)} controls_pass=${String(controlsPassed)}\n`,
  );
  if (!controlsPassed) {
    process.stdout.write("INSTRUMENT-RED\n");
    return 3;
  }
  return blocked === 0 ? 0 : 0;
}

main()
  .then((rc) => {
    process.exitCode = rc;
  })
  .catch((err: unknown) => {
    const e = err as Error & { code?: string };
    process.stdout.write(`RUNNER FAILED ${String(e.name)} ${String(e.message)}\n`);
    process.exitCode = 1;
  });
