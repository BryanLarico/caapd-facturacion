"""Eliminar usuario: confirmación escribiendo BORRAR y borrado en padrón local."""
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt

from servicios.datos import ServicioDatosMemoria
from servicios.datos_padron import ServicioDatosPadron
from ui.paginas.usuarios_dialogos import DialogoEliminarUsuario


def _usuario():
    return {"id_usuario": "30771072", "nombre": "CONDORI MAMANI, CARLOS", "nro_conexion": "000796",
            "sector": "AYACUCHO", "direccion": "CALLE 1", "codigo_categoria": "A", "activo": True,
            "medidores": ["22392996"]}


def test_dialogo_exige_escribir_borrar(qtbot):
    d = DialogoEliminarUsuario(usuario=_usuario())
    qtbot.addWidget(d)
    assert not d.btn_eliminar.isEnabled()
    d.campo_confirmar.setText("borra")
    assert not d.btn_eliminar.isEnabled()
    d.campo_confirmar.setText("borrar")          # minúsculas también valen
    assert d.btn_eliminar.isEnabled()
    d.campo_confirmar.setText("BORRAR")
    qtbot.mouseClick(d.btn_eliminar, Qt.MouseButton.LeftButton)
    assert d.confirmado and d.result() == DialogoEliminarUsuario.DialogCode.Accepted


def test_dialogo_cancelar_no_confirma(qtbot):
    d = DialogoEliminarUsuario(usuario=_usuario(), tiene_movimientos_mes=True)
    qtbot.addWidget(d)
    qtbot.mouseClick(d.btn_cancelar, Qt.MouseButton.LeftButton)
    assert not d.confirmado


def test_servicio_padron_elimina_y_persiste_en_excel():
    tmp = Path(tempfile.mkdtemp())
    s = ServicioDatosPadron(base_dir=tmp)
    s.config["mes_actual"] = {"estado": "CERRADO", "periodo": s.periodo}  # sin Firebase
    u = _usuario()
    s.guardar_usuario(u["id_usuario"], u, agregar_al_mes=True)
    assert u["id_usuario"] in s.cargar_usuarios()
    res = s.eliminar_usuario(u["id_usuario"])
    assert res["eliminado"] is True
    assert u["id_usuario"] not in s.cargar_usuarios()
    assert u["id_usuario"] not in s.mes
    # Reabrir desde disco: sigue eliminado
    s2 = ServicioDatosPadron(base_dir=tmp)
    assert u["id_usuario"] not in s2.cargar_usuarios()


def test_pagina_usuarios_boton_eliminar(qtbot):
    from ui.paginas.usuarios import PaginaUsuarios
    u = _usuario()
    serv = ServicioDatosMemoria(usuarios={u["id_usuario"]: u})
    pag = PaginaUsuarios(serv)
    qtbot.addWidget(pag)
    pag.cargar_datos_asincrono(forzar=True)
    qtbot.waitUntil(lambda: pag.proxy_model.rowCount() == 1, timeout=3000)
    assert not pag.btn_accion_eliminar.isEnabled()
    pag.tabla.selectRow(0)
    assert pag.btn_accion_eliminar.isEnabled()
    # Simular confirmación escrita y eliminar
    import ui.paginas.usuarios as mod

    class _DialogoFalso:
        def __init__(self, *a, **k): self.confirmado = True
        def exec(self): return DialogoEliminarUsuario.DialogCode.Accepted
        DialogCode = DialogoEliminarUsuario.DialogCode
    mod.DialogoEliminarUsuario = _DialogoFalso
    try:
        pag._accion_eliminar()
    finally:
        mod.DialogoEliminarUsuario = DialogoEliminarUsuario
    assert u["id_usuario"] not in serv.usuarios
