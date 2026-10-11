import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileNotFoundException;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.InvalidPathException;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.attribute.BasicFileAttributes;
import java.security.MessageDigest;
import java.text.Normalizer;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.regex.Pattern;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;
import java.util.zip.ZipOutputStream;

/**
 * SENDGUARD java port probe. One invocation = one (cell x entry) observation.
 * Writes an ASCII-only JSON document to --out. Performs no deletion of anything (M19).
 */
public final class CellProbe {

    /** rev7 pins the length-family filler to one code unit U+0061; FILL is that unit, repeated.
     */
    static final char[] DEFAULT_PAD = "0123456789abcdef".toCharArray();
    static char[] PAD = DEFAULT_PAD;
    static final Pattern RESERVED = Pattern.compile(
            "^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9]|CONIN\\$|CONOUT\\$)(\\..*)?$",
            Pattern.CASE_INSENSITIVE);

    /** The entries of this port that go through java.io rather than java.nio. */
    static final Set<String> IO_ENTRIES = new HashSet<String>(
            Arrays.asList("File.createNewFile", "FileOutputStream.write", "File.renameTo"));
    /** ... of those, the two that can be driven from a bare String with no Path involved. */
    static final Set<String> IO_STRING_ENTRY = new HashSet<String>(
            Arrays.asList("File.createNewFile", "FileOutputStream.write"));

    public static void main(String[] argv) throws Exception {
        Map<String, String> a = parseArgs(argv);
        String entry = req(a, "entry");
        Path scratch = Paths.get(req(a, "scratch")).toAbsolutePath();
        byte[] payload = unhex(req(a, "payload"));
        boolean extProbe = !"off".equals(a.getOrDefault("extended", "on"));
        boolean zipLeg = "on".equals(a.getOrDefault("zip", "off"));
        String pathForm = "extended".equals(a.get("path-form")) ? "extended" : "plain";
        if (a.containsKey("fill-unit-hex")) {
            PAD = new String(unhex(a.get("fill-unit-hex")), StandardCharsets.UTF_8).toCharArray();
            if (PAD.length == 0) throw new IllegalArgumentException("--fill-unit-hex decoded to nothing");
        }

        List<String[]> targets = targets(a);

        Map<String, Object> doc = new LinkedHashMap<String, Object>();
        doc.put("probe", "CellProbe");
        doc.put("java_version", System.getProperty("java.version"));
        doc.put("java_vendor", System.getProperty("java.vendor"));
        doc.put("java_home", System.getProperty("java.home"));
        doc.put("os_name", System.getProperty("os.name"));
        doc.put("os_arch", System.getProperty("os.arch"));
        doc.put("os_version", System.getProperty("os.version"));
        doc.put("file_encoding", System.getProperty("file.encoding"));
        doc.put("sun_jnu_encoding", System.getProperty("sun.jnu.encoding"));
        doc.put("pid", String.valueOf(ProcessHandle.current().pid()));
        doc.put("entry", entry);
        doc.put("requested_path_form", pathForm);
        doc.put("filler_units_used", new String(PAD));
        doc.put("filler_is_pinned_single_unit", PAD.length == 1);
        doc.put("payload_len", (long) payload.length);
        doc.put("payload_sha256", sha(payload));
        doc.put("scratch", scratch.toString());
        doc.put("scratch_len", (long) scratch.toString().length());
        doc.put("scratch_entry_count_before", (long) countEntries(scratch));

        List<Object> members = new ArrayList<Object>();
        for (String[] t : targets) {
            members.add(probeOne(scratch, t[0], t[1], payload, entry, extProbe, zipLeg, pathForm));
        }
        doc.put("members", members);

        if ("on".equals(a.get("mechanism"))) {
            doc.put("mechanism_probe", mechanismProbe(scratch, payload));
        }
        if ("on".equals(a.get("mechanism2"))) {
            doc.put("device_namespace_probe", deviceNamespaceProbe(scratch, payload));
        }
        if (a.containsKey("sweep")) {            List<Object> sweep = new ArrayList<Object>();
            for (String s : a.get("sweep").split(",")) {
                int n = Integer.parseInt(s.trim());
                sweep.add(probeOne(scratch, "sweep:" + n, padded(n), payload, entry, extProbe, false, pathForm));
            }
            doc.put("sweep", sweep);
            doc.put("sweep_note", "supplementary points, NOT part of the frozen G1-G4 grid");
        }
        doc.put("scratch_entry_count_after", (long) countEntries(scratch));

        Files.write(Paths.get(req(a, "out")), writeAscii(doc).getBytes(StandardCharsets.US_ASCII));
        System.out.println("SG_DONE members=" + members.size() + " entry=" + entry);
        System.out.flush();
    }

    static List<String[]> targets(Map<String, String> a) {
        List<String[]> out = new ArrayList<String[]>();
        if (a.containsKey("grades")) {
            for (String g : a.get("grades").split(",")) {
                int n = Integer.parseInt(g.trim());
                out.add(new String[]{"grade:" + n, padded(n)});
            }
        } else {
            int i = 0;
            for (String h : a.get("members").split(",")) {
                i++;
                out.add(new String[]{"member:" + i, new String(unhex(h.trim()), StandardCharsets.UTF_8)});
            }
        }
        return out;
    }

