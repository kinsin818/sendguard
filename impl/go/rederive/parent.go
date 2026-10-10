package main

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"sort"
	"strings"
	"time"
)

type pair struct{ K, V string }

type planRow struct {
	Key              string
	CaseID           string
	BaseID           string
	Member           string
	Group            string
	Entry            string
	HexName          string
	MechanismClass   string
	LenTriple        string
	NormalizationDep string
	Locale           string
	Note             string
	Applicable       []string
	SubIdentity      []pair
	Dir              string
	DirExt           string // sibling of Dir, same depth: where the \\?\ probe lands
	Sandbox          string
	MultiMember      bool
	GroupID          string
	DirFirstInGroup  bool
	BaseLen          int
	BaseLenAbs       int
	NameLen          int
	NameUTF16        int
	Tier             string
	Extended         bool
	ScratchPath      string // plan/observation/phase files live in the sandbox, not in the measured dir
	CommandFace      []string
	ChildRC          int
	WallMS           int64
	StdoutFace       string
	StderrFace       string
	TimedOut         bool
	StartedAt        string
	ControlPass      bool
	CleanupFailed    bool
	LongpathMech     string
	ZipNames         []string
	Publish          bool
	PublishReason    string
	Bisect           *BisectSpec
	Packer           string
	Extractor        string
	RollupOver       []string
	DirLegal         string
	DirX             string
	DirY             string
	DirZ             string
	RequiredIdentity string
	Extra            bool
	PathForm         string
	RunStatus        string
	PinWidth         int
	BlindID          int
}

// sandboxRoot is on the same volume as the repo. docs/cleanup-notice.md puts scratch
// under %TEMP%, which on this host is C:; evidence/S00/env-facts-windows-local.json
// records 8dot3 name creation ENABLED on C: and DISABLED on D:, so measuring length
// and enumeration behaviour on C: would not be the volume the project ships from.
const sandboxRoot = `D:\sendguard-run`

const (
	// zipTool names this port's packer and extractor with a version, which
	// spec/cell-identity.md section 6 requires of a zip cell.
	zipTool = "go.archive/zip+go1.23.5"
	// bisectHigh is the rejected anchor of every length bisection: max_component is
	// measured at 255 on this host, so 260 units cannot be accepted by any face.
	bisectHigh = 260
	lenSeed    = "a"
	// The authoritative face is the layer each trap asks about: T17 is the total-path
	// ceiling carried by the Win32 parser, T18 is the component ceiling with that
	// parsing switched off.
	lenAuthFaceT17 = FaceRawPlain
	lenAuthFaceT18 = FacePrefix
)

// defaultLadder is the fallback used only if spec/cells-required.json cannot be read;
// the rungs normally come from that file.
var defaultLadder = []int{78, 120, 200}

// payloadHex is the canonical 28-byte S00 payload (harness/ctrl-baseline.mjs
// PAYLOAD), carried as hex so no cell ever types it out.
var payloadHex = "53454e4447554152442d43414e4f4e2d5041594c4f41442d32303236"

// enforcedTimeoutMS is the externally enforced child timeout this run used; every cell
// records it, because a reading taken under a different ceiling is not the same recipe.
var enforcedTimeoutMS int64 = 5000

func newUUID() string {
	b := make([]byte, 16)
	if _, err := rand.Read(b); err != nil {
		panic(err)
	}
	b[6] = (b[6] & 0x0f) | 0x40
	b[8] = (b[8] & 0x3f) | 0x80
	h := hex.EncodeToString(b)
	return h[0:8] + "-" + h[8:12] + "-" + h[12:16] + "-" + h[16:20] + "-" + h[20:]
}

