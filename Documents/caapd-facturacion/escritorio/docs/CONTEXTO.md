# CONTEXTO — Programa de facturación CAAPD Ispacas (PC de la secretaria)

> **Lee este archivo COMPLETO al inicio de cada fase.**
> Fuentes: `docs/MER_CAAPD_Ispacas_v2.xlsx` (reglas y fórmulas) y `docs/firestore_ejemplo_v2_1.json` (estructura exacta de los documentos).
> Si algo contradice al Excel, **mandan este archivo y el JSON v2.1**. Si falta un dato o hay una contradicción, **pregunta antes de inventar**.

## 1. Qué es
- Programa de facturación de la secretaria del comité de agua (una sola PC con Windows). Hay **dos interfaces posibles sobre la misma lógica**: **HTML con Flask** (ya existente, en la raíz) y **escritorio nativo con PySide6** (en la carpeta `escritorio/`). Lee también `docs/INTERFAZ_HTML.md` o `docs/INTERFAZ_ESCRITORIO.md`, según el proyecto en el que trabajes.
- Stack común (no agregues más): Python 3.11+, firebase-admin, openpyxl, reportlab, matplotlib, qrcode con Pillow, pytest. HTML añade Flask. Escritorio añade PySide6 y pytest-qt.
- Base de datos: Firestore `(default)` con `firebase-admin` y `serviceAccountKey.json` (clave de servicio, no expira y no pide iniciar sesión).
- Otra aplicación independiente (móvil, de los lectores) escribe las lecturas en Firestore. **No la construyas**; respeta su contrato (sección 3).
- Aprox. 800 usuarios. Plan gratuito de Firebase: máx. 50 000 lecturas y 20 000 escrituras por día.

## 2. Reglas de oro
1. **Pocas operaciones en Firebase.** Sin listeners en tiempo real. Carga usuarios y el mes actual UNA vez por sesión a memoria; refresca solo con el botón Actualizar. Escrituras en lotes de máximo 500. La pestaña **Lectores** administra las cuentas de Firebase Authentication también cuando la aplicación de escritorio trabaja en modo local-first con Excel; no toma esas cuentas de la configuración local ni las mezcla con los sectores.
2. **Una sola capa de datos.** Todo acceso a Firestore pasa por `firebase_client.py`. Ningún otro módulo llama a Firestore directamente (esto permite el modo contingencia de la Fase 6).
3. **Estilo centralizado.** Ningún color, tamaño ni fuente suelto en el código de las pantallas: el diseño vive en un solo lugar según la interfaz (ver `INTERFAZ_HTML.md` o `INTERFAZ_ESCRITORIO.md`), para poder cambiarlo después.
4. **Todo en español**: interfaz, mensajes y comentarios.
5. **Pruebas** con pytest para toda lógica de cálculo y formatos.
6. **Seguridad.** `serviceAccountKey.json` en `.gitignore`. No imprimas ni registres credenciales. El servidor HTML escucha solo en 127.0.0.1; la versión de escritorio no abre puertos.
7. **Respaldo.** Después de cualquier cambio de datos llama a `on_datos_cambiados()` (hook definido en la Fase 1B; lo implementa la Fase 6).
8. **Al terminar cada fase**: resumen de lo hecho, cómo probarlo, y **detente a esperar mi OK**.
9. **Fluidez.** Las operaciones lentas (Firebase, PDF, Excel) no bloquean la interfaz y muestran un indicador de carga; los errores se muestran en español.
10. **Rutas.** Las rutas se calculan desde la carpeta del programa (también cuando está empaquetado), nunca desde el directorio de trabajo.
11. **Convivencia de interfaces.** La lógica compartida (`firebase_client.py`, `calculos.py`, `codigos.py`, `respaldo.py`, `config_local.py`, `scripts/`, `tests/`) vive en la raíz y es la misma para ambas interfaces. **No modifiques archivos de la otra interfaz.** Los cambios a la lógica compartida solo se hacen en la Fase 1D o, después, de forma **retrocompatible** (sin cambiar firmas ni comportamiento de lo que ya usa la otra interfaz), con pruebas y avisándome en el resumen.
12. **Estados del mes:** ver la tabla de la sección 3b.

