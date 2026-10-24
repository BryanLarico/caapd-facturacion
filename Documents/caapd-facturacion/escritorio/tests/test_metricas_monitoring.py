"""Cloud Monitoring: agregación, paginación y mensajes de error reales (sin red: requests simulado)."""
import json
import types

import pytest

from servicios import metricas_monitoring as mm


class _Resp:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


def _preparar(monkeypatch, tmp_path, respuestas):
    """respuestas: función(metric_type, pageToken) -> _Resp"""
    clave = tmp_path / "serviceAccountKey.json"
    clave.write_text(json.dumps({"project_id": "caapd-ispacas-optimizado"}), encoding="utf-8")
    monkeypatch.setattr(mm, "_buscar_archivo_credenciales", lambda ruta_personalizada=None: clave)
    monkeypatch.setattr(mm, "_log", lambda msg: None)
    mm._CACHE_METRICAS = {"timestamp": 0.0, "resultado": None}

    llamadas = []

    def fake_get(url, headers=None, params=None, timeout=None):
        llamadas.append(dict(params))
        return respuestas(params["filter"], params.get("pageToken"))

    fake_requests = types.SimpleNamespace(get=fake_get)

    class _Cred:
        token = "tok"
        def refresh(self, _req): pass

    import google.oauth2.service_account as sa
    import google.auth.transport.requests as gar
    monkeypatch.setattr(sa.Credentials, "from_service_account_file", classmethod(lambda cls, *a, **k: _Cred()))
    monkeypatch.setattr(gar, "Request", lambda: None)
    import sys
    monkeypatch.setitem(sys.modules, "requests", fake_requests)
    return llamadas


def test_suma_con_agregacion_y_paginacion(monkeypatch, tmp_path):
    def respuestas(filtro, token):
        if "read_count" in filtro:
            if token is None:
                return _Resp(200, {"timeSeries": [{"points": [{"value": {"int64Value": "3000"}}]}],
                                   "nextPageToken": "p2"})
            return _Resp(200, {"timeSeries": [{"points": [{"value": {"int64Value": "812"}}]}]})
        if "write_count" in filtro:
            return _Resp(200, {"timeSeries": [{"points": [{"value": {"int64Value": "45"}}]}]})
        return _Resp(200, {"timeSeries": [{"points": [{"value": {"int64Value": "802"}}]}]})

    llamadas = _preparar(monkeypatch, tmp_path, respuestas)
    res = mm.consultar_metricas_hoy(forzar=True)
    assert res["disponible"] is True
    assert res["lecturas"] == 3812          # 2 páginas sumadas
    assert res["escrituras"] == 45 + 802    # escrituras + eliminaciones
    assert res["eliminaciones"] == 802
    # Se pidió agregación del lado de Google
    assert llamadas[0]["aggregation.perSeriesAligner"] == "ALIGN_SUM"
    assert llamadas[0]["aggregation.crossSeriesReducer"] == "REDUCE_SUM"
    assert any(l.get("pageToken") == "p2" for l in llamadas)


def test_api_no_habilitada_se_explica(monkeypatch, tmp_path):
    msg = "Cloud Monitoring API has not been used in project 123 before or it is disabled."
    _preparar(monkeypatch, tmp_path, lambda f, t: _Resp(403, {"error": {"message": msg}}))
    res = mm.consultar_metricas_hoy(forzar=True)
    assert res["disponible"] is False
    assert "no está habilitada" in res["error"]


def test_sin_permiso_pide_rol(monkeypatch, tmp_path):
    msg = "Permission monitoring.timeSeries.list denied (or the resource may not exist)."
    _preparar(monkeypatch, tmp_path, lambda f, t: _Resp(403, {"error": {"message": msg}}))
    res = mm.consultar_metricas_hoy(forzar=True)
    assert res["disponible"] is False
    assert "Monitoring Viewer" in res["error"] and "denied" in res["error"]
