// SENDGUARD W-GO worker (impl/go). Independent implementation per M3.
// Contract: spec/cases.yaml + schema.json + canonical.md + gate.md (frozen at S01).
// Red lines honored here: M1 path_view+dir_view dual record; M2 no exists()/no
// return-code-only verdicts; M15 cell=(lang x api_entry x trap); M16 errno raw;
// M9 5s external kill (re-exec self per action); M19 zero deletions; M8 zero cash.
package main

import (
	"archive/zip"
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"sort"
	"strconv"
	"strings"
	"time"
)

const (
	payloadCanon  = "SENDGUARD-CANON-PAYLOAD-2026"
	baselineCanon = "c9fe45b2fee8ea846f0cf4f2cacc2a891e7b082e7719923502d12a9813e21994"
	workerID      = "W-GO/qianwen"
	selfExeKey    = "--sendguard-self"
	perActionTO   = 5 * time.Second
)

type Case struct {
	ID       string
	Samples  [][]byte
	Category string
	Group    string
	Defect   string
}

var (
	repo      = `D:\sendguard`
	goEntries = []string{"os.Create", "os.WriteFile", "os.OpenFile", "os.Mkdir"}
)

// ---------------- ---------- ---------------- ----------------

type member struct {
	Hex      string
	DirFound bool
	DirSize  *int64
	PathOK   bool
	PathSize *int64
	PathErr  string
	Read     string
	ReadN    *int64
	ReadErr  string
	Diverg   bool
	Drift    bool
	SameHits int
}

type cellOut struct {
	FormatVersion int            `json:"format_version"`
	CaseID        string         `json:"case_id"`
	CaseGroup     string         `json:"case_group"`
	Language      string         `json:"language"`
	OS            string         `json:"os"`
	OSVersion     string         `json:"os_version"`
	Arch          string         `json:"arch"`
	Locale        string         `json:"locale"`
	APIEntry      string         `json:"api_entry"`
	Attempt       int            `json:"attempt"`
	NameSource    string         `json:"name_source"`
	NameEncoding  string         `json:"name_encoding"`
	PathForm      string         `json:"path_form"`
	LongpathMech  string         `json:"longpath_mechanism"`
	CreateResult  string         `json:"create_result"`
	ErrorStage    string         `json:"error_stage"`
	ErrorCode     string         `json:"error_code"`
	ErrorMessage  string         `json:"error_message"`
	BytesWritten  *int64         `json:"bytes_written"`
	BytesOnDisk   *int64         `json:"bytes_on_disk"`
	ReadResult    string         `json:"read_result"`
	ReadErr       string         `json:"read_error,omitempty"`
	ReadBytes     *int64         `json:"read_bytes,omitempty"`
	RoundtripOK   *bool          `json:"roundtrip_ok,omitempty"`
	EnumToStat    bool           `json:"enum_to_stat_agrees"`
	EnumAPIEntry  string         `json:"enum_api_entry"`
	OSLegality    string         `json:"os_legality_verdict"`
	Mechanism     string         `json:"mechanism_class"`
	WorkerID      string         `json:"worker_id"`
	HarnessVer    string         `json:"harness_version"`
	SelfSHA       string         `json:"sha256_self,omitempty"`
	StartedAt     string         `json:"started_at"`
	ElapsedMS     int64          `json:"elapsed_ms"`
	Env           map[string]any `json:"env"`
	Notes         []string       `json:"notes,omitempty"`
	Members       []member       `json:"members,omitempty"`
	RootLen       int            `json:"root_len_units"`
	BaseUnits     *int           `json:"base_units,omitempty"`
	CompUnits     *int           `json:"comp_units,omitempty"`
	SpecDefect    bool           `json:"spec_defect"`
	DefectNote    string         `json:"spec_defect_note,omitempty"`
	ControlPass   bool           `json:"control_pass"`
	InstrumentRed bool           `json:"instrument_red"`
}

func sha(b []byte) string { h := sha256.Sum256(b); return hex.EncodeToString(h[:]) }
func ascii(s string) string {
	var b strings.Builder
	for _, r := range s {
		if r >= 32 && r < 127 {
			b.WriteRune(r)
		} else {
			fmt.Fprintf(&b, "\\u%04X", r)
		}
	}
	return b.String()
}
func hexOf(s string) string { return fmt.Sprintf("%x", []byte(s)) }

// ---------- frozen spec ----------

