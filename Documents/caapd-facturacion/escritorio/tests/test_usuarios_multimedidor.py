import copy
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import Qt

from respaldo_excel import generar_respaldo_excel, leer_respaldo_excel
from servicios.datos import ServicioDatosMemoria
from servicios.datos_padron import ServicioDatosPadron
from ui.paginas.usuarios_dialogos import DialogoMotivoCambioMedidor, DialogoUsuario


@pytest.fixture
def servicio():
    usuario = {
        "id_usuario": "12345678", "nombre": "PEREZ RAMOS, ANA",
        "nro_conexion": "000001", "sector": "CENTRO", "direccion": "CALLE UNO",
        "codigo_categoria": "A", "activo": True, "medidores": ["111111", "222222"],
    }
    medidores = [{
        "nro_medidor": numero, "lectura_anterior": 100 * i,
        "lectura_actual": 100 * i + 20, "fecha_anterior": "2026-08-25",
        "fecha_lectura": "2026-09-25", "novedad": "NORMAL", "nota": "Conservar",
        "registrado_por": "lector@local", "estado_lectura": "LEIDO",
        "consumo_anterior": 15, "consumo": 20,
    } for i, numero in enumerate(usuario["medidores"], 1)]
    return ServicioDatosMemoria(
        usuarios={"12345678": usuario},
        mes={"12345678": dict(usuario, medidores=medidores)})


def editar(qtbot, servicio):
    dlg = DialogoUsuario(servicio, servicio.config, servicio.usuarios["12345678"])
    qtbot.addWidget(dlg)
    return dlg


def test_editar_preserva_dos_medidores_y_metadatos(qtbot, servicio):
    antes = copy.deepcopy(servicio.mes["12345678"]["medidores"])
    dlg = editar(qtbot, servicio)
    assert len(dlg.filas_medidores) == 2
    assert all(f.campo_lectura_anterior.isReadOnly() for f in dlg.filas_medidores)
    dlg._guardar()
    assert servicio.usuarios["12345678"]["medidores"] == ["111111", "222222"]
    assert servicio.mes["12345678"]["medidores"] == antes
    assert servicio.mes["12345678"]["consumo_total_m3"] == 40


def test_agregar_enter_boton_limite_y_quitar(qtbot, servicio):
    dlg = editar(qtbot, servicio)
    dlg.show()
    for numero in ("333333", "444444", "555555"):
        dlg.campo_nuevo_medidor.setText(numero)
        if numero == "333333":
            qtbot.keyClick(dlg.campo_nuevo_medidor, Qt.Key.Key_Return)
        else:
            qtbot.mouseClick(dlg.btn_agregar_medidor, Qt.MouseButton.LeftButton)
    assert len(dlg.filas_medidores) == 5
    assert dlg.result() == 0
    assert dlg.filas_medidores[-1].campo_lectura_actual.text() == "0"
    dlg.campo_nuevo_medidor.setText("666666")
    dlg._agregar_medidor()
    assert len(dlg.filas_medidores) == 5
    assert "Máximo 5" in dlg.msg_medidores.text()
    dlg.campo_nuevo_medidor.clear()
    dlg.filas_medidores[-1].btn_quitar.click()
    assert len(dlg.filas_medidores) == 4


@pytest.mark.parametrize("valor", ["111111", "abc", ""])
def test_agregar_invalido_no_modifica_lista(qtbot, servicio, valor):
    dlg = editar(qtbot, servicio)
    dlg.campo_nuevo_medidor.setText(valor)
    dlg._agregar_medidor()
    assert len(dlg.filas_medidores) == 2
    assert not dlg.msg_medidores.isHidden()


def test_validacion_independiente_y_lista_vacia(qtbot, servicio):
    dlg = editar(qtbot, servicio)
    segunda = dlg.filas_medidores[1]
    segunda.campo_lectura_actual.setText("199")
    assert "lectura" in dlg._calcular_errores()
    assert not dlg.btn_guardar.isEnabled()
    segunda.campo_lectura_actual.setText("230")
    segunda.campo_medidor.setText("111111")
    assert "medidores" in dlg._calcular_errores()
    segunda.campo_medidor.setText("222222")
    segunda.campo_lectura_actual.setText("abc")
    assert "lectura" in dlg._calcular_errores()
    for fila in list(dlg.filas_medidores):
        dlg._quitar_medidor(fila)
    assert "medidores" in dlg._calcular_errores()
    assert not dlg.btn_guardar.isEnabled()


