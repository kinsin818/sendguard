# Cleanup notice (project rule)

The harness **never deletes anything** (no `rmtree` / `remove` / `unlink`).
Probe run directories accumulate under `%TEMP%\sendguard-run\` (outside the repo).

Reason: deleting a reserved-name entry (`CON`, `NUL`, `AUX…`) via the plain path
is resolved to the **device namespace** and fails / leaves debris; a hidden
delete in the harness would silently corrupt the evidence chain.

To clean up manually, on Windows use the **extended path form only**, e.g.:

```powershell
# list first, then remove with the \\?\ prefix
Get-ChildItem -Force -Recurse "$env:TEMP\sendguard-run" | Select-Object FullName
Remove-Item -LiteralPath "\\?\$env:TEMP\sendguard-run" -Recurse -Force
```

If any removal is required as part of a run, the harness records
`cleanup_failed` and leaves the directory in place. No automated cleanup ships.
