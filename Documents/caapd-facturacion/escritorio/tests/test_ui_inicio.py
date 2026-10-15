"""
tests/test_ui_inicio.py — Pruebas de interfaz gráfica con pytest-qt (offscreen).

Verifica la apertura de la ventana principal, la navegación entre las 6 páginas,
la barra de estado y los diferentes estados del panel de Inicio.
"""
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton

from servicios.datos import ServicioDatosMemoria
from ui.ventana_principal import VentanaPrincipal


@pytest.fixture
def servicio_memoria():
    """Fixture con servicio de datos en memoria para pruebas rápidas y aisladas."""
    config = {
        "empresa": {"nombre": "CAAPD Ispacas"},
        "sectores": ["CENTRO", "ALTO"],
        "mes_actual": {
            "periodo": "2026-03",
            "fecha_emision": "01/03/2026",
            "fecha_vencimiento": "20/03/2026",
            "estado": "ABIERTO",
        },
    }
    usuarios = {
        "001": {"sector": "CENTRO", "activo": True},
        "002": {"sector": "ALTO", "activo": True},
    }
    mes = {
        "001": {
            "sector": "CENTRO",
            "medidores": [{"lectura_actual": 100}],
            "nro_recibo": "000000001",
            "total_a_pagar": 17.50,
            "monto_pagado": 17.50,
        },
        "002": {
            "sector": "ALTO",
            "medidores": [{"lectura_actual": None}],
            "nro_recibo": "000000002",
            "total_a_pagar": 25.00,
            "monto_pagado": 0.0,
        },
    }
    ops = {"lecturas": 12, "escrituras": 4}
    return ServicioDatosMemoria(config=config, usuarios=usuarios, mes=mes, ops=ops)


def test_ventana_principal_creacion_y_titulo(qtbot, servicio_memoria):
    ventana = VentanaPrincipal(servicio_memoria)
    qtbot.addWidget(ventana)

    assert "CAAPD Ispacas" in ventana.windowTitle()
    assert len(ventana.botones_nav) == 6
    assert ventana.stacked_widget.currentIndex() == 0  # Inicio
    assert ventana.botones_nav["inicio"].property("activo") == "true"


def test_navegacion_entre_las_paginas(qtbot, servicio_memoria):
    ventana = VentanaPrincipal(servicio_memoria)
    qtbot.addWidget(ventana)

    paginas = ["inicio", "usuarios", "lecturas", "lectores", "cobros", "configuracion"]
    for i, pagina in enumerate(paginas):
        ventana.navegar_a(pagina)
        assert ventana.stacked_widget.currentIndex() == i
        assert ventana.botones_nav[pagina].property("activo") == "true"
        # Verificar que los otros botones no estén activos
        for otra, btn in ventana.botones_nav.items():
            if otra != pagina:
                assert btn.property("activo") == "false"

    # Redirección de "recibos" a "cobros"
    ventana.navegar_a("recibos")
    assert ventana.stacked_widget.currentIndex() == paginas.index("cobros")
    assert ventana.botones_nav["cobros"].property("activo") == "true"


def test_barra_estado_muestra_contadores(qtbot, servicio_memoria):
    ventana = VentanaPrincipal(servicio_memoria)
    qtbot.addWidget(ventana)

    assert "12" in ventana.lbl_lecturas.text()
    assert "4" in ventana.lbl_escrituras.text()
    assert not hasattr(ventana, "lbl_ultimo_respaldo")
    textos = [boton.text() for boton in ventana.findChildren(QPushButton)]
    assert any("Base de datos" in texto for texto in textos)
    assert not any(
        etiqueta in texto
        for texto in textos
        for etiqueta in ("Respaldo Excel", "Respaldar ahora", "Respaldos")
    )


