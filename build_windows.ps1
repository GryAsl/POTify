<#
.SYNOPSIS
    Builds and packages POTify into a standalone Windows desktop distribution.

.DESCRIPTION
    1. Validates Python environment and tests.
    2. Builds standalone onedir executable using PyInstaller from POTify.spec.
    3. Copies branding assets and release documentation into the distribution folder.
    4. Executes a noninteractive smoke test on the compiled binary.
    5. Packages the portable distribution into release/POTify-v1.0.0-win64.zip.
    6. Outputs file sizes and SHA-256 checksums.
#>

[CmdletBinding()]
param(
    [switch]$SkipTests,
    [string]$DistVersion = "1.0.0"
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if ($ScriptDir) { Set-Location -Path $ScriptDir }

Write-Host "=== POTify Windows Distribution Builder ===" -ForegroundColor Cyan

# 1. Resolve Python executable
$Python = ""
if (Test-Path ".venv\Scripts\python.exe") {
    $Python = (Resolve-Path ".venv\Scripts\python.exe").Path
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $Python = (Get-Command python).Source
} else {
    Write-Error "Python interpreter not found. Please create .venv or ensure Python 3.11 is in PATH."
    exit 1
}

Write-Host ("[+] Using Python: {0}" -f $Python) -ForegroundColor DarkCyan
& $Python --version

# 2. Run test suite
if (-not $SkipTests) {
    Write-Host "[+] Running pytest suite before packaging..." -ForegroundColor DarkCyan
    & $Python -m pytest -v
    if ($LASTEXITCODE -ne 0) {
        Write-Error ("Pytest test suite failed with exit code {0}. Aborting build." -f $LASTEXITCODE)
        exit $LASTEXITCODE
    }
} else {
    Write-Host "[*] Skipping tests (SkipTests flag specified)" -ForegroundColor Yellow
}

# 3. Clean stale build artifacts
Write-Host "[+] Cleaning stale build outputs..." -ForegroundColor DarkCyan
$StaleItems = @(
    "build",
    "release\POTify",
    ("release\POTify-v{0}-win64.zip" -f $DistVersion)
)
foreach ($item in $StaleItems) {
    if (Test-Path $item) {
        Write-Host ("  Removing: {0}" -f $item)
        Remove-Item -Recurse -Force $item
    }
}

if (-not (Test-Path "release")) {
    New-Item -ItemType Directory -Path "release" | Out-Null
}

# 4. Compile with PyInstaller
Write-Host "[+] Building standalone distribution from POTify.spec..." -ForegroundColor DarkCyan
& $Python -m PyInstaller --noconfirm --clean POTify.spec
if ($LASTEXITCODE -ne 0) {
    Write-Error ("PyInstaller build failed with exit code {0}." -f $LASTEXITCODE)
    exit $LASTEXITCODE
}

$ExePath = "release\POTify\POTify.exe"
if (-not (Test-Path $ExePath)) {
    Write-Error ("Build artifact missing: {0} was not generated." -f $ExePath)
    exit 1
}

# 5. Populate release folder with supplemental files
Write-Host "[+] Staging auxiliary release files..." -ForegroundColor DarkCyan
$ReleaseAssetsDir = "release\POTify\assets"
if (-not (Test-Path $ReleaseAssetsDir)) {
    New-Item -ItemType Directory -Path $ReleaseAssetsDir | Out-Null
}
Copy-Item -Path "assets\*" -Destination $ReleaseAssetsDir -Force
Copy-Item -Path "SHIP_README.txt" -Destination "release\POTify\README.txt" -Force

# 6. Execute binary smoke test
Write-Host ("[+] Running noninteractive smoke test on {0}..." -f $ExePath) -ForegroundColor DarkCyan
& $ExePath --smoke-test
if ($LASTEXITCODE -ne 0) {
    Write-Error ("Binary smoke test failed with exit code {0}." -f $LASTEXITCODE)
    exit $LASTEXITCODE
}
Write-Host "  Smoke test verified successfully (exit code 0)." -ForegroundColor Green

# 7. Package portable ZIP archive
$ZipFileName = ("POTify-v{0}-win64.zip" -f $DistVersion)
$ZipPath = Join-Path "release" $ZipFileName
Write-Host ("[+] Packaging portable distribution archive: {0}..." -f $ZipPath) -ForegroundColor DarkCyan

$ZipScript = @"
import zipfile
from pathlib import Path

source_dir = Path('release/POTify')
zip_path = Path('release/$ZipFileName')

with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
    for file_path in sorted(source_dir.rglob('*')):
        if file_path.is_file():
            arcname = file_path.relative_to(source_dir.parent)
            zf.write(file_path, arcname)

print(f'Archive created successfully: {zip_path.stat().st_size:,} bytes')
"@

& $Python -c $ZipScript

if (-not (Test-Path $ZipPath)) {
    Write-Error ("Failed to create ZIP package: {0}" -f $ZipPath)
    exit 1
}

# 8. Compute checksums and summary
Write-Host "`n================ BUILD RECEIPT ================" -ForegroundColor Green
$ExeItem = Get-Item $ExePath
$ExeHash = (Get-FileHash -Algorithm SHA256 $ExePath).Hash
Write-Host ("Executable : {0}" -f $ExeItem.FullName)
Write-Host ("Size       : {0:N0} bytes ({1:N2} MB)" -f $ExeItem.Length, ($ExeItem.Length / 1MB))
Write-Host ("SHA-256    : {0}" -f $ExeHash)

$ZipItem = Get-Item $ZipPath
$ZipHash = (Get-FileHash -Algorithm SHA256 $ZipPath).Hash
Write-Host ("`nZIP Package: {0}" -f $ZipItem.FullName)
Write-Host ("Size       : {0:N0} bytes ({1:N2} MB)" -f $ZipItem.Length, ($ZipItem.Length / 1MB))
Write-Host ("SHA-256    : {0}" -f $ZipHash)
Write-Host "==============================================`n" -ForegroundColor Green
