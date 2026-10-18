# SENDGUARD — sealed independent expectation table (S01 pre-run)

```
measured_at:      2026-10-11 01:40:12 +0800   (host `date '+%Y-%m-%d %H:%M:%S %z'`, this run)
sha256_cases_yaml: 08484788745DA580FBE99D63D4BB8D1C719786EBA3BE45076A2765A94B61E251
                   (host `powershell Get-FileHash -Algorithm SHA256 spec/cases.yaml`, rc=0, this run)
read_scope:       spec/cases.yaml, spec/canonical.md, spec/gate.md ONLY.
                  No file under impl/, results/, harness/, ci/, docs/, evidence/ was opened.
                  No port was run. No probe file/dir was created, renamed, or deleted.
author_statement: Written without reading any implementation or result file, so that six ports
                  agreeing on something the spec never said is detectable against this table.
```

## Conventions

- Predictions are at **(case x OS)** granularity, never per language port.
- Status words are taken only from `spec/canonical.md` closed sets:
  `create_result` in {ok, err_at_parse, err_at_syscall, hang};
  `read_result` in {ok, eof, err6, hang};
  `os_legality_verdict` in {legal, illegal, unknown};
  `path_form` in {plain, extended}.
- `bytes_on_disk: null` = no directory entry / no file bytes expected.
  `bytes_on_disk: == bytes_written` = file content intact on disk (type II clean).
- `read_result: null` = the read leg has no addressable artifact (creation failed, nothing landed);
  this is a notation of "no expectation", not a status word for a measured cell.
- `name_landed_as` = UTF-8 hex of the name expected in a directory enumeration. `null` = no entry.
- OSes outside a case's frozen `applicable` list are marked `out_of_applicability (cases.yaml)` —
  scope fact from the frozen table, not a verdict word.
- `machine-dependent: yes(...)` names the concrete dependency; see the register at the end.
- Confidence: `high` = named public spec directly covers it; `medium` = documented behaviour,
  stable across versions; `low` = not attributable to a spec at this seal, deliberately flagged.

Sources cited below, shorthand:
- [MS] MS Learn "Naming Files, Paths, and Namespaces" (learn.microsoft.com/windows/win32/fileio/naming-a-file)
- [UT-N] Unicode NormalizationTest.txt / UCD case & composition data
- [UT-B] Unicode BidiTest.txt / UAX #9
- [ZIP] PKWARE APPNOTE.TXT (general purpose flag bit 11, UTF-8 filename)
- [LR] linux man page `path_resolution(7)` + ext4 (`/usr/share/doc` "What filename lengths are allowed?",
  ext4 dir entry name <= 255 bytes, any byte except `/` and NUL)
- [AP] Apple File System reference / HFS Technical Note TN1150 (normalization-forcing NFD volume)
- [DB] "documented behaviour" (widely published OS/tool behaviour, no single normative clause)

---

## 1. Traps T01–T20

### T01 — `434f4e2e747874` (CON.txt) — reserved_device_name

