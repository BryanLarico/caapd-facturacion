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
from ui.paginas.usuarios_dialogos import (
    DialogoCorregirDni,
    DialogoUsuario,
    DialogoConfirmacionDniDuplicado,
    DialogoConfirmacionMedidorDuplicado,
    obtener_siguiente_dni_sugerido,
)
from ui.paginas.usuarios_modelo import ModeloUsuarios, ProxyUsuarios
from PySide6.QtWidgets import QMessageBox, QSizePolicy


@pytest.fixture(autouse=True)
def mock_message_boxes(monkeypatch):
    """Evita diálogos bloqueantes de QMessageBox y confirmaciones en pruebas."""
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(DialogoConfirmacionMedidorDuplicado, "exec", lambda self: setattr(self, "confirmado", True) or 1)



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


def test_modelo_usuarios_filas_columnas_y_datos(qapp, datos_usuarios_prueba):
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
    assert not modelo.data(idx_pend, Qt.ItemDataRole.DecorationRole).isNull()

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

    # 3. Llenar campos (Guardar permanece deshabilitado hasta completar lo obligatorio)
    assert not dialogo.btn_guardar.isEnabled()
    dialogo.campo_nombre.setText("FLORES MAMANI, PEDRO")
    dialogo.campo_direccion.setText("CALLE 05 DE AGOSTO S/N")
    assert not dialogo.btn_guardar.isEnabled()  # aun falta el medidor
    dialogo.campo_nuevo_medidor.setText("998877")
    dialogo._agregar_medidor()
    assert "001000" not in dialogo.medidores_lista
    assert "998877" in dialogo.medidores_lista
    assert dialogo.btn_guardar.isEnabled()

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


def test_nuevo_usuario_mes_abierto_guarda_excel_y_sube_un_doc_firebase(tmp_path):
    """Verifica que con mes ABIERTO se guarde en Excel y se suba un único doc a Firebase sin dinero."""
    from unittest.mock import MagicMock, patch
    from servicios.datos_padron import ServicioDatosPadron

    servicio = ServicioDatosPadron.__new__(ServicioDatosPadron)
    servicio.es_contingencia = False
    servicio.es_local_first = True
    servicio.ops = {"lecturas": 0, "escrituras": 0}
    servicio.base_dir = tmp_path
    servicio.periodo = "2026-09"
    servicio.config = {
        "mes_actual": {"periodo": "2026-09", "estado": "ABIERTO"},
        "sectores": ["CENTRO"],
    }
    servicio.usuarios = {}
    servicio.mes = {}
    servicio.guardar_en_respaldo_local = MagicMock()

    mock_doc = MagicMock()
    mock_col = MagicMock(return_value=mock_doc)
    mock_db = MagicMock()
    mock_db.collection.return_value.document.return_value = mock_doc

    with patch("firebase_client.db", return_value=mock_db):
        exito, err = servicio.guardar_usuario(
            "70889911",
            {
                "nro_conexion": "000999",
                "nombre": "MAMANI CHOQUE, RAUL",
                "sector": "CENTRO",
                "direccion": "AV PRINCIPAL 10",
                "codigo_categoria": "A",
                "medidores": ["554433"],
            },
        )

    assert exito is True
    assert err is None
    # 1. Guardado en Excel
    servicio.guardar_en_respaldo_local.assert_called_once()
    assert "70889911" in servicio.usuarios
    assert "70889911" in servicio.mes

    # 2. Subido a Firebase sin campos de dinero
    mock_db.collection.assert_called_with("mes_2026-09")
    mock_doc.set.assert_called_once()
    payload = mock_doc.set.call_args[0][0]
    assert payload["id_usuario"] == "70889911"
    assert "total_a_pagar" not in payload
    assert "monto_pagado" not in payload
    assert "deuda_anterior" not in payload


