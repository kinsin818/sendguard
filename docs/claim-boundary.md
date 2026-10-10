# Claim boundary - what each result licenses you to say

Written for a reader who will quote this project to someone else. Three columns: what was measured, what
that supports, and the sentence that would be an overclaim. Anything not listed as measured is not
available to anybody, including the author.

Current state, re-checkable with the commands in `README.md` §1:

| | measured | supports | overclaim to avoid |
|---|---|---|---|
| **Ports** | Six ports exist and six instruments were written. **Five** currently have a readable result face: `csharp`, `go`, `java`, `python`, `rust`. The TypeScript face went empty mid-rebuild at 07:16 and its earlier cells were never committed. | "one frozen specification was implemented independently in six languages, and five of the six landed comparable results" | "six ports agree" - the gate can only compare faces that exist |
| **Operating systems** | Windows 10 build 19041, x64, one host, `LongPathsEnabled=0`, console code page 936. No macOS row, no Linux row: CI has not run, and pushing to the public repository is the owner's act. | "measured on Windows" | "cross-platform" in any sentence, in any artifact, including a screenshot caption |
| **Cells** | 44 required cells (20 traps with member splits, 5 pinned controls, 5 blind samples, 12 length rungs) + 26 per-language `tapi` rows + tiers published as `extra`. | "a frozen set of 44 questions, asked of every port" | quoting a percentage over the 44 while the length rungs are still excluded as `unpinned_input` |
| **Verdict fields** | The checker's answer about a name: legality verdict, mechanism class, phantom, roundtrip, mutation, enum/stat agreement, length triple, bytes written, bytes on disk, landed name. These are what the equality gate compares. | "six independent implementations reached the same verdict on N cells, and differed on M" - with N and M read from `ci/equality.py` in the same breath | any sentence containing "identical" without the number of compared cells attached to it |
| **Probe fields** | What each language's own standard library did: `create_result`, `error_stage`, `read_result`, `longpath_mechanism`, `deps_*`. Published as the matrix. | "the ports differ in how their stdlibs behave, which is why a checker built on one language is a bet" | "the ports disagree about the file system" - they mostly disagree about their own APIs, which is a different claim |
| **Not comparable** | Cells excluded because the ports did not ask the same thing: different input bytes (`unpinned_input`), different layer or path form (`incomparable`), or a port with no OS-level legality channel (`verdict_via: none`). | "this project has no comparable length evidence yet" (true as of this commit) | treating an excluded cell as either agreement or a defect |
| **Absences** | A field one port did not record is `NOT-RECORDED`; a cell no port answered is a gap named in `docs/GAP.md`; a declared port with no face is `FACE-MISSING`. | "this port did not measure that" | filling an absence with the neighbours' value - the gate refuses to, and so should a quotation |

Rules this file exists to enforce:

1. **Language count is not capability.** "Six languages" describes the sample, not the skill. The skill is
   the pipeline in `docs/journey.md`, and it is why a seventh language is a work order rather than a
   research problem.
2. **A number is only quotable with its denominator and its date.** `docs/evidence.md` carries both, and is
   regenerated rather than edited.
3. **Unmeasured is a fact about the project, not a placeholder for optimism.** If a cell was not run, the
   sentence about it says so.
4. **The machine's own tools are the referee, not the ports.** Where `evidence/S00/referee-*.md` disagrees
   with all six ports and with the sealed expectation, the disagreement is published instead of resolved by
   vote.
