# F14 - the leak leg's TOOLPATH class is named "absolute path" and matches something looser

Opened 2026-10-12 by the local that owns `ci/`, found while trying to attribute a +3 movement in
`python ci/process_leak_scan.py` for F11's acceptance row (`evidence/closing/F11-acceptance.md` prints the
attempt and its failure).

## Measured

The rule, from `ci/process_leak_scan.py:54`:

```
ANY_PATH = re.compile("[A-Za-z]:[" + SEP2 + "/]{1,2}(?![\\/])|/[A-Za-z0-9_.-]+/")
```

and the class description at line 27: *"TOOLPATH - any other **absolute** path - a recorded executable, a
toolchain root, a runtime location."*

The first branch does mean an absolute Windows path. The second branch, `/[A-Za-z0-9_.-]+/`, fires on any
`/word/` fragment, so it matches every repo-relative reference that has two or more segments - `docs/tickets/`
matches on its `/tickets/`, `evidence/closing/` on its `/closing/`. A single-segment reference like `ci/` does not match,
which is the kind of detail the class name currently hides. Proven by the leg's own `scan_face()` on faces added
by F11:

```
docs/tickets/F13-pairing-rule-scope.md  TOOLPATH head=0 disk=3   (three lines, all repo-relative references)
evidence/closing/F11-acceptance.md          TOOLPATH head=0 disk=5   (all repo-relative references)
```

Nothing fatal moved (`fatal_by_class=HOSTROOT:13,IDENTITY:1134,LOGIN:15,RETIRED:1143` before and after), because
`TOOLPATH` is in `NON_FATAL_CLASSES` and routes to `counted_not_fatal`. So the verdict is unaffected and the
metric is inflated: a reader who sees `TOOLPATH:134` and is told it counts absolute paths is reading a number
that counts something else.

## Why this is a ticket and not a comment

This project's rule is that a count must name its population, and a rule must be named for what it measures -
both because a loose needle once condemned 8,881 innocent lines, and because a gate that over-reports trains
people to ignore it. The class is harmless today and dangerous the day someone raises it to fatal, at which point
every sentence containing `docs/tickets/` becomes a leak.

## Acceptance criteria

1. the second branch is tightened to require a root (`^/` or a POSIX mount point) or the class is renamed to
   `PATHSHAPED` in the print line - whichever the run supports, and the ticket must state which it shipped;
2. a **green arm proving the class still fires** on a real toolchain path (`C:\Python314\python.exe`,
   `/usr/lib/jvm/...`), and a **red arm proving it does not fire** on a repo-relative reference such as
   `docs/tickets/F11-blank-count-sentence.md` - a fix that only ever makes the count smaller needs the second
   arm, or the leg has quietly stopped measuring;
3. the count before/after printed in the acceptance row (`TOOLPATH=NNN -> MMM` with `files_scanned=` beside it),
   and the four fatal classes unchanged;
4. `python ci/process_leak_scan.py --selftest` arms grow by exactly the new arms, and
   `python ci/refresh_all.py` at the new tip reports no new tool failures.

## Do not

- Do not raise `TOOLPATH` to fatal as part of this ticket; that is a disclosure decision, not a rule-shape fix.
- No deletion (project rule), no `spec/`, no history rewriting.

## Allowed surface

`ci/process_leak_scan.py` (the regex or the class name, and its arms) plus the acceptance row in `evidence/closing/`.

## Clock

24 h from dispatch. Queue position: behind F8's six-lane re-emit; it blocks nothing.

## Erratum on the sentence "Nothing fatal moved"

It was true under the needles the leg had at the time. Those needles could not match an escaped Windows path, so
they were blind to the data faces; once `_escaped_forms()` went in, `LOGIN` read 15 -> 1111 and `HOSTROOT`
13 -> 338 on the same tree. The `TOOLPATH` over-match this ticket is about is unaffected and still stands. See
`docs/FINDINGS-rev6.md` M12(a) - and note that this ticket's own criterion 2 demanded both a firing arm and a
non-firing arm, which is the habit that made the needle bug findable at all.

## One more measured cost of the over-match

`evidence/closing/readonly-tree-contamination-20261012.md` lists the 129 faces that session rewrote in the other
checkout, by name, because a record that does not name its scope is not a record. The leg reads that face as
**136 TOOLPATH lines** - every one of them a repo-relative path, none of them a host path, none of them fatal. A
count that inflates by 136 because a face did its job is the clearest argument this ticket has: the class is named
for absolute paths and measures path-shaped text, so it cannot be raised to fatal, and it should not be quoted as
if it counted leaks.
