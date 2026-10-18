# Delivery receipt - every gate read at one instant (2026-10-11 15:49:57 +0800)

One page the owner can hold the delivery against. Nothing here is quoted from memory: each line below is the last 
verdict line the named leg printed, captured in this run, in this tree, at this commit. A leg that printed nothing would be reported as such rather than skipped.

## State

```
commit            aa793da4363e4767138b24e2b4aafd64e2a001c2
public branch tip aa793da4363e4767138b24e2b4aafd64e2a001c2  (matches: True)
ahead=0 behind=0   tracked faces=1176   dirty lines=3 (M docs/acceptance.md;  M evidence/judgement/equality-verdict.json; ?? impl/python/sg_restamp_note.txt)
```

## Gates

| leg and flags | rc | expectation | what it checks | its own words |
|---|---|---|---|---|
| `ci/selftest.py --selftest --scratch-root` | 0 | as expected | the equality gate's own arms, both sides | `OUTCOME=PASS` |
| `ci/lint.py --repo-root --selftest` | 0 | as expected | static checks over the CI workflow and the tracked names | `lint: OK  arms=24 passed=24  workflows=1 runner_labels_checked=7 tracked=1176,untracked=1 names_checked=1177 json_scanned=974` |
| `ci/validate_cells.py --selftest` | 0 | as expected | cell conformance arms | `arms=24 passed=24` |
| `ci/spec_drift.py --selftest` | 0 | as expected | frozen-spec fingerprint arms | `arms=15 passed=15` |
| `ci/coverage_report.py --selftest` | 0 | as expected | the coverage report's arms, including its self-count guard | `arms=9 passed=9` |
| `ci/delivery_form.py --selftest` | 0 | as expected | the delivery-form leg's arms | `arms=18 passed=18` |
| `ci/clone_parity.py --selftest` | 0 | as expected | the cold-clone leg's arms | `arms=14 passed=14` |
| `ci/claim_digest.py --selftest --scratch-root` | 0 | as expected | the number-in-prose digest's arms | `arms=6 passed=6` |
| `ci/link_check.py --selftest` | 0 | as expected | the markdown link leg's arms | `arms=6 passed=6` |
| `ci/equality.py` | 1 | as expected | the six-port verdict - RED is the product, not a fault | `OUTCOME=RED verdict_disagreements=54 verdict_identical_cells=24/44 cells_fully_recorded_and_identical=4 verdict_not_recorded_pairs=121 verdict_pairs` |
| `ci/triangle.py` | 0 | as expected | spec / recorded faces / machine, three-way | `OUTCOME=CLEAN` |
| `ci/acceptance.py` | 0 | as expected | the per-port acceptance board | `wrote docs/acceptance.md bytes=5394 ports=6 faces_excluded=5 faces_ahead_of_head=0 git_status_rc_nonzero=0` |
| `ci/link_check.py` | 0 | as expected | every relative link resolves | `OUTCOME=CLEAN markdown_faces=69 links_checked=24 resolved=24 external=0 broken=0 unreadable=0` |
| `ci/claim_digest.py --scratch-root` | 0 | as expected | quoted numbers against their sources | `OUTCOME=CLEAN stale_claims=0 coverage=full` |

## The verdict the product is selling, in one line

`verdict_disagreements=54` across `44/2640` compared cells - `24` cells carry no conflict, of which `4 (see cells_every_port_recorded_every_verdict_field)` have every verdict field recorded by every port. The last number is the one that keeps the second from being read as the sixth-port agreement story; the legs that publish both, together, are `ci/equality.py` and `docs/coverage.md`.

## What this receipt does not close

- **CI's outcome**: the workflow was triggered by the push; its conclusion is not readable from this local (no `gh`, and the API answers 403 without a token). Owner decision pending: a read-only token turns this line into a standing reading.
- **macOS and Linux result rows**: the instrument job runs the judges on three systems, not the port harnesses, which are Windows-only by construction. 44 sealed non-Windows predictions remain `NOT-RUN(no face for that OS)` in `docs/expected-summary.md`.
- **Two open instrument tickets**, both found by attempting them today and rolled back rather than left half-green: `docs/tickets/F5-acceptance-whole-tree-status.md` (the board counts six directories and lets `faces_ahead_of_head=0` read as "everything is landed", while one face in this tree is untracked - see the dirty line above) and `docs/tickets/F6-claim-digest-covers-the-ops-page.md` (the number digest cannot see the owner-facing page, which is outside the repository; three stale numbers were found there by hand).
- **This page's own self-reference**: `tracked faces=` and `dirty lines=` above were measured before this file existed. The moment it is committed, the tracked count moves by one and this face appears in history with a number that describes the tree one commit earlier - the same lag `docs/evidence.md` declares in its own line, declared here for the same reason: a generated or counted document cannot name the commit that contains it.
- **Cross-machine reproducibility**: the cold-clone verification, including the deliverable's 55 field comparisons, is one host and one interpreter. That is stated wherever the claim is made.
- Owner decisions still open: License, signing and the "发" word, and the three contract questions of the ninth round.

Commands, in the order a stranger would try them:

```
python ci/refresh_all.py                                  # every judge and every generated face
python ci/clone_parity.py --scratch-root ../sg-public \
      --source https://github.com/kinsin818/sendguard     # the published repository, cold
python tool/check.py --name "trail."                      # legal is not the same as intact
python ci/claim_digest.py --scratch-root ../sg-claims     # the numbers in the prose, against their sources
```

## Errata of this page, stated here rather than discovered by a reader

- The commit that created this file (`e050cb0`) carries a literal `%s` where a timestamp was intended: the
  message was built with a format placeholder and never substituted. Commit messages are permanent assertions in
  this repository, so it is not edited - it is named here, and this commit is the forward correction.
- `tracked faces=` on this page was counted before this file was committed, so the number is one lower than the
  tree the same commit produces. That is the self-reference lag declared above, now demonstrated by the page that
  declares it.
- `faces_ahead_of_head=0` in the acceptance row is a statement about the six canonical result directories, not
  about the whole tree; at the instant of this run one face elsewhere in the repository was untracked. The
  instrument gap is ticketed rather than hidden, and the row above is not retracted - it is scoped.
- The message of `3cf68ff` (the audit kit) says its `lint` reading's tracked count is **one** behind the tree
  that commit produces. It was **three** behind: the reading printed `tracked=1177,untracked=4` - three new faces
  plus one other window's note - and `3cf68ff` lands three of them, so the same tree afterwards reads
  `tracked=1180,untracked=1` at the unchanged denominator `names_checked=1181`. The word "one" was copied from
  the shape of the bullet above, where one file is the case; the erratum class is the same one, and that is the
  finding. Corrected here, not in history. The denominator that decides whether a name was checked at all did
  not move.