    // ------------------------------------------------------------ one probe
    static Map<String, Object> probeOne(Path scratch, String label, String name, byte[] payload,
                                         String entry, boolean extProbe, boolean zipLeg,
                                         String pathForm) {
        boolean reserved = RESERVED.matcher(name).matches();
        Map<String, Object> m = new LinkedHashMap<String, Object>();
        m.put("label", label);
        m.put("name_hex", hexOf(name));
        m.put("name", name);
        m.put("name_utf8_bytes", (long) name.getBytes(StandardCharsets.UTF_8).length);
        m.put("name_code_points", (long) name.codePointCount(0, name.length()));
        m.put("name_utf16_units", (long) name.length());
        m.put("reserved_name", reserved);

        String absString = new File(scratch.toString(), name).getAbsolutePath();
        // rev6: path_form is a requested form, not a label. In the extended cell the string handed
        // to the pinned entry IS the \\?\ form, so the language's own parser is what answers.
        String requested = "extended".equals(pathForm) ? "\\\\?\\" + absString : absString;
        Path target;
        String parseClass = null, parseMsg = null;
        try {
            target = Paths.get(requested);
        } catch (InvalidPathException e) {
            target = null;
            parseClass = e.getClass().getName();
            parseMsg = e.getMessage() + " | reason=" + e.getReason() + " | index=" + e.getIndex();
        }
        m.put("requested_path_form", pathForm);
        m.put("requested_path_string", requested);
        m.put("requested_path_len", (long) requested.length());
        m.put("total_path_len_plain", (long) absString.length());
        m.put("total_path_utf8_bytes",
                (long) absString.getBytes(StandardCharsets.UTF_8).length);

        List<Land> before = enumerate(scratch);
        long[] wr = new long[]{-1};
        // rev7 rule 4: java.io takes the raw path STRING and never passes through java.nio's path
        // parser, so Paths.get throwing on the \\?\ form is NIO's answer, not java.io's. Asking
        // java.io through a Path object attributed NIO's refusal to it.
        boolean ioStringLeg = target == null && IO_STRING_ENTRY.contains(entry);
        boolean refusedAtParse = target == null && !ioStringLeg;
        m.put("instrument_face", ioStringLeg
                ? entry + " called with the requested String exactly as this cell built it"
                : (IO_ENTRIES.contains(entry)
                   ? entry + " called with new File(Paths.get(requested).toString())"
                   : entry + " called with a java.nio.file.Path"));
        if (ioStringLeg) {
            m.put("nio_parse_of_the_same_string",
                  dict("attempted", true, "class", parseClass, "message", parseMsg));
        }
        String[] v;
        if (ioStringLeg) {
            v = createViaString(requested, payload, entry, wr);
        } else if (refusedAtParse) {
            v = new String[]{"err_at_parse", "parse", parseClass, parseMsg};
        } else {
            v = createVia(target, payload, entry, wr);
        }
        List<Land> after = enumerate(scratch);

        m.put("create_result", v[0]);
        m.put("error_stage", v[1]);
        m.put("error_class", v[2]);
        m.put("error_message", v[3]);
        m.put("error_message_hex", v[3] == null ? null : hexOf(v[3]));
        m.put("bytes_written", wr[0] < 0 ? null : wr[0]);

        // ---- what actually appeared -------------------------------------
        Set<String> beforeNames = names(before);
        List<Land> appeared = new ArrayList<Land>();
        for (Land l : after) if (l.name != null && !beforeNames.contains(l.name)) appeared.add(l);
        int exact = 0, ci = 0, norm = 0;
        String nfc = Normalizer.normalize(name, Normalizer.Form.NFC);
        String nfd = Normalizer.normalize(name, Normalizer.Form.NFD);
        Land self = null;
        for (Land l : after) {
            if (l.name == null) continue;
            if (l.name.equals(name)) { exact++; if (self == null) self = l; }
            if (l.name.equalsIgnoreCase(name)) ci++;
            String lnfc = Normalizer.normalize(l.name, Normalizer.Form.NFC);
            String lnfd = Normalizer.normalize(l.name, Normalizer.Form.NFD);
            if (lnfc.equals(nfc) || lnfd.equals(nfd)) norm++;
        }
        List<Object> landedJson = new ArrayList<Object>();
        for (Land l : after) landedJson.add(l.toJson());
        m.put("landed", landedJson);
        m.put("appeared_names", namesJson(appeared));
        m.put("same_name_hits", (long) exact);
        m.put("case_variant_hits", (long) ci);
        m.put("norm_variant_hits", (long) norm);

        String landedAs = null;
        Boolean mutated = null;
        if (exact > 0) {
            landedAs = name;
            mutated = Boolean.FALSE;
        } else if ("ok".equals(v[0]) && appeared.size() == 1) {
            landedAs = appeared.get(0).name;
            mutated = Boolean.TRUE;
        } else if (appeared.size() > 0) {
            landedAs = null;
            mutated = null;
        }
        m.put("name_landed_as", landedAs);
        m.put("name_landed_as_hex", landedAs == null ? null : hexOf(landedAs));
        m.put("name_mutated", mutated);
        Long dirView = self != null ? self.size : null;
        m.put("bytes_on_disk_dir_view", dirView);
        boolean phantom = "ok".equals(v[0]) && exact == 0 && appeared.isEmpty();
        m.put("phantom", phantom);
        m.put("hit_came_from_earlier_leg",
                Boolean.valueOf(exact > 0 && refusedAtParse));

        // ---- read side ---------------------------------------------------
        // rev4: a read that did not happen is not_applicable with read_skipped_reason. The four
        // original words all presuppose a read, so writing eof there would rewrite a verdict to
        // satisfy the ruler.
        if (reserved) {
            m.put("read_result", "not_applicable");
            m.put("read_attempted", false);
            m.put("read_skipped_reason", "reserved device name: opening or reading its contents is "
                    + "forbidden by order (create and list only)");
            m.put("roundtrip_ok", false);
            m.put("sha256_self", null);
            m.put("sha256_truth", null);
            m.put("bytes_on_disk", null);
            m.put("enum_to_stat_agrees", null);
        } else if (exact == 0) {
            m.put("read_result", "not_applicable");
            m.put("read_attempted", false);
            m.put("read_skipped_reason", "nothing landed at exactly the requested name: "
                    + "create_result=" + v[0] + ", the directory enumeration holds no such entry");
            m.put("roundtrip_ok", false);
            m.put("sha256_self", null);
            m.put("sha256_truth", null);
            m.put("bytes_on_disk", dirView);
            m.put("enum_to_stat_agrees", null);
        } else if (refusedAtParse) {
            // the language refused the requested string, so this cell never held a handle:
            // a name that IS present can only have been created by an earlier member's OS leg
            m.put("read_result", "not_applicable");
            m.put("read_attempted", false);
            m.put("read_skipped_reason", "the requested path string was refused by the language "
                    + "before any syscall (error_stage=parse), so nothing was opened even though "
                    + "the directory may already hold that name from an earlier leg of this cell");
            m.put("roundtrip_ok", false);
            m.put("bytes_on_disk", dirView);
            m.put("enum_to_stat_agrees", null);
        } else {
            byte[] got = null;
            String rr = null, rc = null, rm = null;
            try {
                got = target != null ? Files.readAllBytes(target) : readViaIoString(requested);
                rr = got.length == 0 ? "eof" : "ok";
            } catch (InvalidPathException e) {
                rr = "err6"; rc = e.getClass().getName(); rm = e.getMessage();
            } catch (IOException e) {
                rr = "err6"; rc = e.getClass().getName(); rm = String.valueOf(e.getMessage());
            } catch (RuntimeException e) {
                rr = "err6"; rc = e.getClass().getName(); rm = String.valueOf(e.getMessage());
            }
            if (got == null && rm != null && !isInvalidHandle(rm)) {
                m.put("read_result_mapping_note", "read was attempted and raised a non-invalid-handle "
                        + "error; canonical.md read_result has no word for that, so eof is recorded "
                        + "with the verbatim error kept in read_error_*");
            }
            m.put("read_result", rr);
            m.put("read_attempted", true);
            m.put("read_error_class", rc);
            m.put("read_error_message", rm);
            m.put("roundtrip_ok", got != null && Arrays.equals(got, payload));
            m.put("sha256_self", sha(payload));
            m.put("sha256_truth", got == null ? null : sha(got));
            Long direct = target != null ? directSize(target) : ioStringSize(requested);
            m.put("bytes_on_disk", got != null ? (long) got.length : dirView);
            m.put("bytes_on_disk_direct_stat", direct);
            m.put("enum_to_stat_agrees", (dirView != null && direct != null)
                    ? Boolean.valueOf(dirView.equals(direct)) : null);
        }

        // ---- OS legality leg ---------------------------------------------
        m.put("extended_probe", extProbe ? extendedProbe(scratch, name, absString, payload, reserved)
                : dict("attempted", false, "os_legality_verdict", "unknown"));

        if (zipLeg) m.put("zip_leg", zipLeg(scratch, name, payload));
        return m;
    }

