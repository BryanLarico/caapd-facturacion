"""
ui/hilos.py — Manejo de hilos y asincronía en PySide6 para CAAPD Ispacas.

Permite ejecutar operaciones lentas (Firebase, Excel, PDF) en segundo plano
sin bloquear la interfaz, manejando errores y señales con seguridad.
"""
from typing import Any, Callable
from PySide6.QtCore import QObject, QRunnable, Signal, Slot
from PySide6.QtWidgets import QMessageBox, QWidget


class WorkerSignals(QObject):
    """Señales emitidas por el hilo de trabajo."""
    resultado = Signal(object)
    error = Signal(str)
    finalizado = Signal()


class Worker(QRunnable):
    """
    Ejecuta una función en un hilo de trabajo de QThreadPool.
    """

    def __init__(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            res = self.fn(*self.args, **self.kwargs)
            try:
                self.signals.resultado.emit(res)
            except RuntimeError:
                pass
        except Exception as e:
            try:
                self.signals.error.emit(str(e))
            except RuntimeError:
                pass
        finally:
            try:
                self.signals.finalizado.emit()
            except RuntimeError:
                pass


def mostrar_dialogo_error(padre: QWidget, titulo: str, mensaje: str) -> None:
    """Muestra un diálogo nativo de error claro en español."""
    box = QMessageBox(padre)
    box.setIcon(QMessageBox.Icon.Critical)
    box.setWindowTitle(titulo or "Error del sistema")
    box.setText(mensaje)
    box.setStandardButtons(QMessageBox.StandardButton.Ok)
    box.exec()