// buildPlan lays out the question set this port answers:
//
//	22 trap cells (one per frozen member, primary entry os.Create)
//	88 tapi cells (22 members x the 4 pinned api_entry.go entries)
//	 5 ctrl cells (primary entry; expectations only from evidence/S00-ctrl-baseline.md)
//	24 len cells  (T17/T18 x the G1-G4 grid pinned in spec/FROZEN.md, 3 points each)
//
// Blind samples are deliberately not measured here: evidence/S00/blind-map.json
// seals them for the S03 dual-blind audit ("do not gate any judgment"), and the
// landed python denominator (117 = 22+88+5+2) does not contain them.
func buildPlan(spec *FrozenSpec, cases map[string]*CaseDef, ladder []int) []*planRow {
	rows := []*planRow{}
	add := func(r *planRow) { rows = append(rows, r) }

	for _, m := range MemberCases(cases, spec.CaseIDs) {
		if m.Kind == "len" {
			continue
		}
		add(&planRow{
			CaseID: m.CaseID, BaseID: m.BaseID, Member: m.Member, Group: "trap",
			Entry: spec.GoEntries[0], HexName: m.Hex, MechanismClass: classOf(m.Category),
			Locale: m.Locale, Note: m.Note, Applicable: m.Applicable, SubIdentity: []pair{},
			MultiMember: len(cases[m.BaseID].Samples) > 1, Publish: true,
		})
		// spec/cell-identity.md section 6 says a zip round-trip cell must carry packer
		// and extractor as named identity dimensions. That would move it off the
		// required (trap, T16, {}) identity, so both are published: the required cell
		// without them, this extra cell with them.
		if m.CaseID == "T16" {
			add(&planRow{
				CaseID: m.CaseID, BaseID: m.BaseID, Member: m.Member, Group: "trap",
				Entry: spec.GoEntries[0], HexName: m.Hex, MechanismClass: "zip_roundtrip",
				Locale: m.Locale, Note: m.Note, Applicable: m.Applicable,
				SubIdentity: []pair{{"packer", zipTool}, {"extractor", zipTool}},
				Packer:      zipTool, Extractor: zipTool, ZipNames: zipNamesFor(cases, m.CaseID),
				Publish: true,
			})
		}
		for _, e := range spec.GoEntries {
			add(&planRow{
				CaseID: m.CaseID, BaseID: m.BaseID, Member: m.Member, Group: "tapi",
				Entry: e, HexName: m.Hex, MechanismClass: classOf(m.Category),
				Locale: m.Locale, Note: m.Note, Applicable: m.Applicable,
				SubIdentity: []pair{{"api_entry", e}},
				ZipNames:    zipNamesFor(cases, m.CaseID), MultiMember: len(cases[m.BaseID].Samples) > 1,
				Publish: false, PublishReason: "per-member entry cell: published as entry_spread on the primary cell instead of as its own file, because ci/equality.py keys identity on (case_group, case_id, sub_identity) and api_entry is deliberately not part of it - four cells at one identity with different digests is precisely its ambiguous_entries refusal",
			})
		}
	}

	// rev6 pins the five control samples in spec/cases.yaml, so their names and payload
	// come from the spec face, not from this port. Before rev6 five ports invented five
	// names for T-CTRL-CANON and hashed two different payloads under one cell id.
	for _, cc := range spec.Controls {
		hexName := cc.Hex
		if hexName == "" {
			hexName = ctrlFallbackHex(cc.ID)
		}
		add(&planRow{
			CaseID: cc.ID, BaseID: cc.ID, Group: "ctrl", Entry: spec.GoEntries[0],
			HexName: hexName, MechanismClass: ctrlClass(cc.ID), Locale: "en-US",
			Note:       "control cell; sample pinned in spec/cases.yaml control_samples, expectation from evidence/S00-ctrl-baseline.md",
			Applicable: []string{"windows"}, SubIdentity: []pair{}, Publish: true,
			PathForm: "plain",
		})
	}

	// The five sealed blind samples. rev6 requires them; the seal is opened by the
	// contract owner's written instruction, not by this seat deciding to unseal it.
	for _, b := range spec.Blind {
		add(&planRow{
			CaseID: b.CaseID, BaseID: b.CaseID, Group: "blind", Entry: spec.GoEntries[0],
			HexName: b.Hex, MechanismClass: "unknown", Locale: "en-US",
			Note:       "blind sample from " + blindMapRef(spec) + "; blind_id " + itoa(b.ID),
			Applicable: []string{"windows", "macos", "ubuntu"}, SubIdentity: []pair{},
			Publish: true, PathForm: "plain", BlindID: b.ID,
		})
	}

	// rev6 requires twelve length cells: the base ladder {78, 120, 200} crossed with the
	// two path forms, because plain and \?\ are two different questions and path_form is
	// an identity dimension for the len group. Each cell bisects the name length at its
	// own rung and in its own form.
	for _, id := range []string{"T17", "T18"} {
		c := cases[id]
		for _, base := range ladder {
			for _, form := range []string{"plain", "extended"} {
				// rev7: the component is the pinned unit repeated until it is exactly
				// base_len code units, and nothing else. base_len is therefore the width of
				// the name handed to the API, not a directory depth.
				pinned := strings.Repeat(spec.LenFill.Unit(), base)
				sub := []pair{{"base_len", itoa(base)}, {"path_form", form}}
				add(&planRow{
					CaseID: id, BaseID: id, Group: "len", Entry: spec.GoEntries[0],
					HexName: toHex(pinned), PinWidth: base, MechanismClass: "component_length_limit",
					Locale: c.Locale, Note: c.Note + " | base ladder and path forms from spec/cells-required.json",
					Applicable: c.Applicable, BaseLen: base, Extended: true, Publish: true,
					PathForm:    form,
					SubIdentity: sub,
					Bisect:      &BisectSpec{Char: spec.LenFill.Unit(), Low: 1, High: bisectHigh, AuthFace: faceForForm(form)},
				})
			}
		}
	}

	// T-API: one cell per pinned entry, as spec/cells-required.json shapes it. Each
	// runs that entry over the S00 baseline name and carries a roll-up of the entry
	// across all 22 frozen members beside it.
	members := []string{}
	for _, m := range MemberCases(cases, spec.CaseIDs) {
		if m.Kind != "len" {
			members = append(members, m.CaseID)
		}
	}
	for _, e := range spec.GoEntries {
		add(&planRow{
			CaseID: "T-API", BaseID: "T-API", Group: "tapi", Entry: e,
			HexName: toHex("report-2026.txt"), MechanismClass: "unknown",
			Locale: "en-US", Note: "T-API instrument self-check cell (spec/cells-required.json)",
			Applicable: []string{"windows"}, SubIdentity: []pair{{"api_entry", e}},
			Publish: true, RollupOver: members,
		})
	}

	seen := map[string]bool{}
	for _, r := range rows {
		r.Key = r.Group + "/" + r.CaseID + "/" + strings.Join(subFlat(r.SubIdentity), ",")
		if seen[r.Key] {
			panic("plan has two rows with the same identity: " + r.Key)
		}
		seen[r.Key] = true
		t := lenTriple(SampleName(r.HexName))
		r.LenTriple = t.String()
		r.NameUTF16 = t.UTF16
		r.NormalizationDep = normDep(r.MechanismClass)
	}
	sort.Slice(rows, func(i, j int) bool { return rows[i].Key < rows[j].Key })
	return rows
}

