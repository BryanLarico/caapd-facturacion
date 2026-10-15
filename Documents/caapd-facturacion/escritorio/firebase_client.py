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

PROYECTO_REAL_ID = "caapd-ispacas-optimizado"
try:
    from config_local import PROYECTO_REAL_ID
except ImportError:
    pass

if os.environ.get("CAAPD_ENTORNO", "").strip().lower() == "prueba":
    try:
        from config_local_prueba import FIREBASE_KEY_PATH
    except ImportError:
        try:
            from config_local import FIREBASE_KEY_PATH
        except ImportError:
            FIREBASE_KEY_PATH = os.environ.get(
                "FIREBASE_KEY_PATH", "serviceAccountKey.json")
else:
    try:
        from config_local import FIREBASE_KEY_PATH
    except ImportError:
        FIREBASE_KEY_PATH = os.environ.get(
            "FIREBASE_KEY_PATH", "serviceAccountKey.json")


def obtener_proyecto_id() -> str:
    """Obtiene el ID del proyecto Firebase configurado en las credenciales."""
    try:
        if os.path.exists(FIREBASE_KEY_PATH):
            import json
            with open(FIREBASE_KEY_PATH, "r", encoding="utf-8") as f:
                d = json.load(f)
                return str(d.get("project_id", "")).strip()
    except Exception:
        pass
    return PROYECTO_REAL_ID


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


def _get_db() -> firestore.Client:
    """Alias de db(). Lo usan generar_recibo_usuario, registrar_pago y anular_pago."""
    return db()


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
        import rutas
        import respaldo_excel
        p_resp = rutas.ruta_respaldos()
        archivos = list(p_resp.glob("RESPALDO_*.xlsx"))
        if not archivos:
            dir_raiz = p_resp.parent / "respaldos"
            if dir_raiz.exists():
                archivos = list(dir_raiz.glob("RESPALDO_*.xlsx"))
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


# ---------------------------------------------------------------------------
# Ciclo de vida del mes (Fase 3: Abrir mes y Lecturas)
# ---------------------------------------------------------------------------

def calcular_mes_siguiente(periodo: str) -> str:
    """Devuelve el siguiente periodo en formato AAAA-MM (ej. 2026-09 -> 2026-10)."""
    import datetime
    try:
        partes = periodo.strip().split("-")
        y, m = int(partes[0]), int(partes[1])
        if m == 12:
            return f"{y + 1:04d}-01"
        return f"{y:04d}-{m + 1:02d}"
    except Exception:
        hoy = datetime.date.today()
        return f"{hoy.year:04d}-{hoy.month:02d}"


def verificar_puede_abrir_mes() -> tuple[bool, str, str]:
    """Verifica si es legal abrir un nuevo mes según el estado del mes actual.

    Devuelve (puede_abrir, mensaje_explicativo, periodo_sugerido).
    Regla: Si hay un mes en curso con estado ABIERTO o CERRADO, NO se puede abrir.
    """
    cfg = cargar_config()
    mes_actual = cfg.get("mes_actual") or {}
    periodo_actual = mes_actual.get("periodo")
    estado_actual = (mes_actual.get("estado") or "").strip().upper()

    # Si ya hay un mes activo sin facturar, no se puede abrir otro
    if periodo_actual and estado_actual in ("ABIERTO", "CERRADO"):
        return (
            False,
            f"Ya existe una base activa para el mes {periodo_actual} (Estado: {estado_actual}). "
            f"Debe cerrarse y facturarse antes de abrir un nuevo mes.",
            periodo_actual,
        )

    # Calcular periodo sugerido
    if periodo_actual:
        siguiente = calcular_mes_siguiente(periodo_actual)
    else:
        # Descubrir si hay colecciones previas
        cols = listar_colecciones_mes()
        if cols:
            siguiente = calcular_mes_siguiente(max(cols))
        else:
            import datetime
            hoy = datetime.date.today()
            siguiente = f"{hoy.year:04d}-{hoy.month:02d}"

    return True, "Listo para abrir un nuevo mes.", siguiente


def verificar_periodo_disponible(periodo: str) -> tuple[bool, str]:
    """Verifica si ya existe una base (colección) en Firestore para el periodo dado.

    Devuelve (disponible, mensaje).
    """
    periodo = periodo.strip()
    if existe_mes(periodo):
        return (
            False,
            f"Ya existe una base de datos registrada para el mes {periodo}. "
            f"No es posible sobrescribir una base existente.",
        )
    return True, f"El periodo {periodo} está disponible."


def _cargar_semilla_mes_previo() -> dict[str, Any]:
    """Carga semilla_mes_previo.json desde salida/ o datos/."""
    from pathlib import Path
    import json

    candidatos = [
        Path(__file__).resolve().parent / "salida" / "semilla_mes_previo.json",
        Path(__file__).resolve().parent.parent /
        "salida" / "semilla_mes_previo.json",
        Path(__file__).resolve().parent / "datos" / "semilla_mes_previo.json",
    ]
    for c in candidatos:
        if c.exists():
            with open(c, "r", encoding="utf-8") as f:
                return json.load(f)
    return {}


