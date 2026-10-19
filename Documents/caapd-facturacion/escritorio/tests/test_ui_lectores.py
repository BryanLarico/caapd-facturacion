"""
tests/test_ui_lectores.py — Pruebas unitarias de la pantalla y modelos de lectores móviles.
"""
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLineEdit

from servicios.datos import ServicioDatosMemoria
from ui.paginas.lectores import PaginaLectores
from ui.paginas.lectores_dialogos import DialogoLector
from ui.paginas.lectores_modelo import ModeloLectores, ProxyLectores


@pytest.fixture
def servicio_memoria():
    return ServicioDatosMemoria()


def test_modelo_y_proxy_lectores():
    lectores = [
        {"uid": "uid1", "email": "lector1@caapd.org", "display_name": "Carlos Quispe", "disabled": False, "last_sign_in": 1700000000000},
        {"uid": "uid2", "email": "lector2@caapd.org", "display_name": "Maria Flores", "disabled": True, "last_sign_in": None},
    ]

    modelo = ModeloLectores(lectores)
    assert modelo.rowCount() == 2
    assert modelo.columnCount() == 5

    # Display values
    assert modelo.data(modelo.index(0, 0)) == "lector1@caapd.org"
    assert modelo.data(modelo.index(0, 1)) == "Carlos Quispe"
    assert modelo.data(modelo.index(0, 2)) == "Activo"
    assert modelo.data(modelo.index(1, 2)) == "Deshabilitado"

    # Proxy filtering
    proxy = ProxyLectores()
    proxy.setSourceModel(modelo)
    assert proxy.rowCount() == 2

    # Filtrar solo activos
    proxy.set_filtro_estado("activos")
    assert proxy.rowCount() == 1
    assert proxy.data(proxy.index(0, 0)) == "lector1@caapd.org"

    # Filtrar solo deshabilitados
    proxy.set_filtro_estado("deshabilitados")
    assert proxy.rowCount() == 1
    assert proxy.data(proxy.index(0, 0)) == "lector2@caapd.org"

    # Filtrar por texto
    proxy.set_filtro_estado("todos")
    proxy.set_texto_filtro("maria")
    assert proxy.rowCount() == 1
    assert proxy.data(proxy.index(0, 1)) == "Maria Flores"


def test_pagina_lectores_creacion_y_carga(qtbot, servicio_memoria, monkeypatch):
    servicio_memoria.crear_lector("test@caapd.org", "123456", "Test Lector")
    llamadas_listar = []
    listar_lectores_original = servicio_memoria.listar_lectores

    def listar_lectores():
        llamadas_listar.append(True)
        return listar_lectores_original()

    monkeypatch.setattr(servicio_memoria, "listar_lectores", listar_lectores)

    pagina = PaginaLectores(servicio_memoria)
    qtbot.addWidget(pagina)

    # La pantalla no debe consultar Firebase al construirse; se carga al abrirla.
    assert pagina.lista_lectores_completa == []
    assert llamadas_listar == []
    pagina.cargar_datos_asincrono()
    qtbot.waitUntil(lambda: len(pagina.lista_lectores_completa) == 1, timeout=2000)
    assert llamadas_listar == [True]

    assert pagina.modelo_base.rowCount() == 1
    assert pagina.btn_accion_editar.isEnabled() is False

    # Seleccionar fila
    pagina.tabla.selectRow(0)
    assert pagina.btn_accion_editar.isEnabled() is True
    assert pagina.btn_accion_cambiar_estado.isEnabled() is True
    assert pagina.btn_accion_eliminar.isEnabled() is True
    assert pagina.btn_accion_cambiar_estado.text() == "Desactivar"


def test_pagina_lectores_oculta_registros_sin_correo_sin_borrarlos(qtbot, servicio_memoria):
    servicio_memoria.crear_lector(
        "bryanlaricoro28@gmail.com", "123456", "Bryan Larico"
    )
    servicio_memoria.lectores.update({
        sector: {
            "uid": sector,
            "email": sector,
            "display_name": sector,
            "disabled": False,
        }
        for sector in ("AYACUCHO", "CHAUPICERCA", "BARRIO DE CHAUPI")
    })

    pagina = PaginaLectores(servicio_memoria)
    qtbot.addWidget(pagina)
    pagina.cargar_datos_asincrono()
    qtbot.waitUntil(
        lambda: pagina.modelo_base.rowCount() == 1
        and not pagina.alerta_flash.isHidden(),
        timeout=2000,
    )

    assert pagina.lista_lectores_completa[0]["email"] == "bryanlaricoro28@gmail.com"
    assert pagina.modelo_base.rowCount() == 1
    assert "Se ocultaron 3 registros" in pagina.alerta_flash.lbl_mensaje.text()
    assert len(servicio_memoria.lectores) == 4