// zipNamesFor returns the frozen sample hex the T16 zip leg puts inside the
// archive: the T16 name itself plus both T09 members, so the non-ASCII branch of
// the zip UTF-8 flag is exercised with frozen samples only.
func zipNamesFor(cases map[string]*CaseDef, caseID string) []string {
	if caseID != "T16" {
		return nil
	}
	out := []string{cases["T16"].Samples[0]}
	if t09, ok := cases["T09"]; ok {
		out = append(out, t09.Samples...)
	}
	return out
}

func subFlat(s []pair) []string {
	out := []string{}
	for _, p := range s {
		out = append(out, p.K+"="+p.V)
	}
	return out
}

func itoa(i int) string { return fmt.Sprintf("%d", i) }

func classOf(category string) string {
	switch category {
	case "reserved_device_name", "path_preprocessing_policy", "illegal_char_filter",
		"unicode_normalization", "case_folding", "control_char_handling",
		"bidi_handling", "zero_width_handling", "zip_roundtrip",
		"component_length_limit", "os_legality", "unknown":
		return category
	}
	return "unknown"
}

func ctrlClass(id string) string {
	switch id {
	case "T-CTRL-NAMETOOLONG":
		return "component_length_limit"
	case "T-CTRL-ILLEGAL-CHAR":
		return "illegal_char_filter"
	case "T-CTRL-PARSE":
		return "control_char_handling"
	}
	// T-CTRL-ASCII and T-CTRL-CANON are baseline names: canonical.md §10 has no
	// class meaning "no mechanism involved", so the closed-set word is used.
	return "unknown"
}

func normDep(class string) string {
	switch class {
	case "unicode_normalization", "case_folding":
		return "not-achievable-in-stdlib: canonical NFC/NFD composition needs golang.org/x/text/unicode/norm " +
			"(external module, absent from this machine's module cache), so this port does not compute normal " +
			"forms. The coexistence question is answered from observation instead: the landed name hex is " +
			"compared against both frozen member forms in the same directory (see t09_coexistence). " +
			"deps_direct=0 is therefore a stated choice with a named substitute, not a silent default."
	}
	return "n/a: not a normalisation cell"
}

