"""
tests/test_usuarios_web.py — Pruebas de integración de la pantalla de Usuarios (Fase 2).
"""

import pytest
from app import app
import firebase_client as fb


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@pytest.fixture(autouse=True)
def setup_usuarios_cache(monkeypatch):
    """Configura usuarios en caché para pruebas web."""
    usuarios_mock = {
        "76807817": {
            "_id": "76807817",
            "nro_conexion": "000796",
            "nombre": "ALVAREZ CHUQUIYANQUI, MARIBEL NAYELI",
            "sector": "BARRIO DE LUCMANI",
            "direccion": "AUCAYPATA S/N",
            "codigo_categoria": "A",
            "activo": True,
            "medidores": ["22392996"],
        },
        "07654321-1": {
            "_id": "07654321-1",
            "nro_conexion": "000100",
            "nombre": "QUISPE MONTALVO, JUAN",
            "sector": "BARRIO DE CHAUPI",
            "direccion": "CHAUPI S/N",
            "codigo_categoria": "A",
            "activo": True,
            "medidores": ["003386"],
        },
        "SD-001": {
            "_id": "SD-001",
            "nro_conexion": "000101",
            "nombre": "MAMANI FLORES, ROSA",
            "sector": "HUAQUILLO",
            "direccion": "HUAQUILLO S/N",
            "codigo_categoria": "A",
            "activo": False,
            "medidores": ["009174"],
        },
    }

    config_mock = {
        "empresa": {"nombre": "CAAPD Ispacas"},
        "sectores": ["BARRIO DE CHAUPI", "BARRIO DE LUCMANI", "HUAQUILLO"],
        "categorias": {"A": {"nombre": "Doméstico"}},
        "mes_actual": {
            "periodo": "2026-09",
            "estado": "ABIERTO",
        },
    }

    monkeypatch.setattr(fb, "cargar_config", lambda: config_mock)
    monkeypatch.setattr(fb, "cargar_usuarios", lambda forzar=False: dict(usuarios_mock))
    monkeypatch.setattr(fb, "obtener_usuario", lambda uid: usuarios_mock.get(uid))
    monkeypatch.setattr(fb, "guardar_usuario", lambda uid, d: usuarios_mock.update({uid: d}))
    monkeypatch.setattr(fb, "actualizar_usuario", lambda uid, d: usuarios_mock[uid].update(d) if uid in usuarios_mock else None)
    monkeypatch.setattr(fb, "borrar_usuario", lambda uid: usuarios_mock.pop(uid, None))
    monkeypatch.setattr(fb, "obtener_siguiente_conexion_libre", lambda: "000797")
    monkeypatch.setattr(fb, "obtener_siguiente_id_sd", lambda: "SD-002")


def test_usuarios_index(client):
    """La página /usuarios carga correctamente y muestra la tabla y botones."""
    res = client.get("/usuarios")
    assert res.status_code == 200
    contenido = res.get_data(as_text=True)
    assert "Padrón de Usuarios" in contenido
    assert "ALVAREZ CHUQUIYANQUI, MARIBEL NAYELI" in contenido
    assert "000796" in contenido
    assert "Pedir DNI" in contenido


def test_usuarios_filtro_activos(client):
    res = client.get("/usuarios?filtro=activos")
    assert res.status_code == 200
    contenido = res.get_data(as_text=True)
    assert "ALVAREZ CHUQUIYANQUI" in contenido
    assert "MAMANI FLORES, ROSA" not in contenido  # inactivo


def test_usuarios_filtro_inactivos(client):
    res = client.get("/usuarios?filtro=inactivos")
    assert res.status_code == 200
    contenido = res.get_data(as_text=True)
    assert "MAMANI FLORES, ROSA" in contenido
    assert "ALVAREZ CHUQUIYANQUI" not in contenido


def test_usuarios_filtro_pendientes(client):
    res = client.get("/usuarios?filtro=pendientes")
    assert res.status_code == 200
    contenido = res.get_data(as_text=True)
    assert "07654321-1" in contenido
    assert "SD-001" in contenido
    assert "76807817" not in contenido


def test_usuarios_busqueda_inteligente(client):
    # Por medidor con ceros
    res = client.get("/usuarios?q=3386")
    assert res.status_code == 200
    contenido = res.get_data(as_text=True)
    assert "QUISPE MONTALVO, JUAN" in contenido
    assert "ALVAREZ CHUQUIYANQUI" not in contenido

    # Por nombre desordenado
    res2 = client.get("/usuarios?q=maribel alvarez")
    assert res2.status_code == 200
    contenido2 = res2.get_data(as_text=True)
    assert "ALVAREZ CHUQUIYANQUI, MARIBEL NAYELI" in contenido2


def test_usuarios_api_detalle(client):
    res = client.get("/api/usuarios/76807817")
    assert res.status_code == 200
    datos = res.get_json()
    assert datos["nro_conexion"] == "000796"
    assert datos["nombre"] == "ALVAREZ CHUQUIYANQUI, MARIBEL NAYELI"

    res_404 = client.get("/api/usuarios/99999999")
    assert res_404.status_code == 404


def test_usuarios_guardar_validacion_medidor_duplicado(client):
    # Intenta asignar el medidor '22392996' (que ya es de Maribel) a otro usuario
    res = client.post("/usuarios/guardar", data={
        "id_usuario": "88888888",
        "nombre": "NUEVO USUARIO",
        "nro_conexion": "000797",
        "sector": "BARRIO DE LUCMANI",
        "direccion": "S/N",
        "codigo_categoria": "A",
        "activo": "1",
        "medidores": "22392996",
    }, follow_redirects=True)
    assert res.status_code == 200
    contenido = res.get_data(as_text=True)
    assert "ya está asignado" in contenido
