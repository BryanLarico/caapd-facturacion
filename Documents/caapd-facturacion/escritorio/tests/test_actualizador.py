import io
import zipfile
from unittest.mock import MagicMock

import pytest

from servicios import actualizador as a


@pytest.fixture(autouse=True)
def cache_vacia(monkeypatch):
    monkeypatch.setattr(a, "_cache_versiones", None)
    monkeypatch.setattr(a, "_cache_hasta", 0.0)


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
    monkeypatch.setattr(a, "_cache_versiones", None)
    get = MagicMock(side_effect=[RuntimeError("sin red"), RuntimeError("sin Atom"),
                                respuesta(release("v99.0.0"))])
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


ATOM = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry><link href="https://github.com/owner/repo/releases/tag/v1.0.12"/>
    <updated>2025-11-01T12:00:00Z</updated>
    <content type="html">&lt;p&gt;Correcciones &amp;amp; mejoras&lt;/p&gt;</content></entry>
  <entry><link href="https://github.com/owner/repo/releases/tag/v1.0.14"/>
    <published>2025-11-03T12:00:00Z</published></entry>
  <entry><link href="https://github.com/owner/repo/releases/tag/v2.0.0-beta"/></entry>
</feed>"""


@pytest.mark.parametrize("fallo", [a.requests.HTTPError("403"), a.requests.HTTPError("429"),
                                 a.requests.ConnectionError("sin red"), ValueError("JSON")])
def test_atom_fallback_y_cache(monkeypatch, fallo):
    atom = respuesta(None)
    atom.content = ATOM
    get = MagicMock(side_effect=[fallo, atom])
    monkeypatch.setattr(a.requests, "get", get)
    infos = a.listar_versiones()
    assert [i.version for i in infos] == ["1.0.14", "1.0.12"]
    assert infos[1].fecha == "2025-11-01T12:00:00Z"
    assert infos[1].notas == "Correcciones & mejoras"
    assert infos[0].tamano == 0
    assert infos[0].url_zip.endswith("/releases/download/v1.0.14/CAAPD-1.0.14.zip")
    infos.clear()
    assert len(a.listar_versiones()) == 2
    assert get.call_count == 2
    assert get.call_args.args[0] == a.URL_ATOM


def test_cache_api_expira_y_cachea_lista_vacia(monkeypatch):
    reloj = [100.0]
    monkeypatch.setattr(a.time, "monotonic", lambda: reloj[0])
    get = MagicMock(return_value=respuesta([]))
    monkeypatch.setattr(a.requests, "get", get)
    assert a.listar_versiones() == []
    reloj[0] += 599
    assert a.listar_versiones() == []
    assert get.call_count == 1
    reloj[0] += 2
    assert a.listar_versiones() == []
    assert get.call_count == 2


@pytest.mark.parametrize("contenido,esperado", [(b"<feed/>", ValueError),
    (b"no xml", a.ElementTree.ParseError),
    (b'<feed xmlns="http://www.w3.org/2005/Atom"/>', None)])
def test_atom_vacio_o_invalido(monkeypatch, contenido, esperado):
    r = respuesta(None)
    r.content = contenido
    monkeypatch.setattr(a.requests, "get", MagicMock(side_effect=[RuntimeError("API"), r]))
    if esperado:
        with pytest.raises(esperado):
            a.listar_versiones()
        assert a._cache_versiones is None
    else:
        assert a.listar_versiones() == []


def test_descarga_sin_tamano_valida_zip(monkeypatch, tmp_path):
    monkeypatch.setattr(a.tempfile, "tempdir", str(tmp_path))
    r = MagicMock()
    r.__enter__.return_value = r
    r.headers = {"Content-Length": "999999"}
    r.iter_content.return_value = [zip_bytes()]
    monkeypatch.setattr(a.requests, "get", lambda *args, **kw: r)
    assert a.descargar_zip(a.InfoActualizacion("1", "url", "", "app.zip")).is_file()
