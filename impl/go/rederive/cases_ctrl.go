package main

import (
	"strings"
)

// Control cells. Their names come from harness/ctrl-baseline.mjs, which
// evidence/ctrl-baseline.md declares the only allowed source of control
// expectations; their stored form is hex like every other sample (N12), so no
// forbidden name is ever typed into this port or landed in the repo.
type ctrlDef struct {
	ID       string
	Hex      string
	Expected map[string]string
}

var ctrlCells = []ctrlDef{
	{ID: "T-CTRL-NAMETOOLONG", Hex: toHex(strings.Repeat("a", 256)),
		Expected: map[string]string{"create_result": "err_at_syscall", "error_stage": "syscall"}},
	{ID: "T-CTRL-ASCII", Hex: toHex("report-2026.txt"),
		Expected: map[string]string{"create_result": "ok", "bytes_written": "28", "bytes_on_disk": "28",
			"read_result": "ok", "roundtrip_ok": "true"}},
	{ID: "T-CTRL-ILLEGAL-CHAR", Hex: toHex("a<b.txt"),
		Expected: map[string]string{"create_result": "err_at_syscall", "error_stage": "syscall"}},
	{ID: "T-CTRL-PARSE", Hex: toHex("nul\x00byte.txt"),
		Expected: map[string]string{"create_result": "err_at_parse", "error_stage": "parse"}},
	{ID: "T-CTRL-CANON", Hex: toHex("canon-go-arm.txt"),
		Expected: map[string]string{"create_result": "ok", "sha256_truth_equals_self": "true"}},
}

// canonBaselineSHA is the sha256 the S00 baseline printed for the canonical
// payload; it is data compared against, never an expectation about behaviour.
const canonBaselineSHA = "c9fe45b2fee8ea846f0cf4f2cacc2a891e7b082e7719923502d12a9813e21994"

// lenGrid is the G1-G4 verification grid pinned by spec/FROZEN.md, verbatim:
//
//	G1 base13  x(244,245,246)
//	G2 base120 x(137,138,139)
//	G3 base13  x(254,255,256)
//	G4 base200 x(254,255,256)
//
// with "G3 == G4 (255)" as the domain-A self-check. spec/FROZEN.md attaches the grid
// to "T17/T18" jointly and never says which tiers belong to which case, so this port
// runs all four tiers for BOTH cases (24 cells): a omitted pinned point cannot be
// recovered later, a duplicated one costs a second and is filtered by S03.
var lenGrid = []struct {
	Tier   string
	Base   int
	Points []int
}{
	{"G1", 13, []int{244, 245, 246}},
	{"G2", 120, []int{137, 138, 139}},
	{"G3", 13, []int{254, 255, 256}},
	{"G4", 200, []int{254, 255, 256}},
}
