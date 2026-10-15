"""
firebase_client.py — Cliente Firebase Admin + caché en memoria.

REGLAS:
- Los usuarios y el mes actual se cargan UNA VEZ por sesión.
- Las escrituras se hacen en lotes de máximo 500.
- Se contabilizan todas las lecturas y escrituras.
- Se emite aviso cuando se acerca a los límites del plan gratuito.
"""

from __future__ import annotations
import os
import threading
import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1 import WriteBatch

try:
    from config_local import FIREBASE_KEY_PATH
except ImportError:
    FIREBASE_KEY_PATH = os.environ.get("FIREBASE_KEY_PATH", "serviceAccountKey.json")

# ---------------------------------------------------------------------------
# Límites del plan gratuito (Spark)
# ---------------------------------------------------------------------------
LIMITE_LECTURAS_DIA = 50_000
LIMITE_ESCRITURAS_DIA = 20_000
UMBRAL_AVISO_LECTURAS = 45_000
UMBRAL_AVISO_ESCRITURAS = 18_000
BATCH_MAX = 500  # Firestore limita 500 operaciones por lote

# ---------------------------------------------------------------------------
# Inicialización de la app Firebase (singleton)
# ---------------------------------------------------------------------------
_lock = threading.Lock()
_app = None
_db = None


def _inicializar():
    global _app, _db
    with _lock:
        if _app is not None:
            return
        if not os.path.exists(FIREBASE_KEY_PATH):
            raise FileNotFoundError(
                f"No se encontró el archivo de credenciales Firebase:\n"
                f"  {FIREBASE_KEY_PATH}\n"
                f"Edita config_local.py con la ruta correcta."
            )
        cred = credentials.Certificate(FIREBASE_KEY_PATH)
        _app = firebase_admin.initialize_app(cred)
        _db = firestore.client()


def db() -> firestore.Client:
    """Devuelve el cliente Firestore, inicializando si es necesario."""
    if _db is None:
        _inicializar()
    return _db


# ---------------------------------------------------------------------------
# Caché en memoria (una sola carga por sesión)
# ---------------------------------------------------------------------------
_cache: dict = {
    "config": None,
    "usuarios": None,       # {id_usuario: {...}}
    "mes": None,            # {id_usuario: {...}}
    "periodo_cargado": None,
    "ops": {"lecturas": 0, "escrituras": 0},
}


def _contar(tipo: str, n: int = 1):
    _cache["ops"][tipo] += n


def get_ops() -> dict:
    """Devuelve el contador de operaciones de la sesión."""
    return dict(_cache["ops"])


def hay_aviso_ops() -> dict:
    """Devuelve avisos si se acerca a los límites del plan gratuito."""
    ops = _cache["ops"]
    avisos = {}
    if ops["lecturas"] >= UMBRAL_AVISO_LECTURAS:
        avisos["lecturas"] = (
            f"⚠ Has usado {ops['lecturas']:,} lecturas hoy. "
            f"El límite gratuito es {LIMITE_LECTURAS_DIA:,}."
        )
    if ops["escrituras"] >= UMBRAL_AVISO_ESCRITURAS:
        avisos["escrituras"] = (
            f"⚠ Has usado {ops['escrituras']:,} escrituras hoy. "
            f"El límite gratuito es {LIMITE_ESCRITURAS_DIA:,}."
        )
    return avisos


def limpiar_cache(limpiar_config: bool = False):
    """Limpia la caché para forzar recarga desde Firestore."""
    _cache["usuarios"] = None
    _cache["mes"] = None
    _cache["periodo_cargado"] = None
    if limpiar_config:
        _cache["config"] = None


# ---------------------------------------------------------------------------
# config/general
# ---------------------------------------------------------------------------

