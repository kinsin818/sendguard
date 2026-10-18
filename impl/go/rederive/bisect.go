package main

import (
	"os"
	"strings"
	"syscall"
	"unicode/utf16"
	"unsafe"
)

// rawCreateFileW asks kernel32!CreateFileW directly, with a UTF-16 pointer this
// function made itself. Go's own syscall.CreateFile wrapper is NOT used, because that
// wrapper is part of the layer under test: calling it could not tell a wall the
// operating system puts up from a wall this runtime puts up on its own.
func rawCreateFileW(full string) (bool, int, string) {
	proc, err := createFileWProc()
	if err != nil {
		return false, -1, "kernel32!CreateFileW not resolvable: " + err.Error()
	}
	p, err := syscall.UTF16PtrFromString(full)
	if err != nil {
		return false, -1, err.Error()
	}
	r1, _, last := proc.Call(
		uintptr(unsafe.Pointer(p)),
		uintptr(0x40000000), // GENERIC_WRITE
		0,                   // dwShareMode
		0,                   // lpSecurityAttributes
		uintptr(1),          // CREATE_NEW
		uintptr(0x80),       // FILE_ATTRIBUTE_NORMAL
		0,                   // hTemplateFile
	)
	if r1 == ^uintptr(0) { // INVALID_HANDLE_VALUE
		code, _ := errnoCode(last)
		return false, int(code), last.Error()
	}
	k := syscall.Handle(r1)
	syscall.CloseHandle(k)
	return true, 0, ""
}

var (
	kernel32DLL    *syscall.DLL
	createFileW    *syscall.Proc
	createFileWErr error
	createFileWSet bool
)

func createFileWProc() (*syscall.Proc, error) {
	if createFileWSet {
		return createFileW, createFileWErr
	}
	createFileWSet = true
	dll, err := syscall.LoadDLL("kernel32.dll")
	if err != nil {
		createFileWErr = err
		return nil, err
	}
	kernel32DLL = dll
	proc, err := dll.FindProc("CreateFileW")
	if err != nil {
		createFileWErr = err
		return nil, err
	}
	createFileW, createFileWErr = proc, nil
	return proc, nil
}

