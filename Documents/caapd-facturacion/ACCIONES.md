# CAAPD Ispacas — Manual Completo de Acciones de la Interfaz (ACCIONES.md)

Este documento describe **cada botón, control, diálogo y acción** disponible en la aplicación de escritorio de facturación de agua potable **CAAPD Ispacas**, detallando exactamente qué hace cada elemento, qué lógica ejecuta en segundo plano y cómo afecta los datos.

---

## 1. Marco Principal de la Aplicación (`VentanaPrincipal`)

La ventana principal alberga la estructura global del sistema:

### 1.1. Banners de Estado Superiores
1. **Banner "ENTORNO DE PRUEBA ACTIVO" (Amarillo / Naranja):**
   - **Cuándo aparece:** Si el sistema se ejecuta con `CAAPD_ENTORNO=prueba` o mediante `iniciar_prueba.bat`.
   - **Efecto:** Informa a la secretaria que todas las lecturas, recibos y modificaciones se aíslan en la carpeta `escritorio/Base de datos PRUEBA/`, evitando tocar los datos reales de la comunidad.
2. **Banner "MODO CONTINGENCIA / RESPALDO" (Amarillo):**
   - **Cuándo aparece:** Si la aplicación se inició con `--contingencia` o si no hay conexión a internet ni acceso a Firebase.
   - **Efecto:** La aplicación trabaja 100% desconectada utilizando los archivos `respaldos/RESPALDO_*.xlsx`.
3. **Banner "COLA OFFLINE" (Naranja):**
   - **Cuándo aparece:** Si se registraron cobros o lecturas mientras no había conexión a internet y quedaron operaciones en cola.
   - **Botón "🔄 Sincronizar ahora":** Ejecuta `servicios.cola_offline.sincronizar_cola()`, enviando en lote todas las escrituras pendientes a Firebase Firestore.

### 1.2. Barra Superior de Navegación
Contiene los 6 botones principales de acceso a los módulos:
- **`🏠 Inicio`:** Muestra el panel de control con estadísticas del mes y avance de lecturas.
- **`👤 Usuarios`:** Abre el padrón maestro de usuarios y conexiones.
- **`📊 Lecturas`:** Abre la planilla de lecturas de medidores del mes activo.
- **`📱 Lectores`:** Permite administrar las cuentas de los lectores autorizados en la app móvil.
- **`💰 Cobros`:** Módulo unificado de emisión de recibos, cobranza diaria y morosidad.
- **`⚙️ Configuración`:** Edición de tarifas por categoría, rangos de $m^3$, IGV y sectores.

### 1.3. Barra Inferior de Estado (Footer)
- **Etiqueta "Último respaldo: [Fecha y hora]":** Muestra cuándo se generó la última copia de seguridad automática.
- **Botón "💾 Respaldar ahora":** 
  - **Qué hace:** Dispara de inmediato la creación de un nuevo archivo `respaldos/RESPALDO_aaaa-mm_HHMMSS.xlsx`.
  - **Código ejecutado:** `respaldo_excel.generar_respaldo_excel()`. Genera la copia con checksum, hojas por sector, hoja de usuarios y JSON de configuración.
- **Botón "📂 Respaldos":**
  - **Qué hace:** Abre el Explorador de Archivos de Windows en la carpeta local `respaldos/`.
- **Botón "⚙️ Operaciones Firebase":**
  - **Qué hace:** Muestra un cuadro de diálogo con las lecturas y escrituras consumidas en Firestore durante el día (tier gratuito de Google Cloud: máx 50,000 lecturas y 20,000 escrituras).
- **Control de Cierre Seguro (`closeEvent`):**
  - Al hacer clic en la "X" para cerrar el programa, el sistema comprueba si hay cambios en la cola offline sin sincronizar. Si los hay, advierte a la secretaria para evitar pérdidas de datos.

---

## 2. Pantalla 1: Inicio (`PaginaInicio`)

