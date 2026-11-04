import pytest

from servicios.actualizador import InfoActualizacion
from ui.dialogo_versiones import DialogoVersiones, HiloVersiones


@pytest.fixture
def dialogo(qtbot, monkeypatch):
    monkeypatch.setattr(HiloVersiones, "start", lambda self: None)
    widget = DialogoVersiones()
    qtbot.addWidget(widget)
    return widget


def test_retorno_exige_confirmacion_exacta(dialogo):
    info = InfoActualizacion("1.0.12", "url", "Notas de la versión", "app.zip",
                             fecha="2025-01-01")
    dialogo._cargar([info])
    assert "1.0.12" in dialogo.lista.item(0).text()
    assert "2025-01-01" in dialogo.lista.item(0).text()
    assert "Notas de la versión" in dialogo.lista.item(0).text()
    for texto in ["", "volver", " VOLVER", "VOLVER "]:
        dialogo.confirmacion.setText(texto)
        assert not dialogo.instalar.isEnabled()
    dialogo.confirmacion.setText("VOLVER")
    assert dialogo.instalar.isEnabled()
    dialogo.instalar.click()
    assert dialogo.info == info


def test_sin_versiones(dialogo):
    dialogo._cargar([])
    dialogo.confirmacion.setText("VOLVER")
    assert not dialogo.instalar.isEnabled()
    assert "No hay versiones anteriores" in dialogo.estado.text()


def test_error_de_red(dialogo):
    dialogo._error("Sin conexión")
    assert "Sin conexión" in dialogo.estado.text()
    assert not dialogo.instalar.isEnabled()
