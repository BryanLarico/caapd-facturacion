"""Script independiente de reemplazo; se ejecuta después de cerrar Qt."""

SCRIPT = r'''
param([string]$Config)
$ErrorActionPreference = 'Stop'
$c = Get-Content -LiteralPath $Config -Raw -Encoding UTF8 | ConvertFrom-Json
$app = Split-Path -Parent $c.exe
$log = Join-Path $app 'logs/actualizador_aplicar.log'
New-Item -ItemType Directory -Force (Split-Path $log) | Out-Null
function Log($s) { Add-Content -LiteralPath $log -Encoding UTF8 -Value ("{0:o} {1}" -f (Get-Date), $s) }
function Mover($origen, $destino) {
    for ($n = 0; $n -lt 30; $n++) {
        try { Move-Item -LiteralPath $origen -Destination $destino -ErrorAction Stop; return }
        catch { if ($n -eq 29) { throw }; Start-Sleep -Milliseconds 500 }
    }
}
$interno = Join-Path $app '_internal'
$viejo = Join-Path $app '_internal.old'
$exeViejo = "$($c.exe).old"
$extraido = Join-Path (Split-Path $Config) 'extraido'
$movioInterno = $false
$movioExe = $false
$nuevoInterno = $false
$nuevoExe = $false
try {
    Log "Esperando PID $($c.pid)"
    Wait-Process -Id $c.pid -ErrorAction SilentlyContinue
    Get-CimInstance Win32_Process -Filter "Name = 'CAAPD.exe'" | ForEach-Object {
        if ($_.ExecutablePath -and [string]::Equals($_.ExecutablePath, $c.exe, [StringComparison]::OrdinalIgnoreCase)) {
            Log "Deteniendo proceso de esta instalación: $($_.ProcessId)"
            Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop
            Wait-Process -Id $_.ProcessId -ErrorAction SilentlyContinue
        }
    }
    Log "Extrayendo $($c.zip)"
    Expand-Archive -LiteralPath $c.zip -DestinationPath $extraido
    foreach ($r in @('CAAPD.exe', '_internal/ui/estilos/tema.qss')) {
        if (-not (Test-Path -LiteralPath (Join-Path $extraido $r) -PathType Leaf)) { throw "Falta $r en la actualización" }
    }
    # No sobrescribir copias de recuperación de una ejecución anterior.
    if ((Test-Path -LiteralPath $viejo) -or (Test-Path -LiteralPath $exeViejo)) {
        throw 'Hay copias .old pendientes. Contacte a soporte antes de actualizar.'
    }
    Mover $interno $viejo
    $movioInterno = $true
    Mover $c.exe $exeViejo
    $movioExe = $true
    Mover (Join-Path $extraido '_internal') $interno
    $nuevoInterno = $true
    Mover (Join-Path $extraido 'CAAPD.exe') $c.exe
    $nuevoExe = $true
    if (-not (Test-Path -LiteralPath (Join-Path $interno 'ui/estilos/tema.qss') -PathType Leaf)) {
        throw 'Falta tema.qss después del reemplazo'
    }
    Log 'Actualización aplicada OK'
} catch {
    Log "ERROR: $_"
    try {
        if ($nuevoExe) { Remove-Item -LiteralPath $c.exe -Force }
        if ($nuevoInterno) { Remove-Item -LiteralPath $interno -Recurse -Force }
        if ($movioExe) { Mover $exeViejo $c.exe }
        if ($movioInterno) { Mover $viejo $interno }
        Log 'Instalación anterior restaurada; datos sin modificar.'
    } catch { Log "ERROR RESTAURANDO: $_" }
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show("No se pudo actualizar. Se intentó restaurar la instalación anterior. Sus datos no se modificaron. Consulte $log", 'Error al actualizar') | Out-Null
    exit 1
}
foreach ($p in @($viejo, $exeViejo)) {
    try { Remove-Item -LiteralPath $p -Recurse -Force; Log "Eliminado $p" }
    catch { Log "Limpieza pendiente: $p : $_" }
}
try {
    # ArgumentList usa la misma representación que la línea de comandos Windows.
    $argumentos = @($c.args | ForEach-Object { '"' + ([string]$_ -replace '(\\*)"', '$1$1\"' -replace '(\\+)$', '$1$1') + '"' })
    if ($argumentos.Count) { Start-Process -FilePath $c.exe -ArgumentList $argumentos -WorkingDirectory $app }
    else { Start-Process -FilePath $c.exe -WorkingDirectory $app }
    Log 'Aplicación reiniciada'
} catch { Log "ERROR al reiniciar: $_" }
'''