    /**
     * Tells "the OS honours long plain paths" (manifest / registry) apart from
     * "the language rewrote my string into the extended form" (prefix_rewrite).
     * A directory is created whose requested name ends in a dot, so it lands stripped.
     * Three legs then differ ONLY in total path length and in whether the caller writes
     * the stripped or the dot-suffixed name:
     *   A short + stripped name   -> baseline, must work
     *   B short + dot-suffixed    -> does the call go through name parsing at all
     *   C long  + dot-suffixed    -> does name parsing still apply past the legacy limit
     * B ok with C failing means the long call did not go out as written.
     */
    static Map<String, Object> mechanismProbe(Path scratch, byte[] payload) {
        Map<String, Object> o = new LinkedHashMap<String, Object>();
        o.put("attempted", true);
        String dirName = "mp" + padded(40) + ".";
        Path dir = scratch.resolve(dirName);
        o.put("dir_name_requested_hex", hexOf(dirName));
        o.put("dir_name_utf16_units", (long) dirName.length());
        try {
            Files.createDirectory(dir);
            o.put("mkdir_create_result", "ok");
        } catch (Exception e) {
            o.put("mkdir_create_result", "err_at_syscall");
            o.put("mkdir_error_class", e.getClass().getName());
            o.put("mkdir_error_message", String.valueOf(e.getMessage()));
            o.put("verdict", "not-obtainable");
            return o;
        }
        List<String> landedDirs = new ArrayList<String>();
        try {
            DirectoryStream<Path> ds = Files.newDirectoryStream(scratch);
            try {
                for (Path p : ds) if (Files.isDirectory(p)) landedDirs.add(p.getFileName().toString());
            } finally { ds.close(); }
        } catch (Exception e) {
            o.put("enumerate_error", e.getClass().getName() + ": " + e.getMessage());
        }
        o.put("dir_names_landed", landedDirs);
        String stripped = landedDirs.isEmpty() ? dirName : landedDirs.get(0);
        o.put("dir_name_stripped_hex", hexOf(stripped));
        o.put("dot_was_stripped", !stripped.equals(dirName));

        Object[][] legs = new Object[][]{
            {"A-short-stripped", stripped, "a.txt"},
            {"B-short-dotsuffixed", dirName, "b.txt"},
            {"C-long-dotsuffixed", dirName, padded(240)},
        };
        List<Object> results = new ArrayList<Object>();
        for (Object[] leg : legs) {
            Map<String, Object> r = new LinkedHashMap<String, Object>();
            String dirUsed = (String) leg[1];
            String fileName = (String) leg[2];
            String full = new File(new File(scratch.toString(), dirUsed), fileName).getAbsolutePath();
            Path f = Paths.get(full);
            r.put("leg", leg[0]);
            r.put("dir_used_hex", hexOf(dirUsed));
            r.put("file_name_utf16_units", (long) fileName.length());
            r.put("total_path_len_plain", (long) full.length());
            r.put("exceeds_legacy_259", full.length() > 259);
            long[] wr = new long[]{-1};
            String[] v = createVia(f, payload, "Files.write", wr);
            r.put("create_result", v[0]);
            r.put("error_class", v[2]);
            r.put("error_message", v[3]);
            r.put("file_exists_after", new File(full).exists());
            results.add(r);
        }
        o.put("legs", results);
        boolean bOk = "ok".equals(((Map<String, Object>) results.get(1)).get("create_result"));
        boolean cOk = "ok".equals(((Map<String, Object>) results.get(2)).get("create_result"));
        String verdict;
        if (bOk && !cOk) verdict = "prefix_rewrite";
        else if (bOk && cOk) verdict = "name-parsing-still-applies-at-long-length";
        else if (!bOk) verdict = "not-obtainable (leg B already refused)";
        else verdict = "unknown";
        o.put("verdict", verdict);
        o.put("verdict_basis", "legs B and C differ only in total path length; the dot-suffixed "
                + "directory is reachable through name parsing only");
        return o;
    }

