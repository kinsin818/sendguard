import java.io.File;
import java.io.FileOutputStream;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.InvalidPathException;
import java.nio.file.Path;
import java.nio.file.Paths;

/**
 * One-shot preflight, not a measurement cell: which instrument on this port can
 * hand a "\\?\" string to the OS untouched? Answers the os_legality_verdict
 * instrument question before CellProbe is wired to it.
 */
public final class ExtPreflight {
    public static void main(String[] x) throws Exception {
        String dir = x[0];
        String name = "preflight-probe.txt";
        String abs = new File(dir, name).getAbsolutePath();
        String ext = "\\\\?\\" + abs;
        System.out.println("abs=" + abs);
        System.out.println("ext=" + ext);
        try {
            Path p = Paths.get(ext);
            System.out.println("nio.Paths.get(ext) OK -> " + p);
        } catch (InvalidPathException e) {
            System.out.println("nio.Paths.get(ext) THROWS InvalidPathException reason=" + e.getReason()
                    + " index=" + e.getIndex());
        }
        try {
            File f = new File(ext);
            boolean created = f.createNewFile();
            System.out.println("io.File.createNewFile(ext) rc=" + created + " exists=" + f.exists()
                    + " len=" + f.length());
        } catch (Exception e) {
            System.out.println("io.File.createNewFile(ext) THROWS " + e.getClass().getName() + ": " + e.getMessage());
        }
        try {
            FileOutputStream fo = new FileOutputStream(ext);
            fo.write("x".getBytes(StandardCharsets.UTF_8));
            fo.close();
            System.out.println("io.FileOutputStream(ext) wrote ok");
        } catch (Exception e) {
            System.out.println("io.FileOutputStream(ext) THROWS " + e.getClass().getName() + ": " + e.getMessage());
        }
        try {
            URI u = new URI("file:///?//" + abs.replace('\\', '/'));
            File f = new File(u);
            System.out.println("uri-form File -> " + f.getAbsolutePath() + " exists=" + f.exists());
        } catch (Exception e) {
            System.out.println("uri-form THROWS " + e.getClass().getName() + ": " + e.getMessage());
        }
        try {
            System.out.println("listing dir: " + java.util.Arrays.toString(new File(dir).list()));
        } catch (Exception e) {
            System.out.println("listing THROWS " + e);
        }
        try {
            ProcessBuilder pb = new ProcessBuilder("cmd", "/c", "dir", "/b", ext);
            pb.redirectErrorStream(true);
            Process pr = pb.start();
            byte[] out = pr.getInputStream().readAllBytes();
            int rc = pr.waitFor();
            System.out.println("cmd dir /b ext rc=" + rc + " out=" + new String(out, StandardCharsets.UTF_8).trim());
        } catch (Exception e) {
            System.out.println("cmd probe THROWS " + e);
        }
    }
}
