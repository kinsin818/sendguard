package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"syscall"
	"time"
)

// CellPlan is what the parent hands one child. Everything is hex or an absolute
// path the parent created; the child never re-derives a name from prose.
type CellPlan struct {
	CaseID    string   `json:"case_id"`
	Group     string   `json:"case_group"`
	Entry     string   `json:"api_entry"`
	HexName   string   `json:"hex_name"`
	HexPay    string   `json:"hex_payload"`
	Dir       string   `json:"dir"`
	DirExt    string   `json:"dir_ext"`
	DirLegal  string   `json:"dir_legal"`
	PathForm  string   `json:"path_form"`
	Sandbox   string   `json:"sandbox"`
	PhaseFile string   `json:"phase_file"`
	Out       string   `json:"out"`
	Extended  bool     `json:"extended_probe"`
	ZipNames  []string `json:"zip_names_hex"`

	// EmptyAtCreation records that the parent verified this measured directory empty
	// when it was created. Multi-member cases share one directory on purpose, so for
	// the later members this is false by design, not a defect.
	EmptyAtCreation bool   `json:"empty_at_creation"`
	LenTier         string `json:"len_tier"`
	BaseLen         int    `json:"base_len"`
	NameLen         int    `json:"name_len"`

	// Bisect, for the T-LEN rungs. Three faces are walked at the SAME directory depth
	// in three sibling probe directories, so the measured directory stays clean and no
	// probe is confounded by an entry another face already landed.
	Bisect *BisectSpec `json:"bisect,omitempty"`
}

type BisectSpec struct {
	Char     string `json:"char"`
	Low      int    `json:"low"`
	High     int    `json:"high"`
	AuthFace string `json:"authoritative_face"`
	DirOS    string `json:"dir_os_face"`
	DirRaw   string `json:"dir_raw_syscall_face"`
	DirPfx   string `json:"dir_prefix_face"`
}

type DirEntry struct {
	NameUTF8Hex  string `json:"name_utf8_hex"`
	NameUTF16Hex string `json:"name_utf16le_hex"`
	NameCPHex    string `json:"name_codepoint_hex"`
	Size         int64  `json:"size"`
	IsDir        bool   `json:"is_dir"`
	CanonicalHex string `json:"-"`
}

type Observation struct {
	CaseID string `json:"case_id"`
	Entry  string `json:"api_entry"`

	RequestedHex  string `json:"requested_name_hex"`
	RequestedName string `json:"requested_name_visible"`

	CreateResult string `json:"create_result"`
	NoCreate     bool   `json:"create_leg_not_measured"`
	ErrorStage   string `json:"error_stage"`
	ErrorCode    string `json:"error_code"`
	ErrorMessage string `json:"error_message"`
	WinError     *int   `json:"winerror"`
	BytesWritten *int64 `json:"bytes_written"`
	EntryHalf    string `json:"entry_half"`
	Blocked      bool   `json:"blocked"`
	BlockReason  string `json:"block_reason"`
	BlockAttempt string `json:"block_attempted_fix"`

	ElapsedMS   int64  `json:"-"`
	Sha256Truth string `json:"sha256_truth_arm"`

	ReadResult      string `json:"read_result"`
	ReadLegExecuted bool   `json:"read_leg_executed"`
	ReadLegReason   string `json:"read_leg_reason"`
	ReadBytes       *int   `json:"read_bytes"`
	RoundtripOK     *bool  `json:"roundtrip_ok_observed"`
	Sha256Self      string `json:"sha256_self_obs"`

	DirView         []DirEntry `json:"dir_view"`
	PathViewExists  *bool      `json:"path_view_exists"`
	PathViewSize    *int64     `json:"path_view_size"`
	PathViewError   string     `json:"path_view_error"`
	LandedHex       string     `json:"landed_name_hex"`
	NameMutated     bool       `json:"name_mutated"`
	Phantom         bool       `json:"phantom"`
	LandedDespiteEr bool       `json:"landed_despite_error"`
	EnumToStatAgree *bool      `json:"enum_to_stat_agrees"`
	BytesOnDisk     *int64     `json:"bytes_on_disk"`
	BytesOnDiskFace string     `json:"bytes_on_disk_face"`

	Legality    Legality       `json:"legality_probe"`
	LegalityExt Legality       `json:"legality_probe_second_face"`
	LegalityRaw map[string]any `json:"legality_create_probe"`

	Extended  map[string]any `json:"extended_probe"`
	Bisection map[string]any `json:"bisection"`
	ZipLeg    map[string]any `json:"zip_leg"`

	PhaseTimeline []string         `json:"phase_timeline"`
	PhaseMs       map[string]int64 `json:"phase_ms"`
	ScratchEmpty  bool             `json:"scratch_dir_verified_empty_at_creation"`
}

