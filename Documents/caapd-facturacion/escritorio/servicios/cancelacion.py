"""Estado compartido de cancelación al cerrar la aplicación."""
from threading import Event

_evento_cierre = Event()


def marcar_cierre() -> None:
    _evento_cierre.set()


def cierre_solicitado() -> bool:
    return _evento_cierre.is_set()