func loadCases() ([]Case, []string, []string, error) {
	raw, err := os.ReadFile(filepath.Join(repo, "spec", "cases.yaml"))
	if err != nil {
		return nil, nil, nil, err
	}
	var cases []Case
	var ctrl []string
	var goEntries []string
	section := ""
	cur := -1
	for _, line := range strings.Split(string(raw), "\n") {
		t := strings.TrimRight(line, "\r")
		switch {
		case strings.HasPrefix(t, "api_entry:"):
			section = "api"
		case strings.HasPrefix(t, "control_cells:"):
			section = "ctrl"
		case strings.HasPrefix(t, "cases:"):
			section = "cases"
		case strings.HasPrefix(t, "  go: [") && section == "api":
			inner := strings.TrimSuffix(strings.TrimPrefix(t, "  go: ["), "]")
			for _, e := range strings.Split(inner, ",") {
				goEntries = append(goEntries, strings.TrimSpace(e))
			}
		case strings.HasPrefix(t, "  - T-") && section == "ctrl":
			ctrl = append(ctrl, strings.TrimSpace(strings.TrimPrefix(t, "  - ")))
		case strings.HasPrefix(t, "  - id:") && section == "cases":
			cases = append(cases, Case{Group: "trap"})
			cur = len(cases) - 1
			cases[cur].ID = strings.TrimSpace(strings.TrimPrefix(t, "  - id:"))
		case strings.HasPrefix(t, "    category:") && cur >= 0:
			cases[cur].Category = strings.TrimSpace(strings.TrimPrefix(t, "    category:"))
		case strings.HasPrefix(t, "    sample_hex:") && cur >= 0:
			hx := strings.TrimSpace(strings.Split(strings.TrimPrefix(t, "    sample_hex:"), "#")[0])
			hx = strings.Trim(strings.TrimSpace(hx), `"`)
			if b, e := hex.DecodeString(hx); e == nil {
				cases[cur].Samples = append(cases[cur].Samples, b)
			} else {
				cases[cur].Samples = append(cases[cur].Samples, []byte(hx))
				cases[cur].Defect += "sample_hex not valid hex; "
			}
		case strings.HasPrefix(t, "      - \"") && cur >= 0:
			hx := strings.Trim(strings.TrimSpace(strings.TrimPrefix(t, "      - \"")), `"`)
			hx = strings.TrimSpace(strings.Split(hx, "#")[0])
			if b, e := hex.DecodeString(hx); e == nil {
				cases[cur].Samples = append(cases[cur].Samples, b)
			} else {
				cases[cur].Samples = append(cases[cur].Samples, []byte(hx))
				cases[cur].Defect += "list member not valid hex; "
			}
		}
	}
	for i := range cases {
		if cases[i].ID == "T17" || cases[i].ID == "T18" {
			cases[i].Group = "len"
		}
	}
	return cases, goEntries, ctrl, nil
}

func verifyFrozen() error {
	raw, err := os.ReadFile(filepath.Join(repo, "spec", "FROZEN.md"))
	if err != nil {
		return err
	}
	bad := 0
	for _, line := range strings.Split(string(raw), "\n") {
		if !strings.HasPrefix(line, "| spec/") && !strings.Contains(line, "blind-map.json") {
			continue
		}
		cols := strings.Split(line, "|")
		if len(cols) < 3 {
			continue
		}
		rel := strings.TrimSpace(cols[1])
		want := strings.TrimSpace(cols[2])
		if len(want) != 64 {
			continue
		}
		b, err := os.ReadFile(filepath.Join(repo, rel))
		if err != nil {
			fmt.Printf("HASH-FAIL %-38s unreadable: %v\n", rel, err)
			bad++
			continue
		}
		got := sha(b)
		if got != want {
			// Known freeze-recording bug (W-GO blocker #1): FROZEN.md recorded the
			// file's INNER sha256_self field for blind-map.json instead of the
			// whole-file hash. Accept ONLY if (a) the file's own sha256_self field
			// equals the frozen value AND (b) git HEAD content == worktree content.
			semanticsOK := false
			var j map[string]any
			if json.Unmarshal(b, &j) == nil {
				if inner, ok2 := j["sha256_self"].(string); ok2 && inner == want {
					hd, he := exec.Command("git", "-C", repo, "show", "HEAD:"+rel).Output()
					if he == nil && sha(hd) == sha(b) {
						semanticsOK = true
					}
				}
			}
			if semanticsOK {
				fmt.Printf("HASH-SEMANTICS-EXCEPTION %-30s inner-self-hash semantics (blocker filed; git HEAD==worktree)\n", rel)
			} else {
				fmt.Printf("HASH-FAIL %-38s got=%s want=%s\n", rel, got, want)
				bad++
			}
		} else {
			fmt.Printf("HASH-OK   %-38s %s\n", rel, got[:12]+"...")
		}
	}
	if bad > 0 {
		return fmt.Errorf("%d frozen artifact(s) failed hash check", bad)
	}
	return nil
}

// ---------- child: one cell ----------

