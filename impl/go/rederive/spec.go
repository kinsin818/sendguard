package main

import (
	"bufio"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strings"
)

// FrozenSpec is everything this port reads out of spec/cases.yaml. Names are held
// as UTF-8 hex and decoded at run time (N12: a forbidden name is never hand-typed
// and never stored as a real path in the repo).
// ControlSample is one of the five pinned control cells (spec/cases.yaml
// control_samples, added at rev6). Before rev6 the control names existed only in the
// S00 baseline instrument, and five ports invented five names for T-CTRL-CANON.
type ControlSample struct {
	ID     string
	Hex    string
	PayHex string
}

// BlindSample is one sealed blind name, read from the file spec/cases.yaml points at.
type BlindSample struct {
	ID     int
	CaseID string
	Hex    string
}

// LenFill is the rev7 pinned filler for the length family. The name of a len cell is
// this unit repeated until the component is exactly base_len code units, and name_source
// is the hex of those bytes -- not a case label, not a description.
type LenFill struct {
	UnitHex  string
	Rule     string
	Applies  []string
	NameRule string
}

func (f LenFill) Unit() string {
	b, err := hex.DecodeString(f.UnitHex)
	if err != nil {
		return ""
	}
	return string(b)
}

type FrozenSpec struct {
	FreezeRevision string   `json:"freeze_revision"`
	CaseIDs        []string `json:"case_ids"`
	Controls       []ControlSample
	Blind          []BlindSample
	LenFill        LenFill
	BlindMap       string
	GoEntries      []string `json:"go_entries"`
	Payload        []byte   `json:"-"`
}

type CaseDef struct {
	ID           string
	Category     string
	Locale       string
	Applicable   []string
	Samples      []string // hex strings; more than one => member cells (T09/T14/T19)
	Kind         string   // "trap" or "len"
	Note         string
	RawSampleHex string
}

var (
	reCaseItem   = regexp.MustCompile(`^\s*-\s+id:\s*(\S+)\s*$`)
	reKeyVal     = regexp.MustCompile(`^\s+([a-z_]+):\s*(.*)$`)
	reListItem   = regexp.MustCompile(`^\s+-\s*(.+)$`)
	reBlindRef   = regexp.MustCompile(`^blind_map_ref:\s*"([^"]+)"`)
	reTopLevel   = regexp.MustCompile(`^([a-z_]+):\s*(.+)$`)
	reGoEntryKey = regexp.MustCompile(`^\s+go:\s*\[(.*)\]\s*$`)
)

func unquote(s string) string {
	s = strings.TrimSpace(s)
	if a, e := strings.IndexByte(s, '"'), strings.LastIndexByte(s, '"'); a >= 0 && e > a {
		return s[a+1 : e]
	}
	return s
}

func stripComment(s string) string {
	if i := strings.Index(s, " #"); i >= 0 {
		return strings.TrimSpace(s[:i])
	}
	return strings.TrimSpace(s)
}