// runParent drives the grid: one child process per cell, an externally enforced
// timeout, one fresh uuid sandbox per cell, and no deletion anywhere (M19).
func runParent(repo, resDir string, timeoutMS int64, only string) error {
	started := time.Now()
	enforcedTimeoutMS = timeoutMS
	spec, cases, err := LoadSpec(repoFile(repo, "spec/cases.yaml"))
	if err != nil {
		return fmt.Errorf("load frozen spec: %w", err)
	}
	if got := hex.EncodeToString(spec.Payload); got != payloadHex {
		return fmt.Errorf("payload drift: spec says %s", got)
	}
	env := envFacts(repo)
	ladder, req, reqErr := loadRequired(repo)
	if reqErr != nil {
		fmt.Fprintf(os.Stderr, "WARN spec/cells-required.json unreadable (%v); using the documented ladder %v\n", reqErr, ladder)
	}
	rows := buildPlan(spec, cases, ladder)
	annotateRequired(rows, req)
	obs := map[string]*Observation{}
	extra := map[string]map[string]any{}

	if only != "" {
		kept := []*planRow{}
		for _, r := range rows {
			if strings.Contains(r.Key, only) {
				kept = append(kept, r)
			}
		}
		rows = kept
	}
	fmt.Fprintf(os.Stderr, "plan=%d cells | only=%q | sandbox=%s | timeout_ms=%d | runner=%s\n",
		len(rows), only, sandboxRoot, timeoutMS, env.RunnerExe)

	shared := map[string]string{}
	for i, r := range rows {
		if err := prepareSandbox(r, shared); err != nil {
			obs[r.Key] = failedObservation(r, err.Error())
			continue
		}
		o, rc, timedOut, phase, stdoutF, stderrF := spawnChild(r, timeoutMS, env)
		r.ChildRC, r.TimedOut = rc, timedOut
		r.StdoutFace, r.StderrFace = stdoutF, stderrF
		if o == nil {
			o = failedObservation(r, "no observation written; last phase="+phase)
			o.PhaseTimeline = []string{phase}
			if timedOut {
				o.CreateResult = "hang"
				o.ErrorStage = phaseStage(phase)
				o.BlockReason = "child was killed at the " + phase + " phase after " + itoa(int(timeoutMS)) + " ms"
			}
			// canonical.md §5: both readings are printed as-is, so the parent adds its
			// own post-mortem listing next to the child reading that never arrived.
			if entries, err := os.ReadDir(r.Dir); err == nil {
				for _, de := range entries {
					o.DirView = append(o.DirView, DirEntry{NameUTF8Hex: toHex(de.Name()), IsDir: de.IsDir()})
				}
				o.ScratchEmpty = false
				extra[r.Key] = map[string]any{
					"post_kill_dir_view_by_parent": len(o.DirView),
					"post_kill_dir_view_note":      "listed by the parent after the child was killed; contents never opened",
				}
			}
		}
		// a length cell probes the boundary name the bisection found, which is not the
		// placeholder the plan started from: recompute the lengths the cell publishes.
		if o.RequestedHex != "" && o.RequestedHex != r.HexName {
			t := lenTriple(mustDecode(o.RequestedHex))
			r.HexName = o.RequestedHex
			r.LenTriple = t.String()
			r.NameUTF16 = t.UTF16
			r.NameLen = t.UTF16
		}
		obs[r.Key] = o
		if (i+1)%20 == 0 {
			fmt.Fprintf(os.Stderr, "  %d/%d cells run\n", i+1, len(rows))
		}
	}

	// Coexistence: for the multi-member cases the question is whether the sibling
	// frozen names are present in the SAME directory, which the shared sandbox lets
	// this port answer from the dir_view it already took.
	groupRows := map[string][]*planRow{}
	for _, r := range rows {
		groupRows[r.GroupID] = append(groupRows[r.GroupID], r)
	}
	for _, r := range rows {
		if !r.MultiMember || obs[r.Key] == nil {
			continue
		}
		seen := []string{}
		hits := 0
		for _, s := range groupRows[r.GroupID] {
			if s == r || obs[s.Key] == nil || obs[s.Key].LandedHex == "" {
				continue
			}
			for _, d := range obs[r.Key].DirView {
				if d.NameUTF8Hex == obs[s.Key].LandedHex {
					hits++
					seen = append(seen, s.CaseID)
					break
				}
			}
		}
		if extra[r.Key] == nil {
			extra[r.Key] = map[string]any{}
		}
		// A sibling created after this cell wrote cannot appear in this cell own
		// dir_view, so the parent lists the shared directory once more after the whole
		// group has run. Both readings are published: the coexistence answer belongs to
		// the finished directory, not to the moment of writing.
		var post []map[string]any
		if ents, lerr := os.ReadDir(r.Dir); lerr == nil {
			for _, de := range ents {
				e := map[string]any{"name_utf8_hex": toHex(de.Name())}
				if info, serr := os.Stat(filepath.Join(r.Dir, de.Name())); serr == nil {
					e["size"] = info.Size()
				}
				e["is_dir"] = de.IsDir()
				post = append(post, e)
			}
		}
		present := map[string]bool{}
		for _, e := range post {
			present[e["name_utf8_hex"].(string)] = true
		}
		membersNow := []string{}
		for _, s := range groupRows[r.GroupID] {
			if present[s.HexName] {
				membersNow = append(membersNow, s.CaseID)
			}
		}
		extra[r.Key]["coexistence"] = map[string]any{
			"cells_sharing_this_dir":     len(groupRows[r.GroupID]),
			"same_dir_siblings_found":    seen,
			"same_name_hits":             hits,
			"members_in_dir_after_group": membersNow,
			"post_group_dir_view":        post,
			"post_group_enumerator":      "parent process, after every member of the group had run; listing only, contents never opened",
			"dir":                        r.Dir,
			"rule":                       "spec/cases.yaml gives T09 the spec_source NFC/NFD coexistence in one directory; siblings are looked for in this cell own dir_view and in the parent post-group listing",
		}
	}

	// Independent read-back arm: the landed bytes are hashed by a different
	// implementation, so sha256_truth is not the same code that produced sha256_self.
	for _, r := range rows {
		o := obs[r.Key]
		if o == nil {
			continue
		}
		t, ok := pythonReadback(r, o, env)
		if extra[r.Key] == nil {
			extra[r.Key] = map[string]any{}
		}
		for k, v := range t {
			extra[r.Key][k] = v
		}
		if ok {
			o.Sha256Truth = strOf(t, "sha256")
		}
	}

	controls := evalControls(rows, obs)
	allControlsPass := true
	for _, cc := range controls {
		if !cc.Pass {
			allControlsPass = false
		}
	}
	perCasePass := map[string]bool{}
	for _, cc := range controls {
		perCasePass[cc.ID] = cc.Pass
	}
	for _, r := range rows {
		r.LongpathMech = longpathMech(r, obs[r.Key], env)
		r.ControlPass = allControlsPass
		if r.Group == "ctrl" {
			r.ControlPass = perCasePass[r.CaseID]
		}
	}

	if err := os.MkdirAll(resDir, 0755); err != nil {
		return fmt.Errorf("mkdir results dir: %w", err)
	}
	published := []*planRow{}
	for _, r := range rows {
		if r.Publish {
			published = append(published, r)
		}
	}
	tapiSpread(rows, obs, extra, spec)
	cells := buildCells(spec, cases, env, published, obs, extra, controls, allControlsPass)
	names := map[string]bool{}
	written := 0
	for _, c := range cells {
		fn := c.FileName()
		if names[fn] {
			return fmt.Errorf("two cells map to one path: %s", fn)
		}
		names[fn] = true
		if err := os.WriteFile(filepath.Join(resDir, fn), c.Bytes(), 0644); err != nil {
			return fmt.Errorf("write cell %s: %w", fn, err)
		}
		written++
	}
	if rb, err := os.ReadFile(env.RunnerExe); err == nil {
		env.ExeSHAAfter = sha256Hex(rb)
	}

	manifest := map[string]any{
		"cells_planned":         len(rows),
		"cells_written":         written,
		"controls_pass":         allControlsPass,
		"control_detail":        controls,
		"run_started_at":        env.RunStartedAt,
		"run_finished_at":       time.Now().UTC().Format(time.RFC3339Nano),
		"wall_ms":               time.Since(started).Milliseconds(),
		"sg_exe_sha256_before":  env.ExeSHA,
		"sg_exe_sha256_after":   env.ExeSHAAfter,
		"exe_face_stable":       env.ExeSHA == env.ExeSHAAfter,
		"sandbox_root":          sandboxRoot,
		"sandbox_dirs_retained": written,
		"cleanup_attempted":     false,
		"timeout_enforced_ms":   timeoutMS,
		"env":                   env,
	}
	mb, _ := json.MarshalIndent(manifest, "", " ")
	mb = append(mb, '\n')
	// Instrument output never lands in results/ (spec/cell-identity.md §3).
	mp := filepath.Join(repo, "evidence", "S02", "go-run-manifest.json")
	if err := os.WriteFile(mp, mb, 0644); err != nil {
		fmt.Fprintf(os.Stderr, "manifest write failed: %v\n", err)
	}
	fmt.Printf("cells_planned=%d cells_written=%d controls_pass=%v wall_ms=%d manifest=%s\n",
		len(rows), written, allControlsPass, time.Since(started).Milliseconds(), mp)
	return nil
}