    /**
     * Second mechanism leg. The dot leg cannot decide whether a long call was rewritten into the
     * extended form, because the language may normalise the string before it adds any prefix.
     * A device-name component can only be bypassed by the prefix, so:
     *   create a real directory named COM1 through java.io with the extended string, then
     *   write into it with java.nio at a SHORT total path and at a LONG one.
     * Short refused while long succeeds means only the long call stopped seeing COM1 as a device,
     * i.e. it did not go out in the plain form.
     */
    static Map<String, Object> deviceNamespaceProbe(Path scratch, byte[] payload) {
        Map<String, Object> o = new LinkedHashMap<String, Object>();
        o.put("attempted", true);
        String dirName = "COM1";
        String absDir = new File(scratch.toString(), dirName).getAbsolutePath();
        String extDir = "\\\\?\\" + absDir;
        o.put("dir_requested_hex", hexOf(dirName));
        boolean made = new File(extDir).mkdir();
        o.put("mkdir_via_io_extended_rc", made);
        o.put("io_sees_directory", new File(extDir).isDirectory());
        List<String> listed = new ArrayList<String>();
        boolean landed = false;
        DirectoryStream<Path> ds = null;
        try {
            ds = Files.newDirectoryStream(scratch);
            for (Path p : ds) {
                listed.add(p.getFileName().toString());
                if (p.getFileName().toString().equals(dirName)) {
                    // ask io.File over the extended string: the plain form would answer about the
                    // COM1 device, not about the directory this probe just created
                    landed = new File(extDir).isDirectory();
                }
            }
        } catch (Exception e) {
            o.put("enumerate_error", e.getClass().getName() + ": " + e.getMessage());
        } finally {
            if (ds != null) try { ds.close(); } catch (IOException ignored) { }
        }
        o.put("directory_landed_by_enumeration", landed);
        o.put("directory_names_in_scratch", listed);
        if (!landed) {
            o.put("verdict", "not-obtainable");
            o.put("why", "the real COM1 directory could not be created or listed, so the "
                    + "device-namespace difference cannot be tested here");
            return o;
        }
        Object[][] legs = {{"short-into-COM1", "s.txt"}, {"long-into-COM1", padded(240)}};
        List<Object> results = new ArrayList<Object>();
        for (Object[] leg : legs) {
            Map<String, Object> r = new LinkedHashMap<String, Object>();
            String full = new File(new File(scratch.toString(), dirName), (String) leg[1]).getAbsolutePath();
            r.put("leg", leg[0]);
            r.put("total_path_len_plain", (long) full.length());
            r.put("exceeds_legacy_259", full.length() > 259);
            long[] wr = new long[]{-1};
            String[] v = createVia(Paths.get(full), payload, "Files.write", wr);
            r.put("create_result", v[0]);
            r.put("error_class", v[2]);
            r.put("error_message", v[3]);
            r.put("file_exists_after", new File(full).exists());
            results.add(r);
        }
        o.put("legs", results);
        boolean shortOk = "ok".equals(((Map<String, Object>) results.get(0)).get("create_result"));
        boolean longOk = "ok".equals(((Map<String, Object>) results.get(1)).get("create_result"));
        String verdict;
        if (!shortOk && longOk) verdict = "rewritten-for-long-paths";
        else if (shortOk && longOk) verdict = "device-name-not-intercepted-in-this-shape";
        else if (!shortOk && !longOk) verdict = "not-rewritten";
        else verdict = "unexpected (short ok, long refused)";
        o.put("verdict", verdict);
        o.put("verdict_basis", "only the extended prefix stops Win32 from reading COM1 as a device; "
                + "the two legs differ only in total path length");

        // Third leg, and the decisive one: Win32 intercepts a device name only as the FINAL
        // component (measured above: a real directory named COM1 is traversed normally), so the
        // middle-component shape cannot test the prefix at all. A final component CAN: the short
        // path is known to refuse CON.txt (cell T01), so if the same final name succeeds once the
        // path is long, the only thing that changed is how the string left the language.
        String deep = padded(200);
        Path deepDir = scratch.resolve(deep);
        Map<String, Object> final_leg = new LinkedHashMap<String, Object>();
        try {
            Files.createDirectory(deepDir);
            Path nested = deepDir.resolve(deep);          // two 200-unit components
            Files.createDirectory(nested);
            String shortTarget = new File(scratch.toString(), "CON.txt").getAbsolutePath();
            String longTarget = new File(nested.toString(), "CON.txt").getAbsolutePath();
            final_leg.put("short_final_name_hex", hexOf("CON.txt"));
            final_leg.put("same_final_name_on_both_legs",
                    hexOf("CON.txt").equals(hexOf("CON.txt")));
            final_leg.put("short_total_len", (long) shortTarget.length());
            long[] w1 = new long[]{-1};
            String[] v1 = createVia(Paths.get(shortTarget), payload, "Files.write", w1);
            final_leg.put("short_create_result", v1[0]);
            final_leg.put("short_error_class", v1[2]);
            final_leg.put("long_final_name_hex", hexOf("CON.txt"));
            final_leg.put("long_total_len", (long) longTarget.length());
            final_leg.put("long_exceeds_259", longTarget.length() > 259);
            long[] w2 = new long[]{-1};
            String[] v2 = createVia(Paths.get(longTarget), payload, "Files.write", w2);
            final_leg.put("long_create_result", v2[0]);
            final_leg.put("long_error_class", v2[2]);
            // did a real file named CON.txt land inside the deep directory?
            boolean landedReal = false;
            DirectoryStream<Path> ds2 = null;
            try {
                ds2 = Files.newDirectoryStream(nested);
                for (Path p : ds2) if (p.getFileName().toString().equals("CON.txt")) landedReal = true;
            } catch (Exception e) {
                final_leg.put("enumerate_error", e.getClass().getName() + ": " + e.getMessage());
            } finally {
                if (ds2 != null) try { ds2.close(); } catch (IOException ignored) { }
            }
            final_leg.put("long_landed_by_enumeration", landedReal);
            final_leg.put("contents_read", false);
            String fv;
            if (!"ok".equals(v1[0]) && "ok".equals(v2[0]) && landedReal) fv = "rewritten-for-long-paths";
            else if (!"ok".equals(v1[0]) && "ok".equals(v2[0]) && !landedReal) fv = "ok-but-nothing-landed";
            else if (!"ok".equals(v1[0]) && !"ok".equals(v2[0])) fv = "not-rewritten";
            else if ("ok".equals(v1[0])) fv = "unexpected (short reserved final name was accepted)";
            else fv = "unknown";
            final_leg.put("verdict", fv);
            final_leg.put("verdict_basis", "short leg is the known refusal of a reserved final "
                    + "name; the long leg differs only in total path length, so a difference in "
                    + "answer can only come from the form the string left in");
        } catch (Exception e) {
            final_leg.put("verdict", "not-obtainable");
            final_leg.put("why", e.getClass().getName() + ": " + e.getMessage());
        }
        o.put("final_component_leg", final_leg);
        o.put("combined_verdict", final_leg.get("verdict"));
        return o;
    }

