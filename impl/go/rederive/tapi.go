package main

// behavEqual compares the columns ci/equality.py digests, so a T-API roll-up says
// "this entry answered differently" in exactly the sense the gate would notice, not
// in the sense of prose differences.
func behavEqual(a, b *Observation) bool {
	if a == nil || b == nil {
		return false
	}
	eqInt := func(x, y *int) bool {
		if x == nil || y == nil {
			return x == nil && y == nil
		}
		return *x == *y
	}
	eq64 := func(x, y *int64) bool {
		if x == nil || y == nil {
			return x == nil && y == nil
		}
		return *x == *y
	}
	return a.CreateResult == b.CreateResult && a.ErrorStage == b.ErrorStage &&
		eqInt(a.WinError, b.WinError) && eq64(a.BytesWritten, b.BytesWritten) &&
		eq64(a.BytesOnDisk, b.BytesOnDisk) && a.ReadResult == b.ReadResult &&
		a.LandedHex == b.LandedHex && a.NameMutated == b.NameMutated &&
		a.Phantom == b.Phantom && a.Blocked == b.Blocked
}

// tapiSpread rolls each pinned entry up over every frozen member and publishes where
// it answers differently from the primary entry. The per-member cells themselves are
// not published as files (see buildPlan): four cells at one (case_group, case_id,
// sub_identity) with different digests is precisely the ambiguous_entries refusal
// that ci/equality.py prints, and spec/cell-identity.md §2 asks for this instead.
func tapiSpread(rows []*planRow, obs map[string]*Observation, extra map[string]map[string]any, spec *FrozenSpec) {
	byCase := map[string]map[string]*Observation{}
	for _, r := range rows {
		if r.Group != "tapi" {
			continue
		}
		if byCase[r.CaseID] == nil {
			byCase[r.CaseID] = map[string]*Observation{}
		}
		byCase[r.CaseID][r.Entry] = obs[r.Key]
	}
	primary := spec.GoEntries[0]
	for _, r := range rows {
		if r.Group != "tapi" || len(r.RollupOver) == 0 {
			continue
		}
		agree, disagree := 0, 0
		hits := []map[string]any{}
		for _, cid := range r.RollupOver {
			m := byCase[cid]
			if m == nil {
				continue
			}
			a, b := m[primary], m[r.Entry]
			if a == nil || b == nil {
				continue
			}
			if behavEqual(a, b) {
				agree++
				continue
			}
			disagree++
			hits = append(hits, map[string]any{
				"member":          cid,
				"primary_answer":  a.CreateResult,
				"this_answer":     b.CreateResult,
				"primary_error":   a.ErrorCode,
				"this_error":      b.ErrorCode,
				"primary_phantom": a.Phantom,
				"this_phantom":    b.Phantom,
				"primary_blocked": a.Blocked,
				"this_blocked":    b.Blocked,
			})
		}
		if extra[r.Key] == nil {
			extra[r.Key] = map[string]any{}
		}
		extra[r.Key]["tapi_spread"] = map[string]any{
			"primary_entry":         primary,
			"members_compared":      agree + disagree,
			"agree_with_primary":    agree,
			"disagree_with_primary": disagree,
			"disagreements":         hits,
			"rule":                  "spec/gate.md §2: a T-API hit count of zero is an instrument failure. The cell's own behaviour fields come from running this entry on the S00 baseline name report-2026.txt, which is a real single measurement; the spread over the 22 frozen members is published beside it",
		}
	}
}
