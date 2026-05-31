param(
    [switch]$NoAlias
)

$AppName = "beckyup"
$SrcDir = Join-Path (Split-Path $PSScriptRoot) "backup_tool"
$ProjectDir = $PSScriptRoot

Write-Host "=== $AppName Installer (Windows) ===" -ForegroundColor Cyan
Write-Host "Source: $SrcDir"

# Step 1: Install deps
Write-Host "`n[1/3] Installing dependencies..." -ForegroundColor Yellow
Set-Location $SrcDir
if (Get-Command uv -ErrorAction SilentlyContinue) {
    uv sync 2>$null
    if (-not $?) { uv pip install -r requirements.txt -q }
} else {
    pip install -r requirements.txt -q
}
Write-Host "  ✓ Dependencies installed" -ForegroundColor Green

# Step 2: Add PowerShell alias (profile)
if (-not $NoAlias) {
    $ProfileDir = Split-Path $PROFILE
    if (-not (Test-Path $ProfileDir)) { New-Item -ItemType Directory -Path $ProfileDir -Force | Out-Null }

    $AliasLine = "function beckyup { Set-Location '$SrcDir'; uv run python main.py @args }"
    $FallbackLine = "function beckyup { Set-Location '$SrcDir'; python main.py @args }"

    if (Test-Path $PROFILE -PathType Leaf) {
        $content = Get-Content $PROFILE -Raw
        if ($content -match "function beckyup") {
            Write-Host "[2/3] Alias already in profile — skipping" -ForegroundColor Yellow
        } else {
            Add-Content $PROFILE "`n# $AppName — emergency backup tool`n$AliasLine"
            Write-Host "  ✓ Alias added to $PROFILE" -ForegroundColor Green
            Write-Host "    Restart PowerShell or run: . `$PROFILE"
        }
    } else {
        New-Item $PROFILE -ItemType File -Force | Out-Null
        Add-Content $PROFILE "`n# $AppName — emergency backup tool`n$AliasLine"
        Write-Host "  ✓ Profile created and alias added" -ForegroundColor Green
    }
}

# Step 3: First run hint
Write-Host "`n[3/3] First run:" -ForegroundColor Yellow
Write-Host "`n  beckyup`n" -ForegroundColor White
Write-Host "  This starts the setup wizard. Follow the prompts:"
Write-Host "    1. Pick folders to back up"
Write-Host "    2. Select file types"
Write-Host "    3. Plug in your backup USB drive"
Write-Host "    4. Choose security mode"
Write-Host "    5. Enable autostart"
Write-Host "`n  After setup, beckyup runs in the background."
Write-Host "  Plug in your known USB → backup starts automatically."
Write-Host "`n━━━ Installation structure ━━━"
Write-Host "  App:     $SrcDir"
Write-Host "  Config:  $env:APPDATA\backup_tool\config.json"
Write-Host "  Logs:    $env:APPDATA\backup_tool\logs\"
Write-Host "  Alias:   PowerShell profile"
Write-Host "  Autostart (if enabled): HKCU\Run\$AppName"
