"""
ui/hilos.py — Manejo de hilos y asincronía en PySide6 para CAAPD Ispacas.

Blindaje contra cierres silenciosos (crash nativo) de PySide6 + QThreadPool:
  1. autoDelete desactivado: C++ NO destruye el QRunnable al terminar run().
  2. El Worker se mantiene vivo en _WORKERS_ACTIVOS hasta RETARDO_LIBERACION_MS
     después de que 'finalizado' llegó al hilo GUI. Así el hilo del pool ya salió
     por completo de run() cuando Python libera el objeto (sin use-after-free).
  3. La liberación la programa un QObject (WorkerSignals) que vive en el hilo GUI,
     con conexión EN COLA explícita: nunca se ejecuta en el hilo de trabajo.
  4. Toda excepción del hilo se registra en logs/hilos.log antes de emitirse.
"""
from __future__ import annotations

import functools
import gc
import logging
import traceback
from typing import Any, Callable, Optional, Set

from PySide6.QtCore import (
    QCoreApplication,
    QObject,
    QRunnable,
    QThread,
    QThreadPool,
    QTimer,
    Qt,
    Signal,
    Slot,
)
from PySide6.QtWidgets import QLabel, QMessageBox, QWidget

import rutas
from servicios.cancelacion import cierre_solicitado

_log = logging.getLogger("caapd.hilos")
if not _log.handlers:
    try:
        _ruta_log = rutas.ruta_aplicacion("logs", "hilos.log")
        _ruta_log.parent.mkdir(parents=True, exist_ok=True)
        _handler = logging.FileHandler(str(_ruta_log), encoding="utf-8")
        _handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s"))
        _log.addHandler(_handler)
        _log.setLevel(logging.INFO)
    except Exception:
        pass

# Workers vivos: evita que Python libere el Worker/WorkerSignals mientras
# el hilo del pool todavía está dentro de run() o hay señales en cola.
_WORKERS_ACTIVOS: Set["Worker"] = set()

# Margen de seguridad (ms) entre 'finalizado' y la liberación real del Worker.
RETARDO_LIBERACION_MS = 1500


class WorkerSignals(QObject):
    """Señales emitidas por el hilo de trabajo. Vive SIEMPRE en el hilo GUI."""
    resultado = Signal(object)
    error = Signal(str)
    finalizado = Signal()

    def __init__(self, worker: "Worker") -> None:
        super().__init__()
        self._worker: Optional["Worker"] = worker

        # Garantizar afinidad al hilo principal aunque el Worker se cree desde otro hilo.
        app = QCoreApplication.instance()
        if app is not None and QThread.currentThread() is not app.thread():
            self.moveToThread(app.thread())

        self._timer_liberar = QTimer(self)
        self._timer_liberar.setSingleShot(True)
        self._timer_liberar.setInterval(RETARDO_LIBERACION_MS)
        self._timer_liberar.timeout.connect(self._liberar_worker)

        # Conexión EN COLA explícita: este slot corre en el hilo GUI, nunca en el del pool.
        self.finalizado.connect(
            self._programar_liberacion, Qt.ConnectionType.QueuedConnection)

    @Slot()
    def _programar_liberacion(self) -> None:
        self._timer_liberar.start()

    @Slot()
    def _liberar_worker(self) -> None:
        w = self._worker
        self._worker = None
        if w is not None:
            _WORKERS_ACTIVOS.discard(w)


