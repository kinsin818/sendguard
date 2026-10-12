package main

import (
	"encoding/json"
	"fmt"
	"regexp"
	"sort"
	"strconv"
	"strings"
)

// Cell is one published measurement record: the raw observation plus its identity,
// environment face and provenance. Fields are emitted as a map so the JSON key set
// is explicit and every ci/equality.py behaviour column is present on every cell.
type Cell struct {
	m map[string]any
}

func newCell() *Cell { return &Cell{m: map[string]any{}} }

func (c *Cell) set(k string, v any) { c.m[k] = v }

func (c *Cell) drop(k string) { delete(c.m, k) }

// sub appends one ordered, named dimension to sub_identity (spec/cell-identity.md §1).
// sub declares one identity dimension. rev6: ci/equality.py reads sub_identity as an
// OBJECT of declared dimensions; an array is logged as a contract defect, so the dims go
// in as keys and the ordered list is kept beside them for the reader.
func (c *Cell) sub(dim string, v any) {
	// a numeric dimension is stored as a number, because spec/cells-required.json writes
	// base_len as 78 and ci/equality.py overlays declared dimensions onto the flat fields:
	// "78" as a string would render as a different identity than the row it must match.
	val := v
	if str, ok := v.(string); ok {
		if n, err := strconv.Atoi(str); err == nil {
			val = n
		}
	}
	obj, _ := c.m["sub_identity"].(map[string]any)
	if obj == nil {
		obj = map[string]any{}
	}
	obj[dim] = val
	c.m["sub_identity"] = obj
	list, _ := c.m["sub_identity_declared"].([]any)
	c.m["sub_identity_declared"] = append(list, map[string]any{"dim": dim, "value": fmt.Sprintf("%v", val)})
}

var reUnsafe = regexp.MustCompile(`[^A-Za-z0-9._-]+`)

// FileName follows spec/cell-identity.md §3: <case_group>__<case_id>[__<sub>].json.
// Every sub_identity dimension is in the name, because two cells that differ only by
// a declared dimension must not land on one path (that is how the earlier run lost
// 153 records into 27 identities).
func (c *Cell) FileName() string {
	group := fmt.Sprintf("%v", c.m["case_group"])
	caseID := fmt.Sprintf("%v", c.m["case_id"])
	subs := []string{}
	if obj, ok := c.m["sub_identity"].(map[string]any); ok {
		for _, k := range sortedKeys(obj) {
			subs = append(subs, fmt.Sprintf("%s-%s", k,
				reUnsafe.ReplaceAllString(fmt.Sprintf("%v", obj[k]), "")))
		}
	}
	name := group + "__" + caseID
	if len(subs) > 0 {
		name += "__" + strings.Join(subs, "_")
	}
	return name + ".json"
}

func (c *Cell) Key() string {
	parts := []string{fmt.Sprintf("%v", c.m["case_group"]), fmt.Sprintf("%v", c.m["case_id"])}
	if list, ok := c.m["sub_identity"].([]any); ok {
		for _, e := range list {
			m := e.(map[string]any)
			parts = append(parts, fmt.Sprintf("%s=%s", m["dim"], m["value"]))
		}
	}
	return strings.Join(parts, "/")
}

// Bytes renders the cell as UTF-8 JSON without BOM, keys sorted by encoding/json,
// LF terminated (ci/lint.py piece 3 refuses a BOM; .gitattributes pins the bytes).
func (c *Cell) Bytes() []byte {
	b, err := json.MarshalIndent(c.m, "", "  ")
	if err != nil {
		panic(err)
	}
	return append(b, '\n')
}

// envFace is measured once per run and stamped into every cell.
type envFace struct {
	OS              string         `json:"os"`
	OSVersion       string         `json:"os_version"`
	Arch            string         `json:"arch"`
	Locale          string         `json:"locale"`
	GoExe           string         `json:"go_exe_resolved"`
	GoVersion       string         `json:"go_version"`
	RunnerExe       string         `json:"runner_exe"`
	ManifestToken   map[string]any `json:"runner_manifest_scan"`
	ManifestControl map[string]any `json:"manifest_scanner_green_arm"`
	ExeSHA          string         `json:"runner_exe_sha256_before"`
	ExeSHAAfter     string         `json:"runner_exe_sha256_after"`
	LongPaths       map[string]any `json:"longpaths_registry"`
	Volume          map[string]any `json:"volume_d"`
	SpecSHA         string         `json:"spec_sha256"`
	SpecSHAOnDisk   string         `json:"spec_sha256_worktree_face"`
	FreezeRevision  string         `json:"freeze_revision"`
	RunStartedAt    string         `json:"run_started_at"`
	PythonExe       string         `json:"python_readback_arm_exe"`
	SandboxRoot     string         `json:"sandbox_root"`
}

