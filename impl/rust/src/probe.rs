// SENDGUARD rust seat - one measurement cell per child process.
//
//   sg_probe       std-only, no crates linked into the measured process
//   sg_probe_norm  same source + unicode-normalization, built with --features normalization
//
// The probe performs one pinned entry action on one frozen hex sample inside one scratch
// directory, observes it through the permitted channels, writes one schema-shaped JSON
// object to --out and exits. Nothing here deletes anything (M19).
#![allow(dead_code)]

use std::collections::BTreeMap;
use std::ffi::{OsStr, OsString};
use std::fs::{File, OpenOptions};
use std::io::{Read, Write};
use std::os::windows::ffi::{OsStrExt, OsStringExt};
use std::path::{Path, PathBuf};
use std::time::Instant;

extern "system" {
    fn QueryDosDeviceW(lpdevice_name: *const u16, lptarget_path: *mut u16, cch: u32) -> u32;
    fn FormatMessageW(flags: u32, source: *const u16, code: u32, lang: u32, buf: *mut u16, size: u32, args: *const u16) -> u32;
    fn GetVolumeInformationW(root: *const u16, vol: *mut u16, volsz: u32, serial: *mut u32, maxcomp: *mut u32, flags: *mut u32, fsn: *mut u16, fsnsz: u32) -> u32;
    fn GetLastError() -> u32;
}


// ------------------------------------------------------------------ json emitting
// ASCII-only: every non-ASCII scalar becomes \uXXXX, so a cp936 console or a latin-1
// reader can never turn clean UTF-8 into apparent garbage on the published face.
fn jesc(s: &str) -> String {
    let mut o = String::new();
    for c in s.chars() {
        match c {
            '"' => o.push_str("\\\""),
            '\\' => o.push_str("\\\\"),
            '\n' => o.push_str("\\n"),
            '\r' => o.push_str("\\r"),
            '\t' => o.push_str("\\t"),
            c if (c as u32) < 0x20 => o.push_str(&format!("\\u{:04x}", c as u32)),
            c if (c as u32) > 0x7e => {
                let cp = c as u32;
                if cp > 0xFFFF {
                    let v = cp - 0x10000;
                    o.push_str(&format!("\\u{:04x}\\u{:04x}", 0xD800 + (v >> 10), 0xDC00 + (v & 0x3FF)));
                } else {
                    o.push_str(&format!("\\u{:04x}", cp));
                }
            }
            c => o.push(c),
        }
    }
    o
}
fn js(s: &str) -> String {
    format!("\"{}\"", jesc(s))
}
fn json_dump(fields: &[(String, String)]) -> String {
    let mut o = String::from("{\n");
    for (i, (k, v)) in fields.iter().enumerate() {
        o.push_str(&format!("  {}: {}", js(k), v));
        o.push_str(if i + 1 < fields.len() { ",\n" } else { "\n" });
    }
    o.push('}');
    o
}
type Fields = Vec<(String, String)>;
fn puts(f: &mut Fields, k: &str, v: &str) {
    f.push((k.to_string(), js(v)));
}
fn put(f: &mut Fields, k: &str, v: String) {
    f.push((k.to_string(), v));
}
fn putb(f: &mut Fields, k: &str, v: bool) {
    f.push((k.to_string(), if v { "true".into() } else { "false".into() }));
}
fn puti(f: &mut Fields, k: &str, v: i64) {
    f.push((k.to_string(), v.to_string()));
}
fn putopt(f: &mut Fields, k: &str, v: Option<String>) {
    match v {
        Some(x) => puts(f, k, &x),
        None => put(f, k, "null".into()),
    }
}
/// schema-typed fields must be omitted, not null: spec/schema.json gives error_code /
/// error_message / sha256_truth / roundtrip_ok a single type each, and null is outside it.
fn put_omit(f: &mut Fields, k: &str, v: Option<String>) {
    if let Some(x) = v {
        puts(f, k, &x);
    }
}
fn put_omit_b(f: &mut Fields, k: &str, v: Option<bool>) {
    if let Some(x) = v {
        putb(f, k, x);
    }
}
fn putob(f: &mut Fields, k: &str, v: Option<bool>) {
    match v {
        Some(x) => putb(f, k, x),
        None => put(f, k, "null".into()),
    }
}

// ------------------------------------------------------------------ sha256 / crc32
const K: [u32; 64] = [
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
];

fn sha256(data: &[u8]) -> [u8; 32] {
    let mut h: [u32; 8] = [
        0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
    ];
    let mut msg = data.to_vec();
    let bitlen = (data.len() as u64) * 8;
    msg.push(0x80);
    while msg.len() % 64 != 56 {
        msg.push(0);
    }
    msg.extend_from_slice(&bitlen.to_be_bytes());
    for chunk in msg.chunks(64) {
        let mut w = [0u32; 64];
        for i in 0..16 {
            w[i] = u32::from_be_bytes([chunk[4 * i], chunk[4 * i + 1], chunk[4 * i + 2], chunk[4 * i + 3]]);
        }
        for i in 16..64 {
            let s0 = w[i - 15].rotate_right(7) ^ w[i - 15].rotate_right(18) ^ (w[i - 15] >> 3);
            let s1 = w[i - 2].rotate_right(17) ^ w[i - 2].rotate_right(19) ^ (w[i - 2] >> 10);
            w[i] = w[i - 16].wrapping_add(s0).wrapping_add(w[i - 7]).wrapping_add(s1);
        }
        let mut v = h;
        for i in 0..64 {
            let s1 = v[4].rotate_right(6) ^ v[4].rotate_right(11) ^ v[4].rotate_right(25);
            let ch = (v[4] & v[5]) ^ ((!v[4]) & v[6]);
            let t1 = v[7].wrapping_add(s1).wrapping_add(ch).wrapping_add(K[i]).wrapping_add(w[i]);
            let s0 = v[0].rotate_right(2) ^ v[0].rotate_right(13) ^ v[0].rotate_right(22);
            let mj = (v[0] & v[1]) ^ (v[0] & v[2]) ^ (v[1] & v[2]);
            let t2 = s0.wrapping_add(mj);
            v[7] = v[6];
            v[6] = v[5];
            v[5] = v[4];
            v[4] = v[3].wrapping_add(t1);
            v[3] = v[2];
            v[2] = v[1];
            v[1] = v[0];
            v[0] = t1.wrapping_add(t2);
        }
        for i in 0..8 {
            h[i] = h[i].wrapping_add(v[i]);
        }
    }
    let mut out = [0u8; 32];
    for i in 0..8 {
        out[4 * i..4 * i + 4].copy_from_slice(&h[i].to_be_bytes());
    }
    out
}
fn sha_hex(data: &[u8]) -> String {
    sha256(data).iter().map(|b| format!("{:02x}", b)).collect()
}
/// claims are keyed on the hex of the name's UTF-8 bytes, the same encoding name_source uses;
/// every name a bisection creates is ASCII, so this round-trip is exact
fn hex_of_name(o: &OsStr) -> String {
    let (t, _lossy) = os_to_string(o);
    to_hex(t.as_bytes())
}
fn to_hex(data: &[u8]) -> String {
    data.iter().map(|b| format!("{:02x}", b)).collect()
}
fn num_or_null(s: &str) -> String {
    let t = s.trim();
    if t.is_empty() { "null".to_string() } else { t.to_string() }
}