## 3. Esquema de datos (resumen; detalle en el JSON v2.1)
```
config/general              un solo documento (tarifas, IGV, mora, observaciones, mes_actual...)
usuarios/{id_usuario}       padrón fijo (~800)
mes_aaaa-mm/{id_usuario}    colección NUEVA cada mes: la "tabla del mes" (como el Excel de lecturas)
```
**config/general**: `empresa`, `igv{activo,porcentaje}`, `dias_vencimiento`, `ultimo_recibo`, `sectores[]`, `categorias{A,B,C}` (con `tarifa_desague`, `cargo_fijo`, `modo_rangos` = "unico" o "tramos", `rangos[]`), `mora[]`, `observaciones[]` (catálogo editable) y `mes_actual{periodo, fecha_emision, fecha_vencimiento, estado}` con estado `ABIERTO` → `CERRADO` → `FACTURADO`.

**usuarios/{id_usuario}**: `nro_conexion`, `nombre`, `sector`, `direccion`, `codigo_categoria`, `activo`, `medidores[]` (lista de textos, solo activos).

**mes_aaaa-mm/{id_usuario}**: copia del padrón (`nro_conexion`, `nombre`, `sector`, `direccion`, `codigo_categoria`), `medidores[]`, `consumo_total_m3`, `historial_m3[]` (5 consumos previos), y después los campos del recibo (`nro_recibo`, `monto_agua`, `monto_desague`, `cargo_fijo`, `deuda_anterior`, `igv`, `redondeo`, `total_a_pagar`, `meses_adeudados`) y del cobro (`monto_pagado`, `fecha_pago`).

**Cada entrada de `medidores[]` en el mes** (contrato con la app móvil):

| Campo | Quién lo escribe | Significado |
|---|---|---|
| `nro_medidor` | PC | Texto, mínimo 6 dígitos con ceros |
| `lectura_anterior` | PC | NO editable por el lector |
| `fecha_anterior` | PC | Fecha de la lectura anterior |
| `consumo_anterior` | PC | m³ del mes pasado de ese medidor (ayuda al lector cuando no ve el medidor) |
| `lectura_actual` | Lector | `null` hasta leerla |
| `fecha_lectura` | Lector | aaaa-mm-dd |
| `estado_lectura` | Lector | `PENDIENTE`, `LEIDO` o `SIN_ACCESO` |
| `novedad` | Lector | Código del catálogo `config.observaciones` (NORMAL, MEDIDOR_DANADO, ...) |
| `nota` | Lector | Texto libre opcional |
| `registrado_por` | Lector/PC | Correo del lector o "ADMIN" si lo corrigió la PC |

`consumo_total_m3` = suma de (actual − anterior) de sus medidores; `null` mientras haya medidores sin leer. El consumo de un medidor nunca se guarda: se calcula.
**Regla de consumo de un medidor** (la misma en la app móvil y en la PC): si `lectura_actual` ≥ `lectura_anterior`, consumo = actual − anterior. Si es menor y `novedad = CAMBIO_MEDIDOR`, el medidor nuevo empieza en cero y consumo = actual (la secretaria puede corregirlo). En cualquier otro caso la lectura es inválida.
**Observaciones:** las que tienen `alerta: true` deben mostrarse a la secretaria al cobrar (ver Fase 5) y respaldarse en el Excel.