- windows | path_form: plain | create_result: ok (attached console) / err_at_syscall (detached) | read_result: hang | bytes_on_disk: null | name_landed_as: null | os_legality_verdict: illegal | machine-dependent: yes — whether a console object is behind `CON` in the harness launch context (attached -> CreateFile opens the console device and the write "succeeds" to the screen; detached/service -> error). Read of a console handle blocks on input -> `hang` at the 5s timeout. No file ever lands on a plain path because `CON` is reserved even with an extension [MS]. With `path_form: extended` (`\\?\CON.txt`) name parsing is bypassed and a literal file lands with hex `434f4e2e747874`, bytes == bytes_written, legal-as-raw-bytes [MS, DB]; this is a documented escape hatch, not the default cell. | source: [MS] reserved names + extension ignored; [DB] `\\?\` bypass. confidence: low (console presence is machine state)
- macos | path_form: plain | create_result: ok | read_result: ok | bytes_on_disk: == bytes_written | name_landed_as: 434f4e2e747874 | os_legality_verdict: legal | reason: `CON` has no device namespace in POSIX; plain filename. | source: [LR] filename may contain any byte except `/` and NUL. confidence: high
- ubuntu | same as macos row. | source: [LR]. confidence: high

### T02 — `4e554c2e7461722e677a` (NUL.tar.gz) — reserved_device_name

- windows | path_form: plain | create_result: ok | read_result: eof | bytes_on_disk: null | name_landed_as: null | os_legality_verdict: illegal | reason: `NUL` is the null device, reserved even with an extension [MS]; writes are accepted and discarded (so creation "succeeds" with zero disk bytes), reads of NUL return EOF immediately (documented behaviour of the null device). No directory entry exists. | source: [MS] + [DB] NUL device semantics. confidence: high
- macos | path_form: plain | create_result: ok | read_result: ok | bytes_on_disk: == bytes_written | name_landed_as: 4e554c2e7461722e677a | os_legality_verdict: legal | source: [LR]. confidence: high
- ubuntu | same as macos. | source: [LR]. confidence: high

### T03 — `613c622e747874` (a<b.txt) — illegal_char_filter

- windows | path_form: plain | create_result: err_at_syscall | read_result: null | bytes_on_disk: null | name_landed_as: null | os_legality_verdict: illegal | reason: `<` is in the invalid-character set [MS]; CreateFile fails ERROR_INVALID_NAME before touching the volume. | source: [MS]. confidence: high
- macos | path_form: plain | create_result: ok | read_result: ok | bytes_on_disk: == bytes_written | name_landed_as: 613c622e747874 | os_legality_verdict: legal | reason: `<` is only a shell metacharacter, not a POSIX filename restriction; Finder-visual quirks aside the byte name lands intact. | source: [LR] (restriction list is `/` and NUL only). confidence: high
- ubuntu | same as macos. | source: [LR]. confidence: high

### T04 — `747261696c2e` (trail.) — path_preprocessing_policy

- windows | path_form: plain | create_result: ok | read_result: ok | bytes_on_disk: == bytes_written | name_landed_as: 7472616c (i.e. `trail`) | os_legality_verdict: illegal (the requested form `trail.` is not permitted as a stored name [MS]: trailing dots are stripped by the path parser) | reason: name-parse stripping => IV' hit (requested len != enumerated len). Extended form (`\\?\`) suppresses stripping and lands `747261696c2e` literally [MS, DB]. | source: [MS] trailing-period rule. confidence: high (for plain form)
- macos | path_form: plain | create_result: ok | read_result: ok | bytes_on_disk: == bytes_written | name_landed_as: 747261696c2e | os_legality_verdict: legal | reason: POSIX stores trailing dots; Finder displays are irrelevant to dir enumeration. | source: [LR]. confidence: high
- ubuntu | same as macos. | source: [LR]. confidence: high

### T05 — `747261696c737020` (`trailsp `, trailing space) — path_preprocessing_policy

- windows | path_form: plain | create_result: ok | read_result: ok | bytes_on_disk: == bytes_written | name_landed_as: 7472616c7370 (`trailsp`) | os_legality_verdict: illegal (trailing spaces stripped, same clause as T04 [MS]) | reason: stripping => IV' hit; extended form lands the space literally [MS, DB]. | source: [MS]. confidence: high
- macos | path_form: plain | create_result: ok | read_result: ok | bytes_on_disk: == bytes_written | name_landed_as: 747261696c737020 | os_legality_verdict: legal | source: [LR]. confidence: high
- ubuntu | same as macos. | source: [LR]. confidence: high

### T06 — `656d6f6a692df09f98802e747874` (emoji-U+1F600.txt) — unicode_normalization

- windows | path_form: plain | create_result: ok | read_result: ok | bytes_on_disk: == bytes_written | name_landed_as: 656d6f6a692df09f98802e747874 | os_legality_verdict: legal | reason: NTFS names are UTF-16; the astral code point is a valid surrogate pair, no filtering. | source: [MS] (valid chars only), [DB] NTFS UTF-16 name storage. confidence: high
- macos | path_form: plain | create_result: ok | read_result: ok | bytes_on_disk: == bytes_written | name_landed_as: same hex | os_legality_verdict: legal | reason: emoji has no decomposition in the normalization tables, so NFD-forcing volumes (if any) do not alter the name; APFS preserves bytes. | source: [UT-N] (U+1F600 not in composition/decomposition exclusions of interest), [AP]. confidence: medium
- ubuntu | path_form: plain | create_result: ok | read_result: ok | bytes_on_disk: == bytes_written | name_landed_as: same hex | os_legality_verdict: legal | source: [LR] (byte-opaque). confidence: high

### T07 — `63616665cc812e747874` (NFD cafe+U+0301.txt) — unicode_normalization; applicable [macos, ubuntu]

- windows | out_of_applicability (cases.yaml frozen `applicable`). No prediction.
- macos | path_form: plain | create_result: ok | read_result: ok | bytes_on_disk: == bytes_written | name_landed_as: 63616665cc812e747874 | os_legality_verdict: legal | reason: input is already NFD; a normalization-forcing (HFS+) volume and a preserving (APFS) volume both land these bytes. | source: [AP], [UT-N]. confidence: high
- ubuntu | path_form: plain | create_result: ok | read_result: ok | bytes_on_disk: == bytes_written | name_landed_as: 63616665cc812e747874 | os_legality_verdict: legal | source: [LR]. confidence: high

### T08 — `636166c3a92e747874` (NFC cafe-with-acute.txt) — unicode_normalization; applicable [macos, ubuntu]

- windows | out_of_applicability (cases.yaml).
- macos | path_form: plain | create_result: ok | read_result: ok | bytes_on_disk: == bytes_written | name_landed_as: **volume-dependent** — APFS (default since macOS 11): 636166c3a92e747874 (bytes preserved); legacy HFS+ normalization-forcing: 63616665cc812e747874 (stored NFD per Apple TN1150) | os_legality_verdict: legal | machine-dependent: yes — filesystem format of the scratch volume (APFS vs HFS+). | source: [AP], [UT-N] NFC/NFD pair e+U+0301. confidence: low (primary seal prediction: preserved bytes on APFS)
- ubuntu | path_form: plain | create_result: ok | read_result: ok | bytes_on_disk: == bytes_written | name_landed_as: 636166c3a92e747874 | os_legality_verdict: legal | reason: ext4 is byte-opaque; no normalization anywhere below the API. | source: [LR]. confidence: high

### T09 — coexistence pair — unicode_normalization headline cell; applicable [macos, ubuntu]

Members: `726573756d652d65cc812e747874` (NFD) / `726573756d652dc3a92e747874` (NFC)

- windows | out_of_applicability (cases.yaml).
- macos | path_form: plain | create_result: ok for member 1; member 2 depends on volume | read_result: ok | bytes_on_disk: see landed-entry count | name_landed_as: APFS normalization-sensitive reading -> two entries, both hex as given; HFS+ (or a normalization-insensitive lookup) -> ONE entry, hex 726573756d652d65cc812e747874 (second create overwrites the first, so requested==stored for member 1 only; type IV' hit on member 2 pair) | os_legality_verdict: legal | machine-dependent: yes — volume format AND volume variant (normalization/case sensitivity options). | source: [AP], [UT-N]. confidence: low (primary seal prediction: two distinct entries on default APFS; flagged because public Apple docs do not state APFS normalization-sensitivity in a normative clause)
- ubuntu | path_form: plain | create_result: ok (both members) | read_result: ok (both) | bytes_on_disk: == bytes_written (two files) | name_landed_as: both hex as given, two separate directory entries | os_legality_verdict: legal | reason: byte-distinct names; kernel does no normalization. | source: [LR]. confidence: high

### T10 — `434f4e` (CON, bare) — reserved_device_name

- windows | path_form: plain | create_result: ok (attached console) / err_at_syscall (detached) | read_result: hang | bytes_on_disk: null | name_landed_as: null | os_legality_verdict: illegal | reason: same device-namespace rule as T01; bare `CON` reads block on console input. machine-dependent: yes — console attachment. Extended form lands literal `434f4e` [MS, DB]. | source: [MS]. confidence: low
- macos | create_result: ok | read_result: ok | bytes_on_disk: == bytes_written | name_landed_as: 434f4e | os_legality_verdict: legal | source: [LR]. confidence: high
- ubuntu | same as macos. | source: [LR]. confidence: high

### T11 — `434f4d312e6c6f67` (COM1.log) — reserved_device_name

- windows | path_form: plain | create_result: **err_at_syscall (primary)** if no COM1 port exists on the machine (CreateFile on `COM1` with no device -> ERROR_FILE_NOT_FOUND; reserved-name parsing blocks file creation either way); ok + bytes_on_disk null + read hang/err6 if a COM1 port IS present (writes go to the serial device, no directory entry) | read_result: null (err case) / hang (device case) | bytes_on_disk: null | name_landed_as: null | os_legality_verdict: illegal (name reserved as COM1 with extension ignored [MS]) | machine-dependent: yes — physical/virtual COM1 presence. This is exactly the dependency the audit check "T11 actually run on pinned entry" anticipates. | source: [MS] reserved device table; [DB] serial-port open semantics. confidence: low (both outcomes are spec-legal depending on machine state; seal prediction = err_at_syscall on a modern headless machine)
- macos | create_result: ok | read_result: ok | bytes_on_disk: == bytes_written | name_landed_as: 434f4d312e6c6f67 | os_legality_verdict: legal | source: [LR]. confidence: high
- ubuntu | same as macos. | source: [LR]. confidence: high

### T12 — `626964692de280ae2e747874` (bidi-U+202E.txt) — bidi_handling

- windows | path_form: plain | create_result: ok | read_result: ok | bytes_on_disk: == bytes_written | name_landed_as: 626964692de280ae2e747874 | os_legality_verdict: legal | reason: U+202E is an assigned formatting character, not in the invalid set; NTFS stores it verbatim. Rendered *display* in Explorer may visually reverse the tail (BidiTest/UAX#9 directional rule), but the enumerated *bytes* are unchanged — display is not the storage layer. | source: [UT-B], [MS] (not an invalid char). confidence: high
- macos | same fields, same hex. | source: [UT-B], [LR] analogue on darwin POSIX layer. confidence: high
- ubuntu | same fields, same hex. | source: [LR], [UT-B]. confidence: high

### T13 — `7a65726f7769647468e2808b2e747874` (zero-width U+200B.txt) — zero_width_handling

- windows | path_form: plain | create_result: ok | read_result: ok | bytes_on_disk: == bytes_written | name_landed_as: 7a65726f7769647468e2808b2e747874 | os_legality_verdict: legal | reason: Cf category character, not invalid for NTFS; invisible in display only. | source: [UT-N] (category Cf), [MS] invalid-char list does not include it. confidence: high
- macos | same as windows row (ok / ok / == bytes_written / same hex / legal). | source: [UT-N], darwin POSIX layer [LR-analogue]. confidence: medium (some macOS UI layers strip Cf on typing, but a direct API create lands bytes)
- ubuntu | same. | source: [LR]. confidence: high

### T14 — member list PRN / AUX.log / LPT9 — reserved_device_name

Member hex: `50524e` (PRN), `4155582e6c6f67` (AUX.log), `4c505439` (LPT9)

- windows | path_form: plain | per member:
  - PRN: create_result: err_at_syscall (no printer redirection) / ok with bytes_on_disk null (printer namespace present, writes spool away); read_result: null / hang; name_landed_as: null; os_legality_verdict: illegal. machine-dependent: yes — printer present/absent. confidence: low
  - AUX.log: create_result: err_at_syscall (primary; AUX aliases COM2 and COM2 typically absent) / ok+null if present; same null/hang pattern; os_legality_verdict: illegal. machine-dependent: yes. confidence: low
  - LPT9: create_result: err_at_syscall (primary; LPT1-LPT9 are all reserved as names [MS]; device LPT9 absent on modern machines -> ERROR_FILE_NOT_FOUND); bytes_on_disk null; name_landed_as null; os_legality_verdict: illegal. confidence: medium (name reservation itself is firm [MS]; the ok-vs-err split only arises with a phantom parallel port)
  All three: no directory entry on a plain path; `\\?\` extended form creates literal files with the given hex [MS, DB].
- macos | all three members: create_result: ok | read_result: ok | bytes_on_disk: == bytes_written | name_landed_as: given hex unchanged | os_legality_verdict: legal | source: [LR]. confidence: high
- ubuntu | same as macos. | source: [LR]. confidence: high

### T15 — `6374726c2d012e747874` (ctrl-U+0001.txt) — control_char_handling

- windows | path_form: plain | create_result: err_at_syscall | read_result: null | bytes_on_disk: null | name_landed_as: null | os_legality_verdict: illegal | reason: characters 0x00-0x1F are not permitted in Win32 file names [MS]; ERROR_INVALID_NAME at parse inside ntdll path validation (before volume). | source: [MS]. confidence: high
- macos | path_form: plain | create_result: ok | read_result: ok | bytes_on_disk: == bytes_written | name_landed_as: 6374726c2d012e747874 | os_legality_verdict: legal | reason: darwin POSIX layer admits any byte except `/` and NUL; Finder rejects only `:` visually. | source: [LR]-analogue, [DB]. confidence: low (Apple publishes no normative statement on control chars at the API; prediction is from documented behaviour only)
- ubuntu | same fields as macos row. | reason: ext4 dir entry names: any byte except `/` and `\0`. | source: [LR] + ext4 doc ("filename may contain any byte except / and NUL"). confidence: high

### T16 — `7a69702d726f756e64747269702e7a6970` (zip-roundtrip.zip) — zip_roundtrip

- windows | path_form: plain | OS-layer cell for the container file: create_result: ok | read_result: ok | bytes_on_disk: == bytes_written | name_landed_as: 7a69702d726f756e64747269702e7a6970 | os_legality_verdict: legal | reason: the sample name itself is pure ASCII; creating/reading the zip container is unremarkable on every OS. The trap lives in the *roundtrip* of non-ASCII entry names through tooling: bit 11 (UTF-8 name flag) [ZIP] is honored by Info-ZIP and modern Explorer (Win10+), but older Explorer/`pkunzip` decode entry names in the OEM codepage -> mojibake landed name on extract (name hex no longer equal to the archived bytes). machine/tool-dependent: yes — which unzip tool and version; not an OS-spec fact. | source: [ZIP] APPNOTE bit 11; [DB] tool behaviour. confidence: low (for the roundtrip-name sub-prediction; the container-file row above is confidence: high)
- macos | container row identical to windows (ok/ok/==/same hex/legal, high). Roundtrip sub-prediction: `ditto`/Archive Utility assume UTF-8 -> entry names land with archived hex; third-party tools may differ. confidence: low (tool-level)
- ubuntu | container row identical. Roundtrip sub-prediction: Info-ZIP `unzip` interprets names in the locale codepage unless bit 11 is set and honored, in which case UTF-8 lands verbatim; with bit 11 set on a UTF-8 locale: names land as archived hex. | source: [ZIP], [DB]. confidence: low (tool-level)

### T17 — path-length bisection (G1–G4) — component_length_limit (whole-path leg)

Form: "T-LEN-PATH" curve, not a point. Predictions are graded: G1 (deep inside limit), G2/G3 (around breakpoint), G4 (far beyond).

- windows | path_form: plain | create_result: ok for total path length <= 259 characters (MAX_PATH 260 incl. terminator, [MS]); err_at_syscall (ERROR_PATH_NOT_FOUND / ENAMETOOLONG-analogue) beyond — **unless** long paths are enabled (Windows 10 1607+ registry `LongPathsEnabled` + application manifest), in which case plain paths up to 32,767 can succeed. path_form: extended (`\\?\`) | ok up to 32,767 chars regardless of registry, because the prefix disables MAX_PATH [MS]. bytes_on_disk: == bytes_written at ok grades, null at err grades. name_landed_as: given hex at ok grades, null at err grades. os_legality_verdict: legal below breakpoint, illegal above. machine-dependent: yes — LongPathsEnabled state and whether the port builds a manifest-enabled binary; two different machines legitimately give different breakpoints. | source: [MS] maximum path length section. confidence: low (which breakpoint the harness machine exhibits is unknowable at seal)
- macos | path_form: plain | breakpoints: PATH_MAX 1024 for the whole path (sysctl kern.pathmax / [DB] Apple limits doc). G1/G2-ish grades <= 1023 bytes ok; beyond -> err_at_syscall (ENAMETOOLONG). Same field pattern as windows row with 1024. | source: darwin `<syslimits.h>`/path_resolution analogue [LR-doc]. confidence: medium
- ubuntu | path_form: plain | breakpoint: PATH_MAX 4096 ([LR] path_resolution(7)). ok <= 4095 bytes, err_at_syscall ENAMETOOLONG beyond. | source: [LR]. confidence: high

### T18 — component-length bisection (G1–G4) — component_length_limit (single-name leg)

- windows | path_form: plain (and extended behaves identically here — component limit is a volume limit, not a parse limit) | breakpoint: 255 UTF-16 characters per component on NTFS [MS, DB]. ok <= 255; err_at_syscall beyond. os_legality_verdict: legal <=255, illegal beyond. | confidence: medium (the "255 chars" figure is documented behaviour, not a normative MS Learn clause)
- macos | breakpoint: APFS/HFS+ 255 UTF-16 characters per component (name max length doc [AP]). ok <= 255 chars; err beyond. Note: counting unit is *characters*, not bytes -> multibyte payloads hit the wall earlier in bytes than Linux. | confidence: medium
- ubuntu | breakpoint: ext4 NAME_MAX = 255 **bytes** ([LR] path_resolution(7): NAME_MAX 255 on ext4; tmpfs differs!). ok <= 255 bytes; err_at_syscall ENAMETOOLONG beyond. machine-dependent: yes — tmpfs NAME_MAX is also 255 bytes but the byte-vs-char divergence between ext4 (bytes) and APFS/NTFS (UTF-16 chars) is a real cross-OS curve-shape difference to expect. | source: [LR]. confidence: high

### T19 — case_folding pair — fullwidth `efbca1efbca2efbca32e747874` / Hangul jamo `e384b1e384b4e384b72e747874`; locale ja-JP

Member 1 (fullwidth ABC .txt):

- windows | path_form: plain | create_result: ok | read_result: ok | bytes_on_disk: == bytes_written | name_landed_as: efbca1efbca2efbca32e747874 | os_legality_verdict: legal | reason: NTFS case-insensitivity uses an upcase table over Unicode simple case mappings; fullwidth latin capitals fold to fullwidth small letters (U+FF21->U+FF41, [UT-N]) but NOT to ASCII, so no collision with `abc.txt` is expected; stored form keeps original case. | source: [UT-N], [DB] NTFS case-insensitive lookup. confidence: low (whether the harness machine's upcase-table behaviour matches expectations for Cf/compat-width chars is not directly spec'd)
- macos | same field values, landed hex unchanged; APFS default volume is case-insensitive, case-preserving -> creation of member 1 collides only with a same-width variant, not with the ASCII row. | source: [AP]. confidence: medium
- ubuntu | ext4: fully case- and width-sensitive -> distinct entries, hex as given. | source: [LR]. confidence: high

Member 2 (Hangul jamo .txt):

- windows | ok / ok / == bytes_written / e384b1e384b4e384b72e747874 / legal | reason: jamo U+3131-U+318F have no case mapping and NFC does not compose half-width jamo into syllables (composition uses U+1100-block conjoining jamo, [UT-N]); stored verbatim. | confidence: medium
- macos | ok / ok / == bytes_written / same hex / legal | reason: NFD-forcing volumes leave U+3131 unchanged (it is a compatibility decomposition, not canonical — [UT-N]); APFS preserves. | confidence: medium
- ubuntu | ok / ok / == bytes_written / same hex / legal. | source: [LR]. confidence: high

### T20 — `2d2d666f7263652e747874` (--force.txt) — unknown (CLI-lookalike)

- windows | path_form: plain | create_result: ok | read_result: ok | bytes_on_disk: == bytes_written | name_landed_as: 2d2d666f7263652e747874 | os_legality_verdict: legal | reason: leading `-` is not special to the OS path layer on any of the three; the trap only bites command-line tools that re-consume the name without `--` separation (tool layer, error_stage `tool`, not modeled in create/read verdicts). | source: [MS] (invalid-char set does not include `-`); [DB] POSIX. confidence: high
- macos | same as windows row. | confidence: high
- ubuntu | same as windows row. | confidence: high

---

## 2. Control cells (T-CTRL-*)

Note: the frozen table names these five but carries no sample hex for them (their expectations are defined
by `evidence/ctrl-baseline.md`, which is outside this seal's read scope). Predictions below are
category-level from each control's name plus `spec/canonical.md` §8 role ("verify the ruler"); rows whose
content I could not see are marked accordingly.

### T-CTRL-NAMETOOLONG

- windows | create_result: err_at_syscall | read_result: null | bytes_on_disk: null | name_landed_as: null | os_legality_verdict: illegal | path_form: plain | reason: by construction exceeds MAX_PATH / NAME limits [MS]. If the cell's length sits between 260 and 32,767 the verdict flips on long-path enablement (machine-dependent, same as T17). confidence: medium
- macos | err_at_syscall (ENAMETOOLONG) | null | null | null | illegal | plain | beyond PATH_MAX/NAME_MAX. confidence: high
- ubuntu | err_at_syscall (ENAMETOOLONG) | null | null | null | illegal | plain | [LR] path_resolution. confidence: high

### T-CTRL-ASCII

- all three OS | path_form: plain | create_result: ok | read_result: ok | bytes_on_disk: == bytes_written | name_landed_as: == requested name (plain ASCII, no transform exists that could alter it) | os_legality_verdict: legal | reason: this is the zero-divergence ruler; any other outcome on any OS means the instrument, not the subject, is broken (canonical §8 -> INSTRUMENT-RED). | source: [MS], [LR], [AP] all permit plain ASCII. confidence: high

### T-CTRL-ILLEGAL-CHAR

- windows | create_result: err_at_syscall | read_result: null | bytes_on_disk: null | name_landed_as: null | os_legality_verdict: illegal | path_form: plain | reason: contains a char from the [MS] invalid set (`< > : " | ? *`). confidence: high
- macos | **content-dependent**: if the char is one of the MS set except `\` (e.g. `<`), POSIX stores it fine -> ok/ok/==/unchanged/legal; if the char is `/`, illegal on darwin too (and Finder additionally maps `:`); if it is `\`, POSIX-legal but Finder-hostile. Sample hex not in my read scope. | source: [LR]-analogue. confidence: low (seal prediction: ok + name preserved, assuming the control uses an MS-set char that is POSIX-legal — which is the only design that makes the control *asymmetric* and hence useful here)
- ubuntu | same split as macos: `:` and `< > " | ? *` are all legal bytes on ext4; `/` and NUL are not. | source: [LR]. confidence: low (same reason)

