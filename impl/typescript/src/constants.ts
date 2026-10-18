/**
 * Closed sets and constants, mirrored from spec/canonical.md and spec/schema.json.
 *
 * Mirrored, not imported: spec/ is frozen and is not a code module. Every word here
 * is a verbatim copy of a row in spec/canonical.md; a word that is NOT in that file
 * must not be added here (contract: an unknown status word voids the cell).
 */

export const HARNESS_VERSION = "sg-ts-1.0.0";
export const IMPLEMENTATION_ID = "typescript-port";
export const PORT_NAME = "typescript";
export const OS_NAME = "windows";
export const ARCH_NAME = "x64";
export const RESULT_DIR = `results/${PORT_NAME}.${OS_NAME}.${ARCH_NAME}`;
export const FORMAT_VERSION = 1;

/** spec/canonical.md S2 - case_group. */
export type CaseGroup = "trap" | "ctrl" | "tapi" | "blind" | "len";

/** spec/canonical.md S3 - create_result. */
export type CreateResult = "ok" | "err_at_parse" | "err_at_syscall" | "hang";

/** spec/canonical.md S4 - error_stage. */
export type ErrorStage = "parse" | "syscall" | "fs" | "tool" | "null";

/** spec/canonical.md S5 - read_result. */
export type ReadResult = "ok" | "eof" | "err6" | "hang";

/** spec/canonical.md S6 - os_legality_verdict. */
export type OsLegalityVerdict = "legal" | "illegal" | "unknown";

/** spec/canonical.md S7 - path_form. */
export type PathForm = "plain" | "extended";

/** spec/canonical.md S8 - longpath_mechanism. */
export type LongpathMechanism = "manifest" | "prefix_rewrite" | "none" | "unknown";

/** spec/canonical.md S9 - attribution_layer. */
export type AttributionLayer = "L1" | "L2" | "L3" | "L3_interaction";

/** spec/canonical.md section 10 - mechanism_class (closed at the S01 freeze). */
export type MechanismClass =
  | "reserved_device_name"
  | "path_preprocessing_policy"
  | "illegal_char_filter"
  | "component_length_limit"
  | "unicode_normalization"
  | "case_folding"
  | "control_char_handling"
  | "bidi_handling"
  | "zero_width_handling"
  | "zip_roundtrip"
  | "os_legality"
  | "unknown";

/** schema.json - name_encoding. */
export type NameEncoding = "utf16_code_units" | "code_points" | "utf8_bytes";

/**
 * Values of the cell-level `status` field. This is NOT a canonical status word:
 * spec/canonical.md has no section for a per-cell execution status, and my order
 * requires `blocked` / `not-achievable-in-stdlib` to be recorded. It therefore
 * lives in an extra field (schema.json additionalProperties: true) and never in a
 * closed-set field. See evidence/judgement/typescript-selfcheck.md, gap G-4.
 */
export type CellRunStatus = "measured" | "blocked" | "not-achievable-in-stdlib";

export const CLOSED_SETS = {
  case_group: ["trap", "ctrl", "tapi", "blind", "len"],
  path_form: ["plain", "extended"],
  longpath_mechanism: ["manifest", "prefix_rewrite", "none", "unknown"],
  create_result: ["ok", "err_at_parse", "err_at_syscall", "hang"],
  error_stage: ["parse", "syscall", "fs", "tool", "null"],
  read_result: ["ok", "eof", "err6", "hang"],
  os_legality_verdict: ["legal", "illegal", "unknown"],
  attribution_layer: ["L1", "L2", "L3", "L3_interaction"],
  name_encoding: ["utf16_code_units", "code_points", "utf8_bytes"],
  mechanism_class: [
    "reserved_device_name",
    "path_preprocessing_policy",
    "illegal_char_filter",
    "component_length_limit",
    "unicode_normalization",
    "case_folding",
    "control_char_handling",
    "bidi_handling",
    "zero_width_handling",
    "zip_roundtrip",
    "os_legality",
    "unknown",
  ],
} as const satisfies Record<string, readonly string[]>;

