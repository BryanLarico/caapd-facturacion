# Guía: «Abrir mes nuevo» y «Actualizar»

Esta guía describe el funcionamiento de la aplicación de escritorio en su modo
normal, **local-first**. En este modo los archivos Excel de `Base de datos/` son
la fuente de verdad y Firebase es un espejo para la aplicación móvil de los
lectores.

## Dónde se guardan los padrones

La carpeta local está junto al programa:

```text
escritorio/
└── Base de datos/
    ├── PADRON_MES_2026-09.xlsx
    └── PADRON_MES_2026-10.xlsx
```

La aplicación reconoce archivos con el patrón `PADRON_MES_aaaa-mm.xlsx`.
Al iniciar, carga y consolida los padrones disponibles; el más reciente se
convierte en el mes activo. Si encuentra más de un archivo para un periodo,
prioriza el nombre canónico y avisa que ignorará los duplicados para evitar
mezclar bases.

Cada padrón Excel integral conserva las hojas de datos del mes, las hojas por
sector, `USUARIOS` y `CONFIG` (además de la hoja informativa `LEEME`). Entre
otros datos, contiene el padrón de usuarios y medidores, lecturas, información
de facturación y configuración. La estructura depende del formato de Excel que
se haya importado.

## Botón «Abrir mes nuevo»

El botón está en **Lecturas del mes**. Abre un formulario para indicar el
periodo `AAAA-MM`, la fecha de emisión y la fecha de vencimiento. El periodo se
sugiere usando el periodo siguiente y el mes calendario actual. El formulario
consulta si el periodo está disponible antes de abrirlo.

**Precaución en el modo local-first actual:** el método
`verificar_periodo_disponible` de `ServicioDatosPadron` actualmente devuelve
que el periodo está disponible sin comprobar si ya existe su Excel. Abrir un
periodo cuyo archivo ya existe puede reemplazar
`PADRON_MES_aaaa-mm.xlsx`. Antes de confirmar, compruebe que ese nombre no
exista en `Base de datos/`; no use «Abrir mes nuevo» para corregir o regenerar
un mes ya creado.

Antes de permitir la apertura, el programa comprueba el estado del mes activo.
Un mes `ABIERTO` impide crear otro. Puede avanzarse desde un mes `CERRADO` si
todas sus lecturas están completas; también puede avanzarse desde uno
`FACTURADO`.

Al confirmar:

1. La aplicación crea un documento nuevo por cada usuario activo y prepara un
   registro nuevo por cada medidor.
2. Busca el padrón disponible más reciente cuyo periodo sea anterior al nuevo.
   Por ejemplo, al crear octubre desde septiembre, usa septiembre como origen.
3. Copia al nuevo mes los datos vigentes del usuario y, por cada medidor que
   coincida por número, usa la `lectura_actual` del mes anterior como
   `lectura_anterior` del nuevo. Copia también la fecha de esa lectura y su
   consumo previo cuando están disponibles.
4. Conserva la serie de `historial_m3` y agrega el consumo del mes anterior si
   está registrado.
5. Calcula el saldo pendiente del mes anterior como
   `max(0, total_a_pagar - monto_pagado)` y ajusta `meses_adeudados`. Si el
   recibo anterior está totalmente pagado, el saldo queda en cero y el contador
   comienza en uno.
6. Inicializa los campos propios del nuevo mes: lectura actual vacía, estado
   `PENDIENTE`, sin nota ni lector asociado, y sin recibo ni pago del nuevo mes.
   No copia al mes nuevo el importe pagado, el número de recibo ni la lectura
   actual como si fueran registros del nuevo periodo.
7. Guarda el padrón mensual nuevo en
   `Base de datos/PADRON_MES_aaaa-mm.xlsx`, establece el periodo y el estado
   `ABIERTO`, y recarga la pantalla de Lecturas.

La creación muestra un indicador de carga y se ejecuta en segundo plano para no
bloquear la interfaz.

### Ejemplo: septiembre → octubre

En el archivo real `PADRON_MES_2026-09.xlsx`, el usuario `02150722` tiene el
medidor `6659665` con lectura anterior `513`, lectura actual `520`, fecha de
lectura `2026-09-25` y consumo `7`. Cuando se crea octubre tomando septiembre
como origen, el resultado esperado para ese medidor es:

| Campo del padrón de octubre | Valor inicial |
|---|---:|
| Lectura anterior | 520 |
| Fecha anterior | 2026-09-25 |
| Consumo anterior | 7 |
| Lectura actual | Vacía |
| Estado | PENDIENTE |

