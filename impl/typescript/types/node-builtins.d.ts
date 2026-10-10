/**
 * Narrow ambient declarations for the Node built-ins this port uses.
 *
 * The project rule is zero third-party dependencies, and `@types/node` is a
 * third-party package, so the surface used here is declared locally. If a seat
 * installs `@types/node`, delete this file rather than keeping two copies.
 *
 * These declarations describe the runtime that actually executes the port:
 * node v24.15.0 at the path recorded in evidence/S00/env-facts-windows-local.json.
 */

declare module "node:fs" {
  export interface Stats {
    readonly isFile: () => boolean;
    readonly isDirectory: () => boolean;
    readonly size: number;
    readonly mtimeMs: number;
  }
  export interface ErrnoExceptionLike extends Error {
    readonly code?: string;
    readonly errno?: number;
    readonly syscall?: string;
    readonly path?: string;
  }
  export function writeFileSync(path: string, data: string | Uint8Array): void;
  export function appendFileSync(path: string, data: string | Uint8Array): void;
  export function readFileSync(path: string): Buffer;
  export function existsSync(path: string): boolean;
  export function statSync(path: string): Stats;
  export function readdirSync(path: string): string[];
  export function mkdirSync(path: string, options?: { recursive?: boolean }): void;
  export function openSync(path: string, flags: string): number;
  export function closeSync(fd: number): void;
  export function createWriteStream(path: string): import("node:stream").Writable;
  export function createReadStream(path: string): import("node:stream").Readable;
}

declare module "node:crypto" {
  export interface Hash {
    update(data: string | Uint8Array): Hash;
    digest(encoding: "hex"): string;
  }
  export function createHash(algorithm: "sha256"): Hash;
  export function randomUUID(): string;
}

declare module "node:zlib" {
  export function crc32(data: string | Uint8Array): number;
}

declare module "node:child_process" {
  import type { Readable } from "node:stream";
  export interface ChildProcess {
    readonly pid: number | undefined;
    readonly stdout: Readable | null;
    readonly stderr: Readable | null;
    kill(signal?: NodeJS.Signals | number): boolean;
    on(event: "exit", listener: (code: number | null, signal: NodeJS.Signals | null) => void): void;
  }
  export interface SpawnOptions {
    readonly cwd?: string;
    readonly env?: NodeJS.ProcessEnv;
    readonly stdio?: "pipe" | "ignore" | readonly ("pipe" | "ignore" | number | string)[];
    readonly windowsHide?: boolean;
  }
  export function spawn(command: string, args: readonly string[], options?: SpawnOptions): ChildProcess;
  export interface ExecFileSyncOptions {
    readonly cwd?: string;
    readonly env?: NodeJS.ProcessEnv;
    readonly timeout?: number;
    readonly maxBuffer?: number;
    readonly windowsHide?: boolean;
    readonly encoding?: string;
  }
  export function execFileSync(command: string, args: readonly string[], options: ExecFileSyncOptions & { encoding: "buffer" }): Buffer;
  export function execFileSync(command: string, args: readonly string[], options?: ExecFileSyncOptions): string;
}

declare module "node:stream" {
  export interface Readable {
    on(event: "data", listener: (chunk: Buffer) => void): void;
    on(event: "end", listener: () => void): void;
    on(event: "error", listener: (err: unknown) => void): void;
  }
  export interface Writable {
    on(event: "finish", listener: () => void): void;
    on(event: "error", listener: (err: unknown) => void): void;
    write(chunk: string | Uint8Array): boolean;
    end(chunk?: string | Uint8Array): void;
  }
}

declare module "node:path" {
  export function resolve(...parts: readonly string[]): string;
  export function dirname(path: string): string;
  export function join(...parts: readonly string[]): string;
}

declare module "node:process" {
  const value: NodeJS.Process;
  export default value;
}

interface NodeJS {
  interface ProcessEnv {
    [key: string]: string | undefined;
  }
  type Signals = "SIGINT" | "SIGTERM" | "SIGKILL" | "SIGHUP" | "SIGBREAK";
  interface Process {
    readonly argv: string[];
    readonly execPath: string;
    readonly version: string;
    readonly arch: string;
    readonly platform: string;
    readonly pid: number;
    env: ProcessEnv;
    cwd(): string;
    exitCode: number;
    hrtime: { bigint(start?: [number, number]): bigint };
    on(event: "exit", listener: (code: number) => void): void;
  }
}

declare var process: NodeJS.Process;
declare var Buffer: {
  from(arrayOrString: unknown, encodingOrOffset?: unknown, length?: unknown): Buffer;
  alloc(size: number): Buffer;
  concat(list: readonly Uint8Array[], totalLength?: number): Buffer;
  isBuffer(value: unknown): boolean;
  readonly prototype: Buffer;
};

declare class Buffer extends Uint8Array {
  toString(encoding?: string, start?: number, end?: number): string;
  writeUInt16LE(value: number, offset: number): number;
  writeUInt32LE(value: number, offset: number): number;
  readUInt16LE(offset: number): number;
  readUInt32LE(offset: number): number;
  subarray(start?: number, end?: number): Buffer;
  slice(start?: number, end?: number): Buffer;
  indexOf(value: number | string, byteOffset?: number): number;
  includes(value: number | string, byteOffset?: number): boolean;
  equals(other: Uint8Array): boolean;
}

declare function setTimeout(handler: () => void, timeout: number): unknown;
declare function clearTimeout(handle: unknown): void;
declare const console: { log(...data: unknown[]): void };