## 3b. Estados del mes (`config.mes_actual.estado`)
| Estado | Significado | Botones principales en Inicio |
|---|---|---|
| (sin mes) | Aún no hay mes abierto | Abrir mes nuevo |
| `ABIERTO` | Los lectores están ingresando lecturas | Ir a Lecturas, **Cerrar lecturas** |
| `CERRADO` | Lecturas cerradas, falta facturar | **Generar recibos**, Reabrir lecturas |
| `FACTURADO` | Recibos generados, se cobra | Ir a Cobros, **Abrir mes nuevo** |
La app móvil solo acepta lecturas con `ABIERTO`. Nota: `inicio.html` (versión HTML) usa estos estados de otra forma en sus botones; en cualquier interfaz manda esta tabla.

## 4. Códigos y búsqueda inteligente
Formatos (se guardan siempre normalizados):
- `nro_medidor`: **mínimo 6 dígitos**, ceros a la izquierda si tiene menos (`100` → `000100`). Si ya tiene 6 o más, **no se toca** (`123456` sigue siendo `123456`; `22392996` sigue igual).
- `nro_conexion`: 6 dígitos (`796` → `000796`). `id_usuario` (DNI): 8 dígitos (`7654321` → `07654321`). `nro_recibo`: 9 dígitos.
- DNI compartido por personas distintas: `07654321-1`, `07654321-2`. Sin DNI: `SD-001`, `SD-002`... Todo ID con guion = **pendiente de corregir** (el programa avisa: pedir el DNI).

**Búsqueda (un solo cuadro en Usuarios, Lecturas y Cobros):**
- Si lo escrito son solo dígitos y tiene MENOS dígitos que el mínimo del campo, buscar primero la coincidencia exacta con los ceros completados y después los que contengan esos dígitos. Si tiene el mínimo o más, buscar tal cual (sin agregar ceros). Se aplica a medidor (6), conexión (6) y DNI (8).
- Si tiene letras: buscar en `nombre`, sin distinguir mayúsculas ni tildes, todas las palabras presentes en cualquier orden.

| Escribo | Campo | Resultado |
|---|---|---|
| `3386` | medidor | primero `003386`, luego los que contengan 3386 |
| `123456` | medidor | `123456` tal cual (NO `000123456`) |
| `796` | conexión | primero `000796` |
| `7654321` | DNI | primero `07654321` |
| `alvarez maribel` | nombre | ambas palabras, sin tildes |

## 5. Reglas de negocio (detalle en las hojas Reglas_negocio y Calculo_ejemplo)
- Una persona = un `nro_conexion` y un recibo, aunque tenga varios medidores (el consumo es la suma).
- `monto_agua` = consumo × precio del rango. `modo_rangos = "unico"`: el precio del rango donde cae el consumo aplica a todo. `"tramos"`: cada tramo con su precio (acumulado). El valor por defecto es "unico" y es editable en Configuración (decisión pendiente del comité).
- IGV solo si está activo, sobre lo afecto (no sobre la deuda). `redondeo` = centésimas restadas para que el total termine en 0.10 (17.56 → 17.50).
- `total_a_pagar` = agua + desagüe + cargo fijo + deuda_anterior + igv − redondeo.
- `deuda_anterior` = MAX(0, total_a_pagar anterior − monto_pagado anterior). `meses_adeudados` = 1 si el recibo anterior está pagado o no existe; si no, los del anterior + 1.
- Color: 1 mes azul, 2 naranja, 3 o más rojo (lista de corte). Recibo pagado: color base. El sistema NO corta el servicio.
- Pago: la secretaria marca pagado (`monto_pagado = total_a_pagar`, `fecha_pago`); admite pago parcial.

## 6. Carpetas
```
RAÍZ (compartido)   firebase_client.py  calculos.py  codigos.py  respaldo.py  config_local.py
                    scripts/  tests/  datos/  respaldos/  salida/  docs/
HTML (existente)    app.py  templates/  static/css/estilo.css  iniciar.bat
ESCRITORIO (nuevo)  escritorio/  main.py  rutas.py  ui/  servicios/  tests/  requirements.txt  pytest.ini  iniciar.bat  venv/
```