def test_nuevo_usuario_mes_cerrado_no_toca_firebase(tmp_path):
    """Verifica que con mes FACTURADO / CERRADO se guarde en Excel pero NO toque Firebase."""
    from unittest.mock import MagicMock, patch
    from servicios.datos_padron import ServicioDatosPadron

    servicio = ServicioDatosPadron.__new__(ServicioDatosPadron)
    servicio.es_contingencia = False
    servicio.es_local_first = True
    servicio.ops = {"lecturas": 0, "escrituras": 0}
    servicio.base_dir = tmp_path
    servicio.periodo = "2026-09"
    servicio.config = {
        "mes_actual": {"periodo": "2026-09", "estado": "FACTURADO"},
        "sectores": ["CENTRO"],
    }
    servicio.usuarios = {}
    servicio.mes = {}
    servicio.guardar_en_respaldo_local = MagicMock()

    with patch("firebase_client.db") as mock_fb:
        exito, err = servicio.guardar_usuario(
            "70889922",
            {
                "nro_conexion": "001000",
                "nombre": "QUISPE MAMANI, LUCIA",
                "sector": "CENTRO",
                "direccion": "CALLE SUR 45",
                "codigo_categoria": "B",
                "medidores": [],
            },
        )

    assert exito is True
    assert err is None
    servicio.guardar_en_respaldo_local.assert_called_once()
    assert "70889922" in servicio.usuarios
    # No debe interactuar con Firebase
    mock_fb.assert_not_called()


def test_guardar_usuario_falla_red_mantiene_excel_y_avisa(qtbot, tmp_path, monkeypatch):
    """Verifica que ante falla de red se guarde en Excel y se alerte al usuario sin perder datos."""
    from unittest.mock import MagicMock, patch
    from servicios.datos_padron import ServicioDatosPadron

    servicio = ServicioDatosPadron.__new__(ServicioDatosPadron)
    servicio.es_contingencia = False
    servicio.es_local_first = True
    servicio.ops = {"lecturas": 0, "escrituras": 0}
    servicio.base_dir = tmp_path
    servicio.periodo = "2026-09"
    servicio.config = {
        "mes_actual": {"periodo": "2026-09", "estado": "ABIERTO"},
        "sectores": ["CENTRO"],
        "categorias": {"A": {"nombre": "Doméstico"}},
    }
    servicio.usuarios = {}
    servicio.mes = {}
    servicio.guardar_en_respaldo_local = MagicMock()

    avisos = []
    monkeypatch.setattr(
        "ui.paginas.usuarios_dialogos.mostrar_dialogo_aviso",
        lambda parent, titulo, texto, detalle=None: avisos.append((titulo, texto)),
    )
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda parent, titulo, texto: avisos.append((titulo, texto)) or QMessageBox.StandardButton.Ok,
    )

    mock_doc = MagicMock()
    mock_doc.set.side_effect = ConnectionError("Falla de conexión a internet")
    mock_db = MagicMock()
    mock_db.collection.return_value.document.return_value = mock_doc

    dialogo = DialogoUsuario(servicio_datos=servicio, config=servicio.config)
    qtbot.addWidget(dialogo)

    dialogo.campo_id.setText("71234567")
    dialogo.campo_nombre.setText("GARCIA LOPEZ, ANA")
    dialogo.campo_direccion.setText("JR. LIMA 123")
    dialogo.campo_nuevo_medidor.setText("77665544")
    dialogo._agregar_medidor()

    with patch("firebase_client.db", return_value=mock_db):
        dialogo._guardar()

    # Excel local quedó guardado con éxito
    servicio.guardar_en_respaldo_local.assert_called_once()
    assert "71234567" in servicio.usuarios

    # Se alertó al usuario sobre la sincronización pendiente
    assert any("Aviso" in a[0] for a in avisos)
    assert any("Enviar mes" in a[1] for a in avisos)


