package main

import (
	"encoding/json"
	"fmt"
	"os"
	"sort"
	"strings"
)

// RequiredCell is one entry of spec/cells-required.json, the list the contract owner
// generated from the committed spec face. A port must emit exactly these; anything
// else it emits is marked extra and stays out of the equality digest.
type RequiredCell struct {
	CaseGroup string         `json:"case_group"`
	CaseID    string         `json:"case_id"`
	Language  string         `json:"language,omitempty"`
	APIEntry  string         `json:"api_entry,omitempty"`
	SubIdent  map[string]any `json:"sub_identity"`
	Source    string
	Identity  string
}

type requiredFile struct {
	GeneratedAt         string            `json:"generated_at"`
	GeneratedBy         string            `json:"generated_by"`
	SpecBlobSHA256      string            `json:"spec_blob_sha256"`
	Withdraws           string            `json:"withdraws"`
	BaseLenLadder       []int             `json:"base_len_ladder"`
	PrimaryEntryPerPort map[string]string `json:"primary_entry_per_port"`
	RequiredCells       []RequiredCell    `json:"required_cells"`
	TapiCells           []RequiredCell    `json:"tapi_cells_per_language"`
}

// Required is the parsed required list plus the derived identity strings.
type Required struct {
	File     requiredFile
	ByPort   map[string][]RequiredCell
	Identity map[string]bool // "go|<identity>" set
}

// faceName renders a sub_identity map the way this port's cells declare it as an
// ordered list: dimensions sorted by name, so a comparison does not depend on the
// order the file happened to be written in.
func faceName(group, caseID string, sub map[string]any, entry string) string {
	keys := []string{}
	for k := range sub {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	parts := []string{}
	for _, k := range keys {
		parts = append(parts, fmt.Sprintf("%s=%s", k, idValue(sub[k])))
	}
	ident := group + "/" + caseID
	if len(parts) > 0 {
		ident += "[" + strings.Join(parts, ",") + "]"
	}
	// api_entry is deliberately NOT part of the cross-port identity (cell-identity §1),
	// but spec/cells-required.json distinguishes the T-API rows by it, so the
	// required-list comparison carries it only for group=tapi.
	if group == "tapi" && entry != "" {
		ident += "{api_entry=" + entry + "}"
	}
	return ident
}

// idValue renders a dimension value the same way whether it arrived from JSON as a
// float64 or from the plan as an int, so the required-list comparison is not an
// artefact of Go number typing.
func idValue(v any) string {
	if f, ok := v.(float64); ok && f == float64(int64(f)) {
		return fmt.Sprintf("%d", int64(f))
	}
	return fmt.Sprintf("%v", v)
}

func loadRequired(repo string) ([]int, *Required, error) {
	path := repoFile(repo, "spec/cells-required.json")
	raw, err := os.ReadFile(path)
	if err != nil {
		return defaultLadder, nil, fmt.Errorf("read %s: %w", path, err)
	}
	var f requiredFile
	if err := json.Unmarshal(raw, &f); err != nil {
		return defaultLadder, nil, fmt.Errorf("parse %s: %w", path, err)
	}
	if len(f.BaseLenLadder) == 0 {
		return defaultLadder, nil, fmt.Errorf("%s carries no base_len_ladder", path)
	}
	r := &Required{File: f, ByPort: map[string][]RequiredCell{}, Identity: map[string]bool{}}
	for _, c := range f.RequiredCells {
		c.Source = "required_cells"
		c.Identity = faceName(c.CaseGroup, c.CaseID, c.SubIdent, c.APIEntry)
		r.Identity["all|"+c.Identity] = true
	}
	for _, c := range f.TapiCells {
		c.Source = "tapi_cells_per_language"
		c.Identity = faceName(c.CaseGroup, c.CaseID, c.SubIdent, c.APIEntry)
		r.ByPort[c.Language] = append(r.ByPort[c.Language], c)
		r.Identity[c.Language+"|"+c.Identity] = true
		r.Identity["all|"+c.Identity] = true
	}
	return f.BaseLenLadder, r, nil
}

// cellIdentity builds the same string the required list uses, from a published cell
// record, so the comparison is between two renderings of one rule.
func cellIdentity(c map[string]any) string {
	sub := map[string]any{}
	group, _ := c["case_group"].(string)
	caseID, _ := c["case_id"].(string)
	entry, _ := c["api_entry"].(string)
	// the gate (ci/equality.py) reads these dimensions as flat top-level fields
	for _, f := range []string{"base_len", "builder", "reader", "packer", "extractor"} {
		if v, ok := c[f]; ok && v != nil && v != "" {
			sub[f] = v
		}
	}
	// the port also publishes them as an ordered list; the flat face wins on a clash,
	// because that is the face the shipped gate reads
	if list, ok := c["sub_identity"].([]any); ok {
		for _, e := range list {
			m, _ := e.(map[string]any)
			if m == nil {
				continue
			}
			k, _ := m["dim"].(string)
			if k == "" || k == "api_entry" {
				continue
			}
			if _, seen := sub[k]; !seen {
				sub[k] = m["value"]
			}
		}
	}
	return faceName(group, caseID, sub, entry)
}

// annotateRequired marks each planned row as required or extra. Extra rows are still
// published; the notice says they stay out of the equality digest.
func annotateRequired(rows []*planRow, req *Required) {
	if req == nil {
		for _, r := range rows {
			r.RequiredIdentity = "not-checked: spec/cells-required.json unreadable"
			r.Extra = true
		}
		return
	}
	for _, r := range rows {
		ident := rowIdentity(r)
		ok := req.Identity["go|"+ident] || req.Identity["all|"+ident]
		r.RequiredIdentity = ident
		r.Extra = !ok
	}
}

func rowIdentity(r *planRow) string {
	sub := map[string]any{}
	for _, d := range r.SubIdentity {
		if d.K == "api_entry" {
			continue
		}
		// base_len is a number in the required file; keep the same face here
		if n, err := atoiStrict(d.V); err == nil && d.K == "base_len" {
			sub[d.K] = n
		} else {
			sub[d.K] = d.V
		}
	}
	return faceName(r.Group, r.CaseID, sub, r.Entry)
}

func atoiStrict(s string) (int, error) {
	var n int
	_, err := fmt.Sscanf(s, "%d", &n)
	if err != nil {
		return 0, err
	}
	if fmt.Sprintf("%d", n) != s {
		return 0, fmt.Errorf("not an integer face: %q", s)
	}
	return n, nil
}

// faceForForm maps a cell's path form to the bisection face that answers it: the plain
// form is asked through the pinned entry, the extended form through the \?\ prefix.
func faceForForm(form string) string {
	if form == "extended" {
		return FacePrefix
	}
	return FaceOSPlain
}

// ctrlFallbackHex is used only if the pinned control_samples block carries no hex for a
// cell, which rev6 makes a spec defect rather than a port choice: the port says so in the
// cell instead of inventing a name silently.
func ctrlFallbackHex(id string) string {
	switch id {
	case "T-CTRL-ASCII":
		return toHex("report-2026.txt")
	case "T-CTRL-ILLEGAL-CHAR":
		return toHex("a<b.txt")
	case "T-CTRL-PARSE":
		return toHex("nul\x00byte.txt")
	case "T-CTRL-NAMETOOLONG":
		return toHex(strings.Repeat("a", 256))
	case "T-CTRL-CANON":
		return toHex("canon-check.txt")
	}
	return ""
}

func blindMapRef(spec *FrozenSpec) string {
	if spec != nil && spec.BlindMap != "" {
		return spec.BlindMap
	}
	return "evidence/freeze/blind-map.json (path unread)"
}