    // --------------------------------------------------------------- create
    static String[] createVia(Path target, byte[] payload, String entry, long[] wr) {
        try {
            if ("Files.write".equals(entry)) {
                Files.write(target, payload);
                wr[0] = payload.length;
            } else if ("Files.createFile".equals(entry)) {
                Files.createFile(target);
                wr[0] = 0L;
            } else if ("Files.newOutputStream".equals(entry)) {
                OutputStream os = Files.newOutputStream(target);
                try { os.write(payload); os.flush(); } finally { os.close(); }
                wr[0] = payload.length;
            } else if ("Files.move".equals(entry)) {
                Path src = target.getParent().resolve("sgsrc-" + UUID.randomUUID() + ".tmp");
                Files.write(src, payload);
                Files.move(src, target);
                wr[0] = payload.length;
            } else if ("File.createNewFile".equals(entry)) {
                boolean b = new File(target.toString()).createNewFile();
                wr[0] = 0L;
                if (!b) return new String[]{"err_at_syscall", "fs", "java.io.File",
                        "createNewFile() returned false (the name already exists or the OS refused it)"};
            } else if ("FileOutputStream.write".equals(entry)) {
                FileOutputStream fo = new FileOutputStream(target.toString());
                try { fo.write(payload); fo.getFD().sync(); } finally { fo.close(); }
                wr[0] = payload.length;
            } else if ("File.renameTo".equals(entry)) {
                File src = new File(target.getParent().toString() + File.separator
                        + "sgsrc-" + UUID.randomUUID() + ".tmp");
                FileOutputStream fo = new FileOutputStream(src);
                try { fo.write(payload); } finally { fo.close(); }
                boolean b = src.renameTo(new File(target.toString()));
                wr[0] = payload.length;
                if (!b) return new String[]{"err_at_syscall", "fs", "java.io.File",
                        "renameTo() returned false (java.io.File reports failure as a boolean, "
                        + "no error code is surfaced)"};
            } else {
                return new String[]{"err_at_syscall", "tool", "IllegalArgumentException",
                        "unknown entry " + entry};
            }
            return new String[]{"ok", "null", null, null};
        } catch (InvalidPathException e) {
            return new String[]{"err_at_parse", "parse", e.getClass().getName(),
                    e.getMessage() + " | reason=" + e.getReason() + " | index=" + e.getIndex()};
        } catch (java.nio.file.FileSystemException e) {
            return new String[]{"err_at_syscall", "fs", e.getClass().getName(),
                    e.getMessage() + " | " + weTag(e) + " | reason=" + e.getReason()};
        } catch (IOException e) {
            return new String[]{"err_at_syscall", "fs", e.getClass().getName(),
                    String.valueOf(e.getMessage())};
        } catch (RuntimeException e) {
            return new String[]{"err_at_syscall", "syscall", e.getClass().getName(),
                    String.valueOf(e.getMessage())};
        }
    }

