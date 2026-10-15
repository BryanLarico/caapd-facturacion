"""
ui/hilos.py — Manejo de hilos y asincronía en PySide6 para CAAPD Ispacas.

Permite ejecutar operaciones lentas (Firebase, Excel, PDF) en segundo plano
sin bloquear la interfaz, manejando errores y señales con seguridad.

Blindaje contra cierres silenciosos (crash nativo) de PySide6 + QThreadPool:
  1. autoDelete desactivado: C++ NO destruye el QRunnable al terminar run().
  2. Registro de Workers activos: el objeto Python (y su WorkerSignals) se
     mantiene vivo hasta que TODAS las señales encoladas se hayan entregado
     en el hilo de la interfaz. Solo entonces se libera.
  3. Toda excepción del hilo se registra en logs/hilos.log antes de emitirse.
"""
from __future__ import annotations

import logging
import traceback
from typing import Any, Callable, Set

from PySide6.QtCore import QObject, QRunnable, QTimer, Signal, Slot
from PySide6.QtWidgets import QMessageBox, QWidget

import rutas

# ---------------------------------------------------------------------------
# Registro de archivo para errores en hilos (útil para diagnosticar cierres)
# ---------------------------------------------------------------------------
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

# Workers vivos. Evita que Python libere el Worker/WorkerSignals mientras
# todavía hay señales encoladas pendientes de entrega en el hilo GUI.
_WORKERS_ACTIVOS: Set["Worker"] = set()


class WorkerSignals(QObject):
    """Señales emitidas por el hilo de trabajo."""
    resultado = Signal(object)
    error = Signal(str)
    finalizado = Signal()


class Worker(QRunnable):
    """
    Ejecuta una función en un hilo de trabajo de QThreadPool.

    Uso (idéntico al anterior, no hay que cambiar las páginas):
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
        self.signals = WorkerSignals()

        # 1) C++ no debe destruir este objeto; lo gestiona Python.
        self.setAutoDelete(False)

        # 2) Mantener vivo hasta que 'finalizado' haya sido procesado en el hilo GUI.
        _WORKERS_ACTIVOS.add(self)
        self.signals.finalizado.connect(self._programar_liberacion)

    @Slot()
    def _programar_liberacion(self) -> None:
        """Se ejecuta en el hilo GUI (conexión encolada). Libera el Worker un ciclo de eventos después,
        garantizando que 'resultado'/'error' (emitidas antes que 'finalizado') ya fueron entregadas."""
        QTimer.singleShot(0, self._liberar)

    def _liberar(self) -> None:
        _WORKERS_ACTIVOS.discard(self)

    @Slot()
    def run(self) -> None:
        nombre = getattr(self.fn, "__qualname__", None) or getattr(self.fn, "__name__", "tarea")
        try:
            res = self.fn(*self.args, **self.kwargs)
            try:
                self.signals.resultado.emit(res)
            except RuntimeError:
                pass
        except Exception as e:
            _log.error("Error en hilo '%s': %s\n%s", nombre, e, traceback.format_exc())
            try:
                self.signals.error.emit(str(e))
            except RuntimeError:
                pass
        finally:
            try:
                self.signals.finalizado.emit()
            except RuntimeError:
                # Si las señales ya no existen, liberar directamente para no dejar fugas.
                _WORKERS_ACTIVOS.discard(self)


def mostrar_dialogo_error(padre: QWidget, titulo: str, mensaje: str) -> None:
    """Muestra un diálogo nativo de error claro en español."""
    box = QMessageBox(padre)
    box.setIcon(QMessageBox.Icon.Critical)
    box.setWindowTitle(titulo or "Error del sistema")
    box.setText(mensaje)
    box.setStandardButtons(QMessageBox.StandardButton.Ok)
    box.exec()