def _intentar_cargar_desde_respaldo_local() -> dict:
    """Lee el respaldo local más reciente para evitar lecturas innecesarias a Firestore."""
    try:
        from pathlib import Path
        import respaldo_excel
        dir_resp = Path(__file__).resolve().parent / "respaldos"
        archivos = list(dir_resp.glob("RESPALDO_*.xlsx"))
        if not archivos:
            dir_resp = Path(__file__).resolve().parent / "escritorio" / "respaldos"
            archivos = list(dir_resp.glob("RESPALDO_*.xlsx"))
        if archivos:
            archivos.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            return respaldo_excel.leer_respaldo_excel(archivos[0])
    except Exception:
        pass
    return {}


def cargar_config() -> dict:
    """Carga config/general desde caché, respaldo local o Firestore."""
    if _cache["config"] is not None:
        return _cache["config"]

    datos_local = _intentar_cargar_desde_respaldo_local()
    if datos_local.get("config"):
        _cache["config"] = datos_local["config"]
        return _cache["config"]

    doc = db().collection("config").document("general").get()
    _contar("lecturas", 1)
    if not doc.exists:
        raise RuntimeError(
            "No existe config/general en Firestore. "
            "Ejecuta scripts/sembrar_config.py primero."
        )
    _cache["config"] = doc.to_dict()
    return _cache["config"]


def guardar_config(datos: dict):
    """Guarda config/general en Firestore y actualiza la caché."""
    db().collection("config").document("general").set(datos)
    _contar("escrituras", 1)
    _cache["config"] = datos


def actualizar_config_campo(campo: str, valor):
    """Actualiza un único campo de config/general (merge)."""
    db().collection("config").document("general").update({campo: valor})
    _contar("escrituras", 1)
    if _cache["config"] is not None:
        # Actualizar caché anidada con notación de punto
        partes = campo.split(".")
        nodo = _cache["config"]
        for p in partes[:-1]:
            nodo = nodo.setdefault(p, {})
        nodo[partes[-1]] = valor


# ---------------------------------------------------------------------------
# Usuarios
# ---------------------------------------------------------------------------

def cargar_usuarios(forzar: bool = False) -> dict:
    """Carga todos los usuarios activos UNA vez (caché por sesión o respaldo local).

    Devuelve dict {id_usuario: {...}}.
    forzar=True obliga recarga desde Firestore.
    """
    if _cache["usuarios"] is not None and not forzar:
        return _cache["usuarios"]

    if not forzar:
        datos_local = _intentar_cargar_desde_respaldo_local()
        if datos_local.get("usuarios"):
            _cache["usuarios"] = datos_local["usuarios"]
            return _cache["usuarios"]

    docs = db().collection("usuarios").stream()
    usuarios = {}
    n = 0
    for doc in docs:
        datos = doc.to_dict()
        datos["_id"] = doc.id
        usuarios[doc.id] = datos
        n += 1
    _contar("lecturas", n)
    _cache["usuarios"] = usuarios
    return usuarios


def obtener_usuario(id_usuario: str) -> dict | None:
    """Devuelve un usuario de la caché (o Firestore si no está cargado)."""
    if _cache["usuarios"] is not None:
        return _cache["usuarios"].get(id_usuario)
    doc = db().collection("usuarios").document(id_usuario).get()
    _contar("lecturas", 1)
    return doc.to_dict() if doc.exists else None


def guardar_usuario(id_usuario: str, datos: dict):
    """Crea o sobreescribe un documento de usuario."""
    db().collection("usuarios").document(id_usuario).set(datos)
    _contar("escrituras", 1)
    if _cache["usuarios"] is not None:
        datos["_id"] = id_usuario
        _cache["usuarios"][id_usuario] = datos


def actualizar_usuario(id_usuario: str, cambios: dict):
    """Actualiza campos de un usuario (merge parcial)."""
    db().collection("usuarios").document(id_usuario).update(cambios)
    _contar("escrituras", 1)
    if _cache["usuarios"] is not None and id_usuario in _cache["usuarios"]:
        _cache["usuarios"][id_usuario].update(cambios)


