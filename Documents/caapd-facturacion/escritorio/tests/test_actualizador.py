import io
import zipfile
from unittest.mock import MagicMock

import pytest

from servicios import actualizador as a


def release(version, **extras):
    return dict(tag_name=version, assets=[dict(name="CAAPD.zip",
                browser_download_url="https://example.test/app.zip", size=123)],
                published_at="2025-01-01", **extras)


def respuesta(data):
    r = MagicMock()
    r.json.return_value = data
    r.links = {}
    return r


def test_listar_filtra_ordena_y_pagina(monkeypatch):
    r = respuesta([release("v1.0.2"), release("v9", draft=True),
                   release("v8", prerelease=True), dict(tag_name="v7", assets=[])])
    r.links = {"next": {"url": "pagina2"}}
    get = MagicMock(side_effect=[r, respuesta([release("v1.0.10")])])
    monkeypatch.setattr(a.requests, "get", get)
    infos = a.listar_versiones()
    assert [i.version for i in infos] == ["1.0.10", "1.0.2"]
    assert infos[0].tamano == 123
    assert get.call_count == 2


def test_seleccion_mayor_y_solo_anteriores(monkeypatch):
    monkeypatch.setattr(a, "VERSION", "1.0.5")
    monkeypatch.setattr(a.requests, "get", lambda *args, **kw:
                        respuesta([release("1.0.3"), release("1.0.9"), release("1.0.5")]))
    # buscar usa la VERSION de ejecución, no el valor por defecto de hay_version_mayor.
    assert a.buscar_actualizacion().version == "1.0.9"
    assert [i.version for i in a.versiones_anteriores()] == ["1.0.3"]
    assert a.version_para_reparar().version == "1.0.9"


def test_vacio_y_fallo_latest(monkeypatch):
    monkeypatch.setattr(a.requests, "get", lambda *args, **kw: respuesta([]))
    assert a.buscar_actualizacion() is None
    assert a.versiones_anteriores() == []
    with pytest.raises(RuntimeError):
        a.version_para_reparar()
    get = MagicMock(side_effect=[RuntimeError("sin red"), respuesta(release("v99.0.0"))])
    monkeypatch.setattr(a.requests, "get", get)
    assert a.buscar_actualizacion().version == "99.0.0"
    get.side_effect = RuntimeError("sin red")
    assert a.buscar_actualizacion() is None


def zip_bytes(faltante=False):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("CAAPD.exe", b"exe")
        if not faltante:
            z.writestr("_internal/ui/estilos/tema.qss", b"tema")
    return b.getvalue()


@pytest.mark.parametrize("contenido,error", [
    (zip_bytes(), False), (zip_bytes(True), True), (b"no zip", True),
])
def test_descarga_valida_y_borra_invalidos(monkeypatch, tmp_path, contenido, error):
    monkeypatch.setattr(a.tempfile, "tempdir", str(tmp_path))
    r = MagicMock()
    r.__enter__.return_value = r
    r.iter_content.return_value = [contenido]
    monkeypatch.setattr(a.requests, "get", lambda *args, **kw: r)
    info = a.InfoActualizacion("1", "url", "", "app.zip", len(contenido))
    if error:
        with pytest.raises(ValueError, match="ZIP inválida"):
            a.descargar_zip(info)
        assert list(tmp_path.iterdir()) == []
    else:
        assert a.descargar_zip(info).is_file()


def test_tamano_incorrecto(monkeypatch, tmp_path):
    monkeypatch.setattr(a.tempfile, "tempdir", str(tmp_path))
    r = MagicMock()
    r.__enter__.return_value = r
    r.iter_content.return_value = [zip_bytes()]
    monkeypatch.setattr(a.requests, "get", lambda *args, **kw: r)
    with pytest.raises(ValueError, match="Descarga incompleta"):
        a.descargar_zip(a.InfoActualizacion("1", "url", "", "app.zip", 1))
    assert list(tmp_path.iterdir()) == []


def test_bundle_ausente(monkeypatch):
    monkeypatch.setattr(a, "CA_BUNDLE", "no-existe.pem")
    assert a._verificacion() is True
