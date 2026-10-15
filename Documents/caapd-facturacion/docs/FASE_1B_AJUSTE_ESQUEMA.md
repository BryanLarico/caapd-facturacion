# FASE 1B — Ajuste del esquema y de los códigos (sobre lo que ya existe)

**Cómo usarlo en Antigravity:** conversación nueva, modo Planning, y escribe:
`Lee docs/CONTEXTO.md y ejecuta docs/FASE_1B_AJUSTE_ESQUEMA.md. No rehagas lo que ya existe: audita y completa.`

## Situación
La Fase 0 y la Fase 1 ya están hechas (el programa abre, el pie de página cuenta lecturas y escrituras, las pantallas Usuarios y Recibos dicen "disponible en la Fase N"). El esquema evolucionó a la **v2.1**: observaciones, consumo anterior, estado de lectura, lector y estados del mes. Esta fase alinea el código con `docs/CONTEXTO.md` y `docs/firestore_ejemplo_v2_1.json`.

## Tareas
1. **Auditoría (primero, sin cambiar nada).** Revisa el código actual y dame una lista corta de: qué cumple, qué falta y qué contradice el esquema v2.1. Espera mi OK antes de modificar.
2. **codigos.py** (módulo puro) con pruebas:
   - `completar_ceros(valor, minimo)`: solo si son solo dígitos y tiene menos que `minimo`; si no, devuelve igual.
   - `normalizar_medidor`, `normalizar_conexion`, `normalizar_dni`, `normalizar_recibo`.
   - `es_id_pendiente(id_usuario)`: verdadero si tiene guion.
   - `buscar(consulta, registros)`: la búsqueda inteligente de la sección 4 de CONTEXTO.md, reutilizable en Usuarios, Lecturas y Cobros.
3. **Pruebas de formato**: 100 → 000100, 3200 → 003200, 990991 → 990991, **123456 → 123456**, 22392996 → 22392996, DNI 7654321 → 07654321, conexión 796 → 000796, recibo 58391 → 000058391. Pruebas de búsqueda: la tabla de la sección 4.
4. **Configuración**: agrega al soporte de `config/general` los campos nuevos (`observaciones`, `categorias.*.modo_rangos`, estados del mes `ABIERTO/CERRADO/FACTURADO`). Actualiza `scripts/sembrar_config.py` para que sea **idempotente y no pise lo ya editado**: solo agrega las claves que falten.
5. **calculos.py**: soporta `modo_rangos` "unico" y "tramos". Pruebas:
   - Caso 1: medidor 42→58, precio 1.00, desagüe 0, cargo fijo 1.50, sin deuda, IGV apagado → consumo 16, total 17.50, meses 1, AZUL.
   - Caso 2: medidores 42→61 y 120→124, IGV 18% activo, recibo anterior 18.50 sin pagar con 1 mes → consumo 23, IGV 4.41, redondeo 0.01, total 47.40, meses 2, NARANJA.
   - Caso 3 (tramos): rangos 0–10 a 1.00 y 10 en adelante a 1.50, consumo 16 → agua 19.00 (en modo "unico" sería 24.00).
6. **Hook de respaldo**: crea `respaldo.py` con `on_datos_cambiados()` vacío (solo registra en el log). La Fase 6 lo implementa.
7. Verifica que NINGÚN módulo fuera de `firebase_client.py` use Firestore directamente; si lo hay, muévelo.
8. Actualiza `README.md` con los cambios.

## Criterios de aceptación
- `pytest` pasa completo.
- El programa sigue abriendo y el diseño no cambió.
- `sembrar_config.py --simular` muestra qué claves agregaría sin escribir nada.

## Al terminar
Resume, indica cómo probar y **espera mi OK** para la Fase 2.
