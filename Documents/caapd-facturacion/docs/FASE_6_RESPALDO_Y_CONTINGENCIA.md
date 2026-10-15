# FASE 6 — Respaldo en Excel, contingencia y pulido final

**Antigravity:** conversación nueva, modo Planning:
`Lee docs/CONTEXTO.md y ejecuta docs/FASE_6_RESPALDO_Y_CONTINGENCIA.md.`

## Objetivo
Que **todo lo que se cree quede respaldado en Excel** y que, si Firebase falla o se pierde, se pueda **subir de nuevo** ese Excel y seguir trabajando.

## Parte A — Respaldo automático (`respaldo.py` + `respaldo_excel.py`)
Implementa `on_datos_cambiados()`:
- Programa un respaldo con **espera de 2 minutos** desde el último cambio (varios cambios seguidos = un solo respaldo). Además se ejecuta al abrir un mes, al generar recibos y al cerrar el programa.
- Guarda `respaldos/RESPALDO_aaaa-mm.xlsx` (versión vigente) y **una copia por día** en `respaldos/historial/` (conserva 30 días). Se arma con los datos ya cargados en memoria: **0 lecturas extra de Firebase**.
- Botón "Respaldar ahora" y "Abrir carpeta de respaldos". Se muestra la fecha y hora del último respaldo en el pie.

**Contenido del Excel (todo lo necesario para reconstruir):**
1. `LEEME`: versión del formato, fecha, periodo, cantidad de usuarios y documentos, suma de `total_a_pagar` (para verificar al restaurar) y estas instrucciones.
2. Una hoja por **sector**, igual al Excel actual: Fecha de lectura, Número de conexión, Número de medidor, Beneficiario, Dirección, Lectura anterior, Lectura actual, Consumo, **Observación** y **Nota**, Recibo N°, Deuda anterior, Total a pagar, Meses adeudados, Pagado, Fecha de pago. Una fila por medidor (datos de recibo y pago en la primera fila de la persona).
   A la derecha, un bloque gris "Datos para restaurar": ID usuario, fecha anterior, consumo anterior, estado de lectura, registrado por, categoría, historial_m3, consumo total y los montos del recibo (agua, desagüe, cargo fijo, IGV, redondeo).
3. `USUARIOS`: el padrón completo (ID, conexión, nombre, sector, dirección, categoría, activo, medidores separados por coma).
4. `CONFIG`: el documento `config/general` completo (una celda JSON + una tabla legible).
Fórmulas simples donde ayuden (consumo = actual − anterior) y formato legible. Prueba que abra en Excel y en LibreOffice.

## Parte B — Restauración (`scripts/restaurar_excel.py`)
`python scripts/restaurar_excel.py --archivo respaldos/RESPALDO_2026-09.xlsx [--solo usuarios|config|mes] [--simular] [--sobrescribir] [--credenciales otra_clave.json]`
- `--simular` (por defecto la primera vez): muestra qué escribiría y las diferencias con lo que hay en Firebase.
- Sin `--sobrescribir`, **nunca pisa** documentos existentes.
- Valida el `LEEME` (versión, conteos). Tras restaurar, vuelve a contar documentos y compara la suma de `total_a_pagar`; informa si no coincide.
- Restaura en el orden: config → usuarios → mes. Para varios meses, ejecutar el script por cada archivo.
- Debe funcionar contra un **proyecto nuevo** de Firebase usando otra clave de servicio.
- **Prueba de ida y vuelta**: exportar a Excel → restaurar en un repositorio simulado en memoria → comparar con el original (iguales campo por campo).

## Parte C — Modo contingencia (sin internet o con Firebase caído)
- Si al iniciar no se puede conectar, el programa ofrece **"Trabajar con el último respaldo"**: carga los datos del Excel más reciente en modo de consulta (buscar usuarios, ver deudas, ver observaciones, reimprimir PDF) mediante un repositorio alterno con la misma interfaz que `firebase_client.py`. Muestra un banner permanente "MODO RESPALDO".
- **Cola local de cambios** (`cola_pendiente.json`): los cobros y correcciones hechos sin conexión se guardan en la cola, se aplican a la vista en memoria y se **envían solos** al volver la conexión (reintento cada 60 segundos mientras el programa esté abierto). Banner "N cambios pendientes de enviar" con botón Reintentar. Si el documento cambió en el servidor mientras tanto, pide decidir.
- El respaldo en Excel debe seguir generándose aun sin conexión.

## Parte D — Documento `docs/PLAN_CONTINGENCIA.md` (en español, para la secretaria)
Pasos cortos y numerados para estos casos:
1. **Sin internet**: seguir con el programa (cola local) y qué banner aparece.
2. **Firebase caído un rato**: igual que el caso 1; los lectores siguen leyendo sin conexión y sus datos suben luego.
3. **Se borraron datos por error**: restaurar solo ese mes o solo usuarios desde el Excel con `--solo`.
4. **Se perdió o bloqueó el proyecto de Firebase**: crear proyecto nuevo (Firestore `(default)`, publicar las reglas de seguridad, generar nueva clave de servicio), cambiar `serviceAccountKey.json`, restaurar config → usuarios → mes con `--simular` y luego real. La app móvil necesita el nuevo `google-services.json` y reinstalarse, y se deben recrear las cuentas de los lectores.
5. **Copias fuera de la PC**: copiar `respaldos/` a una memoria USB o a una carpeta de Google Drive cada semana (nunca depender de una sola copia).

## Parte E — Pulido
`iniciar.bat` (crea el entorno si falta, instala dependencias, inicia y abre el navegador), `README.md` completo en español, revisión de mensajes de error, y una lista de **pruebas manuales** (checklist) para la secretaria.

## Criterios de aceptación
- Un respaldo de prueba restaurado en el repositorio simulado coincide campo por campo con el original.
- `restaurar_excel.py --simular` nunca escribe.
- El modo contingencia abre con la red desconectada y permite buscar y ver observaciones.
- Cobros hechos sin conexión se envían al reconectar sin duplicarse.

## Al terminar
Resume y entrega la checklist de pruebas manuales.
