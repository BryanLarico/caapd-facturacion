"""
scripts/descargar_iconos.py — Descarga los íconos Tabler (outline) que usa la
aplicación a `recursos/iconos/`. Ejecutar una sola vez (o cuando se agregue
un ícono nuevo a la lista).

    cd escritorio
    python scripts/descargar_iconos.py

Tabler Icons — https://tabler.io/icons — Licencia MIT.
"""
from pathlib import Path
import sys
import urllib.request

RAIZ = Path(__file__).resolve().parents[1]
DESTINO = RAIZ / "recursos" / "iconos"
BASE_URL = "https://raw.githubusercontent.com/tabler/tabler-icons/main/icons/outline/{}.svg"

ICONOS = [
    # Navegación
    "home", "user", "chart-bar", "device-mobile", "coins", "settings", "droplet", "database",
    # Acciones
    "refresh", "lock", "lock-open", "receipt", "calendar-plus", "folder-open", "folder",
    "search", "credit-card", "printer", "device-floppy", "download", "upload",
    "plus", "edit", "trash", "eye", "file-text", "clock",
    # Estados / mensajes
    "circle-check", "circle-x", "info-circle", "alert-triangle", "alert-octagon",
    "check", "x", "wifi-off", "arrow-back-up",
]


def main() -> int:
    DESTINO.mkdir(parents=True, exist_ok=True)
    errores = 0
    for nombre in ICONOS:
        destino = DESTINO / f"{nombre}.svg"
        if destino.exists():
            continue
        try:
            urllib.request.urlretrieve(BASE_URL.format(nombre), destino)
            print(f"  ok  {nombre}")
        except Exception as e:  # noqa: BLE001
            errores += 1
            print(f"  ERROR {nombre}: {e}")
    print(f"Listo. {len(ICONOS) - errores} íconos en {DESTINO}")
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main())
