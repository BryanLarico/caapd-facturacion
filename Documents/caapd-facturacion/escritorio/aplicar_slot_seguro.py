"""Script de un solo uso: agrega @slot_seguro a los slots conectados a Workers."""
from __future__ import annotations

import re
from pathlib import Path

BASE = Path(__file__).resolve().parent

OBJETIVOS = {
    "ui/paginas/lecturas.py": [
        "_al_terminar_subida", "_al_terminar_publicacion_mes_actual",
        "_al_terminar_descarga", "_al_fallar_sincronizacion",
        "_al_recibir_datos", "_al_fallar_carga", "_al_finalizar_carga",
    ],
    "ui/paginas/inicio.py": [
        "_al_terminar_subida", "_al_terminar_descarga",
        "_al_fallar_sincronizacion", "_al_recibir_datos",
        "_al_fallar_carga", "_al_finalizar_carga",
    ],
    "ui/paginas/lectores.py": ["_al_recibir_datos", "_al_fallar_carga"],
    "ui/paginas/cobros.py": ["_al_recibir_datos", "_al_fallar_carga"],
    "ui/paginas/usuarios.py": ["_al_recibir_datos", "_al_fallar_carga"],
    "ui/paginas/configuracion.py": ["_al_recibir_datos", "_al_fallar_carga"],
    "ui/paginas/mes_dialogo.py": [
        "_al_exito_apertura", "_al_error_apertura", "_al_finalizar_tarea",
    ],
    "ui/ventana_principal.py": [
        "_al_recibir_metricas", "_al_terminar_metricas",
        "_verificar_archivos_externos", "_al_terminar_recarga_externa",
        "_al_fallar_recarga_externa", "_mostrar_progreso_ui",
        "_ocultar_progreso_ui", "_limpiar_progreso",
    ],
}


def procesar(ruta_rel: str, nombres: list[str]) -> None:
    ruta = BASE / ruta_rel
    texto = ruta.read_text(encoding="utf-8")
    original = texto

    # 1. Importar slot_seguro desde ui.hilos.
    if "slot_seguro" not in texto.split("\n\n")[0] and "slot_seguro," not in texto:
        m = re.search(r"^from ui\.hilos import (.+)$", texto, flags=re.MULTILINE)
        if m and "slot_seguro" not in m.group(1):
            piezas = sorted({p.strip() for p in m.group(1).split(",")} | {"slot_seguro"})
            texto = texto[:m.start()] + "from ui.hilos import " + ", ".join(piezas) + texto[m.end():]
        elif not m:
            raise SystemExit(f"{ruta_rel}: no se encontró el import de ui.hilos")

    # 2. Insertar el decorador justo encima de cada def (debajo de @Slot si existe).
    agregados = []
    for nombre in nombres:
        patron = re.compile(
            r"(?P<indent>[ \t]*)def " + re.escape(nombre) + r"\(", re.MULTILINE
        )
        m = patron.search(texto)
        if not m:
            raise SystemExit(f"{ruta_rel}: no se encontró def {nombre}(")
        inicio_linea = texto.rfind("\n", 0, m.start()) + 1
        previo = texto[:inicio_linea]
        if previo.rstrip(" \t").endswith("@slot_seguro"):
            continue
        indent = m.group("indent")
        texto = previo + f"{indent}@slot_seguro\n" + texto[inicio_linea:]
        agregados.append(nombre)

    if texto != original:
        ruta.write_text(texto, encoding="utf-8")
    print(f"{ruta_rel}: {len(agregados)} slot(s) protegidos -> {', '.join(agregados) or 'ninguno'}")


for rel, nombres_fn in OBJETIVOS.items():
    procesar(rel, nombres_fn)
