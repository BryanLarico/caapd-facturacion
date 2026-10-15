"""
codigos.py — Normalización de identificadores y búsqueda inteligente.

Reglas del sistema CAAPD Ispacas (definidas en docs/CONTEXTO.md y docs/MER_CAAPD_Ispacas_v2.xlsx):
- Medidores: mínimo 6 dígitos con ceros a la izquierda.
- Conexión: mínimo 6 dígitos con ceros a la izquierda.
- DNI / id_usuario: 8 dígitos con ceros a la izquierda si son 7 dígitos.
- Recibo: 9 dígitos con ceros a la izquierda.
- ID pendiente: cualquier id_usuario que contenga un guion ('-' ej. 07654321-1, SD-001).
- Búsqueda inteligente: un solo cuadro de búsqueda para medidor, conexión, DNI y nombre.
"""

from __future__ import annotations
import re
import unicodedata
from typing import Any


def limpiar_texto(valor: Any) -> str:
    """Convierte a string, elimina sufijos decimales flotantes y espacios."""
    if valor is None:
        return ""
    s = str(valor).strip()
    if s.endswith(".0"):
        s = s[:-2].strip()
    return s


def completar_ceros(valor: Any, minimo: int) -> str:
    """Si el valor son solo dígitos y tiene menos que `minimo`, completa con ceros.

    Si tiene el mínimo o más, o no son solo dígitos, lo devuelve limpio sin modificar.
    """
    s = limpiar_texto(valor)
    if s.isdigit() and len(s) < minimo:
        return s.zfill(minimo)
    return s


def normalizar_medidor(valor: Any) -> str:
    """Devuelve el número de medidor normalizado a mínimo 6 dígitos.

    Si ya tiene 6 o más dígitos, se respeta tal cual.
    Ejemplos:
        100      → '000100'
        3200     → '003200'
        990991   → '990991'
        123456   → '123456'
        22392996 → '22392996'
    """
    return completar_ceros(valor, 6)


def normalizar_conexion(valor: Any, longitud: int = 6) -> str:
    """Devuelve el número de conexión con mínimo 6 dígitos con ceros."""
    return completar_ceros(valor, longitud)


def normalizar_dni(valor: Any) -> str:
    """Devuelve el DNI con 8 dígitos (agrega cero al frente si tiene 7).

    Si tiene 8 o 9 dígitos se respeta sin modificar.
    """
    return completar_ceros(valor, 8)


def normalizar_recibo(valor: Any) -> str:
    """Devuelve el número de recibo con 9 dígitos."""
    return completar_ceros(valor, 9)


def generar_id_usuario(
    dni: Any,
    contador_sin_dni: int | None = None,
    sufijo: int | None = None,
) -> str:
    """Genera el id_usuario según las reglas del padrón.

    Casos:
        - DNI con 7 u 8 dígitos, único → '07654321'
        - DNI compartido (sufijo 1, 2, ...) → '07654321-1'
        - Sin DNI → 'SD-001', 'SD-002', ...
    """
    s = limpiar_texto(dni)
    if not s:
        if contador_sin_dni is None:
            raise ValueError("Se requiere contador_sin_dni para usuarios sin DNI.")
        return f"SD-{contador_sin_dni:03d}"
    dni_norm = normalizar_dni(s)
    if sufijo is not None:
        return f"{dni_norm}-{sufijo}"
    return dni_norm


def es_id_pendiente(id_usuario: str) -> bool:
    """Devuelve True si el id_usuario contiene un guion (pendiente de pedir DNI)."""
    return "-" in limpiar_texto(id_usuario)