// assembleCell maps one raw observation onto the published cell record.
func assembleCell(p *planRow, o *Observation, spec *FrozenSpec, env *envFace,
	extra map[string]any, spread map[string]any, isPrimary bool) *Cell {
	c := newCell()
	c.set("format_version", 1)
	c.set("case_id", p.CaseID)
	c.set("case_group", p.Group)
	c.set("language", "go")
	c.set("os", "windows")
	c.set("os_version", env.OSVersion)
	c.set("arch", env.Arch)
	c.set("arch_dir_label", "x64")
	c.set("locale", env.Locale)
	c.set("api_entry", p.Entry)
	c.set("attempt", 1)
	// name_source is the name the child actually probed. For a length cell that is the
	// boundary name the bisection found, not the placeholder the plan started from.
	sourceHex := p.HexName
	if o.RequestedHex != "" {
		sourceHex = o.RequestedHex
	}
	c.set("name_source", sourceHex)
	// rev3 split: length_unit says what a length was counted in, name_encoding says how
	// the name in this record is encoded. spec/canonical.md owns the second meaning.
	c.set("length_unit", "utf16_code_units")
	c.set("name_encoding", "hex_raw_bytes")
	c.set("length_unit_basis", "os.Create takes a Go string (UTF-8) and this port converts it with syscall.UTF16PtrFromString before CreateFileW, so the unit a length limit bites in is UTF-16 code units; the code-point and UTF-8 counts of the same name are published in len_triple")
	c.set("name_encoding_note", "name_source and name_landed_as are lowercase hex of the name's raw UTF-8 bytes, the face spec/cases.yaml pins; the UTF-16LE and code-point faces of every enumerated name are published beside it in dir_view")
	c.set("path_form", pathFormOf(p))
	c.set("longpath_mechanism", p.LongpathMech)
	c.set("extra", p.Extra)
	c.set("required_identity", p.RequiredIdentity)
	if !p.Publish {
		c.set("publish_reason", p.PublishReason)
	}
	c.set("error_stage", o.ErrorStage)
	c.set("error_code", o.ErrorCode)
	c.set("error_message", o.ErrorMessage)
	c.set("bytes_written", o.BytesWritten)
	c.set("bytes_on_disk", o.BytesOnDisk)
	c.set("read_result", o.ReadResult)
	c.set("os_legality_verdict", o.Legality.Verdict)
	// rev3: a verdict must name the tool that was asked.
	c.set("verdict_via", verdictVia(o.Legality.Probe))
	c.set("verdict_via_probe", o.Legality.Probe)
	c.set("verdict_via_path_form", pathFormOf(p))
	c.set("verdict_via_note", "every legality answer in this port comes from kernel32 FindFirstFileW through syscall, which creates nothing and opens no contents; the cell with no verdict_via tool is the one whose name this runtime refused before any call")
	c.set("harness_version", harnessVersion+"+"+short(env.ExeSHA))
	c.set("started_at", p.StartedAt)
	c.set("elapsed_ms", p.WallMS)
	if o.CreateResult == "" {
		// Nothing was measured on the create leg, so nothing is claimed: the cell
		// fails the required-field rule and is therefore void and excluded, which is
		// what canonical.md §1 says a cell with no lawful status word must be.
		c.drop("create_result")
	} else {
		c.set("create_result", o.CreateResult)
	}

	// ---- behaviour columns ci/equality.py digests ----
	c.set("name_landed_as", nullable(o.LandedHex))
	c.set("name_mutated", o.NameMutated)
	c.set("phantom", o.Phantom)
	// roundtrip_ok and enum_to_stat_agrees are not nullable in spec/schema.json, and the
	// frozen spec/validate.py:67 voids a null one. rev6 section 9.1 says an answer a port
	// did not record stays NOT-RECORDED, which is a completeness finding, never an answer -
	// so when the leg did not run the field is absent, and the reason is published beside it.
	if o.RoundtripOK != nil {
		c.set("roundtrip_ok", *o.RoundtripOK)
	} else {
		c.set("roundtrip_ok_basis", "not recorded: "+o.ReadLegReason)
	}
	if o.EnumToStatAgree != nil {
		c.set("enum_to_stat_agrees", *o.EnumToStatAgree)
	} else {
		c.set("enum_to_stat_agrees_basis", "not recorded: the path_view probe did not run ("+o.PathViewError+")")
	}
	c.set("deps_direct", 0)
	c.set("deps_total", 0)
	c.set("mechanism_class", p.MechanismClass)
	c.set("len_triple", lenTriple(mustDecode(sourceHex)).String())
	c.set("len_triple_planned", p.LenTriple)
	c.set("instrument_red", false)
	c.set("instrument_conflict", o.LandedDespiteEr)
	c.set("control_pass", p.ControlPass)
	c.set("sha256_self", nullable(o.Sha256Self))
	c.set("sha256_truth", nullable(o.Sha256Truth))

	// ---- identity: sub_identity is carried inside the cell, never only in the name ----
	for _, d := range p.SubIdentity {
		c.sub(d.K, d.V)
	}
	if p.Group == "tapi" {
		c.set("primary_entry", isPrimary)
	}
	if spread != nil {
		c.set("entry_spread", spread)
	}

	// ---- supporting evidence, published but outside the digest ----
	c.set("case_id_frozen_base", p.BaseID)
	c.set("member", nullable(p.Member))
	if p.BlindID > 0 {
		c.set("blind_id", p.BlindID)
	}
	c.set("run_status", runStatusOf(p, o))
	c.set("spec_source", p.Note)
	c.set("case_locale", p.Locale)
	c.set("case_applicable_os", p.Applicable)
	c.set("requested_name_visible", o.RequestedName)
	c.set("winerror", o.WinError)
	c.set("winerror_face", winErrorFace(o.WinError))
	c.set("entry_half", nullable(o.EntryHalf))
	c.set("blocked", o.Blocked)
	if o.Blocked || o.CreateResult == "" {
		c.set("block_reason", o.BlockReason)
		c.set("block_command", joinArgv(p.CommandFace))
		c.set("block_exit_code", p.ChildRC)
		c.set("block_attempted_fix", o.BlockAttempt)
	}
	c.set("read_leg_executed", o.ReadLegExecuted)
	c.set("read_leg_reason", o.ReadLegReason)
	c.set("read_bytes", o.ReadBytes)
	c.set("roundtrip_leg_executed", o.ReadLegExecuted)
	c.set("bytes_on_disk_face", o.BytesOnDiskFace)
	c.set("dir_view", o.DirView)
	c.set("dir_view_count", len(o.DirView))
	c.set("path_view_exists", o.PathViewExists)
	c.set("path_view_size", o.PathViewSize)
	c.set("path_view_error", nullable(o.PathViewError))
	c.set("legality_probe", o.Legality)
	c.set("legality_create_probe", o.LegalityRaw)
	c.set("legality_probe_second_face_findfirstfile", o.LegalityExt)
	if o.Extended != nil {
		c.set("extended_probe", o.Extended)
	}
	if o.ZipLeg != nil {
		c.set("zip_leg", o.ZipLeg)
	}
	c.set("phase_timeline", o.PhaseTimeline)
	c.set("phase_ms", o.PhaseMs)
	c.set("scratch_dir_verified_empty_at_creation", o.ScratchEmpty)
	c.set("sandbox_sharing", map[string]any{
		"group_id":            p.GroupID,
		"multi_member_case":   p.MultiMember,
		"first_cell_in_group": p.DirFirstInGroup,
		"measured_dir":        p.Dir,
		"extended_probe_dir":  p.DirExt,
		"rule":                "one fresh uuid sandbox per cell; the multi-member cases T09/T14/T19 share the directory of their (case x entry) group because coexistence in ONE directory is the frozen question, and the port own plan/phase/observation files sit in the sandbox root so they can never enter a dir_view",
	})
	c.set("cleanup_attempted", false)
	c.set("cleanup_failed", p.CleanupFailed)
	c.set("cleanup_note", "M19: this port contains no delete/unlink call anywhere; cleanup_failed is true only if a directory that had to be reused was not already empty, which is reported instead of cleaned")
	c.set("sandbox_dir", p.Sandbox)
	c.set("cell_dir", p.Dir)
	c.set("child_command", p.CommandFace)
	c.set("child_rc", p.ChildRC)
	c.set("child_stdout", p.StdoutFace)
	c.set("child_stderr", p.StderrFace)
	c.set("timed_out", p.TimedOut)
	c.set("child_timeout_ms_enforced", enforcedTimeoutMS)
	c.set("child_process", "one child process per cell, killed by the parent on deadline")
	// the read-back arm's own record stays under its name; the roll-ups the parent added
	// beside it are top-level evidence fields, not arm internals
	armOnly := map[string]any{}
	for k, v := range extra {
		switch k {
		case "coexistence", "tapi_spread", "post_kill_dir_view_by_parent", "post_kill_dir_view_note":
			c.set(k, v)
		default:
			armOnly[k] = v
		}
	}
	if len(armOnly) > 0 {
		c.set("independent_readback_arm", armOnly)
	}
	c.set("env", map[string]any{
		"LongPathsEnabled":           env.LongPaths["value"],
		"LongPathsEnabled_status":    env.LongPaths["status"],
		"dot3name":                   nil,
		"max_component":              env.Volume["max_component"],
		"unicode_version":            "not-obtainable-here",
		"toolchain":                  env.GoVersion + " | builder=" + env.GoExe + " | runner=" + env.RunnerExe,
		"runner_manifest_scan":       env.ManifestToken,
		"manifest_scanner_green_arm": env.ManifestControl,
		"os_build_claim":             "recorded from env probe, see os_version",
		"sandbox_root":               env.SandboxRoot,
	})
	c.set("provenance", map[string]any{
		"spec_sha256":            env.SpecSHA,
		"spec_sha256_face":       "git cat-file blob HEAD:spec/cases.yaml",
		"spec_sha256_worktree":   env.SpecSHAOnDisk,
		"freeze_revision":        spec.FreezeRevision,
		"go_exe_resolved":        env.GoExe,
		"go_version_string":      env.GoVersion,
		"runner_exe":             env.RunnerExe,
		"sg_exe_sha256_before":   env.ExeSHA,
		"harness_source":         "impl/go/rederive/",
		"independent_enumerator": "harness/audit.go is the audit instrument; this port shares no code with it and never invoked it",
		"independence":           "no file under results/ and no other language under impl/ was opened by this seat",
	})
	c.set("normalization_dependency", p.NormalizationDep)
	c.set("payload_hex", payloadHex)
	c.set("implementation_id", "go-port")
	// len cells carry the arithmetic the S03 gate needs
	if p.Packer != "" {
		c.set("packer", p.Packer)
	}
	if p.Extractor != "" {
		c.set("extractor", p.Extractor)
	}
	if o.Bisection != nil {
		c.set("bisection", o.Bisection)
	}
	if p.Group == "len" {
		c.set("base_len", p.BaseLen)
		// rev7 rule 3: the measured ceiling is its own quantity. It never goes into
		// len_triple, which describes the name that was handed to the API.
		bis := asMap(o.Bisection)
		ceilings := map[string]any{}
		for _, e := range asList(bis["faces"]) {
			m := asMap(e)
			if m["face"] != nil {
				ceilings[fmt.Sprintf("%v", m["face"])] = m["boundary_len"]
			}
		}
		c.set("len_ceiling", map[string]any{
			"authoritative_face": bis["authoritative_face"],
			"ceiling_code_units": bis["authoritative_boundary"],
			"probes":             bis["authoritative_probes"],
			"bracket":            bis["bracket"],
			"per_face":           ceilings,
			"seed_char_hex":      spec.LenFill.UnitHex,
			"rule":               "spec/cases.yaml len_fill: the ceiling is where this port's bisection of the pinned filler converged. It is a different quantity from the width of the component handed to the API and is therefore kept out of len_triple",
		})
		c.set("len_pinned_fill", map[string]any{
			"unit_hex":             spec.LenFill.UnitHex,
			"rule":                 spec.LenFill.Rule,
			"name_source_rule":     spec.LenFill.NameRule,
			"component_code_units": p.PinWidth,
			"applies_to":           spec.LenFill.Applies,
		})
		c.set("len_face", map[string]any{
			"question": map[bool]string{true: "T17: how wide a component does this form still accept at all",
				false: "T18: where does the COMPONENT itself stop being accepted"}[p.BaseID == "T17"],
			"this_name_abs_total": p.BaseLenAbs + 1 + p.NameUTF16,
			"measured_dir_len":    p.BaseLenAbs,
			"face_note":           "base_len is the width of the component (spec/cells-required.json base_len_ladder read as spec/cases.yaml len_fill directs), not a directory depth; the measured directory is the ordinary one-level sandbox used by every other cell",
		})
	}
	return c
}