class Worker(QRunnable):
    """
    Ejecuta una función en un hilo de trabajo de QThreadPool.

    Uso (idéntico al anterior):
        worker = Worker(mi_funcion, arg1, arg2)
        worker.signals.resultado.connect(al_terminar)
        worker.signals.error.connect(al_fallar)
        QThreadPool.globalInstance().start(worker)
    """

    def __init__(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals(self)

        # C++ no debe destruir este objeto; lo gestiona Python (ver WorkerSignals).
        self.setAutoDelete(False)
        _WORKERS_ACTIVOS.add(self)

    @staticmethod
    def _emitir(senal: Any, *args: Any) -> None:
        if cierre_solicitado():
            return
        try:
            senal.emit(*args)
        except RuntimeError:
            # El objeto de señales ya no existe (app cerrándose): ignorar.
            pass

    def run(self) -> None:
        nombre = getattr(self.fn, "__qualname__", None) or getattr(
            self.fn, "__name__", "tarea")
        if not cierre_solicitado():
            _log.info("Hilo '%s' iniciado (thread=%s).",
                      nombre, hex(id(QThread.currentThread())))
        try:
            res = self.fn(*self.args, **self.kwargs)
        except Exception as e:
            if not cierre_solicitado():
                _log.error("Error en hilo '%s': %s\n%s",
                           nombre, e, traceback.format_exc())
            self._emitir(self.signals.error, str(e) or e.__class__.__name__)
        else:
            self._emitir(self.signals.resultado, res)
        finally:
            self._emitir(self.signals.finalizado)
            if not cierre_solicitado():
                _log.info("Hilo '%s' terminado.", nombre)


def slot_seguro(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Evita que una excepción dentro de un slot cierre el programa.

    En PySide6 6.12 una excepción que escapa de un slot llega al código C++ de Qt y
    termina el proceso con «Fatal Python error: Aborted», sin ventana de error. Este
    envoltorio registra el fallo en logs/hilos.log y lo muestra en un diálogo normal,
    de modo que la ventana permanece abierta.
    """
    @functools.wraps(fn)
    def envoltura(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            nombre = getattr(fn, "__qualname__", None) or getattr(
                fn, "__name__", "slot")
            _log.error("Error en slot '%s': %s\n%s",
                       nombre, e, traceback.format_exc())
            padre = args[0] if args and isinstance(args[0], QWidget) else None
            try:
                mostrar_dialogo_error(
                    padre,
                    "Se produjo un error en la operación",
                    f"La operación no se completó, pero el programa sigue abierto.\n\n"
                    f"Detalle: {e.__class__.__name__}: {e}\n\n"
                    f"El detalle técnico quedó guardado en logs/hilos.log.",
                )
            except Exception:
                pass
            return None

    return envoltura


class RecolectorBasuraGUI(QObject):
    """Ejecuta el GC de Python SOLO en el hilo GUI: así ningún QWidget/QObject
    se destruye desde un hilo del QThreadPool (causa del cierre nativo)."""

    def __init__(self, app: QCoreApplication, intervalo_ms: int = 1000) -> None:
        super().__init__(app)
        gc.disable()
        self._ciclos = 0
        self._timer = QTimer(self)
        self._timer.setInterval(intervalo_ms)
        self._timer.timeout.connect(self._recolectar)
        self._timer.start()

    @Slot()
    def _recolectar(self) -> None:
        self._ciclos += 1
        gc.collect(2 if self._ciclos % 10 == 0 else 1)


def esperar_hilos(ms: int = 8000) -> bool:
    """Espera como máximo ``ms`` y reporta si todos los Workers terminaron."""
    try:
        pool = QThreadPool.globalInstance()
        return pool.waitForDone(int(ms))
    except Exception:
        _log.exception("No se pudo esperar la finalización de los Workers.")
        return False


def precargar_firebase_en_hilo_principal() -> bool:
    """
    Importa firebase_client (firebase_admin + gRPC nativo) y las librerías de la
    ruta REST desde el HILO PRINCIPAL, antes de que cualquier Worker las necesite.

    Motivo: en Windows, si la PRIMERA importación de gRPC (cygrpc) ocurre dentro de
    un hilo del QThreadPool, el proceso puede cerrarse sin traceback mostrando solo
    «QThreadStorage: entry N destroyed before end of thread». Importar aquí NO abre
    conexiones ni hace lecturas a Firebase; solo carga el código.
    Debe llamarse desde el hilo GUI (por ejemplo con QTimer.singleShot tras mostrar
    la ventana). Devuelve True si la precarga fue completa.
    """
    app = QCoreApplication.instance()
    if app is not None and QThread.currentThread() is not app.thread():
        _log.warning(
            "precargar_firebase_en_hilo_principal() llamado fuera del hilo GUI; se omite.")
        return False
    ok = True
    try:
        from servicios import firestore_rest
        if not firestore_rest.precargar_dependencias():
            ok = False
    except Exception as e:
        _log.warning("No se pudo precargar la ruta REST: %s", e)
        ok = False
    try:
        import firebase_client  # noqa: F401  (firebase_admin + gRPC, solo importación)
    except Exception as e:
        # Sin credenciales o sin firebase_admin: no es fatal, las acciones que lo
        # necesiten mostrarán su propio error en español.
        _log.warning("No se pudo precargar firebase_client: %s", e)
        ok = False
    _log.info("Precarga de Firebase/gRPC en hilo principal: %s",
              "completa" if ok else "parcial")
    return ok


def instalar_diagnostico_cierre(app: QCoreApplication) -> None:
    """
    Registra en logs/hilos.log POR QUÉ se cierra el programa, para que un cierre
    inesperado deje rastro aunque la consola no muestre traceback:
      - lastWindowClosed / aboutToQuit con la pila de llamadas Python del momento.
      - Excepciones no capturadas en el hilo principal y en hilos de threading.
    """
    import sys
    import threading

    def _pila() -> str:
        return "".join(traceback.format_stack(limit=12))

    def _al_cerrar_ultima_ventana() -> None:
        _log.warning("Qt emitió lastWindowClosed. Pila:\n%s", _pila())

    def _al_salir() -> None:
        activos = QThreadPool.globalInstance().activeThreadCount()
        _log.warning(
            "Qt emitió aboutToQuit (workers activos: %d). Pila:\n%s", activos, _pila())

    try:
        app.lastWindowClosed.connect(_al_cerrar_ultima_ventana)
        app.aboutToQuit.connect(_al_salir)
    except Exception:
        pass

    hook_anterior = sys.excepthook

    def _excepthook(tipo, valor, tb):
        _log.error("Excepción no capturada en el hilo principal:\n%s",
                   "".join(traceback.format_exception(tipo, valor, tb)))
        try:
            hook_anterior(tipo, valor, tb)
        except Exception:
            pass

    sys.excepthook = _excepthook

    def _thread_hook(args):
        _log.error("Excepción no capturada en hilo '%s':\n%s", getattr(args.thread, "name", "?"),
                   "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)))

    try:
        threading.excepthook = _thread_hook
    except Exception:
        pass


def _crear_caja(padre: Optional[QWidget], icono: Any, titulo: str, mensaje: str, ancho_min: int) -> QMessageBox:
    box = QMessageBox(padre)
    box.setIcon(icono)
    box.setWindowTitle(titulo)
    box.setText(mensaje)
    box.setStandardButtons(QMessageBox.StandardButton.Ok)
    # Ancho mínimo del texto: evita que la primera línea se corte.
    box.setStyleSheet(
        f"QLabel#qt_msgbox_label {{ min-width: {int(ancho_min)}px; }}")
    lbl = box.findChild(QLabel, "qt_msgbox_label")
    if lbl is not None:
        lbl.setWordWrap(True)
    return box


def mostrar_dialogo_info(padre: Optional[QWidget], titulo: str, mensaje: str, ancho_min: int = 560) -> None:
    """Diálogo informativo ancho: el texto largo se ve completo y con salto de línea."""
    _crear_caja(padre, QMessageBox.Icon.Information,
                titulo or "Información", mensaje, ancho_min).exec()


def mostrar_dialogo_error(padre: Optional[QWidget], titulo: str, mensaje: str, ancho_min: int = 480) -> None:
    """Muestra un diálogo nativo de error claro en español."""
    _crear_caja(padre, QMessageBox.Icon.Critical,
                titulo or "Error del sistema", mensaje, ancho_min).exec()


def mostrar_dialogo_aviso(
    padre: Optional[QWidget],
    titulo: str,
    mensaje: str,
    detalle: Optional[str] = None,
    ancho_min: int = 560,
) -> None:
    """Diálogo de advertencia ancho con salto de línea. El detalle técnico va en
    una sección plegable ('Mostrar detalles...') con scroll, así nunca deforma la caja."""
    box = _crear_caja(padre, QMessageBox.Icon.Warning,
                      titulo or "Aviso", mensaje, ancho_min)
    if detalle:
        box.setDetailedText(str(detalle))
    box.exec()