def borrar_usuario(id_usuario: str):
    """Elimina un documento de usuario (solo para corrección de DNI)."""
    db().collection("usuarios").document(id_usuario).delete()
    _contar("escrituras", 1)
    if _cache["usuarios"] is not None:
        _cache["usuarios"].pop(id_usuario, None)


def guardar_usuarios_lote(usuarios: dict[str, dict]):
    """Guarda múltiples usuarios en lotes de máximo 500."""
    items = list(usuarios.items())
    col = db().collection("usuarios")
    for i in range(0, len(items), BATCH_MAX):
        chunk = items[i:i + BATCH_MAX]
        batch: WriteBatch = db().batch()
        for id_usr, datos in chunk:
            ref = col.document(id_usr)
            batch.set(ref, datos)
        batch.commit()
        _contar("escrituras", len(chunk))
        if _cache["usuarios"] is not None:
            for id_usr, datos in chunk:
                datos["_id"] = id_usr
                _cache["usuarios"][id_usr] = datos


# ---------------------------------------------------------------------------
# Mes (colección mes_aaaa-mm)
# ---------------------------------------------------------------------------

def nombre_coleccion_mes(periodo: str) -> str:
    """Devuelve el nombre de la colección para el periodo dado."""
    return f"mes_{periodo}"


def cargar_mes(periodo: str, forzar: bool = False) -> dict:
    """Carga todos los documentos del mes UNA vez (caché por sesión o respaldo local).

    Devuelve dict {id_usuario: {...}}.
    """
    if (
        _cache["mes"] is not None
        and _cache["periodo_cargado"] == periodo
        and not forzar
    ):
        return _cache["mes"]

    if not forzar:
        datos_local = _intentar_cargar_desde_respaldo_local()
        if datos_local.get("mes_docs"):
            _cache["mes"] = datos_local["mes_docs"]
            _cache["periodo_cargado"] = periodo
            return _cache["mes"]

    col = nombre_coleccion_mes(periodo)
    docs = db().collection(col).stream()
    mes = {}
    n = 0
    for doc in docs:
        datos = doc.to_dict()
        datos["_id"] = doc.id
        mes[doc.id] = datos
        n += 1
    _contar("lecturas", n)
    _cache["mes"] = mes
    _cache["periodo_cargado"] = periodo
    return mes


def existe_mes(periodo: str) -> bool:
    """True si ya existe al menos un documento en el mes (evita sobrescribir)."""
    col = nombre_coleccion_mes(periodo)
    docs = list(db().collection(col).limit(1).stream())
    _contar("lecturas", 1)
    return len(docs) > 0


def obtener_doc_mes(periodo: str, id_usuario: str) -> dict | None:
    """Devuelve el documento de un usuario en el mes (desde caché)."""
    if _cache["mes"] is not None and _cache["periodo_cargado"] == periodo:
        return _cache["mes"].get(id_usuario)
    col = nombre_coleccion_mes(periodo)
    doc = db().collection(col).document(id_usuario).get()
    _contar("lecturas", 1)
    return doc.to_dict() if doc.exists else None


def actualizar_doc_mes(periodo: str, id_usuario: str, cambios: dict):
    """Actualiza campos de un documento del mes."""
    col = nombre_coleccion_mes(periodo)
    db().collection(col).document(id_usuario).update(cambios)
    _contar("escrituras", 1)
    if _cache["mes"] is not None and id_usuario in _cache["mes"]:
        _cache["mes"][id_usuario].update(cambios)


def guardar_mes_lote(periodo: str, documentos: dict[str, dict]):
    """Crea o sobreescribe documentos del mes en lotes de máximo 500."""
    col_name = nombre_coleccion_mes(periodo)
    col = db().collection(col_name)
    items = list(documentos.items())
    for i in range(0, len(items), BATCH_MAX):
        chunk = items[i:i + BATCH_MAX]
        batch: WriteBatch = db().batch()
        for id_usr, datos in chunk:
            ref = col.document(id_usr)
            batch.set(ref, datos)
        batch.commit()
        _contar("escrituras", len(chunk))
        if _cache["mes"] is not None and _cache["periodo_cargado"] == periodo:
            for id_usr, datos in chunk:
                datos["_id"] = id_usr
                _cache["mes"][id_usr] = datos


