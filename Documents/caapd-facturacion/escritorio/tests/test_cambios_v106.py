import json, sys, os
sys.path.insert(0, os.getcwd())
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from pathlib import Path
import tempfile, shutil

def test_config_persiste_en_json_y_prevalece_sobre_excel():
    from servicios.datos_padron import ServicioDatosPadron
    from servicios.datos import ServicioDatosMemoria
    tmp = Path(tempfile.mkdtemp())
    # Arranque "limpio" (sin Base de datos) -> defaults
    s = ServicioDatosPadron(base_dir=tmp)
    cfg = s.cargar_config()
    cfg["categorias"]["A"]["cargo_fijo"] = 7.25
    cfg["categorias"]["A"]["nombre"] = "MI CATEGORIA"
    cfg["sectores"] = ["SECTOR PRUEBA"]
    s.guardar_config(cfg)
    assert (tmp / "config.json").exists(), "config.json no se creo"
    datos = json.loads((tmp / "config.json").read_text(encoding="utf-8"))
    assert datos["categorias"]["A"]["cargo_fijo"] == 7.25
    # Simular "actualizacion/reinicio": nueva instancia sobre la misma carpeta
    s2 = ServicioDatosPadron(base_dir=tmp)
    c2 = s2.cargar_config()
    assert c2["categorias"]["A"]["cargo_fijo"] == 7.25
    assert c2["categorias"]["A"]["nombre"] == "MI CATEGORIA"
    assert c2["sectores"] == ["SECTOR PRUEBA"]
    # Simular Excel regenerado SIN la config del usuario: borrar hoja CONFIG del xlsx
    import openpyxl
    for x in tmp.glob("PADRON_MES_*.xlsx"):
        wb = openpyxl.load_workbook(x)
        if "CONFIG" in wb.sheetnames:
            del wb["CONFIG"]
        wb.save(x)
    s3 = ServicioDatosPadron(base_dir=tmp)
    c3 = s3.cargar_config()
    assert c3["categorias"]["A"]["cargo_fijo"] == 7.25, "config.json debia prevalecer"
    shutil.rmtree(tmp, ignore_errors=True)

def test_pantalla_configuracion_layout(qtbot):
    from PySide6.QtCore import Qt
    from servicios.datos import ServicioDatosMemoria
    from ui.paginas.configuracion import PaginaConfiguracion
    serv = ServicioDatosMemoria()
    pag = PaginaConfiguracion(serv)
    qtbot.addWidget(pag)
    pag.resize(1400, 900); pag.show(); qtbot.waitExposed(pag)
    pag.cargar_datos_asincrono()
    qtbot.waitUntil(lambda: pag.config_cargada, timeout=5000)
    qtbot.wait(200)
    # Botones del mismo tamano
    assert pag.btn_guardar.size() == pag.btn_recargar.size(), (pag.btn_guardar.size(), pag.btn_recargar.size())
    # Texto del spinbox con margen izquierdo (desplazado a la derecha)
    assert pag.spin_cat_cargo_fijo.lineEdit().textMargins().left() == 12
    # Etiqueta centrada verticalmente respecto a su caja
    f = pag.grp_cat.layout()
    from PySide6.QtWidgets import QFormLayout
    lbl = f.itemAt(1, QFormLayout.ItemRole.LabelRole).widget()
    campo = f.itemAt(1, QFormLayout.ItemRole.FieldRole).widget()
    cl, cc = lbl.geometry().center().y(), campo.geometry().center().y()
    assert abs(cl - cc) <= 2, f"label center {cl} vs field center {cc}"
    pag.grab().save("/tmp/config_v106.png")

def test_lectores_uid_oculto(qtbot):
    from servicios.datos import ServicioDatosMemoria
    from ui.paginas.lectores import PaginaLectores
    pag = PaginaLectores(ServicioDatosMemoria())
    qtbot.addWidget(pag)
    assert pag.tabla.isColumnHidden(4)
    assert pag.tabla.model().columnCount() == 5