@pytest.mark.parametrize("motivo", ["CORRECCION", "REINSTALACION", None])
def test_cambio_solo_afecta_fila_elegida(qtbot, servicio, monkeypatch, motivo):
    antes = copy.deepcopy(servicio.mes["12345678"]["medidores"])
    monkeypatch.setattr(DialogoMotivoCambioMedidor, "exec",
                        lambda self: setattr(self, "motivo_elegido", motivo) or (1 if motivo else 0))
    dlg = editar(qtbot, servicio)
    segunda = dlg.filas_medidores[1]
    segunda.campo_medidor.setText("333333")
    assert segunda.confirmar_cambio() == bool(motivo)
    dlg._guardar()
    actuales = servicio.mes["12345678"]["medidores"]
    assert actuales[0] == antes[0]
    if motivo == "CORRECCION":
        assert actuales[1] == dict(antes[1], nro_medidor="333333")
    elif motivo == "REINSTALACION":
        assert actuales[1]["nro_medidor"] == "333333"
        assert actuales[1]["lectura_anterior"] == actuales[1]["lectura_actual"] == 0
        assert actuales[1]["novedad"] == "CAMBIO_MEDIDOR"
        assert actuales[1]["fecha_anterior"] is None
    else:
        assert actuales == antes


def test_nuevo_tres_lecturas_y_cobro_unico(qtbot):
    servicio = ServicioDatosMemoria()
    dlg = DialogoUsuario(servicio, servicio.config)
    qtbot.addWidget(dlg)
    dlg.campo_id.setText("87654321")
    dlg.campo_nombre.setText("RAMOS PEREZ, JOSE")
    dlg.campo_direccion.setText("CALLE DOS")
    for numero in ("111111", "222222", "333333"):
        dlg.campo_nuevo_medidor.setText(numero)
        dlg._agregar_medidor()
    for i, fila in enumerate(dlg.filas_medidores, 1):
        fila.campo_lectura_actual.setText(str(i * 10))
    dlg._guardar()
    doc = servicio.mes["87654321"]
    assert len(doc["medidores"]) == 3
    assert doc["consumo_total_m3"] == 60


def test_excel_y_payload_firebase_preservan_lista(tmp_path, servicio):
    s = ServicioDatosPadron.__new__(ServicioDatosPadron)
    s.usuarios = copy.deepcopy(servicio.usuarios)
    s.mes = copy.deepcopy(servicio.mes)
    s.config = dict(servicio.config, mes_actual={"estado": "ABIERTO", "periodo": "2026-09"})
    s.periodo = "2026-09"
    s.es_contingencia = False
    s.ops = {"lecturas": 0, "escrituras": 0}
    s.guardar_en_respaldo_local = MagicMock()
    s.generar_recibo_usuario = MagicMock()
    medidores = copy.deepcopy(s.mes["12345678"]["medidores"])
    medidores[1]["nro_medidor"] = "333333"
    with patch("firebase_client.db") as db:
        s.actualizar_usuario("12345678", {"medidores": medidores})
    payload = db.return_value.collection.return_value.document.return_value.set.call_args.args[0]
    assert [m["nro_medidor"] for m in payload["medidores"]] == ["111111", "333333"]
    for recibido, original in zip(payload["medidores"], medidores):
        for campo in ("lectura_anterior", "lectura_actual", "fecha_anterior",
                      "fecha_lectura", "novedad", "nota", "registrado_por", "consumo_anterior"):
            assert recibido[campo] == original[campo]
    archivo = generar_respaldo_excel(config=s.config, usuarios=s.usuarios,
                                    mes_docs=s.mes, periodo=s.periodo,
                                    ruta_archivo=tmp_path / "padron.xlsx")
    leido = leer_respaldo_excel(archivo)
    assert leido["usuarios"]["12345678"]["medidores"] == ["111111", "333333"]
    for recibido, original in zip(leido["mes_docs"]["12345678"]["medidores"], medidores):
        for campo in ("nro_medidor", "lectura_anterior", "lectura_actual",
                      "fecha_anterior", "fecha_lectura", "novedad", "nota", "registrado_por"):
            assert recibido[campo] == original[campo]