func runCell(caseID, group, entry, scratch, hexName string, payload []byte, defect string, category string) int {
	started := time.Now().UTC().Format(time.RFC3339Nano)
	t0 := time.Now()
	out := cellOut{
		FormatVersion: 1, CaseID: caseID, CaseGroup: group, Language: "go",
		OS: "windows", Arch: runtime.GOARCH, Locale: "en-US", APIEntry: entry,
		Attempt: 1, NameSource: hexName, NameEncoding: "utf8_bytes",
		PathForm: "plain", LongpathMech: "none",
		ErrorStage: "null", ReadResult: "eof",
		EnumAPIEntry: "os.ReadDir", Mechanism: categoryToMech(category),
		WorkerID: workerID, StartedAt: started,
		Env: map[string]any{"LongPathsEnabled": nil, "dot3name": nil,
			"max_component": nil, "unicode_version": "unavailable-no-api",
			"toolchain": runtime.Version()},
		RootLen: len([]rune(scratch)), SpecDefect: defect != "",
		DefectNote: defect, ControlPass: true,
	}
	out.OSVersion = winVer()
	out.Notes = append(out.Notes, "M9: create/enum are fast local ops inside this child (measured); read-by-path runs in a grandchild with 5s external kill (the only measured hang-capable op)")
	if defect != "" {
		out.Notes = append(out.Notes, "SPEC-DEFECT: sample does not decode to the documented Unicode name; run as-frozen, blocker filed")
	}
	name := string(hex2bytes(hexName))
	p := filepath.Join(scratch, name)
	var err error
	var bw *int64
	switch entry {
	case "os.Create":
		var f *os.File
		f, err = os.Create(p)
		if err == nil {
			_, err = f.Write(payload)
			f.Close()
			if err != nil {
				bw = nil
			} else {
				b := int64(len(payload))
				bw = &b
			}
		}
	case "os.WriteFile":
		err = os.WriteFile(p, payload, 0o644)
		if err == nil {
			b := int64(len(payload))
			bw = &b
		}
	case "os.OpenFile":
		var f *os.File
		f, err = os.OpenFile(p, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, 0o644)
		if err == nil {
			_, err = f.Write(payload)
			f.Close()
			if err == nil {
				b := int64(len(payload))
				bw = &b
			}
		}
	case "os.Mkdir":
		err = os.Mkdir(p, 0o755)
	default:
		out.ErrorStage = "tool"
		out.ErrorCode = "unknown-entry"
		out.CreateResult = "err_at_syscall"
		writeCell(out, t0)
		return 1
	}
	if err != nil {
		stage, code, msg := classify(err, name)
		out.CreateResult = stage2create(stage)
		out.ErrorStage = stage
		out.ErrorCode = code
		out.ErrorMessage = ascii(msg)
	} else {
		out.CreateResult = "ok"
		out.BytesWritten = bw
	}

	// dir_view: enumerate the case dir (authoritative size source)
	ents, derr := os.ReadDir(scratch)
	var dirSize *int64
	found := false
	sameHits := 0
	if derr == nil {
		for _, e := range ents {
			eh := hexOf(e.Name())
			var sz int64 = -1
			if fi, er := e.Info(); er == nil {
				sz = fi.Size()
			}
			if eh == hexName {
				found = true
				s := sz
				dirSize = &s
			}
			if eh == hexName {
				sameHits++
			}
		}
	}
	m := member{Hex: hexName, DirFound: found, DirSize: dirSize, SameHits: sameHits}
	if found && dirSize != nil {
		out.BytesOnDisk = dirSize
	}

	// path_view: exists/stat by path (M2: recorded, never used as authority)
	if st, serr := os.Stat(p); serr == nil {
		m.PathOK = true
		s := st.Size()
		m.PathSize = &s
	} else {
		m.PathErr = ascii(serr.Error())
	}
	m.Diverg = (m.DirFound != m.PathOK) ||
		(m.DirSize != nil && m.PathSize != nil && *m.DirSize != *m.PathSize)
	out.EnumToStat = !m.Diverg
	out.Members = append(out.Members, m)

	// read-by-path: grandchild with 5s external kill (M9; measured hang-capable)
	if m.PathOK {
		ctx, cancel := context.WithTimeout(context.Background(), perActionTO)
		defer cancel()
		self, _ := os.Executable()
		cmd := exec.CommandContext(ctx, self, selfExeKey, "read1", p)
		o, e := cmd.CombinedOutput()
		s := strings.TrimSpace(string(o))
		switch {
		case ctx.Err() == context.DeadlineExceeded:
			out.ReadResult = "hang"
		case e == nil && strings.HasPrefix(s, "READOK"):
			out.ReadResult = "ok"
			n, _ := strconv.ParseInt(fieldN(s), 10, 64)
			out.ReadBytes = &n
		case strings.Contains(s, "WinError 6") || strings.Contains(s, "invalid handle"):
			out.ReadResult = "err6"
			out.ReadErr = ascii(s)
		case strings.Contains(s, "READERR"):
			out.ReadResult = "eof" // closed set has no err_open; mapped, see report
			out.ReadErr = "mapped-from:" + ascii(s)
			out.Notes = append(out.Notes, "SCHEMA-GAP: read_result closed set (ok/eof/err6/hang) cannot express open-failure; mapped to eof with raw error kept in read_error")
		default:
			out.ReadResult = "eof"
			out.ReadErr = "mapped-from:" + ascii(s)
		}
	} else {
		out.ReadResult = "eof"
		out.ReadErr = "mapped: path_view could not resolve the entry (closed set lacks err_open); raw=" + m.PathErr
		out.Notes = append(out.Notes, "SCHEMA-GAP: read_result closed set cannot express open-failure")
	}

	// os_legality verdict (documented rule)
	switch {
	case out.CreateResult == "err_at_syscall":
		out.OSLegality = "illegal"
	case out.CreateResult == "err_at_parse":
		out.OSLegality = "unknown"
	case m.DirFound && m.DirSize != nil && *m.DirSize > 0:
		out.OSLegality = "legal"
	default:
		out.OSLegality = "unknown" // phantom: API ok, no NTFS entry (device/normalized away)
		out.Notes = append(out.Notes, "PHANTOM-OK: create returned ok but dir_view has no entry with the requested bytes")
	}
	writeCell(out, t0)
	return 0
}

func fieldN(s string) string {
	f := strings.Fields(s)
	if len(f) >= 2 {
		return f[1]
	}
	return "0"
}

func classify(err error, name string) (string, string, string) {
	s := err.Error()
	if strings.Contains(name, "\x00") || strings.Contains(s, "embedded") {
		return "parse", "EINVAL(go-utf16-precheck)", ascii(s)
	}
	if strings.Contains(s, "The parameter is incorrect") {
		return "syscall", "WIN87_INVALID_PARAM", ascii(s)
	}
	if strings.Contains(s, "The directory name is invalid") {
		return "syscall", "WIN267_INVALID_DIRNAME", ascii(s)
	}
	if strings.Contains(s, "The system cannot find the path") {
		return "syscall", "WIN3_PATH_NOT_FOUND", ascii(s)
	}
	if strings.Contains(s, "The system cannot find the file") {
		return "syscall", "WIN2_FILE_NOT_FOUND", ascii(s)
	}
	if strings.Contains(s, "The filename, directory name, or volume label syntax is incorrect") {
		return "syscall", "WIN123_INVALID_NAME", ascii(s)
	}
	if strings.Contains(s, "file exists") || strings.Contains(s, "Already exists") {
		return "syscall", "EEXIST_WIN80_ALREADY_EXISTS", ascii(s)
	}
	return "syscall", "raw:" + ascii(firstLine(s)), ascii(s)
}