### 2.1. Cabecera
- **Botón "🔄 Actualizar":**
  - Al hacer clic, abre el diálogo de sincronización tripartito:
    1. *Recargar padrón local:* Recarga la memoria desde el archivo Excel de la PC.
    2. *Subir bases a Firebase:* Toma los datos locales del Excel y los sube a Firestore (usado al sembrar un mes nuevo).
    3. *Descargar lecturas de Firebase:* Descarga a la PC las lecturas tomadas por los lectores móviles en sus celulares.

### 2.2. Banner del Mes Activo
- **Si el mes está ABIERTO:**
  - Muestra el periodo (ej. `2026-10`), fecha de emisión y fecha de vencimiento.
  - **Botón "🔒 Cerrar lecturas":** Cambia el estado del mes a `CERRADO`, congelando la toma de lecturas en los celulares de los lectores para proceder con la facturación.
  - **Botón "🧾 Emitir recibos":** Navega directamente a la pantalla de Cobros y abre el asistente de emisión masiva.
- **Si el mes está CERRADO o no hay mes activo:**
  - Muestra alerta amarilla informativa.
  - **Botón "📅 Abrir mes nuevo":** Abre el modal para iniciar el siguiente periodo contable.

### 2.3. Tarjetas de Estadísticas (KPIs)
- **Tarjeta "Recibos generados" (Azul):** Conteo de usuarios que ya tienen recibo emitido. Al hacer clic, navega a *Cobros*.
- **Tarjeta "Pagados" (Verde):** Cantidad de usuarios que ya cancelaron su recibo del mes. Al hacer clic, filtra los cobros por "Pagados".
- **Tarjeta "Pendientes de pago" (Naranja):** Cantidad de usuarios con recibo emitido que aún deben dinero. Al hacer clic, filtra por "Pendientes".

### 2.4. Avance de Lecturas por Sector
- Por cada sector (barrio) registrado, muestra una fila con:
  - Nombre del barrio (ej. *BARRIO DE CHAUPI*, *BARRIO DE LUCMANI*).
  - Barra de progreso porcentual.
  - Conteo de medidores leídos vs. total (ej. `120 / 145 (82.7%)`).

---

## 3. Pantalla 2: Padrón de Usuarios (`PaginaUsuarios`)

### 3.1. Barra de Herramientas
- **Botón "➕ Nuevo Usuario":**
  - Abre el diálogo modal `DialogoUsuario` para dar de alta a un usuario.
  - **Campos:** DNI / Documento, Nombres y Apellidos, Sector, Dirección, Categoría (A, B, C), Estado Activo y lista de números de medidor.
  - **Validaciones:** Impide duplicar números de medidor ya asignados a otra persona. Sugiere el siguiente código de conexión disponible automáticamente.
- **Botón "📥 Importar Excel":**
  - Abre el asistente de importación para cargar o actualizar usuarios desde planillas Excel externas.
- **Botón "🔄 Actualizar":**
  - Recarga la lista completa de usuarios desde la base de datos en segundo plano.

### 3.2. Búsqueda y Filtros Rápidos
- **Buscador Inteligente (`campo_busqueda`):**
  - Cuenta con un *debounce* de 150 ms para no saturar la CPU mientras se escribe.
  - Permite buscar por: nombre de usuario (incluso en orden invertido y sin tildes, ej. `"maribel alvarez"`), DNI, número de conexión o número de medidor.
- **Chips de Filtro:**
  - **`Todos (X)`:** Muestra el padrón completo.
  - **`Activos (X)`:** Filtra solo conexiones activas.
  - **`Inactivos (X)`:** Filtra usuarios cortados o dados de baja temporalmente.
  - **`⚠️ Pedir DNI (X)`:** Filtra usuarios con código provisional (`SD-001` o DNI con guion como `07654321-1`).