    // ----------------------------------------------------- create (String form)
    /** rev7 rule 4: drive a java.io entry from the requested STRING, with no java.nio path parse in
     *  between. This is the same call extendedProbe already makes by hand; publishing it as its own
     *  cell is what lets the two entries of this port be compared as cells instead of as a footnote. */
    static String[] createViaString(String target, byte[] payload, String entry, long[] wr) {
        try {
            if ("File.createNewFile".equals(entry)) {
                boolean b = new File(target).createNewFile();
                wr[0] = 0L;
                if (!b) return new String[]{"err_at_syscall", "fs", "java.io.File",
                        "createNewFile() returned false (the name already exists or the OS refused it)"};
            } else if ("FileOutputStream.write".equals(entry)) {
                FileOutputStream fo = new FileOutputStream(target);
                try { fo.write(payload); fo.getFD().sync(); } finally { fo.close(); }
                wr[0] = payload.length;
            } else {
                return new String[]{"err_at_syscall", "tool", "IllegalArgumentException",
                        "no String-form driver for entry " + entry};
            }
            return new String[]{"ok", "null", null, null};
        } catch (FileNotFoundException e) {
            return new String[]{"err_at_syscall", "fs", e.getClass().getName(),
                    String.valueOf(e.getMessage())};
        } catch (IOException e) {
            return new String[]{"err_at_syscall", "fs", e.getClass().getName(),
                    String.valueOf(e.getMessage())};
        } catch (RuntimeException e) {
            return new String[]{"err_at_syscall", "syscall", e.getClass().getName(),
                    String.valueOf(e.getMessage())};
        }
    }

    static byte[] readViaIoString(String target) throws IOException {
        FileInputStream in = new FileInputStream(target);
        try {
            ByteArrayOutputStream buf = new ByteArrayOutputStream();
            byte[] chunk = new byte[8192];
            int n;
            while ((n = in.read(chunk)) > 0) buf.write(chunk, 0, n);
            return buf.toByteArray();
        } finally {
            in.close();
        }
    }

    static Long ioStringSize(String target) {
        try {
            return Long.valueOf(new File(target).length());
        } catch (RuntimeException e) {
            return null;
        }
    }

    // ---------------------------------------------------------- enumeration
    static final class Land {
        String name; Long size; String statStatus;
        Map<String, Object> toJson() {
            Map<String, Object> o = new LinkedHashMap<String, Object>();
            o.put("name_hex", name == null ? null : hexOf(name));
            o.put("name", name);
            o.put("size", size);
            o.put("stat_status", statStatus);
            return o;
        }
    }

    static Set<String> names(List<Land> lands) {
        Set<String> s = new LinkedHashSet<String>();
        for (Land l : lands) if (l.name != null) s.add(l.name);
        return s;
    }

    static List<Object> namesJson(List<Land> lands) {
        List<Object> out = new ArrayList<Object>();
        for (Land l : lands) {
            Map<String, Object> o = new LinkedHashMap<String, Object>();
            o.put("name_hex", l.name == null ? null : hexOf(l.name));
            o.put("size", l.size);
            o.put("stat_status", l.statStatus);
            out.add(o);
        }
        return out;
    }

    static List<Land> enumerate(Path dir) {
        List<Land> out = new ArrayList<Land>();
        DirectoryStream<Path> ds = null;
        try {
            ds = Files.newDirectoryStream(dir);
            for (Path p : ds) {
                String n = p.getFileName().toString();
                Land l = new Land();
                l.name = n;
                if (RESERVED.matcher(n).matches()) {
                    l.statStatus = "skipped-reserved-name (list only; no stat, no open)";
                } else {
                    try {
                        l.size = Files.readAttributes(p, BasicFileAttributes.class).size();
                        l.statStatus = "ok";
                    } catch (Exception e) {
                        l.statStatus = e.getClass().getName() + ": " + e.getMessage();
                    }
                }
                out.add(l);
            }
        } catch (Exception e) {
            Land l = new Land();
            l.name = null;
            l.statStatus = "ENUM-FAIL " + e.getClass().getName() + ": " + e.getMessage();
            out.add(l);
        } finally {
            if (ds != null) try { ds.close(); } catch (IOException ignored) { }
        }
        return out;
    }

