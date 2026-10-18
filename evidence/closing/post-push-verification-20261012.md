# Post-push stranger-side verification, 2026-10-12

The order was: scrub the unpublished messages, push, then verify from the stranger's side and report what the
stranger actually finds. Every reading below was taken either from a clone made from the public URL or with needles
assembled at run time from this local's own tree - so the check asks "what did the public side get", not "what does
my working copy look like". Absolute host paths are quoted by class, not by bytes: a verification face that
re-publishes the paths it was written to disown is the defect twice, and the leg prints them itself when it runs.

## 1. The three identities agree

| reading | value |
|---|---|
| `git ls-remote --heads github` (rc=0) | `f71550e838c7d617b2822a3fedeff070bf42c4fd refs/heads/main` |
| local `git rev-parse main` (rc=0) | `f71550e838c7d617b2822a3fedeff070bf42c4fd` |
| `git rev-parse HEAD` inside the fresh public clone (rc=0) | `f71550e838c7d617b2822a3fedeff070bf42c4fd` |

The push was a fast-forward (`git merge-base --is-ancestor bd0c430 HEAD`, rc=0): no force, no rewrite of anything
that a stranger could already have cloned. 12 commits moved, of which 11 are the rewritten range and one is the
record face for the rewrite.

## 2. The ruler, run from the stranger's side

`python ci/face_preflight.py --messages bd0c430..HEAD` executed **inside the clone made from the public URL**:

```
preflight-messages| checked=12 blocked=0
OUTCOME=CLEAN
```

and a direct needle census over the same 12 messages, with the needles taken from this local's tree at run time
(so the census cannot be satisfied by a rule that was edited to match):

| needle | occurrences in the 12 pushed messages |
|---|---|
| host profile login name | 0 |
| host profile root | 0 |
| this working copy's own directory, in either separator spelling and the JSON-escaped one | 0 |

Before the pass the same ruler read `checked=11 blocked=3` on the pre-scrub chain. The site table, the old-to-new
hash mapping and the four defects the pass caught in itself are in `msg-scrub-20261012.md`, not repeated here.

## 3. The whole judgement, reproduced from the public URL

`python ci/clone_parity.py --scratch-root <outside the tree> --source https://github.com/kinsin818/sendguard`
(rc=0):

```
OUTCOME=CLEAN faces_compared=13 identical=11 declared=1 differing=0 missing=0 host_bound=1 clone=<scratch>/parity-6
tool| names=5 fields_compared=55 differing=0
```

Read the counts as they are: 11 of 13 generated faces are byte-identical to the commit they came from; one is
`declared` - `docs/evidence.md` pins the commit that was current when the generator ran, which is necessarily one
behind the commit that carries the regenerated face, and the leg says so inside the face instead of pretending the
loop is closed; one is `host_bound` and excluded **by name** (`docs/host-stamp.md`, which records the interpreter
of the machine that produced it). `differing=0` is the claim that matters, and `missing=0` with it. The tool face
answers the frozen contract from the clone with 5 names x 55 fields and 0 differences.

## 4. Disclosure census of what a stranger receives

`python ci/process_leak_scan.py --repo-root .` inside the public clone:

```
OUTCOME=RED files_scanned=1212 unreadable=0 FATAL=2006 MENTIONED=198 counted_not_fatal=8503
fatal_by_class=IDENTITY:443,LOGIN:1111,RETIRED:452
```

Two things a reader should not be allowed to confuse:

- **HOSTROOT reads 0 in a clone and that is not a clean bill of health.** The leg builds that needle from the tree it
  is standing in, so the class is zero by construction for any clone - it can only ever fire on the machine that
  produced the faces. What a stranger actually receives was therefore counted directly, face by face, with needles
  assembled from this local's tree: of 1,212 tracked faces in the clone, **301 carry the host profile login name**
  and **267 carry the host profile root**, concentrated in `evidence/freeze/` (the environment captures) and the
  `evidence/recovered/…` result copies. That is the exposure already admitted in
  `exposure-rescan-20261012.md`; what this push changed about that set was measured rather than asserted - the same
  census run over the blobs of the previous published tip and of the new one:

  | tree | tracked faces | carrying the login name | carrying the profile root | carrying this working copy's directory |
  |---|---|---|---|---|
  | `bd0c430` (published before today's push) | 1,195 | 301 | 267 | 5 |
  | `f71550e` (published by today's push) | 1,212 | 301 | 267 | 5 |

  17 faces went out and **0** faces joined the exposed set: the marginal disclosure of the push is zero for all
  three needle classes. The 17 are 6 evidence faces written today, 4 result faces of the go lane's re-run, 4
  tickets, 2 tool faces and 1 hook - none of them quotes a host path, which is what the pre-flight was built to
  make impossible before the commit rather than after the push.
- **`RETIRED:452` and `IDENTITY:443` are the classes the owner ruled "认了, 不动, 记录在案".** They are the vocabulary
  of the six ports' own result faces and of the audit evidence that quotes it. Removing them means editing
  evidence, which is the one thing this project's exhibit is not allowed to do.

## 5. Residue in the published segment (cannot be changed, so it is named)

`git rev-list bd0c430` = 127 commits. **10 commit messages carry 11 drive-letter path shapes**, in `f67eeb9 0186b8e
98d549c aa793da a00ee80 b6f863c 8900037 d6994fd e3c1acd 1d0e2ba`; one of them (`e3c1acd`, line 3) names this working
copy's own directory. Those commits are on the published side, so under the project rules they stay exactly as
they are. A stranger who greps public history finds this admission before finding them.

## 6. What the CI says about this push

The push triggered `sendguard-matrix`. The third job's conclusion is **still unread from this local**: reading
Actions requires the read-only token the owner said he would supply, and until it lands the honest state of that
cell is `NOT-REACHED(reason=no token for the log reader)`, not green and not red. The two legs this pass added to
the workflow (`face_preflight --selftest`, `process_leak_scan --selftest`, and the message mode over
`${{ github.event.before }}..${{ github.sha }}`) run in that same job, so when the token lands the range-scan
result is the first thing to read: it should print `checked=12 blocked=0`, which is what the clone printed.