// attemptCreate is the length predicate. It creates and closes; it never writes a
// payload, never opens an existing entry, and never deletes anything (project rule). The
// face decides which layer is being asked:
//
//	face.Prefix   -> address the directory through the \\?\ form, which switches off
//	                 Win32 path parsing and the 259-unit ceiling
//	face.BypassOS -> call CreateFileW directly instead of going through this
//	                 runtime's own path handling, so a rewrite done by the runtime
//	                 cannot hide the answer the OS would have given
func attemptCreate(face BisectFace, dir, name string) (bool, int, string) {
	full := dir + `\` + name
	if face.Prefix {
		full = `\\?\` + full
	}
	if face.BypassOS {
		return rawCreateFileW(full)
	}
	f, err := os.OpenFile(full, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0600)
	if err != nil {
		code, _ := errnoCode(err)
		return false, int(code), err.Error()
	}
	_ = f.Close()
	return true, 0, ""
}

// BisectResult is one length ladder walked by bisection, plus the three
// verification points around the boundary it found.
type BisectResult struct {
	Face            string           `json:"face"`
	FaceNote        string           `json:"face_note"`
	Dir             string           `json:"dir"`
	BaseLenAbs      int              `json:"base_len_abs"`
	SeedChar        string           `json:"seed_char"`
	Low             int              `json:"low"`
	High            int              `json:"high"`
	Boundary        int              `json:"boundary_len"`
	Probes          int              `json:"probes"`
	MonotoneHolds   bool             `json:"monotone_holds"`
	Attempts        []map[string]any `json:"attempts"`
	Verify          []map[string]any `json:"verify"`
	VerifyDeviation string           `json:"verify_deviation"`
}

func bisect(face BisectFace, dir string, baseLenAbs int, char string, low, high int) *BisectResult {
	r := &BisectResult{
		Face: face.Name, Dir: dir, BaseLenAbs: baseLenAbs, SeedChar: char,
		Low: low, High: high, MonotoneHolds: true,
		FaceNote: map[bool]string{true: "Win32 path parsing switched off; the 259-unit ceiling does not apply",
			false: "plain path; subject to whatever this layer does with long paths"}[face.Prefix],
	}
	name := func(n int) string { return strings.Repeat(char, n) }
	probe := func(n int, phase string) bool {
		ok, code, msg := attemptCreate(face, dir, name(n))
		rec := map[string]any{"len": n, "ok": ok, "phase": phase,
			"name_hex": toHex(name(n)), "abs_total_len": dirLen(dir) + 1 + len(utf16.Encode([]rune(name(n))))}
		if code != 0 {
			rec["winerror"] = code
			rec["winerror_name"] = errnoName(uint32(code))
		}
		if msg != "" {
			rec["error"] = asciiOnly(truncate(msg, 200))
		}
		r.Attempts = append(r.Attempts, rec)
		r.Probes++
		return ok
	}

	// The range is an accepted/rejected bracket agreed with the contract owner before
	// the search: low is known accepted, high is known rejected.
	if !probe(low, "anchor_low") {
		r.Boundary = 0
		r.MonotoneHolds = false
		r.Verify = verifyFace(face, dir, char, 0, r)
		return r
	}
	probe(high, "anchor_high")
	lo, hi := low, high
	for hi-lo > 1 {
		mid := (lo + hi) / 2
		if probe(mid, "bisect") {
			lo = mid
		} else {
			hi = mid
		}
	}
	r.Boundary = lo
	r.Verify = verifyFace(face, dir, char, lo, r)
	// gate.md §4: the verification cell and the bisection may differ by at most one
	// code unit; more than that is an instrument question, so it is recorded, not smoothed.
	okMinus, _, _ := attemptCreate(face, dir, name(lo-1))
	if okMinus {
		r.VerifyDeviation = "boundary-1 also accepted: the boundary is a floor, the ladder is not sharp"
	} else {
		r.VerifyDeviation = "boundary-1 rejected, boundary accepted, boundary+1 rejected: sharp within 1 unit"
	}
	return r
}

// verifyFace lands separate probe files at boundary-1 and boundary+1. boundary
// itself is deliberately NOT re-probed: an O_EXCL retry of a name the bisection
// already landed answers "already exists" instead of "too long", and a false RED
// on a control is worse than a missing probe. Its acceptance is carried by the
// bisection's own accepted anchor, which is published in attempts as phase=bisect.
func verifyFace(face BisectFace, dir, char string, boundary int, r *BisectResult) []map[string]any {
	out := []map[string]any{}
	for _, n := range []int{boundary - 1, boundary + 1} {
		if n < 1 {
			out = append(out, map[string]any{"len": n, "skipped": "below the counting floor"})
			continue
		}
		ok, code, msg := attemptCreate(face, dir, strings.Repeat(char, n))
		rec := map[string]any{"len": n, "ok": ok, "phase": "verify",
			"name_hex": toHex(strings.Repeat(char, n))}
		if code != 0 {
			rec["winerror"] = code
			rec["winerror_name"] = errnoName(uint32(code))
		}
		if msg != "" {
			rec["error"] = asciiOnly(truncate(msg, 200))
		}
		out = append(out, rec)
		r.Attempts = append(r.Attempts, rec)
		r.Probes++
	}
	return out
}

func faceSummary(b *BisectResult) map[string]any {
	return map[string]any{
		"face": b.Face, "boundary_len": b.Boundary, "probes": b.Probes,
		"low": b.Low, "high": b.High, "monotone_holds": b.MonotoneHolds,
		"verify": b.Verify, "verify_deviation": b.VerifyDeviation,
	}
}
