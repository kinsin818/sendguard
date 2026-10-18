package main

import (
	"fmt"
	"sort"
	"strconv"
)

// ControlResult is one control cell judged against evidence/ctrl-baseline.md.
// Control cells verify the ruler; they are not data (spec/gate.md §8).
type ControlResult struct {
	ID       string            `json:"cell"`
	Pass     bool              `json:"pass"`
	Expected map[string]string `json:"expected"`
	Got      map[string]string `json:"got"`
	Mismatch []string          `json:"mismatch"`
	Note     string            `json:"note"`
}

func evalControls(rows []*planRow, obs map[string]*Observation) []ControlResult {
	out := []ControlResult{}
	for _, cc := range ctrlCells {
		var row *planRow
		for _, r := range rows {
			if r.Group == "ctrl" && r.CaseID == cc.ID {
				row = r
				break
			}
		}
		if row == nil {
			out = append(out, ControlResult{ID: cc.ID, Pass: false, Expected: cc.Expected,
				Note: "control cell was not in the plan"})
			continue
		}
		o := obs[row.Key]
		if o == nil {
			out = append(out, ControlResult{ID: cc.ID, Pass: false, Expected: cc.Expected,
				Note: "no observation for the control cell"})
			continue
		}
		got := map[string]string{
			"create_result":     o.CreateResult,
			"error_stage":       o.ErrorStage,
			"bytes_written":     intPtr(o.BytesWritten),
			"bytes_on_disk":     intPtr(o.BytesOnDisk),
			"read_result":       o.ReadResult,
			"read_leg_executed": strconv.FormatBool(o.ReadLegExecuted),
			"roundtrip_ok":      boolPtr(o.RoundtripOK),
			"sha256_self":       o.Sha256Self,
			"sha256_truth":      o.Sha256Truth,
			"winerror":          intPtrP(o.WinError),
		}
		mismatch := []string{}
		for k, want := range cc.Expected {
			if k == "sha256_truth_equals_self" {
				if o.Sha256Self == "" || o.Sha256Truth == "" || o.Sha256Self != o.Sha256Truth {
					mismatch = append(mismatch, fmt.Sprintf(
						"sha256_truth_equals_self: want %s got self=%q truth=%q", want, o.Sha256Self, o.Sha256Truth))
				}
				continue
			}
			if got[k] != want {
				mismatch = append(mismatch, fmt.Sprintf("%s: want %q got %q", k, want, got[k]))
			}
		}
		note := ""
		if cc.ID == "T-CTRL-CANON" || cc.ID == "T-CTRL-ASCII" {
			if o.Sha256Truth != "" && o.Sha256Truth != canonBaselineSHA {
				mismatch = append(mismatch, fmt.Sprintf("sha256_truth differs from the S00 baseline value %s", canonBaselineSHA))
			}
			note = "sha256_self is this port's own hash of the payload; sha256_truth is the independent python read-back arm's hash"
		}
		sort.Strings(mismatch)
		out = append(out, ControlResult{
			ID: cc.ID, Pass: len(mismatch) == 0, Expected: cc.Expected, Got: got,
			Mismatch: mismatch, Note: note,
		})
	}
	return out
}

func intPtr(v *int64) string {
	if v == nil {
		return "null"
	}
	return strconv.FormatInt(*v, 10)
}

func intPtrP(v *int) string {
	if v == nil {
		return "null"
	}
	return strconv.Itoa(*v)
}

func boolPtr(v *bool) string {
	if v == nil {
		return "null"
	}
	return strconv.FormatBool(*v)
}

// buildCells turns every plan row plus its observation into a published cell.
func buildCells(spec *FrozenSpec, cases map[string]*CaseDef, env *envFace, rows []*planRow,
	obs map[string]*Observation, extra map[string]map[string]any,
	controls []ControlResult, allPass bool) []*Cell {

	cells := []*Cell{}
	primaryEntry := spec.GoEntries[0]
	for _, r := range rows {
		o := obs[r.Key]
		if o == nil {
			o = failedObservation(r, "observation missing")
		}
		spread := map[string]any{}
		if r.Group == "trap" {
			spread = entrySpread(rows, obs, r.CaseID, primaryEntry)
		}
		c := assembleCell(r, o, spec, env, extra[r.Key], spread, r.Entry == primaryEntry)
		if cd, ok := cases[r.BaseID]; ok {
			c.set("case_category_frozen", cd.Category)
		}
		if r.Group == "ctrl" {
			for _, cc := range controls {
				if cc.ID == r.CaseID {
					c.set("control_expectation", cc.Expected)
					c.set("control_got", cc.Got)
					c.set("control_mismatch", cc.Mismatch)
				}
			}
		}
		if r.Group == "tapi" && r.Entry == primaryEntry {
			c.set("primary_entry_cell", true)
		}
		if r.Group == "len" {
			c.set("longpath_mechanism_basis", "abs dir length + 1 + name utf16 units vs 259, with LongPathsEnabled from the registry probe")
		}
		if !allPass {
			c.set("round_instrument_red", true)
		}
		cells = append(cells, c)
	}
	sort.Slice(cells, func(i, j int) bool { return cells[i].FileName() < cells[j].FileName() })
	return cells
}
