// SENDGUARD S02 C# port - per-cell child probe.
// BCL only (zero NuGet). One process per cell, invoked by impl/csharp/run_csharp.py.
// Contract discipline:
//   - names travel as HEX only (N12): this probe never prints or stores a raw sample name.
//   - reserved device names are CREATED and LISTED, never opened for content.
//   - no deletion logic anywhere (M19).
// Exit codes: 0 report written, 2 bad arguments, 3 instrument precondition failed.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.IO.Compression;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace SendGuardProbe
{
    internal static class Program
    {
        private const string CanonPayloadText = "SENDGUARD-CANON-PAYLOAD-2026"; // 28 bytes, per harness/ctrl-baseline.mjs
        private static readonly Regex ReservedRe =
            new Regex(@"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9]|CONIN\$|CONOUT\$)(\..*)?$",
                      RegexOptions.IgnoreCase | RegexOptions.Compiled);

        [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
        private static extern IntPtr CreateFileW(
            string lpFileName, uint dwDesiredAccess, uint dwShareMode, IntPtr lpSecurityAttributes,
            uint dwCreationDisposition, uint dwFlagsAndAttributes, IntPtr hTemplateFile);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool CloseHandle(IntPtr hObject);

        private const uint ShareAll = 0x00000001 | 0x00000002 | 0x00000004;
        private const uint CreateNew = 1;
        private const uint FileAttributeNormal = 0x00000080;

        private sealed class Opts
        {
            public string Mode = "point";
            public string Dir = "";
            public int BaseLen = -1;
            public string Shape = "name";
            public string NameHex = "";
            public int CompLen = 0;
            public char Fill = 'a';
            public string Entry = "File.WriteAllBytes";
            public string Form = "plain";
            public bool Legality;
            public string PayloadPolicy = "canon"; // canon | zero
            public string ReportPath = "";
            public int BisectLo = 1;
            public int BisectHi = 300;
            public List<string> ZipEntryHexes = new List<string>();
            public List<int> Points = new List<int>();
            public string CoNameHex = "";
            public string PayloadHex = "";
            public int PinnedLen = 0;
        }

        private static int Main(string[] argv)
        {
            var sw = Stopwatch.StartNew();
            var o = new Opts();
            try
            {
                ParseArgs(argv, o);
            }
            catch (Exception e)
            {
                Console.Error.WriteLine("args: " + e.GetType().Name + ": " + e.Message);
                return 2;
            }

            string policy = o.PayloadPolicy;
            byte[] payload;
            if (o.PayloadHex.Length > 0)
            {
                // rev6: the five control cells must hand the OS the PINNED bytes, so the payload
                // arrives as hex from the spec face instead of from a constant in this file.
                payload = HexBytes(o.PayloadHex);
                policy = "pinned-hex";
            }
            else if (o.PayloadPolicy == "zero")
            {
                payload = new byte[0];
            }
            else
            {
                payload = Encoding.UTF8.GetBytes(CanonPayloadText);
            }

            var report = new Dictionary<string, object>
            {
                {"mode", o.Mode},
                {"entry", o.Entry},
                {"form", o.Form},
                {"shape", o.Shape},
                {"payload_policy", policy},
                {"payload_bytes", payload.Length},
                {"sha256_payload_self", Hex(SHA256.HashData(payload))},
            };

            try
            {
                report["precondition"] = Precondition(o);
                if (!(bool)((Dictionary<string, object>)report["precondition"])["ok"])
                {
                    return WriteReport(o, report, sw); // precondition failed -> exit 3, no attempt made
                }

                string targetDir;
                report["dir_setup"] = Setup(o, o.CompLen, out targetDir);

                if (o.Mode == "bisect")
                {
                    report["bisect"] = Bisect(o, targetDir, payload);
                }
                else
                {
                    string name;
                    var created = new List<string>();
                    if (o.Mode == "len")
                    {
                        string primaryDir;
                        var lm = MeasureLen(o, o.Dir, payload, out primaryDir);
                        targetDir = primaryDir;
                        report["len_measure"] = lm;
                        name = new string(o.Fill, o.PinnedLen);
                        report["attempts"] = new List<object> { lm["primary"] };
                        foreach (object a in AllAttempts(lm))
                        {
                            created.Add((string)((Dictionary<string, object>)a)["name_hex"]);
                        }
                        // the bisection probes create entries too; every name this cell made has to
                        // be declared, otherwise a legitimate landing reads as a phantom later
                        foreach (object p in (List<object>)((Dictionary<string, object>)lm["bisect"])["probes"])
                        {
                            object hv;
                            if (((Dictionary<string, object>)p).TryGetValue("name_hex", out hv) && hv is string)
                            {
                                created.Add((string)hv);
                            }
                        }
                        created.Add(Hex(Encoding.UTF8.GetBytes(new string('w', 60))));
                    }
                    else
                    {
                        name = ResolveName(o);
                        report["attempts"] = new List<object> { Attempt(o, targetDir, name, payload, "create", o.Form) };
                        created.Add(Hex(Encoding.UTF8.GetBytes(name)));
                    }
                    report["name_hex"] = Hex(Encoding.UTF8.GetBytes(name));
                    report["name_utf16_units"] = name.Length;
                    report["name_code_points"] = CodePoints(name);
                    report["name_utf8_bytes"] = Encoding.UTF8.GetByteCount(name);
                    report["name_reserved"] = ReservedRe.IsMatch(name);
                    report["move_source_name"] = MoveSourceName(o, name);
                    report["created_names_hex"] = created;
                    report["target_dir_hex"] = Hex(Encoding.UTF8.GetBytes(targetDir));
                    report["target_dir_len"] = targetDir.Length;

                    // enumerate BEFORE the legality probe, so an entry the probe itself creates
                    // can never be mistaken for one the measured entry landed.
                    report["path_view_after_create"] = new Dictionary<string, object>
                    {
                        {"cell_dir", ViewOf(o.Dir, SafeEnumerate(o.Dir, o.Form))},
                        {"target_dir", ViewOf(targetDir, SafeEnumerate(targetDir, o.Form))},
                        {"target_entry_count", SafeEnumerate(targetDir, o.Form).Length},
                    };

                    if (o.CoNameHex.Length > 0)
                    {
                        report["coexistence"] = Coexist(o, targetDir, payload);
                    }

                    report["legality"] = o.Legality ? LegalityProbe(targetDir, name) : UnknownLegality();

                    report["path_view_after_legality"] = new Dictionary<string, object>
                    {
                        {"cell_dir", ViewOf(o.Dir, SafeEnumerate(o.Dir, o.Form))},
                        {"target_dir", ViewOf(targetDir, SafeEnumerate(targetDir, o.Form))},
                        {"target_entry_count", SafeEnumerate(targetDir, o.Form).Length},
                    };

                    if (o.ZipEntryHexes.Count > 0)
                    {
                        report["zip"] = ZipRoundtrip(o, targetDir, payload);
                    }
                }
            }
            catch (Exception e)
            {
                report["child_exception"] = Describe(e);
            }
            int rc = WriteReport(o, report, sw);
            return rc;
        }

        private static Dictionary<string, object> Precondition(Opts o)
        {
            if (!Directory.Exists(o.Dir))
            {
                return new Dictionary<string, object>
                {
                    {"scratch_exists", false}, {"entry_count", -1}, {"ok", false},
                    {"reason", "cell scratch dir absent before the child ran"}
                };
            }
            int n = SafeEnumerate(o.Dir, o.Form).Length;
            return new Dictionary<string, object>
            {
                {"scratch_exists", true}, {"entry_count", n}, {"ok", n == 0},
                {"reason", n == 0 ? "empty before attempt" : "scratch not empty before attempt"}
            };
        }

        // For shape=nested the file lives at the end of a chain of short directories whose
        // component lengths never approach the volume limit, so only the TOTAL length varies.
        // The returned target dir is always UNPREFIXED: the prefix is applied per call site, and
        // baking it in here would double it on every later join.
        // Chain components use 'w' so a chain dir can never collide with a probed file name
        // (nothing is deleted between probes, M19).
        private static Dictionary<string, object> Setup(Opts o, int x, out string targetDir)
        {
            targetDir = o.Dir;
            var row = new Dictionary<string, object> { {"attempted", o.Shape == "nested"}, {"ok", true} };
            if (o.Shape != "nested")
            {
                row["depth"] = 0;
                return row;
            }
            int depth = 0;
            try
            {
                while (x - 61 >= 1)
                {
                    targetDir = targetDir + "\\" + new string('w', 60);
                    Directory.CreateDirectory(Prefix(targetDir, o.Form));
                    x -= 61;
                    depth++;
                }
                row["created"] = depth;
                row["final_component_len"] = x;
                row["chain_char"] = "w";
            }
            catch (Exception e)
            {
                bool pre = PreSyscall(e);
                row["ok"] = false;
                row["error_stage"] = pre ? "parse" : "syscall";
                row["error_code"] = ErrorCode(e);
                row["error_message"] = Describe(e);
                row["created_before_failure"] = depth;
            }
            return row;
        }

        private static Dictionary<string, object> UnknownLegality()
        {
            return new Dictionary<string, object>
            {
                {"attempted", false}, {"verdict", "unknown"},
                {"reason", "no legality probe requested for this cell"}
            };
        }

        // ---------- one create attempt through one pinned entry ----------
        private static Dictionary<string, object> Attempt(Opts o, string dir, string name, byte[] payload,
                                                          string kind, string form)
        {
            string path = Combine(dir, name, form);
            var row = new Dictionary<string, object>
            {
                {"kind", kind},
                {"entry", o.Entry},
                {"form", form},
                {"path_hex", Hex(Encoding.UTF8.GetBytes(path))},
                {"path_len", path.Length},
                {"name_utf16_units", name.Length},
                {"name_hex", Hex(Encoding.UTF8.GetBytes(name))},
            };
            try
            {
                switch (o.Entry)
            {
                    case "File.WriteAllBytes":
                        File.WriteAllBytes(path, payload);
                        break;
                    case "File.Create":
                        using (FileStream fs = File.Create(path))
                        {
                            fs.Write(payload, 0, payload.Length);
                            fs.Flush(true);
                        }
                        break;
                    case "FileStream":
                        using (FileStream fs = new FileStream(path, FileMode.CreateNew, FileAccess.Write))
                        {
                            fs.Write(payload, 0, payload.Length);
                            fs.Flush(true);
                        }
                        break;
                    case "File.Move":
                        string src = Combine(dir, MoveSourceName(o, name), form);
                        File.WriteAllBytes(src, payload);
                        File.Move(src, path);
                        break;
                    default:
                        row["create_result"] = "err_at_syscall";
                        row["error_stage"] = "tool";
                        row["error_code"] = "unknown-entry";
                        row["error_message"] = "entry is not in the pinned csharp list: " + o.Entry;
                        return row;
                }
                row["create_result"] = "ok";
                row["error_stage"] = "null";
                row["bytes_written"] = payload.Length;
            }
            catch (Exception e)
            {
                bool pre = PreSyscall(e);
                row["create_result"] = pre ? "err_at_parse" : "err_at_syscall";
                row["error_stage"] = pre ? "parse" : "syscall";
                row["error_code"] = ErrorCode(e);
                row["error_message"] = Describe(e);
                row["bytes_written"] = null;
            }
            return row;
        }

        private static string MoveSourceName(Opts o, string name)
        {
            if (o.Entry != "File.Move") return null;
            return "sgsrc-" + o.Fill + "-" + name.Length + ".bin";
        }

        private static Dictionary<string, object> LegalityProbe(string dir, string name)
        {
            var row = new Dictionary<string, object> { {"attempted", false}, {"verdict", "unknown"} };
            if (name.IndexOf('\0') >= 0)
            {
                row["reason"] = "name carries U+0000: P/Invoke marshalling would truncate it, so the OS was not asked";
                return row;
            }
            // Ask the OS directly, not the language: \\?\ bypasses Win32 name parsing and
            // dwDesiredAccess=0 requests creation only - no content channel is opened, so a
            // reserved name is created and listed but never read.
            // It runs in its OWN subdirectory: whatever this probe lands must never be mistaken
            // for an entry the measured create attempt produced.
            string legDir = Path.Combine(dir, "leg");
            try { Directory.CreateDirectory(legDir); } catch { /* the probe below reports the real error */ }
            string path = @"\\?\" + Path.Combine(legDir, name);
            row["leg_dir_name"] = "leg";
            row["leg_dir_len_delta"] = 4;
            row["path_hex"] = Hex(Encoding.UTF8.GetBytes(path));
            row["mechanism"] = "prefix_rewrite(\\\\?\\) + dwDesiredAccess=0 + CREATE_NEW";
            IntPtr h = CreateFileW(path, 0u, ShareAll, IntPtr.Zero, CreateNew, FileAttributeNormal, IntPtr.Zero);
            row["attempted"] = true;
            // CreateFileW signals failure with INVALID_HANDLE_VALUE (-1), NOT with zero.
            if (h != IntPtr.Zero && h != new IntPtr(-1))
            {
                CloseHandle(h);
                row["verdict"] = "legal";
                row["winerror"] = 0;
                row["reason"] = "NTFS accepted the name; 0-byte entry created in the probe dir, no content handle opened";
                return row;
            }
            int err = Marshal.GetLastWin32Error();
            row["winerror"] = err;
            row["winerror_text"] = WinText(err);
            if (err == 183) // ERROR_FILE_EXISTS: the measured attempt already landed it
            {
                row["verdict"] = "legal";
                row["reason"] = "ERROR_FILE_EXISTS: the entry is present, so the OS allows this name to exist";
            }
            else
            {
                row["verdict"] = "illegal";
                row["reason"] = "refused even through the prefix that bypasses Win32 name parsing";
            }
            return row;
        }

        // T16 mechanism: does a ZIP entry name survive pack -> extract byte-identically,
        // and did the packer set the UTF-8 name flag (general purpose bit 11)?
        private static Dictionary<string, object> ZipRoundtrip(Opts o, string targetDir, byte[] payload)
        {
            var row = new Dictionary<string, object>
            {
                {"packer", "System.IO.Compression.ZipArchive"},
                {"extractor", "System.IO.Compression.ZipFile.ExtractToDirectory"},
                {"requested_entry_hexes", o.ZipEntryHexes},
            };
            string artifact = "_zipbuild.zip";
            string artifactPath = Path.Combine(targetDir, artifact);
            row["artifact_name_hex"] = Hex(Encoding.UTF8.GetBytes(artifact));
            try
            {
                byte[] archiveBytes;
                using (MemoryStream ms = new MemoryStream())
                {
                    using (ZipArchive za = new ZipArchive(ms, ZipArchiveMode.Create))
                    {
                        foreach (string h in o.ZipEntryHexes)
                        {
                            ZipArchiveEntry e = za.CreateEntry(HexDecode(h), CompressionLevel.NoCompression);
                            using (Stream es = e.Open())
                            {
                                es.Write(payload, 0, payload.Length);
                            }
                        }
                    }
                    archiveBytes = ms.ToArray();
                }
                File.WriteAllBytes(artifactPath, archiveBytes);
                row["artifact_bytes"] = archiveBytes.Length;

                var headers = new List<object>();
                for (int i = 0; i + 8 <= archiveBytes.Length; i++)
                {
                    if (archiveBytes[i] == 0x50 && archiveBytes[i + 1] == 0x4b
                        && archiveBytes[i + 2] == 0x03 && archiveBytes[i + 3] == 0x04)
                    {
                        int f = archiveBytes[i + 6] | (archiveBytes[i + 7] << 8);
                        headers.Add(new Dictionary<string, object>
                            { {"offset", i}, {"gp_flag_bits", f}, {"bit11_utf8_name", (f & 0x800) != 0} });
                    }
                }
                row["local_file_headers"] = headers;

                string dest = Path.Combine(targetDir, "_unz");
                ZipFile.ExtractToDirectory(artifactPath, dest);
                string[] landedEntries = Directory.GetFileSystemEntries(dest);
                row["extracted"] = ViewOf(dest, landedEntries);
                row["extracted_count"] = landedEntries.Length;
                var byHex = new Dictionary<string, bool>();
                foreach (object rr in (List<object>)row["extracted"])
                {
                    byHex[(string)((Dictionary<string, object>)rr)["name_hex"]] = true;
                }
                var survived = new List<object>();
                foreach (string h in o.ZipEntryHexes)
                {
                    survived.Add(new Dictionary<string, object> { {"entry_hex", h}, {"byte_identical", byHex.ContainsKey(h)} });
                }
                row["entry_roundtrip"] = survived;
                row["ok"] = true;
            }
            catch (Exception e)
            {
                row["ok"] = false;
                row["error_stage"] = PreSyscall(e) ? "parse" : "syscall";
                row["error_code"] = ErrorCode(e);
                row["error_message"] = Describe(e);
            }
            return row;
        }

        // ---------- one cell that answers a length question ----------
        // spec/cell-identity.md: a len cell's identity is (len, case_id, base_len). path_form is
        // NOT in that identity, so the extended-prefix leg cannot be a second record of the same
        // cell - the gate would read it as the port disagreeing with itself. It rides inside.
        private static Dictionary<string, object> MeasureLen(Opts o, string baseDir, byte[] payload,
                                                             out string primaryDir)
        {
            var bis = Bisect(o, baseDir, payload);
            int boundary = Convert.ToInt32(bis["boundary"]);
            var row = new Dictionary<string, object>
            {
                {"bisect", bis},
                {"boundary", boundary},
                {"boundary_at_instrument_ceiling", boundary >= o.BisectHi},
                {"bisect_lo", o.BisectLo},
                {"bisect_hi", o.BisectHi},
                {"shape", o.Shape},
            };
            // rev7 pins what the recorded component is made of: one code unit (U+0061) repeated to
            // exactly base_len code units, nothing appended. THAT component is the cell's measured
            // act, so name_source and len_triple describe it; the ceiling the bisection converged to
            // is a different quantity and travels as boundary/len_ceiling, never as a name width.
            string pd;
            row["primary"] = Attempt(o, baseDir, new string(o.Fill, o.PinnedLen), payload,
                                     "pinned-component", o.Form);
            primaryDir = baseDir;
            row["pinned_len"] = o.PinnedLen;
            row["fill_unit_hex"] = Hex(Encoding.UTF8.GetBytes(new string(o.Fill, 1)));
            row["boundary_attempt"] = AttemptLen(o, baseDir, boundary, payload, "at-boundary",
                                                 o.Form, o.Fill, out pd);
            if (boundary + 1 <= o.BisectHi)
            {
                string d2;
                row["boundary_plus1"] = AttemptLen(o, baseDir, boundary + 1, payload, "at-boundary-plus-1",
                                                   o.Form, o.Fill, out d2);
            }
            var pts = new List<object>();
            foreach (int x in o.Points)
            {
                string dp;
                pts.Add(AttemptLen(o, baseDir, x, payload, "tier-point", o.Form, o.Fill, out dp));
            }
            if (pts.Count > 0) row["tier_points"] = pts;
            return row;
        }

        private static Dictionary<string, object> AttemptLen(Opts o, string baseDir, int x, byte[] payload,
                                                             string kind, string form, char fill,
                                                             out string dir)
        {
            dir = baseDir;
            if (o.Shape == "nested")
            {
                string td;
                var setup = Setup(o, x, out td);
                dir = td;
                if (!(bool)setup["ok"])
                {
                    string nm = NameForLen(o, x, fill);
                    return new Dictionary<string, object>
                    {
                        {"kind", kind}, {"x", x}, {"entry", o.Entry}, {"form", form},
                        {"create_result", "err_at_syscall"}, {"error_stage", setup["error_stage"]},
                        {"error_code", setup["error_code"]}, {"error_message", setup["error_message"]},
                        {"name_hex", Hex(Encoding.UTF8.GetBytes(nm))},
                        {"name_utf16_units", nm.Length}, {"bytes_written", null},
                        {"dir_setup_failed", true}
                    };
                }
            }
            string name = NameForLen(o, x, fill);
            var row = Attempt(o, dir, name, payload, kind, form);
            row["x"] = x;
            return row;
        }

        private static string NameForLen(Opts o, int x, char fill)
        {
            if (o.Shape == "comp") return new string(fill, x);
            if (o.Shape == "nested") return new string(fill, FinalLen(x));
            return HexDecode(o.NameHex);
        }

        private static List<object> AllAttempts(Dictionary<string, object> lm)
        {
            var all = new List<object> { lm["primary"] };
            if (lm.ContainsKey("boundary_attempt")) all.Add(lm["boundary_attempt"]);
            if (lm.ContainsKey("boundary_plus1")) all.Add(lm["boundary_plus1"]);
            if (lm.ContainsKey("tier_points")) all.AddRange((List<object>)lm["tier_points"]);
            return all;
        }

        // T09's headline question is whether two spellings of one name COEXIST in one directory.
        // The required list makes T09-m1 and T09-m2 separate cells, each with its own scratch dir,
        // so the sibling is created here as evidence inside the cell instead of as a second record.
        private static Dictionary<string, object> Coexist(Opts o, string dir, byte[] payload)
        {
            string sibling = HexDecode(o.CoNameHex);
            string thisName = ResolveName(o);
            var attempts = new List<object>();
            attempts.Add(Attempt(o, dir, sibling, payload, "co-sibling", o.Form));
            string[] entries = SafeEnumerate(dir, o.Form);
            var hexes = new List<string>();
            foreach (string full in entries)
            {
                hexes.Add(Hex(Encoding.UTF8.GetBytes(Path.GetFileName(full.TrimEnd('\\')))));
            }
            return new Dictionary<string, object>
            {
                {"sibling_name_hex", o.CoNameHex},
                {"sibling_utf16_units", sibling.Length},
                {"this_cell_name_hex", Hex(Encoding.UTF8.GetBytes(thisName))},
                {"attempts", attempts},
                {"dir_entry_hexes", hexes},
                {"dir_entry_count", hexes.Count},
                {"same_name_hits_sibling", CountEqual(hexes, o.CoNameHex)},
                {"same_name_hits_this_cell", CountEqual(hexes, Hex(Encoding.UTF8.GetBytes(thisName)))},
                {"coexist", CountEqual(hexes, o.CoNameHex) == 1
                            && CountEqual(hexes, Hex(Encoding.UTF8.GetBytes(thisName))) == 1}
            };
        }

        private static int CountEqual(List<string> items, string value)
        {
            int n = 0;
            foreach (string s in items) { if (s == value) n++; }
            return n;
        }

        // ---------- length bisection (T-LEN) ----------
        private static Dictionary<string, object> Bisect(Opts o, string targetDir, byte[] payload)
        {
            int lo = o.BisectLo, hi = o.BisectHi;
            var probes = new List<object>();
            if (!Try(o, targetDir, lo, payload, probes))
            {
                return new Dictionary<string, object>
                {
                    {"lo", lo}, {"hi", hi}, {"boundary", 0}, {"conclusive", false},
                    {"probes_run", probes.Count},
                    {"reason", "smallest probe failed - no monotone interval"}, {"probes", probes}
                };
            }
            int a = lo, b = hi;
            if (Try(o, targetDir, hi, payload, probes))
            {
                return new Dictionary<string, object>
                {
                    {"lo", lo}, {"hi", hi}, {"boundary", hi}, {"conclusive", false},
                    {"probes_run", probes.Count},
                    {"reason", "largest probe succeeded - boundary is at least hi, interval did not bracket it"},
                    {"probes", probes}
                };
            }
            while (b - a > 1)
            {
                int mid = a + (b - a) / 2;
                if (Try(o, targetDir, mid, payload, probes)) a = mid; else b = mid;
            }
            return new Dictionary<string, object>
            {
                {"lo", lo}, {"hi", hi}, {"boundary", a}, {"conclusive", true},
                {"probes_run", probes.Count}, {"probes", probes}
            };
        }

        private static bool Try(Opts o, string targetDirBase, int x, byte[] payload, List<object> probes)
        {
            string dir = targetDirBase;
            if (o.Shape == "nested")
            {
                // rebuild the chain for this probe length, always starting from the cell dir
                string td;
                var setup = Setup(o, x, out td);
                dir = td;
                if (!(bool)setup["ok"])
                {
                    probes.Add(new Dictionary<string, object>
                    {
                        {"x", x}, {"kind", "bisect-probe"}, {"entry", o.Entry}, {"form", o.Form},
                        {"create_result", "err_at_syscall"}, {"error_stage", setup["error_stage"]},
                        {"error_code", setup["error_code"]}, {"error_message", setup["error_message"]},
                        {"name_utf16_units", FinalLen(x)}, {"bytes_written", null}
                    });
                    return false;
                }
            }
            string name = ResolveNamed(o, x);
            var row = Attempt(o, dir, name, payload, "bisect-probe", o.Form);
            row["x"] = x;
            probes.Add(row);
            return (string)row["create_result"] == "ok";
        }

        private static string ResolveNamed(Opts o, int x)
        {
            if (o.Shape == "comp") return new string(o.Fill, x);
            if (o.Shape == "nested") return new string(o.Fill, FinalLen(x));
            return HexDecode(o.NameHex);
        }

        // x code units split into a chain of (60 + separator) plus a final component
        private static int FinalLen(int x)
        {
            int k = 0;
            while (x - 61 * (k + 1) >= 1) k++;
            return x - 61 * k;
        }

        private static string ResolveName(Opts o)
        {
            if (o.Shape == "name") return HexDecode(o.NameHex);
            return ResolveNamed(o, o.CompLen);
        }

        private static byte[] HexBytes(string hex)
        {
            byte[] b = new byte[hex.Length / 2];
            for (int i = 0; i < b.Length; i++)
            {
                b[i] = byte.Parse(hex.Substring(i * 2, 2), NumberStyles.HexNumber, CultureInfo.InvariantCulture);
            }
            return b;
        }

        private static string HexDecode(string hex)
        {
            return Encoding.UTF8.GetString(HexBytes(hex));
        }

        private static string Prefix(string p, string form)
        {
            return form == "extended" ? @"\\?\" + p : p;
        }

        private static string Combine(string dir, string name, string form)
        {
            string p = dir.EndsWith("\\", StringComparison.Ordinal) ? dir + name : dir + "\\" + name;
            return Prefix(p, form);
        }

        private static string[] SafeEnumerate(string dir, string form)
        {
            try { return Directory.GetFileSystemEntries(Prefix(dir, form)); }
            catch { return new string[0]; }
        }

        private static List<object> ViewOf(string dir, string[] entries)
        {
            var rows = new List<object>();
            foreach (string full in entries)
            {
                string nm = Path.GetFileName(full.TrimEnd('\\'));
                var row = new Dictionary<string, object>
                {
                    {"name_hex", Hex(Encoding.UTF8.GetBytes(nm))},
                    {"name_utf16_units", nm.Length},
                    {"name_code_points", CodePoints(nm)},
                    {"name_utf8_bytes", Encoding.UTF8.GetByteCount(nm)},
                    {"reserved", ReservedRe.IsMatch(nm)},
                };
                try
                {
                    if (Directory.Exists(full))
                    {
                        row["is_dir"] = true;
                        row["size"] = null;
                    }
                    else
                    {
                        row["is_dir"] = false;
                        row["size"] = new FileInfo(full).Length;
                    }
                }
                catch (Exception e)
                {
                    row["is_dir"] = null;
                    row["size"] = null;
                    row["stat_error"] = Describe(e);
                }
                rows.Add(row);
            }
            return rows;
        }

        // .NET rejected the call in managed code before any syscall was issued.
        private static bool PreSyscall(Exception e)
        {
            return e is ArgumentException || e is ArgumentNullException || e is NotSupportedException
                   || e is PathTooLongException || e is UriFormatException;
        }

        private static string ErrorCode(Exception e)
        {
            int hr = e.HResult;
            int code = hr & 0xFFFF;
            if ((e is IOException || e is UnauthorizedAccessException || e is DirectoryNotFoundException
                 || e is PathTooLongException) && code != 0)
            {
                return "winerror=" + code.ToString(CultureInfo.InvariantCulture);
            }
            return e.GetType().Name + "(hresult=0x" + hr.ToString("X8", CultureInfo.InvariantCulture) + ")";
        }

        private static string Describe(Exception e)
        {
            string s = e.GetType().Name + ": " + e.Message;
            if (e.InnerException != null) s += " <- " + e.InnerException.GetType().Name + ": " + e.InnerException.Message;
            return s.Length > 400 ? s.Substring(0, 400) : s;
        }

        private static string WinText(int err)
        {
            try { return new System.ComponentModel.Win32Exception(err).Message; }
            catch { return ""; }
        }

        private static int CodePoints(string s)
        {
            int n = 0;
            for (int i = 0; i < s.Length; i++)
            {
                n++;
                if (char.IsHighSurrogate(s[i]) && i + 1 < s.Length && char.IsLowSurrogate(s[i + 1])) i++;
            }
            return n;
        }

        private static string Hex(byte[] bytes)
        {
            var sb = new StringBuilder(bytes.Length * 2);
            foreach (byte b in bytes) sb.Append(b.ToString("x2", CultureInfo.InvariantCulture));
            return sb.ToString();
        }

        private static void ParseArgs(string[] argv, Opts o)
        {
            for (int i = 0; i + 1 < argv.Length; i += 2)
            {
                string k = argv[i].TrimStart('-'), v = argv[i + 1];
                switch (k)
                {
                    case "mode": o.Mode = v; break;
                    case "dir": o.Dir = v; break;
                    case "base-len": o.BaseLen = int.Parse(v, CultureInfo.InvariantCulture); break;
                    case "shape": o.Shape = v; break;
                    case "name-hex": o.NameHex = v; break;
                    case "comp-len": o.CompLen = int.Parse(v, CultureInfo.InvariantCulture); break;
                    case "fill": o.Fill = v.Length > 0 ? v[0] : 'a'; break;
                    case "entry": o.Entry = v; break;
                    case "form": o.Form = v; break;
                    case "legality": o.Legality = v == "1"; break;
                    case "payload": o.PayloadPolicy = v; break;
                    case "report": o.ReportPath = v; break;
                    case "bisect-lo": o.BisectLo = int.Parse(v, CultureInfo.InvariantCulture); break;
                    case "bisect-hi": o.BisectHi = int.Parse(v, CultureInfo.InvariantCulture); break;
                    case "zip-entry-hexes":
                        foreach (string h in v.Split(','))
                        {
                            if (h.Length > 0) o.ZipEntryHexes.Add(h);
                        }
                        break;
                    case "points":
                        foreach (string p in v.Split(','))
                        {
                            if (p.Length > 0) o.Points.Add(int.Parse(p, CultureInfo.InvariantCulture));
                        }
                        break;
                    case "co-name-hex": o.CoNameHex = v; break;
                    case "payload-hex": o.PayloadHex = v; break;
                    case "pinned-len": o.PinnedLen = int.Parse(v, CultureInfo.InvariantCulture); break;
                    default: throw new ArgumentException("unknown flag " + k);
                }
            }
            if (o.ReportPath == "" || o.Dir == "") throw new ArgumentException("--dir and --report are required");
            if (o.Mode == "len" && o.PinnedLen < 1)
            {
                throw new ArgumentException("--mode len requires --pinned-len (rev7 pins the recorded "
                                           + "component; without it the cell would describe an empty name)");
            }
        }

        private static int WriteReport(Opts o, Dictionary<string, object> report, Stopwatch sw)
        {
            report["elapsed_child_ms"] = sw.ElapsedMilliseconds;
            bool pre = report.ContainsKey("precondition")
                       && (bool)((Dictionary<string, object>)report["precondition"])["ok"];
            report["instrument_ok"] = pre && !report.ContainsKey("child_exception");
            string json = JsonSerializer.Serialize(report);
            File.WriteAllText(o.ReportPath, json, new UTF8Encoding(false));
            Console.Write("REPORT_WRITTEN");
            return pre ? 0 : 3;
        }
    }
}
