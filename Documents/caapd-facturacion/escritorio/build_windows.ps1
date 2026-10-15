$ErrorActionPreference = "Stop"

Push-Location $PSScriptRoot
try {
    $python = Join-Path $PSScriptRoot "venv\Scripts\python.exe"
    if (-not (Test-Path $python)) {
        $python = (Get-Command python -ErrorAction Stop).Source
    }

    & $python -c "import PyInstaller" 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller is missing. Install build requirements first: python -m pip install -r requirements-build.txt"
    }

    & $python -m PyInstaller --noconfirm --clean --distpath dist --workpath build CAAPD.spec
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE"
    }

    $appRoot = Join-Path $PSScriptRoot "dist\CAAPD"
    @("Base de datos", "datos", "logs", "plantillas", "salida", "respaldos") | ForEach-Object {
        New-Item -ItemType Directory -Force -Path (Join-Path $appRoot $_) | Out-Null
    }

    Write-Host "Build complete: $(Join-Path $appRoot 'CAAPD.exe')"
}
finally {
    Pop-Location
}
