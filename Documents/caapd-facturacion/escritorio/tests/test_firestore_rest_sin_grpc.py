"""
tests/test_firestore_rest_sin_grpc.py — La ruta REST de «Traer lecturas de los lectores»
NO debe importar firebase_client / firebase_admin / gRPC (código nativo) dentro del
hilo de trabajo. Esa importación tardía era la causa del cierre silencioso en Windows
(«QThreadStorage: entry N destroyed before end of thread»).
"""
import json
import subprocess
import sys
from pathlib import Path

DIR_ESCRITORIO = Path(__file__).resolve().parent.parent

CODIGO = r"""
import sys, json
sys.path.insert(0, %r)
from servicios import firestore_rest
firestore_rest.ruta_credenciales()          # no debe arrastrar gRPC
firestore_rest.precargar_dependencias()     # solo requests + google-auth
mods = sorted(m for m in sys.modules if m.split('.')[0] in ('firebase_client', 'firebase_admin', 'grpc'))
print(json.dumps(mods))
"""


def test_ruta_rest_no_importa_grpc_ni_firebase_admin():
    res = subprocess.run(
        [sys.executable, "-c", CODIGO % str(DIR_ESCRITORIO)],
        capture_output=True, text=True, timeout=120, cwd=str(DIR_ESCRITORIO),
    )
    assert res.returncode == 0, res.stderr
    modulos = json.loads(res.stdout.strip().splitlines()[-1])
    assert modulos == [], f"La ruta REST importó código de gRPC/firebase_admin: {modulos}"


def test_ruta_credenciales_respeta_variable_de_entorno(tmp_path, monkeypatch):
    from servicios import firestore_rest

    clave = tmp_path / "clave.json"
    clave.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("FIREBASE_KEY_PATH", str(clave))
    assert firestore_rest.ruta_credenciales() == clave


def test_worker_descarga_usa_firestore_rest(monkeypatch):
    from servicios import descarga_lecturas_proc, firestore_rest

    eventos = []
    llamadas = []

    def descargar(periodo, campos, timeout, callback_progreso):
        llamadas.append((periodo, campos, timeout))
        callback_progreso(1, "documento recibido")
        return {"30771152": {"nombre": "Usuario", "medidores": []}}

    monkeypatch.setattr(firestore_rest, "descargar_documentos_mes", descargar)
    monkeypatch.setattr(descarga_lecturas_proc, "_emitir", eventos.append)

    resultado = descarga_lecturas_proc.descargar("2026-09", timeout_stream=30)

    assert resultado == {
        "docs": {"30771152": {"nombre": "Usuario", "medidores": []}},
        "recibidos": 1,
    }
    assert llamadas == [
        ("2026-09", ("medidores", "nombre"), (firestore_rest.TIMEOUT_CONEXION_S, 30))
    ]
    assert any(evento.get("t") == "prog" for evento in eventos)


def test_worker_registra_inicio_y_fin_en_log():
    """ui/hilos.py debe dejar rastro de cada hilo para diagnosticar cierres sin traceback."""
    fuente = (DIR_ESCRITORIO / "ui" / "hilos.py").read_text(encoding="utf-8")
    assert "Hilo '%s' iniciado" in fuente
    assert "Hilo '%s' terminado" in fuente
    assert "def precargar_firebase_en_hilo_principal" in fuente
    assert "def instalar_diagnostico_cierre" in fuente


def test_main_desactiva_quit_on_last_window_closed():
    fuente = (DIR_ESCRITORIO / "main.py").read_text(encoding="utf-8")
    assert "setQuitOnLastWindowClosed(False)" in fuente
    assert "precargar_firebase_en_hilo_principal" in fuente
    ventana = (DIR_ESCRITORIO / "ui" / "ventana_principal.py").read_text(encoding="utf-8")
    assert "app.quit" in ventana
