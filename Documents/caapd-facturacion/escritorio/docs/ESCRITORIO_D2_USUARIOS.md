# ESCRITORIO D2 — Pantalla Usuarios (réplica del HTML)

**Antigravity:** conversación nueva, modo Planning:
`Lee docs/CONTEXTO.md y docs/INTERFAZ_ESCRITORIO.md y ejecuta docs/ESCRITORIO_D2_USUARIOS.md.`

## Objetivo
Replicar en escritorio **todo lo que ya hace la pantalla Usuarios del HTML** (rutas `/usuarios*` de `app.py` y `usuarios.html`), usando la misma lógica de `firebase_client` y `codigos`. **Solo dentro de `escritorio/`.**

## Tareas
1. **Auditoría primero.** Lee las rutas `usuarios`, `usuarios_guardar`, `usuarios_cambiar_estado`, `usuarios_corregir_dni` y `api_usuario_detalle` de `app.py` y la plantilla `usuarios.html`. Lista cada comportamiento y validación que vas a reproducir. **Espera mi OK.**
2. **Tabla** (`QTableView` + modelo propio + `QSortFilterProxyModel`, sin paginación): conexión, nombre, ID (DNI) con insignia **"Pedir DNI"** si `codigos.es_id_pendiente`, sector, dirección, categoría, medidores y estado (activo/inactivo). Orden inicial por conexión.
3. **Filtros** con contadores: Todos, Activos, Inactivos, Pendientes de DNI.
4. **Búsqueda inteligente** con `codigos.buscar` (un solo cuadro; 150 ms de espera al teclear), con la regla de ceros de CONTEXTO §4.
5. **Nuevo / Editar** en un `QDialog`: ID (DNI) o casilla "Sin DNI" (usa `fb.obtener_siguiente_id_sd()`), conexión (sugerida con `fb.obtener_siguiente_conexion_libre()`), nombre y dirección en mayúsculas, sector (lista de `config.sectores`), categoría (de `config.categorias`), activo y medidores (se normalizan con `codigos.normalizar_medidor`, sin repetidos).
   Reproduce las validaciones y mensajes de `usuarios_guardar`: ID existente, medidores únicos entre personas distintas (`fb.validar_medidores_unicos`), DNI de 7 u 8 dígitos normalizado. Guarda con `fb.guardar_usuario`. Si hay un mes ABIERTO, casilla "Agregar al mes actual" (`fb.agregar_usuario_al_mes_actual`). Llama a `on_datos_cambiados(...)` con los mismos parámetros que el HTML.
6. **Activar / Desactivar** (`fb.actualizar_usuario`) con confirmación.
7. **Corregir DNI** (solo para IDs con guion): pide el DNI real (7 u 8 dígitos), normaliza y llama a `fb.corregir_dni_usuario`; muestra el resumen (incluye en cuántos meses se actualizó). Mismos mensajes de error que el HTML.
8. **Detalle** de un usuario (equivale a `api_usuario_detalle`): panel o diálogo al hacer doble clic.
9. Todo en segundo plano (hilos) con indicador de carga; los avisos usan el componente de D1.
10. **Rendimiento:** con 800 usuarios, tabla poblada en menos de 300 ms con los datos en memoria y filtrado en menos de 100 ms. Anótalo en `RENDIMIENTO.md`.
11. **Pruebas:** filtros, búsqueda (la tabla de CONTEXTO §4), validaciones de guardado, corregir DNI y el modelo de la tabla, con un doble en memoria.

## Criterios de aceptación
- Todo lo que hacía la pantalla Usuarios del HTML funciona en escritorio.
- La versión HTML sigue intacta (ningún archivo modificado fuera de `escritorio/`).
- Dame una **tabla de diferencias** HTML vs. escritorio (qué se comporta distinto, aunque sea mínimo).

## Al terminar
Resume, entrega la tabla de diferencias y las mediciones, y **espera mi OK**. Después **comparas ambas versiones** y decides con `ESCRITORIO_D8_CONSOLIDAR.md`.