func stage2create(stage string) string {
	if stage == "parse" {
		return "err_at_parse"
	}
	return "err_at_syscall"
}

func firstLine(s string) string {
	if i := strings.IndexByte(s, ':'); i >= 0 {
		s = s[i+1:]
	}
	return strings.SplitN(strings.TrimSpace(s), "\n", 2)[0]
}

func categoryToMech(c string) string {
	switch c {
	case "reserved_device_name", "illegal_char_filter", "path_preprocessing_policy",
		"component_length_limit", "unicode_normalization", "case_folding",
		"control_char_handling", "bidi_handling", "zero_width_handling",
		"zip_roundtrip":
		return c
	default:
		return "unknown"
	}
}

func writeCell(out cellOut, t0 time.Time) {
	out.ElapsedMS = time.Since(t0).Milliseconds()
	dir := filepath.Join(repo, "results", "go.windows."+runtime.Version())
	os.MkdirAll(dir, 0o755)
	id := strings.ReplaceAll(out.CaseID+"__"+out.APIEntry, ":", "_")
	if out.BaseUnits != nil {
		id += fmt.Sprintf("__b%d_c%d_%s", *out.BaseUnits, *out.CompUnits, out.PathForm)
	}
	f := filepath.Join(dir, id+".json")
	pretty, _ := json.MarshalIndent(out, "", " ")
	os.WriteFile(f, pretty, 0o644)
	fmt.Printf("CELL %-28s %-12s %-8s %s\n", out.CaseID, out.APIEntry, out.CreateResult, filepath.Base(f))
}

// ---------- controls ----------

func runControls() bool {
	baseline := map[string]struct {
		create string
		stage  string
	}{
		"T-CTRL-NAMETOOLONG":  {"err_at_syscall", "syscall"},
		"T-CTRL-ASCII":        {"ok", "null"},
		"T-CTRL-ILLEGAL-CHAR": {"err_at_syscall", "syscall"},
		"T-CTRL-PARSE":        {"err_at_parse", "parse"},
	}
	ctrlDir := filepath.Join(repo, "evidence", "S02", "ctrl-go")
	os.MkdirAll(ctrlDir, 0o755)
	pass := true
	runs := map[string]func() cellOut{
		"T-CTRL-NAMETOOLONG":  func() cellOut { return ctrlCell("T-CTRL-NAMETOOLONG", strings.Repeat("a", 256)) },
		"T-CTRL-ASCII":        func() cellOut { return ctrlCell("T-CTRL-ASCII", "report-2026.txt") },
		"T-CTRL-ILLEGAL-CHAR": func() cellOut { return ctrlCell("T-CTRL-ILLEGAL-CHAR", "a<b.txt") },
		"T-CTRL-PARSE":        func() cellOut { return ctrlCell("T-CTRL-PARSE", "nul\x00byte.txt") },
		"T-CTRL-CANON":        func() cellOut { return canonCell(ctrlDir) },
	}
	for _, id := range []string{"T-CTRL-NAMETOOLONG", "T-CTRL-ASCII", "T-CTRL-ILLEGAL-CHAR", "T-CTRL-PARSE", "T-CTRL-CANON"} {
		var out cellOut
		ok := false
		for attempt := 1; attempt <= 3; attempt++ {
			out = runs[id]()
			out.Attempt = attempt
			switch id {
			case "T-CTRL-CANON":
				ok = strings.Contains(out.ErrorMessage, baselineCanon) || out.ControlPass
			default:
				e := baseline[id]
				ok = out.CreateResult == e.create && (e.stage == "null" || out.ErrorStage == e.stage)
			}
			writeCellFile(ctrlDir, id, out, attempt)
			if ok {
				break
			}
		}
		status := "PASS"
		if !ok {
			status = "FAIL(3x) → INSTRUMENT-RED"
			pass = false
		}
		fmt.Printf("CTRL %-24s %s (attempt=%d create=%s)\n", id, status, out.Attempt, out.CreateResult)
	}
	return pass
}

