package main

import (
	"fmt"
	"os"
	"os/exec"
	"strconv"
	"strings"
	"syscall"
	"time"
	"unsafe"
)

// Win32 error numbers this port names explicitly. Everything else is stored
// verbatim as a number (M16), never translated into a status word.
const (
	errFileNotFound     = 2
	errPathNotFound     = 3
	errInvalidHandle    = 6
	errAccessDenied     = 5
	errAlreadyExists    = 80
	errInvalidName      = 123
	errBadPathname      = 161
	errEnvarLimit       = 206 // ERROR_FILENAME_EXCED_RANGE
	errInvalidParameter = 87
	errDirNotFound      = 267 // ERROR_DIRECTORY: the directory part of the name is invalid
)

func errnoCode(err error) (uint32, bool) {
	if err == nil {
		return 0, false
	}
	if en, ok := err.(syscall.Errno); ok {
		return uint32(en), true
	}
	if pe, ok := err.(*os.PathError); ok {
		if en, ok2 := pe.Err.(syscall.Errno); ok2 {
			return uint32(en), true
		}
	}
	if le, ok := err.(*os.LinkError); ok {
		if en, ok2 := le.Err.(syscall.Errno); ok2 {
			return uint32(en), true
		}
	}
	return 0, false
}

// osLegality asks the OS, through FindFirstFileW, whether this exact name is
// addressable as a file in dir. It creates nothing and reads no contents.
//
//	legal      -> the OS answered "no such file" for a well-formed name (2/3/267)
//	 illegal    -> the OS refused the name itself (123/161/204), or resolved it to
//	              something whose enumerated name is not the requested name
//	unknown     -> the OS answer could not be obtained in this cell
type Legality struct {
	Verdict      string `json:"verdict"`
	WinError     int    `json:"winerror"`
	WinErrorName string `json:"winerror_name"`
	FoundNameHex string `json:"found_name_hex"`
	Probe        string `json:"probe"`
	Note         string `json:"note"`
}

