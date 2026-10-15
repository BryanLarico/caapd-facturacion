# FASE 5 — Cobros, observaciones y morosos

**Antigravity:** conversación nueva, modo Planning:
`Lee docs/CONTEXTO.md y ejecuta docs/FASE_5_COBROS_Y_MOROSOS.md.`

## Objetivo
La pantalla **Cobros**: que la secretaria busque a la persona, vea cuánto debe y **las observaciones de su medidor**, y marque que pagó.

## Ficha de cobro (al elegir una persona)
- Datos: nombre, conexión, sector, dirección.
- Montos: total del mes, deuda anterior, **total a pagar**, meses adeudados con su color (azul, naranja, rojo) y estado (Pagado / Pendiente / Parcial).
- **Observaciones del medidor** (obligatorio): por cada medidor con `novedad` cuyo catálogo tenga `alerta: true`, muestra un recuadro llamativo con el texto de la observación, la nota libre y quién la registró (ej.: "Medidor dañado — La tapa está rota. Registrado por lector1@..."). Así la secretaria se lo comunica al cliente. En lectura estimada, indica la lectura usada.
- Botón **Marcar como pagado**: `monto_pagado = total_a_pagar` y `fecha_pago = hoy`. Opción **pago parcial** (monto editable; lo no pagado pasa como deuda al mes siguiente). Pide confirmación mostrando el monto.
- **Anular cobro** (con confirmación): `monto_pagado = 0`, `fecha_pago = null`.
- Reimprimir el recibo (PDF) desde la ficha.

## Buscador y listas
- Buscador inteligente único (nombre, conexión, medidor o DNI con la regla de ceros de la sección 4).
- Lista **Pendientes de pago** por sector con filtro por nivel de mora.
- **Reporte de morosos** por nivel (azul, naranja, rojo) y **lista de corte** (3 meses o más), exportable a Excel con nombre, conexión, sector, dirección, meses y total adeudado. El sistema NO corta el servicio.
- Totales del mes: recibos, pagados, pendientes y monto cobrado vs. por cobrar.

## Reglas técnicas
- Se trabaja sobre la copia en memoria del mes (una sola carga); cada cobro es **un update de un documento** y actualiza la copia en memoria.
- Un recibo solo se cobra si el mes está `FACTURADO`.
- Cada cobro o anulación llama a `on_datos_cambiados()`.
- Mensaje claro si la escritura falla (la Fase 6 agrega la cola sin conexión).

## Criterios de aceptación
- Pruebas: pago total, parcial (deuda al mes siguiente), anulación, filtros de mora y lista de corte.
- Una persona con observación `MEDIDOR_DANADO` y nota muestra el recuadro de alerta en su ficha.
- Marcar un pago genera exactamente 1 escritura (visible en el contador del pie).

## Al terminar
Resume y **espera mi OK** para la Fase 6.
