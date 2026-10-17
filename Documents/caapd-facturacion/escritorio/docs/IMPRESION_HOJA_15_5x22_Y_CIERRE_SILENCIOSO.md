# Recibos en hoja física 15.5 × 22 cm y corrección del cierre silencioso

## 1. Recibo PDF centrado en la hoja física

**Problema.** La página del PDF medía 13.97 × 21.59 cm (media carta) con el fondo a
página completa. La hoja real mide 15.5 × 22 cm y la impresora no imprime 1.9 cm a
cada lado, 0.2 cm arriba y 0.1 cm abajo: el recibo salía descentrado y recortado.

**Solución (`servicios/generador_pdf.py`, bloque GEOMETRIA DE IMPRESION).**

| Concepto | Valor |
|---|---|
| Página del PDF | 15.5 × 22.0 cm (= hoja física) |
| Bordes blancos | 1.9 cm izq/der · 0.5 cm arriba/abajo |
| Área útil (fondo) | 11.7 × 21.0 cm, centrada |
| Espacio de diseño | 13.97 × 21.59 cm (coordenadas originales y PNG 1650×2550) |

- El fondo PNG se dibuja ocupando exactamente el área útil.
- La clase `_Lienzo` proyecta todas las coordenadas originales al área útil:
  posiciones `(x, y) → (ox + x·sx, oy + y·sy)`, fuentes escaladas por `sx` (no se
  deforman), QR cuadrado.
- `MODO_AJUSTE = "estirar"` (ocupa los 11.7 × 21 exactos; el fondo se alarga ~16 %
  en vertical) o `"proporcional"` (sin deformar; deja ~1.96 cm arriba/abajo).
- Calibración: `DESPLAZAMIENTO_X_CM / Y_CM` (cm reales, mueve todo),
  `AJUSTE_TEXTO_Y_CM` (solo texto respecto al fondo), `AJUSTE_TALON_Y_CM`,
  `DIBUJAR_MARCO_GUIA = True` para imprimir un marco y medir con regla.

**Al imprimir:** papel personalizado 15.5 × 22 cm y escala "Tamaño real / 100 %"
(nunca "Ajustar a página").

**Imágenes de fondo.** No es obligatorio cambiarlas. Para evitar el estirado
vertical, rehacerlas a proporción 11.7 × 21 (p. ej. **1382 × 2480 px** a 300 dpi)
extendiendo la zona plana del centro, no estirando.

Pruebas: `tests/test_generador_pdf_hoja.py`.

## 2. Cierre del programa en «Extraer lecturas de los lectores»

**Síntoma.** Al confirmar «Sí, traer lecturas» el programa se cierra y la consola solo
muestra `QThreadStorage: entry N destroyed before end of thread 0x...`. Ese mensaje
es un *síntoma*: Qt está destruyendo sus objetos globales (el proceso termina)
mientras un hilo del `QThreadPool` sigue vivo.

**Causa.** La descarga por REST (`servicios/firestore_rest.py`) seguía ejecutando
`import firebase_client` dentro del hilo de trabajo para leer `FIREBASE_KEY_PATH`.
Como el programa es *local-first* y no toca Firebase al arrancar, esa era la
**primera** importación de `firebase_admin → google.cloud.firestore → gRPC (cygrpc)`
y ocurría en un hilo secundario. La pila nativa de gRPC inicializada fuera del hilo
principal es exactamente el componente que ya había provocado cierres por
*access violation* en Windows.

**Corrección (en capas).**

1. `servicios/firestore_rest.py`: `ruta_credenciales()` ya **no importa**
   `firebase_client`; resuelve la clave con `_ruta_clave_configurada()` (variable de
   entorno, `config_local.py`, rutas por defecto). Nueva `precargar_dependencias()`.
2. `ui/hilos.py`: `precargar_firebase_en_hilo_principal()` importa firebase_admin/gRPC
   y google-auth desde el hilo GUI (solo importación, 0 lecturas);
   `instalar_diagnostico_cierre(app)` registra en `logs/hilos.log` el motivo de
   cualquier cierre (`lastWindowClosed`, `aboutToQuit`, excepciones no capturadas);
   cada Worker registra inicio y fin.
3. `main.py`: `app.setQuitOnLastWindowClosed(False)` + precarga diferida 1.5 s tras
   abrir la ventana. El programa solo termina cuando el usuario cierra la ventana
   principal (`VentanaPrincipal.closeEvent` → `app.quit()`), y ese cierre ya se
   bloquea si hay Workers activos.

**Si volviera a ocurrir**, revisar `escritorio/logs/hilos.log` (motivo del cierre,
hilo iniciado/terminado) y `escritorio/logs/crash.log` (fallos nativos vía
`faulthandler`).

Pruebas: `tests/test_firestore_rest_sin_grpc.py`.
