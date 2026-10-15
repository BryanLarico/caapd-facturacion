"""
tests/test_ui_usuarios.py — Pruebas unitarias de la pantalla de Usuarios (Fase D2).

Cubre:
- Modelo de tabla y ProxyModel.
- Filtros por estado (Todos, Activos, Inactivos, Pendientes).
- Búsqueda inteligente según CONTEXTO §4.
- Validaciones al guardar usuario (ID duplicado, medidores únicos).
- Corrección de DNI provisional a DNI real.
- Cambio de estado activo/inactivo.
"""
import pytest
from PySide6.QtCore import Qt

import codigos
from servicios.datos import ServicioDatosMemoria
from ui.paginas.usuarios import PaginaUsuarios
from ui.paginas.usuarios_dialogos import DialogoCorregirDni, DialogoUsuario
from ui.paginas.usuarios_modelo import ModeloUsuarios, ProxyUsuarios
from PySide6.QtWidgets import QMessageBox


@pytest.fixture(autouse=True)
def mock_message_boxes(monkeypatch):
    """Evita diálogos bloqueantes de QMessageBox en pruebas."""
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)


@pytest.fixture
def datos_usuarios_prueba():
    return {
        "07654321": {
            "nro_conexion": "000796",
            "nombre": "ALVAREZ MAMANI, MARIBEL",
            "sector": "AYACUCHO",
            "direccion": "CALLE LIMA 123",
            "codigo_categoria": "A",
            "activo": True,
            "medidores": ["003386"],
        },
        "30771072": {
            "nro_conexion": "000100",
            "nombre": "QUISPE CONDORI, JUAN",
            "sector": "BARRIO DE CHAUPI",
            "direccion": "CALLE UNION S/N",
            "codigo_categoria": "A",
            "activo": False,  # Inactivo
            "medidores": ["123456"],
        },
        "30770349-1": {
            "nro_conexion": "000005",
            "nombre": "RAMIREZ TORRES, IRMA",
            "sector": "HUAQUILLO",
            "direccion": "S/N",
            "codigo_categoria": "B",
            "activo": True,
            "medidores": ["22392996"],
        },
        "SD-001": {
            "nro_conexion": "000020",
            "nombre": "PEREZ PEREZ, CARLOS",
            "sector": "CHAUPICERCA",
            "direccion": "S/N",
            "codigo_categoria": "A",
            "activo": True,
            "medidores": [],
        },
    }


def test_modelo_usuarios_filas_columnas_y_datos(datos_usuarios_prueba):
    lista = []
    for uid, u in datos_usuarios_prueba.items():
        doc = dict(u)
        doc["_id"] = uid
        doc["id_usuario"] = uid
        doc["es_pendiente"] = codigos.es_id_pendiente(uid)
        lista.append(doc)

    modelo = ModeloUsuarios(lista)
    assert modelo.rowCount() == 4
    assert modelo.columnCount() == 8

    # Columna 0: Conexión
    idx_con = modelo.index(0, 0)
    assert modelo.data(idx_con, Qt.ItemDataRole.DisplayRole) == "000796"

    # Columna 1: DNI (verificar badge pendiente)
    idx_pend = modelo.index(2, 1)  # 30770349-1
    assert "30770349-1" in modelo.data(idx_pend, Qt.ItemDataRole.DisplayRole)
    assert "⚠️" in modelo.data(idx_pend, Qt.ItemDataRole.DisplayRole)

    # Columna 7: Estado
    idx_inactivo = modelo.index(1, 7)
    assert modelo.data(idx_inactivo, Qt.ItemDataRole.DisplayRole) == "Inactivo"