### 3.3. Tabla de Usuarios y Acciones de Fila
- **Doble clic en una fila:** Abre el diálogo de edición del usuario.
- **Menú contextual (clic derecho) / Botones de acción:**
  - **`✏️ Editar Usuario`:** Permite corregir nombres, sector, categoría o añadir/quitar medidores.
  - **`🆔 Corregir DNI`:** Exclusivo para usuarios con DNI pendiente. Abre `DialogoCorregirDni`. Al ingresar el DNI real de 8 dígitos, el sistema migra limpiamente el documento sin romper el historial de lecturas pasadas.
  - **`🚫 Desactivar / ✅ Activar`:** Cambia el flag `activo` del usuario en el padrón.

---

## 4. Pantalla 3: Lecturas del Mes (`PaginaLecturas`)

### 4.1. Cabecera y Ciclo de Facturación
- **Pestañas por Sector:** Muestra una pestaña por cada barrio de la comunidad con su avance en tiempo real (ej. `Chaupi (45/50)`). Al hacer clic en una pestaña, la tabla filtra inmediatamente los medidores de esa zona.
- **Botón "🔒 Cerrar lecturas" / "🔓 Reabrir lecturas":**
  - Alterna el estado del mes entre `ABIERTO` y `CERRADO`.
  - Cuando está cerrado, la app móvil de los lectores bloquea la edición de lecturas.
- **Botón "📅 Abrir mes nuevo":**
  - Abre `DialogoAbrirMes`.
  - Exige que el mes previo esté cerrado.
  - Configura el nuevo periodo (ej. `2026-11`), fecha de emisión y fecha de vencimiento.
  - Toma la lectura actual de cada medidor del mes anterior y la copia automáticamente como `lectura_anterior` del nuevo mes.
- **Botón "📥 Importar Excel":**
  - Abre `DialogoImportarMes` para cargar masivamente lecturas desde una plantilla Excel provista por lectores que no usaron la app móvil.
- **Botón "🔄 Actualizar":**
  - Descarga desde Firestore todas las lecturas enviadas por los celulares de los lectores y las guarda en el Excel local.

### 4.2. Tabla de Medidores y Edición Individual
- Muestra: Conexión, Medidor, Titular, Lectura Anterior, Lectura Actual, Consumo ($m^3$), Novedad y Observación.
- **Doble clic en un medidor:** Abre el modal `DialogoLectura`:
  - **Campo "Lectura actual":** Al escribir el número, calcula inmediatamente los $m^3$ consumidos.
  - **Validaciones y Alertas visuales:**
    - *Consumo Negativo:* Si la lectura actual es menor que la anterior, bloquea el guardado a menos que la novedad sea `CAMBIO_MEDIDOR`.
    - *Consumo Alto (> 100 $m^3$):* Muestra alerta amarilla de confirmación.
    - *Consumo Atípico (3x histórico):* Advierte posible fuga no visible.
  - **Desplegable "Novedad":** Permite marcar `NORMAL`, `MEDIDOR_DANADO`, `CAMBIO_MEDIDOR`, `CASA_CERRADA`, `FUGA_VISIBLE`, etc.
  - **Campo "Nota del lector":** Observación de campo.
  - **Botón "Guardar Lectura":** Actualiza el documento en el Excel local y encola/envía la mutación a Firestore.

---

## 5. Pantalla 4: Cobros y Facturación (`PaginaCobros`)

Es el centro operativo principal para la secretaria de CAAPD Ispacas.

### 5.1. Tarjetas de Resumen Financiero (KPIs)
- **`Recibos Generados`:** Ejemplo: `760 de 766`. Indica cuántos usuarios ya cuentan con recibo calculado.
- **`Total Facturado`:** Suma total en soles a cobrar en el mes (incluye agua, desagüe, cargo fijo, IGV y deuda anterior).
- **`Recaudado / Saldo`:** Dinero en efectivo cobrado en caja vs. saldo pendiente de cobranza.
- **`En Lista de Corte`:** Cantidad de usuarios con 3 o más meses impagos (estado ROJO).