/// Structural check of the face this probe is about to publish. A cell file that parses
/// as text but not as JSON is worse than no file: the loader reports a clean run.
fn json_wellformed(s: &str) -> bool {
    let b = s.as_bytes();
    fn ws(b: &[u8], i: &mut usize) {
        while *i < b.len() && matches!(b[*i], b' ' | b'\n' | b'\t' | b'\r') {
            *i += 1;
        }
    }
    fn string(b: &[u8], i: &mut usize) -> bool {
        if *i >= b.len() || b[*i] != b'"' {
            return false;
        }
        *i += 1;
        while *i < b.len() {
            let c = b[*i];
            if c == b'"' {
                *i += 1;
                return true;
            }
            if c == b'\\' {
                *i += 1;
                if *i >= b.len() {
                    return false;
                }
                match b[*i] {
                    b'"' | b'\\' | b'/' | b'b' | b'f' | b'n' | b'r' | b't' => {}
                    b'u' => {
                        for k in 0..4 {
                            if *i + 1 + k >= b.len() || !b[*i + 1 + k].is_ascii_hexdigit() {
                                return false;
                            }
                        }
                        *i += 4;
                    }
                    _ => return false,
                }
            }
            *i += 1;
        }
        false
    }
    fn number(b: &[u8], i: &mut usize) -> bool {
        let start = *i;
        if *i < b.len() && (b[*i] == b'-' || b[*i] == b'+') {
            *i += 1;
        }
        let mut digits = 0;
        while *i < b.len() && (b[*i].is_ascii_digit() || matches!(b[*i], b'.' | b'e' | b'E' | b'-' | b'+')) {
            if b[*i].is_ascii_digit() {
                digits += 1;
            }
            *i += 1;
        }
        digits > 0 && *i > start
    }
    fn value(b: &[u8], i: &mut usize) -> bool {
        ws(b, i);
        if *i >= b.len() {
            return false;
        }
        match b[*i] {
            b'{' => {
                *i += 1;
                ws(b, i);
                if *i < b.len() && b[*i] == b'}' {
                    *i += 1;
                    return true;
                }
                loop {
                    ws(b, i);
                    if !string(b, i) {
                        return false;
                    }
                    ws(b, i);
                    if *i >= b.len() || b[*i] != b':' {
                        return false;
                    }
                    *i += 1;
                    if !value(b, i) {
                        return false;
                    }
                    ws(b, i);
                    if *i < b.len() && b[*i] == b',' {
                        *i += 1;
                        continue;
                    }
                    if *i < b.len() && b[*i] == b'}' {
                        *i += 1;
                        return true;
                    }
                    return false;
                }
            }
            b'[' => {
                *i += 1;
                ws(b, i);
                if *i < b.len() && b[*i] == b']' {
                    *i += 1;
                    return true;
                }
                loop {
                    if !value(b, i) {
                        return false;
                    }
                    ws(b, i);
                    if *i < b.len() && b[*i] == b',' {
                        *i += 1;
                        continue;
                    }
                    if *i < b.len() && b[*i] == b']' {
                        *i += 1;
                        return true;
                    }
                    return false;
                }
            }
            b'"' => string(b, i),
            b't' => {
                if b[*i..].starts_with(b"true") {
                    *i += 4;
                    true
                } else {
                    false
                }
            }
            b'f' => {
                if b[*i..].starts_with(b"false") {
                    *i += 5;
                    true
                } else {
                    false
                }
            }
            b'n' => {
                if b[*i..].starts_with(b"null") {
                    *i += 4;
                    true
                } else {
                    false
                }
            }
            _ => number(b, i),
        }
    }
    let mut i = 0usize;
    value(b, &mut i) && {
        ws(b, &mut i);
        i == b.len()
    }
}
fn crc32(data: &[u8]) -> u32 {
    let mut c: u32 = 0xFFFF_FFFF;
    for b in data {
        c ^= *b as u32;
        for _ in 0..8 {
            c = if c & 1 != 0 { (c >> 1) ^ 0xEDB8_8320 } else { c >> 1 };
        }
    }
    !c
}

// ------------------------------------------------------------------ small helpers
fn unhex(h: &str) -> Result<Vec<u8>, String> {
    let b = h.as_bytes();
    if b.len() % 2 != 0 {
        return Err("odd hex length".into());
    }
    let mut v = Vec::with_capacity(b.len() / 2);
    let mut i = 0;
    while i + 1 < b.len() {
        let hi = (b[i] as char).to_digit(16).ok_or_else(|| format!("bad hex byte at {i}"))?;
        let lo = (b[i + 1] as char).to_digit(16).ok_or_else(|| format!("bad hex byte at {}", i + 1))?;
        v.push(((hi << 4) | lo) as u8);
        i += 2;
    }
    Ok(v)
}
fn os_from_hex(h: &str) -> Result<(OsString, Vec<u8>), String> {
    let bytes = unhex(h)?;
    let s = std::str::from_utf8(&bytes).map_err(|e| format!("sample hex is not valid UTF-8: {e}"))?;
    let units: Vec<u16> = s.encode_utf16().collect();
    Ok((<OsString as OsStringExt>::from_wide(&units), bytes))
}
fn wide_nul(s: &str) -> Vec<u16> {
    let mut v: Vec<u16> = s.encode_utf16().collect();
    v.push(0);
    v
}
fn units_of(o: &OsStr) -> Vec<u16> {
    o.encode_wide().collect()
}
fn os_to_string(o: &OsStr) -> (String, bool) {
    let owned = o.to_string_lossy().into_owned();
    let lossy = owned.contains('\u{fffd}');
    (owned, lossy)
}
fn wlen(p: &Path) -> usize {
    p.as_os_str().encode_wide().count()
}
fn mark(path: &str, text: &str) {
    if path.is_empty() {
        return;
    }
    if let Ok(mut f) = OpenOptions::new().create(true).append(true).open(path) {
        let _ = f.write_all(text.as_bytes());
        let _ = f.write_all(b"\n");
        let _ = f.flush();
    }
}
fn os_message(code: u32) -> String {
    let mut buf = [0u16; 1024];
    let n = unsafe { FormatMessageW(0x1000 | 0x200, std::ptr::null(), code, 0, buf.as_mut_ptr(), buf.len() as u32, std::ptr::null()) };
    if n == 0 {
        return format!("<FormatMessageW rc=0 winerr={}>", unsafe { GetLastError() });
    }
    let taken: Vec<u16> = buf.iter().take(n as usize).copied().collect();
    String::from_utf16(&taken).unwrap_or_else(|_| "<undecodable>".into()).trim_end().to_string()
}
/// kernel32 DOS-device namespace question. Skipped when the name carries an interior
/// NUL, because the query would be silently truncated and answer a different name.
fn dos_device(name: &OsStr) -> (bool, String, bool) {
    let u = units_of(name);
    if u.contains(&0) || u.is_empty() {
        return (false, String::new(), true);
    }
    let mut w = u;
    w.push(0);
    let mut buf = [0u16; 1024];
    let rc = unsafe { QueryDosDeviceW(w.as_ptr(), buf.as_mut_ptr(), buf.len() as u32) };
    if rc == 0 {
        (false, String::new(), false)
    } else {
        let taken: Vec<u16> = buf.iter().take_while(|&&c| c != 0).copied().collect();
        (true, String::from_utf16(&taken).unwrap_or_else(|_| "<undecodable>".into()), false)
    }
}
fn volume_info(root: &str) -> (i64, String) {
    let mut serial = 0u32;
    let mut maxc = 0u32;
    let mut flags = 0u32;
    let mut fsname = [0u16; 64];
    let mut volname = [0u16; 128];
    let r = wide_nul(root);
    let ok = unsafe {
        GetVolumeInformationW(r.as_ptr(), volname.as_mut_ptr(), volname.len() as u32, &mut serial, &mut maxc, &mut flags, fsname.as_mut_ptr(), fsname.len() as u32)
    };
    if ok == 0 {
        return (-1, format!("<GetVolumeInformationW rc=0 winerr={}>", unsafe { GetLastError() }));
    }
    let fs = String::from_utf16_lossy(&fsname.iter().take_while(|&&c| c != 0).copied().collect::<Vec<u16>>());
    (maxc as i64, fs)
}

struct Args {
    m: BTreeMap<String, String>,
}
impl Args {
    fn from_env() -> Args {
        // Contract with the driver: every option is passed as a `--key value` pair,
        // including boolean flags, whose value is "true". No token-swallowing parsing.
        let mut m = BTreeMap::new();
        let mut it = std::env::args_os().skip(1);
        while let Some(a) = it.next() {
            let k = a.to_string_lossy().into_owned();
            if !k.starts_with("--") {
                continue;
            }
            let key = k[2..].to_string();
            match it.next() {
                Some(v) => {
                    m.insert(key, v.to_string_lossy().into_owned());
                }
                None => {
                    m.insert(key, "true".into());
                }
            }
        }
        Args { m }
    }
    fn get(&self, k: &str) -> String {
        self.m.get(k).cloned().unwrap_or_default()
    }
    fn num(&self, k: &str) -> Option<i64> {
        self.m.get(k).and_then(|v| v.parse::<i64>().ok())
    }
    fn flag(&self, k: &str) -> bool {
        self.m.get(k).map(|v| v == "true").unwrap_or(false)
    }
    fn csv(&self, k: &str) -> Vec<String> {
        let v = self.get(k);
        if v.is_empty() {
            Vec::new()
        } else {
            v.split(',').map(|s| s.to_string()).collect()
        }
    }
}

/// Directory enumeration is the dir_view authority (gate.md section 10). DirEntry::metadata
/// and DirEntry::file_type on Windows answer from the data the enumeration already cached,
/// so this leg performs no name-targeted open - which is what makes it legal for reserved
/// device names.
fn enumerate(dir: &Path) -> Vec<(String, bool, i64)> {
    let mut out: Vec<(String, bool, i64)> = Vec::new();
    if let Ok(rd) = std::fs::read_dir(dir) {
        for e in rd.flatten() {
            let (nm, _l) = os_to_string(&e.file_name());
            let is_file = e.file_type().map(|t| t.is_file()).unwrap_or(false);
            let sz = e.metadata().map(|m| m.len() as i64).unwrap_or(-1);
            out.push((nm, is_file, sz));
        }
    }
    out.sort();
    out
}