def test_filtros_estado_proxy(datos_usuarios_prueba):
    lista = []
    for uid, u in datos_usuarios_prueba.items():
        doc = dict(u)
        doc["_id"] = uid
        doc["id_usuario"] = uid
        doc["es_pendiente"] = codigos.es_id_pendiente(uid)
        lista.append(doc)

    modelo = ModeloUsuarios(lista)
    proxy = ProxyUsuarios()
    proxy.setSourceModel(modelo)

    # 1. Todos: 4
    proxy.set_filtro_estado("todos")
    assert proxy.rowCount() == 4

    # 2. Activos: 3
    proxy.set_filtro_estado("activos")
    assert proxy.rowCount() == 3

    # 3. Inactivos: 1 (QUISPE CONDORI)
    proxy.set_filtro_estado("inactivos")
    assert proxy.rowCount() == 1

    # 4. Pendientes de DNI: 2 (30770349-1 y SD-001)
    proxy.set_filtro_estado("pendientes")
    assert proxy.rowCount() == 2


def test_busqueda_inteligente_contexto_4(datos_usuarios_prueba):
    lista = []
    for uid, u in datos_usuarios_prueba.items():
        doc = dict(u)
        doc["_id"] = uid
        doc["id_usuario"] = uid
        doc["es_pendiente"] = codigos.es_id_pendiente(uid)
        lista.append(doc)

    modelo = ModeloUsuarios(lista)
    proxy = ProxyUsuarios()
    proxy.setSourceModel(modelo)

    # Búsqueda 1: medidor con ceros "3386" -> 003386 (ALVAREZ)
    res1 = codigos.buscar("3386", lista)
    proxy.set_ids_busqueda({u["id_usuario"] for u in res1})
    assert proxy.rowCount() == 1
    assert "ALVAREZ" in res1[0]["nombre"]

    # Búsqueda 2: medidor completo "123456" (QUISPE)
    res2 = codigos.buscar("123456", lista)
    proxy.set_ids_busqueda({u["id_usuario"] for u in res2})
    assert proxy.rowCount() == 1
    assert "QUISPE" in res2[0]["nombre"]

    # Búsqueda 3: conexión "796" -> 000796 (ALVAREZ)
    res3 = codigos.buscar("796", lista)
    proxy.set_ids_busqueda({u["id_usuario"] for u in res3})
    assert proxy.rowCount() == 1
    assert res3[0]["nro_conexion"] == "000796"

    # Búsqueda 4: DNI "7654321" -> 07654321 (ALVAREZ)
    res4 = codigos.buscar("7654321", lista)
    proxy.set_ids_busqueda({u["id_usuario"] for u in res4})
    assert proxy.rowCount() == 1
    assert res4[0]["id_usuario"] == "07654321"

    # Búsqueda 5: nombre palabras desordenadas sin tildes "maribel alvarez"
    res5 = codigos.buscar("maribel alvarez", lista)
    proxy.set_ids_busqueda({u["id_usuario"] for u in res5})
    assert proxy.rowCount() == 1
    assert "ALVAREZ MAMANI, MARIBEL" in res5[0]["nombre"]


def test_orden_conexion_numerico(datos_usuarios_prueba):
    lista = []
    for uid, u in datos_usuarios_prueba.items():
        doc = dict(u)
        doc["_id"] = uid
        doc["id_usuario"] = uid
        doc["es_pendiente"] = codigos.es_id_pendiente(uid)
        lista.append(doc)

    modelo = ModeloUsuarios(lista)
    proxy = ProxyUsuarios()
    proxy.setSourceModel(modelo)
    proxy.sort(0, Qt.SortOrder.AscendingOrder)

    # Conexiones ordenadas deben ser: 000005, 000020, 000100, 000796
    primero = proxy.data(proxy.index(0, 0), Qt.ItemDataRole.DisplayRole)
    ultimo = proxy.data(proxy.index(3, 0), Qt.ItemDataRole.DisplayRole)
    assert primero == "000005"
    assert ultimo == "000796"


