import json
import subprocess
import sys
import zipfile

import pytest

from servicios.script_actualizacion import SCRIPT


@pytest.mark.skipif(sys.platform != "win32", reason="Reemplazo portable de Windows")
@pytest.mark.parametrize("bloqueada", [False, True])
def test_copias_old_se_limpian_o_aborta_sin_reemplazar(tmp_path, bloqueada):
    app = tmp_path / "instalación"
    app.mkdir()
    exe = app / "CAAPD.exe"
    exe.write_bytes(b"exe anterior")
    interno = app / "_internal"
    interno.mkdir()
    (interno / "anterior.txt").write_text("anterior")
    viejo = app / "_internal.old"
    viejo.mkdir()
    pendiente = viejo / "pendiente.txt"
    pendiente.write_text("pendiente")
    (app / "CAAPD.exe.old").write_text("copia vieja")
    (app / "datos").mkdir()
    (app / "datos/conservar.txt").write_text("datos")
    archivo_zip = tmp_path / "nuevo.zip"
    with zipfile.ZipFile(archivo_zip, "w") as z:
        z.writestr("CAAPD.exe", b"exe nuevo")
        z.writestr("_internal/ui/estilos/tema.qss", b"tema")
    config = tmp_path / "config.json"
    config.write_text(json.dumps(dict(exe=str(exe), zip=str(archivo_zip),
                                     pid=0, args=[])), encoding="utf-8")
    # Evitar un diálogo modal durante la prueba de fallo.
    script = tmp_path / "aplicar.ps1"
    script.write_text("\n".join(
        "    Write-Output 'ERROR_DIALOG'" if "[System.Windows.Forms.MessageBox]::Show" in linea else linea
        for linea in SCRIPT.splitlines()), encoding="utf-8-sig")
    bloqueo = pendiente.open("rb") if bloqueada else None
    try:
        resultado = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", str(script), str(config)], capture_output=True, timeout=60)
    finally:
        if bloqueo:
            bloqueo.close()
    assert (app / "datos/conservar.txt").read_text() == "datos"
    if bloqueada:
        assert resultado.returncode == 1
        assert exe.read_bytes() == b"exe anterior"
        assert (interno / "anterior.txt").read_text() == "anterior"
    else:
        assert resultado.returncode == 0, resultado.stderr
        assert exe.read_bytes() == b"exe nuevo"
        assert (interno / "ui/estilos/tema.qss").is_file()
        assert not viejo.exists()
        assert not (app / "CAAPD.exe.old").exists()