// rung returns the measured directory and its same-depth siblings for a row. The
// probe directories are one character wide like the measured one, so every directory
// under the uuid sandbox has an identical absolute length and a bisection in one of
// them is the same measurement at the same rung.
func rung(sandbox, letter string, baseLen int) string {
	d := filepath.Join(sandbox, letter)
	if baseLen > 0 {
		d = filepath.Join(d, strings.Repeat("b", baseLen))
	}
	return d
}

func prepareSandbox(r *planRow, shared map[string]string) error {
	key := r.BaseID + "|" + r.Entry + "|" + r.Group
	r.GroupID = key
	if sb, ok := shared[key]; ok && r.MultiMember {
		// Multi-member cases (T09/T14/T19) share one directory on purpose: whether the
		// members coexist in the SAME directory is the frozen question, and two separate
		// sandboxes can never answer it.
		r.Sandbox = sb
		r.ScratchPath = sb
		r.Dir = rung(sb, "t", r.BaseLen)
		r.DirExt = rung(sb, "e", r.BaseLen)
		r.DirLegal = rung(sb, "l", r.BaseLen)
		r.BaseLenAbs = dirLen(r.Dir)
		return nil
	}
	r.Sandbox = filepath.Join(sandboxRoot, newUUID())
	r.ScratchPath = r.Sandbox // plan/phase/observation live here, never in a measured dir
	depth := 0
	if r.PinWidth == 0 {
		depth = r.BaseLen
	}
	r.Dir = rung(r.Sandbox, "t", depth)
	r.DirExt = rung(r.Sandbox, "e", depth)
	r.DirLegal = rung(r.Sandbox, "l", depth)
	if r.Bisect != nil {
		r.DirX = rung(r.Sandbox, "x", depth)
		r.DirY = rung(r.Sandbox, "y", depth)
		r.DirZ = rung(r.Sandbox, "z", depth)
	}
	for _, d := range []string{r.Dir, r.DirExt, r.DirLegal, r.DirX, r.DirY, r.DirZ} {
		if d == "" {
			continue
		}
		if err := os.MkdirAll(d, 0755); err != nil {
			return fmt.Errorf("mkdir %s: %w", d, err)
		}
		ents, err := os.ReadDir(d)
		if err != nil {
			return fmt.Errorf("verify empty %s: %w", d, err)
		}
		if len(ents) != 0 {
			r.CleanupFailed = true
			return fmt.Errorf("fresh uuid sandbox dir was not empty (%d entries): %s", len(ents), d)
		}
	}
	// Every directory this cell may touch must be the same length, or a bisection in a
	// sibling would not be a measurement at the rung the cell claims.
	n := dirLen(r.Dir)
	for _, d := range []string{r.DirExt, r.DirLegal, r.DirX, r.DirY, r.DirZ} {
		if d != "" && dirLen(d) != n {
			return fmt.Errorf("probe dir %s is %d units, measured dir is %d", d, dirLen(d), n)
		}
	}
	r.BaseLenAbs = n
	shared[key] = r.Sandbox
	return nil
}

