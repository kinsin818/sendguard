# SENDGUARD double-click chain pilot (B19 technical half)

Date: 2026-10-10 (S00). Verdict: **Tauri path OK** -> use Tauri for the
sender-side checker GUI unless a later stage finds a blocker.

## What was verified

| item | value |
|---|---|
| stack | Tauri v2.12.2 (Rust 1.98.0, cargo 1.98.0), frontend static HTML |
| build | `cargo build --release` in src-tauri; first build needed icon.ico (generated 32x32, PNG-in-ICO) |
| artifact | `target/release/sg-pilot.exe` = 8,470,016 bytes |
| launch | Start-Process (double-click equivalent) |
| window | title = "SENDGUARD Pilot", MainWindowHandle = 395702, Responding = True |
| teardown | process stopped cleanly after check |

## Findings

1. Double-click chain works: exe launches, window is really created
   (non-zero HWND), process responsive. No console flash
   (`windows_subsystem = "windows"` in main.rs).
2. Tauri v2 needs `src-tauri/icons/icon.ico` for the Windows resource;
   a minimal 32x32 PNG-in-ICO satisfies `tauri-build` for a pilot.
3. Incremental rebuild was 46.76s after first full dependency compile.
4. No GUI-specific blocker found. Electron fallback NOT triggered.

## Implications for S10

- Checker GUI shell: Tauri (Rust). Frontend kept thin (architecture rule:
  valuable logic server-side / engine-side; frontend is a shell).
- Release binary size ~8.5MB before optimization (trimpath/upx out of
  scope for now).
- Full bundle (installer) still needs real icons + signing decision (N2,
  pending owner).
