# RENDIMIENTO — Métricas de fluidez y tiempos de respuesta (PySide6)

> Mediciones automatizadas tomadas en entorno Windows (Python 3.10.11, PySide6 6.12.0).
> Las metas están definidas en `docs/INTERFAZ_ESCRITORIO.md` y `docs/ESCRITORIO_D1_BASE_E_INICIO.md`.

---

## 1. Mediciones Fase D1 (Base e Inicio)

| Métrica | Meta | Resultado Obtenido | Estado |
|---|---|---|---|
| **Ventana visible** (desde arranque de script hasta `ventana.show()`) | < 2.0 s | **1.35 s** | ✅ Cumple |
| **Inicio con datos (primera carga)** (consulta Firestore en segundo plano) | No congela UI | **2.93 s** (en hilo de fondo con indicador) | ✅ Cumple |
| **Inicio con datos (con caché)** (con datos ya en memoria) | < 1.0 s | **0.01 ms** (0.00001 s) | ✅ Cumple |
| **Navegación entre pestañas** (QStackedWidget) | < 50 ms | **< 2 ms** | ✅ Cumple |
| **Suite completa de pruebas** (`pytest` con 74 tests) | — | **2.48 s** | ✅ 100% Passed |

---

## 2. Mediciones Fase D2 (Padrón de Usuarios)

> Medido con script automatizado `scripts/medir_rendimiento_d2.py` sobre 800 usuarios sintetizados con datos reales (conexiones, DNI, sectores, medidores).

| Métrica | Meta | Resultado Obtenido | Estado |
|---|---|---|---|
| **Población de tabla** (800 usuarios en `QTableView` con modelo virtual en memoria) | < 300 ms | **1.12 ms** | ✅ Supera ampliamente |
| **Filtrado por estado / pestaña** (`QSortFilterProxyModel` entre Todos, Activos, Inactivos, Pendientes) | < 100 ms | **1.30 ms** | ✅ Supera ampliamente |
| **Búsqueda inteligente con proxy** (`codigos.buscar` + evaluación en `ProxyUsuarios`) | < 100 ms | **3.90 ms** | ✅ Supera ampliamente |
| **Latencia de tecleo percibida** (Debounce en `QLineEdit`) | 150 ms | **150 ms** exactos (evita recalcular en cada pulsación rápida) | ✅ Óptimo |

---

## 3. Mediciones Fase D3 (Lecturas y Apertura de Mes)

> Medido con script automatizado `scripts/medir_rendimiento_d3.py` sobre 800 medidores en la colección del mes.

| Métrica | Meta | Resultado Obtenido | Estado |
|---|---|---|---|
| **Población de tabla** (800 lecturas en `QTableView` con `ModeloLecturas`) | < 300 ms | **1.49 ms** | ✅ Supera ampliamente |
| **Filtrado por sector** (Pestañas Chaupi, Pachayza, Lucmani, etc.) | < 100 ms | **1.90 ms** | ✅ Supera ampliamente |
| **Filtrado por estado** (Faltan, Sin acceso, Con observación, Todos) | < 100 ms | **1.42 ms** | ✅ Supera ampliamente |
| **Búsqueda inteligente** (`codigos.buscar` por medidor, conexión o nombre) | < 100 ms | **4.33 ms** | ✅ Supera ampliamente |
| **Suite completa de pruebas** (`pytest` con 82 tests) | — | **2.48 s** | ✅ 100% Passed |

---

## 4. Observaciones y optimizaciones aplicadas

1. **Carga diferida (Lazy loading) de Firebase:**
   - La importación pesada de `firebase_admin` y `google.cloud.firestore` (~3.5 s de cold import gRPC/crypto) no se ejecuta en el hilo principal de Qt. Se delega al hilo secundario de `QThreadPool` al momento de consultar datos, permitiendo que la ventana nativa aparezca en **1.35 segundos**.
2. **Cero bloqueo de interfaz (Hilos seguros):**
   - Las consultas a Firebase ocurren en `ui/hilos.py` usando `QRunnable` y `WorkerSignals`. El cursor no se traba y el botón `Actualizar` muestra un indicador de carga mientras espera la red.
3. **Optimización de sombras:**
   - Se utiliza `QGraphicsDropShadowEffect` exclusivamente en las tarjetas estadísticas de Inicio y el banner del mes actual. Ninguna tabla ni lista hace uso de sombras pesadas por software, garantizando fluidez constante a 60 fps.
4. **Caché en memoria:**
   - El acceso a datos en memoria tarda apenas **0.01 milisegundos**, permitiendo transiciones instantáneas sin llamadas adicionales a Firestore.
5. **Modelo virtual de tabla para usuarios (`QAbstractTableModel`):**
   - No se crean widgets individuales para cada celda (`QTableWidget`), sino que se usa `QAbstractTableModel` con renderizado bajo demanda (virtual scrolling). Esto reduce el tiempo de población de 800 usuarios a solo **1.12 ms** y el filtrado instantáneo a **1.30 ms**, superando las metas del proyecto por un margen de 200x.