### 5.2. Botones de Acción Masiva y Directa
- **Botón "🧾 Emitir recibos del mes…":**
  - Abre el asistente en 3 pasos `DialogoAsistenteEmitirRecibos`:
    - **Paso 1 (Revisión de Faltantes):** Detecta qué medidores no tienen lectura. Permite estimar lecturas automáticamente (usando el promedio de los últimos 6 meses) o continuar emitiendo solo a los leídos.
    - **Paso 2 (Generación Idempotente):** Calcula todos los recibos mediante `calculos.calcular_recibo()` y genera los archivos PDF en disco con barra de progreso. Si un recibo ya fue emitido y pagado, no lo sobreescribe para preservar la integridad del cobro.
    - **Paso 3 (Resultados):** Muestra el resumen contable final, total recaudable y botones directos para abrir la carpeta o descargar el archivo ZIP.
- **Botón "🖨️ Imprimir / Descargar recibo PDF":**
  - **Qué hace:** Abre directamente el recibo en formato PDF del usuario seleccionado en el visor predeterminado del sistema operativo (listo para imprimir con `Ctrl+P` o guardar en disco). Si el usuario seleccionado aún no tiene un recibo emitido, ofrece generarlo al vuelo automáticamente en un solo paso.
- **Menú "Recibos ▾":**
  - **`🖨️ Imprimir recibo PDF (seleccionado)`:** Abre el visor de impresión para la conexión seleccionada.
  - **`💾 Guardar recibo PDF como... (descargar)`:** Abre una ventana de Windows para descargar y guardar una copia del PDF en cualquier carpeta elegida (como un USB o Descargas).
  - **`📦 Descargar ZIP de recibos (todos)`:** Comprime todos los archivos PDF del mes en un único archivo ZIP en la ubicación que elija la secretaria (ideal para llevar en USB a imprenta).
  - **`📂 Abrir carpeta de recibos`:** Abre la carpeta local `salidas/recibos/aaaa-mm/` con todos los PDFs generados.
  - **`🧾 Emitir un recibo individual...`:** Emite el recibo individual del usuario seleccionado si no se hubiera emitido en el lote.
- **Botón "⚠️ Exportar morosos (Excel)":**
  - Genera y abre una planilla Excel con la lista de usuarios en estado de corte (3+ meses) y advertencia (2 meses), con teléfonos, conexiones y montos adeudados para la cuadrilla de cortes en campo.
- **Botón "🧾 Emitir un recibo a la vez...":**
  - Emite o recalcula el recibo exclusivamente para la fila que esté seleccionada en la tabla.

### 5.3. Tabla de Cobros y Filtros de Búsqueda
- **Chips de filtro:**
  - `Todos`, `Sin facturar`, `Pendientes`, `2 Meses (Naranja)`, `Corte 3+ m. (Rojo)`, `Pagados (Verde)`, `⚠️ Con Alertas`.
- **Selector de Sector:** Filtra la cobranza por barrio.
- **Buscador:** Búsqueda en tiempo real por nombre, DNI, número de recibo o conexión.
- **Clic derecho sobre cualquier fila:**
  - `🖨️ Imprimir / Descargar recibo PDF`
  - `💾 Guardar recibo PDF en otra carpeta...`
  - `💳 Marcar como pagado` / `↩️ Anular cobro`
  - `🧾 Emitir recibo`

### 5.4. Ficha Lateral del Usuario (Panel de Cobranza)
Al hacer clic en cualquier fila de la tabla, la ficha lateral muestra:
- **Badge de Nivel de Mora:**
  - Verde: *Al día / 1 mes*
  - Naranja: *2 meses de deuda (notificación)*
  - Rojo: *3+ meses de deuda (orden de corte de servicio)*
- **Recuadro de Alertas de Medidor:** Si el lector reportó novedades como `FUGA_VISIBLE` o `MEDIDOR_DANADO`, se muestra un recuadro amarillo destacado para alertar a la secretaria antes de cobrar.
- **Desglose Contable:**
  - Deuda anterior (S/.)
  - Consumo del mes (S/.)
  - Cargo fijo (S/.)
  - Total a pagar (S/.)
  - Monto ya pagado (S/.)
