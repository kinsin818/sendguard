# SENDGUARD S00 quota record (Actions free minutes + macOS multiplier)

Source: GitHub Docs "About billing for GitHub Actions"
https://docs.github.com/en/billing/managing-billing-for-your-products/managing-billing-for-github-actions/about-billing-for-github-actions
Fetched: 2026-10-10 (S00).

## Official numbers

- GitHub Actions usage is **free for standard GitHub-hosted runners in PUBLIC
  repositories**. (Larger runners are NOT free even in public repos.)
- Private-repo included minutes per month (GitHub Free): **2,000**.
- Minute multipliers (standard runners): Linux **1x** / Windows **2x** /
  macOS **10x**.
- Per-minute rates beyond included (standard): Linux 2-core $0.008 /
  Windows 2-core $0.016 / macOS 3-4 core $0.08.
- Minutes reset monthly; storage does not.

## Zero-cash implication (M8 / M20)

- CI runs ONLY on public-repo standard runners (windows-2025, macos-15,
  ubuntu-24.04). No private-repo CI (macOS 10x would burn paid minutes).
- **macOS free-minute leg**: a 3-line macOS hello-world job is run at S00; the
  ACTUAL consumption must be read from the billing/usage readout. If no real
  consumption figure can be read, the six-language full-matrix claim steps back
  to "deep-measure Node/Python/Go only" (no gambling on macOS being free).
  - macOS hello-world leg status: PENDING (runs after repo push; readout from
    GitHub usage page, login state permitting).
- quota.png: screenshot of the billing page / usage readout appended when
  accessible; official numbers above remain the paper trail.
