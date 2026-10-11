# SG-F5 - the acceptance sheet must not let `faces_ahead_of_head=0` read as "everything is landed"

Opened 2026-10-11 15:42 +0800 by the seat that owns `ci/`. Attempted today and **rolled back unpublished**: the
version I reached had three self-test arms red, and a red suite does not go into a tree the owner audits tomorrow.
The three files came back to their committed blobs byte-for-byte and `git status` is clean afterwards. What the
attempt found is the reason to finish it.

## The blind spot

`ci/acceptance.py` reads status per canonical face only (six `results/<port>.windows.x64` directories), so the
sheet prints `faces_ahead_of_head=0` while the same repository holds `impl/python/sg_restamp_note.txt` untracked -
another window's work, present all afternoon. A reader who takes that 0 as "nothing here is unlanded" is wrong,
and this sheet is the thing that taught them the 0.

## What the attempt measured before the rollback

The whole-tree table named it correctly:

```
| changed inside a canonical result face   | 0 | - |
| untracked inside a canonical result face | 0 | - |
| changed elsewhere in the tree            | 2 | ci/acceptance.py, ci/refresh_all.py |
| untracked elsewhere                      | 1 | impl/python/sg_restamp_note.txt |
```

and it caught a real defect in my own classifier: a path git C-quotes (a name with a space or non-ASCII) went
through the canonical test **with its quotes still attached**, so a result face whose name needs quoting would
have been counted as "elsewhere". Both findings are worth finishing properly, not shipping half-done.

## Acceptance criteria

1. a pure `classify_status(status_lines, canonical_dirs)` returning buckets: canonical changed/untracked, other
   changed/untracked, renames, C-quoted paths, `unparsed`;
2. unquoting happens **before** the canonical test, with an arm feeding `?? "spaced name.txt"` and requiring the
   unquoted name in the bucket;
3. an unmappable line lands in `unparsed` and the sheet exits 1 - a line the code does not understand is never
   evidence of a clean tree;
4. an empty status must classify to all-zero buckets and exit 0, so the gate is proven able to pass, not only to
   refuse;
5. a rename counts at its destination and in its own bucket; the table prints the number of status lines read as a
   denominator, and the buckets must sum to it;
6. the sheet names other windows' untracked faces and acts on none of them, and says so on its face: landing
   another window's work is not this seat's act;
7. `--selftest` carries the self-counting arm guard the other legs have, and is wired into
   `ci/refresh_all.py`'s judge list.