// LoadSpec parses the frozen case table. It is deliberately line-oriented rather
// than a YAML library: stdlib only (deps_direct=0) and the frozen file's shape is
// pinned by spec/FROZEN.md.
func LoadSpec(path string) (*FrozenSpec, map[string]*CaseDef, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, nil, fmt.Errorf("open %s: %w", path, err)
	}
	defer f.Close()

	spec := &FrozenSpec{Payload: []byte("SENDGUARD-CANON-PAYLOAD-2026")}
	cases := map[string]*CaseDef{}
	order := []string{}
	section := ""
	cur := (*CaseDef)(nil)
	inHexList := false

	sc := bufio.NewScanner(f)
	sc.Buffer(make([]byte, 1<<20), 1<<20)
	for sc.Scan() {
		line := sc.Text()
		if t := strings.TrimSpace(line); t == "" || strings.HasPrefix(t, "#") {
			continue
		}
		if !strings.HasPrefix(line, " ") {
			// top-level scalars are read wherever they sit in the file
			if m := reTopLevel.FindStringSubmatch(line); m != nil {
				switch m[1] {
				case "freeze_revision":
					spec.FreezeRevision = unquote(m[2])
				case "blind_map_ref":
					spec.BlindMap = unquote(m[2])
				}
			}
			section = strings.TrimSuffix(strings.TrimSpace(line), ":")
			cur = nil
			inHexList = false
			continue
		}
		switch section {
		case "api_entry":
			if m := reGoEntryKey.FindStringSubmatch(line); m != nil {
				for _, e := range strings.Split(m[1], ",") {
					if e = strings.TrimSpace(e); e != "" {
						spec.GoEntries = append(spec.GoEntries, e)
					}
				}
			}
		case "control_samples":
			if m := reCaseItem.FindStringSubmatch(line); m != nil {
				spec.Controls = append(spec.Controls, ControlSample{ID: m[1]})
				continue
			}
			if len(spec.Controls) == 0 {
				continue
			}
			if m := reKeyVal.FindStringSubmatch(line); m != nil {
				last := &spec.Controls[len(spec.Controls)-1]
				switch m[1] {
				case "sample_hex":
					last.Hex = unquote(stripComment(m[2]))
				case "payload_hex":
					last.PayHex = unquote(stripComment(m[2]))
				}
			}
		case "len_fill":
			if m := reKeyVal.FindStringSubmatch(line); m != nil {
				switch m[1] {
				case "unit_hex":
					spec.LenFill.UnitHex = unquote(stripComment(m[2]))
				case "rule":
					spec.LenFill.Rule = unquote(stripComment(m[2]))
				case "name_source_rule":
					spec.LenFill.NameRule = unquote(stripComment(m[2]))
				case "applies_to":
					v := strings.TrimSuffix(strings.TrimPrefix(strings.TrimSpace(stripComment(m[2])), "["), "]")
					for _, a := range strings.Split(v, ",") {
						if a = strings.TrimSpace(a); a != "" {
							spec.LenFill.Applies = append(spec.LenFill.Applies, a)
						}
					}
				}
			}
		case "cases":
			if m := reCaseItem.FindStringSubmatch(line); m != nil {
				cur = &CaseDef{ID: m[1], Kind: "trap"}
				cases[cur.ID] = cur
				order = append(order, cur.ID)
				inHexList = false
				continue
			}
			if cur == nil {
				continue
			}
			if m := reKeyVal.FindStringSubmatch(line); m != nil {
				k, v := m[1], stripComment(m[2])
				switch k {
				case "sample_hex":
					cur.RawSampleHex = unquote(v)
					cur.Samples = []string{cur.RawSampleHex}
					inHexList = false
				case "sample_hex_list":
					inHexList = true
					cur.Samples = nil
				case "category":
					cur.Category = unquote(v)
					inHexList = false
				case "locale":
					cur.Locale = unquote(v)
					inHexList = false
				case "applicable":
					v = strings.TrimSuffix(strings.TrimPrefix(strings.TrimSpace(v), "["), "]")
					cur.Applicable = nil
					for _, a := range strings.Split(v, ",") {
						if a = strings.TrimSpace(a); a != "" {
							cur.Applicable = append(cur.Applicable, a)
						}
					}
					inHexList = false
				case "spec_source":
					cur.Note = unquote(v)
					inHexList = false
				default:
					inHexList = false
				}
				continue
			}
			if inHexList {
				if m := reListItem.FindStringSubmatch(line); m != nil {
					cur.Samples = append(cur.Samples, unquote(m[1]))
				}
			}
		case "":
			t := strings.TrimSpace(line)
			if strings.HasPrefix(t, "freeze_revision:") {
				spec.FreezeRevision = unquote(strings.SplitN(t, ":", 2)[1])
			}
			if m := reBlindRef.FindStringSubmatch(t); m != nil {
				spec.BlindMap = m[1]
			}
		}
	}
	if err := sc.Err(); err != nil {
		return nil, nil, err
	}
	spec.CaseIDs = order

	// T17/T18 are bisection cells: their sample_hex is a prose marker, not hex.
	for _, id := range []string{"T17", "T18"} {
		if c, ok := cases[id]; ok {
			c.Kind = "len"
		}
	}
	for id, c := range cases {
		if c.Kind != "len" {
			for _, h := range c.Samples {
				if _, err := hex.DecodeString(h); err != nil {
					return nil, nil, fmt.Errorf("case %s sample_hex %q is not valid hex: %v", id, h, err)
				}
			}
		}
		if len(c.Samples) == 0 {
			return nil, nil, fmt.Errorf("case %s has no sample", id)
		}
	}
	if len(spec.GoEntries) == 0 {
		return nil, nil, fmt.Errorf("api_entry.go list not found in %s", path)
	}
	if len(spec.Controls) == 0 {
		return nil, nil, fmt.Errorf("spec/cases.yaml has no control_samples block; rev6 pins them and this port will not invent names again")
	}
	if spec.LenFill.UnitHex == "" || spec.LenFill.Unit() == "" {
		return nil, nil, fmt.Errorf("spec/cases.yaml len_fill unit_hex is missing or not hex; rev7 pins the length-family filler and this port will not choose its own")
	}
	// rev6 pins ONE payload for all five control cells; if the five disagree the port says
	// so instead of picking one and calling it the canonical bytes.
	for i, c := range spec.Controls {
		if i == 0 {
			continue
		}
		if c.PayHex != spec.Controls[0].PayHex {
			return nil, nil, fmt.Errorf("control %s carries payload_hex %s while %s carries %s; rev6 pins one payload for all five",
				c.ID, c.PayHex, spec.Controls[0].ID, spec.Controls[0].PayHex)
		}
	}
	for _, c := range spec.Controls {
		if _, err := hex.DecodeString(c.Hex); err != nil {
			return nil, nil, fmt.Errorf("control %s sample_hex is not hex: %v", c.ID, err)
		}
		if _, err := hex.DecodeString(c.PayHex); err != nil {
			return nil, nil, fmt.Errorf("control %s payload_hex is not hex: %v", c.ID, err)
		}
	}
	// spec.BlindMap was captured while scanning the top level of the file
	if spec.BlindMap == "" {
		spec.BlindMap = "evidence/freeze/blind-map.json"
	}
	spec.Blind = LoadBlind(filepath.Join(filepath.Dir(filepath.Dir(path)), spec.BlindMap))
	if len(spec.Blind) != 5 {
		return nil, nil, fmt.Errorf("blind map %s gave %d samples, expected 5", spec.BlindMap, len(spec.Blind))
	}
	return spec, cases, nil
}