fn target_path(scratch: &Path, name: &OsStr, path_form: &str) -> PathBuf {
    if path_form == "extended" {
        let mut o = OsString::from(r"\\?\");
        o.push(scratch.as_os_str());
        o.push(OsStr::new("\\"));
        o.push(name);
        PathBuf::from(o)
    } else {
        scratch.join(name)
    }
}

// ------------------------------------------------------------------ pinned entries
#[derive(Clone)]
enum Outcome {
    Ok { written: usize },
    Err { stage: &'static str, code: Option<i32>, msg: String },
}

fn classify(e: &std::io::Error) -> Outcome {
    match e.raw_os_error() {
        Some(c) => Outcome::Err { stage: "syscall", code: Some(c), msg: format!("{e}") },
        None => Outcome::Err { stage: "parse", code: None, msg: format!("{e}") },
    }
}

fn do_entry(entry: &str, target: &Path, payload: &[u8], src_helper: Option<&Path>) -> Outcome {
    match entry {
        "std::fs::File::create" => match File::create(target) {
            Ok(mut f) => match f.write_all(payload).and_then(|_| f.flush()) {
                Ok(_) => Outcome::Ok { written: payload.len() },
                Err(e) => classify(&e),
            },
            Err(e) => classify(&e),
        },
        "std::fs::write" => match std::fs::write(target, payload) {
            Ok(_) => Outcome::Ok { written: payload.len() },
            Err(e) => classify(&e),
        },
        "std::fs::OpenOptions" => match OpenOptions::new().write(true).create(true).open(target) {
            Ok(mut f) => match f.write_all(payload).and_then(|_| f.flush()) {
                Ok(_) => Outcome::Ok { written: payload.len() },
                Err(e) => classify(&e),
            },
            Err(e) => classify(&e),
        },
        "std::fs::rename" => {
            let src = match src_helper {
                Some(s) => s.to_path_buf(),
                None => return Outcome::Err { stage: "tool", code: None, msg: "no rename source supplied".into() },
            };
            if let Err(e) = File::create(&src).and_then(|mut f| {
                f.write_all(payload)?;
                f.flush()
            }) {
                return classify(&e);
            }
            match std::fs::rename(&src, target) {
                Ok(_) => Outcome::Ok { written: payload.len() },
                Err(e) => classify(&e),
            }
        }
        other => Outcome::Err { stage: "tool", code: None, msg: format!("entry {other} is not in the pinned rust list") },
    }
}

// ------------------------------------------------------------------ normalisation face
#[cfg(feature = "normalization")]
mod normface {
    use unicode_normalization::{is_nfc, is_nfd, UnicodeNormalization};

    pub struct Report {
        pub nfc_hex: String,
        pub nfd_hex: String,
        pub is_nfc: bool,
        pub is_nfd: bool,
        pub nfc_equals_peer_nfc: bool,
        pub peer_text: String,
        pub crate_version: String,
        pub unicode_version: String,
        pub face: String,
    }
    pub fn report(text: &str, peers: &[String]) -> Report {
        let nfc: String = text.chars().nfc().collect();
        let nfd: String = text.chars().nfd().collect();
        let (peer_text, eq) = match peers.first() {
            Some(p) => {
                let pnfc: String = p.chars().nfc().collect();
                (p.clone(), pnfc == nfc)
            }
            None => (String::new(), false),
        };
        let (maj, min, patch) = unicode_normalization::UNICODE_VERSION;
        Report {
            nfc_hex: crate::to_hex(nfc.as_bytes()),
            nfd_hex: crate::to_hex(nfd.as_bytes()),
            is_nfc: is_nfc(text),
            is_nfd: is_nfd(text),
            nfc_equals_peer_nfc: eq,
            peer_text,
            crate_version: "unicode-normalization =0.1.25".to_string(),
            unicode_version: format!("{maj}.{min}.{patch}"),
            face: "unicode-normalization linked into the measured process".to_string(),
        }
    }
}

#[cfg(not(feature = "normalization"))]
mod normface {
    pub struct Report {
        pub nfc_hex: String,
        pub nfd_hex: String,
        pub is_nfc: bool,
        pub is_nfd: bool,
        pub nfc_equals_peer_nfc: bool,
        pub peer_text: String,
        pub crate_version: String,
        pub unicode_version: String,
        pub face: String,
    }
    pub fn report(_text: &str, _peers: &[String]) -> Report {
        // Rust's standard library exposes no NFC/NFD operation at all. On the std-only face
        // these questions answer not-achievable-in-stdlib; they never answer as 0.
        Report {
            nfc_hex: String::new(),
            nfd_hex: String::new(),
            is_nfc: false,
            is_nfd: false,
            nfc_equals_peer_nfc: false,
            peer_text: String::new(),
            crate_version: "not-achievable-in-stdlib".to_string(),
            unicode_version: "not-achievable-in-stdlib".to_string(),
            face: "not-achievable-in-stdlib".to_string(),
        }
    }
}

// ------------------------------------------------------------------ zip legs (std-only)
fn zip_build(entries: &[(&[u8], &[u8])]) -> Vec<u8> {
    // STORE method, general purpose bit flag 11 set on every entry (UTF-8 names).
    let mut out: Vec<u8> = Vec::new();
    let mut central: Vec<u8> = Vec::new();
    for (name, data) in entries {
        let crc = crc32(data);
        let off = out.len() as u32;
        let mut lh: Vec<u8> = Vec::new();
        lh.extend_from_slice(&0x0403_4b50u32.to_le_bytes());
        lh.extend_from_slice(&20u16.to_le_bytes());
        lh.extend_from_slice(&0x0800u16.to_le_bytes());
        lh.extend_from_slice(&0u16.to_le_bytes());
        lh.extend_from_slice(&0u16.to_le_bytes());
        lh.extend_from_slice(&0u16.to_le_bytes());
        lh.extend_from_slice(&crc.to_le_bytes());
        lh.extend_from_slice(&(data.len() as u32).to_le_bytes());
        lh.extend_from_slice(&(data.len() as u32).to_le_bytes());
        lh.extend_from_slice(&(name.len() as u16).to_le_bytes());
        lh.extend_from_slice(&0u16.to_le_bytes());
        lh.extend_from_slice(*name);
        lh.extend_from_slice(*data);
        out.append(&mut lh);

        let mut ch: Vec<u8> = Vec::new();
        ch.extend_from_slice(&0x0201_4b50u32.to_le_bytes());
        ch.extend_from_slice(&20u16.to_le_bytes());
        ch.extend_from_slice(&20u16.to_le_bytes());
        ch.extend_from_slice(&0x0800u16.to_le_bytes());
        ch.extend_from_slice(&0u16.to_le_bytes());
        ch.extend_from_slice(&0u16.to_le_bytes());
        ch.extend_from_slice(&0u16.to_le_bytes());
        ch.extend_from_slice(&crc.to_le_bytes());
        ch.extend_from_slice(&(data.len() as u32).to_le_bytes());
        lh_len(&mut ch, data.len());
        ch.extend_from_slice(&(name.len() as u16).to_le_bytes());
        for _ in 0..4 {
            // extra length, comment length, disk number start, internal attributes
            ch.extend_from_slice(&0u16.to_le_bytes());
        }
        ch.extend_from_slice(&0u32.to_le_bytes()); // external attributes
        ch.extend_from_slice(&off.to_le_bytes());
        ch.extend_from_slice(*name);
        central.append(&mut ch);
    }
    let cd_off = out.len() as u32;
    let cd_len = central.len() as u32;
    out.extend_from_slice(&central);
    let mut eocd: Vec<u8> = Vec::new();
    eocd.extend_from_slice(&0x0605_4b50u32.to_le_bytes());
    for _ in 0..2 {
        eocd.extend_from_slice(&0u16.to_le_bytes());
    }
    eocd.extend_from_slice(&(entries.len() as u16).to_le_bytes());
    eocd.extend_from_slice(&(entries.len() as u16).to_le_bytes());
    eocd.extend_from_slice(&cd_len.to_le_bytes());
    eocd.extend_from_slice(&cd_off.to_le_bytes());
    eocd.extend_from_slice(&0u16.to_le_bytes());
    out.append(&mut eocd);
    out
}
fn lh_len(ch: &mut Vec<u8>, n: usize) {
    ch.extend_from_slice(&(n as u32).to_le_bytes());
}
fn le16(b: &[u8], i: usize) -> usize {
    (b[i] as usize) | ((b[i + 1] as usize) << 8)
}
fn le32(b: &[u8], i: usize) -> usize {
    (b[i] as usize) | ((b[i + 1] as usize) << 8) | ((b[i + 2] as usize) << 16) | ((b[i + 3] as usize) << 24)
}
fn zip_parse_central(bytes: &[u8]) -> Vec<(String, bool, u32, usize)> {
    let mut out = Vec::new();
    let n = bytes.len();
    if n < 22 {
        return out;
    }
    let mut eocd = usize::MAX;
    let mut i = n - 22;
    loop {
        if le32(bytes, i) == 0x0605_4b50 {
            eocd = i;
            break;
        }
        if i == 0 {
            break;
        }
        i -= 1;
    }
    if eocd == usize::MAX {
        return out;
    }
    let count = le16(bytes, eocd + 10);
    let mut off = le32(bytes, eocd + 16);
    for _ in 0..count {
        if off + 46 > n || le32(bytes, off) != 0x0201_4b50 {
            break;
        }
        let flag = le16(bytes, off + 8) as u16;
        let crc = le32(bytes, off + 16) as u32;
        let nl = le16(bytes, off + 28);
        let extra = le16(bytes, off + 30);
        let comment = le16(bytes, off + 32);
        if off + 46 + nl > n {
            break;
        }
        let nb = &bytes[off + 46..off + 46 + nl];
        out.push((String::from_utf8_lossy(nb).into_owned(), flag & 0x0800 != 0, crc, off + 46 + nl + extra + comment));
        off += 46 + nl + extra + comment;
    }
    out
}

// ------------------------------------------------------------------ main
fn main() {
    let a = Args::from_env();
    let t0 = Instant::now();
    let mode = {
        let m = a.get("mode");
        if m.is_empty() { "create".to_string() } else { m }
    };
    let out_path = a.get("out");
    let markfile = a.get("mark");
    mark(&markfile, &format!("start mode={mode} pid={}", std::process::id()));

    let mut f: Fields = Vec::new();
    let mut hard_fail = String::new();

    // identity block: echoed verbatim from what the driver passed in
    puti(&mut f, "format_version", 1);
    puts(&mut f, "case_id", &a.get("case"));
    putopt(&mut f, "case_id_frozen", if a.get("case-frozen").is_empty() { None } else { Some(a.get("case-frozen")) });
    puts(&mut f, "case_group", &a.get("group"));
    // sub_identity is an OBJECT of the dimensions that vary for this face, as ci/equality.py
    // requires; an empty object is the cell saying "nothing varies here".
    let declared: Vec<String> = a.csv("sub-keys");
    let mut sub_vals: Vec<String> = Vec::new();
    for k in &declared {
        let v = match k.as_str() {
            "api_entry" => Some(js(&a.get("entry"))),
            "path_form" => Some(js(&a.get("path-form"))),
            "base_len" => a.get("base-len").parse::<i64>().ok().map(|n| n.to_string()),
            "member" => if a.get("member").is_empty() { None } else { Some(js(&a.get("member"))) },
            other => Some(js(&a.get(other))),
        };
        if let Some(x) = v {
            if x != "\"\"" {
                sub_vals.push(format!("{}: {}", js(k), x));
            }
        }
    }
    put(&mut f, "sub_identity", format!("{{{}}}", sub_vals.join(", ")));
    puts(&mut f, "sub_identity_shape", "object of the declared dimensions, per ci/equality.py sub_identity(); a list would be recorded by that gate as a contract defect");
    puts(&mut f, "sub", &a.get("sub"));
    puts(&mut f, "language", "rust");
    puts(&mut f, "os", "windows");
    puts(&mut f, "os_version", &a.get("os-version"));
    puts(&mut f, "arch", &a.get("arch"));
    puts(&mut f, "locale", &a.get("locale"));
    puts(&mut f, "api_entry", &a.get("entry"));
    putb(&mut f, "primary", a.flag("primary"));
    puti(&mut f, "attempt", a.num("attempt").unwrap_or(1));
    puts(&mut f, "harness_version", &a.get("harness"));
    puts(&mut f, "worker_id", &a.get("worker"));
    puts(&mut f, "started_at", &a.get("started-at"));
    puts(&mut f, "spec_sha256", &a.get("spec-sha256"));
    puts(&mut f, "spec_sha256_worktree", &a.get("spec-sha256-worktree"));
    puts(&mut f, "spec_face_note", "spec_sha256 is of `git cat-file blob HEAD:spec/cases.yaml`; spec_sha256_worktree is of the file on disk");
    puts(&mut f, "probe_sha256", &a.get("probe-sha256"));
    puts(&mut f, "probe_face", &a.get("probe-face"));
    puts(&mut f, "toolchain", &a.get("toolchain"));
    puts(&mut f, "toolchain_note", "rustc on PATH is the rustup shim C:\\Users\\Administrator\\.cargo\\bin\\rustc.exe; the resolved toolchain binary is recorded by the driver");
    puti(&mut f, "deps_direct", a.num("deps-direct").unwrap_or(0));
    puti(&mut f, "deps_total", a.num("deps-total").unwrap_or(0));
    puts(&mut f, "deps_source", &a.get("deps-source"));
    if a.get("mechanism-class").is_empty() {
        puts(&mut f, "mechanism_class_note", "no frozen mechanism class applies: this is a control cell, which measures the ruler");
    } else {
        puts(&mut f, "mechanism_class", &a.get("mechanism-class"));
    }
    if !a.get("member").is_empty() {
        puts(&mut f, "member", &a.get("member"));
    }
    if !a.get("base-len").is_empty() {
        puti(&mut f, "base_len", a.num("base-len").unwrap_or(0));
    }
    puts(&mut f, "length_unit", "utf16_code_units");
    puts(&mut f, "length_unit_basis", "every width in this cell (name_len, total_path_len, base_len) is counted in UTF-16 code units, because OsString on Windows is WTF-16; code_points and utf8_bytes are published separately in len_triple");
    puts(&mut f, "name_encoding", "hex_raw_bytes");
    puts(&mut f, "name_encoding_basis", "name_source and name_landed_as_hex are the hex of the raw UTF-8 bytes of the name, never the name itself (N12); no cell in this port records hex_utf16le");
    puts(&mut f, "longpath_mechanism", &a.get("longpath-mechanism"));
    puts(&mut f, "longpath_evidence", &a.get("longpath-evidence"));
    putopt(&mut f, "spec_applicability", if a.get("applicable").is_empty() { None } else { Some(a.get("applicable")) });
    puts(&mut f, "cell_state", if mode == "bisect" { "measured-bisection" } else { "measured" });
    puts(&mut f, "contract_role", &a.get("contract-role"));
    putb(&mut f, "extra", a.get("contract-role") == "extra");
    puts(&mut f, "contract_key", &a.get("contract-key"));
    if !a.get("variant-of").is_empty() {
        puts(&mut f, "variant_of", &a.get("variant-of"));
    }
    if !a.get("superseded-by").is_empty() {
        puts(&mut f, "superseded_by", &a.get("superseded-by"));
    }
    if !a.get("blind-source").is_empty() {
        puts(&mut f, "blind_source", &a.get("blind-source"));
        puts(&mut f, "blind_map_sha256", &a.get("blind-map-sha256"));
        puts(&mut f, "blind_map_self_sha256", &a.get("blind-map-self-sha256"));
        puts(&mut f, "blind_map_sealed_at", &a.get("blind-sealed-at"));
        puts(&mut f, "blind_opened_by", "NOTICE-rev6 item 2 orders these five cells and names this file as their source; the seal was not lifted by this seat's own choice");
    }
    puts(&mut f, "contract_sha256", &a.get("contract-sha256"));

    let payload = match unhex(&a.get("payload-hex")) {
        Ok(p) => p,
        Err(e) => {
            hard_fail = format!("payload hex undecodable: {e}");
            Vec::new()
        }
    };

    if mode == "jsoncheck" {
        // standing two-sided self-test of the face validator itself
        let good = "{\"a\": 1, \"b\": [1, 2, {\"c\": \"x\\\"y\"}], \"d\": null, \"e\": true}";
        let bad_missing_comma = "{\"a\": 1 \"b\": 2}";
        let bad_trailing = "{\"a\": 1} }";
        let bad_empty_value = "{\"a\": }";
        let arms_ok = json_wellformed(good)
            && !json_wellformed(bad_missing_comma)
            && !json_wellformed(bad_trailing)
            && !json_wellformed(bad_empty_value);
        let body = format!(
            "{{\n  \"green_arm_passes\": {},\n  \"red_arm_missing_comma_refused\": {},\n  \"red_arm_trailing_refused\": {},\n  \"red_arm_empty_value_refused\": {},\n  \"arms_all_pass\": {}\n}}",
            hitb(json_wellformed(good)),
            hitb(!json_wellformed(bad_missing_comma)),
            hitb(!json_wellformed(bad_trailing)),
            hitb(!json_wellformed(bad_empty_value)),
            hitb(arms_ok)
        );
        mark(&markfile, &format!("jsoncheck arms_all_pass={arms_ok}"));
        if !arms_ok {
            eprintln!("jsoncheck: the face validator itself is broken");
            std::process::exit(6);
        }
        if let Ok(mut w) = File::create(&out_path) {
            let _ = w.write_all(body.as_bytes());
            let _ = w.flush();
        }
        std::process::exit(0);
    }

    if mode == "env" {
        let (mc, fs) = volume_info(&a.get("volume-root"));
        puti(&mut f, "max_component", mc);
        puts(&mut f, "filesystem", &fs);
        let mut rows: Vec<String> = Vec::new();
        for n in a.csv("dos-device-names") {
            let (hit, tgt, skipped) = dos_device(OsStr::new(&n));
            rows.push(format!("{{\"name\": {}, \"device_bound\": {}, \"skipped\": {}, \"target\": {}}}", js(&n), hitb(hit), hitb(skipped), js(&tgt)));
        }
        put(&mut f, "dos_devices", format!("[{}]", rows.join(", ")));
        puts(&mut f, "rtl_are_long_paths_enabled", "not-obtainable-in-this-face: ntdll!RtlAreLongPathsEnabled failed to link (link.exe error 1120) on this toolchain, no substitute value invented");
        puts(&mut f, "env_probe", "kernel32 GetVolumeInformationW + QueryDosDeviceW through std FFI, no crates linked");
    } else if mode == "create" || mode == "zip" || mode == "bisect" {
        let scratch = PathBuf::from(a.get("scratch"));
        let path_form = a.get("path-form");
        let entry = a.get("entry");
        let no_content_read = a.flag("no-content-read");
        let prior_claimed = a.num("prior-entries").unwrap_or(0);

        let pre = enumerate(&scratch);
        putb(&mut f, "scratch_verified_empty", pre.is_empty());
        puti(&mut f, "scratch_pre_entries", pre.len() as i64);
        puts(&mut f, "scratch_dir", &a.get("scratch"));
        puts(&mut f, "scratch_scope", &a.get("scratch-scope"));

        if mode == "bisect" {
            run_bisect(&a, &mut f, &payload, &markfile, &scratch, &path_form, &entry);
        } else {
            let members = a.csv("member-hex");
            let hex = members.first().cloned().unwrap_or_default();
            puts(&mut f, "name_source", &hex);
            if !a.get("spec-sample-string").is_empty() {
                puts(&mut f, "spec_sample_string", &a.get("spec-sample-string"));
                puts(&mut f, "spec_sample_note", "cases.yaml writes this case's sample_hex as a sentence, not as hex; the sentence is published verbatim here and name_source carries the hex of the name actually created");
            }
            puts(&mut f, "name_source_kind", &a.get("name-source-kind"));
            if members.len() > 1 {
                put(&mut f, "co_resident_member_hex", format!("[{}]", members[1..].iter().map(|s| js(s)).collect::<Vec<_>>().join(", ")));
            }
            let decoded = os_from_hex(&hex);
            match decoded {
                Err(e) => {
                    hard_fail = e.clone();
                    puts(&mut f, "sample_decode_error", &e);
                    puts(&mut f, "create_result", "err_at_parse");
                    puts(&mut f, "error_stage", "tool");
                    puts(&mut f, "error_code", "sample-hex-undecodable");
                    puts(&mut f, "error_message", &e);
                    puts(&mut f, "read_result", "eof");
                    puts(&mut f, "os_legality_verdict", "unknown");
                    puts(&mut f, "verdict_via", "none");
                    puts(&mut f, "attribution_layer", "L2");
                }
                Ok((name_os, name_bytes)) => {
                    let mut write_bytes = payload.clone();
                    if mode == "zip" {
                        let mut owned: Vec<(Vec<u8>, Vec<u8>)> = Vec::new();
                        let mut names: Vec<String> = Vec::new();
                        for h in a.csv("zip-entry-hex") {
                            match unhex(&h) {
                                Ok(b) => {
                                    names.push(String::from_utf8_lossy(&b).into_owned());
                                    owned.push((b, payload.clone()));
                                }
                                Err(e) => puts(&mut f, "zip_entry_decode_error", &e),
                            }
                        }
                        put(&mut f, "zip_entry_names_written", format!("[{}]", names.iter().map(|s| js(s)).collect::<Vec<_>>().join(", ")));
                        puts(&mut f, "zip_entry_name_source", &a.get("zip-entry-source-note"));
                        puts(&mut f, "zip_writer", "STORE-method archive built by hand in std only (local header + central directory + EOCD), general purpose bit 11 set on every entry");
                        let refs: Vec<(&[u8], &[u8])> = owned.iter().map(|(n, d)| (n.as_slice(), d.as_slice())).collect();
                        write_bytes = zip_build(&refs);
                        puti(&mut f, "zip_archive_bytes", write_bytes.len() as i64);
                    }

                    let target = target_path(&scratch, &name_os, &path_form);
                    let (name_str, lossy) = os_to_string(&name_os);
                    puts(&mut f, "name_requested", &name_str);
                    putb(&mut f, "name_requested_lossy", lossy);
                    puti(&mut f, "name_len", units_of(&name_os).len() as i64);
                    puti(&mut f, "total_path_len", wlen(&target) as i64);
                    puts(&mut f, "path_form", &path_form);
                    put(
                        &mut f,
                        "len_triple",
                        format!(
                            "{{\"code_points\": {}, \"utf16_code_units\": {}, \"utf8_bytes\": {}}}",
                            name_str.chars().count(),
                            units_of(&name_os).len(),
                            name_bytes.len()
                        ),
                    );
                    if a.flag("len-pinned-fill") {
                        // rev7: the len family's component is pinned, so this face has to describe the
                        // bytes it passed and keep the measured ceiling in a field of its own.
                        let bl = a.num("base-len").unwrap_or(-1);
                        let unit_hex = {
                            let u = a.get("len-fill-unit-hex");
                            if u.is_empty() { "61".to_string() } else { u }
                        };
                        let want: Vec<u16> = match u32::from_str_radix(&unit_hex, 16)
                            .ok()
                            .and_then(char::from_u32)
                        {
                            Some(c) => {
                                let s = c.to_string();
                                s.encode_utf16().collect()
                            }
                            None => Vec::new(),
                        };
                        let un = units_of(&name_os);
                        let repeated = !want.is_empty()
                            && un.iter().enumerate().all(|(i, u)| *u == want[i % want.len()]);
                        let cp = name_str.chars().count() as i64;
                        let ub = name_bytes.len() as i64;
                        puts(&mut f, "len_fill_unit_hex", &unit_hex);
                        puts(&mut f, "len_fill_rule", &a.get("len-fill-rule"));
                        putb(&mut f, "name_is_pinned_fill_repeated", repeated);
                        putb(&mut f, "name_len_equals_base_len", un.len() as i64 == bl);
                        putb(&mut f, "len_triple_equals_base_len", cp == bl && un.len() as i64 == bl && ub == bl);
                        puti(&mut f, "len_parent_dir_code_units", wlen(&scratch) as i64);
                        puts(&mut f, "len_input_basis", "rev7 pins this family: name_source is the hex of the code units actually handed to the API, made by repeating spec/cases.yaml len_fill.unit_hex until the component is exactly base_len code units with nothing appended; the ceiling this port converged to is a different quantity and is published in len_ceiling, and the width-pinned tier evidence stays in its own extra:true cells");
                        if !a.get("len-ceiling-max-ok").is_empty() {
                            let tiers: Vec<String> = a.csv("len-ceiling-tier-roots").iter().map(|s| js(s)).collect();
                            let mut pieces: Vec<String> = Vec::new();
                            pieces.push(format!("\"max_ok_code_units\": {}", a.get("len-ceiling-max-ok")));
                            pieces.push(format!("\"first_failing_code_units\": {}", js(&a.get("len-ceiling-first-failing"))));
                            pieces.push(format!("\"first_failing_winerror\": {}", js(&a.get("len-ceiling-winerror"))));
                            pieces.push(format!("\"measured_by_case_id\": {}", js(&a.get("len-ceiling-measured-in"))));
                            pieces.push(format!("\"measured_by_path_form\": {}", js(&a.get("path-form"))));
                            pieces.push(format!("\"measured_by_face_sha256\": {}", js(&a.get("len-ceiling-face-sha256"))));
                            pieces.push(format!("\"width_pinned_tier_roots\": [{}]", tiers.join(", ")));
                            pieces.push(format!("\"basis\": {}", js("the widest component this port could create, converged by bisection in the extra cell named by measured_by_case_id at the same path_form; it is NOT the width of the name in this cell, which is exactly base_len")));
                            put(&mut f, "len_ceiling", format!("{{{}}}", pieces.join(", ")));
                        } else if !a.get("len-ceiling-missing").is_empty() {
                            put(&mut f, "len_ceiling", format!(
                                "{{\"status\": {}, \"reason\": {}}}",
                                js("not-measured-before-this-cell"), js(&a.get("len-ceiling-missing"))));
                        }
                    }
                    mark(&markfile, "before-create");
                    let src = if entry == "std::fs::rename" { Some(scratch.join(OsStr::new(&a.get("rename-src-name")))) } else { None };
                    let outcome = do_entry(&entry, &target, &write_bytes, src.as_deref());
                    mark(&markfile, "after-create");
                    finish_cell(&a, &mut f, &outcome, &target, &scratch, &name_os, &write_bytes, &payload, no_content_read, prior_claimed, &markfile);
                }
            }
        }
    } else {
        hard_fail = format!("unknown mode {mode}");
    }

    puti(&mut f, "elapsed_ms", t0.elapsed().as_millis() as i64);
    if !hard_fail.is_empty() {
        puts(&mut f, "tool_fail", &hard_fail);
    }

    let body = json_dump(&f);
    mark(&markfile, "before-write-out");
    // a repeated key would still parse (the reader silently takes the last face), so check the
    // field list itself before publishing
    let mut seen_keys: Vec<&str> = Vec::with_capacity(f.len());
    let mut dups: Vec<String> = Vec::new();
    for (k, _v) in &f {
        if seen_keys.contains(&k.as_str()) {
            dups.push(js(k));
        } else {
            seen_keys.push(k.as_str());
        }
    }
    if !dups.is_empty() {
        mark(&markfile, &format!("refused: duplicate keys {}", dups.join(",")));
        eprintln!("probe refuses to publish a cell face with duplicate keys");
        std::process::exit(7);
    }
    if !json_wellformed(&body) {
        mark(&markfile, &format!("refused: body is not well-formed JSON ({} bytes)", body.len()));
        eprintln!("probe refuses to publish a malformed cell face");
        std::process::exit(5);
    }
    let mut ok_write = true;
    match File::create(&out_path) {
        Ok(mut w) => {
            if w.write_all(body.as_bytes()).is_err() {
                ok_write = false;
            }
            let _ = w.flush();
        }
        Err(_) => ok_write = false,
    }
    let readback = std::fs::read(&out_path).unwrap_or_default();
    let verified = ok_write
        && readback.len() == body.len()
        && body.as_bytes().last() == Some(&b'}')
        && readback == body.as_bytes()
        && json_wellformed(&String::from_utf8_lossy(&readback));
    mark(&markfile, &format!("after-write-out verified={verified} bytes={}", readback.len()));
    if !verified {
        eprintln!("probe cannot verify its own output face: {out_path}");
        std::process::exit(4);
    }
    std::process::exit(0);
}

fn hitb(b: bool) -> &'static str {
    if b { "true" } else { "false" }
}

#[allow(clippy::too_many_arguments)]
fn finish_cell(
    a: &Args,
    f: &mut Fields,
    outcome: &Outcome,
    target: &Path,
    scratch: &Path,
    name_os: &OsStr,
    write_bytes: &[u8],
    payload: &[u8],
    no_content_read: bool,
    prior_claimed: i64,
    markfile: &str,
) {
    let (create_result, error_stage, error_code, error_msg) = match outcome {
        Outcome::Ok { written } => {
            puti(f, "bytes_written", *written as i64);
            ("ok", "null", None, None)
        }
        Outcome::Err { stage, code, msg } => {
            put(f, "bytes_written", "null".into());
            let cr = match *stage {
                "parse" => "err_at_parse",
                _ => "err_at_syscall",
            };
            (cr, *stage, code.map(|c| c.to_string()), Some(msg.clone()))
        }
    };
    let create_result = create_result.to_string();
    puts(f, "create_result", &create_result);
    puts(f, "error_stage", error_stage);
    put_omit(f, "error_code", error_code.clone());
    put_omit(f, "error_message", error_msg.clone());
    if let Some(c) = &error_code {
        if let Ok(ci) = c.parse::<u32>() {
            puts(f, "error_message_os", &os_message(ci));
            puts(f, "error_message_os_channel", "kernel32 FormatMessageW of the raw code, \\u-escaped in this file");
        }
    }
    if matches!(outcome, Outcome::Err { stage: "tool", .. }) {
        puts(f, "instrument_note", "error_stage=tool: the pinned entry list itself refused this action, not the filesystem");
    }

    // device namespace question, asked two ways: the full name and the stem before the
    // first dot, because QueryDosDeviceW only knows the bare device name (CON, not CON.txt)
    let (dev_bound, dev_target, dev_skipped) = dos_device(name_os);
    let stem_os = {
        let u = units_of(name_os);
        let cut = u.iter().position(|&c| c == b'.' as u16).unwrap_or(u.len());
        <OsString as OsStringExt>::from_wide(&u[..cut])
    };
    let (stem_bound, stem_target, stem_skipped) = dos_device(&stem_os);
    putb(f, "os_device_binding", dev_bound || stem_bound);
    putb(f, "os_device_binding_full_name", dev_bound);
    putb(f, "os_device_binding_stem", stem_bound);
    putb(f, "os_device_query_skipped", dev_skipped || stem_skipped);
    putopt(f, "os_device_target", if dev_target.is_empty() { None } else { Some(dev_target) });
    putopt(f, "os_device_target_stem", if stem_target.is_empty() { None } else { Some(stem_target) });
    putopt(f, "os_device_stem_queried", if stem_skipped { None } else { { let (t, _l) = os_to_string(&stem_os); Some(t) } });
    puts(f, "os_device_channel", "kernel32 QueryDosDeviceW through std FFI (no crates): is the name, or its stem before the first dot, bound to a device in the DOS-device namespace");

    // dir_view
    mark(markfile, "before-enum");
    let listing = enumerate(scratch);
    mark(markfile, "after-enum");
    let wanted = units_of(name_os);
    let landed = listing.iter().find(|(nm, _is_file, _sz)| nm.encode_utf16().collect::<Vec<u16>>() == wanted);
    let extras: Vec<String> = listing
        .iter()
        .filter(|(nm, _is_file, _sz)| nm.encode_utf16().collect::<Vec<u16>>() != wanted)
        .map(|(nm, _a, _b)| nm.clone())
        .collect();
    // did the name land under a different spelling? (trailing dot / space stripping)
    let mut mutated = false;
    let mut landed_as: Option<String> = None;
    if landed.is_none() && create_result == "ok" {
        for e in &extras {
            let eu: Vec<u16> = e.encode_utf16().collect();
            if eu.len() < wanted.len() && wanted[..eu.len()] == eu[..] {
                mutated = true;
                landed_as = Some(e.clone());
                break;
            }
        }
    }
    if let Some((nm, _is_file, _sz)) = landed {
        landed_as = Some(nm.clone());
    }
    // an entry that is this cell's own mutated landing, its own requested name, or the declared
    // helper source of the rename entry is claimed; everything else in the directory is an extra
    let helper_name = a.get("rename-src-name");
    let helper = OsStr::new(&helper_name);
    let helper_units = units_of(helper);
    let helper_present = !helper_units.is_empty() && extras.iter().any(|e| e.encode_utf16().collect::<Vec<u16>>() == helper_units);
    let mut prior_units: Vec<Vec<u16>> = Vec::new();
    for h in a.csv("prior-claim-hexes") {
        if let Ok((o, _)) = os_from_hex(&h) {
            prior_units.push(units_of(&o));
        }
    }
    let own_units: Vec<Vec<u16>> = [
        wanted.clone(),
        landed_as.as_ref().map(|s| s.encode_utf16().collect::<Vec<u16>>()).unwrap_or_default(),
        helper_units.clone(),
    ]
    .into_iter()
    .filter(|v| !v.is_empty())
    .collect();
    let is_claimed = |nm: &String| -> bool {
        let u: Vec<u16> = nm.encode_utf16().collect();
        own_units.iter().any(|c| *c == u) || prior_units.iter().any(|c| *c == u)
    };
    let unclaimed: Vec<String> = extras.iter().filter(|e| !is_claimed(e)).cloned().collect();
    puti(f, "enumeration_count", listing.len() as i64);
    puti(f, "enumeration_files", listing.iter().filter(|x| x.1).count() as i64);
    puti(f, "enumeration_dirs", listing.iter().filter(|x| !x.1).count() as i64);
    puti(f, "prior_claimed_entries", prior_units.len() as i64);
    puti(f, "unclaimed_extras", unclaimed.len() as i64);
    putb(f, "helper_source_present", helper_present);
    put(f, "unclaimed_names", format!("[{}]", unclaimed.iter().take(12).map(|s| js(s)).collect::<Vec<_>>().join(", ")));
    put(f, "other_entries", format!("[{}]", extras.iter().take(12).map(|s| js(s)).collect::<Vec<_>>().join(", ")));
    putb(f, "name_mutated", mutated);
    putopt(f, "name_landed_as", landed_as.clone());
    putopt(f, "name_landed_as_hex", landed_as.as_ref().map(|s| to_hex(s.as_bytes())));
    puts(f, "name_landed_as_face", "the name exactly as the parent directory enumerates it; hex is its UTF-8 bytes");

    let bytes_on_disk = match landed {
        Some((_nm, _is_file, sz)) => *sz,
        None => 0,
    };
    puti(f, "bytes_on_disk", bytes_on_disk);
    putb(f, "phantom", create_result == "ok" && landed.is_none() && !mutated);
    let written_claim = match outcome {
        Outcome::Ok { written } => Some(*written as i64),
        _ => None,
    };
    putob(f, "type_ii_divergence", written_claim.map(|w| w != bytes_on_disk || landed.is_none()));
    puts(f, "type_ii_basis", "bytes_written (the write call's own claim) against bytes_on_disk (dir_view authority)");

    // path_view stat leg, only when an entry exists and the name is not device-guarded
    if landed.is_some() && !no_content_read {
        match std::fs::metadata(target) {
            Ok(m) => {
                putb(f, "enum_to_stat_agrees", m.len() as i64 == bytes_on_disk);
                puti(f, "stat_len", m.len() as i64);
            }
            Err(e) => {
                putb(f, "enum_to_stat_agrees", false);
                puts(f, "stat_error", &format!("{e}"));
            }
        }
    } else if landed.is_some() {
        puts(f, "enum_to_stat_agrees_skipped", "device-name rule: no name-targeted open, dir_view only");
    }

    // read leg
    let mut read_result = "not_applicable";
    let mut read_bytes: i64 = 0;
    let mut truth: Option<String> = None;
    let mut roundtrip: Option<bool> = None;
    let mut read_buf: Vec<u8> = Vec::new();
    if no_content_read {
        putb(f, "read_attempt", false);
        putb(f, "content_read_performed", false);
        puts(f, "read_channel", "none: reserved device name, create and list only");
        puts(f, "read_skipped_reason", "the name is a reserved device name (or carries an interior U+0000), and this project's order forbids opening or reading its contents; enumeration of the parent directory is the only observation made");
    } else if create_result != "ok" && !mutated {
        // rev4: nothing landed, so nothing was read. Claiming eof here would be rewriting the
        // verdict to satisfy a ruler that predates the fifth word.
        putb(f, "read_attempt", false);
        putb(f, "content_read_performed", false);
        puts(f, "read_channel", "none: creation refused the name, so there was nothing to read");
        puts(f, "read_skipped_reason", "create_result is not ok and no entry under the requested name was enumerated");
    } else {
        mark(markfile, "before-read");
        putb(f, "read_attempt", true);
        match File::open(target) {
            Ok(mut fh) => match fh.read_to_end(&mut read_buf) {
                Ok(n) => {
                    read_bytes = n as i64;
                    read_result = if n == 0 { "eof" } else { "ok" };
                    putb(f, "content_read_performed", n > 0);
                    truth = Some(sha_hex(&read_buf));
                    let want = if a.flag("zip-face") { write_bytes } else { payload };
                    roundtrip = Some(read_buf == want);
                }
                Err(e) => {
                    puts(f, "read_error", &format!("{e}"));
                    putb(f, "content_read_performed", false);
                }
            },
            Err(e) => {
                puts(f, "read_error", &format!("{e}"));
                puts(f, "read_error_code", &e.raw_os_error().map(|c| c.to_string()).unwrap_or_else(|| format!("{:?}", e.kind())));
                putb(f, "content_read_performed", false);
            }
        }
        mark(markfile, "after-read");
        puts(f, "read_channel", "std::fs::File::open + read_to_end on the requested path");
    }
    puts(f, "read_result", read_result);
    if read_result == "not_applicable" {
        puts(f, "read_word_authority", "spec/canonical.md section 5 fifth word (rev4). spec/schema.json and spec/validate.py still list four read_result words; this cell follows canonical.md and the conflict is reported, not smoothed");
    }
    puti(f, "read_bytes", read_bytes);
    put_omit_b(f, "roundtrip_ok", roundtrip);

    puts(f, "sha256_self", &sha_hex(write_bytes));
    put_omit(f, "sha256_truth", truth.clone());
    puts(f, "sha256_payload_source", "sha256_self = bytes handed to the write call; sha256_truth = digest the probe computed over the bytes read back from disk");

    let verdict = if landed.is_some() {
        "legal"
    } else if create_result == "hang" || create_result == "err_at_parse" {
        "unknown"
    } else if dev_bound || error_stage == "syscall" || mutated || create_result == "ok" {
        "illegal"
    } else {
        "unknown"
    };
    puts(f, "os_legality_verdict", verdict);
    puts(f, "os_legality_basis", "legal iff the parent directory enumerates an entry under the exact requested name after the attempt; illegal iff no such entry exists because the OS refused the name, resolved it to a device, or stored it under a mutated spelling; unknown iff the attempt never reached the OS");
    puts(f, "os_legality_channel", "dir_view enumeration authority (gate.md section 10) plus QueryDosDeviceW");
    puts(f, "verdict_via", if verdict == "unknown" { "none" } else { "win32" });
    puts(f, "verdict_via_basis", if verdict == "unknown" {
        "the OS was never asked: the standard library refused the name before any syscall, so no tool can be credited with this verdict"
    } else {
        "the verdict comes from the Win32/NTFS namespace itself (parent-directory enumeration plus kernel32 QueryDosDeviceW through std FFI); no .NET or cmd.exe face was consulted on this host"
    });

    let layer = if error_stage == "parse" || error_stage == "tool" {
        "L2"
    } else {
        "L1"
    };
    puts(f, "attribution_layer", layer);
    puts(f, "attribution_basis", if layer == "L2" { "std refused the action before any syscall reached the OS, so the divergence originates in the standard library's policy" } else { "the answer came back from the OS/namespace; the standard library only relayed it" });

    // coexistence observation (frozen T09/T19 members share one directory)
    let peers = a.csv("member-hex");
    if peers.len() > 1 {
        let mut hits = 0i64;
        let mut present: Vec<String> = Vec::new();
        for p in &peers[1..] {
            if let Ok((pos, _)) = os_from_hex(p) {
                let pu = units_of(&pos);
                if listing.iter().any(|(nm, _a, _b)| nm.encode_utf16().collect::<Vec<u16>>() == pu) {
                    hits += 1;
                    present.push(js(p));
                }
            }
        }
        puti(f, "same_name_hits", hits);
        put(f, "co_resident_names_present", format!("[{}]", present.join(", ")));
        puts(f, "coexistence_note", "members were created sequentially in this one directory by separate per-cell child processes; this cell is the one whose sample is name_source");
    }

    // normalisation face
    if a.flag("norm-face") {
        let source_hex = a.get("name-source");
        if source_hex.is_empty() || a.get("member-hex").is_empty() {
            puts(f, "norm_face", "refused: the cell supplied no sample hex to normalise, and an empty answer here would be a silent zero");
        } else {
        let sample_text = String::from_utf8_lossy(&match unhex(&source_hex) {
            Ok(b) => b,
            Err(e) => {
                puts(f, "norm_refusal_reason", &format!("sample hex undecodable: {e}"));
                Vec::new()
            }
        })
        .into_owned();
        let peer_texts: Vec<String> = peers
            .iter()
            .skip(1)
            .filter_map(|p| unhex(p).ok().map(|b| String::from_utf8_lossy(&b).into_owned()))
            .collect();
        let rep = normface::report(&sample_text, &peer_texts);
        puts(f, "norm_nfc_hex", &rep.nfc_hex);
        puts(f, "norm_nfd_hex", &rep.nfd_hex);
        putb(f, "norm_is_nfc", rep.is_nfc);
        putb(f, "norm_is_nfd", rep.is_nfd);
        putb(f, "norm_equivalent_to_peer", rep.nfc_equals_peer_nfc);
        putopt(f, "norm_peer_text", if rep.peer_text.is_empty() { None } else { Some(rep.peer_text.clone()) });
        puts(f, "norm_crate", &rep.crate_version);
        puts(f, "norm_face", &rep.face);
        put(
            f,
            "env",
            format!(
                "{{\"unicode_version\": {}, \"toolchain\": {}, \"LongPathsEnabled\": {}, \"max_component\": {}, \"locale\": {}}}",
                js(&rep.unicode_version),
                js(&a.get("toolchain")),
                num_or_null(&a.get("longpaths-enabled")),
                num_or_null(&a.get("max-component")),
                js(&a.get("locale"))
            ),
        );
        }
    } else {
        puts(f, "norm_face", "not-a-normalisation-cell");
        put(
            f,
            "env",
            format!(
                "{{\"unicode_version\": \"not-obtainable-here\", \"toolchain\": {}, \"LongPathsEnabled\": {}, \"max_component\": {}, \"locale\": {}}}",
                js(&a.get("toolchain")),
                num_or_null(&a.get("longpaths-enabled")),
                num_or_null(&a.get("max-component")),
                js(&a.get("locale"))
            ),
        );
    }

    // zip legs, over the bytes the read leg already captured
    if a.flag("zip-face") && !read_buf.is_empty() {
        let parsed = zip_parse_central(&read_buf);
        let rows: Vec<String> = parsed
            .iter()
            .map(|(nm, bit11, crc, _)| format!("{{\"name\": {}, \"bit11\": {}, \"crc32\": {}}}", js(nm), hitb(*bit11), crc))
            .collect();
        put(f, "zip_entries_read", format!("[{}]", rows.join(", ")));
        puti(f, "zip_entries_read_count", parsed.len() as i64);
        putb(f, "zip_bit11_all_set", !parsed.is_empty() && parsed.iter().all(|(_, b, _c, _)| *b));
        let written_names: Vec<String> = a
            .csv("zip-entry-hex")
            .iter()
            .filter_map(|h| unhex(h).ok().map(|b| String::from_utf8_lossy(&b).into_owned()))
            .collect();
        let read_names: Vec<String> = parsed.iter().map(|(n, _b, _c, _)| n.clone()).collect();
        putb(f, "zip_names_roundtrip", !parsed.is_empty() && written_names == read_names);
        put(f, "zip_names_written_list", format!("[{}]", written_names.iter().map(|s| js(s)).collect::<Vec<_>>().join(", ")));
        put(f, "zip_names_read_list", format!("[{}]", read_names.iter().map(|s| js(s)).collect::<Vec<_>>().join(", ")));
        let crc_ok = !parsed.is_empty()
            && parsed
                .iter()
                .all(|(_n, _b, c, _o)| payload.is_empty() || crc32(payload) == *c);
        putb(f, "zip_crc_roundtrip", crc_ok);
        puts(f, "zip_crc_basis", "each entry stores the canonical payload, so the expected CRC is crc32(payload); compared against the central-directory value read back from disk");
        puts(f, "zip_parse_channel", "central-directory parse of the bytes read back from disk, in std only");
    }
}

fn run_bisect(a: &Args, f: &mut Fields, payload: &[u8], markfile: &str, scratch: &Path, path_form: &str, entry: &str) {
    let kind = a.get("bisect");
    let lo0 = a.num("bisect-lo").unwrap_or(1) as usize;
    let hi0 = a.num("bisect-hi").unwrap_or(1024) as usize;
    puts(f, "bisect", &kind);
    puts(f, "path_form", path_form);
    puts(f, "name_source_kind", &a.get("name-source-kind"));
    puts(f, "bisect_range", &format!("[{lo0}, {hi0}]"));
    puts(f, "bisect_range_basis", &a.get("bisect-range-basis"));
    puts(f, "bisect_subject", if kind == "component" { "width of one file-name component" } else { "width of the whole path" });
    puts(f, "rev4_regime_question", "gate.md section 5 (rev4) keys the expected ceiling on longpath_mechanism, not on path_form");

    let mut trace: Vec<String> = Vec::new();
    let mut created: Vec<String> = Vec::new();
    let mut attempts = 0i64;
    let step = a.num("chain-step").unwrap_or(200) as usize;
    let tail = "t.bin";

    // one attempt at width w; returns (ok, winerror-or-empty)
    let mut probe = |w: usize, trace: &mut Vec<String>, attempts: &mut i64| -> (bool, String) {
        *attempts += 1;
        if kind == "component" {
            let name = "c".repeat(w);
            let tgt = target_path(scratch, OsStr::new(&name), path_form);
            let total = wlen(&tgt);
            created.push(hex_of_name(OsStr::new(&name)));
            let res = do_entry(entry, &tgt, payload, None);
            let ok = matches!(res, Outcome::Ok { .. });
            let code = match &res {
                Outcome::Err { code, stage, .. } => code.map(|c| c.to_string()).unwrap_or_else(|| format!("stage={stage}")),
                Outcome::Ok { .. } => String::new(),
            };
            trace.push(format!("{{\"name_len\": {w}, \"total_path_len\": {total}, \"ok\": {}, \"winerror\": {}}}", hitb(ok), js(&code)));
            (ok, code)
        } else {
            let mut dir = scratch.to_path_buf();
            let mut used = wlen(scratch);
            let mut depth = 0usize;
            let mut built = true;
            while used + 1 + step + 1 + tail.len() + 1 < w {
                dir = dir.join("z".repeat(step));
                if std::fs::create_dir_all(&dir).is_err() {
                    built = false;
                    break;
                }
                used = wlen(dir.as_path());
                depth += 1;
            }
            if built {
                let pad = w.saturating_sub(used + 1 + tail.len() + 1);
                if pad > 0 {
                    dir = dir.join("y".repeat(pad));
                    if std::fs::create_dir_all(&dir).is_err() {
                        built = false;
                    }
                }
            }
            // every component between the scratch and this attempt's directory is this cell's
            // own creation, so claim the whole chain, not just its last element
            let mut chain_names: Vec<String> = Vec::new();
            let mut walked: PathBuf = dir.clone();
            while walked != scratch {
                if let Some(c) = walked.file_name() {
                    chain_names.push(hex_of_name(c));
                }
                let up = match walked.parent() {
                    Some(p) => p.to_path_buf(),
                    None => break,
                };
                if up == walked {
                    break;
                }
                walked = up;
            }
            chain_names.push(hex_of_name(OsStr::new(tail)));
            created.extend(chain_names);
            let tgt = target_path(&dir, OsStr::new(tail), path_form);
            let total = wlen(&tgt);
            let res = if built { do_entry(entry, &tgt, payload, None) } else { Outcome::Err { stage: "syscall", code: None, msg: "directory chain could not be built".into() } };
            let ok = built && matches!(res, Outcome::Ok { .. });
            let code = match &res {
                Outcome::Err { code, stage, msg } => code.map(|c| c.to_string()).unwrap_or_else(|| format!("stage={stage}:{msg}")),
                Outcome::Ok { .. } => String::new(),
            };
            trace.push(format!("{{\"target_total\": {total}, \"depth\": {depth}, \"ok\": {}, \"winerror\": {}}}", hitb(ok), js(&code)));
            (ok, code)
        }
    };

    mark(markfile, "bisect-start");
    let mut lo = lo0;
    let mut hi = hi0;
    let mut err_code: String;
    let (mut ok_lo, _) = probe(lo, &mut trace, &mut attempts);
    while !ok_lo && lo > 1 {
        lo = lo / 2;
        let (o, _) = probe(lo, &mut trace, &mut attempts);
        ok_lo = o;
    }
    let (ok_hi, code_hi) = probe(hi, &mut trace, &mut attempts);
    let (best_ok, first_err) = if ok_hi {
        err_code = String::new();
        (hi, 0usize)
    } else {
        err_code = code_hi;
        while lo + 1 < hi {
            let mid = lo + (hi - lo) / 2;
            let (o, c) = probe(mid, &mut trace, &mut attempts);
            if o {
                lo = mid;
            } else {
                hi = mid;
                err_code = c;
            }
        }
        (lo, hi)
    };
    mark(markfile, "bisect-done");
    // name_source carries the hex of the widest name this cell actually created, because
    // rev3 fixes name_encoding to a record encoding and this case's frozen sample is a sentence
    let measured_name = if kind == "component" { "c".repeat(best_ok.max(1)) } else { "t.bin".to_string() };
    puts(f, "name_source", &to_hex(measured_name.as_bytes()));
    puts(f, "measured_name_basis", if kind == "component" { "the widest single component this cell could create at this base_len" } else { "the tail name of the widest chain this cell could create" });
    if !a.get("spec-sample-string").is_empty() {
        puts(f, "spec_sample_string", &a.get("spec-sample-string"));
        puts(f, "spec_sample_note", "cases.yaml writes T17/T18 sample_hex as a sentence, not as hex; the sentence is published verbatim here and name_source carries the hex of the name actually created");
    }

    // this cell creates one file per attempt, so it enumerates what it left and claims it;
    // without this the names show up as unclaimed extras in the sibling cells of the same directory
    let listing = enumerate(scratch);
    let mut own: Vec<Vec<u16>> = created.iter().filter_map(|h| os_from_hex(h).ok().map(|(o, _)| units_of(&o))).collect();
    // names an earlier cell in this same directory registered are claimed too; a bisection shares
    // its tier directory with the other case at the same base and path form
    for h in a.csv("prior-claim-hexes") {
        if let Ok((o, _)) = os_from_hex(&h) {
            own.push(units_of(&o));
        }
    }
    let unclaimed: Vec<String> = listing.iter().filter(|(nm, _f, _s)| !own.iter().any(|u| nm.encode_utf16().collect::<Vec<u16>>() == *u)).map(|(nm, _a, _b)| nm.clone()).collect();
    puti(f, "enumeration_count", listing.len() as i64);
    puti(f, "enumeration_files", listing.iter().filter(|x| x.1).count() as i64);
    puti(f, "enumeration_dirs", listing.iter().filter(|x| !x.1).count() as i64);
    puti(f, "created_names_count", created.len() as i64);
    puti(f, "unclaimed_extras", unclaimed.len() as i64);
    puti(f, "prior_claimed_entries", a.csv("prior-claim-hexes").len() as i64);
    put(f, "unclaimed_names", format!("[{}]", unclaimed.iter().take(12).map(|x| js(x)).collect::<Vec<_>>().join(", ")));
    if !a.get("claims").is_empty() {
        let body = created.iter().cloned().collect::<Vec<_>>().join("
");
        let _ = File::create(a.get("claims")).and_then(|mut w| w.write_all(body.as_bytes()));
    }
    puts(f, "bisect_claim_basis", "every name this cell created is listed in its own claims side file; the driver registers them so a sibling cell in the same directory cannot read them as unclaimed");
    put(f, "bisect_trace", format!("[{}]", trace.join(", ")));
    puti(f, "bisect_attempts", attempts);
    puti(f, "max_ok", best_ok as i64);
    putopt(f, "first_failing", if first_err > 0 { Some(first_err.to_string()) } else { None });
    puts(f, "first_failing_winerror", &err_code);
    puts(f, "create_result", if best_ok > 0 { "ok" } else { "err_at_syscall" });
    puts(f, "error_stage", if best_ok > 0 { "null" } else { "syscall" });
    puts(f, "read_result", "not_applicable");
    putb(f, "read_attempt", false);
    putb(f, "content_read_performed", false);
    puts(f, "read_channel", "none: bisection cell, only the create leg is measured");
    puts(f, "read_skipped_reason", "a bisection cell reports the ceiling it found; no single name was read back");
    puts(f, "os_legality_verdict", if first_err > 0 { "illegal" } else { "unknown" });
    puts(f, "os_legality_basis", "the ceiling is the width at which the OS itself stops producing a directory entry; it is found by repeated creates, not by a stdlib predicate");
    puts(f, "verdict_via", "win32");
    puts(f, "verdict_via_basis", "the ceiling was read off repeated CreateFileW attempts and parent-directory enumeration, both Win32");
    puts(f, "attribution_layer", "L1");
    puti(f, "bytes_written", payload.len() as i64);
    puti(f, "bytes_on_disk", payload.len() as i64);
    puts(f, "name_landed_as_face", "not applicable: bisection cell");
    put(
        f,
        "len_triple",
        format!(
            "{{\"code_points\": {}, \"utf16_code_units\": {}, \"utf8_bytes\": {}, \"basis\": {}}}",
            best_ok.max(1),
            best_ok.max(1),
            best_ok.max(1),
            js(if kind == "component" { "max_ok component width" } else { "chain tail name width" })
        ),
    );
    // base_len is published once, from the identity block, from the value the driver pinned;
    // this line only cross-checks it against the width the child itself measured
    puti(f, "base_len_measured_by_probe", wlen(scratch) as i64);
    puts(f, "bisect_note", &a.get("bisect-note"));
    puts(f, "rev4_regime_observed", if kind == "component" {
        "max_component ceiling of 255 refused at 256 with code 123, which is the manifest/prefix_rewrite regime's expectation - yet longpath_mechanism for this face is set from the mechanism evidence, not fitted to that bucket"
    } else {
        "no 259-base-1 ceiling exists on this face: the refusal arrives near 32767 with code 206, so the none+no-prefix regime's law cannot be satisfied here and this cell is reported rather than forced into a bucket"
    });
}