func spawnChild(r *planRow, timeoutMS int64, env *envFace) (*Observation, int, bool, string, string, string) {
	if r.Bisect != nil {
		r.Bisect.DirOS = r.DirX
		r.Bisect.DirRaw = r.DirY
		r.Bisect.DirPfx = r.DirZ
	}
	planPath := filepath.Join(r.ScratchPath, "_plan.json")
	outPath := filepath.Join(r.ScratchPath, "_observation.json")
	phasePath := filepath.Join(r.ScratchPath, "_phase.txt")
	r.StartedAt = time.Now().UTC().Format(time.RFC3339Nano)
	p := CellPlan{
		CaseID: r.CaseID, Group: r.Group, Entry: r.Entry, HexName: r.HexName,
		HexPay: payloadHex, Dir: r.Dir, Sandbox: r.Sandbox, PhaseFile: phasePath,
		Out: outPath, Extended: r.Extended, LenTier: r.Tier, BaseLen: r.BaseLen, NameLen: r.NameLen,
		ZipNames: r.ZipNames, DirExt: r.DirExt, DirLegal: r.DirLegal, PathForm: r.PathForm,
		EmptyAtCreation: r.DirFirstInGroup,
		Bisect:          r.Bisect,
	}
	b, _ := json.Marshal(&p)
	if err := os.WriteFile(planPath, b, 0644); err != nil {
		return nil, -1, false, "plan-write", "", err.Error()
	}
	exe := env.RunnerExe
	ctx, cancel := context.WithTimeout(context.Background(), time.Duration(timeoutMS)*time.Millisecond)
	defer cancel()
	cmd := exec.CommandContext(ctx, exe, "cell", "--plan", planPath)
	var stdout, stderr strings.Builder
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr
	t0 := time.Now()
	_ = cmd.Run()
	r.WallMS = time.Since(t0).Milliseconds()
	r.CommandFace = []string{exe, "cell", "--plan", planPath}
	timedOut := ctx.Err() == context.DeadlineExceeded
	rc := 0
	if cmd.ProcessState != nil {
		rc = cmd.ProcessState.ExitCode()
	}
	phase := ""
	if pb, err := os.ReadFile(phasePath); err == nil {
		phase = strings.TrimSpace(string(pb))
	}
	raw, rerr := os.ReadFile(outPath)
	if rerr != nil {
		return nil, rc, timedOut, phase, truncate(stdout.String(), 200), truncate(stderr.String(), 400)
	}
	var o Observation
	if err := json.Unmarshal(raw, &o); err != nil {
		return nil, rc, timedOut, "observation-parse", truncate(stdout.String(), 200), truncate(err.Error(), 300)
	}
	return &o, rc, timedOut, phase, truncate(stdout.String(), 200), truncate(stderr.String(), 400)
}

func phaseStage(phase string) string {
	switch phase {
	case "create", "read", "dir_view", "path_view":
		return "syscall"
	case "legality", "extended_probe":
		return "fs"
	}
	return "tool"
}

func failedObservation(r *planRow, why string) *Observation {
	return &Observation{
		CaseID: r.CaseID, Entry: r.Entry, RequestedHex: r.HexName,
		RequestedName: visible(SampleName(r.HexName)),
		CreateResult:  "", NoCreate: true,
		ErrorStage: "tool", ErrorCode: "instrument-failure", ErrorMessage: truncate(why, 400),
		ReadResult: "eof", ReadLegReason: "not executed: " + truncate(why, 200),
		BytesOnDiskFace: "instrument failure",
		Legality:        Legality{Verdict: "unknown", Probe: "none", Note: "not probed"},
		Blocked:         true, BlockReason: "instrument could not produce an observation: " + truncate(why, 200),
		BlockAttempt: "re-checked the sandbox and the child phase file; see evidence/S02/go-selfcheck.md",
	}
}

// pythonReadback hashes the landed bytes with a different implementation, opening
// the entry as the DIRECTORY enumerated it (never the requested path), so it can
// not reach a device namespace by name.
//
// The arm is tried in the plain form first. On this host a plain path longer than
// 259 units makes Python's listdir/open raise WinError 3 even though os.path.isdir
// answers True, so a length-shaped failure is retried through the \?\ form and both
// attempts are published: the limitation belongs to the read-back instrument, not
// to the Go behaviour under test, and it must be visible rather than silent.
func pythonReadback(r *planRow, o *Observation, env *envFace) (map[string]any, bool) {
	res := map[string]any{"arm": "python open('rb') + hashlib.sha256", "exe": env.PythonExe}
	defer func() { o.Sha256Truth = strOf(res, "sha256") }()
	if o.LandedHex == "" {
		res["attempted"] = false
		res["note"] = "nothing landed; there are no bytes for a second instrument to hash"
		return res, false
	}
	if isReservedName(mustDecode(o.LandedHex)) {
		res["attempted"] = false
		res["note"] = "not attempted: the landed name is a reserved device name"
		return res, false
	}
	if env.PythonExe == "" {
		res["attempted"] = false
		res["note"] = "not-obtainable-here: no python interpreter resolved on this host"
		return res, false
	}
	attempts := []map[string]any{}
	for _, face := range []string{"plain", "extended"} {
		if face == "extended" {
			alreadyTried := false
			for _, a := range attempts {
				if a["ok"] == true {
					alreadyTried = true
				}
			}
			if alreadyTried {
				break
			}
		}
		a := armOnce(env, r.Dir, o.LandedHex, face)
		attempts = append(attempts, a)
		if a["ok"] == true {
			res["attempted"] = true
			res["ok"] = true
			res["face_used"] = face
			res["sha256"] = a["sha256"]
			res["bytes"] = a["bytes"]
			res["attempts"] = attempts
			return res, true
		}
	}
	res["attempted"] = true
	res["ok"] = false
	res["attempts"] = attempts
	res["note"] = "the independent read-back arm could not open the landed entry in either path form"
	return res, false
}