def corregir_dni_en_mes(periodo: str,
                         id_viejo: str,
                         id_nuevo: str):
    """Copia el doc del mes al nuevo ID y borra el viejo."""
    col_name = nombre_coleccion_mes(periodo)
    col = db().collection(col_name)

    doc_viejo = col.document(id_viejo).get()
    _contar("lecturas", 1)
    if not doc_viejo.exists:
        return

    datos = doc_viejo.to_dict()
    col.document(id_nuevo).set(datos)
    col.document(id_viejo).delete()
    _contar("escrituras", 2)

    if _cache["mes"] is not None and _cache["periodo_cargado"] == periodo:
        _cache["mes"][id_nuevo] = datos
        _cache["mes"].pop(id_viejo, None)


# ---------------------------------------------------------------------------
# Corrección de DNI (usuarios + todos los meses conocidos)
# ---------------------------------------------------------------------------

def listar_colecciones_mes() -> list[str]:
    """Descubre o devuelve los periodos de colecciones mes_* existentes."""
    periodos = set()
    # 1. Del mes_actual en config
    cfg = cargar_config()
    periodo_cfg = cfg.get("mes_actual", {}).get("periodo")
    if periodo_cfg:
        periodos.add(periodo_cfg)

    # 2. De las colecciones en Firestore
    try:
        cols = db().collections()
        for col in cols:
            if col.id.startswith("mes_"):
                periodos.add(col.id[4:])
    except Exception:
        pass
    return sorted(list(periodos))


def corregir_dni_usuario(
    id_viejo: str, id_nuevo: str, periodos: list[str] | None = None
) -> dict[str, Any]:
    """Crea el doc con el ID correcto, copia datos, borra el anterior.

    Aplica en la colección usuarios y en cada mes indicado (o todos los meses descubiertos).
    Devuelve un resumen de las operaciones realizadas.
    """
    id_viejo = id_viejo.strip()
    id_nuevo = id_nuevo.strip()

    if id_viejo == id_nuevo:
        raise ValueError("El nuevo ID es igual al ID actual.")

    # 1. Validar que id_nuevo no exista
    existente = obtener_usuario(id_nuevo)
    if existente is not None:
        raise ValueError(
            f"El usuario con ID {id_nuevo} ya existe en el padrón ({existente.get('nombre')})."
        )

    # 2. Obtener datos del viejo
    datos = obtener_usuario(id_viejo)
    if datos is None:
        raise ValueError(f"El usuario con ID {id_viejo} no existe.")

    datos_limpios = {k: v for k, v in datos.items() if k != "_id"}
    guardar_usuario(id_nuevo, datos_limpios)
    borrar_usuario(id_viejo)

    # 3. Colecciones de mes
    if periodos is None:
        periodos = listar_colecciones_mes()

    meses_actualizados = []
    for periodo in periodos:
        # Verificar si existe el doc en ese mes antes de renombrar
        doc_mes = obtener_doc_mes(periodo, id_viejo)
        if doc_mes is not None:
            corregir_dni_en_mes(periodo, id_viejo, id_nuevo)
            meses_actualizados.append(periodo)

    return {
        "id_viejo": id_viejo,
        "id_nuevo": id_nuevo,
        "nombre": datos_limpios.get("nombre", ""),
        "usuario_actualizado": True,
        "meses_actualizados": meses_actualizados,
    }


# ---------------------------------------------------------------------------
# Utilidades para gestión del padrón de usuarios
# ---------------------------------------------------------------------------

def obtener_siguiente_conexion_libre() -> str:
    """Devuelve el siguiente número de conexión disponible (6 dígitos)."""
    usuarios = cargar_usuarios()
    max_num = 0
    for u in usuarios.values():
        con = str(u.get("nro_conexion") or "").strip()
        if con.isdigit():
            val = int(con)
            if val > max_num:
                max_num = val
    return f"{max_num + 1:06d}"


