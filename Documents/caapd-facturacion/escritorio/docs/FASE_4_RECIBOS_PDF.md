# FASE 4 — Generar recibos y PDF

**Antigravity:** conversación nueva, modo Planning:
`Lee docs/CONTEXTO.md y ejecuta docs/FASE_4_RECIBOS_PDF.md.`

## Objetivo
Pantalla **Recibos**: generar los recibos del mes, ver el estado y descargar PDF (individual y ZIP por sector).

## Parte A — Generar recibos
1. Habilitado si el mes está `CERRADO` (si está `ABIERTO`, avisa que aún pueden entrar lecturas y pide confirmación).
2. **Lecturas faltantes**: lista a quienes tengan algún medidor PENDIENTE o SIN_ACCESO. Para cada uno, dos acciones (no se puede generar sin resolver todos):
   - **Ingresar lectura** manual.
   - **Estimar con consumo anterior**: lectura_actual = lectura_anterior + `consumo_anterior`; pone `novedad = "LECTURA_ESTIMADA"`, `estado_lectura = "LEIDO"`, `nota = "Estimada por la secretaria"` y `registrado_por = "ADMIN"`. Si `consumo_anterior` es null, pide el valor.
3. Lee el mes anterior **una vez, fresco** para calcular `deuda_anterior` y `meses_adeudados` (pueden haber cobrado después de abrir el mes). Sin mes anterior: deuda 0 y meses 1.
4. Calcula con `calculos.py` (modo "unico" o "tramos" según la categoría).
5. Numera con `config.ultimo_recibo + 1`, en orden por sector y nombre. Escribe los campos del recibo y `monto_pagado = 0`, `fecha_pago = null` en lotes de 500; al final actualiza `config.ultimo_recibo` y pasa `mes_actual.estado` a `FACTURADO`. Si falla a medias, se puede reintentar sin duplicar números (idempotente por documento).
6. Llama a `on_datos_cambiados()`.

## Parte B — PDF (media hoja; replica `docs/recibo_ejemplo.jpg`)
Encabezado del comité (nombre, "CAAPD ISPACAS", dirección, teléfono) y **RESOLUCION 192-2017**; último día de pago; monto a pagar; temporada (MES AÑO); recibo nro; fecha de emisión; conexión; nombre; DNI/RUC (vacío si el ID tiene guion); zona; categoría; dirección.
Tabla de medidores: medidor, lectura anterior y su fecha, lectura actual y su fecha, consumo; y "Periodo / Ciclo del ... al ...".
Conceptos con columnas Inafectos y Afectos: 001 SERVICIO DE AGUA, 008 SERVICIO DE DESAGUE, 407 CARGO FIJO, DEUDA ANTERIOR (SIN DEUDA / CON DEUDA).
Histograma de 6 meses (`historial_m3` + consumo actual; eje Y fijo hasta 100 m³, dinámico si se supera).
Subtotal, IGV, Redondeo, TOTAL MES, TOTAL A PAGAR y "Son: DIECISIETE 50/100 SOLES".
Línea de corte y talón: QR de WhatsApp (si `empresa.whatsapp` está vacío, deja el espacio con el texto "WhatsApp por definir"), conexión, nombre, total, recibo, emisión y vencimiento.
- **Color según mora**: usa `config.mora` (azul, naranja, rojo); pagado o sin deuda = color base celeste. Colores solo desde config.
- **Las observaciones NO se imprimen** en el recibo (son para la secretaria).
- Dos o más medidores: una fila por medidor.
- PDF individual al instante; ZIP por sector. Se guardan en `recibos/aaaa-mm/<sector>/`.

## Número a letras en español (`numero_a_letras`, con pruebas)
17.50 → "DIECISIETE 50/100 SOLES"; 21.00 → "VEINTIUNO 00/100 SOLES"; 100.00 → "CIEN 00/100 SOLES"; 101.00 → "CIENTO UNO 00/100 SOLES"; 0.50 → "CERO 50/100 SOLES"; 1234.00 → "MIL DOSCIENTOS TREINTA Y CUATRO 00/100 SOLES"; 2000.00 → "DOS MIL 00/100 SOLES". Hasta 99 999.99.

## Pantalla Recibos
Estado del mes, contador de generados, tabla por sector con número de recibo, total, meses adeudados (con el color) y botones PDF; reimprimir cualquier recibo; vista previa del PDF (en escritorio, dentro de la ventana con `QPdfView`; en HTML, en el navegador).

## Criterios de aceptación
- Pruebas: numeración, deuda y meses desde el mes anterior, persona con 2 medidores, estimación, número a letras.
- El PDF de la conexión 000796 (consumo 16, total 17.50) se parece al recibo de ejemplo.
- Ejecutarlo dos veces no duplica números de recibo.

## Al terminar
Resume, entrega un PDF de ejemplo en `salida/` y **espera mi OK**.