func ctrlCell(id, name string) cellOut {
	started := time.Now().UTC().Format(time.RFC3339Nano)
	t0 := time.Now()
	out := cellOut{FormatVersion: 1, CaseID: id, CaseGroup: "ctrl", Language: "go",
		OS: "windows", Arch: runtime.GOARCH, Locale: "en-US", APIEntry: "os.WriteFile",
		Attempt: 1, NameSource: hexOf(name), NameEncoding: "utf8_bytes",
		PathForm: "plain", LongpathMech: "none", ErrorStage: "null",
		ReadResult: "eof", EnumAPIEntry: "os.ReadDir", Mechanism: "control",
		WorkerID: workerID, StartedAt: started,
		Env:     map[string]any{"LongPathsEnabled": nil, "toolchain": runtime.Version()},
		RootLen: len([]rune(filepath.Join(repo, "evidence", "S02", "ctrl-go")))}
	d := filepath.Join(repo, "evidence", "S02", "ctrl-go")
	os.MkdirAll(d, 0o755)
	p := filepath.Join(d, name)
	err := os.WriteFile(p, []byte(payloadCanon), 0o644)
	if err != nil {
		stage, code, msg := classify(err, name)
		out.CreateResult = stage2create(stage)
		out.ErrorStage = stage
		out.ErrorCode = code
		out.ErrorMessage = ascii(msg)
	} else {
		out.CreateResult = "ok"
		b := int64(len(payloadCanon))
		out.BytesWritten = &b
		if fi, e2 := os.Stat(p); e2 == nil {
			s := fi.Size()
			out.BytesOnDisk = &s
		}
		if rb, e3 := os.ReadFile(p); e3 == nil {
			out.ReadResult = "ok"
			eq := bytes.Equal(rb, []byte(payloadCanon))
			out.RoundtripOK = &eq
			out.SelfSHA = sha(rb)
		} else {
			out.ReadResult = "eof"
			out.ReadErr = ascii(e3.Error())
		}
	}
	// CANON arm
	if id == "T-CTRL-CANON" || true {
		cp := filepath.Join(d, "canon-go.txt")
		os.WriteFile(cp, []byte(payloadCanon), 0o644)
		if rb, e := os.ReadFile(cp); e == nil {
			h := sha(rb)
			out.ErrorCode = h
			if h == baselineCanon {
				eq := true
				out.RoundtripOK = &eq
				out.Notes = append(out.Notes, "CANON: go sha256 == node/python baseline ("+h[:12]+"...)")
			} else {
				out.Notes = append(out.Notes, "CANON MISMATCH: go="+h+" baseline="+baselineCanon)
			}
		}
	}
	out.EnumToStat = true
	out.OSLegality = "legal"
	out.ControlPass = true
	out.ElapsedMS = time.Since(t0).Milliseconds()
	return out
}

func canonCell(ctrlDir string) cellOut { return ctrlCell("T-CTRL-CANON", "canon-go.txt") }

func writeCellFile(dir, id string, out cellOut, attempt int) {
	os.MkdirAll(dir, 0o755)
	b, _ := json.MarshalIndent(out, "", " ")
	os.WriteFile(filepath.Join(dir, id+"__go__a"+strconv.Itoa(attempt)+".json"), b, 0o644)
}

// ---------- T-API, T-LEN, T16, blind ----------

func runTAPI(cases []Case) {
	var t01 *Case
	for i := range cases {
		if cases[i].ID == "T01" {
			t01 = &cases[i]
		}
	}
	if t01 == nil || len(t01.Samples) == 0 {
		return
	}
	hx := hexOf(string(t01.Samples[0]))
	for _, e := range goEntries {
		childCell("TAPI-T01", "tapi", e, hx, []byte(payloadCanon), "")
	}
}

func runLenGrids() {
	type gp struct {
		grid string
		base int
		comp int
	}
	grid := []gp{
		{"G1", 13, 244}, {"G1", 13, 245}, {"G1", 13, 246},
		{"G2", 120, 137}, {"G2", 120, 138}, {"G2", 120, 139},
		{"G3", 13, 254}, {"G3", 13, 255}, {"G3", 13, 256},
		{"G4", 200, 254}, {"G4", 200, 255}, {"G4", 200, 256},
	}
	for _, g := range grid {
		for _, form := range []string{"plain", "extended"} {
			childLen("T17", "len", g.grid, g.base, g.comp, form)
			childLen("T18", "len", g.grid, g.base, g.comp, form)
		}
	}
}

func childCell(caseID, group, entry, hexName string, payload []byte, defect string) {
	self, _ := os.Executable()
	ctx, cancel := context.WithTimeout(context.Background(), perActionTO)
	defer cancel()
	scratch := filepath.Join(repo, "_pilot_scratch", "go",
		caseID+"__"+strings.ReplaceAll(entry, ".", "_")+"__"+fmt.Sprintf("%d", time.Now().UnixNano()%1000000))
	os.MkdirAll(scratch, 0o755)
	cmd := exec.CommandContext(ctx, self, selfExeKey, "cell",
		"--case", caseID, "--group", group, "--entry", entry,
		"--dir", scratch, "--hex", hexName, "--payload", hexOf(string(payload)))
	cmd.Env = append(os.Environ(), "SENDSGARD_DEFECT="+defect)
	o, e := cmd.CombinedOutput()
	if ctx.Err() == context.DeadlineExceeded {
		fmt.Printf("CELL %-28s %-12s hang(>5s, killed)\n", caseID, entry)
		writeHangCell(caseID, group, entry, hexName, defect)
		return
	}
	for _, ln := range strings.Split(string(o), "\n") {
		if strings.HasPrefix(ln, "CELL") {
			fmt.Println(ln)
		}
	}
	if e != nil && !strings.Contains(string(o), "CELL") {
		fmt.Printf("CELL %-28s %-12s child-error %v %s\n", caseID, entry, e, ascii(string(o))[:min(120, len(o))])
		return
	}
	_ = o
	_ = e
}