def test_dialogo_lector_validacion(qtbot, servicio_memoria):
    diag = DialogoLector(servicio_memoria, lector=None)
    qtbot.addWidget(diag)

    assert diag.lbl_error.objectName() == "dialogo_error"
    assert diag.btn_guardar.text() == "Guardar Lector"
    assert not hasattr(diag, "btn_ver_pass")
    assert diag.txt_password.echoMode() == QLineEdit.EchoMode.Password
    diag.chk_mostrar_contrasenas.setChecked(True)
    assert diag.txt_password.echoMode() == QLineEdit.EchoMode.Normal
    assert diag.txt_confirm_pass.echoMode() == QLineEdit.EchoMode.Normal
    diag.chk_mostrar_contrasenas.setChecked(False)
    assert diag.txt_password.echoMode() == QLineEdit.EchoMode.Password
    assert diag.txt_confirm_pass.echoMode() == QLineEdit.EchoMode.Password

    # Intentar guardar sin correo
    diag._guardar()
    assert not diag.lbl_error.isHidden()
    assert "correo electrónico" in diag.lbl_error.text()

    # Correo válido pero contraseña corta
    diag.txt_email.setText("nuevo@caapd.org")
    diag.txt_password.setText("123")
    diag._guardar()
    assert "al menos 6 caracteres" in diag.lbl_error.text()

    # Contraseñas no coinciden
    diag.txt_password.setText("123456")
    diag.txt_confirm_pass.setText("654321")
    diag._guardar()
    assert "no coinciden" in diag.lbl_error.text()


def test_dialogo_confirmacion(qtbot):
    from ui.componentes.dialogo_confirmar import DialogoConfirmacion
    diag = DialogoConfirmacion(
        parent=None,
        titulo="Confirmar desactivar",
        mensaje_principal="¿Está seguro de desactivar la cuenta?",
        detalle="Lector: test@caapd.org",
        texto_confirmar="Desactivar",
        texto_cancelar="Cancelar",
        es_peligro=True,
    )
    qtbot.addWidget(diag)
    assert diag.btn_confirmar.text() == "Desactivar"
    assert diag.btn_cancelar.text() == "Cancelar"


def test_cambio_estado_optimista_instantaneo(qtbot, servicio_memoria):
    servicio_memoria.crear_lector("instantaneo@caapd.org", "123456", "Lector Rapido")
    pagina = PaginaLectores(servicio_memoria)
    qtbot.addWidget(pagina)

    pagina.cargar_datos_asincrono()
    qtbot.waitUntil(lambda: len(pagina.lista_lectores_completa) == 1, timeout=2000)

    # Seleccionar fila 0
    pagina.tabla.selectRow(0)
    assert pagina.btn_accion_cambiar_estado.text() == "Desactivar"

    # Desactivar con actualización optimista (0 ms)
    pagina._accion_cambiar_estado()

    # Inmediatamente debe reflejarse en la UI sin esperar red
    assert pagina.modelo_base.data(pagina.modelo_base.index(0, 2)) == "Deshabilitado"
    assert pagina.btn_accion_cambiar_estado.text() == "Activar"
    assert "desactivada" in pagina.alerta_flash.lbl_mensaje.text()

    # Esperar que el worker secundario finalice la sincronización
    qtbot.waitUntil(lambda: pagina.thread_pool.activeThreadCount() == 0, timeout=2000)

    # Reactivar inmediatamente
    pagina._accion_cambiar_estado()
    assert pagina.modelo_base.data(pagina.modelo_base.index(0, 2)) == "Activo"
    assert pagina.btn_accion_cambiar_estado.text() == "Desactivar"
    assert "activada" in pagina.alerta_flash.lbl_mensaje.text()


def test_modelo_actualizacion_y_eliminacion_fila_unica():
    lectores = [
        {"uid": "uid1", "email": "a@caapd.org", "display_name": "A", "disabled": False},
        {"uid": "uid2", "email": "b@caapd.org", "display_name": "B", "disabled": False},
    ]
    modelo = ModeloLectores(lectores)
    assert modelo.rowCount() == 2

    # Actualizar fila única
    row = modelo.actualizar_lector_en_fila("uid1", {"disabled": True, "display_name": "A Modificado"})
    assert row == 0
    assert modelo.data(modelo.index(0, 2)) == "Deshabilitado"
    assert modelo.data(modelo.index(0, 1)) == "A Modificado"

    # Eliminar fila única
    ok = modelo.eliminar_lector_por_uid("uid2")
    assert ok is True
    assert modelo.rowCount() == 1
    assert modelo.data(modelo.index(0, 0)) == "a@caapd.org"