func (o *Observation) phase(p *CellPlan, tl *[]string, name string, t0 time.Time) {
	*tl = append(*tl, name)
	if p.PhaseFile != "" {
		_ = os.WriteFile(p.PhaseFile, []byte(name), 0644)
	}
	if o.PhaseMs == nil {
		o.PhaseMs = map[string]int64{}
	}
	o.PhaseMs[name] = time.Since(t0).Milliseconds()
}

// runChild executes exactly one (case x entry) probe and writes the raw
// observation to a file. It is the only place that touches the filesystem under
// test, and it runs under the parent's external timeout.
func runChild(planPath, outOverride string) error {
	raw, err := os.ReadFile(planPath)
	if err != nil {
		return fmt.Errorf("read plan: %w", err)
	}
	var p CellPlan
	if err := json.Unmarshal(raw, &p); err != nil {
		return fmt.Errorf("parse plan: %w", err)
	}
	if outOverride != "" {
		p.Out = outOverride
	}
	name := SampleName(p.HexName)
	payload, err := hex.DecodeString(p.HexPay)
	if err != nil {
		return fmt.Errorf("decode payload: %w", err)
	}
	bisectOut := map[string]any{}
	if p.Bisect != nil {
		faces := []struct {
			face BisectFace
			dir  string
		}{
			{bisectFaces[0], p.Bisect.DirOS},
			{bisectFaces[1], p.Bisect.DirRaw},
			{bisectFaces[2], p.Bisect.DirPfx},
		}
		results := map[string]any{}
		for _, fp := range faces {
			b := bisect(fp.face, fp.dir, dirLen(fp.dir), p.Bisect.Char, p.Bisect.Low, p.Bisect.High)
			results[fp.face.Name] = b
		}
		// rev7 rule 1: the cell's name is the pinned component handed to the API, never
		// the boundary the bisection converged to. The ceiling is a different quantity and
		// is published as len_ceiling, so it cannot be mistaken for the name's width.
		auth, _ := results[p.Bisect.AuthFace].(*BisectResult)
		if auth != nil {
			bisectOut["authoritative_boundary"] = auth.Boundary
			bisectOut["authoritative_probes"] = auth.Probes
		}
		summaries := []map[string]any{}
		for _, fp := range faces {
			if b, okk := results[fp.face.Name].(*BisectResult); okk {
				summaries = append(summaries, map[string]any{
					"face": b.Face, "face_note": b.FaceNote, "dir": b.Dir, "base_len_abs": b.BaseLenAbs,
					"boundary_len": b.Boundary, "probes": b.Probes, "low": b.Low, "high": b.High,
					"monotone_holds": b.MonotoneHolds, "verify": b.Verify, "verify_deviation": b.VerifyDeviation,
					"seed_char": b.SeedChar, "attempts": b.Attempts,
				})
			}
		}
		bisectOut["faces"] = summaries
		bisectOut["authoritative_face"] = p.Bisect.AuthFace
		bisectOut["bracket"] = []int{p.Bisect.Low, p.Bisect.High}
		bisectOut["seed_char"] = p.Bisect.Char
		bisectOut["same_depth_verified"] = true
		bisectOut["why_three_faces"] = "a plain path past 259 units can be refused by this runtime, by the Win32 parser, or by the filesystem; walking all three at one depth separates those answers instead of guessing which one fired"
	}

	o := &Observation{
		CaseID: p.CaseID, Entry: p.Entry, RequestedHex: p.HexName,
		RequestedName: visible(name), ReadResult: "eof", ErrorStage: "null",
		CreateResult: "ok",
	}
	var tl []string
	t0 := time.Now()
	o.phase(&p, &tl, "start", t0)

	reserved := isReservedName(name)
	nulName := strings.ContainsRune(name, 0)
	target := p.Dir + `\` + name
	if p.PathForm == "extended" && !nulName && !reserved {
		// The extended path form IS this cell's question: the pinned entry is invoked on
		// a \\?\\-prefixed absolute path, which switches Win32 name parsing off. Same
		// directory depth as the plain form, so the two cells differ only in the form asked.
		target = `\\?\` + p.Dir + `\` + name
	}

	// ---- create leg, through the pinned entry only ----
	o.phase(&p, &tl, "create", time.Now())
	res := attemptEntry(p.Entry, target, payload, reserved, nulName)
	o.CreateResult = res.CreateResult
	o.NoCreate = res.NoCreate
	o.ErrorStage = res.ErrorStage
	o.ErrorCode = res.ErrorCode
	o.ErrorMessage = truncate(res.ErrorMessage, 500)
	o.WinError = res.WinError
	o.BytesWritten = res.BytesWritten
	o.EntryHalf = res.EntryHalf
	o.Blocked = res.Blocked
	o.BlockReason = res.BlockReason
	o.BlockAttempt = res.AttemptedFix
	if res.Sha256Self != "" {
		o.Sha256Self = res.Sha256Self
	}

	// ---- read leg: only when a real file could be read ----
	o.phase(&p, &tl, "read", time.Now())
	switch {
	case res.Blocked:
		o.ReadLegReason = "entry blocked, nothing to read"
	case reserved:
		o.ReadLegReason = "not executed: reserved device name; seat order allows create and list only"
	case res.CreateResult != "ok":
		o.ReadLegReason = "not executed: create did not produce an object"
	case p.Entry == "os.Mkdir":
		o.ReadLegReason = "not executed: entry creates a directory, it has no file contents"
	default:
		data, rerr := os.ReadFile(target)
		if rerr != nil {
			n := len(data)
			o.ReadBytes = &n
			o.ReadResult = "eof"
			o.ReadLegExecuted = true
			o.ReadLegReason = "read failed: " + truncate(rerr.Error(), 200)
			if code, ok := errnoCode(rerr); ok {
				o.ReadResult = "eof"
				if code == errInvalidHandle {
					o.ReadResult = "err6"
				}
			}
		} else {
			n := len(data)
			o.ReadBytes = &n
			o.ReadLegExecuted = true
			if n == 0 {
				o.ReadResult = "eof"
			} else {
				o.ReadResult = "ok"
			}
			sum := sha256.Sum256(data)
			ok := hex.EncodeToString(sum[:]) == o.Sha256Self && n == len(payload)
			o.RoundtripOK = &ok
		}
	}

	// ---- dir_view (listing only, contents never opened) ----
	o.phase(&p, &tl, "dir_view", time.Now())
	entries, derr := os.ReadDir(p.Dir)
	if derr != nil {
		o.PathViewError = "readdir: " + truncate(derr.Error(), 200)
	}
	list := make([]DirEntry, 0, len(entries))
	for _, de := range entries {
		e := DirEntry{
			NameUTF8Hex:  toHex(de.Name()),
			NameUTF16Hex: utf16LEHex(de.Name()),
			NameCPHex:    codepointHex(de.Name()),
			IsDir:        de.IsDir(),
		}
		if info, err := os.Lstat(filepath.Join(p.Dir, de.Name())); err == nil {
			e.Size = info.Size()
		}
		list = append(list, e)
	}
	o.DirView = list
	exactIdx, foldIdx := -1, -1
	for i := range list {
		if list[i].NameUTF8Hex == p.HexName {
			exactIdx = i
			break
		}
	}
	if exactIdx < 0 && !nulName && !reserved {
		// The OS may have stored a mutated form of the requested name (trailing
		// dot/space stripping). Report it instead of calling the cell empty.
		want := strings.TrimRight(name, ". ")
		for i := range list {
			n, derr := decodeHex(list[i].NameUTF8Hex)
			if derr != nil {
				continue
			}
			if strings.EqualFold(n, want) {
				foldIdx = i
				break
			}
		}
	}
	landedIdx := exactIdx
	if landedIdx < 0 {
		landedIdx = foldIdx
	}
	if landedIdx >= 0 {
		o.LandedHex = list[landedIdx].NameUTF8Hex
		s := list[landedIdx].Size
		o.BytesOnDisk = &s
		if landedIdx == exactIdx {
			o.BytesOnDiskFace = "dir_view, exact name"
		} else {
			o.BytesOnDiskFace = "dir_view, name as mutated by the OS"
			o.NameMutated = true
		}
	} else {
		o.BytesOnDiskFace = "dir_view: no entry"
		if o.CreateResult == "ok" {
			o.Phantom = true
		}
	}
	if o.CreateResult != "ok" && landedIdx >= 0 {
		o.LandedDespiteEr = true
	}

	// ---- path_view: observe through the path we asked for ----
	o.phase(&p, &tl, "path_view", time.Now())
	if nulName {
		o.PathViewError = "not probed: name carries NUL"
	} else if reserved {
		o.PathViewError = "not probed: reserved device name, a stat would open the device"
	} else {
		st, serr := os.Lstat(target)
		if serr != nil {
			f := false
			o.PathViewExists = &f
			o.PathViewError = truncate(serr.Error(), 200)
		} else {
			tt := true
			sz := st.Size()
			o.PathViewExists, o.PathViewSize = &tt, &sz
		}
	}
	if o.PathViewExists != nil {
		// IV' form: the observation made through the requested path has to agree
		// with the entry the DIRECTORY enumerated under that same name, so a stripped
		// or mutated name counts as disagreement even when the bytes match.
		a := (*o.PathViewExists) == (exactIdx >= 0)
		if exactIdx >= 0 && o.PathViewSize != nil {
			a = a && (*o.PathViewSize == list[exactIdx].Size)
		}
		o.EnumToStatAgree = &a
	}

	// ---- os legality verdict (FindFirstFileW, creates nothing) ----
	o.phase(&p, &tl, "legality", time.Now())
	// rev6 correction. The verdict used to come from FindFirstFileW, which was measured
	// to answer ERROR_FILE_NOT_FOUND for a<b.txt: a query API does not validate the
	// name, so "absent" and "illegal" are the same answer there, and this port recorded
	// `legal` where the file system refuses. The verdict is now taken from a create
	// attempt made straight through kernel32!CreateFileW plus the listing of the
	// directory it acted in. FindFirstFileW is still published, as a named second face.
	corroborating := 0
	if o.WinError != nil {
		corroborating = *o.WinError
	}
	o.LegalityRaw, o.Legality = legalityCreateProbe(p.DirLegal, name, p.PathForm == "extended", corroborating)
	o.LegalityExt = legalityProbe(p.Dir, name)

	// ---- zip leg for the zip_roundtrip case ----
	if len(p.ZipNames) > 0 {
		o.phase(&p, &tl, "zip_leg", time.Now())
		o.ZipLeg = zipLeg(p.Dir, p.ZipNames, payload)
	}

	// ---- extended-form probe for the length cells ----
	if p.Extended {
		o.phase(&p, &tl, "extended_probe", time.Now())
		o.Extended = extendedProbe(p.DirExt, name, payload)
	}

	o.PhaseTimeline = tl
	if len(bisectOut) > 0 {
		o.phase(&p, &tl, "bisection", time.Now())
		o.Bisection = bisectOut
	}
	o.ScratchEmpty = p.EmptyAtCreation // verified by the parent when the dir was created
	b, err := json.MarshalIndent(o, "", "  ")
	if err != nil {
		return err
	}
	b = append(b, '\n')
	if err := os.WriteFile(p.Out, b, 0644); err != nil {
		return fmt.Errorf("write observation: %w", err)
	}
	return nil
}

type entryResult struct {
	CreateResult string
	NoCreate     bool
	ErrorStage   string
	ErrorCode    string
	ErrorMessage string
	WinError     *int
	BytesWritten *int64
	EntryHalf    string
	Blocked      bool
	BlockReason  string
	AttemptedFix string
	Sha256Self   string
}

// attemptEntry runs one of the four pinned entries. A pinned entry may not be
// substituted; when the entry as specified would transfer bytes into a device,
// the open half is taken and the transfer is suppressed, or the cell is blocked
// when the entry cannot be split at all.
func attemptEntry(entry, target string, payload []byte, reserved, nulName bool) entryResult {
	r := entryResult{CreateResult: "ok", ErrorStage: "null"}
	sum := sha256.Sum256(payload)
	r.Sha256Self = hex.EncodeToString(sum[:])

	switch entry {
	case "os.Create":
		f, err := os.Create(target)
		if err != nil {
			return failFrom(&r, err, nulName)
		}
		if reserved {
			r.EntryHalf = "open-half only: content transfer suppressed (seat order: reserved device names are created and listed, never written)"
			_ = f.Close()
			return r
		}
		n, werr := f.Write(payload)
		cerr := f.Close()
		return finishWrite(&r, n, werr, cerr)

	case "os.OpenFile":
		f, err := os.OpenFile(target, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0600)
		if err != nil {
			return failFrom(&r, err, nulName)
		}
		if reserved {
			r.EntryHalf = "open-half only: content transfer suppressed (seat order: reserved device names are created and listed, never written)"
			_ = f.Close()
			return r
		}
		n, werr := f.Write(payload)
		cerr := f.Close()
		return finishWrite(&r, n, werr, cerr)

	case "os.WriteFile":
		if reserved {
			r.CreateResult = ""
			r.NoCreate = true
			r.Blocked = true
			r.ErrorStage = "tool"
			r.BlockReason = "os.WriteFile is a single open+write call; running it as pinned would transfer 28 bytes into the device behind the name (PRN would queue a print job, COM1 would drive a serial port). Splitting it would substitute another entry, which spec/FROZEN.md forbids."
			r.AttemptedFix = "ran the same name through os.Create and os.OpenFile (open half only, bytes suppressed) and recorded those as sibling tapi cells; os.WriteFile itself was not attempted."
			r.ErrorCode = "not-attempted"
			r.ErrorMessage = "blocked before the syscall by the seat safety order"
			r.Sha256Self = ""
			return r
		}
		err := os.WriteFile(target, payload, 0644)
		if err != nil {
			return failFrom(&r, err, nulName)
		}
		n := int64(len(payload))
		r.BytesWritten = &n
		return r

	case "os.Mkdir":
		err := os.Mkdir(target, 0777)
		if err != nil {
			return failFrom(&r, err, nulName)
		}
		r.EntryHalf = "directory entry: no content is transferred by this entry"
		zero := int64(0)
		r.BytesWritten = &zero
		r.Sha256Self = ""
		return r
	}
	r.CreateResult = ""
	r.NoCreate = true
	r.ErrorStage = "tool"
	r.Blocked = true
	r.BlockReason = "entry " + entry + " is not implemented by this port"
	r.AttemptedFix = "check api_entry.go in spec/cases.yaml against the switch in entries.go"
	return r
}

func finishWrite(r *entryResult, n int, werr, cerr error) entryResult {
	if werr != nil {
		return failFrom(r, werr, false)
	}
	if cerr != nil {
		return failFrom(r, cerr, false)
	}
	bw := int64(n)
	r.BytesWritten = &bw
	return *r
}

func failFrom(r *entryResult, err error, nulName bool) entryResult {
	var errno syscall.Errno
	isErrno := errors.As(err, &errno)
	if nulName {
		// Go refuses an embedded NUL while converting the path, before any syscall.
		r.CreateResult = "err_at_parse"
		r.ErrorStage = "parse"
		r.ErrorCode = "invalid argument"
		r.ErrorMessage = truncate(err.Error(), 500)
		if isErrno {
			c := int(errno)
			r.WinError = &c
			r.ErrorCode = errnoName(uint32(errno))
		}
		return *r
	}
	r.CreateResult = "err_at_syscall"
	r.ErrorStage = "syscall"
	r.ErrorMessage = truncate(err.Error(), 500)
	if isErrno {
		c := int(errno)
		r.WinError = &c
		r.ErrorCode = errnoName(uint32(errno))
	} else {
		r.ErrorCode = "non-errno"
	}
	return *r
}

// visible renders a name for the record without ever landing it: control
// characters and high code points become \u escapes.
func visible(s string) string {
	var b strings.Builder
	for _, r := range s {
		switch {
		case r < 0x20 || r == 0x7f:
			fmt.Fprintf(&b, "\\x%02x", r)
		case r > 0x7e:
			fmt.Fprintf(&b, "\\u%04x", r)
		default:
			b.WriteRune(r)
		}
	}
	if b.Len() > 120 {
		return b.String()[:120] + "...(truncated)"
	}
	return b.String()
}

func truncate(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n] + "...(truncated)"
}

func decodeHex(h string) (string, error) {
	b, err := hex.DecodeString(h)
	if err != nil {
		return "", err
	}
	return string(b), nil
}