func armOnce(env *envFace, dir, landedHex, face string) map[string]any {
	prefix := ""
	if face == "extended" {
		prefix = string([]byte{0x5c, 0x5c, 0x3f, 0x5c})
	}
	script := "import hashlib,sys\n" +
		"name=bytes.fromhex(sys.argv[1]).decode('utf-8','surrogateescape')\n" +
		"data=open(sys.argv[3]+sys.argv[2]+chr(92)+name,'rb').read()\n" +
		"print('sha256='+hashlib.sha256(data).hexdigest())\n" +
		"print('bytes='+str(len(data)))\n"
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	cmd := exec.CommandContext(ctx, env.PythonExe, "-c", script, landedHex, dir, prefix)
	var es strings.Builder
	cmd.Stderr = &es
	out, err := cmd.Output()
	rc := -1
	if cmd.ProcessState != nil {
		rc = cmd.ProcessState.ExitCode()
	}
	a := map[string]any{
		"face": face, "rc": rc,
		"command": []string{env.PythonExe, "-c", "<4-line readback script>", "<landed-name-hex>", dir, prefix},
	}
	lines := strings.Split(strings.TrimSpace(string(out)), "\n")
	for i := range lines {
		lines[i] = strings.TrimSpace(lines[i])
	}
	if rc != 0 || len(lines) < 2 || !strings.HasPrefix(lines[0], "sha256=") {
		a["ok"] = false
		a["error"] = asciiOnly(truncate(errStr(err)+" | "+es.String(), 400))
		return a
	}
	a["ok"] = true
	a["sha256"] = strings.TrimPrefix(lines[0], "sha256=")
	a["bytes"] = strings.TrimPrefix(lines[1], "bytes=")
	return a
}

func errStr(err error) string {
	if err == nil {
		return ""
	}
	return err.Error()
}

func mustDecode(h string) string {
	s, err := decodeHex(h)
	if err != nil {
		return ""
	}
	return s
}

func strOf(m map[string]any, k string) string {
	if v, ok := m[k].(string); ok {
		return v
	}
	return ""
}

// longpathMechanism is decided from evidence this port collected, not inferred from one
// layer's answer:
//
//	none           -> the path stayed inside the 259-unit ceiling, or the raw OS entry
//	                 accepted the same length this runtime did, so nothing was rewritten
//	prefix_rewrite-> this runtime accepted a plain path that kernel32!CreateFileW itself
//	                 refused at the same directory depth
//	unknown        -> the facts needed to decide were not both available
//
// The round before this one claimed prefix_rewrite from "a long plain path worked while
// LongPathsEnabled=0". The three-face bisection falsified that inference on this host -
// the raw entry accepted too - so that claim is withdrawn here instead of carried forward.
func longpathMech(r *planRow, o *Observation, env *envFace) string {
	if o == nil {
		return "unknown"
	}
	total := r.BaseLenAbs + 1 + r.NameUTF16
	if total <= 259 {
		return "none"
	}
	if o.CreateResult != "ok" {
		return "unknown"
	}
	raw, ok := faceBoundary(o, FaceRawPlain)
	if !ok {
		if ext, _ := o.Extended["ok"].(bool); ext {
			return "none"
		}
		return "unknown"
	}
	if raw >= r.NameUTF16 {
		return "none"
	}
	return "prefix_rewrite"
}

// faceBoundary reads one face's boundary out of a child observation.
func faceBoundary(o *Observation, name string) (int, bool) {
	if o == nil || o.Bisection == nil {
		return 0, false
	}
	faces, _ := o.Bisection["faces"].([]any)
	for _, e := range faces {
		m, _ := e.(map[string]any)
		if m == nil || m["face"] != name {
			continue
		}
		if b, ok := m["boundary_len"].(float64); ok {
			return int(b), true
		}
	}
	return 0, false
}