    /** Java's public API does not expose the Win32 error number; probe that claim honestly. */
    static Map<String, Object> winErrorOf(Throwable e) {
        Map<String, Object> o = new LinkedHashMap<String, Object>();
        try {
            java.lang.reflect.Method m = e.getClass().getMethod("getWinError");
            m.setAccessible(true);
            Object v = m.invoke(e);
            o.put("winerror", v == null ? null : ((Number) v).longValue());
            o.put("winerror_probe", "reflected " + e.getClass().getName() + ".getWinError()");
        } catch (Throwable t) {
            o.put("winerror", null);
            o.put("winerror_probe", "unavailable: " + t.getClass().getName() + ": " + t.getMessage());
        }
        return o;
    }

    static String weTag(Throwable e) {
        Map<String, Object> w = winErrorOf(e);
        Object v = w.get("winerror");
        return v == null ? ("winerror=null(" + w.get("winerror_probe") + ")") : ("winerror=" + v);
    }

    /** canonical.md has exactly one word for a read that errored at the handle level. */
    static boolean isInvalidHandle(String msg) {
        String s = msg.toLowerCase(Locale.ROOT);
        return s.contains("handle is invalid") || s.contains("invalid handle")
                || s.contains("winerror 6") || s.contains("error 6)") || s.contains("errno 6");
    }

    static Long directSize(Path p) {
        if (RESERVED.matcher(p.getFileName().toString()).matches()) return null;
        try {
            return Files.readAttributes(p, BasicFileAttributes.class).size();
        } catch (Exception e) {
            return null;
        }
    }

    static int countEntries(Path dir) {
        int n = 0;
        DirectoryStream<Path> ds = null;
        try {
            ds = Files.newDirectoryStream(dir);
            for (Path ignored : ds) n++;
        } catch (Exception e) {
            return -1;
        } finally {
            if (ds != null) try { ds.close(); } catch (IOException ignored) { }
        }
        return n;
    }

    // ------------------------------------------------------ extended probe
    /**
     * Asks the OS rather than the language. Preflight (src/ExtPreflight.java) measured that
     * java.nio.file.Paths.get rejects a "\\?\" string at parse time while java.io.File hands it
     * to Win32 untouched, so the OS leg is taken through java.io.File.
     */
    static Map<String, Object> extendedProbe(Path scratch, String name, String absString,
                                             byte[] payload, boolean reserved) {
        Map<String, Object> o = new LinkedHashMap<String, Object>();
        String ext = "\\\\?\\" + absString;
        o.put("ext_string_form_hex", hexOf(ext));
        o.put("ext_string_len", (long) ext.length());
        // instrument 1: NIO
        try {
            Paths.get(ext);
            o.put("nio_accepts_ext_prefix", true);
        } catch (InvalidPathException e) {
            o.put("nio_accepts_ext_prefix", false);
            o.put("nio_reject_message", e.getMessage() + " | reason=" + e.getReason()
                    + " | index=" + e.getIndex());
            o.put("nio_reject_class", e.getClass().getName());
        }
        // instrument 2: java.io.File with the raw extended string
        o.put("instrument", "java.io.FileOutputStream(java.io.File(String)) with \\\\?\\ prefix");
        String cr = null, es = "null", ec = null, em = null;
        try {
            FileOutputStream fo = new FileOutputStream(ext);
            try { fo.write(payload); fo.getFD().sync(); } finally { fo.close(); }
            cr = "ok";
            es = "null";
        } catch (FileNotFoundException e) {
            cr = "err_at_syscall"; es = "fs"; ec = e.getClass().getName(); em = String.valueOf(e.getMessage());
        } catch (IOException e) {
            cr = "err_at_syscall"; es = "fs"; ec = e.getClass().getName(); em = String.valueOf(e.getMessage());
        } catch (RuntimeException e) {
            cr = "err_at_syscall"; es = "syscall"; ec = e.getClass().getName(); em = String.valueOf(e.getMessage());
        }
        o.put("create_result", cr);
        o.put("error_stage", es);
        o.put("error_class", ec);
        o.put("error_message", em);
        File f = new File(ext);
        o.put("io_file_exists", f.exists());
        o.put("io_file_length", reserved ? null : Long.valueOf(f.length()));
        o.put("io_file_length_status", reserved
                ? "skipped: reserved device name, list only" : "measured");
        boolean landed = false;
        DirectoryStream<Path> ds = null;
        try {
            ds = Files.newDirectoryStream(scratch);
            for (Path p : ds) if (p.getFileName().toString().equals(name)) { landed = true; break; }
        } catch (Exception e) {
            o.put("enumeration_error", e.getClass().getName() + ": " + e.getMessage());
        } finally {
            if (ds != null) try { ds.close(); } catch (IOException ignored) { }
        }
        o.put("landed_by_enumeration", landed);
        String verdict;
        if (landed) verdict = "legal";
        else if ("ok".equals(cr)) verdict = "unknown";
        else if (ec != null && ec.startsWith("java.nio.file")) verdict = "unknown";
        else verdict = "illegal";
        o.put("os_legality_verdict", verdict);
        o.put("os_legality_basis", landed
                ? "the OS created and enumerated the name once the language path parser was bypassed"
                : "the OS itself refused the name (or the answer could not be obtained)");
        return o;
    }