El `PADRON_MES_2026-10.xlsx` que ya existe se creó antes de incorporar este
traspaso: en el archivo revisado hay 28 usuarios y 29 medidores, todos sin
lectura actual, y ese medidor aparece con lectura anterior `0`. Ese archivo se
dejó intacto durante la corrección. Si se intenta abrir nuevamente octubre en
el modo local-first actual, el guardado puede reemplazarlo; por eso se debe
confirmar que el periodo no exista antes de usar el botón. El traspaso se aplica
al generar un periodo nuevo a partir de un padrón previo.

## Botón «Actualizar»

En modo local-first abre **Sincronización con Lectores Móviles**. Ofrece tres
acciones: reemplazar la ventana de meses publicada, publicar solo el mes nuevo
o descargar lecturas desde los teléfonos.

### «Traer lecturas de los lectores» — Nube → Excel

1. Lee los documentos de Firebase de la colección `mes_aaaa-mm` del mes activo.
2. Para cada usuario y medidor correspondiente, incorpora lecturas actuales,
   estado, novedad, nota, fecha de lectura y correo del lector.
3. Recalcula el consumo local cuando corresponda y escribe el resultado en el
   padrón Excel activo de `Base de datos/`.
4. Si una lectura local ya está registrada por `ADMIN`, la protege frente a un
   valor distinto de Firebase y reporta el conflicto; se conserva el valor de
   ADMIN.

Esta opción no reemplaza pagos ni datos de dinero. El resultado es una
actualización local; no vuelve a subir los datos a Firebase en el mismo paso.

### «Enviar mes a los lectores» — Excel → Nube

Antes de ejecutar pide escribir exactamente `CONFIRMAR`. Además, bloquea el
envío si detecta en la carpeta un Excel marcado como archivo de prueba.

Al continuar:

1. Intenta copiar los Excel de `Base de datos/` a
   `Base de datos/_historial/` como respaldo previo del envío.
2. Publica el mes activo y el periodo anterior más reciente que exista en los
   archivos locales, en sus colecciones `mes_aaaa-mm` de Firebase. Los
   documentos enviados incluyen los datos de usuarios, medidores y lecturas;
   se excluyen importes y otros datos de dinero.
3. Actualiza `config/general` en Firebase con el periodo activo, el estado, las
   fechas, los sectores y las observaciones disponibles.
4. Compara los documentos de las colecciones publicadas con el padrón local y
   elimina documentos sobrantes. También elimina las colecciones `mes_...`
   fuera de esa ventana de dos periodos y la colección obsoleta `usuarios`.
5. Registra la fecha del último envío en la configuración local y en el padrón
   mensual activo.

**Importante:** el envío reemplaza en Firebase los documentos de los meses que
publica y puede borrar datos móviles que no se hayan descargado antes. Antes de
enviar, use «Traer lecturas de los lectores» para conservar lecturas pendientes
de los teléfonos. Revise también que los Excel sean los correctos. La
confirmación escrita reduce errores accidentales, pero no convierte la acción
en reversible.

### «Publicar solo el mes actual» — Excel → Nube

Esta opción sirve para habilitar en la aplicación Android un periodo recién
creado sin ejecutar la limpieza amplia del envío anterior. Publica únicamente
los usuarios y medidores del mes activo en `mes_aaaa-mm` y actualiza
`config/general` para que los lectores seleccionen ese periodo. Agrega el nuevo
periodo a `periodos_disponibles` sin retirar los anteriores.

La publicación usa creación exclusiva: si `mes_aaaa-mm` ya contiene cualquier
documento, se detiene y no reemplaza lecturas existentes. Tampoco elimina
usuarios, documentos ni colecciones de otros meses. El padrón local no se
modifica. Si Firebase ya tiene datos del periodo, primero revise la situación y
use «Traer lecturas de los lectores» cuando corresponda.

El envío antiguo revisa las colecciones para buscar documentos obsoletos y
puede tardar mientras Firebase lista esos documentos. La barra inferior ahora
indica el mes o la colección que está revisando. Para un mes recién abierto,
use esta acción nueva; evita ese barrido y no reemplaza las bases anteriores.

### Cancelar y abrir la carpeta

`Cancelar` cierra el diálogo sin sincronizar. `Abrir carpeta 'Base de datos'`
abre la carpeta local en el Explorador de Windows; no sube ni descarga datos.

## Relación entre Excel y Firebase

En el modo normal, al iniciar, el programa usa `ServicioDatosPadron` y carga los
Excel locales. Abrir un mes nuevo escribe el nuevo padrón localmente; **no
crea por sí solo una colección en Firebase**. Para habilitar el periodo en la
app móvil, después de verificar el Excel se debe usar «Actualizar» →
«Enviar mes a los lectores».

