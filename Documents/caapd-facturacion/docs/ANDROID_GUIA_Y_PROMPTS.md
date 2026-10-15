# Android Studio — Guía paso a paso y prompts por fase

App de **lecturas** (la que usan los lectores). Esta guía crea el proyecto desde cero, lo conecta a Firebase y le da las instrucciones al asistente de Android Studio.
> Los nombres de los menús pueden variar un poco según la versión de Android Studio.

---
## PARTE 1 — Crear el proyecto

### Paso 1. Requisitos
- Android Studio estable reciente (con el SDK instalado) y una cuenta de Google para el asistente Gemini.
- Un celular Android con **Depuración USB** activada, o un emulador.

### Paso 2. Nuevo proyecto
1. Pantalla de bienvenida → **New Project** (o *File → New → New Project*).
2. Plantilla **Empty Activity** (la de Compose) → **Next**.
3. Completa:
   - **Name:** `Lecturas CAAPD`
   - **Package name:** `com.caapd.lecturas` (debe ser **idéntico** al que registres en Firebase)
   - **Save location:** la carpeta que prefieras
   - **Minimum SDK:** API 24
   - **Build configuration language:** Kotlin DSL (`build.gradle.kts`)
4. **Finish** y espera a que termine el *Gradle sync* (barra inferior).

### Paso 3. Conectar con Firebase
1. En la consola de Firebase: engranaje → **Configuración del proyecto** → pestaña **General** → *Tus apps* → icono **Android**.
2. Nombre del paquete: `com.caapd.lecturas`. Apodo opcional. **No necesitas SHA-1** (usas correo y contraseña). **Registrar app**.
3. **Descarga `google-services.json`**.
4. En Android Studio cambia la vista del panel izquierdo de **Android** a **Project** (menú desplegable arriba del panel).
5. Copia `google-services.json` dentro de la carpeta `app/` (al lado de `app/build.gradle.kts`).
6. Las demás dependencias las agrega el asistente en la Fase 1.

### Paso 4. Poner las instrucciones y los datos del proyecto
1. En vista **Project**, clic derecho sobre el nombre del proyecto (raíz) → **New → File** → `AGENTS.md` → pega el contenido del archivo `AGENTS.md` que te entrego.
2. Clic derecho en la raíz → **New → Directory** → `docs`. Dentro, crea la carpeta `capturas`.
3. Copia a `docs/` el archivo `firestore_ejemplo_v2_1.json` y a `docs/capturas/` las capturas de la app (lista del sector y pantalla de lectura).

Android Studio lee automáticamente un `AGENTS.md` en la raíz del proyecto para tener las instrucciones presentes en cada conversación. Si el asistente parece no tenerlo en cuenta, adjúntalo con `@AGENTS.md` en el chat.

### Paso 5. Abrir el asistente en modo Agente
1. *View → Tool Windows → Gemini* (o el icono de Gemini a la derecha). Inicia sesión con tu cuenta de Google.
2. Cambia al modo **Agent** (selector junto a la caja de texto). Este modo edita varios archivos y corrige errores por sí solo.
3. Adjunta con el clip o con `@` los archivos que cada prompt menciona (el JSON y las capturas).
4. Pega el prompt de la fase, revisa los cambios que propone (aceptar o revertir) y **ejecuta la app** (botón ▶) en tu celular o emulador.
5. **Una conversación nueva por fase.** No pases a la siguiente hasta probar la actual.

> Si prefieres usar Claude: abre esta misma carpeta en Antigravity con modo Planning y pega los mismos prompts; compila y prueba siempre desde Android Studio.

### Paso 6. Crear las cuentas de los lectores
Firebase → **Authentication** → **Usuarios** → **Agregar usuario** (correo y contraseña por lector). **No cambies esas contraseñas después**: la sesión de un lector solo se invalida si se elimina o deshabilita su cuenta, o si se cambia su contraseña o correo.

---
## PARTE 2 — Prompts (uno por conversación)

### FASE A1 — Proyecto, tema y sesión
```text
Lee AGENTS.md, docs/firestore_ejemplo_v2_1.json y mira las capturas de docs/capturas/.

FASE A1. Haz solo esto:
1. Configura Gradle (plugin google-services en el proyecto y en app, Firebase BoM con firebase-auth y firebase-firestore, Compose, Navigation Compose). Compila sin errores.
2. Crea Theme.kt con la paleta aproximada de las capturas (barra azul, fondo gris azulado, verde, ámbar, celeste), tipografía y formas redondeadas. Todo el estilo debe poder cambiarse desde ese archivo.
3. Navegación con 4 destinos vacíos: Login, Sectores, ListaSector, Lectura.
4. Pantalla de Login (correo y contraseña) y la lógica de sesión de AGENTS.md: si currentUser no es null entra directo, incluso sin internet; nunca cierra sesión automáticamente; errores de red se ignoran.
5. Inicializa Firestore con caché persistente explícita.
6. Un menú discreto con "Cerrar sesión" con confirmación.
Al terminar explícame cómo probar: iniciar sesión, cerrar la app, volver a abrirla (debe entrar sin pedir login) y repetir con el modo avión. Detente y espera mi OK.
```