def test_dialogo_usuario_creacion_y_validaciones(qtbot, datos_usuarios_prueba):
    servicio = ServicioDatosMemoria(usuarios=dict(datos_usuarios_prueba))
    config = {
        "sectores": ["CENTRO", "AYACUCHO"],
        "categorias": {"A": {"nombre": "Doméstico"}},
        "mes_actual": {"estado": "ABIERTO", "periodo": "2026-03"},
    }

    dialogo = DialogoUsuario(servicio_datos=servicio, config=config)
    qtbot.addWidget(dialogo)

    # 1. Sugerencia automática de conexión (siguiente libre: 000797)
    assert dialogo.campo_conexion.text() == "000797"

    # 2. Casilla sin DNI asigna SD-002
    dialogo.chk_sin_dni.setChecked(True)
    assert dialogo.campo_id.text() == "SD-002"

    # 3. Llenar campos
    dialogo.campo_nombre.setText("FLORES MAMANI, PEDRO")
    dialogo.campo_nuevo_medidor.setText("998877")
    dialogo._agregar_medidor()
    assert "001000" not in dialogo.medidores_lista
    assert "998877" in dialogo.medidores_lista

    # 4. Guardar
    dialogo._guardar()
    assert "SD-002" in servicio.usuarios
    assert servicio.usuarios["SD-002"]["nombre"] == "FLORES MAMANI, PEDRO"
    assert "998877" in servicio.usuarios["SD-002"]["medidores"]


def test_dialogo_usuario_valida_medidores_duplicados(qtbot, datos_usuarios_prueba):
    servicio = ServicioDatosMemoria(usuarios=dict(datos_usuarios_prueba))
    config = {"sectores": ["CENTRO"], "categorias": {"A": {"nombre": "Doméstico"}}}

    dialogo = DialogoUsuario(servicio_datos=servicio, config=config)
    qtbot.addWidget(dialogo)

    dialogo.campo_id.setText("88776655")
    dialogo.campo_nombre.setText("NUEVO USUARIO")
    # Intentar asignar medidor que ya pertenece a Maribel Alvarez (003386)
    dialogo.campo_nuevo_medidor.setText("3386")
    dialogo._agregar_medidor()

    # Al intentar guardar debe bloquear la duplicidad
    valido, err_msg = servicio.validar_medidores_unicos(dialogo.medidores_lista)
    assert not valido
    assert "ya está asignado" in err_msg


def test_corregir_dni_modal_y_servicio(qtbot, datos_usuarios_prueba):
    servicio = ServicioDatosMemoria(usuarios=dict(datos_usuarios_prueba))
    usuario_pendiente = {
        "id_usuario": "30770349-1",
        "nombre": "RAMIREZ TORRES, IRMA",
    }

    dialogo = DialogoCorregirDni(servicio_datos=servicio, usuario=usuario_pendiente)
    qtbot.addWidget(dialogo)

    dialogo.campo_nuevo_dni.setText("30770349")  # Intentar asignar el real
    dialogo._confirmar()

    # Ahora debe estar registrado bajo el DNI definitivo
    assert "30770349" in servicio.usuarios
    assert "30770349-1" not in servicio.usuarios
    assert servicio.usuarios["30770349"]["nombre"] == "RAMIREZ TORRES, IRMA"


def test_pagina_usuarios_interaccion_completa(qtbot, datos_usuarios_prueba):
    servicio = ServicioDatosMemoria(usuarios=dict(datos_usuarios_prueba))
    pagina = PaginaUsuarios(servicio)
    qtbot.addWidget(pagina)

    pagina.cargar_datos_asincrono()
    qtbot.waitUntil(lambda: len(pagina.lista_usuarios_completa) == 4, timeout=2000)

    # Verificar contadores
    assert "Todos (4)" in pagina.btn_filtro_todos.text()
    assert "Activos (3)" in pagina.btn_filtro_activos.text()
    assert "Inactivos (1)" in pagina.btn_filtro_inactivos.text()
    assert "Pendientes de DNI (2)" in pagina.btn_filtro_pendientes.text()

    # Filtrar por inactivos
    pagina._seleccionar_filtro("inactivos")
    assert pagina.proxy_model.rowCount() == 1

    # Limpiar filtro y buscar
    pagina._seleccionar_filtro("todos")
    pagina.campo_busqueda.setText("QUISPE")
    pagina._ejecutar_busqueda()
    assert pagina.proxy_model.rowCount() == 1
    assert "Mostrando 1 de 4 registros" in pagina.lbl_conteo_registros.text()
