# AGENTS.md — App de lecturas CAAPD Ispacas (Android)

> Este archivo va en la **raíz del proyecto** de Android Studio. Describe el proyecto de forma permanente. Hay capturas de la interfaz esperada en `docs/capturas/` y la estructura exacta de los datos en `docs/firestore_ejemplo_v2_1.json`. Si falta un dato o algo se contradice, **pregunta antes de inventar**.

## Qué es
App para los **lectores** del comité de agua CAAPD Ispacas. Recorren las casas, leen el medidor y registran la lectura. Debe funcionar **sin internet** y **sin pedir iniciar sesión de nuevo**. No factura, no cobra y no crea usuarios (eso lo hace el programa de la secretaria).

## Stack (no agregues más)
Kotlin, Jetpack Compose con Material 3, Navigation Compose, ViewModel con StateFlow, Firebase BoM con `firebase-auth` y `firebase-firestore`, Gradle Kotlin DSL, plugin `com.google.gms.google-services`. minSdk 24. Paquete `com.caapd.lecturas`. Sin Hilt, sin Room, sin otras librerías. Textos en español. Todo el tema (colores, tipografía, formas) en un solo archivo `Theme.kt`.

## Firebase (Firestore `(default)`, autenticación correo y contraseña)
- `config/general`: `mes_actual {periodo, estado}` (`ABIERTO`, `CERRADO` o `FACTURADO`), `sectores[]`, `observaciones[] {codigo, texto, alerta}`.
- `mes_{periodo}/{id_usuario}`: `nro_conexion`, `nombre`, `sector`, `direccion`, `medidores[]`, `consumo_total_m3`, `historial_m3[]` (más campos de recibo que la app NO toca).
- Cada entrada de `medidores[]`: `nro_medidor` (texto), `lectura_anterior`, `fecha_anterior`, `consumo_anterior`, `lectura_actual`, `fecha_lectura`, `estado_lectura` (`PENDIENTE`, `LEIDO`, `SIN_ACCESO`), `novedad` (código de observación), `nota`, `registrado_por`.
- Las reglas de seguridad solo permiten actualizar `medidores` y `consumo_total_m3`.
- `nro_medidor` y `nro_conexion` son **texto**: nunca los conviertas a número (perderían los ceros).

## Sesión: que NO vuelva a pedir login
- Solo correo y contraseña de Firebase. **Sin Google Sign-In ni "sincronizar con Google".**
- Al iniciar, si `FirebaseAuth.currentUser != null`, entra directo, **incluso sin internet**. Solo muestra el login si es null.
- **Nunca** llames a `signOut()` automáticamente. Si llamas a `reload()` o al refresco del token y falla por red o por cualquier error, **ignóralo**. Solo cierra sesión por una acción explícita del usuario ("Cerrar sesión" en un menú discreto, con confirmación).
- El token se renueva solo; no escribas lógica de expiración propia.

## Pantallas (replica `docs/capturas/`)
**1. Login**: correo y contraseña, botón Entrar, mensajes de error claros.

**2. Sectores**: lista desde `config.sectores` con el avance de cada uno (leídos de total), el periodo abierto y estado. Si el estado no es `ABIERTO`, avisa y no permitas ingresar lecturas (solo ver).

**3. Lista del sector**
- Barra superior azul con el nombre del sector, "N conexiones · M pendientes" y un punto de conexión (verde si hay internet, gris si no).
- Buscador "Buscar nombre, conexión o medidor". Chips: Todos, Pendientes, Leídos, Sin acceso.
- Tarjetas blancas redondeadas: nombre (en mayúsculas), "Conex. 000527 · Med. 2001887", dirección. A la derecha un chip de estado ("Leído" en verde) y "105 → 118". Si hay varios medidores: "Med. 000100 +1" y "1/2 leídos".
- Botón flotante ámbar "Siguiente pendiente ›". Orden alfabético por nombre.
- Los datos del sector se cargan **una vez** y se filtran en memoria.