func joinArgv(a []string) string { return strings.Join(a, " ") } // entrySpread summarises the sibling entry cells of one primary trap cell, keeping
// the non-primary entries published without entering the digest (cell-identity §2).
func entrySpread(rows []*planRow, obsByKey map[string]*Observation, caseID, primary string) map[string]any {
	out := map[string]any{}
	for _, r := range rows {
		if r.Group != "tapi" || r.CaseID != caseID || r.Entry == primary {
			continue
		}
		o := obsByKey[r.Key]
		if o == nil {
			continue
		}
		out[r.Entry] = map[string]any{
			"create_result":  o.CreateResult,
			"error_stage":    o.ErrorStage,
			"winerror":       o.WinError,
			"bytes_written":  o.BytesWritten,
			"bytes_on_disk":  o.BytesOnDisk,
			"read_result":    o.ReadResult,
			"name_landed_as": nullable(o.LandedHex),
			"phantom":        o.Phantom,
			"blocked":        o.Blocked,
			"cell":           r.Key,
		}
	}
	return out
}

// winErrorFace names which layer produced the number in error_code: every real
// Win32 code is below 0x10000, so a larger value is one Go synthesised itself,
// which is the evidence that the name was refused before the syscall.
func winErrorFace(v *int) string {
	if v == nil {
		return "no error"
	}
	if *v >= 0x10000 {
		return "go-synthesized (not a Win32 code): the runtime refused the name before the syscall"
	}
	return "win32"
}

