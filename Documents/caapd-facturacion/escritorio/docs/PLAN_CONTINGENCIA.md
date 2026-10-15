# Plan de Contingencia y Recuperación ante Fallos — CAAPD Ispacas

Este manual contiene las instrucciones paso a paso para la secretaria y administradores en caso de cortes de internet, caídas de servicio o emergencias técnicas.

---

### Caso 1: Se cortó el Internet en la oficina

El programa está diseñado para **no detenerse** aunque no haya internet.

1. **Continuar trabajando normalmente**:
   - Puedes seguir buscando usuarios, consultando deudas, registrando cobros y emitiendo recibos.
2. **Identificar el aviso en pantalla**:
   - En la parte superior aparecerá un banner anaranjado:
     `⚠️ Hay N cambio(s) pendiente(s) de sincronizar con el servidor.`
   - Cada cobro realizado se almacena de forma segura en el disco de tu computadora (`datos/cola_pendiente.json`).
3. **Al volver el internet**:
   - El sistema reintenta la sincronización automáticamente cada 60 segundos.
   - También puedes presionar el botón **"🔄 Sincronizar ahora"** en el banner.
   - Los cobros se subirán a la nube sin duplicarse.

> **Importante:** Si vas a cerrar la aplicación antes de que vuelva la luz o el internet, el sistema te avisará que hay cambios pendientes y los conservará en disco para enviarlos apenas vuelvas a abrir el sistema con red.

---

### Caso 2: El servidor de Firebase está temporalmente caído

Si el servicio en la nube sufre una interrupción temporal:

1. **Para la secretaria (PC)**:
   - Sigue el mismo procedimiento del **Caso 1**. Tus operaciones locales no se pierden.
   - Si abres el programa con el servidor caído, la aplicación te ofrecerá iniciar en **Modo Contingencia** cargando el último respaldo de Excel disponible.
2. **Para los lectores en campo (App Móvil)**:
   - Los lectores pueden seguir registrando lecturas y fotos en sus celulares sin internet.
   - La aplicación móvil almacena las lecturas localmente y las sube automáticamente cuando recuperen la señal o al regresar a la oficina con WiFi.

---

### Caso 3: Se borraron o modificaron datos por error humano

Si se alteró accidentalmente el padrón o los datos de un mes:

1. Localiza el último archivo en la carpeta de respaldos (ej. `respaldos/RESPALDO_2026-10.xlsx`).
2. Abre la terminal o comunícate con el soporte técnico para ejecutar la restauración granular:
   - **Para restaurar solo el mes afectado (sin tocar usuarios ni configuración):**
     ```bash
     python scripts/restaurar_excel.py --archivo respaldos/RESPALDO_2026-10.xlsx --solo mes --simular
     python scripts/restaurar_excel.py --archivo respaldos/RESPALDO_2026-10.xlsx --solo mes --ejecutar --sobrescribir
     ```
   - **Para restaurar solo el padrón de usuarios:**
     ```bash
     python scripts/restaurar_excel.py --archivo respaldos/RESPALDO_2026-10.xlsx --solo usuarios --ejecutar --sobrescribir
     ```
   - **Para restaurar solo la configuración de tarifas:**
     ```bash
     python scripts/restaurar_excel.py --archivo respaldos/RESPALDO_2026-10.xlsx --solo config --ejecutar --sobrescribir
     ```

---

### Caso 4: Se perdió, bloqueó o eliminó el proyecto de Firebase

Si se pierde el acceso total a la cuenta de Google/Firebase o se requiere migrar a un proyecto nuevo:

1. **Crear un nuevo proyecto en Firebase Console**:
   - Crear el proyecto en [console.firebase.google.com](https://console.firebase.google.com).
   - Crear la base de datos Cloud Firestore en modo `(default)`.
   - Publicar las reglas de seguridad oficiales de Firestore.
   - Habilitar autenticación por Email/Password.
2. **Generar la nueva clave de servicio**:
   - En *Configuración del proyecto* > *Cuentas de servicio* > *Generar nueva clave privada*.
   - Guardar el archivo `.json` en la computadora.
3. **Restaurar toda la información desde el Excel de respaldo**:
   - Primero simular para verificar conteos y sumas:
     ```bash
     python scripts/restaurar_excel.py --archivo respaldos/RESPALDO_2026-10.xlsx --credenciales mi_nueva_clave.json --simular
     ```
   - Luego ejecutar la restauración real:
     ```bash
     python scripts/restaurar_excel.py --archivo respaldos/RESPALDO_2026-10.xlsx --credenciales mi_nueva_clave.json --ejecutar
     ```
   - Reemplazar el archivo de credenciales local con la nueva clave.
4. **Actualizar la aplicación móvil de los lectores**:
   - Descargar el nuevo `google-services.json` desde Firebase Console.
   - Recompilar e instalar la app móvil en los celulares de los lectores.
   - Volver a crear los correos de los lectores desde la pestaña **"📱 Lectores"** del sistema de escritorio.

---

### Caso 5: Resguardo de copias fuera de la computadora (Políticas de Seguridad)

Para evitar la pérdida total por robo, daño de disco duro o virus:

1. **Frecuencia**: Todos los **viernes** o al cierre de cada mes.
2. **Procedimiento**:
   - En el pie de la ventana del programa, haz clic en **"📂 Respaldos"**.
   - Se abrirá la carpeta con los archivos `RESPALDO_AAAA-MM.xlsx` y la subcarpeta `historial/`.
   - Copia toda la carpeta `respaldos/` a:
     - Una memoria USB externa exclusiva para la CAAPD.
     - O a la carpeta sincronizada de Google Drive / OneDrive institucional.
3. **Regla de oro**: **Nunca depender de una sola copia física en la misma computadora.**