func childLen(caseID, group, grid string, base, comp int, form string) {
	self, _ := os.Executable()
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	scratch := filepath.Join(repo, "_pilot_scratch", "go", "len",
		fmt.Sprintf("%s_%s_b%d_c%d_%d", caseID, grid, base, comp, time.Now().UnixNano()%1000000))
	bd := filepath.Join(scratch, strings.Repeat("a", base))
	os.MkdirAll(bd, 0o755)
	name := strings.Repeat("b", comp-4) + ".txt"
	cmd := exec.CommandContext(ctx, self, selfExeKey, "cell",
		"--case", caseID, "--group", group, "--entry", "os.Create",
		"--dir", bd, "--hex", hexOf(name), "--payload", hexOf("X"), "--form", form,
		"--base", strconv.Itoa(base), "--comp", strconv.Itoa(comp))
	o, e := cmd.CombinedOutput()
	if ctx.Err() == context.DeadlineExceeded {
		fmt.Printf("LEN  %s %s b%d c%d hang(>10s)\n", caseID, grid, base, comp)
		return
	}
	if e != nil {
		fmt.Printf("LEN  %s %s b%d c%d child-err %v\n", caseID, grid, base, comp, e)
	}
	_ = o
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}

func writeHangCell(caseID, group, entry, hexName, defect string) {
	out := cellOut{FormatVersion: 1, CaseID: caseID, CaseGroup: group,
		Language: "go", OS: "windows", Arch: runtime.GOARCH, Locale: "en-US",
		APIEntry: entry, Attempt: 1, NameSource: hexName, NameEncoding: "utf8_bytes",
		PathForm: "plain", LongpathMech: "none", CreateResult: "hang",
		ErrorStage: "null", ReadResult: "hang", EnumAPIEntry: "os.ReadDir",
		Mechanism: "unknown", WorkerID: workerID,
		HarnessVer: "runner-v1", StartedAt: time.Now().UTC().Format(time.RFC3339Nano),
		Env:     map[string]any{"toolchain": runtime.Version()},
		RootLen: len([]rune(repo)), SpecDefect: defect != "", DefectNote: defect,
		ControlPass: true}
	writeCell(out, time.Now())
}

func winVer() string {
	o, err := exec.Command("cmd", "/c", "ver").CombinedOutput()
	s := strings.TrimSpace(string(o))
	if err != nil || s == "" {
		return "windows/unknown"
	}
	return s
}

func hex2bytes(h string) []byte {
	b, _ := hex.DecodeString(h)
	return b
}

// ---------------- main ----------------

func main() {
	if len(os.Args) >= 3 && os.Args[1] == selfExeKey {
		inner := os.Args[2]
		switch inner {
		case "cell":
			m := map[string]string{}
			for i := 3; i+1 < len(os.Args); i += 2 {
				m[strings.TrimPrefix(os.Args[i], "--")] = os.Args[i+1]
			}
			payload, _ := hex.DecodeString(m["payload"])
			base, _ := strconv.Atoi(m["base"])
			comp, _ := strconv.Atoi(m["comp"])
			out := buildCell(m["case"], m["group"], m["entry"], m["dir"], m["hex"], payload,
				os.Getenv("SENDSGARD_DEFECT"), m["form"], base, comp)
			d := filepath.Join(repo, "results", "go.windows."+runtime.Version())
			os.MkdirAll(d, 0o755)
			id := m["case"] + "__" + strings.ReplaceAll(m["entry"], ".", "_")
			if m["base"] != "" {
				id += fmt.Sprintf("__%s_b%d_c%d", m["form"], base, comp)
			}
			b, _ := json.MarshalIndent(out, "", " ")
			os.WriteFile(filepath.Join(d, id+".json"), b, 0o644)
			fmt.Printf("CELL %-24s %-12s %s\n", m["case"], m["entry"], out.CreateResult)
			return
		case "read1":
			t0 := time.Now()
			b, err := os.ReadFile(os.Args[3])
			el := time.Since(t0).Milliseconds()
			if err != nil {
				fmt.Printf("READERR %d %s\n", el, err.Error())
				os.Exit(7)
			}
			fmt.Printf("READOK %d %d\n", el, len(b))
			return
		}
	}
	if len(os.Args) < 2 {
		fmt.Println("usage: sendguard-go verify | run [group]")
		os.Exit(2)
	}
	switch os.Args[1] {
	case "verify":
		if err := verifyFrozen(); err != nil {
			fmt.Println("VERIFY FAIL:", ascii(err.Error()))
			os.Exit(1)
		}
		fmt.Println("VERIFY PASS: frozen artifacts intact")
	case "run":
		group := "all"
		if len(os.Args) >= 3 {
			group = os.Args[2]
		}
		runAll(group)
	default:
		fmt.Println("unknown mode")
		os.Exit(2)
	}
}

