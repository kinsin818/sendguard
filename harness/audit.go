// SENDGUARD independent enumerator (audit instrument).
// Written by the taking-data local, NOT by any language worker (M3/M10).
// Shares zero code with the six measured implementations.
//
// Build:  CGO_ENABLED=0 go build -trimpath -o audit.exe .
// Usage:  audit.exe <dir>            -> JSON enumeration record on stdout
//         audit.exe <dir> --probe    -> also print env probe (S00 env metadata)
// All English, ASCII preferred (M21). Samples are referenced by hex only;
// forbidden-name entries are NEVER materialized as real filesystem paths here.
package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"runtime"
	"time"
	"unicode/utf16"
	"unicode/utf8"
)

const toolVersion = "0.1.0-s00"

type Entry struct {
	NameUTF8Hex   string `json:"name_utf8_hex"`
	NameUTF16Hex  string `json:"name_utf16le_hex"`
	NameCPHex     string `json:"name_codepoint_hex"`
	Size          int64  `json:"size"`
	Mode          string `json:"mode"`
	MtimeUnixNano int64  `json:"mtime_unix_nano"`
	SHA256        string `json:"sha256"`
	IsDir         bool   `json:"is_dir"`
}

type Output struct {
	Tool      string    `json:"tool"`
	Version   string    `json:"version"`
	OS        string    `json:"os"`
	GoVersion string    `json:"go_version"`
	Dir       string    `json:"dir"`
	StartedAt time.Time `json:"started_at"`
	Entries   []Entry   `json:"entries"`
}

func utf8Hex(s string) string     { return hex.EncodeToString([]byte(s)) }
func utf16leHex(s string) string  { u := utf16.Encode([]rune(s)); b := make([]byte, 0, len(u)*2); for _, c := range u { b = append(b, byte(c), byte(c>>8)) }; return hex.EncodeToString(b) }
func codepointHex(s string) string { out := ""; for _, r := range s { out += fmt.Sprintf("%04X", r) }; return out }

func sha256File(p string) (string, error) {
	f, err := os.Open(p)
	if err != nil {
		return "", err
	}
	defer f.Close()
	h := sha256.New()
	if _, err := io.Copy(h, f); err != nil {
		return "", err
	}
	return hex.EncodeToString(h.Sum(nil)), nil
}

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "usage: audit.exe <dir> [--probe]")
		os.Exit(2)
	}
	dir := os.Args[1]
	out := Output{
		Tool:      "sendguard-audit",
		Version:   toolVersion,
		OS:        runtime.GOOS + "/" + runtime.GOARCH,
		GoVersion: runtime.Version(),
		Dir:       dir,
		StartedAt: time.Now().UTC(),
	}
	entries, err := os.ReadDir(dir)
	if err != nil {
		fmt.Fprintln(os.Stderr, "readdir error:", err)
		os.Exit(1)
	}
	for _, de := range entries {
		name := de.Name()
		if !utf8.ValidString(name) {
			fmt.Fprintln(os.Stderr, "invalid utf8 name, skipping (hex:", utf8Hex(name), ")")
			continue
		}
		e := Entry{
			NameUTF8Hex:  utf8Hex(name),
			NameUTF16Hex: utf16leHex(name),
			NameCPHex:    codepointHex(name),
			IsDir:        de.IsDir(),
		}
		full := filepath.Join(dir, name)
		if info, err := os.Lstat(full); err == nil {
			e.Size = info.Size()
			e.Mode = info.Mode().String()
			e.MtimeUnixNano = info.ModTime().UnixNano()
		}
		if !de.IsDir() {
			if sum, err := sha256File(full); err == nil {
				e.SHA256 = sum
			}
		}
		out.Entries = append(out.Entries, e)
	}
	b, err := json.MarshalIndent(out, "", "  ")
	if err != nil {
		fmt.Fprintln(os.Stderr, "marshal error:", err)
		os.Exit(1)
	}
	os.Stdout.Write(b)
	os.Stdout.Write([]byte("\n"))
}
