// Command sg is the SENDGUARD Go port, re-derived against spec/cell-identity.md.
//
// stdlib only (deps_direct=0). Two modes:
//
//	sg.exe cell --plan <json>  : one (case x entry) probe, runs as a child process
//	sg.exe run  --repo <root>  : parent; spawns one child per cell, enforces the 5 s timeout
//	sg.exe env  --repo <root>  : prints the environment face the cells are stamped with
//
// The child never talks the result protocol on stdout: it writes a JSON file at a
// parent-chosen path, so a payload that lands on a device handle cannot corrupt it.
package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"os"
)

const harnessVersion = "sg-go-rederive-1.0.0"

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "usage: sg <cell|run|env> [flags]")
		os.Exit(2)
	}
	mode := os.Args[1]
	fs := flag.NewFlagSet(mode, flag.ExitOnError)
	repo := fs.String("repo", "", "repository root")
	plan := fs.String("plan", "", "path to the child plan JSON (cell mode)")
	out := fs.String("out", "", "path the child writes its raw observation to (cell mode)")
	resDir := fs.String("results", "", "directory for per-cell JSON (run mode)")
	limit := fs.Int("timeout-ms", 5000, "externally enforced child timeout")
	only := fs.String("only", "", "run only rows whose key contains this substring (smoke test / single-cell re-run)")
	fs.Parse(os.Args[2:])

	switch mode {
	case "cell":
		if err := runChild(*plan, *out); err != nil {
			fmt.Fprintln(os.Stderr, "child error:", err)
			os.Exit(1)
		}
	case "run":
		if err := runParent(*repo, *resDir, int64(*limit), *only); err != nil {
			fmt.Fprintln(os.Stderr, "parent error:", err)
			os.Exit(1)
		}
	case "env":
		f := envFacts(*repo)
		b, _ := json.MarshalIndent(f, "", "  ")
		os.Stdout.Write(b)
		os.Stdout.Write([]byte("\n"))
	default:
		fmt.Fprintln(os.Stderr, "unknown mode", mode)
		os.Exit(2)
	}
}
