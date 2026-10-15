# ESCRITORIO D8 — Elegir una versión y eliminar la otra

**Úsalo solo cuando ya comparaste las dos versiones.** Antes de pegar nada, decide con esta lista (marca cuál gana en cada punto):

| Criterio | HTML | Escritorio |
|---|---|---|
| Rapidez al abrir y al cambiar de pantalla | | |
| Fluidez con la tabla de usuarios y la búsqueda | | |
| Diseño y comodidad para la secretaria | | |
| No depender de un servidor ni de un navegador abierto | | |
| Instalación y actualización en su PC | | |
| Facilidad para que tú cambies el diseño | | |

## Opción A — Me quedo con ESCRITORIO

**Antigravity:** conversación nueva, modo Planning:
`Lee docs/CONTEXTO.md y ejecuta docs/ESCRITORIO_D8_CONSOLIDAR.md, Opción A.`

1. **Respaldo de seguridad primero:** un `.zip` del proyecto (sin `venv`) en `respaldos/proyecto_antes_de_consolidar.zip`.
2. **Plan de limpieza:** lista exacta de lo que se elimina (`app.py`, `templates/`, `static/`, `iniciar.bat` de la raíz, Flask y Jinja2 de los requisitos, el `venv` antiguo) y de lo que se mueve. **Espera mi confirmación explícita antes de borrar.**
3. **Reorganizar:** deja una sola estructura. Las carpetas `escritorio/*` pasan a ser la raíz del programa junto a la lógica compartida (`firebase_client`, `calculos`, `codigos`, `respaldo`, `scripts`, `tests`). Corrige todos los imports y `rutas.py` (sin `sys.path` hacia la carpeta anterior).
4. Un solo `requirements.txt` y un solo `pytest.ini`. `python main.py` abre la aplicación.
5. Actualiza `docs/CONTEXTO.md` (sin la convivencia de interfaces), borra `INTERFAZ_HTML.md` y deja `INTERFAZ_ESCRITORIO.md` como único documento de interfaz. Actualiza el README.
6. Pasa toda la suite de pruebas y confirma que la aplicación abre.
7. Después continúa con las Fases 3 a 6 y la Fase 7 (instalador).

## Opción B — Me quedo con HTML

`Lee docs/CONTEXTO.md y ejecuta docs/ESCRITORIO_D8_CONSOLIDAR.md, Opción B.`

1. Respaldo `.zip` de seguridad (sin `venv`).
2. Plan de limpieza: se elimina la carpeta `escritorio/` completa y `docs/ESCRITORIO_*.md` y `docs/INTERFAZ_ESCRITORIO.md`. **Espera mi confirmación antes de borrar.**
3. Actualiza `docs/CONTEXTO.md` (solo HTML) y corrige en `inicio.html` la lógica de botones según CONTEXTO §3b.
4. Pasa las pruebas y confirma que `iniciar.bat` abre la aplicación.
5. Continúa con las Fases 3 a 6 en HTML (la Fase 7 no aplica).
