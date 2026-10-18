package main

import (
	"encoding/hex"
	"fmt"
	"regexp"
	"strings"
	"unicode/utf16"
	"unicode/utf8"
)

// reservedRE mirrors ci/lint.py RESERVED_NAMES exactly, so the port's safety rule
// and the repo's tracked-name legality rule cannot drift apart.
var reservedRE = regexp.MustCompile(`(?i)^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9]|CONIN\$|CONOUT\$)(\..*)?$`)

func toHex(s string) string { return hex.EncodeToString([]byte(s)) }

func baseName(p string) string {
	p = strings.TrimPrefix(p, `\\?\`)
	if i := strings.LastIndexAny(p, `\/`); i >= 0 {
		return p[i+1:]
	}
	return p
}

// isReservedName reports whether the FINAL component addresses a Win32 device
// rather than a file in a directory. Such names may be created and listed, never
// opened or read (local order), and no payload may be transferred to them.
func isReservedName(name string) bool {
	return reservedRE.MatchString(baseName(name))
}

func utf16LEHex(s string) string {
	u := utf16.Encode([]rune(s))
	b := make([]byte, 0, len(u)*2)
	for _, c := range u {
		b = append(b, byte(c), byte(c>>8))
	}
	return hex.EncodeToString(b)
}

func codepointHex(s string) string {
	var b strings.Builder
	for _, r := range s {
		fmt.Fprintf(&b, "%04x", r)
	}
	return b.String()
}

// LenTriple is the counting-unit triple gate.md IV' asks for: code points,
// UTF-16 code units, UTF-8 bytes.
type LenTriple struct {
	CP    int `json:"cp"`
	UTF16 int `json:"utf16"`
	UTF8  int `json:"utf8"`
}

func lenTriple(s string) LenTriple {
	return LenTriple{
		CP:    utf8.RuneCountInString(s),
		UTF16: len(utf16.Encode([]rune(s))),
		UTF8:  len([]byte(s)),
	}
}

func (t LenTriple) String() string { return fmt.Sprintf("%d/%d/%d", t.CP, t.UTF16, t.UTF8) }

// DirLen is cell-identity.md §1's base_len: the length of the directory path with
// no trailing separator.
func dirLen(p string) int { return len(strings.TrimRight(p, `\`)) }

// BisectFace is one way of asking "can a name this long be created here". The
// three faces separate the three things that can actually refuse: this runtime's
// path handling, the Win32 parser below it, and the filesystem itself.
type BisectFace struct {
	Name     string
	Prefix   bool // address the directory through the \\?\ form
	BypassOS bool // call CreateFileW directly, skipping this runtime's path handling
}

// Face names are constants so a plan and the face it asks for cannot drift apart.
const (
	FaceOSPlain  = "os.Create(plain)"
	FaceRawPlain = "kernel32.CreateFileW(raw)"
	FacePrefix   = `explicit(\\?\)`
)

var bisectFaces = []BisectFace{
	{Name: FaceOSPlain, Prefix: false, BypassOS: false},
	{Name: FaceRawPlain, Prefix: false, BypassOS: true},
	{Name: FacePrefix, Prefix: true, BypassOS: true},
}

func faceByName(n string) BisectFace {
	for _, f := range bisectFaces {
		if f.Name == n {
			return f
		}
	}
	return bisectFaces[0]
}