def test_dialogo_editar_dni_sd_a_real_renombra_y_sincroniza(qtbot, tmp_path):
    """Verifica la corrección de DNI desde el diálogo de edición: renombra en Excel y sincroniza en Firebase."""
    from unittest.mock import MagicMock, patch
    from servicios.datos_padron import ServicioDatosPadron

    servicio = ServicioDatosPadron.__new__(ServicioDatosPadron)
    servicio.es_contingencia = False
    servicio.es_local_first = True
    servicio.ops = {"lecturas": 0, "escrituras": 0}
    servicio.base_dir = tmp_path
    servicio.periodo = "2026-09"
    servicio.config = {
        "mes_actual": {"periodo": "2026-09", "estado": "ABIERTO"},
        "sectores": ["CENTRO"],
        "categorias": {"A": {"nombre": "Doméstico"}},
    }
    servicio.usuarios = {
        "SD-001": {
            "_id": "SD-001",
            "id_usuario": "SD-001",
            "nro_conexion": "000010",
            "nombre": "USUARIO SIN DNI INICIAL",
            "sector": "CENTRO",
            "direccion": "CALLE REAL",
            "codigo_categoria": "A",
            "activo": True,
            "medidores": ["112233"],
        }
    }
    servicio.mes = {
        "SD-001": {
            "_id": "SD-001",
            "id_usuario": "SD-001",
            "nro_conexion": "000010",
            "nombre": "USUARIO SIN DNI INICIAL",
            "sector": "CENTRO",
            "direccion": "CALLE REAL",
            "codigo_categoria": "A",
            "medidores": [{"nro_medidor": "112233", "lectura_actual": None}],
        }
    }
    servicio.guardar_en_respaldo_local = MagicMock()

    mock_doc_viejo = MagicMock()
    mock_doc_nuevo = MagicMock()

    def doc_selector(doc_id):
        return mock_doc_viejo if doc_id == "SD-001" else mock_doc_nuevo

    mock_db = MagicMock()
    mock_db.collection.return_value.document.side_effect = doc_selector

    usuario_editar = dict(servicio.usuarios["SD-001"])
    dialogo = DialogoUsuario(servicio_datos=servicio, usuario=usuario_editar, config=servicio.config)
    qtbot.addWidget(dialogo)

    # Reemplazar SD-001 por DNI definitivo 30771072
    dialogo.campo_id.setText("30771072")
    dialogo.campo_nombre.setText("QUISPE CONDORI, JUAN")

    with patch("firebase_client.db", return_value=mock_db):
        dialogo._guardar()

    # Verificaciones:
    # 1. En padrón ya no existe SD-001 y existe 30771072
    assert "SD-001" not in servicio.usuarios
    assert "30771072" in servicio.usuarios
    assert servicio.usuarios["30771072"]["nombre"] == "QUISPE CONDORI, JUAN"

    # 2. En Firebase: se eliminó SD-001 y se guardó 30771072
    mock_doc_viejo.delete.assert_called()
    mock_doc_nuevo.set.assert_called()


def test_pagina_usuarios_btn_actualizar_excel(qtbot, datos_usuarios_prueba):
    servicio = ServicioDatosMemoria(usuarios=dict(datos_usuarios_prueba))
    pagina = PaginaUsuarios(servicio)
    qtbot.addWidget(pagina)

    assert hasattr(pagina, "btn_actualizar_excel")
    assert pagina.btn_actualizar_excel.text() == "Actualizar Excel"
    assert pagina.btn_actualizar_excel.property("activo") == "false"
    assert pagina.btn_actualizar_excel.property("class") == "filtro_btn_excel"

    # Clic en el botón
    pagina.btn_actualizar_excel.click()
    assert pagina.btn_actualizar_excel.property("activo") == "true"

    qtbot.waitUntil(lambda: pagina.btn_actualizar_excel.isEnabled() is True, timeout=2000)
    assert pagina.btn_actualizar_excel.text() == "Actualizar Excel"

    # Al cambiar de filtro, se desactiva
    pagina._seleccionar_filtro("activos")
    assert pagina.btn_actualizar_excel.property("activo") == "false"


