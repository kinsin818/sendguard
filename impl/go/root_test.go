package main

// SG-F15 arms: the lane must resolve the tree it measures, and must fail loudly when it cannot.
//
// Two-sided by this repository's rule (a leg that only demonstrates refusal is the most diligently
// looking useless leg there is), and every fixture is planted outside the repository in a directory this
// function is told about - never at a drive root, never inside the tree it is judging.

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func plantedRoot(t *testing.T, digest string) string {
	t.Helper()
	tmp := t.TempDir()
	if err := os.MkdirAll(filepath.Join(tmp, "spec"), 0o755); err != nil {
		t.Fatalf("plant: %v", err)
	}
	if err := os.WriteFile(filepath.Join(tmp, "spec", "FROZEN.md"),
		[]byte("| file | sha256 |\n|---|---|\n| spec/x.txt | "+digest+" |\n"), 0o644); err != nil {
		t.Fatalf("plant table: %v", err)
	}
	if err := os.WriteFile(filepath.Join(tmp, "spec", "x.txt"), []byte("not the frozen bytes\n"), 0o644); err != nil {
		t.Fatalf("plant face: %v", err)
	}
	return tmp
}

// A1 red: no contract root above the working directory, and no -repo -> refuse, do not guess.
func TestResolveRepoRefusesWithoutAContractRoot(t *testing.T) {
	tmp := t.TempDir()
	wd, err := os.Getwd()
	if err != nil {
		t.Fatalf("cwd: %v", err)
	}
	if err := os.Chdir(tmp); err != nil {
		t.Fatalf("chdir: %v", err)
	}
	defer func() {
		if err := os.Chdir(wd); err != nil {
			t.Fatalf("restore cwd: %v", err)
		}
	}()
	if p, err := resolveRepo(nil); err == nil {
		t.Fatalf("red arm: resolveRepo accepted a directory tree with no spec/FROZEN.md at all, got %q", p)
	}
}

// A2 red: a caller that names a directory which is not a contract root is refused, not silently accepted.
func TestResolveRepoRefusesAForeignRepoFlag(t *testing.T) {
	tmp := t.TempDir()
	if _, err := resolveRepo([]string{"-repo", tmp}); err == nil {
		t.Fatalf("red arm: -repo pointing at a non-contract directory was accepted")
	}
}

// A3 red: verifying a tree whose frozen face no longer matches the frozen table must return an error.
// This is the arm that would have caught SG-F15: the lane reported "frozen artifacts intact" while reading
// a checkout at an older contract revision.
func TestVerifyFrozenFailsOnAPlantedTree(t *testing.T) {
	tmp := plantedRoot(t, strings.Repeat("0", 64))
	saved := repo
	repo = tmp
	defer func() { repo = saved }()
	if err := verifyFrozen(); err == nil {
		t.Fatalf("red arm: verifyFrozen reported success for a face that does not match its frozen digest")
	}
}

// A4 green: the same function, aimed at the repository the test runs inside, still passes - a refusal that
// also refuses the correct tree is not an instrument, it is a brick.
func TestVerifyFrozenPassesOnThisRepository(t *testing.T) {
	p, err := resolveRepo(nil)
	if err != nil {
		t.Fatalf("green arm: this repository was not accepted as a contract root: %v", err)
	}
	saved := repo
	repo = p
	defer func() { repo = saved }()
	if err := verifyFrozen(); err != nil {
		t.Fatalf("green arm: verifyFrozen failed for %s: %v", p, err)
	}
	if _, err := os.Stat(filepath.Join(p, "spec", "FROZEN.md")); err != nil {
		t.Fatalf("resolved root %q has no frozen table: %v", p, err)
	}
}

// A5 green: the resolved root is the tree the caller is standing in, derived from cwd, and the walk-up finds
// exactly one such root between the module directory and the drive.
func TestResolveRepoWalksUpFromTheModuleDirectory(t *testing.T) {
	wd, err := os.Getwd()
	if err != nil {
		t.Fatalf("cwd: %v", err)
	}
	p, err := resolveRepo(nil)
	if err != nil {
		t.Fatalf("walk-up: %v", err)
	}
	if !strings.HasPrefix(wd, p) {
		t.Fatalf("resolved root %q is not an ancestor of the working directory %q", p, wd)
	}
	if p == wd {
		t.Fatalf("resolved root equals the module directory %q: the walk-up did not move", p)
	}
}

// A6 red: the defect itself is asserted absent - no checkout path may be written into the lane's source.
// A constant that names a particular working copy is how this lane verified a contract it was not shipped
// against.
func TestLaneSourceCarriesNoCheckoutLiteral(t *testing.T) {
	b, err := os.ReadFile("main.go")
	if err != nil {
		t.Fatalf("reading own source: %v", err)
	}
	text := string(b)
	for _, lit := range []string{"D:" + string(os.PathSeparator) + "sendguard", "D:\\sendguard"} {
		if strings.Contains(text, lit) {
			t.Fatalf("red arm: main.go still hardcodes a checkout root %q", lit)
		}
	}
	if !strings.Contains(text, "func resolveRepo(") {
		t.Fatalf("red arm: main.go no longer defines resolveRepo, so the root is decided by something else")
	}
}