- **Botón "💳 Marcar como pagado":**
  - **Qué hace:** Aplica la regla contable **"Todo o Nada"**. Registra el pago por el 100% del monto adeudado.
  - **Datos modificados:** `monto_pagado = total_a_pagar`, `pago = "SI"`, `fecha_pago = [Fecha de hoy]`.
- **Botón "🖨️ Imprimir / Descargar recibo PDF":**
  - **Qué hace:** Botón principal destacado en azul que genera el PDF del usuario (si no lo tenía) y lo abre de inmediato en el visor de documentos de Windows, con opciones inmediatas para imprimir o guardar.
- **Botón "↩️ Anular cobro":**
  - **Qué hace:** En caso de error de digitación o reclamo, revierte el cobro.
  - **Datos modificados:** `monto_pagado = 0.0`, `pago = "NO"`, `fecha_pago = None`.
- **Botón "🧾 Emitir recibo a este usuario":**
  - Visible si el usuario aún no tiene recibo emitido en el mes.

---

## 6. Pantalla 5: Lectores Móviles (`PaginaLectores`)

Gestiona las cuentas de los operarios de campo que usan la app Android:
- **Botón "➕ Nuevo Lector":** Abre un modal para crear un usuario en Firebase Authentication con Correo electrónico, Contraseña y Nombre visible.
- **Botón "🔄 Actualizar":** Consulta la lista actualizada de lectores desde Firebase Auth.
- **Acciones sobre cada Lector (menú contextual o doble clic):**
  - *Cambiar contraseña:* Restablece la clave de acceso del lector.
  - *Desactivar / Activar:* Bloquea el acceso a la app móvil sin eliminar sus lecturas históricas.
  - *Eliminar cuenta:* Borra definitivamente el acceso del lector.

---

## 7. Pantalla 6: Configuración del Sistema (`PaginaConfiguracion`)

Permite parametrizar las reglas de negocio del sistema:

### 7.1. Pestaña "Institucional"
- Campos editables: Nombre del Comité, Resolución de Creación (ej. `RESOLUCION 192-2017`), Celular / WhatsApp de atención, Dirección y Mensaje personalizado al pie del recibo.

### 7.2. Pestaña "Tarifas y Categorías"
- Permite seleccionar la categoría (A: Doméstico, B: Comercial, C: Estatal).
- **Cargo fijo mensual (S/.):** Monto fijo obligatorio (por defecto S/. 5.00 o S/. 1.50 según configuración).
- **Tarifa de desagüe (S/.):** Costo por servicio de alcantarillado.
- **Modo de cálculo de rangos:**
  - *Rango Único:* Todo el consumo se cobra a la tarifa del rango donde cae el total de $m^3$.
  - *Por Tramos:* Cobro escalonado acumulativo por cada bloque de $m^3$.
- **Tabla de Rangos:** Botones para agregar, editar o eliminar rangos (`m3_desde`, `m3_hasta`, `precio_m3`).

### 7.3. Pestaña "Impuestos y Mora"
- **IGV:** Checkbox para activar/desactivar el cobro del 18% de IGV (inafecto por defecto en comunidades campesinas).
- **Políticas de Mora:** Configura los colores de advertencia (Azul, Naranja, Rojo) y cuántos meses impagos activan la orden de corte físico del suministro.

### 7.4. Pestaña "Sectores"
- Lista de barrios registrados en la comunidad (Chaupi, Lucmani, Pachayza, Huaquillo, etc.).
- Permite agregar nuevos sectores o renombrar existentes.

### 7.5. Pestaña "Observaciones de Medidor"
- Configura el catálogo de novedades que ven los lectores en la app móvil (ej. `MEDIDOR_DANADO`, `CASA_CERRADA`).
- Permite marcar qué observaciones disparan una alerta visual en la PC de cobranza.

### 7.6. Guardado Global
- **Botón "💾 Guardar Cambios":** Valida todos los formularios y persiste la nueva configuración en el documento `config/general` de Firestore y en la hoja `CONFIG` del Excel local.