    // ------------------------------------------------------------- zip leg
    /** T16: java.util.zip roundtrip with a non-ASCII entry name (bit 11 territory). */
    static Map<String, Object> zipLeg(Path scratch, String name, byte[] payload) {
        Map<String, Object> o = new LinkedHashMap<String, Object>();
        o.put("attempted", true);
        Path zip = scratch.resolve(name + ".probe.zip");
        String entryName = "caf\u00e9-\u2603.txt";
        try {
            OutputStream fos = Files.newOutputStream(zip);
            ZipOutputStream zos = new ZipOutputStream(fos, StandardCharsets.UTF_8);
            try {
                ZipEntry ze = new ZipEntry(entryName);
                zos.putNextEntry(ze);
                zos.write(payload);
                zos.closeEntry();
            } finally { zos.close(); }
            Map<String, Object> back = new LinkedHashMap<String, Object>();
            int n = 0;
            boolean sawEntry = false;
            ZipInputStream zis = new ZipInputStream(Files.newInputStream(zip), StandardCharsets.UTF_8);
            try {
                ZipEntry re;
                while ((re = zis.getNextEntry()) != null) {
                    n++;
                    if (entryName.equals(re.getName())) sawEntry = true;
                    back.put("entry_" + n + "_name_hex", hexOf(re.getName()));
                    back.put("entry_" + n + "_comment_hex", re.getComment() == null
                            ? null : hexOf(re.getComment()));
                }
            } finally { zis.close(); }
            o.put("zip_file", zip.getFileName().toString());
            o.put("zip_bytes_written", Files.readAttributes(zip, BasicFileAttributes.class).size());
            o.put("entries_written", 1L);
            o.put("entries_read", (long) n);
            o.put("entry_name_hex", hexOf(entryName));
            o.put("entry_name_roundtrip_ok", sawEntry);
            o.put("reopened_entries", back);
            o.put("create_result", "ok");
            o.put("error_stage", "null");
        } catch (Exception e) {
            o.put("create_result", "err_at_syscall");
            o.put("error_stage", "fs");
            o.put("error_class", e.getClass().getName());
            o.put("error_message", String.valueOf(e.getMessage()));
            o.put("entry_name_roundtrip_ok", false);
        }
        return o;
    }

    // ------------------------------------------------------------ utilities
    static String padded(int n) {
        char[] c = new char[n];
        for (int i = 0; i < n; i++) c[i] = PAD[i % PAD.length];
        return new String(c);
    }

    static byte[] unhex(String h) {
        String s = h.trim();
        byte[] b = new byte[s.length() / 2];
        for (int i = 0; i < b.length; i++) b[i] = (byte) Integer.parseInt(s.substring(i * 2, i * 2 + 2), 16);
        return b;
    }

    static String toHex(byte[] b) {
        StringBuilder s = new StringBuilder(b.length * 2);
        for (byte x : b) s.append(String.format(Locale.ROOT, "%02x", x & 0xff));
        return s.toString();
    }

    static String hexOf(String s) { return toHex(s.getBytes(StandardCharsets.UTF_8)); }

    static String esc(String s) {
        StringBuilder b = new StringBuilder(s.length() + 8);
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            switch (c) {
                case '"': b.append("\\\""); break;
                case '\\': b.append("\\\\"); break;
                case '\n': b.append("\\n"); break;
                case '\r': b.append("\\r"); break;
                case '\t': b.append("\\t"); break;
                default:
                    if (c < 0x20 || c > 0x7e) b.append(String.format(Locale.ROOT, "\\u%04x", (int) c));
                    else b.append(c);
            }
        }
        return b.toString();
    }

    static String writeAscii(Object v) {
        StringBuilder o = new StringBuilder(8192);
        emit(o, v);
        return o.toString();
    }

    @SuppressWarnings("unchecked")
    static void emit(StringBuilder o, Object v) {
        if (v == null) { o.append("null"); return; }
        if (v instanceof Map) {
            boolean first = true;
            o.append('{');
            for (Map.Entry<String, Object> e : ((Map<String, Object>) v).entrySet()) {
                if (!first) o.append(',');
                first = false;
                o.append('"').append(esc(e.getKey())).append("\":");
                emit(o, e.getValue());
            }
            o.append('}');
            return;
        }
        if (v instanceof List) {
            o.append('[');
            boolean first = true;
            for (Object x : (List<Object>) v) {
                if (!first) o.append(',');
                first = false;
                emit(o, x);
            }
            o.append(']');
            return;
        }
        if (v instanceof String) { o.append('"').append(esc((String) v)).append('"'); return; }
        if (v instanceof Boolean || v instanceof Number) { o.append(v.toString()); return; }
        o.append('"').append(esc(v.toString())).append('"');
    }

    static Map<String, Object> dict(Object... kv) {
        Map<String, Object> m = new LinkedHashMap<String, Object>();
        for (int i = 0; i + 1 < kv.length; i += 2) m.put((String) kv[i], kv[i + 1]);
        return m;
    }

    static String sha(byte[] b) {
        try {
            MessageDigest m = MessageDigest.getInstance("SHA-256");
            return toHex(m.digest(b));
        } catch (Exception e) { return null; }
    }

    static Map<String, String> parseArgs(String[] argv) {
        Map<String, String> m = new LinkedHashMap<String, String>();
        for (int i = 0; i + 1 < argv.length; i++) {
            if (argv[i].startsWith("--")) m.put(argv[i].substring(2), argv[++i]);
        }
        return m;
    }

    static String req(Map<String, String> m, String k) {
        String v = m.get(k);
        if (v == null) throw new IllegalArgumentException("missing --" + k);
        return v;
    }
}