**4. Lectura**
- Barra con sector y "Conex. X · Med. Y". Tarjeta con nombre, dirección y chip de estado. Si ya hay lectura, texto ámbar: "Registrado por {registrado_por}. Al guardar se reemplazará."
- Dos recuadros: **LECTURA ANTERIOR** (solo lectura, NO se puede modificar) y **LECTURA ACTUAL** (único campo editable, teclado numérico, enfocado al entrar).
- Debajo de la anterior: **"Consumo anterior: N m³"**, para ayudar cuando no se vea el medidor. Botón secundario "Estimar con consumo anterior": rellena actual = anterior + consumo_anterior y marca la observación `LECTURA_ESTIMADA`.
- Recuadro **CONSUMO** en verde, solo lectura, calculado en vivo; no se puede modificar.
- **Observación**: chips deslizables desde `config.observaciones` (Normal, Medidor dañado, Medidor empañado/ilegible, Fuga visible, Sin medidor, Casa cerrada, Lectura estimada, Cambio de medidor, Otro). Por defecto `NORMAL`. Es importante: la secretaria la verá al cobrar. Si el catálogo no carga, usa esta lista como respaldo.
- Campo "Nota libre (opcional)".
- Botón verde "Guardar y siguiente pendiente" y botón secundario "Sin acceso / casa cerrada" (marca `SIN_ACCESO`, `novedad = CASA_CERRADA`, sin lectura, y pasa al siguiente).
- Varios medidores: selector de medidor arriba; al guardar pasa al siguiente medidor pendiente de la misma persona y luego a la siguiente persona.

## Reglas de lectura
- Consumo de un medidor: si actual ≥ anterior → actual − anterior. Si actual < anterior y la observación es `CAMBIO_MEDIDOR` → consumo = actual (medidor nuevo desde cero). Si no → error: "La lectura actual es menor que la anterior. Si cambiaron el medidor, elige Cambio de medidor."
- Si el consumo es mayor a 3 veces el promedio de `historial_m3` o mayor a 100 m³: diálogo "¿Es correcto?" (no bloquea).
- Guardar: `fecha_lectura` = hoy (aaaa-mm-dd), `estado_lectura = LEIDO`, `registrado_por` = correo del usuario. Un solo `update` de `medidores` (lista completa, conservando los campos de cada medidor) y `consumo_total_m3` (suma; `null` si queda algún medidor sin leer).

## Búsqueda inteligente (con pruebas unitarias)
- Solo dígitos y menos del mínimo (medidor 6, conexión 6): primero la coincidencia exacta con ceros a la izquierda y después los que contengan esos dígitos. `3386` → `003386`; `796` → `000796`.
- Con el mínimo o más dígitos: tal cual, **sin agregar ceros** (`123456` sigue siendo `123456`).
- Con letras: en el nombre, sin mayúsculas ni tildes, todas las palabras en cualquier orden.

## Sin conexión
- Caché persistente de Firestore habilitada explícitamente.
- Cargar un sector: `collection("mes_" + periodo).whereEqualTo("sector", sector).get()`, una vez al entrar; botón Actualizar manual. **Sin listeners en tiempo real.**
- Guardar: actualiza la lista local al instante y **no esperes** la respuesta del servidor; muestra "Guardado. Se enviará cuando haya internet". Maneja errores con mensaje claro.

## Diseño
Uso al aire libre: alto contraste, letra y botones grandes. Paleta aproximada de las capturas: barra azul `#0B6E99`, fondo gris azulado claro, tarjetas blancas con sombra suave, guardar verde `#1F9254`, botón flotante ámbar, secundario celeste.

## Pruebas unitarias
Consumo (normal, menor sin y con CAMBIO_MEDIDOR), consumo atípico, consumo_total con medidores sin leer, búsqueda con ceros (tabla de arriba) y selección del siguiente pendiente.

## No hagas
Recibos, pagos, usuarios, Google Sign-In, listeners en tiempo real, ni escribir campos distintos de `medidores` y `consumo_total_m3`.
