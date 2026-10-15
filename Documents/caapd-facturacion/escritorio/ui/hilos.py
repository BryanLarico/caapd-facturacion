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

_log = logging.getLogger("caapd.hilos")
if not _log.handlers:
    try:
        _ruta_log = rutas.ruta_recurso("logs", "hilos.log")
        _ruta_log.parent.mkdir(parents=True, exist_ok=True)
        _handler = logging.FileHandler(str(_ruta_log), encoding="utf-8")
        _handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
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
        self.finalizado.connect(self._programar_liberacion, Qt.ConnectionType.QueuedConnection)

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
        try:
            senal.emit(*args)
        except RuntimeError:
            # El objeto de señales ya no existe (app cerrándose): ignorar.
            pass

    def run(self) -> None:
        nombre = getattr(self.fn, "__qualname__", None) or getattr(self.fn, "__name__", "tarea")
        try:
            res = self.fn(*self.args, **self.kwargs)
        except Exception as e:
            _log.error("Error en hilo '%s': %s\n%s", nombre, e, traceback.format_exc())
            self._emitir(self.signals.error, str(e) or e.__class__.__name__)
        else:
            self._emitir(self.signals.resultado, res)
        finally:
            self._emitir(self.signals.finalizado)


def esperar_hilos(ms: int = 8000) -> None:
    """Espera (máximo ms) a que terminen los Workers del pool global.
    Llamar al cerrar la ventana/app para evitar
    'QThreadStorage: entry destroyed before end of thread' y cierres abruptos."""
    try:
        pool = QThreadPool.globalInstance()
        pool.clear()  # descarta tareas que aún no empezaron
        pool.waitForDone(int(ms))
    except Exception:
        pass


def _crear_caja(padre: Optional[QWidget], icono: Any, titulo: str, mensaje: str, ancho_min: int) -> QMessageBox:
    box = QMessageBox(padre)
    box.setIcon(icono)
    box.setWindowTitle(titulo)
    box.setText(mensaje)
    box.setStandardButtons(QMessageBox.StandardButton.Ok)
    # Ancho mínimo del texto: evita que la primera línea se corte.
    box.setStyleSheet(f"QLabel#qt_msgbox_label {{ min-width: {int(ancho_min)}px; }}")
    lbl = box.findChild(QLabel, "qt_msgbox_label")
    if lbl is not None:
        lbl.setWordWrap(True)
    return box


def mostrar_dialogo_info(padre: Optional[QWidget], titulo: str, mensaje: str, ancho_min: int = 560) -> None:
    """Diálogo informativo ancho: el texto largo se ve completo y con salto de línea."""
    _crear_caja(padre, QMessageBox.Icon.Information, titulo or "Información", mensaje, ancho_min).exec()


def mostrar_dialogo_error(padre: Optional[QWidget], titulo: str, mensaje: str, ancho_min: int = 480) -> None:
    """Muestra un diálogo nativo de error claro en español."""
    _crear_caja(padre, QMessageBox.Icon.Critical, titulo or "Error del sistema", mensaje, ancho_min).exec()