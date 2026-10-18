import java.io.File;
import java.nio.file.InvalidPathException;
import java.nio.file.Path;
import java.nio.file.Paths;

/**
 * SENDGUARD java port, rev7 question 1 and 2: which call raises on the extended-prefix form, and
 * whether java.nio rejects the "\\?\" prefix in general or only for the path shape the harness
 * builds.
 *
 * Read-only by construction: Path.of / Paths.get / new File(String) perform no filesystem I/O, and
 * this program creates, opens and lists nothing. The reserved-name rule is not touched either.
 */
public final class ExtPathOfRepro {

    static String rep(char c, int n) {
        StringBuilder b = new StringBuilder(n);
        for (int i = 0; i < n; i++) b.append(c);
        return b.toString();
    }

    static void one(String tag, String s) {
        StringBuilder b = new StringBuilder();
        b.append("TAG ").append(tag).append(" | len=").append(s.length()).append(" | input=").append(s);
        try {
            Path p = Paths.get(s);
            b.append("\n    Paths.get          -> OK  impl=").append(p.getClass().getName())
             .append(" toString=").append(p);
        } catch (InvalidPathException e) {
            b.append("\n    Paths.get          -> THREW ").append(e.getClass().getName())
             .append(" | message=").append(e.getMessage())
             .append(" | reason=").append(e.getReason())
             .append(" | index=").append(e.getIndex())
             .append(" | input=").append(e.getInput());
            StackTraceElement[] st = e.getStackTrace();
            int show = Math.min(st.length, 5);
            for (int i = 0; i < show; i++) b.append("\n        at ").append(st[i]);
        } catch (RuntimeException e) {
            b.append("\n    Paths.get          -> THREW ").append(e.getClass().getName())
             .append(" | message=").append(e.getMessage());
        }
        try {
            Path p2 = Path.of(s);
            b.append("\n    Path.of            -> same result as Paths.get (toString match=")
             .append(Boolean.valueOf(String.valueOf(p2).equals(tryPathsGet(s))))
             .append(")");
        } catch (RuntimeException e) {
            b.append("\n    Path.of            -> THREW ").append(e.getClass().getName());
        }
        try {
            File f = new File(s);
            b.append("\n    new File(String)   -> OK  getPath=").append(f.getPath())
             .append(" | isAbsolute=").append(f.isAbsolute())
             .append(" | name=").append(f.getName());
        } catch (RuntimeException e) {
            b.append("\n    new File(String)   -> THREW ").append(e.getClass().getName())
             .append(" | message=").append(e.getMessage());
        }
        System.out.println(b.toString());
        System.out.println();
    }

    static String tryPathsGet(String s) {
        try {
            return String.valueOf(Paths.get(s));
        } catch (RuntimeException e) {
            return "<refused:" + e.getClass().getSimpleName() + ">";
        }
    }

    public static void main(String[] argv) {
        System.out.println("java.version       = " + System.getProperty("java.version"));
        System.out.println("java.vendor        = " + System.getProperty("java.vendor"));
        System.out.println("java.home          = " + System.getProperty("java.home"));
        System.out.println("java.class.version = " + System.getProperty("java.class.version"));
        System.out.println("os.name            = " + System.getProperty("os.name"));
        System.out.println("argv0              = "
                + (argv.length > 0 ? argv[0] : System.getProperty("sun.java.command")));
        System.out.println();

        String hex48 = "0123456789abcdef0123456789abcdef0123456789abcdef01";
        String dir = "D:\\s\\9431b6\\" + hex48;
        String plain78 = dir + "\\" + rep('a', 78);
        String plain200 = dir + "\\" + rep('a', 200);
        String ext78 = "\\\\?\\" + plain78;
        String ext200 = "\\\\?\\" + plain200;

        one("1 plain rung base_len=78 (the harness plain string)", plain78);
        one("2 extended rung base_len=78 (the harness extended string)", ext78);
        one("3 extended, SHORT, ordinary drive path", "\\\\?\\D:\\the maintainer");
        one("4 extended, drive root only", "\\\\?\\C:\\");
        one("5 plain, SHORT, ordinary drive path", "D:\\the maintainer");
        one("6 extended UNC variant", "\\\\?\\UNC\\server\\share\\x.txt");
        one("7 single leading backslash then ?", "\\?\\D:\\the maintainer");
        one("8 extended written with forward slashes", "//?/D:/the maintainer");
        one("9 plain rung base_len=200 (plain total path > 259)", plain200);
        one("10 extended rung base_len=200", ext200);
        one("11 device-prefix variant", "\\\\.\\PhysicalDrive0");

        System.out.println("note: the recorded cell at "
                + "results/java.windows.x64/len__T17__base_len-78__extended.json carries this same");
        System.out.println("note: message verbatim in its error_message field; this program is the "
                + "one-command reproduction of it.");
    }
}