def test_obtener_siguiente_dni_sugerido(datos_usuarios_prueba):
    servicio = ServicioDatosMemoria(usuarios=dict(datos_usuarios_prueba))

    # 30771072 existe en datos_usuarios_prueba -> siguiente sugerido es 30771072-1
    sug1 = obtener_siguiente_dni_sugerido(servicio, "30771072")
    assert sug1 == "30771072-1"

    # 30770349-1 ya existe en datos_usuarios_prueba -> siguiente sugerido es 30770349-2
    sug2 = obtener_siguiente_dni_sugerido(servicio, "30770349-1")
    assert sug2 == "30770349-2"


def test_dialogo_usuario_acepta_dni_con_sufijo(qtbot, datos_usuarios_prueba):
    """Una misma persona puede tener 2 conexiones: 30771072 y 30771072-1 (o -A)."""
    servicio = ServicioDatosMemoria(usuarios=dict(datos_usuarios_prueba))
    config = {"sectores": ["CENTRO"], "categorias": {"A": {"nombre": "Doméstico"}}}

    dialogo = DialogoUsuario(servicio_datos=servicio, config=config)
    qtbot.addWidget(dialogo)
    dialogo.campo_nombre.setText("QUISPE CONDORI, JUAN SEGUNDA CONEXION")
    dialogo.campo_direccion.setText("JR. LIMA 45")
    dialogo.campo_nuevo_medidor.setText("55443322")
    dialogo._agregar_medidor()

    # DNI repetido: se bloquea y se sugiere el sufijo libre
    dialogo.campo_id.setText("30771072")
    dialogo._marcar_tocado("dni")
    assert not dialogo.btn_guardar.isEnabled()
    assert "30771072-1" in dialogo.msg_id.text()

    # Con sufijo numerico o letra se acepta y se normaliza en mayusculas
    dialogo.campo_id.setText("30771072-1")
    assert dialogo.btn_guardar.isEnabled()
    assert dialogo._normalizar_id_ingresado("30771072-a") == "30771072-A"
    assert dialogo._normalizar_id_ingresado("7646978") == "07646978"
    assert dialogo._normalizar_id_ingresado("30771072-") is None
    assert dialogo._normalizar_id_ingresado("3077") is None

    dialogo._guardar()
    assert "30771072-1" in servicio.usuarios
    assert "55443322" in servicio.usuarios["30771072-1"]["medidores"]


def test_dialogo_usuario_validacion_en_vivo_dni_y_medidor(qtbot, datos_usuarios_prueba):
    servicio = ServicioDatosMemoria(usuarios=dict(datos_usuarios_prueba))
    config = {"sectores": ["CENTRO"], "categorias": {"A": {"nombre": "Doméstico"}}}

    dialogo = DialogoUsuario(servicio_datos=servicio, config=config)
    qtbot.addWidget(dialogo)
    dialogo.show()

    # 1. DNI repetido en vivo
    dialogo.campo_id.setText("30771072")
    assert not dialogo.lbl_error_dni.isHidden()
    assert "DNI registrado" in dialogo.lbl_error_dni.text()

    # DNI no repetido
    dialogo.campo_id.setText("99887766")
    assert dialogo.lbl_error_dni.isHidden()

    # 2. Medidor repetido en vivo (003386 ya pertenece a Maribel Alvarez)
    dialogo.campo_nuevo_medidor.setText("3386")
    assert not dialogo.lbl_error_medidor.isHidden()
    assert "Medidor registrado" in dialogo.lbl_error_medidor.text()

    # Medidor único
    dialogo.campo_nuevo_medidor.setText("778899")
    assert dialogo.lbl_error_medidor.isHidden()

    # Añadir medidor y verificar advertencia si se intenta agregar el mismo de nuevo
    dialogo._agregar_medidor()
    assert "778899" in dialogo.medidores_lista
    dialogo.campo_nuevo_medidor.setText("778899")
    assert not dialogo.lbl_error_medidor.isHidden()
    assert "Medidor ya agregado" in dialogo.lbl_error_medidor.text()


