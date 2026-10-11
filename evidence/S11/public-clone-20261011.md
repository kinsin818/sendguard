# S11 - the public repository, cloned from GitHub and re-verified (2026-10-11)

Run at 15:24-15:25 +0800, ten minutes after the push. The claim this tests is the one the delivery is actually
selling: not "my working copy reproduces in a directory I made", but **a stranger who clones
`https://github.com/kinsin818/sendguard` gets the same thing, and it says the same things there.**

## 1. The source tip was read from the source, not from a cached ref

```
local HEAD      | a2037c13b581163cb6ffc9fde33810e3f8450a55
public tip      | a2037c13b581163cb6ffc9fde33810e3f8450a55
local  tree     | cd81ef4aa42ba4884921da046ba2529d2f5c2cb8
fetched public tree | cd81ef4aa42ba4884921da046ba2529d2f5c2cb8
same commit: True | same tree object: True
git diff HEAD github/main | no differences
```

## 2. A real network clone, then the whole pipeline inside it

```
network clone rc=0 | Cloning into 'D:\sendguard-work\public-1'...
clone HEAD | a2037c13b581163cb6ffc9fde33810e3f8450a55  equals public tip: True
clone tree | cd81ef4aa42ba4884921da046ba2529d2f5c2cb8  equals local tree: True
clone status lines at start: 0 (a stranger's tree must be empty)
clone tracked paths: 1171
pipeline inside the public clone rc=1; last verdicts: OUTCOME=CLEAN refusals=1 tool_failures=0
```

`rc=1` is the pipeline's own honest state: the equality gate is RED by design and `refusals=1` names that
measurement, while `tool_failures=0` says nothing crashed.

## 3. Face parity, and the false alarm that produced it

The first pass reported 8 identical and 4 differing. All four differences were defects in **my throwaway
comparator**, not in the repository: it normalised `2026-10-11 14:54:33 +0800` but not `2026-10-11T14:54:42+0800`,
and three of the four lines were exactly that field (`written_at` inside the gate's artifact and the two headers
that quote it). Re-normalised:

```
declared| docs/evidence.md - 1 line(s) naming the commit and the uncommitted count of the tree that generated it
public-clone face parity with the ISO timestamps normalised too: identical=11 declared=1 differing=0 of 12
```

Eleven of twelve derived faces regenerate byte-for-byte inside a GitHub clone; the twelfth is the same
self-describing line `ci/clone_parity.py` has declared all afternoon.

## 4. The deliverable, and where this run stopped short

The same pass tried to compare the checker's verdict fields between the seat and the public clone using its own
parser, and **that parser failed on both sides**:

```
INSTRUMENT| report-2026.txt: a verdict block could not be parsed (seat=unparseable clone=unparseable rc=0/0)
deliverable asked from the public clone: names=5 fields_compared=0 differing=0
```

`fields_compared=0` is not agreement, and it is not reported as such - an empty comparison is its own finding.
The field-level comparison of the deliverable between this tree and a cold clone of the same commit is done by the
standing leg instead, which reads `tool| names=5 fields_compared=55 differing=0` (see
`evidence/S11/tool-coldrun-20261011.md`), and the two are the same bytes because of section 5. Writing a second
parser to re-prove it was a mistake of exactly the kind this repository has been catching all day: the leg that
judges again, differently.

## 5. The strongest and cheapest proof: blob-by-blob

```
face                               seat           public-1 clone github/main
tool/check.py                      e82c90287831   e82c90287831   e82c90287831   OK
spec/cases.yaml                    5e01d11258a7   5e01d11258a7   5e01d11258a7   OK
ci/equality.py                     f409cd6b4fe4   f409cd6b4fe4   f409cd6b4fe4   OK
ci/clone_parity.py                 a42bbd22f8d0   a42bbd22f8d0   a42bbd22f8d0   OK
README.md                          a5e325e8d329   a5e325e8d329   a5e325e8d329   OK
docs/whitepaper.md                 1af164b7cf53   1af164b7cf53   1af164b7cf53   OK
.github/workflows/matrix.yml       5c81f212abd9   5c81f212abd9   5c81f212abd9   OK
every tracked face compared blob-by-blob: faces=1171  differing=0  only-in-seat=0  only-in-clone=0
VERDICT: public tree == verified local tree: True
```

Every one of the 1,171 tracked faces has the same blob hash in the seat, in the GitHub clone, and on the public
branch - and no face exists on one side and not the other. Content addressing makes that a stronger statement than
a file list: the public repository **is** the tree this seat verified in cold clones at `parity-4` through
`parity-7`, not a copy of it.

## What this proves, and what it does not

Proves: the public repo carries exactly the verified content; the pipeline runs and produces its honest verdict
inside a network clone; derived faces reproduce there modulo timestamps with one declared exception.

Does not prove: the CI workflow's outcome (its job has been triggered by the push; its conclusion is not readable
from this seat - no `gh`, and the API answers 403 without a token); any macOS or Linux *result* rows (the
instrument job runs the judges on three systems, not the port harnesses); that the deliverable answers identically
on another machine (the field comparison cited in section 4 is seat-versus-clone on one host).

`docs/tickets/SG-F4-clone-parity-source.md` is queued so this whole sequence becomes one command
(`ci/clone_parity.py --source <url>`) instead of a script written beside the repository at 15:24.


## Addendum, 15:29 +0800 - the records commit is not on the public branch yet

The verification above ran against the public branch as pushed at 15:14 (`a2037c1`), and that commit **is** on
GitHub: `git ls-remote` confirmed the tip before the network changed. The follow-up record commit (`b6f863c`, this
file plus `docs/tickets/SG-F4-clone-parity-source.md`) could not be pushed at 15:26-15:29:

```
fatal: unable to access 'https://github.com/kinsin818/sendguard.git/': Recv failure: Connection was reset
fatal: unable to access 'https://github.com/kinsin818/sendguard.git/': Failed to connect to github.com port 443 after 21072 ms: Could not connect to server
```

So the published deliverable and the local repository differ by one documentation commit, and the numbers in this
file describe the branch that is actually public (`a2037c1`). Nothing was claimed about a push that had not
happened; when the connection returns, `git push github main:main` is a fast-forward of that one commit and the
divergence closes. Until then, anyone reading the public repository sees `a2037c1`, which is the tree that
section 5 proved identical blob-for-blob.
