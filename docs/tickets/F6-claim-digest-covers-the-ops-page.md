# F6 - `ci/claim_digest.py` must also police the page the maintainer actually reads first

Opened 2026-10-11 15:47 +0800 by the maintainer that owns `ci/`.

## The hole, measured rather than suspected

`ci/claim_digest.py` checks quoted numbers in `README.md`, `docs/claim-boundary.md` and `docs/whitepaper.md`, and
today it earned its keep. But the document the maintainer reads first is **not in the repository**: the morning
one-pager lives at `D:\probe\ops\morning-brief-20261011.md`, outside `REPO`, so the leg never opens it.

Auditing that page at 15:47 by hand found three numbers that had gone stale in it, all written by this machine and
all correct when written:

| what the page said | what the tree said at audit | how it went stale |
|---|---|---|
| "1171 tracked faces, zero differences three ways" | 1175 tracked faces | two tickets and one new leg landed after the blob comparison |
| "the parity leg self-tests with 12 arms" | 14 arms | the leg grew arms the same afternoon the sentence was written |
| "tree is 81 commits ahead - your call whether to push" | `ahead=0`, pushed on the maintainer's word at 15:14 | the decision row outlived the decision |

The third is the expensive kind: not a wrong number, a **stale status** that would have made the maintainer think an
order he gave was not carried out.

## Acceptance criteria

1. `--extra-face <path>` (repeatable) on `ci/claim_digest.py`, so an out-of-repository face is checked against the
   same declared claim table; the path is verified to exist and is refused with rc=3 if it does not, rather than
   being skipped silently - a claim set that quietly drops a face reports coverage it does not have;
2. the out-of-repo faces get their **own** claim list (the numbers above), because their sentences are worded
   differently from the README's; each entry names the kind (`gate`, `arms`, `status`) the way the existing table
   does, and a `status` claim is compared against a live external fact (`ahead`/`behind` from `git rev-list`, read
   from the source rather than a cached ref, per the rule that produced F4);
3. a vanished anchor is a finding, not a pass, exactly as in the in-repo table;
4. `--selftest` gains both sides: an out-of-repo face with a matching number verifies, one with a stale number is
   named with both values, and a missing `--extra-face` path exits 3;
5. the pipeline or the leg's own run line prints which faces were read and how many claims each carried, so
   "checked" never means "the three files I happened to know about".

## Do not do

Do not solve this by hand-copying numbers from the page into the repository, and do not move the page into the
repository to make the check easier - the page is the maintainer-facing record and the repository is the deliverable,
and merging those two faces is a worse trade than a flag.