def test_dialogo_confirmacion_dni_duplicado_botones_y_acciones(qtbot, datos_usuarios_prueba):
    servicio = ServicioDatosMemoria(usuarios=dict(datos_usuarios_prueba))
    usr_existente = servicio.obtener_usuario("30771072")

    dlg = DialogoConfirmacionDniDuplicado(
        dni="30771072",
        dni_sugerido="30771072-1",
        usuario_existente=usr_existente,
    )
    qtbot.addWidget(dlg)

    # Verificar que los 3 botones existan y tengan política de expansión igual
    assert dlg.btn_aceptar.text() == "Aceptar"
    assert dlg.btn_cancelar.text() == "Cancelar"
    assert dlg.btn_sugerido.text() == "Guardar 30771072-1"

    assert dlg.btn_aceptar.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding
    assert dlg.btn_cancelar.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding
    assert dlg.btn_sugerido.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding

    # Clic en Sugerido
    dlg.btn_sugerido.click()
    assert dlg.accion_elegida == DialogoConfirmacionDniDuplicado.ACCION_SUGERIDO


def test_dialogo_usuario_guardar_con_sugerido(qtbot, datos_usuarios_prueba, monkeypatch):
    servicio = ServicioDatosMemoria(usuarios=dict(datos_usuarios_prueba))
    config = {"sectores": ["CENTRO"], "categorias": {"A": {"nombre": "Doméstico"}}}

    # Mockear el diálogo para simular que el usuario hace clic en "Guardar 30771072-1"
    monkeypatch.setattr(
        DialogoConfirmacionDniDuplicado,
        "exec",
        lambda self: setattr(self, "accion_elegida", DialogoConfirmacionDniDuplicado.ACCION_SUGERIDO) or 1,
    )

    dialogo = DialogoUsuario(servicio_datos=servicio, config=config)
    qtbot.addWidget(dialogo)

    dialogo.campo_id.setText("30771072")
    dialogo.campo_nombre.setText("QUISPE SEGUNDA CONEXION")
    dialogo.campo_direccion.setText("JR. LIMA 45")
    dialogo.campo_nuevo_medidor.setText("55443322")
    dialogo._agregar_medidor()
    dialogo._guardar()

    # Debe haberse guardado con el DNI sugerido con sufijo -1
    assert "30771072-1" in servicio.usuarios
    assert servicio.usuarios["30771072-1"]["nombre"] == "QUISPE SEGUNDA CONEXION"
    # El titular original 30771072 debe permanecer intacto
    assert servicio.usuarios["30771072"]["nombre"] == "QUISPE CONDORI, JUAN"


def test_dialogo_usuario_guardar_cancelar_mantiene_edicion(qtbot, datos_usuarios_prueba, monkeypatch):
    servicio = ServicioDatosMemoria(usuarios=dict(datos_usuarios_prueba))
    config = {"sectores": ["CENTRO"], "categorias": {"A": {"nombre": "Doméstico"}}}

    # Mockear el diálogo para simular que el usuario hace clic en "Cancelar" (volver a editar)
    monkeypatch.setattr(
        DialogoConfirmacionDniDuplicado,
        "exec",
        lambda self: setattr(self, "accion_elegida", DialogoConfirmacionDniDuplicado.ACCION_CANCELAR) or 0,
    )

    dialogo = DialogoUsuario(servicio_datos=servicio, config=config)
    qtbot.addWidget(dialogo)

    dialogo.campo_id.setText("30771072")
    dialogo.campo_nombre.setText("INTENTO FALLIDO")
    dialogo.campo_direccion.setText("JR. LIMA 45")
    dialogo.campo_nuevo_medidor.setText("55443322")
    dialogo._agregar_medidor()
    dialogo._guardar()

    # No debe haberse guardado nada nuevo
    assert "30771072-1" not in servicio.usuarios
    assert servicio.usuarios["30771072"]["nombre"] == "QUISPE CONDORI, JUAN"