### T-CTRL-PARSE

- all three OS | predicted create_result: **err_at_parse** | read_result: null | bytes_on_disk: null | name_landed_as: null | os_legality_verdict: unknown (the OS is never asked — that is the point of the cell) | path_form: plain | reason: control designed to prove the parse layer is observable: e.g. an embedded NUL in the name string is rejected by stdlibs before any syscall (Rust `CString::new` -> `NulError`; Python `open()` with `\x00` -> `ValueError`; Go `C.CString` truncates -> error at boundary). This is the only mechanism I can source for a pre-syscall rejection. | source: [DB] stdlib string-boundary behaviour. confidence: low (the control's actual payload was not visible at seal; if the payload is NOT NUL-bearing, this whole row is expected-wrong by design)

### T-CTRL-CANON

- all three OS | path_form: plain | create_result: ok | read_result: ok | bytes_on_disk: == bytes_written | name_landed_as: == requested | os_legality_verdict: legal | plus the pair-binding expectation from canonical §8: **two instruments hashing the same payload MUST report identical sha256**; any mismatch is INSTRUMENT-RED, not a data cell. reason: canonicalization ruler; a pure-ASCII/safe-name payload is the only construction that makes this a ruler. | source: spec/canonical.md §8, gate.md §8. confidence: high

---

## 3. Blind samples — declared NO COVERAGE at this seal

The blind set is referenced only as `seed_blind_samples: 7f3c1a9e...` and
`blind_map_ref: evidence/freeze/blind-map.json`. The five blind sample names are **not** present in
`spec/cases.yaml`, and `evidence/` is inside this seal's forbidden-read set (reading the map would also
violate the blind protocol). Therefore no per-case prediction can be written without guessing, and
guessing silently is exactly what this document exists to forbid. Recorded instead:

- blind_1 .. blind_5 | prediction: withheld — hex not available within sealed read scope.
- Process note for the local: a valid sealed expectation for the blind cells requires either (a) the
  five sample hex strings handed over through a channel that does not reveal trap identity
  (blind-by-construction: values only, no mapping), or (b) accepting that blind cells are checked
  post-hoc against the trap rows whose category they turn out to share.
- Consistency guard the local can still use: whatever the blind samples turn out to be, the
  per-OS predictions above already pin every mechanism_class in canonical §10 except `unknown`.

---

## 4. Machine-dependency register (answers depend on the box, not the spec)

1. T01, T10 (CON) — console attachment of the harness process. Attached => create ok/write-to-console/read-blocks(hang); detached => err_at_syscall.
2. T11 (COM1.log) — presence of a COM1 serial (or virtual serial) device. Absent => err_at_syscall; present => ok with no bytes on disk.
3. T14 (PRN / AUX / LPT9) — printer spooler namespace and legacy parallel/aux device presence. Same shape as T11.
4. T08, T09 — scratch volume format: APFS (normalization-preserving) vs HFS+ (normalization-forcing NFD, TN1150); also case-sensitivity variant of the APFS volume.
5. T17 — Windows long-path enablement: `LongPathsEnabled` registry + per-application manifest; breakpoint 260 vs 32,767.
6. T18 — cross-OS counting-unit difference at the wall: ext4 NAME_MAX in bytes vs NTFS/APFS 255 in UTF-16 code units; also tmpfs vs ext4 if the scratch dir is a tmpfs.
7. T16 — unzip tool identity/version (Explorer built-in vs Info-ZIP vs ditto vs third-party), not an OS fact at all.
8. T-CTRL-NAMETOOLONG — inherits dependency 5 on Windows if the cell length lands in 260..32767.