def abrir_mes(
    periodo: str,
    fecha_emision: str,
    fecha_vencimiento: str,
    lecturas_iniciales: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Abre un nuevo mes operativo creando la colección mes_aaaa-mm con copia de usuarios activos.

    Aplica la lógica de Fase 3:
    - Validación: bloquea si ya hay un mes activo sin facturar o si la base ya existe.
    - Medidores: lectura anterior tomada del mes previo o de semilla_mes_previo.json.
    - Escritura en lotes de 500.
    - Actualización de config.mes_actual a estado ABIERTO.
    - Llamada a on_datos_cambiados.
    """
    periodo = periodo.strip()
    lecturas_iniciales = lecturas_iniciales or {}

    # 1. Validar reglas de apertura
    puede, motivo, _ = verificar_puede_abrir_mes()
    if not puede:
        raise ValueError(motivo)

    disponible, motivo_disp = verificar_periodo_disponible(periodo)
    if not disponible:
        raise ValueError(motivo_disp)

    # 2. Cargar usuarios activos del padrón
    todos_usuarios = cargar_usuarios()
    usuarios_activos = {
        uid: u for uid, u in todos_usuarios.items() if u.get("activo", True)
    }
    if not usuarios_activos:
        raise ValueError(
            "No se encontraron usuarios activos en el padrón para abrir el mes.")

    # 3. Determinar mes anterior para encadenar lecturas
    cols_existentes = [c for c in listar_colecciones_mes() if c < periodo]
    periodo_anterior = max(cols_existentes) if cols_existentes else None

    mes_anterior = None
    if periodo_anterior and existe_mes(periodo_anterior):
        try:
            mes_anterior = cargar_mes(periodo_anterior)
        except Exception:
            mes_anterior = None

    semilla = {}
    if mes_anterior is None:
        semilla = _cargar_semilla_mes_previo()

    # 4. Construir documentos del nuevo mes
    documentos_mes: dict[str, dict[str, Any]] = {}

    for uid, u in usuarios_activos.items():
        doc_anterior = (mes_anterior or {}).get(uid)
        historial_previo = (doc_anterior.get("historial_m3")
                            or []) if doc_anterior else []
        consumo_previo_total = doc_anterior.get(
            "consumo_total_m3") if doc_anterior else None

        # Historial: últimos 5 consumos
        if consumo_previo_total is not None and isinstance(consumo_previo_total, (int, float)):
            nuevo_historial = (historial_previo +
                               [int(consumo_previo_total)])[-5:]
        else:
            nuevo_historial = historial_previo[-5:]

        # Medidores del usuario
        medidores_mes = []
        for m_item in u.get("medidores", []):
            nro_med = m_item if isinstance(
                m_item, str) else m_item.get("nro_medidor", "")
            if not nro_med:
                continue

            lectura_ant = 0
            fecha_ant = None
            consumo_ant = None

            if doc_anterior:
                # Buscar el medidor en el mes anterior
                m_ant = next(
                    (m for m in doc_anterior.get("medidores", [])
                     if m.get("nro_medidor") == nro_med),
                    None,
                )
                if m_ant:
                    if m_ant.get("estado_lectura") == "LEIDO" and m_ant.get("lectura_actual") is not None:
                        lectura_ant = int(m_ant["lectura_actual"])
                        fecha_ant = m_ant.get("fecha_lectura")
                        consumo_ant = int(
                            lectura_ant - (m_ant.get("lectura_anterior") or 0))
                    else:
                        lectura_ant = int(m_ant.get("lectura_anterior") or 0)
                        fecha_ant = m_ant.get("fecha_anterior")
                        consumo_ant = m_ant.get("consumo_anterior")
            else:
                # Primer mes: buscar en semilla
                if nro_med in semilla:
                    sem = semilla[nro_med]
                    lectura_ant = int(sem.get("lectura_actual", 0))
                    fecha_ant = sem.get("fecha")
                    c_ant = lectura_ant - int(sem.get("lectura_anterior", 0))
                    consumo_ant = c_ant if c_ant >= 0 else None
                    if not nuevo_historial and consumo_ant is not None:
                        nuevo_historial = [consumo_ant]
                elif nro_med in lecturas_iniciales:
                    lectura_ant = int(lecturas_iniciales[nro_med])
                    fecha_ant = None
                    consumo_ant = None

            medidores_mes.append(
                {
                    "nro_medidor": nro_med,
                    "lectura_anterior": lectura_ant,
                    "fecha_anterior": fecha_ant,
                    "consumo_anterior": consumo_ant,
                    "lectura_actual": None,
                    "fecha_lectura": None,
                    "estado_lectura": "PENDIENTE",
                    "novedad": "",
                    "nota": "",
                    "registrado_por": None,
                }
            )

        documentos_mes[uid] = {
            "nro_conexion": u.get("nro_conexion", ""),
            "nombre": u.get("nombre", ""),
            "sector": u.get("sector", ""),
            "direccion": u.get("direccion", ""),
            "codigo_categoria": u.get("codigo_categoria", "A"),
            "medidores": medidores_mes,
            "consumo_total_m3": None,
            "historial_m3": nuevo_historial,
            "nro_recibo": None,
            "monto_agua": None,
            "monto_desague": None,
            "cargo_fijo": None,
            "deuda_anterior": 0.0,
            "igv": 0.0,
            "redondeo": 0.0,
            "total_a_pagar": None,
            "meses_adeudados": 1,
            "monto_pagado": 0.0,
            "fecha_pago": None,
        }

    # 5. Guardar documentos en lotes de 500
    guardar_mes_lote(periodo, documentos_mes)

    # 6. Actualizar config.mes_actual
    nuevo_mes_actual = {
        "periodo": periodo,
        "fecha_emision": fecha_emision,
        "fecha_vencimiento": fecha_vencimiento,
        "estado": "ABIERTO",
    }
    actualizar_config_campo("mes_actual", nuevo_mes_actual)

    # Limpiar caché
    limpiar_cache(limpiar_config=True)

    # 7. Disparar evento de respaldo
    try:
        from respaldo import on_datos_cambiados
        on_datos_cambiados(
            "abrir_mes", {"periodo": periodo, "usuarios": len(documentos_mes)})
    except Exception:
        pass

    return {
        "periodo": periodo,
        "usuarios_creados": len(documentos_mes),
        "estado": "ABIERTO",
    }


def cerrar_lecturas(periodo: str | None = None) -> dict[str, Any]:
    """Pasa el estado del mes actual a CERRADO (la app móvil deja de aceptar lecturas)."""
    cfg = cargar_config()
    mes_actual = cfg.get("mes_actual") or {}
    periodo_obj = periodo or mes_actual.get("periodo")
    if not periodo_obj:
        raise ValueError("No hay un mes activo para cerrar lecturas.")

    actualizar_config_campo("mes_actual.estado", "CERRADO")
    limpiar_cache(limpiar_config=True)

    try:
        from respaldo import on_datos_cambiados
        on_datos_cambiados("cerrar_lecturas", {"periodo": periodo_obj})
    except Exception:
        pass

    return {"periodo": periodo_obj, "estado": "CERRADO"}


def reabrir_lecturas(periodo: str | None = None) -> dict[str, Any]:
    """Reabre lecturas (pasa de CERRADO a ABIERTO). No permitido si ya está FACTURADO."""
    cfg = cargar_config()
    mes_actual = cfg.get("mes_actual") or {}
    periodo_obj = periodo or mes_actual.get("periodo")
    if not periodo_obj:
        raise ValueError("No hay un mes activo para reabrir.")

    estado_actual = (mes_actual.get("estado") or "").upper()
    if estado_actual == "FACTURADO":
        raise ValueError(
            "El mes ya fue facturado y no puede reabrirse para lecturas.")

    actualizar_config_campo("mes_actual.estado", "ABIERTO")
    limpiar_cache(limpiar_config=True)

    try:
        from respaldo import on_datos_cambiados
        on_datos_cambiados("reabrir_lecturas", {"periodo": periodo_obj})
    except Exception:
        pass

    return {"periodo": periodo_obj, "estado": "ABIERTO"}


def guardar_lectura_medidor(
    periodo: str,
    id_usuario: str,
    nro_medidor: str,
    lectura_actual: int,
    novedad: str = "NORMAL",
    nota: str = "",
    registrado_por: str = "ADMIN",
) -> dict[str, Any]:
    """Actualiza la lectura de un medidor en el mes y recalcula el consumo_total_m3 del usuario."""
    import datetime
    import calculos

    doc = obtener_doc_mes(periodo, id_usuario)
    if doc is None:
        raise ValueError(
            f"No se encontró el documento para el usuario {id_usuario} en el mes {periodo}.")

    medidores = doc.get("medidores", [])
    medidor_encontrado = None
    for m in medidores:
        if m.get("nro_medidor") == nro_medidor:
            medidor_encontrado = m
            break

    if medidor_encontrado is None:
        raise ValueError(
            f"El medidor {nro_medidor} no pertenece al usuario {id_usuario}.")

    hoy_str = datetime.date.today().isoformat()
    medidor_encontrado["lectura_actual"] = int(lectura_actual)
    medidor_encontrado["fecha_lectura"] = hoy_str
    medidor_encontrado["estado_lectura"] = "LEIDO"
    medidor_encontrado["novedad"] = novedad or "NORMAL"
    medidor_encontrado["nota"] = nota or ""
    medidor_encontrado["registrado_por"] = registrado_por

    # Recalcular consumo_total_m3 si todos los medidores están leídos
    todos_leidos = all(m.get("lectura_actual") is not None for m in medidores)
    if todos_leidos:
        consumo_total = 0.0
        for m in medidores:
            ant = m.get("lectura_anterior") or 0
            act = m["lectura_actual"]
            nov = m.get("novedad")
            c = calculos.consumo_medidor(ant, act, nov)
            consumo_total += c
        doc["consumo_total_m3"] = round(consumo_total, 2)
    else:
        doc["consumo_total_m3"] = None

    actualizar_doc_mes(periodo, id_usuario, doc)

    try:
        from respaldo import on_datos_cambiados
        on_datos_cambiados(
            "lectura_guardada",
            {
                "periodo": periodo,
                "id_usuario": id_usuario,
                "nro_medidor": nro_medidor,
                "lectura_actual": lectura_actual,
            },
        )
    except Exception:
        pass

    return {
        "id_usuario": id_usuario,
        "nro_medidor": nro_medidor,
        "consumo_total_m3": doc.get("consumo_total_m3"),
    }


# ---------------------------------------------------------------------------
# Fase 4: Generación de Recibos y Facturación del Mes
# ---------------------------------------------------------------------------

def verificar_estado_generacion_recibos(periodo: str | None = None) -> dict[str, Any]:
    """Analiza el estado del mes para determinar si se pueden generar los recibos.

    Retorna un resumen con estadísticas y la lista de medidores pendientes o sin acceso.
    """
    cfg = cargar_config()
    mes_actual = cfg.get("mes_actual") or {}
    periodo_obj = periodo or mes_actual.get("periodo")
    if not periodo_obj:
        return {
            "periodo": None,
            "estado": None,
            "puede_generar": False,
            "motivo": "No hay un mes configurado en el sistema.",
            "faltantes": [],
            "total_usuarios": 0,
            "recibos_generados": 0,
            "total_facturado": 0.0,
            "pagados": 0,
            "pendientes": 0,
        }

    estado_mes = (mes_actual.get("estado") or "ABIERTO").upper()
    docs_mes = cargar_mes(periodo_obj)

    faltantes = []
    recibos_generados = 0
    total_facturado = 0.0
    pagados = 0
    pendientes = 0

    for uid, doc in docs_mes.items():
        meds = doc.get("medidores") or []
        for m in meds:
            act = m.get("lectura_actual")
            st = (m.get("estado_lectura") or "").upper()
            if act is None or st in ("PENDIENTE", "SIN_ACCESO"):
                faltantes.append({
                    "id_usuario": uid,
                    "nro_conexion": doc.get("nro_conexion", ""),
                    "nombre": doc.get("nombre", ""),
                    "sector": doc.get("sector", ""),
                    "nro_medidor": m.get("nro_medidor", ""),
                    "lectura_anterior": m.get("lectura_anterior", 0),
                    "consumo_anterior": m.get("consumo_anterior"),
                    "estado_lectura": st or "PENDIENTE",
                    "novedad": m.get("novedad", ""),
                })

        if doc.get("nro_recibo"):
            recibos_generados += 1
            total = float(doc.get("total_a_pagar") or 0.0)
            pagado_monto = float(doc.get("monto_pagado") or 0.0)
            total_facturado += total
            if pagado_monto >= total and total > 0:
                pagados += 1
            else:
                pendientes += 1

    puede_generar = (len(faltantes) == 0)
    return {
        "periodo": periodo_obj,
        "estado": estado_mes,
        "puede_generar": puede_generar,
        "faltantes": faltantes,
        "total_usuarios": len(docs_mes),
        "recibos_generados": recibos_generados,
        "total_facturado": round(total_facturado, 2),
        "pagados": pagados,
        "pendientes": pendientes,
    }


def estimar_lectura_medidor(
    periodo: str,
    id_usuario: str,
    nro_medidor: str,
    consumo_estimado: int | None = None,
) -> dict[str, Any]:
    """Estima la lectura de un medidor basándose en el consumo anterior o valor manual."""
    doc = obtener_doc_mes(periodo, id_usuario)
    if doc is None:
        raise ValueError(
            f"Usuario {id_usuario} no encontrado en el mes {periodo}.")

    medidor_obj = None
    for m in doc.get("medidores", []):
        if m.get("nro_medidor") == nro_medidor:
            medidor_obj = m
            break
    if medidor_obj is None:
        raise ValueError(
            f"Medidor {nro_medidor} no encontrado en el usuario {id_usuario}.")

    if consumo_estimado is not None:
        consumo = int(consumo_estimado)
    else:
        c_ant = medidor_obj.get("consumo_anterior")
        if c_ant is None:
            raise ValueError(
                f"El medidor {nro_medidor} no tiene consumo anterior registrado. Ingrese un valor manual."
            )
        consumo = int(c_ant)

    l_ant = int(medidor_obj.get("lectura_anterior") or 0)
    lectura_nueva = max(0, l_ant + max(0, consumo))

    return guardar_lectura_medidor(
        periodo=periodo,
        id_usuario=id_usuario,
        nro_medidor=nro_medidor,
        lectura_actual=lectura_nueva,
        novedad="LECTURA_ESTIMADA",
        nota="Estimada por la secretaria",
        registrado_por="ADMIN",
    )


def estimar_todas_lecturas_faltantes(periodo: str) -> dict[str, Any]:
    """Estima automáticamente todas las lecturas pendientes que tengan consumo anterior."""
    estado = verificar_estado_generacion_recibos(periodo)
    estimados = 0
    requieren_manual = []

    for f in estado.get("faltantes", []):
        uid = f["id_usuario"]
        n_med = f["nro_medidor"]
        c_ant = f.get("consumo_anterior")
        if c_ant is not None:
            estimar_lectura_medidor(
                periodo, uid, n_med, consumo_estimado=int(c_ant))
            estimados += 1
        else:
            requieren_manual.append(f)

    return {
        "estimados": estimados,
        "requieren_manual": requieren_manual,
    }


def generar_recibos_mes(periodo: str | None = None) -> dict[str, Any]:
    """Genera los recibos de todo el mes de forma ordenada, calculada e idempotente.

    - Requiere que todas las lecturas estén resueltas (sin PENDIENTE ni SIN_ACCESO).
    - Lee el mes anterior para arrastrar deuda y meses de mora.
    - Numera de forma consecutiva e idempotente según config.ultimo_recibo.
    - Escribe los recibos en lotes de 500 y actualiza mes_actual.estado a FACTURADO.
    """
    import calculos

    cfg = cargar_config()
    mes_actual = cfg.get("mes_actual") or {}
    periodo_obj = periodo or mes_actual.get("periodo")
    if not periodo_obj:
        raise ValueError("No hay un periodo configurado para generar recibos.")

    docs_mes = cargar_mes(periodo_obj)
    if not docs_mes:
        raise ValueError(
            f"No hay registros de usuarios en el mes {periodo_obj}.")

    # 1. Validar que no haya lecturas pendientes
    faltantes = []
    for uid, d in docs_mes.items():
        for m in d.get("medidores", []):
            if m.get("lectura_actual") is None or (m.get("estado_lectura") or "").upper() in ("PENDIENTE", "SIN_ACCESO"):
                faltantes.append(f"{d.get('nombre')} ({m.get('nro_medidor')})")
    if faltantes:
        raise ValueError(
            f"No se pueden generar recibos: existen {len(faltantes)} medidores con lectura pendiente o sin acceso. "
            "Resuélvalos o estímelos antes de facturar."
        )

    # 2. Cargar mes anterior fresco
    cols_prev = [c for c in listar_colecciones_mes() if c < periodo_obj]
    periodo_ant = max(cols_prev) if cols_prev else None
    mes_ant = {}
    if periodo_ant and existe_mes(periodo_ant):
        try:
            mes_ant = cargar_mes(periodo_ant, forzar=True)
        except Exception:
            mes_ant = {}

    # 3. Configuración de cálculo
    ultimo_recibo_num = int(cfg.get("ultimo_recibo") or 0)
    categorias = cfg.get("categorias", {})
    igv_cfg = cfg.get("igv") or {}
    igv_activo = bool(igv_cfg.get("activo", False))
    igv_porcentaje = float(igv_cfg.get("porcentaje", 0.18))
    sectores = cfg.get("sectores") or []

    # Ordenar por sector y luego por nombre
    def orden_clave(item):
        uid, d = item
        sec = str(d.get("sector") or "")
        sec_idx = sectores.index(sec) if sec in sectores else 999
        return (sec_idx, sec, str(d.get("nombre") or "").upper())

    items_ordenados = sorted(docs_mes.items(), key=orden_clave)

    # 4. Procesar y calcular recibos
    documentos_a_guardar = {}
    recibos_generados_ahora = 0
    total_monto_facturado = 0.0

    for uid, doc in items_ordenados:
        # Idempotencia: si ya tiene número de recibo, lo conserva
        if doc.get("nro_recibo"):
            nro_recibo = doc["nro_recibo"]
        else:
            ultimo_recibo_num += 1
            nro_recibo = f"{ultimo_recibo_num:09d}"
            recibos_generados_ahora += 1

        doc["nro_recibo"] = nro_recibo

        # Recibo anterior para arrastrar deuda y meses de mora
        rec_ant = mes_ant.get(uid)
        recibo_ant_dict = None
        if rec_ant:
            tap_ant = float(rec_ant.get("total_a_pagar") or 0.0)
            mp_ant = float(rec_ant.get("monto_pagado") or 0.0)
            m_ant = int(rec_ant.get("meses_adeudados") or 1)
            recibo_ant_dict = {
                "total_a_pagar": tap_ant,
                "monto_pagado": mp_ant,
                "meses_adeudados": m_ant,
            }

        # Categoría tarifaria
        cat_cod = doc.get("codigo_categoria", "A")
        cat_obj = categorias.get(cat_cod) or categorias.get("A", {
            "tarifa_desague": 0.0,
            "cargo_fijo": 1.5,
            "modo_rangos": "unico",
            "rangos": [{"m3_desde": 0, "m3_hasta": None, "precio_m3": 1.0}],
        })

        # Cálculo de recibo
        calc = calculos.calcular_recibo(
            medidores=doc.get("medidores", []),
            categoria=cat_obj,
            igv_activo=igv_activo,
            igv_porcentaje=igv_porcentaje,
            recibo_anterior=recibo_ant_dict,
        )

        doc.update({
            "consumo_total_m3": calc["consumo_total_m3"],
            "monto_agua": calc["monto_agua"],
            "monto_desague": calc["monto_desague"],
            "cargo_fijo": calc["cargo_fijo"],
            "deuda_anterior": calc["deuda_anterior"],
            "igv": calc["igv"],
            "redondeo": calc["redondeo"],
            "total_a_pagar": calc["total_a_pagar"],
            "meses_adeudados": calc["meses_adeudados"],
            "monto_pagado": 0.0,
            "fecha_pago": None,
        })

        total_monto_facturado += calc["total_a_pagar"]
        documentos_a_guardar[uid] = doc

    # 5. Guardar en lotes de 500
    guardar_mes_lote(periodo_obj, documentos_a_guardar)

    # 6. Actualizar config (último recibo y estado del mes)
    actualizar_config_campo("ultimo_recibo", ultimo_recibo_num)
    actualizar_config_campo("mes_actual.estado", "FACTURADO")
    limpiar_cache(limpiar_config=True)

    try:
        from respaldo import on_datos_cambiados
        on_datos_cambiados("generar_recibos", {
            "periodo": periodo_obj,
            "total_documentos": len(documentos_a_guardar),
            "ultimo_recibo": ultimo_recibo_num,
        })
    except Exception:
        pass

    return {
        "periodo": periodo_obj,
        "total_recibos": len(documentos_a_guardar),
        "nuevos_recibos": recibos_generados_ahora,
        "ultimo_recibo": ultimo_recibo_num,
        "total_facturado": round(total_monto_facturado, 2),
    }


def generar_recibo_usuario(periodo: str | None = None, id_usuario: str = "") -> dict[str, Any]:
    """Genera o actualiza el recibo de un único usuario bajo demanda.

    Permite facturar a una persona individualmente en ventanilla sin necesidad
    de cerrar todas las lecturas de todo el pueblo a la vez.
    """
    import calculos

    cfg = cargar_config()
    mes_actual = cfg.get("mes_actual") or {}
    periodo_obj = periodo or mes_actual.get("periodo")
    if not periodo_obj:
        raise ValueError("No hay un periodo configurado para generar recibos.")

    docs_mes = cargar_mes(periodo_obj)
    doc = docs_mes.get(id_usuario)
    if not doc:
        raise ValueError(
            f"Usuario {id_usuario} no encontrado en el mes {periodo_obj}.")

    # Si algún medidor no tiene lectura actual, asegurar lectura anterior (consumo 0) para permitir facturar
    for m in doc.get("medidores", []):
        if m.get("lectura_actual") is None:
            m["lectura_actual"] = m.get("lectura_anterior") or 0
            m["estado_lectura"] = "ESTIMADO"

    # Buscar mes anterior para arrastrar deuda y meses de mora
    cols_prev = [c for c in listar_colecciones_mes() if c < periodo_obj]
    periodo_ant = max(cols_prev) if cols_prev else None
    recibo_ant_dict = None
    if periodo_ant and existe_mes(periodo_ant):
        try:
            mes_ant = cargar_mes(periodo_ant)
            rec_ant = mes_ant.get(id_usuario)
            if rec_ant:
                tap_ant = float(rec_ant.get("total_a_pagar") or 0.0)
                mp_ant = float(rec_ant.get("monto_pagado") or 0.0)
                m_ant = int(rec_ant.get("meses_adeudados") or 1)
                recibo_ant_dict = {
                    "total_a_pagar": tap_ant,
                    "monto_pagado": mp_ant,
                    "meses_adeudados": m_ant,
                }
        except Exception:
            recibo_ant_dict = None

    # Numeración de recibo consecutiva
    ultimo_recibo_num = int(cfg.get("ultimo_recibo") or 0)
    if not doc.get("nro_recibo"):
        ultimo_recibo_num += 1
        doc["nro_recibo"] = f"{ultimo_recibo_num:09d}"
        actualizar_config_campo("ultimo_recibo", ultimo_recibo_num)

    # Configuración tarifaria
    categorias = cfg.get("categorias", {})
    cat_cod = doc.get("codigo_categoria", "A")
    cat_obj = categorias.get(cat_cod) or categorias.get("A", {
        "tarifa_desague": 0.0,
        "cargo_fijo": 1.5,
        "modo_rangos": "unico",
        "rangos": [{"m3_desde": 0, "m3_hasta": None, "precio_m3": 1.0}],
    })
    igv_cfg = cfg.get("igv") or {}
    igv_activo = bool(igv_cfg.get("activo", False))
    igv_porcentaje = float(igv_cfg.get("porcentaje", 0.18))

    calc = calculos.calcular_recibo(
        medidores=doc.get("medidores", []),
        categoria=cat_obj,
        igv_activo=igv_activo,
        igv_porcentaje=igv_porcentaje,
        recibo_anterior=recibo_ant_dict,
    )

    doc.update({
        "consumo_total_m3": calc["consumo_total_m3"],
        "monto_agua": calc["monto_agua"],
        "monto_desague": calc["monto_desague"],
        "cargo_fijo": calc["cargo_fijo"],
        "deuda_anterior": calc["deuda_anterior"],
        "igv": calc["igv"],
        "redondeo": calc["redondeo"],
        "total_a_pagar": calc["total_a_pagar"],
        "meses_adeudados": calc["meses_adeudados"],
    })
    if "monto_pagado" not in doc or doc.get("monto_pagado") is None:
        doc["monto_pagado"] = 0.0
        doc["fecha_pago"] = None

    # Guardar documento individual en Firestore
    db = _get_db()
    db.collection(f"mes_{periodo_obj}").document(id_usuario).set(doc)
    _contar("escrituras", 1)

    # Actualizar copia en memoria
    if _cache.get("mes") and id_usuario in _cache["mes"]:
        _cache["mes"][id_usuario] = doc

    try:
        from respaldo import on_datos_cambiados
        on_datos_cambiados("generar_recibo_individual", {
            "periodo": periodo_obj,
            "id_usuario": id_usuario,
            "nro_recibo": doc["nro_recibo"],
        })
    except Exception:
        pass

    return doc


# ---------------------------------------------------------------------------
# Cobros, Pagos y Reporte de Morosos (Fase 5)
# ---------------------------------------------------------------------------

def registrar_pago(
    periodo: str,
    id_usuario: str,
    monto_pagado: float,
    fecha_pago: Optional[str] = None,
) -> Dict[str, Any]:
    """Registra el pago (total o parcial) de un recibo en el mes especificado.

    - monto_pagado: float >= 0.
    - fecha_pago: YYYY-MM-DD (por defecto hoy).
    Actualiza 1 documento en Firestore e incrementa el contador de escrituras en 1.
    Actualiza la copia en memoria y notifica on_datos_cambiados().
    """
    import datetime
    db = _get_db()
    periodo = periodo.strip()
    id_usuario = id_usuario.strip()

    fecha = fecha_pago or datetime.date.today().isoformat()
    monto = round(float(monto_pagado), 2)

    doc_ref = db.collection(f"mes_{periodo}").document(id_usuario)
    doc_snap = doc_ref.get()
    _contar("lecturas", 1)

    if not doc_snap.exists:
        raise ValueError(
            f"No existe el usuario {id_usuario} en el mes {periodo}.")

    datos_actuales = doc_snap.to_dict() or {}

    cambios = {
        "monto_pagado": monto,
        "fecha_pago": fecha,
    }
    doc_ref.update(cambios)
    _contar("escrituras", 1)

    # Actualizar cache en memoria
    if _cache["mes"] is not None and _cache.get("periodo_cargado") == periodo:
        if id_usuario in _cache["mes"]:
            _cache["mes"][id_usuario].update(cambios)

    try:
        from respaldo import on_datos_cambiados
        on_datos_cambiados("pago", {
            "periodo": periodo,
            "id_usuario": id_usuario,
            "monto_pagado": monto,
            "fecha_pago": fecha,
        })
    except Exception:
        pass

    datos_actuales.update(cambios)
    return datos_actuales


def anular_pago(periodo: str, id_usuario: str) -> Dict[str, Any]:
    """Anula el pago registrado de un usuario (monto_pagado = 0, fecha_pago = None)."""
    db = _get_db()
    periodo = periodo.strip()
    id_usuario = id_usuario.strip()

    doc_ref = db.collection(f"mes_{periodo}").document(id_usuario)
    doc_snap = doc_ref.get()
    _contar("lecturas", 1)

    if not doc_snap.exists:
        raise ValueError(
            f"No existe el usuario {id_usuario} en el mes {periodo}.")

    datos_actuales = doc_snap.to_dict() or {}

    cambios = {
        "monto_pagado": 0.0,
        "fecha_pago": None,
    }
    doc_ref.update(cambios)
    _contar("escrituras", 1)

    # Actualizar cache en memoria
    if _cache["mes"] is not None and _cache.get("periodo_cargado") == periodo:
        if id_usuario in _cache["mes"]:
            _cache["mes"][id_usuario].update(cambios)

    try:
        from respaldo import on_datos_cambiados
        on_datos_cambiados("anular_pago", {
            "periodo": periodo,
            "id_usuario": id_usuario,
        })
    except Exception:
        pass

    datos_actuales.update(cambios)
    return datos_actuales


def exportar_reporte_morosos_excel(
    periodo: Optional[str] = None,
    ruta_salida: Optional[str] = None,
) -> str:
    """Exporta el reporte de morosos y la lista de corte a un archivo Excel formateado."""
    import openpyxl
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    cfg = cargar_config()
    periodo_obj = periodo or (cfg.get("mes_actual") or {}).get(
        "periodo") or "2026-10"
    docs = cargar_mes(periodo_obj)
    sectores = cfg.get("sectores") or []

    wb = openpyxl.Workbook()
    # Hoja 1: Lista de Corte
    ws_corte = wb.active
    ws_corte.title = "Lista de Corte (3+ Meses)"

    # Hoja 2: Todos los Morosos
    ws_morosos = wb.create_sheet(title="Todos los Morosos")

    # Hoja 3: Resumen
    ws_resumen = wb.create_sheet(title="Resumen Cobranza")

    # Estilos
    fuente_titulo = Font(name="Arial", size=13, bold=True, color="1E293B")
    fuente_sub = Font(name="Arial", size=10, italic=True, color="64748B")
    fuente_encabezado_rojo = Font(
        name="Arial", size=10, bold=True, color="FFFFFF")
    fill_rojo = PatternFill(start_color="DC2626",
                            end_color="DC2626", fill_type="solid")

    fuente_encabezado_azul = Font(
        name="Arial", size=10, bold=True, color="FFFFFF")
    fill_azul = PatternFill(start_color="1E3A8A",
                            end_color="1E3A8A", fill_type="solid")

    borde_fino = Border(
        left=Side(style="thin", color="CBD5E1"),
        right=Side(style="thin", color="CBD5E1"),
        top=Side(style="thin", color="CBD5E1"),
        bottom=Side(style="thin", color="CBD5E1"),
    )

    # 1. Hoja Lista de Corte
    ws_corte.merge_cells("A1:G1")
    ws_corte[
        "A1"] = f"CAAPD ISPACAS — USUARIOS EN LISTA DE CORTE (3 O MÁS MESES) — PERIODO {periodo_obj}"
    ws_corte["A1"].font = fuente_titulo
    ws_corte["A1"].alignment = Alignment(vertical="center")

    encabezados_corte = [
        "N° Conexión", "N° Recibo", "Titular / Usuario", "Sector", "Dirección",
        "Meses Adeudados", "Total Adeudado (S/.)"
    ]
    for col_idx, enc in enumerate(encabezados_corte, start=1):
        cell = ws_corte.cell(row=3, column=col_idx, value=enc)
        cell.font = fuente_encabezado_rojo
        cell.fill = fill_rojo
        cell.alignment = Alignment(
            horizontal="center", vertical="center", wrap_text=True)

    # 2. Hoja Todos los Morosos
    ws_morosos.merge_cells("A1:H1")
    ws_morosos["A1"] = f"CAAPD ISPACAS — PADRÓN GENERAL DE MOROSIDAD — PERIODO {periodo_obj}"
    ws_morosos["A1"].font = fuente_titulo
    ws_morosos["A1"].alignment = Alignment(vertical="center")

    encabezados_morosos = [
        "N° Conexión", "N° Recibo", "Titular / Usuario", "Sector", "Dirección",
        "Meses Adeudados", "Nivel de Mora", "Saldo Pendiente (S/.)"
    ]
    for col_idx, enc in enumerate(encabezados_morosos, start=1):
        cell = ws_morosos.cell(row=3, column=col_idx, value=enc)
        cell.font = fuente_encabezado_azul
        cell.fill = fill_azul
        cell.alignment = Alignment(
            horizontal="center", vertical="center", wrap_text=True)

    def orden_sec(item):
        d = item[1]
        sec = str(d.get("sector") or "")
        s_idx = sectores.index(sec) if sec in sectores else 999
        return (s_idx, sec, str(d.get("nombre") or "").upper())

    items_ord = sorted(docs.items(), key=orden_sec)

    fila_corte = 4
    fila_morosos = 4

    tot_recibos = 0
    tot_pagados = 0
    tot_pendientes = 0
    tot_facturado = 0.0
    tot_recaudado = 0.0
    tot_saldo_pendiente = 0.0
    cnt_corte = 0
    cnt_dos_meses = 0
    cnt_al_dia = 0

    for uid, d in items_ord:
        tot_recibos += 1
        tot_a_pagar = float(d.get("total_a_pagar") or 0.0)
        m_pagado = float(d.get("monto_pagado") or 0.0)
        saldo = max(0.0, round(tot_a_pagar - m_pagado, 2))
        meses = int(d.get("meses_adeudados") or 1)

        tot_facturado += tot_a_pagar
        tot_recaudado += m_pagado

        if saldo <= 0.0 and tot_a_pagar > 0:
            tot_pagados += 1
        else:
            tot_pendientes += 1
            tot_saldo_pendiente += saldo

            # Nivel de mora
            if meses >= 3:
                nivel_str = "Corte (3+ m.)"
                cnt_corte += 1
                # Escribir en hoja de corte
                ws_corte.cell(row=fila_corte, column=1, value=str(
                    d.get("nro_conexion") or "")).border = borde_fino
                ws_corte.cell(row=fila_corte, column=2, value=str(
                    d.get("nro_recibo") or "-")).border = borde_fino
                ws_corte.cell(row=fila_corte, column=3, value=str(
                    d.get("nombre") or "")).border = borde_fino
                ws_corte.cell(row=fila_corte, column=4, value=str(
                    d.get("sector") or "")).border = borde_fino
                ws_corte.cell(row=fila_corte, column=5, value=str(
                    d.get("direccion") or "")).border = borde_fino
                c_m = ws_corte.cell(row=fila_corte, column=6, value=meses)
                c_m.alignment = Alignment(horizontal="center")
                c_m.border = borde_fino
                c_tot = ws_corte.cell(row=fila_corte, column=7, value=saldo)
                c_tot.number_format = '"S/. "#,##0.00'
                c_tot.border = borde_fino
                fila_corte += 1
            elif meses == 2:
                nivel_str = "2 Meses"
                cnt_dos_meses += 1
            else:
                nivel_str = "Al Día (1 m.)"
                cnt_al_dia += 1

            # Escribir en hoja de morosos
            ws_morosos.cell(row=fila_morosos, column=1, value=str(
                d.get("nro_conexion") or "")).border = borde_fino
            ws_morosos.cell(row=fila_morosos, column=2, value=str(
                d.get("nro_recibo") or "-")).border = borde_fino
            ws_morosos.cell(row=fila_morosos, column=3, value=str(
                d.get("nombre") or "")).border = borde_fino
            ws_morosos.cell(row=fila_morosos, column=4, value=str(
                d.get("sector") or "")).border = borde_fino
            ws_morosos.cell(row=fila_morosos, column=5, value=str(
                d.get("direccion") or "")).border = borde_fino
            c_m2 = ws_morosos.cell(row=fila_morosos, column=6, value=meses)
            c_m2.alignment = Alignment(horizontal="center")
            c_m2.border = borde_fino
            c_niv = ws_morosos.cell(
                row=fila_morosos, column=7, value=nivel_str)
            c_niv.alignment = Alignment(horizontal="center")
            c_niv.border = borde_fino
            c_sal = ws_morosos.cell(row=fila_morosos, column=8, value=saldo)
            c_sal.number_format = '"S/. "#,##0.00'
            c_sal.border = borde_fino
            fila_morosos += 1

    # 3. Hoja Resumen
    ws_resumen.column_dimensions["A"].width = 35
    ws_resumen.column_dimensions["B"].width = 25
    ws_resumen["A1"] = f"RESUMEN DE RECAUDACIÓN — PERIODO {periodo_obj}"
    ws_resumen["A1"].font = fuente_titulo

    resumen_data = [
        ("Total Usuarios / Recibos", tot_recibos, False),
        ("Recibos Pagados", tot_pagados, False),
        ("Recibos Pendientes de Pago", tot_pendientes, False),
        ("Efectividad de Cobro (%)", round(
            (tot_pagados / tot_recibos * 100), 1) if tot_recibos else 0.0, False),
        ("Total Facturado (S/.)", tot_facturado, True),
        ("Total Recaudado (S/.)", tot_recaudado, True),
        ("Saldo por Cobrar (S/.)", tot_saldo_pendiente, True),
        ("Usuarios en Lista de Corte (3+ meses)", cnt_corte, False),
        ("Usuarios con 2 Meses de Adeudo", cnt_dos_meses, False),
        ("Usuarios con 1 Mes de Adeudo", cnt_al_dia, False),
    ]

    for idx, (label, val, es_monto) in enumerate(resumen_data, start=3):
        c_lbl = ws_resumen.cell(row=idx, column=1, value=label)
        c_lbl.font = Font(name="Arial", size=10, bold=True)
        c_lbl.border = borde_fino
        c_v = ws_resumen.cell(row=idx, column=2, value=val)
        c_v.border = borde_fino
        if es_monto:
            c_v.number_format = '"S/. "#,##0.00'

    # Ajustar anchos
    for ws in (ws_corte, ws_morosos):
        for col in ws.columns:
            letra = get_column_letter(col[0].column)
            max_len = max(len(str(c.value or "")) for c in col)
            ws.column_dimensions[letra].width = max(max_len + 3, 12)

    # Ruta de destino
    if ruta_salida:
        p_salida = Path(ruta_salida)
    else:
        p_salida = rutas.ruta_salida(f"reporte_morosos_{periodo_obj}.xlsx")
    p_salida.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(p_salida))
    return str(p_salida)
