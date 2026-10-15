# CAAPD Ispacas — Sistema de Facturación de Agua Potable

Sistema de facturación mensual para la secretaria del Comité de Administración de Agua Potable y Desagüe de la Comunidad Campesina de Ispacas.

## Requisitos

- Windows 10 o superior
- Python 3.11 o superior instalado y en el PATH
- Conexión a Internet (para Firebase y la primera instalación de dependencias)

## Instalación y uso

1. **Configura las credenciales de Firebase** en `config_local.py`:
   ```python
   FIREBASE_KEY_PATH = "caapd-ispacas-optimizado-firebase-adminsdk-fbsvc-e6c4b2f0b0.json"
   ```

2. **Siembra la configuración inicial** (solo la primera vez):
   ```
   venv\Scripts\python scripts\sembrar_config.py
   ```

3. **Importa los usuarios** (solo la primera vez):
   ```
   REM Primero simula para ver el reporte:
   venv\Scripts\python scripts\importar_excel.py --simular

   REM Si todo está bien, ejecuta la importación real:
   venv\Scripts\python scripts\importar_excel.py
   ```

4. **Inicia el sistema** haciendo doble clic en `iniciar.bat`.

   El sistema abre automáticamente en `http://127.0.0.1:5000`.

## Estructura del proyecto

```
caapd-facturacion/
├── app.py               Servidor Flask principal
├── firebase_client.py   Conexión Firebase + caché en memoria
├── calculos.py          Cálculos del recibo (testeable sin Firebase)
├── recibo_pdf.py        Generación de PDFs
├── respaldo_excel.py    Excel de respaldo mensual
├── scripts/
│   ├── importar_excel.py    Importación inicial de usuarios
│   └── sembrar_config.py    Configura Firestore por primera vez
├── templates/           Plantillas HTML (Jinja2)
├── static/
│   ├── css/estilo.css   Todo el estilo (variables CSS)
│   └── js/main.js       JavaScript mínimo
├── tests/               Pruebas pytest
├── respaldos/           Excels mensuales generados (no subir)
└── salida/              Reportes CSV de importación (no subir)
```

## Ejecutar pruebas

```
venv\Scripts\python -m pytest tests/ -v
```

## Límites del plan gratuito de Firebase (Spark)

| Operación | Límite diario | Uso estimado máximo |
|-----------|--------------|---------------------|
| Lecturas  | 50 000       | ~3 200 (6.4 %)      |
| Escrituras| 20 000       | ~1 600 (8.0 %)      |

El pie de página muestra el contador de la sesión con aviso si se acerca al límite.

## Fases de desarrollo

| Fase | Estado | Contenido |
|------|--------|-----------|
| 0 | ✅ Completada | Plan general, reglas de negocio y estructura del proyecto |
| 1 | ✅ Completada | Configuración, cliente Firebase en memoria, cálculos matemáticos con 100% pruebas |
| 2 | ✅ Completada | Importación masiva desde Excel, normalización de DNIs y gestión de Usuarios |
| 3 | ✅ Completada | Apertura de periodos mensuales, carga de lecturas, estimaciones y validaciones |
| 4 | ✅ Completada | Generación de recibos PDF individuales y masivos en ZIP con logo institucional |
| 5 | ✅ Completada | Registro de cobranzas, historial de pagos, lista de morosos y módulo de Lectores |
| 6 | ✅ Completada | Respaldo integral a Excel, cola de operaciones offline, modo contingencia y CLI de restauración |

## Modo de Contingencia y Recuperación (Fase 6)

El sistema incluye redundancia total para garantizar la continuidad operativa de la CAAPD:

1. **Respaldo Automático en Excel:**
   - Cada cambio de datos activa una copia de seguridad en `respaldos/RESPALDO_AAAA-MM.xlsx` (con debounce de 2 minutos).
   - Acciones críticas (abrir mes, emitir recibos, cerrar aplicación) generan respaldo inmediato.
   - Rotación diaria en `respaldos/historial/` con retención de 30 días.
   - Cero lecturas adicionales a Firestore (usa la copia en memoria).

2. **Operación Fuera de Línea (Offline Queue):**
   - Si se corta el internet, la aplicación sigue funcionando. Los cobros y lecturas se guardan en `datos/cola_pendiente.json`.
   - Se sincronizan automáticamente cada 60 segundos al restablecerse la conexión, o manualmente mediante el botón **"🔄 Sincronizar ahora"**.

3. **Restauración desde CLI:**
   ```bash
   # Simulación sin alterar la base de datos
   python scripts/restaurar_excel.py --archivo respaldos/RESPALDO_2026-10.xlsx --simular

   # Restauración real en caso de emergencia
   python scripts/restaurar_excel.py --archivo respaldos/RESPALDO_2026-10.xlsx --ejecutar --sobrescribir

   # Restauración hacia un nuevo proyecto de Firebase
   python scripts/restaurar_excel.py --archivo respaldos/RESPALDO_2026-10.xlsx --credenciales nueva_clave.json --ejecutar
   ```

Consulte el manual completo para la secretaria en [docs/PLAN_CONTINGENCIA.md](docs/PLAN_CONTINGENCIA.md).