### FASE A2 — Sectores y lista de personas
```text
Lee AGENTS.md y mira docs/capturas/ (lista del sector).

FASE A2. Haz solo esto:
1. Pantalla Sectores: lee config/general una vez (sectores, mes_actual, observaciones) y muestra cada sector con su avance. Si mes_actual.estado no es ABIERTO, avisa y deja solo consulta.
2. Pantalla ListaSector idéntica a la captura: barra azul con el sector, "N conexiones · M pendientes" y punto verde/gris de internet; buscador; chips Todos / Pendientes / Leídos / Sin acceso; tarjetas; botón flotante "Siguiente pendiente".
3. Carga el sector UNA vez con whereEqualTo("sector", ...) .get() sobre la colección "mes_" + periodo, y filtra en memoria. Botón Actualizar manual. Sin listeners en tiempo real.
4. Búsqueda inteligente de AGENTS.md (3386 -> 003386; 796 -> 000796; 123456 se queda igual; nombres sin tildes) como función pura con pruebas unitarias.
5. Personas con varios medidores: "Med. 000100 +1" y "1/2 leídos".
Prueba con docs/firestore_ejemplo_v2_1.json cargado en un mes de prueba. Explícame cómo probar y espera mi OK.
```

### FASE A3 — Pantalla de lectura
```text
Lee AGENTS.md y mira docs/capturas/ (pantalla de lectura).

FASE A3. Haz solo esto:
1. Pantalla Lectura idéntica a las capturas: tarjeta de la persona (con el texto ámbar "Registrado por ... Al guardar se reemplazará." si ya hay lectura), LECTURA ANTERIOR (no editable), LECTURA ACTUAL (único campo editable, teclado numérico) y CONSUMO (no editable, verde, en vivo).
2. Muestra "Consumo anterior: N m³" bajo la lectura anterior y el botón "Estimar con consumo anterior" (rellena la actual y marca LECTURA_ESTIMADA).
3. Chips de Observación desde config.observaciones (con la lista de respaldo de AGENTS.md) y la Nota libre. La observación se guarda en "novedad" y la nota en "nota".
4. Botón "Guardar y siguiente pendiente" y botón "Sin acceso / casa cerrada".
5. Reglas de consumo y avisos de AGENTS.md (lectura menor sin y con CAMBIO_MEDIDOR, consumo atípico con confirmación "¿Es correcto?"), como funciones puras con pruebas unitarias.
6. Guardado con un solo update de "medidores" y "consumo_total_m3"; registrado_por = correo del usuario; fecha_lectura = hoy.
7. Varios medidores: selector arriba y avance al siguiente pendiente de la misma persona, luego a la siguiente persona.
Explícame cómo probar cada regla y espera mi OK.
```

### FASE A4 — Sin conexión, pruebas y APK
```text
Lee AGENTS.md.

FASE A4. Haz solo esto:
1. Guardar sin internet: actualizar la lista local al instante, no esperar al servidor y mostrar "Guardado. Se enviará cuando haya internet". Maneja errores con mensajes claros.
2. Indicador de conexión (punto verde/gris) con ConnectivityManager.
3. Revisa que la app nunca cierre sesión sola ni pida login al abrir sin internet.
4. Completa las pruebas unitarias de AGENTS.md y corre todas.
5. Revisa que no haya listeners en tiempo real y que cada guardado sea exactamente 1 escritura.
6. Pulido: iconos, nombre de la app "Lecturas CAAPD", textos en español, rotación bloqueada en vertical.
Dame la checklist de pruebas manuales (modo avión, guardar sin internet y reconectar, medidor con observación, sin acceso, persona con 2 medidores) y los pasos para generar el APK.
```

---
## PARTE 3 — Probar y repartir el APK
- **Probar sin internet:** activa el modo avión, abre la app (debe entrar sin login), guarda una lectura y vuelve a conectar. En el programa de la PC debe aparecer.
- **Generar el APK:** *Build → Build Bundle(s) / APK(s) → Build APK(s)*. Al terminar, *locate* abre la carpeta del archivo `.apk`.
- **Instalar en el celular de cada lector:** pasa el `.apk` por cable o WhatsApp y permite *instalar desde fuentes desconocidas*. Inicia sesión **una sola vez** con la cuenta de ese lector.