// LoadBlind reads the sealed blind map spec/cases.yaml names. rev6 requires the five
// blind cells, so the seal is opened by the contract owner's instruction, not by this
// local deciding to unseal it.
func LoadBlind(path string) []BlindSample {
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil
	}
	var doc struct {
		Entries []struct {
			BlindID int    `json:"blind_id"`
			Hex     string `json:"name_utf8_hex"`
		} `json:"entries"`
	}
	if err := json.Unmarshal(raw, &doc); err != nil {
		return nil
	}
	out := []BlindSample{}
	for _, e := range doc.Entries {
		if _, err := hex.DecodeString(e.Hex); err != nil {
			continue
		}
		out = append(out, BlindSample{ID: e.BlindID, CaseID: fmt.Sprintf("B%d", e.BlindID), Hex: e.Hex})
	}
	return out
}

// SampleName decodes a frozen hex sample at run time.
func SampleName(h string) string {
	b, err := hex.DecodeString(h)
	if err != nil {
		panic("undecodable sample " + h)
	}
	return string(b)
}

// Member is one frozen sample: a single-member case, or one branch of a
// multi-member case (T09/T14/T19), named per spec/FROZEN.md (T09a, T14c, ...).
type Member struct {
	CaseID     string
	BaseID     string
	Member     string
	Hex        string
	Category   string
	Locale     string
	Applicable []string
	Kind       string
	Note       string
}

// MemberCases expands multi-member cases into the member ids spec/FROZEN.md
// already names (T09a/T09b, T14a/T14b/T14c, T19a/T19b).
func MemberCases(cases map[string]*CaseDef, order []string) []Member {
	out := []Member{}
	for _, id := range order {
		c := cases[id]
		for i, h := range c.Samples {
			// spec/cells-required.json names the member cells T09-m1, T14-m2, T19-m1 ...
			m := Member{CaseID: id, BaseID: id, Hex: h, Category: c.Category, Locale: c.Locale,
				Applicable: c.Applicable, Kind: c.Kind, Note: c.Note}
			if len(c.Samples) > 1 {
				m.CaseID = fmt.Sprintf("%s-m%d", id, i+1)
				m.Member = fmt.Sprintf("m%d", i+1)
			}
			out = append(out, m)
		}
	}
	return out
}

func repoFile(repo, rel string) string { return filepath.Join(repo, filepath.FromSlash(rel)) }