Firebase usa colecciones mensuales (`mes_aaaa-mm`) para los datos de lecturas y
`config/general` para la configuración general. El envío y la descarga pasan
por `firebase_client.py`, que inicializa Firebase Admin y obtiene el cliente
Firestore cuando se necesita. Las operaciones de Firebase se realizan por
acción explícita; el arranque local-first no necesita descargar el padrón de
Firestore.

La aplicación también se puede iniciar explícitamente con `--firebase`; en ese
modo usa `ServicioDatosFirebase` en lugar del servicio local-first. Abrir un
mes en este modo delega a `firebase_client.abrir_mes`: lee el mes previo de
Firestore (o la semilla si no hay uno), crea la colección `mes_aaaa-mm` y
actualiza `config/general`. En este modo, «Actualizar» vuelve a cargar los
datos de Firebase en lugar de mostrar el diálogo con las tres acciones de
sincronización local-first. `--contingencia` selecciona el modo de contingencia,
en el que no se permite abrir meses.

## Ubicación de las credenciales para verificar Firebase

La ruta de la clave de Firebase Admin está configurada en
`config_local.py`, en `FIREBASE_KEY_PATH`. En esta instalación apunta al JSON
`escritorio/caapd-ispacas-optimizado-firebase-adminsdk-fbsvc-e6c4b2f0b0.json`,
que se encuentra junto a `config_local.py` en la carpeta del programa.
`firebase_client.py` utiliza esa ruta; si el archivo no está allí, admite la
variable de entorno `FIREBASE_KEY_PATH` y muestra un error con la ruta
configurada.

Para comprobar la configuración sin exponer secretos:

1. Verifique que la ruta de `FIREBASE_KEY_PATH` exista en el equipo donde corre
   el programa.
2. Revise que la identidad configurada tenga acceso al proyecto de Firebase
   esperado y a Firestore.
3. No copie el contenido del JSON en documentación, mensajes, capturas ni
   repositorios. Es una clave privada de servicio: no debe compartirse ni
   subirse a Git.

`PROYECTO_REAL_ID` en `config_local.py` identifica el proyecto real usado por
validaciones de seguridad del programa. La presencia de la clave por sí sola
no prueba que la conexión, los permisos o las reglas de Firestore sean
correctos; para comprobarlos hay que ejecutar una operación autorizada y
verificar el resultado en Firebase.

## Qué archivos puede modificar cada acción

| Acción | Archivos locales | Firebase |
|---|---|---|
| Abrir mes nuevo (modo local-first) | Crea o guarda `Base de datos/PADRON_MES_aaaa-mm.xlsx` para el nuevo periodo. | No escribe ni crea la colección del nuevo mes. |
| Traer lecturas | Actualiza y guarda el padrón activo `PADRON_MES_aaaa-mm.xlsx`. | Lee `mes_aaaa-mm`; no publica la copia Excel. |
| Enviar mes a lectores | Intenta copiar los Excel existentes a `Base de datos/_historial/` y actualiza la configuración/fecha de envío guardada en el padrón activo. | Escribe los dos periodos elegidos y `config/general`; elimina sobrantes y periodos fuera de la ventana indicada arriba. |
| Publicar solo el mes actual | No modifica archivos locales. | Crea exclusivamente documentos en `mes_aaaa-mm` (si la colección está vacía) y actualiza `config/general`; conserva los demás periodos y documentos. |
| Cancelar | Ninguno. | Ninguno. |
| Abrir carpeta | Ninguno. Solo abre el Explorador. | Ninguno. |

La sincronización de Windows o Google Drive con la carpeta es independiente:
el programa guarda los archivos localmente; el cliente de sincronización los
sube según su propia configuración.

## Procedimiento recomendado para crear y publicar un mes

1. Confirme que el padrón del último periodo está en `Base de datos/` y revise
   que las lecturas del mes estén completas.
2. Si las lecturas llegaron desde teléfonos, ejecute primero «Actualizar» →
   «Traer lecturas de los lectores» y revise el Excel resultante.
3. Use «Abrir mes nuevo», confirme el periodo y las fechas, y espere a que
   termine la operación.
4. Revise el nuevo `PADRON_MES_aaaa-mm.xlsx`, en especial la lectura anterior,
   fecha anterior y consumo anterior de algunos medidores.
5. Cuando el nuevo padrón esté correcto y se quiera habilitar para los
   lectores, use «Actualizar» → «Publicar solo el mes actual». Esta opción
   conserva los demás periodos de Firebase. Use «Enviar mes a los lectores»
   únicamente cuando quiera reemplazar los periodos y limpiar los documentos
   obsoletos; antes, descargue las lecturas móviles que deba conservar.
