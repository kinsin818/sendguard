# SENDGUARD audit.ps1 - Windows third-party cross-check enumerator.
# Independent from audit.go (different implementation path); same output shape.
# Usage:  powershell -File audit.ps1 <dir>
# All English, ASCII preferred (M21). Samples by hex only.
$ErrorActionPreference = "Stop"

if ($args.Count -lt 1) {
    Write-Error "usage: audit.ps1 <dir>"
    exit 2
}
$dir = [IO.Path]::GetFullPath($args[0])

function Get-Hex([byte[]]$bytes) {
    return -join ($bytes | ForEach-Object { $_.ToString("x2") })
}

function Get-Utf16LeHex([string]$s) {
    $bytes = [Text.Encoding]::Unicode.GetBytes($s)  # UTF-16LE
    return Get-Hex $bytes
}

function Get-CodepointHex([string]$s) {
    $sb = New-Object System.Text.StringBuilder
    foreach ($ch in $s.ToCharArray()) {
        [void]$sb.Append(([int]$ch).ToString("X4"))
    }
    return $sb.ToString()
}

function Get-Sha256([string]$p) {
    try {
        $fs = [IO.File]::OpenRead($p)
        try {
            $sha = [Security.Cryptography.SHA256]::Create()
            $hash = $sha.ComputeHash($fs)
            return Get-Hex $hash
        } finally { $fs.Dispose() }
    } catch { return "" }
}

$entries = @()
foreach ($item in Get-ChildItem -LiteralPath $dir -Force) {
    $name = $item.Name
    $e = [ordered]@{
        name_utf8_hex     = Get-Hex ([Text.Encoding]::UTF8.GetBytes($name))
        name_utf16le_hex  = Get-Utf16LeHex $name
        name_codepoint_hex = Get-CodepointHex $name
        size              = if ($item.PSIsContainer) { $null } else { $item.Length }
        mode              = "win-" + $(if ($item.PSIsContainer) { "dir" } else { "file" })
        mtime_unix_nano   = ([int64]([DateTimeOffset]$item.LastWriteTimeUtc).ToUnixTimeMilliseconds()) * 1000000
        sha256            = if ($item.PSIsContainer) { "" } else { Get-Sha256 $item.FullName }
        is_dir            = [bool]$item.PSIsContainer
    }
    $entries += $e
}

$out = [ordered]@{
    tool       = "sendguard-audit-ps1"
    version    = "0.1.0-s00"
    os         = "windows/powershell"
    ps_version = $PSVersionTable.PSVersion.ToString()
    dir        = $dir
    started_at = [DateTime]::UtcNow.ToString("o")
    entries    = $entries
}
$out | ConvertTo-Json -Depth 6
