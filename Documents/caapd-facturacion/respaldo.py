"""
respaldo.py — Sistema de respaldo automático y gestión de copias de seguridad de CAAPD Ispacas.

Fase 6:
- Escucha on_datos_cambiados() con espera (debounce) de 2 minutos.
- Ejecución inmediata al abrir mes, generar recibos, cerrar el programa o petición manual.
- Guarda respaldos/RESPALDO_{aaaa-mm}.xlsx y una copia por día en respaldos/historial/ (30 días).
- Cero lecturas extra a Firebase (usa la copia ya cargada en memoria).
"""
from __future__ import annotations
import datetime
import logging
from pathlib import Path
import threading
from typing import Any, Dict, Optional, Tuple

import respaldo_excel

logger = logging.getLogger("caapd.respaldo")

_timer_respaldo: Optional[threading.Timer] = None
_lock = threading.Lock()
_ultimo_respaldo_info: Dict[str, Any] = {
    "fecha_hora": None,
    "periodo": None,
    "ruta": None,
    "total_docs": 0,
    "suma_total": 0.0,
    "exito": False,
}


def _obtener_directorio_respaldos() -> Path:
    """Devuelve la ruta a la carpeta respaldos/."""
    # Buscar primero en la raíz del proyecto, luego en carpeta actual
    dir_actual = Path(__file__).resolve().parent
    dir_resp = dir_actual / "respaldos"
    dir_resp.mkdir(parents=True, exist_ok=True)
    return dir_resp


def obtener_info_ultimo_respaldo() -> Dict[str, Any]:
    """Devuelve un diccionario con la fecha, hora y estado del último respaldo realizado."""
    global _ultimo_respaldo_info
    with _lock:
        return dict(_ultimo_respaldo_info)


def rotar_historial(dir_historial: Path, max_archivos: int = 30) -> None:
    """Conserva solo los últimos `max_archivos` en el directorio de historial."""
    try:
        archivos = sorted(dir_historial.glob("RESPALDO_*.xlsx"), key=lambda p: p.stat().st_mtime)
        if len(archivos) > max_archivos:
            for p in archivos[:-max_archivos]:
                try:
                    p.unlink()
                except Exception as e:
                    logger.warning("No se pudo eliminar archivo antiguo de historial %s: %s", p, e)
    except Exception as e:
        logger.error("Error al rotar historial de respaldos: %s", e)


def ejecutar_respaldo_ahora(
    config: Optional[Dict[str, Any]] = None,
    usuarios: Optional[Dict[str, Dict[str, Any]]] = None,
    mes_docs: Optional[Dict[str, Dict[str, Any]]] = None,
    periodo: Optional[str] = None,
) -> Optional[Path]:
    """Ejecuta de inmediato la generación del archivo Excel de respaldo.

    Utiliza los datos en memoria para no generar lecturas extra a Firestore.
    """
    global _ultimo_respaldo_info
    with _lock:
        try:
            # Si no se pasan datos explícitos, extraerlos del caché en memoria de firebase_client
            if config is None or usuarios is None or mes_docs is None:
                try:
                    import firebase_client as fb
                    cache = getattr(fb, "_cache", {})
                    cfg = config or cache.get("config") or {}
                    usr = usuarios or cache.get("usuarios") or {}
                    mes = mes_docs or cache.get("mes") or {}
                    p = periodo or cache.get("periodo_cargado") or (cfg.get("mes_actual") or {}).get("periodo")
                except Exception as e_fb:
                    logger.warning("No se pudo obtener caché de firebase_client: %s", e_fb)
                    cfg = config or {}
                    usr = usuarios or {}
                    mes = mes_docs or {}
                    p = periodo or "2026-10"
            else:
                cfg = config
                usr = usuarios
                mes = mes_docs
                p = periodo or (cfg.get("mes_actual") or {}).get("periodo") or "2026-10"

            if not p:
                p = datetime.date.today().strftime("%Y-%m")

            dir_respaldos = _obtener_directorio_respaldos()
            ruta_vigente = dir_respaldos / f"RESPALDO_{p}.xlsx"

            # 1. Generar archivo vigente
            ruta_creada = respaldo_excel.generar_respaldo_excel(
                config=cfg,
                usuarios=usr,
                mes_docs=mes,
                periodo=p,
                ruta_archivo=ruta_vigente,
            )

            # 2. Generar copia en historial con fecha del día
            dir_historial = dir_respaldos / "historial"
            dir_historial.mkdir(parents=True, exist_ok=True)
            hoy_str = datetime.date.today().isoformat()
            ruta_historial = dir_historial / f"RESPALDO_{p}_{hoy_str}.xlsx"

            # Copiar o guardar en historial
            import shutil
            shutil.copy2(ruta_creada, ruta_historial)

            # Rotar historial a 30 días
            rotar_historial(dir_historial, max_archivos=30)

            # Registrar metadatos
            ahora_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            suma_tot = sum(float(d.get("total_a_pagar") or 0.0) for d in mes.values())
            _ultimo_respaldo_info = {
                "fecha_hora": ahora_str,
                "periodo": p,
                "ruta": str(ruta_creada),
                "total_docs": len(mes),
                "suma_total": round(suma_tot, 2),
                "exito": True,
            }
            logger.info("Respaldo completado exitosamente: %s", ruta_creada)
            return ruta_creada
        except Exception as e:
            logger.error("Error al ejecutar respaldo automático: %s", e, exc_info=True)
            _ultimo_respaldo_info["exito"] = False
            return None


def on_datos_cambiados(tipo: str = "general", detalle: dict[str, Any] | None = None) -> None:
    """Hook global de notificación cuando se modifican usuarios, lecturas o configuración.

    - Si el tipo es 'abrir_mes', 'generar_recibos', 'cierre_programa' o 'manual': respalda inmediatamente.
    - Para otros cambios (pagos, lecturas, ediciones de usuario): reinicia el temporizador de 2 minutos (debounce).
    """
    global _timer_respaldo
    logger.info("Cambio de datos registrado: tipo=%s, detalle=%s", tipo, detalle or {})

    tipos_inmediatos = {"abrir_mes", "generar_recibos", "cierre_programa", "manual"}

    with _lock:
        # Cancelar cualquier temporizador previo
        if _timer_respaldo is not None:
            try:
                _timer_respaldo.cancel()
            except Exception:
                pass
            _timer_respaldo = None

        if tipo in tipos_inmediatos:
            # Respaldar de inmediato en un hilo separado o directo si es cierre
            if tipo == "cierre_programa":
                ejecutar_respaldo_ahora()
            else:
                hilo = threading.Thread(target=ejecutar_respaldo_ahora, daemon=True)
                hilo.start()
        else:
            # Programar a los 120 segundos (2 minutos)
            _timer_respaldo = threading.Timer(120.0, ejecutar_respaldo_ahora)
            _timer_respaldo.daemon = True
            _timer_respaldo.start()