def quitar_tildes(texto: str) -> str:
    """Elimina acentos y diacríticos de un texto."""
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def buscar(consulta: str, registros: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Búsqueda inteligente según la tabla de la sección 4 de CONTEXTO.md.

    Reglas:
    1. Si la consulta son solo dígitos:
       - Si tiene MENOS dígitos que el mínimo del campo:
         Buscar primero coincidencia exacta completando ceros (medidor a 6, conexión a 6, DNI a 8).
         Luego buscar aquellos donde el campo contenga los dígitos ingresados.
       - Si tiene el mínimo o más dígitos:
         Buscar tal cual sin agregar ceros extras.
       Aplica a:
         * Medidores asociados al usuario (lista medidores o medidores[] con nro_medidor).
         * Número de conexión (nro_conexion).
         * ID / DNI del usuario (id_usuario o _id).
    2. Si tiene letras / caracteres no solo dígitos:
       - Buscar en 'nombre', sin distinguir mayúsculas ni tildes, exigiendo que
         todas las palabras de la consulta estén presentes en cualquier orden.
       - Si la consulta tiene guion (ej. 'SD-001'), buscar también en id_usuario.

    Prioridad de ordenamiento:
       0: Coincidencia exacta con ceros completados en medidor, conexión o ID/DNI.
       1: Coincidencia que contenga la subcadena en medidor, conexión o ID/DNI.
       2: Coincidencia por nombre (orden alfabético por nombre).
    """
    q_limpia = limpiar_texto(consulta)
    if not q_limpia:
        return list(registros)

    def extraer_medidores(reg: dict[str, Any]) -> list[str]:
        raw = reg.get("medidores", [])
        resultado = []
        for m in raw:
            if isinstance(m, dict):
                nro = limpiar_texto(m.get("nro_medidor"))
            else:
                nro = limpiar_texto(m)
            if nro:
                resultado.append(nro)
        return resultado

    def extraer_id(reg: dict[str, Any]) -> str:
        return limpiar_texto(reg.get("id_usuario") or reg.get("_id") or reg.get("dni"))

    def extraer_conexion(reg: dict[str, Any]) -> str:
        return limpiar_texto(reg.get("nro_conexion"))

    def extraer_nombre(reg: dict[str, Any]) -> str:
        return reg.get("nombre") or reg.get("beneficiario") or ""

    if q_limpia.isdigit():
        len_q = len(q_limpia)
        target_medidor = q_limpia.zfill(6) if len_q < 6 else q_limpia
        target_conexion = q_limpia.zfill(6) if len_q < 6 else q_limpia
        target_dni = q_limpia.zfill(8) if len_q < 8 else q_limpia

        prioridad_0 = []  # Exacto con ceros completados
        prioridad_1 = []  # Contiene subcadena
        ids_vistos = set()

        for reg in registros:
            reg_id = extraer_id(reg)
            medidores = extraer_medidores(reg)
            conexion = extraer_conexion(reg)

            # 1. Coincidencia exacta
            es_exacto = (
                any(m == target_medidor for m in medidores)
                or conexion == target_conexion
                or reg_id == target_dni
            )
            if es_exacto:
                prioridad_0.append(reg)
                ids_vistos.add(id(reg))
                continue

            # 2. Contiene los dígitos
            contiene = (
                any(q_limpia in m for m in medidores)
                or (q_limpia in conexion)
                or (q_limpia in reg_id)
            )
            if contiene:
                prioridad_1.append(reg)
                ids_vistos.add(id(reg))

        return prioridad_0 + prioridad_1

    # Búsqueda por texto (nombre o ID con guion)
    palabras_q = [quitar_tildes(p).lower() for p in q_limpia.split() if p]
    q_normalizada = quitar_tildes(q_limpia).lower()

    exactos = []
    parciales = []

    for reg in registros:
        reg_id = extraer_id(reg).lower()
        if reg_id == q_limpia.lower():
            exactos.append(reg)
            continue
        elif q_limpia.lower() in reg_id:
            parciales.append(reg)
            continue

        nombre_orig = extraer_nombre(reg)
        nombre_norm = quitar_tildes(nombre_orig).lower()

        # Todas las palabras de la consulta deben estar en el nombre
        if all(p in nombre_norm for p in palabras_q):
            parciales.append(reg)

    return exactos + parciales