## 5. Totals

- Cases predicted: traps T01–T20 => 66 (case x OS) rows (incl. T09/T14/T19 per-member rows);
  controls T-CTRL-* => 15 (case x OS) rows; blind => 5 cells declared withheld.
  Total prediction rows written: 81.
- Rows flagged machine-dependent: T01-win, T10-win, T11-win, T14-win(3 members), T08-mac, T09-mac,
  T17-win, T-CTRL-NAMETOOLONG-win, T16 roundtrip sub-predictions (3 OS).
- Rows carrying the literal tag `confidence: low`: 16 (T01-win, T08-mac, T09-mac, T10-win, T11-win,
  T14 PRN-win, T14 AUX-win, T15-mac, T16 roundtrip x3 OS, T17-win, T19a-win,
  T-CTRL-ILLEGAL-CHAR mac+ubuntu, T-CTRL-PARSE all-OS single row).


---

## Correction (append-only, 2026-10-11 04:35) - does not alter any prediction

The header binds this table to `sha256_cases_yaml: 08484788745D...`, which is the digest of the
**checked-out file**, taken with `Get-FileHash`. The committed blob face of the same file is
`a7f9a57df1b4d39a19421a54d175e87793100ce3393e363622ca59816e19148b`. The sealer did nothing wrong in substance - it read the spec it was told to read and predicted from
it - but the binding line pointed at the wrong face, so a stranger could not verify which spec this table
was written against.

Predictions, confidence marks and the machine-dependency register below are unchanged. See
`spec/cell-identity.md` section 7: from now on every digest in this repository is a blob-face digest, and
`ci/blobhash.py` is the only way to compute one.
