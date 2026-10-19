"""
aplicar_parche_lecturas.py — Reemplaza el método traer_lecturas_de_lectores en
servicios/datos_padron.py por la versión REST (sin gRPC). Hace copia de seguridad.
Ejecutar desde la carpeta escritorio/:   python aplicar_parche_lecturas.py
"""
import ast
import shutil
from pathlib import Path

RUTA = Path(__file__).resolve().parent / "servicios" / "datos_padron.py"

NUEVO_METODO = '''    def traer_lecturas_de_lectores(
        self,
        periodo: Optional[str] = None,
        callback_progreso: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Acción B: ExExtraer lecturas de los lectores (Nube -> Excel).
        Descarga por la API REST de Firestore (servicios/firestore_rest.py), NO por gRPC.
        La versión anterior usaba `col.select([...]).stream()`, que en Windows podía
        colgarse dentro de gRPC y cerrar el proceso con un «access violation».
        La fusión con el Excel local la hace `fusionar_lecturas_nube`.
        """
        import time
        from servicios import firestore_rest

        t_inicio = time.perf_counter()
        p = periodo or self.periodo

        if callback_progreso:
            callback_progreso(10, "Autenticando con Firebase (API REST, sin gRPC)...")

        total_docs_locales = max(1, len(self.mes))

        def _progreso_descarga(n_recibidos: int, texto: str) -> None:
            if not callback_progreso:
                return
            pct = 20 + int(min(n_recibidos, total_docs_locales) / total_docs_locales * 50)
            callback_progreso(min(pct, 70), texto)

        if callback_progreso:
            callback_progreso(
                20,
                "Conectando con Firebase; cada petición tiene un límite de "
                f"{int(firestore_rest.TIMEOUT_LECTURA_S)} segundos...",
            )

        # 1. Descarga completa (paginada) por REST. Lanza excepción clara si falla.
        docs_nube = firestore_rest.descargar_documentos_mes(
            p,
            campos=("medidores", "nombre"),
            callback_progreso=_progreso_descarga,
        )
        docs_recibidos = len(docs_nube)
        self.ops["lecturas"] += docs_recibidos

        # 2. Fusión en memoria con protección ADMIN y recálculo de consumos.
        if callback_progreso:
            callback_progreso(75, f"Consolidando {docs_recibidos} documento(s) con el padrón local...")
        actualizados, conflictos_admin = fusionar_lecturas_nube(docs_nube, self.mes)

        # 3. Guardar en Excel local
        if callback_progreso:
            callback_progreso(
                85,
                f"Descarga completa ({docs_recibidos} documentos). Guardando el Excel local...",
            )
        ahora_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.config["ultima_descarga_lectores"] = ahora_str
        self.guardar_en_respaldo_local()

        duracion = time.perf_counter() - t_inicio
        if callback_progreso:
            callback_progreso(100, f"¡{actualizados} lectura(s) descargadas en {duracion:.2f} s!")

        return {
            "periodo": p,
            "documentos_descargados": docs_recibidos,
            "actualizados": actualizados,
            "conflictos_admin": conflictos_admin,
            "tiempo_segundos": round(duracion, 2),
            "metodo": "REST",
            "exito": True,
        }

'''


def main() -> None:
    texto = RUTA.read_text(encoding="utf-8")

    # 1. El archivo original debe compilar (si no, restaurarlo primero).
    try:
        ast.parse(texto)
    except SyntaxError as e:
        raise SystemExit(
            f"ERROR: {RUTA.name} tiene errores de sintaxis (línea {e.lineno}). "
            "Restaura el archivo original (git checkout o desde el zip) y vuelve a ejecutar."
        )

    inicio = texto.find("    def traer_lecturas_de_lectores(")
    fin = texto.find("    def sincronizar_desde_firebase(")
    if inicio == -1 or fin == -1 or fin < inicio:
        raise SystemExit(
            "ERROR: no se encontraron los límites del método. ¿Es el archivo correcto?")

    if "firestore_rest" in texto[inicio:fin]:
        print("El parche ya estaba aplicado. No se hizo nada.")
        return

    # 2. Copia de seguridad.
    respaldo = RUTA.with_suffix(".py.bak_antes_parche")
    shutil.copy2(RUTA, respaldo)

    # 3. Reemplazar SOLO el método.
    nuevo_texto = texto[:inicio] + NUEVO_METODO + texto[fin:]
    ast.parse(nuevo_texto)  # garantiza que el resultado compila
    RUTA.write_text(nuevo_texto, encoding="utf-8")

    print(f"Parche aplicado correctamente a {RUTA}")
    print(f"Copia de seguridad: {respaldo}")


if __name__ == "__main__":
    main()