func envFacts(repo string) *envFace {
	e := &envFace{OS: "windows", Arch: runtime.GOARCH, SandboxRoot: sandboxRoot}
	e.GoExe = resolvedGo()
	e.GoVersion = goVersionString(e.GoExe)
	e.OSVersion = windowsVersion()
	e.Locale = localeFace()
	e.LongPaths = registryLongPaths()
	e.Volume = volumeMaxComponent(`D:\`)
	e.SpecSHA, e.SpecSHAOnDisk = specSHA256s(repo)
	e.FreezeRevision = "not-read"
	if sp, _, err := LoadSpec(repoFile(repo, "spec/cases.yaml")); err == nil {
		e.FreezeRevision = sp.FreezeRevision
	}
	e.RunStartedAt = time.Now().UTC().Format(time.RFC3339Nano)
	e.PythonExe = resolvePython()
	if exe, err := os.Executable(); err == nil {
		e.RunnerExe = exe
		if b, err := os.ReadFile(exe); err == nil {
			e.ExeSHA = sha256Hex(b)
			e.ManifestToken = manifestScan(b)
		}
	}
	return e
}

func resolvedGo() string {
	for _, c := range []string{"go", `C:\Program Files\Go\bin\go.exe`} {
		if p, err := exec.LookPath(c); err == nil {
			if abs, aerr := filepath.Abs(p); aerr == nil {
				return abs
			}
			return p
		}
	}
	return "not-obtainable-here"
}

func resolvePython() string {
	for _, c := range []string{`C:\Python314\python.exe`, "python"} {
		if p, err := exec.LookPath(c); err == nil {
			return p
		}
	}
	return ""
}

// specSHA256s hashes the committed blob face of spec/cases.yaml, exactly as the
// contract asks, and the worktree face beside it so a reader can see whether the
// two faces differ on this host.
func specSHA256s(repo string) (blob, disk string) {
	out, err := runArgv([]string{"git", "-C", repo, "cat-file", "blob", "HEAD:spec/cases.yaml"}, 15000)
	if err != nil {
		blob = "not-obtainable-here: " + err.Error()
	} else {
		blob = sha256Hex(out)
	}
	if b, err := os.ReadFile(repoFile(repo, "spec/cases.yaml")); err == nil {
		disk = sha256Hex(b)
	}
	return
}

// manifestScan looks for the longPathAware token in the bytes of the binary doing the
// measuring. Like evidence/S00/env-facts-windows-local.json this is a byte scan, not a
// PE manifest parse: it proves the string is in the file, not that the loader honours
// it, and the absence of the string is reported the same way.
func manifestScan(b []byte) map[string]any {
	hits := strings.Count(string(b), "longPathAware")
	return map[string]any{
		"token":         "longPathAware",
		"bytes_scanned": len(b),
		"hit_count":     hits,
		"method":        "byte scan of the runner exe, NOT a PE manifest parse",
		"why":           "LongPathsEnabled=0 on this host, but whether the 259-unit ceiling bites depends on the manifest of the binary that asks, so the runner's own face is recorded instead of assumed",
	}
}

func sha256Hex(b []byte) string {
	s := sha256.Sum256(b)
	return hex.EncodeToString(s[:])
}

func runArgv(argv []string, timeoutMS int64) ([]byte, error) {
	ctx, cancel := context.WithTimeout(context.Background(), time.Duration(timeoutMS)*time.Millisecond)
	defer cancel()
	cmd := exec.CommandContext(ctx, argv[0], argv[1:]...)
	var stderr strings.Builder
	cmd.Stderr = &stderr
	out, err := cmd.Output()
	if err != nil {
		rc := -1
		if cmd.ProcessState != nil {
			rc = cmd.ProcessState.ExitCode()
		}
		return out, fmt.Errorf("rc=%d %v: %s", rc, err, truncate(stderr.String(), 200))
	}
	return out, nil
}

func goVersionString(goexe string) string {
	if goexe == "" || goexe == "not-obtainable-here" {
		return "not-obtainable-here"
	}
	out, err := runArgv([]string{goexe, "version"}, 15000)
	if err != nil {
		return "not-obtainable-here: " + err.Error()
	}
	return strings.TrimSpace(string(out))
}

func windowsVersion() string {
	out, err := runArgv([]string{"reg", "query", `HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion`, "/v", "CurrentBuild"}, 8000)
	if err != nil {
		return "not-obtainable-here: " + truncate(err.Error(), 120)
	}
	for _, line := range strings.Split(string(out), "\n") {
		if strings.Contains(line, "CurrentBuild") {
			return "registry:" + asciiOnly(strings.TrimSpace(line))
		}
	}
	return "not-obtainable-here: rc=0 but no CurrentBuild line"
}

func localeFace() string {
	out, err := envProbeCmd([]string{"chcp"}, 8000)
	if err != nil {
		return "not-obtainable-here: " + truncate(err.Error(), 120)
	}
	digits := strings.Map(func(r rune) rune {
		if r >= '0' && r <= '9' {
			return r
		}
		return 0
	}, asciiOnly(string(out)))
	digits = strings.ReplaceAll(digits, string(rune(0)), "")
	if digits == "" {
		return "not-obtainable-here: rc=0 but no code page number in the output"
	}
	return "console_code_page=" + digits + " (the label around it is cp936 text; non-ASCII bytes are dropped, never guessed)"
}

// asciiOnly keeps only printable ASCII so a cp936 console string cannot be baked
// into a cell as replacement characters. evidence/S00/env-facts-windows-local.json
// records this host's console code page as 936.
func asciiOnly(s string) string {
	b := []byte(s)
	out := make([]byte, 0, len(b))
	for _, c := range b {
		if c >= 0x20 && c < 0x7f {
			out = append(out, c)
		}
	}
	return string(out)
}

// envProbeCmd runs one read-only console probe through the cmd interpreter that
// Windows actually resolves, with rc checked before the text is used. Output is
// ASCII here, so the host console code page (936 per evidence/S00) cannot mangle it.
func envProbeCmd(args []string, timeoutMS int64) ([]byte, error) {
	sh, err := exec.LookPath("cmd")
	if err != nil {
		return nil, fmt.Errorf("cmd interpreter not resolved: %w", err)
	}
	argv := append([]string{sh, "/c"}, args...)
	return runArgv(argv, timeoutMS)
}
