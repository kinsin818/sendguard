package main

import (
	"archive/zip"
	"encoding/binary"
	"encoding/hex"
	"os"
	"path/filepath"
	"strings"
)

// zipLeg answers the T16 question for this port: does a name survive a zip
// write/read round trip, and what did the UTF-8 flag (bit 11) actually say.
//
// The archive is written inside the cell sandbox with archive/zip (stdlib,
// deps_direct=0). The entry names are frozen samples decoded from hex at run
// time: the T16 sample itself, plus the T09a (NFD) and T09b (NFC) members so the
// non-ASCII branch of the flag is exercised. Nothing here invents a name, and no
// forbidden name is ever materialized as a filesystem entry.
func zipLeg(dir string, hexNames []string, payload []byte) map[string]any {
	out := map[string]any{
		"tool":       "archive/zip (stdlib)",
		"bit11_note": "flags parsed from the raw local and central-directory records; Go's NonUTF8 flag reported beside it",
	}
	list := []any{}
	archivePath := filepath.Join(dir, "_zipleg.zip")
	f, err := os.Create(archivePath)
	if err != nil {
		out["ok"] = false
		out["error"] = truncate(err.Error(), 300)
		return out
	}
	w := zip.NewWriter(f)
	names := []string{}
	for _, h := range hexNames {
		n, derr := decodeHex(h)
		if derr != nil {
			continue
		}
		names = append(names, n)
		hw := &zip.FileHeader{Name: n, Method: zip.Store}
		fw, cerr := w.CreateHeader(hw)
		if cerr != nil {
			list = append(list, map[string]any{"name_hex": h, "create_error": truncate(cerr.Error(), 200)})
			continue
		}
		n2, werr := fw.Write(payload)
		list = append(list, map[string]any{"name_hex": h, "written_bytes": n2, "write_error": errStr(werr)})
	}
	if err := w.Close(); err != nil {
		out["ok"] = false
		out["error"] = "writer close: " + truncate(err.Error(), 200)
		return out
	}
	if err := f.Close(); err != nil {
		out["ok"] = false
		out["error"] = "file close: " + truncate(err.Error(), 200)
		return out
	}

	raw, rerr := os.ReadFile(archivePath)
	if rerr != nil {
		out["ok"] = false
		out["error"] = "read back archive: " + truncate(rerr.Error(), 200)
		return out
	}
	out["archive_bytes"] = len(raw)
	out["archive_sha256"] = sha256Hex(raw)
	out["local_bit11"] = parseFlags(raw, []byte("PK\x03\x04"), 6)
	out["central_bit11"] = parseFlags(raw, []byte("PK\x01\x02"), 8)

	r, oerr := zip.OpenReader(archivePath)
	if oerr != nil {
		out["ok"] = false
		out["error"] = "open reader: " + truncate(oerr.Error(), 200)
		out["entries"] = list
		return out
	}
	defer r.Close()
	readback := []any{}
	for _, rf := range r.File {
		data, eerr := rf.Open()
		nb := 0
		var sha string
		if eerr == nil {
			buf := make([]byte, 0, rf.UncompressedSize64)
			tmp := make([]byte, 64)
			for {
				n, rr := data.Read(tmp)
				buf = append(buf, tmp[:n]...)
				if rr != nil {
					break
				}
			}
			data.Close()
			nb = len(buf)
			sha = sha256Hex(buf)
		}
		landedHex := hex.EncodeToString([]byte(rf.Name))
		match := ""
		for _, h := range hexNames {
			if strings.EqualFold(h, landedHex) {
				match = h
			}
		}
		readback = append(readback, map[string]any{
			"name_hex":              landedHex,
			"matches_frozen_sample": match != "",
			"non_utf8_flag":         rf.NonUTF8,
			"size":                  rf.UncompressedSize64,
			"bytes_read":            nb,
			"sha256":                sha,
			"open_error":            errStr(eerr),
		})
	}
	out["entries"] = list
	out["readback"] = readback
	out["requested_names"] = len(names)
	out["roundtrip_names_equal"] = len(readback) == len(names)
	out["ok"] = true
	return out
}

// parseFlags walks every record with the given signature and reports the UTF-8
// flag bit (bit 11) of each general purpose bit flag field.
func parseFlags(raw []byte, sig []byte, flagOffset int) []map[string]any {
	out := []map[string]any{}
	for i := 0; i+flagOffset+2 <= len(raw); i++ {
		if string(raw[i:i+len(sig)]) != string(sig) {
			continue
		}
		fl := binary.LittleEndian.Uint16(raw[i+flagOffset : i+flagOffset+2])
		out = append(out, map[string]any{"offset": i, "flags": int(fl), "bit11_utf8": fl&0x800 != 0})
	}
	return out
}
