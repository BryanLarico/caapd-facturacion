# INTERFAZ DE ESCRITORIO (PySide6) — convenciones

> Léelo solo si trabajas en `escritorio/`. **Es un proyecto aparte dentro de la misma carpeta.** Si luego se descarta, se borra `escritorio/` y no pasa nada con la versión HTML.

## Reglas de convivencia
- Trabaja **solo dentro de `escritorio/`**. No modifiques `app.py`, `templates/`, `static/`, `iniciar.bat`, `config_local.py` ni ningún archivo de la raíz.
- **Reutiliza la lógica compartida de la raíz sin copiarla**: `firebase_client`, `calculos`, `codigos`, `respaldo`, `config_local`. `escritorio/rutas.py` agrega la raíz del proyecto a `sys.path`. No importes nada de `app.py` (es de Flask): si necesitas una lógica que hoy está dentro de una ruta de `app.py`, escríbela de nuevo como función pura en `escritorio/servicios/` con pruebas.
- Entorno propio: `escritorio/venv`, `escritorio/requirements.txt` y `escritorio/pytest.ini` (con `pythonpath = . ..`). Así la versión HTML no se afecta.
- Si necesitas un cambio en la lógica compartida, **no lo hagas**: propónmelo en el resumen (o se hace en la Fase 1D).

## Estructura
```
escritorio/
  main.py   rutas.py   iniciar.bat   requirements.txt   pytest.ini   RENDIMIENTO.md
  servicios/    lógica de pantalla sin Qt (estadísticas de Inicio, filtros, validaciones) con pruebas
  ui/
    ventana_principal.py
    paginas/    inicio.py  usuarios.py  lecturas.py  recibos.py  cobros.py  configuracion.py
    componentes/  tarjeta, tabla_filtrable, alerta, barra_progreso, indicador_carga, mensajes
    hilos.py
    estilos/    paleta.py  tema.qss  fuentes/
  tests/
```

## Diseño: igual al HTML, pero intercambiable
- Copia la apariencia de `static/css/estilo.css`, `templates/base.html` y las capturas de `docs/capturas/html/`: barra superior azul, fondo celeste claro, tarjetas redondeadas con sombra suave, tarjetas de estadísticas con degradado (azul, verde, naranja), alertas con borde de color, mismos íconos (emoji, con la fuente Segoe UI Emoji) y misma tipografía. Si el CSS usa una fuente web (por ejemplo Inter), empaquétala en `ui/estilos/fuentes/` si su licencia lo permite, o usa Segoe UI.
- **Todo el aspecto** en `paleta.py` (colores, radios, tamaños, fuentes) y `tema.qss` (hoja de estilos de Qt, muy parecida a CSS). Ningún color ni tamaño suelto en el código de las pantallas: usa `objectName` o propiedades dinámicas.
- Así el diseño se cambia después editando esos dos archivos, o adoptando una librería de temas (por ejemplo `qt-material` o `PySide6-Fluent-Widgets`; revisa su licencia antes). **No las instales ahora.**

## Fluidez (objetivo: tan rápida como el HTML)
- **Hilos:** toda llamada a Firebase, PDF o Excel corre en un hilo de trabajo (`ui/hilos.py`: `QRunnable` más señales) con indicador de carga y cursor de espera. Errores en un diálogo claro, en español. La ventana nunca se congela.
- La ventana aparece de inmediato; los datos se cargan después en segundo plano. Páginas creadas **una vez** y reutilizadas (carga perezosa la primera vez que se abren).
- Tablas con `QTableView` + modelo propio (`QAbstractTableModel`) + `QSortFilterProxyModel`. **Sin paginación**: la vista es virtual y soporta 800 filas sin problema. El filtro de búsqueda espera 150 ms después de teclear.
- Usa solo la caché de `firebase_client` (una carga por sesión). No agregues lecturas extra.
- Metas (mídelas y anótalas en `escritorio/RENDIMIENTO.md`): ventana visible en menos de 2 s; Inicio con datos en menos de 1 s con caché; tabla de 800 usuarios poblada en menos de 300 ms con los datos en memoria; filtrar en menos de 100 ms.

## Equivalencias con el HTML
| HTML | Escritorio |
|---|---|
| `base.html` + barra superior | `ventana_principal.py` con navegación y `QStackedWidget` |
| `flash(...)` (exito, peligro, info, aviso) | Banner/aviso en la parte superior de la página, con los mismos 4 tipos |
| Modal de formulario | `QDialog` |
| Tarjetas y barras de progreso | `QFrame` con propiedades y `QProgressBar` |
| Paginación de 40 en 40 | No hace falta (vista virtual) |
| `/api/actualizar` | Botón "Actualizar" (`limpiar_cache(limpiar_config=True)` y recarga) |
| Pie con contadores | Barra de estado con Lecturas, Escrituras, límite diario y avisos |

## Pruebas
`pytest` más `pytest-qt` con `QT_QPA_PLATFORM=offscreen`. Las pantallas reciben su "servicio de datos" por parámetro, así que las pruebas usan un doble en memoria (sin Firebase real).
