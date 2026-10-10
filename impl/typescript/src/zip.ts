/**
 * Minimal ZIP container, pack and unpack, written against the APPNOTE layout.
 *
 * Why this exists instead of a package: the T16 cell is a zip bit-11 roundtrip and
 * Node's standard library has no archive container reader/writer (node:zlib does raw
 * and gzip streams only). Hand-assembling the container keeps the port at zero
 * third-party dependencies. Method is 0 (stored), so no compressor is involved and
 * the entry bytes are exactly the payload; CRC-32 comes from node:zlib.
 *
 * Timestamps are fixed constants so a re-pack of the same input is byte-identical.
 */
import { crc32 } from "node:zlib";

const SIG_LOCAL = 0x04034b50;
const SIG_CENTRAL = 0x02014b50;
const SIG_EOCD = 0x06054b50;
const FLAG_UTF8_NAME = 0x0800;
const METHOD_STORED = 0;
const VERSION_MADE_BY = 0x031e;
const VERSION_NEEDED = 20;
const FIXED_DOS_TIME = 0x36a0;
const FIXED_DOS_DATE = 0x5a91;

export interface ZipEntry {
  readonly name: string;
  readonly data: Buffer;
}

export interface UnpackedEntry {
  readonly name: string;
  readonly nameWasUtf8Flagged: boolean;
  readonly nameDecodedVia: "utf8" | "latin1";
  readonly crcOnDisk: number;
  readonly crcRecomputed: number;
  readonly size: number;
}

export function packZip(entries: readonly ZipEntry[], setBit11: boolean): Buffer {
  const local: Buffer[] = [];
  const central: Buffer[] = [];
  let offset = 0;

  for (const entry of entries) {
    const nameBytes = Buffer.from(entry.name, "utf8");
    const crc = crc32(entry.data) >>> 0;
    const flags = setBit11 ? FLAG_UTF8_NAME : 0;

    const lfh = Buffer.alloc(30);
    lfh.writeUInt32LE(SIG_LOCAL, 0);
    lfh.writeUInt16LE(VERSION_NEEDED, 4);
    lfh.writeUInt16LE(flags, 6);
    lfh.writeUInt16LE(METHOD_STORED, 8);
    lfh.writeUInt16LE(FIXED_DOS_TIME, 10);
    lfh.writeUInt16LE(FIXED_DOS_DATE, 12);
    lfh.writeUInt32LE(crc, 14);
    lfh.writeUInt32LE(entry.data.length, 18);
    lfh.writeUInt32LE(entry.data.length, 22);
    lfh.writeUInt16LE(nameBytes.length, 26);
    lfh.writeUInt16LE(0, 28);
    local.push(lfh, nameBytes, entry.data);

    const cdh = Buffer.alloc(46);
    cdh.writeUInt32LE(SIG_CENTRAL, 0);
    cdh.writeUInt16LE(VERSION_MADE_BY, 4);
    cdh.writeUInt16LE(VERSION_NEEDED, 6);
    cdh.writeUInt16LE(flags, 8);
    cdh.writeUInt16LE(METHOD_STORED, 10);
    cdh.writeUInt16LE(FIXED_DOS_TIME, 12);
    cdh.writeUInt16LE(FIXED_DOS_DATE, 14);
    cdh.writeUInt32LE(crc, 16);
    cdh.writeUInt32LE(entry.data.length, 20);
    cdh.writeUInt32LE(entry.data.length, 24);
    cdh.writeUInt16LE(nameBytes.length, 28);
    cdh.writeUInt16LE(0, 30);
    cdh.writeUInt16LE(0, 32);
    cdh.writeUInt16LE(0, 34);
    cdh.writeUInt16LE(0, 36);
    cdh.writeUInt32LE(0, 38);
    cdh.writeUInt32LE(offset, 42);
    central.push(cdh, nameBytes);

    offset += lfh.length + nameBytes.length + entry.data.length;
  }

  const centralBytes = Buffer.concat(central);
  const localBytes = Buffer.concat(local);
  const eocd = Buffer.alloc(22);
  eocd.writeUInt32LE(SIG_EOCD, 0);
  eocd.writeUInt16LE(0, 4);
  eocd.writeUInt16LE(0, 6);
  eocd.writeUInt16LE(entries.length, 8);
  eocd.writeUInt16LE(entries.length, 10);
  eocd.writeUInt32LE(centralBytes.length, 12);
  eocd.writeUInt32LE(localBytes.length, 16);
  eocd.writeUInt16LE(0, 20);

  return Buffer.concat([localBytes, centralBytes, eocd]);
}

/** Walk the central directory, then read each entry's data through its local header. */
export function unpackZip(buf: Buffer): UnpackedEntry[] {
  const eocdAt = buf.lastIndexOf(Buffer.from([0x50, 0x4b, 0x05, 0x06]));
  if (eocdAt < 0) throw new Error("no end-of-central-directory signature");
  const count = buf.readUInt16LE(eocdAt + 8);
  const cdSize = buf.readUInt32LE(eocdAt + 12);
  const cdOffset = buf.readUInt32LE(eocdAt + 16);

  if (cdOffset + cdSize !== eocdAt) {
    throw new Error(`central directory span disagrees: ${cdOffset}+${cdSize} != ${eocdAt}`);
  }

  const out: UnpackedEntry[] = [];
  let p = cdOffset;
  for (let i = 0; i < count; i += 1) {
    if (buf.readUInt32LE(p) !== SIG_CENTRAL) throw new Error(`central record ${i} has no signature`);
    const flags = buf.readUInt16LE(p + 8);
    const method = buf.readUInt16LE(p + 10);
    const crc = buf.readUInt32LE(p + 16) >>> 0;
    const compSize = buf.readUInt32LE(p + 20);
    const uncompSize = buf.readUInt32LE(p + 24);
    const nameLen = buf.readUInt16LE(p + 28);
    const extraLen = buf.readUInt16LE(p + 30);
    const commentLen = buf.readUInt16LE(p + 32);
    const localOffset = buf.readUInt32LE(p + 42);
    const nameBytes = buf.subarray(p + 46, p + 46 + nameLen);
    const bit11 = (flags & FLAG_UTF8_NAME) !== 0;
    p += 46 + nameLen + extraLen + commentLen;

    if (method !== METHOD_STORED) throw new Error(`unsupported method ${method}`);
    if (buf.readUInt32LE(localOffset) !== SIG_LOCAL) throw new Error("local header signature missing");
    const localNameLen = buf.readUInt16LE(localOffset + 26);
    const localExtraLen = buf.readUInt16LE(localOffset + 28);
    const dataAt = localOffset + 30 + localNameLen + localExtraLen;
    if (compSize !== uncompSize) throw new Error("stored entry sizes disagree");
    const data = buf.subarray(dataAt, dataAt + compSize);
    if (data.length !== uncompSize) throw new Error("entry data truncated");

    out.push({
      name: nameBytes.toString(bit11 ? "utf8" : "latin1"),
      nameWasUtf8Flagged: bit11,
      nameDecodedVia: bit11 ? "utf8" : "latin1",
      crcOnDisk: crc,
      crcRecomputed: crc32(data) >>> 0,
      size: data.length,
    });
  }
  return out;
}