func legalityProbe(dir, name string) Legality {
	full := dir + `\` + name
	p, uerr := syscall.UTF16PtrFromString(full)
	if uerr != nil {
		return Legality{Verdict: "unknown", Probe: "FindFirstFileW", WinErrorName: "utf16-convert-refused",
			Note: "name rejected before the OS was asked (embedded NUL)"}
	}
	var data syscall.Win32finddata
	h, err := syscall.FindFirstFile(p, &data)
	if err == nil {
		syscall.FindClose(h)
		found := syscall.UTF16ToString(data.FileName[:])
		if isReservedName(name) {
			// A reserved name never resolves to a directory entry: the OS answers from
			// the device namespace. The name as written therefore cannot exist there.
			return Legality{Verdict: "illegal", Probe: "FindFirstFileW", FoundNameHex: toHex(found), WinError: 0,
				Note: "FindFirstFileW answered from the device namespace, not from the directory: the plain path cannot hold a file with this name"}
		}
		if strings.EqualFold(found, name) {
			return Legality{Verdict: "legal", Probe: "FindFirstFileW", FoundNameHex: toHex(found), WinError: 0,
				Note: "OS resolves this name to an existing entry in this directory"}
		}
		return Legality{Verdict: "illegal", Probe: "FindFirstFileW", FoundNameHex: toHex(found), WinError: 0,
			Note: fmt.Sprintf("OS resolved the requested name to a different entry (%q): the name as written cannot exist", found)}
	}
	code, ok := errnoCode(err)
	if !ok {
		return Legality{Verdict: "unknown", Probe: "FindFirstFileW", Note: "non-Errno error: " + err.Error()}
	}
	nameStr := errnoName(code)
	switch code {
	case errFileNotFound:
		return Legality{Verdict: "legal", Probe: "FindFirstFileW", WinError: int(code), WinErrorName: nameStr,
			Note: "OS accepted the name and reported it absent"}
	case errPathNotFound, errDirNotFound:
		return Legality{Verdict: "unknown", Probe: "FindFirstFileW", WinError: int(code), WinErrorName: nameStr,
			Note: "OS said the path (not the name) is unusable; with the parent directory verified to exist this is usually an over-long component, but the API does not say which"}
	case errInvalidName, errBadPathname, errEnvarLimit, errInvalidParameter:
		return Legality{Verdict: "illegal", Probe: "FindFirstFileW", WinError: int(code), WinErrorName: nameStr,
			Note: "OS rejected the name itself"}
	case errAccessDenied:
		return Legality{Verdict: "unknown", Probe: "FindFirstFileW", WinError: int(code), WinErrorName: nameStr,
			Note: "OS answered access-denied, which is not a legality answer"}
	}
	return Legality{Verdict: "unknown", Probe: "FindFirstFileW", WinError: int(code), WinErrorName: nameStr,
		Note: "winerror not mapped by this port"}
}

// legalityCreateProbe asks the file system the only question that decides legality:
// attempt to create this exact name here, through kernel32!CreateFileW, in a directory
// this cell owns and verified empty, then list that directory and compare the entry the
// file system actually stored with the name that was asked for.
//
// It never writes and never reads contents, so a reserved device name is created at most
// (which is what the seat order allows) and nothing is ever transferred into it.
func legalityCreateProbe(dir string, name string, extended bool) (map[string]any, Legality) {
	res := map[string]any{
		"probe":     "kernel32!CreateFileW(CREATE_NEW) + directory listing",
		"dir":       dir,
		"path_form": map[bool]string{true: "extended", false: "plain"}[extended],
		"attempted": false,
		"writes":    false,
		"deletes":   false,
	}
	if dir == "" || strings.ContainsRune(name, 0) {
		res["note"] = "not attempted: no probe directory, or the name carries an embedded NUL and was refused before the OS"
		return res, Legality{Verdict: "unknown", Probe: "none", WinErrorName: "refused-before-os",
			Note: "the OS was never asked, so it has no answer for this cell"}
	}
	full := dir + `\` + name
	if extended {
		full = `\?\` + full
	}
	res["attempted"] = true
	ok, code, msg := rawCreateFileW(full)
	res["created"] = ok
	res["winerror"] = code
	res["winerror_name"] = errnoName(uint32(code))
	if msg != "" {
		res["error"] = asciiOnly(truncate(msg, 200))
	}
	entries := []map[string]any{}
	exact, mutated := false, ""
	if ents, err := os.ReadDir(dir); err == nil {
		for _, de := range ents {
			h := toHex(de.Name())
			entries = append(entries, map[string]any{"name_utf8_hex": h, "is_dir": de.IsDir()})
			switch {
			case h == toHex(name):
				exact = true
			case mutated == "" && strings.EqualFold(de.Name(), strings.TrimRight(name, ". ")):
				mutated = h
			}
		}
	} else {
		res["list_error"] = truncate(err.Error(), 160)
	}
	res["listing"] = entries
	switch {
	case ok && exact:
		return res, Legality{Verdict: "legal", Probe: "CreateFileW+listing", WinError: 0,
			Note: "the file system created this exact name in this directory"}
	case ok && !exact:
		v := "illegal"
		note := "the create returned success but the directory stored no entry under the name asked"
		if mutated != "" {
			note = "the file system stored a different name than was asked (" + mutated + "): the name as written cannot exist"
		}
		return res, Legality{Verdict: v, Probe: "CreateFileW+listing", WinError: 0, FoundNameHex: mutated, Note: note}
	case !ok && (code == errInvalidName || code == errBadPathname || code == errEnvarLimit):
		return res, Legality{Verdict: "illegal", Probe: "CreateFileW+listing", WinError: code,
			WinErrorName: errnoName(uint32(code)), Note: "the file system refused the name itself"}
	case !ok && code == errFileNotFound:
		return res, Legality{Verdict: "unknown", Probe: "CreateFileW+listing", WinError: code,
			WinErrorName: errnoName(uint32(code)),
			Note:         "CREATE_NEW answered no-such-file, which is not a legality answer this port can read as either"}
	}
	return res, Legality{Verdict: "unknown", Probe: "CreateFileW+listing", WinError: code,
		WinErrorName: errnoName(uint32(code)), Note: "answer not mapped by this port; winerror stored verbatim"}
}

// legalityProbeExtended asks the same legality question with the \\?\ form, which
// switches off Win32 name parsing (device mapping, trailing-dot/space stripping).
// It is a second face of the OS answer, listed not created, and it is what lets a
// reserved-name cell say "this literal name CAN exist, just not through a plain path".
func legalityProbeExtended(dir, name string) Legality {
	if dir == "" {
		return Legality{Verdict: "unknown", Probe: "none", Note: "no directory face to probe"}
	}
	full := `\\?\` + dir + `\` + name
	p, uerr := syscall.UTF16PtrFromString(full)
	if uerr != nil {
		return Legality{Verdict: "unknown", Probe: "FindFirstFileW(\\\\?\\)", Note: "name rejected before the OS was asked"}
	}
	var data syscall.Win32finddata
	h, err := syscall.FindFirstFile(p, &data)
	if err == nil {
		syscall.FindClose(h)
		found := syscall.UTF16ToString(data.FileName[:])
		v := "legal"
		if !strings.EqualFold(found, name) {
			v = "illegal"
		}
		return Legality{Verdict: v, Probe: "FindFirstFileW(\\\\?\\)", FoundNameHex: toHex(found),
			Note: "extended form answered from the directory, the device namespace is switched off"}
	}
	code, ok := errnoCode(err)
	if !ok {
		return Legality{Verdict: "unknown", Probe: "FindFirstFileW(\\\\?\\)", Note: "non-Errno error: " + err.Error()}
	}
	switch code {
	case errFileNotFound:
		return Legality{Verdict: "legal", Probe: "FindFirstFileW(\\\\?\\)", WinError: int(code),
			WinErrorName: errnoName(code), Note: "the literal name is addressable in the extended form; it is absent"}
	case errInvalidName, errBadPathname, errEnvarLimit:
		return Legality{Verdict: "illegal", Probe: "FindFirstFileW(\\\\?\\)", WinError: int(code),
			WinErrorName: errnoName(code), Note: "OS rejected the name even with parsing switched off"}
	}
	return Legality{Verdict: "unknown", Probe: "FindFirstFileW(\\\\?\\)", WinError: int(code),
		WinErrorName: errnoName(code), Note: "winerror not mapped by this port"}
}

func errnoName(code uint32) string {
	switch code {
	case errFileNotFound:
		return "ERROR_FILE_NOT_FOUND"
	case errPathNotFound:
		return "ERROR_PATH_NOT_FOUND"
	case errInvalidHandle:
		return "ERROR_INVALID_HANDLE"
	case errInvalidName:
		return "ERROR_INVALID_NAME"
	case errBadPathname:
		return "ERROR_BAD_PATHNAME"
	case errDirNotFound:
		return "ERROR_DIRECTORY"
	case errEnvarLimit:
		return "ERROR_FILENAME_EXCED_RANGE"
	case errAccessDenied:
		return "ERROR_ACCESS_DENIED"
	case errAlreadyExists:
		return "ERROR_ALREADY_EXISTS"
	case errInvalidParameter:
		return "ERROR_INVALID_PARAMETER"
	}
	return "winerror:" + strconv.Itoa(int(code))
}

// extendedProbe attempts the same create through the \\?\ path form, which turns
// off Win32 path parsing (trailing-dot/space stripping, device-name mapping) and
// the 260 unit ceiling. It isolates "the OS/NTFS said no" from "Go/Win32 parsing
// said no". Supplementary observation only: it never replaces the pinned entry.
func extendedProbe(absDir, name string, payload []byte) map[string]any {
	out := map[string]any{"attempted": false}
	if strings.ContainsRune(name, 0) || absDir == "" {
		out["note"] = "not attempted: name carries NUL, or the directory path is unknown"
		return out
	}
	target := `\\?\` + absDir + `\` + name
	f, err := os.OpenFile(target, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0644)
	out["attempted"] = true
	if err != nil {
		code, ok := errnoCode(err)
		out["ok"] = false
		out["error"] = truncate(err.Error(), 400)
		if ok {
			out["winerror"] = int(code)
			out["winerror_name"] = errnoName(code)
		}
		return out
	}
	n, werr := f.Write(payload)
	cerr := f.Close()
	out["ok"] = werr == nil && cerr == nil
	out["bytes_written"] = n
	if werr != nil {
		out["write_error"] = truncate(werr.Error(), 400)
	}
	out["note"] = "created in extended form; no deletion is attempted (M19), the entry is left in place"
	return out
}

// registryLongPaths reads LongPathsEnabled with rc checked before the value is
// used. Value 0 and value absent are different facts and are recorded apart.
func registryLongPaths() map[string]any {
	res := map[string]any{"key": `HKLM\SYSTEM\CurrentControlSet\Control\FileSystem\LongPathsEnabled`}
	cmd := exec.Command("reg", "query", `HKLM\SYSTEM\CurrentControlSet\Control\FileSystem`, "/v", "LongPathsEnabled")
	started := time.Now()
	out, err := cmd.Output()
	rc := cmd.ProcessState.ExitCode()
	res["command"] = []string{"reg", "query", `HKLM\SYSTEM\CurrentControlSet\Control\FileSystem`, "/v", "LongPathsEnabled"}
	res["rc"] = rc
	res["elapsed_ms"] = time.Since(started).Milliseconds()
	if err != nil && rc == 0 {
		rc = -1
	}
	if rc != 0 {
		res["status"] = "command-failed"
		res["value"] = nil
		res["note"] = truncate(err.Error(), 200)
		return res
	}
	line := ""
	for _, l := range strings.Split(string(out), "\n") {
		if strings.Contains(l, "LongPathsEnabled") {
			line = strings.TrimSpace(l)
		}
	}
	res["raw_line"] = line
	if line == "" {
		res["status"] = "rc0-no-output"
		res["value"] = nil
		return res
	}
	fields := strings.Fields(line)
	if len(fields) >= 3 && strings.HasPrefix(fields[len(fields)-1], "0x") {
		v, cerr := strconv.ParseInt(fields[len(fields)-1], 0, 32)
		if cerr == nil {
			res["status"] = "present"
			res["value"] = int(v)
			res["value_type"] = "REG_DWORD"
			return res
		}
	}
	res["status"] = "unparsable"
	res["value"] = nil
	return res
}

// volumeMaxComponent uses GetVolumeInformationW through kernel32; if the call
// cannot be made the fact is recorded as not-obtainable, never defaulted.
func volumeMaxComponent(root string) map[string]any {
	res := map[string]any{"root": root, "method": "kernel32.GetVolumeInformationW via syscall.LoadDLL"}
	dll, err := syscall.LoadDLL("kernel32.dll")
	if err != nil {
		res["status"] = "not-obtainable-here"
		res["note"] = truncate(err.Error(), 200)
		return res
	}
	proc, err := dll.FindProc("GetVolumeInformationW")
	if err != nil {
		res["status"] = "not-obtainable-here"
		res["note"] = truncate(err.Error(), 200)
		return res
	}
	var nameBuf [261]uint16
	var fsBuf [261]uint16
	var serial, maxComp, fsFlags uint32
	rp := uintptr(0)
	if root != "" {
		p, e := syscall.UTF16PtrFromString(root)
		if e != nil {
			res["status"] = "not-obtainable-here"
			res["note"] = truncate(e.Error(), 200)
			return res
		}
		rp = uintptr(unsafe.Pointer(p))
	}
	r1, _, last := proc.Call(
		rp,
		uintptr(unsafe.Pointer(&nameBuf[0])), uintptr(len(nameBuf)),
		uintptr(unsafe.Pointer(&serial)),
		uintptr(unsafe.Pointer(&maxComp)),
		uintptr(unsafe.Pointer(&fsFlags)),
		uintptr(unsafe.Pointer(&fsBuf[0])), uintptr(len(fsBuf)),
	)
	res["r1"] = r1
	res["last_error"] = last
	if r1 == 0 {
		res["status"] = "api-failure"
		if code, ok := errnoCode(last); ok {
			res["winerror"] = int(code)
			res["winerror_name"] = errnoName(code)
		}
		res["max_component"] = nil
		return res
	}
	res["status"] = "ok"
	res["max_component"] = int(maxComp)
	res["filesystem_name"] = syscall.UTF16ToString(fsBuf[:])
	res["volume_name"] = syscall.UTF16ToString(nameBuf[:])
	res["volume_serial"] = serial
	res["volume_flags"] = fsFlags
	return res
}
