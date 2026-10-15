# FASE 3 — Abrir mes y pantalla Lecturas

**Antigravity:** conversación nueva, modo Planning:
`Lee docs/CONTEXTO.md y ejecuta docs/FASE_3_MES_Y_LECTURAS.md.`

## Objetivo
Crear la "tabla nueva del mes" y ver/corregir las lecturas que ingresan los lectores desde su app.

## Parte A — Abrir mes (botón en Inicio y Lecturas)
1. Solo si no hay un mes ABIERTO/CERRADO sin facturar. Pide el periodo (por defecto el mes siguiente al último; el primero lo elijo yo), `fecha_emision` (hoy) y `fecha_vencimiento` (emisión + `dias_vencimiento`, editable).
2. Lee los usuarios activos y el mes anterior (una lectura de cada colección).
3. Crea `mes_aaaa-mm/{id_usuario}` con la copia del padrón y, por cada medidor:
   - `lectura_anterior` = `lectura_actual` del mes pasado si su `estado_lectura` fue LEIDO. Si el mes pasado quedó sin leer, conserva su `lectura_anterior`.
   - `fecha_anterior` = `fecha_lectura` del mes pasado.
   - `consumo_anterior` = actual − anterior del mes pasado.
   - `estado_lectura = "PENDIENTE"`, `lectura_actual`, `fecha_lectura`, `registrado_por` en null, `novedad = ""`, `nota = ""`.
   - `historial_m3` = (historial previo + consumo total previo), últimos 5.
4. **Primer mes (no hay mes anterior)**: usa `salida/semilla_mes_previo.json` (lectura actual → `lectura_anterior`; actual − anterior → `consumo_anterior`). Los medidores que no estén ahí (nuevos) se muestran en una tabla "Falta lectura anterior" para que yo la escriba antes de abrir. No abras con huecos.
5. Escribe en lotes de 500 y actualiza `config.mes_actual` (`estado = "ABIERTO"`). Si la colección del mes ya existe, **no la sobrescribas**: ofrece "Completar solo los usuarios que faltan".
6. Llama a `on_datos_cambiados()`.

## Parte B — Pantalla Lecturas
- Pestañas por sector. Tabla: persona, conexión, medidor, lectura anterior, lectura actual, consumo (calculado), estado (PENDIENTE / LEIDO / SIN_ACCESO), observación (insignia con color) y nota, y "registrado por".
- Filtros: Todos, Faltan por leer, Sin acceso, Con observación. Búsqueda inteligente. Avance por sector (x de y).
- **Corregir** una lectura: la PC puede editar `lectura_actual`, `novedad` (lista desde `config.observaciones`) y `nota`; al guardar pone `registrado_por = "ADMIN"` y recalcula `consumo_total_m3`. La `lectura_anterior` y el consumo **no se editan** (solo con una acción "corrección avanzada" con confirmación, que deja constancia en `nota`).
- Aviso si el consumo es negativo, mayor a 100 m³ o mayor a 3 veces el promedio de `historial_m3`.
- **Cerrar lecturas**: pasa `mes_actual.estado` a `CERRADO` (la app móvil deja de aceptar lecturas). Muestra cuántos quedan PENDIENTE o SIN_ACCESO y pide confirmación. "Reabrir" disponible mientras no esté FACTURADO.
- Los datos se cargan una vez a memoria; botón Actualizar para releer el mes.

## Criterios de aceptación
- Pruebas: abrir mes (con mes previo, sin mes previo con semilla, medidor nuevo), cálculo de `consumo_anterior`, `historial_m3`, consumo total con medidores sin leer (queda null).
- Abrir el mes dos veces no duplica ni pisa datos.
- El JSON generado coincide con `docs/firestore_ejemplo_v2_1.json` en nombres y tipos.

## Al terminar
Resume, indica cómo probar sin tocar datos reales (usa un mes de prueba o un modo simulado) y **espera mi OK**.