/** The 5s external timeout, in ms (spec/gate.md S10: every probe action -> hang). */
export const PROBE_TIMEOUT_MS = 5000;

/**
 * The 28-byte write payload. Length matches bytes_written=28 recorded for
 * T-CTRL-ASCII in evidence/ctrl-baseline.md. The baseline publishes the length
 * and the sha256 of the S00 payload but not its bytes, so content equality against
 * the S00 sha is not derivable from spec; the payload is declared here instead.
 * No newline: a probe that lands on the CON device writes its payload to the
 * process output stream, and a stray newline would break the NDJSON event framing.
 */
export const PAYLOAD_TEXT = "sendguard-payload-0123456789";

/** Sub-directory names inside a cell's uuid scratch dir. ASCII only, never a sample name. */
export const ENTRY_SUBDIR = (index: number): string => `p${index}`;
export const OSPROBE_SUBDIR = "oz";

/** Control-cell expectations, taken only from evidence/ctrl-baseline.md. */
export interface CtrlExpectation {
  readonly caseId: string;
  readonly createResult: CreateResult;
  readonly errorStage: ErrorStage;
}

export const CTRL_EXPECTATIONS: readonly CtrlExpectation[] = [
  { caseId: "T-CTRL-NAMETOOLONG", createResult: "err_at_syscall", errorStage: "syscall" },
  { caseId: "T-CTRL-ASCII", createResult: "ok", errorStage: "null" },
  { caseId: "T-CTRL-ILLEGAL-CHAR", createResult: "err_at_syscall", errorStage: "syscall" },
  { caseId: "T-CTRL-PARSE", createResult: "err_at_parse", errorStage: "parse" },
] as const;

/** The 20 frozen trap ids, in order, per spec/FROZEN.md. */
export const FROZEN_TRAP_IDS: readonly string[] = [
  "T01", "T02", "T03", "T04", "T05", "T06", "T07", "T08", "T09", "T10",
  "T11", "T12", "T13", "T14", "T15", "T16", "T17", "T18", "T19", "T20",
] as const;

/** T17/T18 carry a descriptive marker instead of hex in the frozen table. */
export const LEN_CASE_MARKERS: Readonly<Record<string, string>> = {
  T17: "T-LEN-PATH (length bisection, G1-G4)",
  T18: "T-LEN-COMP (component length bisection, G1-G4)",
} as const;

/**
 * The frozen G1-G4 verification grid (spec/FROZEN.md, "20 frozen traps" note).
 * base = length of the directory path with no trailing separator; comp = component length.
 * G1/G2 straddle the total-path wall (domain B); G3/G4 straddle the component wall (domain A).
 */
export interface GridPoint {
  readonly caseId: "T17" | "T18";
  readonly tier: "G1" | "G2" | "G3" | "G4";
  readonly baseLen: number;
  readonly compLen: number;
}

export const GRID: readonly GridPoint[] = [
  { caseId: "T17", tier: "G1", baseLen: 13, compLen: 244 },
  { caseId: "T17", tier: "G1", baseLen: 13, compLen: 245 },
  { caseId: "T17", tier: "G1", baseLen: 13, compLen: 246 },
  { caseId: "T17", tier: "G2", baseLen: 120, compLen: 137 },
  { caseId: "T17", tier: "G2", baseLen: 120, compLen: 138 },
  { caseId: "T17", tier: "G2", baseLen: 120, compLen: 139 },
  { caseId: "T18", tier: "G3", baseLen: 13, compLen: 254 },
  { caseId: "T18", tier: "G3", baseLen: 13, compLen: 255 },
  { caseId: "T18", tier: "G3", baseLen: 13, compLen: 256 },
  { caseId: "T18", tier: "G4", baseLen: 200, compLen: 254 },
  { caseId: "T18", tier: "G4", baseLen: 200, compLen: 255 },
  { caseId: "T18", tier: "G4", baseLen: 200, compLen: 256 },
] as const;