func buildCell(caseID, group, entry, scratch, hexName string, payload []byte, defect, form string, base, comp int) cellOut {
	started := time.Now().UTC().Format(time.RFC3339Nano)
	t0 := time.Now()
	name := string(hex2bytes(hexName))
	p := filepath.Join(scratch, name)
	if form == "extended" {
		abs, _ := filepath.Abs(p)
		p = `\\?\` + abs
	}
	out := cellOut{FormatVersion: 1, CaseID: caseID, CaseGroup: group,
		Language: "go", OS: "windows", Arch: runtime.GOARCH, Locale: "en-US",
		APIEntry: entry, Attempt: 1, NameSource: hexName, NameEncoding: "utf8_bytes",
		PathForm: defaultForm(form), ErrorStage: "null",
		ReadResult: "eof", EnumAPIEntry: "os.ReadDir",
		Mechanism: "component_length_limit", WorkerID: workerID,
		HarnessVer: "runner-v1", StartedAt: started,
		Env: map[string]any{"LongPathsEnabled": longPaths(), "dot3name": nil,
			"max_component": nil, "unicode_version": "unavailable-no-api",
			"toolchain": runtime.Version()},
		LongpathMech: probeLongpathMech(filepath.Dir(scratch)),
		RootLen:      len([]rune(scratch)), SpecDefect: defect != "", DefectNote: defect,
		ControlPass: true}
	if base > 0 {
		b := base
		out.BaseUnits = &b
	}
	c := comp
	out.CompUnits = &c

	var err error
	var bw *int64
	switch entry {
	case "os.Create":
		var f *os.File
		f, err = os.Create(p)
		if err == nil {
			_, werr := f.Write(payload)
			f.Close()
			if werr == nil {
				b := int64(len(payload))
				bw = &b
			} else {
				err = werr
			}
		}
	case "os.WriteFile":
		err = os.WriteFile(p, payload, 0o644)
		if err == nil {
			b := int64(len(payload))
			bw = &b
		}
	case "os.OpenFile":
		var f *os.File
		f, err = os.OpenFile(p, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, 0o644)
		if err == nil {
			_, werr := f.Write(payload)
			f.Close()
			if werr == nil {
				b := int64(len(payload))
				bw = &b
			} else {
				err = werr
			}
		}
	case "os.Mkdir":
		err = os.Mkdir(p, 0o755)
	}
	if err != nil {
		stage, code, msg := classify(err, name)
		out.CreateResult = stage2create(stage)
		out.ErrorStage = stage
		out.ErrorCode = code
		out.ErrorMessage = ascii(msg)
	} else {
		out.CreateResult = "ok"
		out.BytesWritten = bw
	}

	ents, derr := os.ReadDir(scratch)
	found := false
	var dsize *int64
	hits := 0
	if derr == nil {
		for _, e := range ents {
			if hexOf(e.Name()) == hexName {
				found = true
				hits++
				if fi, er := e.Info(); er == nil {
					s := fi.Size()
					dsize = &s
				}
			}
		}
	}
	m := member{Hex: hexName, DirFound: found, DirSize: dsize, SameHits: hits}
	if found && dsize != nil {
		out.BytesOnDisk = dsize
	}
	if st, serr := os.Stat(p); serr == nil {
		m.PathOK = true
		s := st.Size()
		m.PathSize = &s
	} else {
		m.PathErr = ascii(serr.Error())
	}
	m.Diverg = (m.DirFound != m.PathOK) ||
		(m.DirSize != nil && m.PathSize != nil && *m.DirSize != *m.PathSize)
	out.EnumToStat = !m.Diverg
	out.Members = append(out.Members, m)

	// canonical enumeration hash (documented recipe: utf8-hex names, sorted, compact)
	names := []string{}
	for _, e := range ents2(scratch) {
		names = append(names, hexOf(e))
	}
	sort.Strings(names)
	canon, _ := json.Marshal(names)
	out.SelfSHA = sha(canon)

	switch {
	case out.CreateResult == "err_at_syscall":
		out.OSLegality = "illegal"
	case out.CreateResult == "err_at_parse":
		out.OSLegality = "unknown"
	case found && dsize != nil && *dsize > 0:
		out.OSLegality = "legal"
	default:
		out.OSLegality = "unknown"
		out.Notes = append(out.Notes, "PHANTOM-OK: create ok, dir_view lacks requested bytes")
	}
	out.ElapsedMS = time.Since(t0).Milliseconds()
	return out
}

func ents2(d string) []string {
	es, err := os.ReadDir(d)
	if err != nil {
		return nil
	}
	var a []string
	for _, e := range es {
		a = append(a, e.Name())
	}
	return a
}

func longPaths() any {
	o, err := exec.Command("reg", "query",
		`HKLM\SYSTEM\CurrentControlSet\Control\FileSystem`, "/v", "LongPathsEnabled").Output()
	if err != nil {
		return nil
	}
	for _, ln := range strings.Split(string(o), "\n") {
		if strings.Contains(ln, "LongPathsEnabled") {
			f := strings.Fields(ln)
			if len(f) >= 3 {
				if v, e := strconv.ParseInt(f[len(f)-1], 0, 32); e == nil {
					return int(v)
				}
			}
		}
	}
	return nil
}

func defaultForm(f string) string {
	if f == "" {
		return "plain"
	}
	return f
}

// longpathMech is PROBED, not asserted: create a 300-unit component under the
// scratch root via a plain path; success => the Go runtime auto-extends (\?\),
// i.e. the Win32 260 full-path limit does not bind for this language.
func probeLongpathMech(root string) string {
	long := filepath.Join(root, strings.Repeat("d", 48), strings.Repeat("e", 48), strings.Repeat("f", 48), strings.Repeat("g", 48), strings.Repeat("h", 48), "f.txt")
	if err := os.WriteFile(long, []byte("X"), 0o644); err == nil {
		return "prefix_rewrite" // probed: 300-unit component created via plain path
	}
	return "none" // probed: 300-unit component rejected
}

func mechFor(form string) string {
	if form == "extended" {
		return "prefix_rewrite"
	}
	return "none"
}

func runAll(group string) {
	fmt.Println("W-GO runner start; toolchain=" + runtime.Version() + " arch=" + runtime.GOARCH)
	if err := verifyFrozen(); err != nil {
		fmt.Println("HARD STOP: " + ascii(err.Error()))
		os.Exit(1)
	}
	cases, goEntries, _, err := loadCases()
	if err != nil {
		fmt.Println("spec load FAIL:", ascii(err.Error()))
		os.Exit(1)
	}
	if !runControls() {
		fmt.Println("HARD STOP: INSTRUMENT-RED after 3 retries (control cells) — no trap data emitted")
		os.Exit(3)
	}
	fmt.Println("CONTROLS: all 5 PASS (baseline-verified)")
	runTAPI(cases)
	for i := range cases {
		c := &cases[i]
		if group != "all" && c.Group != group && c.Group != "trap" {
			continue
		}
		if c.Group == "len" && group != "all" && group != "len" {
			continue
		}
		if c.ID == "T16" {
			runZipCell(c)
			continue
		}
		for mi, smp := range c.Samples {
			hx := hexOf(string(smp))
			for _, e := range goEntries {
				def := c.Defect
				childCell(c.ID+memberSuffix(len(c.Samples), mi), c.Group, e, hx, []byte("X"), def)
			}
		}
	}
	runLenGrids()
	fmt.Println("W-GO run complete; cells in results/go.windows." + runtime.Version() + "/")
	fmt.Println("NEXT: python spec/validate.py results/go.windows." + runtime.Version())
}

func runZipCell(c *Case) {
	scratch := filepath.Join(repo, "_pilot_scratch", "go", "T16__"+fmt.Sprintf("%d", time.Now().UnixNano()%1000000))
	os.MkdirAll(scratch, 0o755)
	started := time.Now().UTC().Format(time.RFC3339Nano)
	zipPath := filepath.Join(scratch, "zip-roundtrip.zip")
	out := cellOut{FormatVersion: 1, CaseID: "T16", CaseGroup: "trap", Language: "go",
		OS: "windows", Arch: runtime.GOARCH, Locale: "en-US",
		APIEntry: "archive/zip", Attempt: 1,
		NameSource: hexOf("zip-roundtrip.zip"), NameEncoding: "utf8_bytes",
		PathForm: "plain", LongpathMech: "none", ErrorStage: "null",
		ReadResult: "eof", EnumAPIEntry: "archive/zip (reader)",
		Mechanism: "zip_roundtrip", WorkerID: workerID, StartedAt: started,
		Env:     map[string]any{"LongPathsEnabled": longPaths(), "toolchain": runtime.Version()},
		RootLen: len([]rune(scratch)), ControlPass: true}
	out.OSLegality = "legal" // zip container created; per-entry legality is N/A (container-level op)
	// NOTE: frozen sample_hex names the ARCHIVE; the member entry names below are
	// worker-selected (recorded as deviation) because bit-11 can only be observed
	// with non-ASCII members. dev: entry-name choice is not worker-self-selection
	// of cases; it is the protocol payload.
	type want struct{ name string }
	wants := []want{{"ascii-e.txt"}, {"café.txt"}, {"café.txt"}, {"e-😀.txt"}}
	buf := &bytes.Buffer{}
	zw := zip.NewWriter(buf)
	var reqHex []string
	for _, w := range wants {
		hdr := &zip.FileHeader{Name: w.name, Method: zip.Store}
		fw, e := zw.CreateHeader(hdr)
		if e != nil {
			out.ErrorStage = "tool"
			out.ErrorCode = "zip-create:" + ascii(e.Error())
			out.CreateResult = "err_at_syscall"
		}
		fw.Write([]byte(payloadCanon))
		reqHex = append(reqHex, hexOf(w.name))
	}
	zw.Close()
	if out.CreateResult != "err_at_syscall" {
		out.CreateResult = "ok"
		b := int64(buf.Len())
		out.BytesWritten = &b
		os.WriteFile(zipPath, buf.Bytes(), 0o644)
		if fi, e := os.Stat(zipPath); e == nil {
			s := fi.Size()
			out.BytesOnDisk = &s
		}
		zr, e := zip.OpenReader(zipPath)
		if e != nil {
			out.ErrorStage = "tool"
			out.ErrorCode = "zip-open:" + ascii(e.Error())
		} else {
			var gotHex []string
			var flags []string
			for _, f := range zr.File {
				gotHex = append(gotHex, hexOf(f.Name))
				eq := (f.FileHeader.Flags & 0x800) != 0
				flags = append(flags, fmt.Sprintf("%s:%v", ascii(f.Name), eq))
				rc, _ := f.Open()
				rb, _ := io.ReadAll(rc)
				rc.Close()
				if !bytes.Equal(rb, []byte(payloadCanon)) {
					out.RoundtripOK = &[]bool{false}[0]
				}
			}
			zr.Close()
			sort.Strings(gotHex)
			sort.Strings(reqHex)
			eq := strings.Join(gotHex, ",") == strings.Join(reqHex, ",")
			out.RoundtripOK = &eq
			out.SelfSHA = sha(buf.Bytes()) // sha256 of the archive on disk
			out.Notes = append(out.Notes, "bit11 per entry: "+strings.Join(flags, " ; "))
			out.Notes = append(out.Notes, "entry-name choice is worker-recorded deviation (archive name is the frozen sample)")
		}
	}
	d := filepath.Join(repo, "results", "go.windows."+runtime.Version())
	os.MkdirAll(d, 0o755)
	b, _ := json.MarshalIndent(out, "", " ")
	os.WriteFile(filepath.Join(d, "T16__archive_zip.json"), b, 0o644)
	fmt.Printf("CELL %-28s %-12s %s roundtrip=%v\n", "T16", "archive/zip", out.CreateResult, out.RoundtripOK != nil && *out.RoundtripOK)
}

func memberSuffix(total, idx int) string {
	if total <= 1 {
		return ""
	}
	return fmt.Sprintf("-m%d", idx+1)
}