def obtener_siguiente_id_sd() -> str:
    """Devuelve el siguiente ID para persona sin DNI (formato SD-xxx)."""
    usuarios = cargar_usuarios()
    max_sd = 0
    import re
    for uid in usuarios.keys():
        m = re.match(r"^SD-(\d+)$", str(uid).strip())
        if m:
            val = int(m.group(1))
            if val > max_sd:
                max_sd = val
    return f"SD-{max_sd + 1:03d}"


def validar_medidores_unicos(
    medidores: list[str], id_usuario_actual: str | None = None
) -> tuple[bool, str | None]:
    """Verifica que ningún medidor de la lista esté asignado a otra persona.

    Devuelve (True, None) si son válidos, o (False, mensaje_error) si hay colisión.
    """
    usuarios = cargar_usuarios()
    meds_set = {m.strip() for m in medidores if m and m.strip()}

    for uid, u in usuarios.items():
        if id_usuario_actual and uid == id_usuario_actual:
            continue
        u_meds = [
            m if isinstance(m, str) else m.get("nro_medidor", "")
            for m in u.get("medidores", [])
        ]
        u_meds_set = {m.strip() for m in u_meds if m and m.strip()}
        interseccion = meds_set.intersection(u_meds_set)
        if interseccion:
            med_duplicado = list(interseccion)[0]
            nombre_duenho = u.get("nombre", "Desconocido")
            return (
                False,
                f"El medidor {med_duplicado} ya está asignado a '{nombre_duenho}' (ID: {uid}).",
            )

    return True, None


def agregar_usuario_al_mes_actual(
    id_usuario: str, datos_usuario: dict[str, Any]
) -> bool:
    """Si el mes actual está ABIERTO, crea la fila del usuario en la colección mes."""
    cfg = cargar_config()
    mes_actual = cfg.get("mes_actual", {})
    if mes_actual.get("estado") != "ABIERTO":
        return False

    periodo = mes_actual.get("periodo")
    if not periodo:
        return False

    col = nombre_coleccion_mes(periodo)
    doc_ref = db().collection(col).document(id_usuario)
    doc_existente = doc_ref.get()
    _contar("lecturas", 1)
    if doc_existente.exists:
        return False

    # Preparar medidores del mes
    medidores_mes = []
    for m in datos_usuario.get("medidores", []):
        nro = m if isinstance(m, str) else m.get("nro_medidor", "")
        if nro:
            medidores_mes.append(
                {
                    "nro_medidor": nro,
                    "lectura_anterior": 0,
                    "fecha_anterior": None,
                    "consumo_anterior": None,
                    "lectura_actual": None,
                    "fecha_lectura": None,
                    "estado_lectura": "PENDIENTE",
                    "novedad": "NORMAL",
                    "nota": "",
                    "registrado_por": None,
                }
            )

    doc_mes = {
        "nro_conexion": datos_usuario.get("nro_conexion", ""),
        "nombre": datos_usuario.get("nombre", ""),
        "sector": datos_usuario.get("sector", ""),
        "direccion": datos_usuario.get("direccion", ""),
        "codigo_categoria": datos_usuario.get("codigo_categoria", "A"),
        "medidores": medidores_mes,
        "consumo_total_m3": None,
        "historial_m3": [],
        "nro_recibo": None,
        "monto_agua": 0.0,
        "monto_desague": 0.0,
        "cargo_fijo": 0.0,
        "deuda_anterior": 0.0,
        "igv": 0.0,
        "redondeo": 0.0,
        "total_a_pagar": 0.0,
        "meses_adeudados": 1,
        "monto_pagado": 0.0,
        "fecha_pago": None,
    }

    doc_ref.set(doc_mes)
    _contar("escrituras", 1)
    if _cache["mes"] is not None and _cache["periodo_cargado"] == periodo:
        doc_mes["_id"] = id_usuario
        _cache["mes"][id_usuario] = doc_mes
    return True
