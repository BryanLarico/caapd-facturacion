# FASE 1D — Corregir la lógica compartida (sirve a las dos interfaces)

**Antigravity:** conversación nueva, modo Planning:
`Lee docs/CONTEXTO.md y ejecuta docs/FASE_1D_LOGICA_COMPARTIDA.md. Solo toca calculos.py, codigos.py y tests/.`

## Por qué
La revisión de `calculos.py` y `codigos.py` encontró diferencias con `docs/CONTEXTO.md`. Se corrigen **una sola vez**, de forma retrocompatible, para que HTML y escritorio usen la misma lógica. **No toques** `app.py`, `templates/`, `static/`, `iniciar.bat`, `config_local.py` ni `firebase_client.py`.

## Tareas
1. **Auditoría primero.** Compara `calculos.py`/`codigos.py` y sus pruebas con CONTEXTO.md (secciones 3, 4 y 5). Resume lo que difiere y **espera mi OK**.
2. **`modo_rangos`** en `calcular_monto_agua` y `calcular_recibo`: lee `categoria.get("modo_rangos", "unico")`. Con `"unico"` el comportamiento actual no cambia. Con `"tramos"`, cada tramo se cobra a su precio y se suma. Prueba: rangos 0–10 a 1.00 y 10 en adelante a 1.50, consumo 16 → "tramos" = 19.00 y "unico" = 24.00.
3. **Consumo de un medidor** (regla de CONTEXTO §3): nueva función pura `consumo_medidor(anterior, actual, novedad=None)`. Si actual ≥ anterior, actual − anterior. Si es menor y la novedad es `CAMBIO_MEDIDOR`, consumo = actual. En otro caso, `ValueError` con mensaje en español. `calcular_recibo` debe usarla en lugar de `max(0, ...)` (hoy un consumo negativo se convierte en 0 sin avisar).
4. **`numero_a_letras`**: hoy escribe "UN" donde debe decir "UNO". Casos obligatorios: 17.50 → "DIECISIETE 50/100 SOLES"; 21.00 → "VEINTIUNO 00/100 SOLES"; 31.00 → "TREINTA Y UNO 00/100 SOLES"; 100.00 → "CIEN 00/100 SOLES"; 101.00 → "CIENTO UNO 00/100 SOLES"; 1001.00 → "MIL UNO 00/100 SOLES"; 21000.00 → "VEINTIÚN MIL 00/100 SOLES"; 2000.00 → "DOS MIL 00/100 SOLES"; 0.50 → "CERO 50/100 SOLES"; 1234.00 → "MIL DOSCIENTOS TREINTA Y CUATRO 00/100 SOLES". Evita el error de redondeo de centavos (por ejemplo 2.999 no debe dar "100/100").
5. **`calcular_nivel_mora`**: para un recibo pagado devuelve `color = None` (la interfaz usa su color base) en lugar de un verde fijo en el código.
6. **Pruebas:** agrega o ajusta las de `tests/`. Si una prueba existente contradice CONTEXTO.md, cámbiala y **dímelo explícitamente**. Mantén los casos 1 y 2 de siempre:
   - Caso 1: medidor 42→58, precio 1.00, desagüe 0, cargo fijo 1.50, sin deuda, IGV apagado → consumo 16, total 17.50, meses 1.
   - Caso 2: medidores 42→61 y 120→124, IGV 18%, recibo anterior 18.50 sin pagar con 1 mes → consumo 23, IGV 4.41, redondeo 0.01, total 47.40, meses 2.
7. Verifica que `python -m pytest` pasa y que la aplicación HTML sigue abriendo igual (no se usa `calcular_recibo` todavía).

## Al terminar
Resume los cambios archivo por archivo y **espera mi OK**.