def test_barra_estado_no_inicia_consultas_de_red(qtbot, servicio_memoria, monkeypatch):
    def consulta_remota_no_permitida():
        raise AssertionError("El inicio no debe consultar Google ni Firebase")

    monkeypatch.setattr(
        "servicios.metricas_monitoring.consultar_metricas_hoy",
        consulta_remota_no_permitida,
    )
    ventana = VentanaPrincipal(servicio_memoria)
    qtbot.addWidget(ventana)

    hilos_activos = ventana.pagina_inicio.thread_pool.activeThreadCount()
    ventana.actualizar_barra_estado()

    assert ventana.lbl_lecturas.text() == "Lecturas: 12"
    assert ventana.lbl_escrituras.text() == "Escrituras: 4"
    assert ventana.pagina_inicio.thread_pool.activeThreadCount() == hilos_activos


def test_inicio_sin_mes_muestra_alerta_y_boton(qtbot, monkeypatch):
    # Servicio sin mes_actual
    servicio = ServicioDatosMemoria(config={"mes_actual": {}}, ops={"lecturas": 0, "escrituras": 0})
    ventana = VentanaPrincipal(servicio)
    qtbot.addWidget(ventana)

    inicio = ventana.pagina_inicio
    inicio.renderizar_datos({}, [], {"generados": 0, "pagados": 0, "pendientes": 0})

    # Verificar que exista el botón "Abrir mes nuevo"
    botones = inicio.findChildren(QPushButton)
    btn_abrir = next((b for b in botones if "Abrir mes nuevo" in b.text()), None)
    assert btn_abrir is not None

    # Al presionar el botón debe abrir el diálogo de nuevo mes
    llamadas = []
    monkeypatch.setattr(inicio, "abrir_dialogo_nuevo_mes", lambda: llamadas.append(True))
    btn_abrir.click()
    assert len(llamadas) == 1


def test_inicio_botones_segun_contexto_3b(qtbot, servicio_memoria):
    ventana = VentanaPrincipal(servicio_memoria)
    qtbot.addWidget(ventana)
    inicio = ventana.pagina_inicio

    # 1. Estado ABIERTO
    cfg_abierto = {
        "mes_actual": {"periodo": "2026-03", "estado": "ABIERTO"},
    }
    inicio.renderizar_datos(cfg_abierto, [], {"generados": 0, "pagados": 0, "pendientes": 0})
    textos_botones = [b.text() for b in inicio.findChildren(QPushButton)]
    assert any("Ir a Lecturas" in t for t in textos_botones)
    assert any("Cerrar lecturas" in t for t in textos_botones)

    # 2. Estado CERRADO
    cfg_cerrado = {
        "mes_actual": {"periodo": "2026-03", "estado": "CERRADO"},
    }
    inicio.renderizar_datos(cfg_cerrado, [], {"generados": 0, "pagados": 0, "pendientes": 0})
    textos_botones = [b.text() for b in inicio.findChildren(QPushButton)]
    assert any("Generar recibos" in t for t in textos_botones)
    assert any("Reabrir lecturas" in t for t in textos_botones)

    # 3. Estado FACTURADO
    cfg_facturado = {
        "mes_actual": {"periodo": "2026-03", "estado": "FACTURADO"},
    }
    inicio.renderizar_datos(cfg_facturado, [], {"generados": 0, "pagados": 0, "pendientes": 0})
    textos_botones = [b.text() for b in inicio.findChildren(QPushButton)]
    assert any("Ir a Cobros" in t for t in textos_botones)
    assert any("Abrir mes nuevo" in t for t in textos_botones)


def test_carga_asincrona_actualiza_tarjetas(qtbot, servicio_memoria):
    ventana = VentanaPrincipal(servicio_memoria)
    qtbot.addWidget(ventana)
    inicio = ventana.pagina_inicio

    with qtbot.waitSignal(inicio.datos_cargados, timeout=3000):
        inicio.cargar_datos_asincrono()

    # Verificar valores en las tarjetas estadísticas
    assert inicio.card_generados.lbl_numero.text() == "2"
    assert inicio.card_pagados.lbl_numero.text() == "1"
    assert inicio.card_pendientes.lbl_numero.text() == "1"
