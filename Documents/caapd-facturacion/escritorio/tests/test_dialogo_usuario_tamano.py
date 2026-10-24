"""El diálogo Nuevo/Editar Usuario se dimensiona según la pantalla, no recorta su contenido y queda centrado."""
from PySide6.QtWidgets import QWidget

from servicios.datos import ServicioDatosMemoria
from ui.paginas.usuarios_dialogos import DialogoUsuario


def _config():
    return {"sectores": ["BARRIO DE CHAUPI", "BARRIO DE PACHAYZA", "AYACUCHO"],
            "categorias": {"A": {"nombre": "Doméstico / General"}, "B": {"nombre": "Comercial"}},
            "mes_actual": {"estado": "ABIERTO", "periodo": "2026-03"}}


def test_dialogo_usuario_tamano_proporcional_sin_recorte_y_centrado(qtbot):
    padre = QWidget()
    area0 = padre.screen().availableGeometry()
    padre.resize(min(1600, area0.width() - 60), min(900, area0.height() - 60))
    padre.move(area0.left() + 30, area0.top() + 30)
    qtbot.addWidget(padre)
    padre.show()
    qtbot.waitExposed(padre)

    d = DialogoUsuario(servicio_datos=ServicioDatosMemoria(), config=_config(), parent=padre)
    qtbot.addWidget(d)
    d.show()
    qtbot.waitExposed(d)
    qtbot.wait(50)

    area = padre.screen().availableGeometry()
    # Ya no es la franja fija de 560 px: crece con la pantalla
    assert d.width() >= 620
    assert d.width() <= area.width()
    assert d.height() >= 560

    # El contenido del formulario cabe completo: no se recorta por la derecha
    assert d._scroll_widget.width() <= d.width()
    assert d._scroll_widget.minimumSizeHint().width() <= d.width()

    # Centrado respecto a la ventana principal
    c_d = d.frameGeometry().center()
    c_p = padre.frameGeometry().center()
    assert abs(c_d.x() - c_p.x()) <= 40
    assert abs(c_d.y() - c_p.y()) <= 40
