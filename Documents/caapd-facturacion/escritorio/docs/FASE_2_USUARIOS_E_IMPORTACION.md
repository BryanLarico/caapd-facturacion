# FASE 2 — Usuarios e importación inicial

**Antigravity:** conversación nueva, modo Planning:
`Lee docs/CONTEXTO.md y ejecuta docs/FASE_2_USUARIOS_E_IMPORTACION.md.`

## Objetivo
La pantalla **Usuarios** completa (buscar, agregar, editar, desactivar, medidores, corregir DNI) y el script que importa tus dos Excel actuales al padrón.

> **Estado:** la **Parte A** (script) ya está hecha (`scripts/importar_excel.py`). La **Parte B** (pantalla Usuarios) ya existe en la versión HTML; en la versión de escritorio se replica con `docs/ESCRITORIO_D2_USUARIOS.md`. Este archivo queda como referencia de las reglas.

## Parte A — Script de importación `scripts/importar_excel.py`
Archivos: `datos/LISTA_DE_USUARIOS_2026.xlsx` (DNI, estado, medidor, sector, dirección) y `datos/RELACION_DE_USUARIOS_DEL_CAAPD.xlsx` (una hoja por sector; trae el número de conexión).
Modos: `--simular` (solo reporte, no escribe) y real (pide confirmación escrita antes de escribir).

Reglas (hoja `Migracion_datos` del Excel):
1. Solo ACTIVOS. El estado mal escrito `NACTIVO` se trata como inactivo.
2. Une ambas bases por **número de medidor**, normalizando ceros a la izquierda.
3. Agrupa por persona = DNI + nombre normalizado (mayúsculas, espacios y comas limpios).
4. **Un solo `nro_conexion` por persona**: el menor de sus códigos. Lista las que tenían varios (para que yo lo confirme).
5. DNI a 8 dígitos con ceros. DNI compartido por personas distintas → `-1`, `-2` en todas. Sin DNI → `SD-001`, `SD-002`...
6. Medidores a mínimo 6 dígitos. Si una persona repite el mismo medidor, deja uno.
7. Cada persona queda con `medidores[]` (solo textos).
8. Genera además `salida/semilla_mes_previo.json`: por medidor, la **lectura actual** y la **lectura anterior** del Excel RELACION (más la fecha si existe). Lo usará la Fase 3 para el primer mes.
9. Reportes CSV en `salida/`: personas con varios códigos de conexión, DNI con guion (pendientes), DNI de 9 dígitos, medidores repetidos entre personas distintas, activos sin código de conexión, conexión sin medidor.

**Cifras esperadas** (hoja Migracion_datos; si difieren, explica por qué): 766 activos → unas 714 personas (664 con un medidor y 50 con 2 o 3); 49 con más de un código de conexión; 22 DNI compartidos (48 personas); 25 sin DNI; 31 DNI de 7 dígitos; 3 DNI de 9 dígitos; 3 medidores de menos de 6 dígitos; 2 activos sin código de conexión; 2 números de medidor repetidos.

## Parte B — Pantalla Usuarios
- Tabla con búsqueda inteligente (`codigos.buscar`) y filtros: Todos, Activos, Inactivos, **Pendientes de DNI**.
- Los IDs con guion se muestran con una insignia "Pedir DNI".
- Agregar y editar: ID (DNI), conexión (se sugiere el siguiente número libre), nombre, sector (lista desde config), dirección, categoría, activo.
- Medidores: agregar y quitar; normaliza a mínimo 6 dígitos al guardar. Un medidor no puede repetirse entre personas.
- Un medidor reemplazado se quita de la lista (el historial queda en los meses).
- **Corregir DNI**: pide el DNI real, valida 8 dígitos y que no exista; crea el documento nuevo, copia, borra el anterior, y lo renombra en cada colección `mes_*` que lo contenga. Todo con confirmación y un resumen de operaciones.
- "Agregar al mes actual": si hay un mes ABIERTO y la persona es nueva, crea su documento del mes (lo usa la Fase 3).
- Cada cambio llama a `on_datos_cambiados()`.

## Criterios de aceptación
- `importar_excel.py --simular` imprime cifras coherentes con las esperadas.
- Pruebas para: agrupación por persona, unión de códigos, sufijos -1/-2, SD-xxx y el renombrado de ID.
- La búsqueda cumple la tabla de la sección 4 de CONTEXTO.md.

## Al terminar
Resume, muestra el reporte del `--simular`, y **espera mi OK** antes de la importación real y de la Fase 3.
