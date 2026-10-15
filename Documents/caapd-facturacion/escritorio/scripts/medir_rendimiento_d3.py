"""
scripts/medir_rendimiento_d3.py — Benchmark automatizado para Fase D3 (Lecturas y Mes).
Mide:
1. Tiempo de poblar ModeloLecturas con 800 lecturas en memoria.
2. Tiempo de filtrado por sector en ProxyLecturas.
3. Tiempo de filtrado por estado (Faltan, Sin acceso, Observados).
4. Tiempo de búsqueda inteligente con codigos.buscar.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import time
from PySide6.QtWidgets import QApplication, QTableView
from PySide6.QtCore import Qt

from ui.paginas.lecturas_modelo import ModeloLecturas, ProxyLecturas
import codigos

def generar_800_filas_lecturas():
    sectores = ["BARRIO DE CHAUPI", "BARRIO DE PACHAYZA", "BARRIO DE LUCMANI", "HUAQUILLO", "CHAUPICERCA", "AYACUCHO"]
    novedades = ["NORMAL", "CASA_CERRADA", "MEDIDOR_DANADO", "FUGA", "NORMAL"]
    filas = []
    
    for i in range(1, 801):
        est = "LEIDO" if (i % 3 != 0) else "PENDIENTE"
        if i % 15 == 0:
            est = "SIN_ACCESO"
        
        act = (100 + i) if est == "LEIDO" else None
        nov = novedades[i % len(novedades)] if est != "PENDIENTE" else ""
        
        filas.append({
            "id_usuario": f"{70000000 + i}",
            "nro_conexion": f"{i:06d}",
            "nombre": f"ABONADO REGISTRADO {i} APELLIDO",
            "sector": sectores[i % len(sectores)],
            "direccion": f"CALLE {i}",
            "codigo_categoria": "A",
            "historial_m3": [10, 12, 14, 15, 12],
            "nro_medidor": f"M-{10000+i}",
            "lectura_anterior": 100,
            "lectura_actual": act,
            "fecha_anterior": "2026-09-08",
            "fecha_lectura": "2026-10-10" if act else None,
            "estado_lectura": est,
            "novedad": nov,
            "nota": "Verificado" if i % 10 == 0 else "",
            "registrado_por": "lector1@caapd.pe" if act else None,
            "es_pendiente": (i % 25 == 0),
        })
    return filas

def run_benchmarks():
    app = QApplication.instance() or QApplication(sys.argv)
    filas = generar_800_filas_lecturas()
    
    tabla = QTableView()
    modelo = ModeloLecturas()
    proxy = ProxyLecturas()
    proxy.setSourceModel(modelo)
    tabla.setModel(proxy)
    
    # 1. Poblar modelo
    tiempos_poblado = []
    for _ in range(5):
        t0 = time.perf_counter()
        modelo.actualizar_datos(filas)
        t1 = time.perf_counter()
        tiempos_poblado.append((t1 - t0) * 1000.0)
    t_pob_ms = sum(tiempos_poblado) / len(tiempos_poblado)
    
    # 2. Filtrado por sector
    sectores = ["BARRIO DE CHAUPI", "BARRIO DE PACHAYZA", "todos"]
    tiempos_sector = []
    for s in sectores * 3:
        t0 = time.perf_counter()
        proxy.set_filtro_sector(s)
        _ = proxy.rowCount()
        t1 = time.perf_counter()
        tiempos_sector.append((t1 - t0) * 1000.0)
    t_sec_ms = sum(tiempos_sector) / len(tiempos_sector)
    
    # 3. Filtrado por estado
    estados = ["faltan", "sin_acceso", "con_observacion", "todos"]
    tiempos_estado = []
    for e in estados * 3:
        t0 = time.perf_counter()
        proxy.set_filtro_estado(e)
        _ = proxy.rowCount()
        t1 = time.perf_counter()
        tiempos_estado.append((t1 - t0) * 1000.0)
    t_est_ms = sum(tiempos_estado) / len(tiempos_estado)
    
    # 4. Búsqueda inteligente
    consultas = ["000050", "700000", "CHAUPI", "M-1005"]
    tiempos_busq = []
    for q in consultas * 2:
        t0 = time.perf_counter()
        encontrados = codigos.buscar(q, filas)
        ids = {str(item.get("id_usuario")) for item in encontrados}
        proxy.set_ids_permitidos(ids)
        _ = proxy.rowCount()
        t1 = time.perf_counter()
        tiempos_busq.append((t1 - t0) * 1000.0)
    t_busq_ms = sum(tiempos_busq) / len(tiempos_busq)
    
    print("--- RESULTADOS BENCHMARK FASE D3 ---")
    print(f"1. Poblar tabla con 800 lecturas: {t_pob_ms:.2f} ms (Meta: < 300 ms)")
    print(f"2. Filtrado por sector: {t_sec_ms:.2f} ms (Meta: < 100 ms)")
    print(f"3. Filtrado por estado: {t_est_ms:.2f} ms (Meta: < 100 ms)")
    print(f"4. Búsqueda inteligente + proxy: {t_busq_ms:.2f} ms (Meta: < 100 ms)")

if __name__ == "__main__":
    run_benchmarks()
