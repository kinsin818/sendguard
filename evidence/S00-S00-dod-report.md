# SENDGUARD S00 DoD acceptance report

Date: 2026-10-10 (S00 close). Verifier: MainAgent (doubao seat).
Each DoD item below is checked against the frozen 军令 (豆包-终裁确认稿-总军令.md, S00 section).

| # | DoD item (frozen) | status | evidence |
|---|---|---|---|
| 1 | 三平台 CI 全绿 | PASS | run #2 `sendguard-matrix` success 47s: probe-windows-2025 / probe-macos-15 / probe-ubuntu-24.04 all green (github.com/kinsin818/sendguard/actions) |
| 2 | crossread job 绿 | PASS | crossread (node<->python interop gate) 6s, run #2 success |
| 3 | audit.exe 输出过 schema | PASS | CI "Audit self-check" builds audit(.exe/.bin) and validates JSON (`d['tool']=='sendguard-audit'`); local audit.go built CGO_ENABLED=0, sha256 cross-check vs audit.ps1 matched |
| 4 | 额度实测腿读到真实消耗数 | PASS | billing summary: metered usage **USD 0.21** (period 10-01..10-30, spike 10-10), plan GitHub Free $0/mo; screenshot `evidence/S00/quota.png`. M20 leg: full 3-OS claim KEPT (no step-back) |
| 5 | 五枚控制格基线已预跑入库 | PASS | `evidence/S00-ctrl-baseline.md`: NAMETOOLONG=err_at_syscall(ENOENT), ASCII=ok, ILLEGAL-CHAR=err_at_syscall(ENOENT), PARSE=err_at_parse, CANON node==python sha256. Also logged: Node reports ENOENT (not WinError 123) -> language self-report cannot fill os_legality_verdict |
| 6 | CI lint 三件套就位且自身带红/绿两臂 | PASS | `ci/lint.py` (runs-on whitelist / tracked-name legality incl. 8.3 short names / BOM+UTF-16LE) --selftest red+green arms passed in CI run #2 |
| 7 | longpath_mechanism 2×2 子实验有读数 | PASS | `evidence/S00-longpath-probe.md` + `S00-longpath-probe-lpe1.md`: LPE=0 + plain -> Node auto `\\?\` prefix (prefix_rewrite); LPE=1 + plain -> manifest path; per-language mechanism recorded |
| 8 | 六门工具链"路径+版本"逐条在表 | PASS | `evidence/S00/toolchain.txt`: Node v22.23.2 (sandbox path), Python 3.13.13 (sandbox path), Go 1.23.5, rustc/cargo 1.98.0, Java 17.0.17 (3 jvms on PATH), dotnet 8.0.413 (csproj confirmed, C# closed per C4) |
| 9 | 双击链打样已录（Tauri 顺不顺） | PASS | `docs/pilots/tauri-pilot.md`: Tauri v2.12.2 build OK, sg-pilot.exe 8.47MB, launch -> window created (HWND 395702, title SENDGUARD Pilot). Tauri path CONFIRMED; Electron fallback not triggered |
| 10 | 岗位互换表已按 B14 更新 | PASS | `docs/roles.md`: W-PY=小侠, W-RUST=小工; instrument author (老马 audit.go) not measured-language (M10/M17); every seat holds 2 languages after swap |

## Additional S00 legs recorded (军令 S00 Required work)

- Repo: **kinsin818/sendguard** public, pushed (commits bb95fe5, 31c40e2, 80e925d, ae48d1c).
- OAuth pre-check (B23 + 老板拍板 6): `get_me` OK (kinsin818), create_repository OK, git ls-files illegal-name assertion testable via lint.py piece 2.
- Predictions archive isolated: `evidence/S00-predictions.md` (non-gating, "we guessed wrong is whitepaper gold").
- blind-map sealed: `evidence/S00/blind-map.json` (5 blind samples, hex-only, sha256 locked; to be unsealed after S01 audit).
- Env metadata: `evidence/S00/env-windows.json` (max_component=255, LongPathsEnabled=0, 8dot3name=2, locale zh-CN, NTFS).

## Conclusion

S00 DoD: **10/10 PASS**. No open red lines. Proceed to S01.
