import rutas


def test_preparar_directorios_crea_carpetas_de_trabajo(tmp_path, monkeypatch):
    monkeypatch.setattr(rutas, "DIR_BASE", tmp_path)

    rutas.preparar_directorios()

    for nombre in ("Base de datos", "datos", "logs", "plantillas", "salida", "respaldos"):
        assert (tmp_path / nombre).is_dir()


def test_preparar_directorios_no_elimina_archivos_existentes(tmp_path, monkeypatch):
    monkeypatch.setattr(rutas, "DIR_BASE", tmp_path)
    base_datos = tmp_path / "Base de datos"
    base_datos.mkdir()
    padron = base_datos / "PADRON_MES_2026-10.xlsx"
    padron.write_bytes(b"padron existente")

    rutas.preparar_directorios()

    assert padron.read_bytes() == b"padron existente"