// boundaryLen reads the authoritative boundary out of a child observation.
func boundaryLen(o *Observation) (int, bool) {
	if o == nil || o.Bisection == nil {
		return 0, false
	}
	faces, _ := o.Bisection["faces"].([]any)
	auth, _ := o.Bisection["authoritative_face"].(string)
	for _, e := range faces {
		m, _ := e.(map[string]any)
		if m == nil {
			continue
		}
		if m["face"] == auth {
			if b, ok := m["boundary_len"].(float64); ok {
				return int(b), true
			}
		}
	}
	return 0, false
}

// verdictVia names the tool the legality question was put to, as rev3 requires.
func verdictVia(probe string) string {
	switch {
	case probe == "":
		return "none"
	case strings.HasPrefix(probe, "CreateFileW"), strings.HasPrefix(probe, "FindFirstFileW"):
		return "win32"
	}
	return "none"
}

func asMap(v any) map[string]any {
	m, _ := v.(map[string]any)
	if m == nil {
		return map[string]any{}
	}
	return m
}

func asList(v any) []any {
	l, _ := v.([]any)
	return l
}

func pathFormOf(p *planRow) string {
	if p.PathForm == "extended" {
		return "extended"
	}
	return "plain"
}

// runStatusOf is the rev6 field: a cell that could not be run is named, not left absent.
func runStatusOf(p *planRow, o *Observation) string {
	if p.RunStatus != "" {
		return p.RunStatus
	}
	if o == nil || o.CreateResult == "" {
		return "blocked"
	}
	return "ran"
}

func sortedKeys(m map[string]any) []string {
	out := make([]string, 0, len(m))
	for k := range m {
		out = append(out, k)
	}
	sort.Strings(out)
	return out
}

func nullable(s string) any {
	if s == "" {
		return nil
	}
	return s
}

func short(s string) string {
	if len(s) > 12 {
		return s[:12]
	}
	return s
}
