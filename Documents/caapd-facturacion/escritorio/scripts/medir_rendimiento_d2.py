"""
scratch/medir_rendimiento_d2.py — Medición automatizada de rendimiento para Fase D2 (Usuarios).
Mide:
1. Tiempo de poblar QTableView con 800 usuarios en memoria (Meta: < 300 ms).
2. Tiempo de filtrado por pestaña/estado (Meta: < 100 ms).
3. Tiempo de filtrado por búsqueda inteligente (Meta: < 100 ms).
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import time
from PySide6.QtWidgets import QApplication, QTableView
from PySide6.QtCore import Qt

from ui.paginas.usuarios_modelo import ModeloUsuarios, ProxyUsuarios
import codigos

def generar_800_usuarios():
    usuarios = []
    sectores = ["CENTRO", "ALTO", "BAJO", "MIRAFLORES", "SAN ISIDRO"]
    categorias = ["A", "B", "C"]
    
    for i in range(1, 801):
        es_sd = (i % 15 == 0)
        activo = (i % 8 != 0)
        dni = f"SD-{i:03d}" if es_sd else f"{70000000 + i}"
        usuarios.append({
            "id_usuario": dni,
            "_id": dni,
            "nro_conexion": f"{i:06d}",
            "nombre": f"USUARIO DE PRUEBA {i} APELLIDO",
            "sector": sectores[i % len(sectores)],
            "direccion": f"CALLE PRINCIPAL {i}",
            "codigo_categoria": categorias[i % len(categorias)],
            "medidores": [f"M-{1000+i}", f"SEC-{i}"] if (i % 5 == 0) else [f"M-{1000+i}"],
            "activo": activo,
            "es_pendiente": es_sd,
        })
    return usuarios

def run_benchmarks():
    app = QApplication.instance() or QApplication(sys.argv)
    
    usuarios = generar_800_usuarios()
    
    # 1. Medir tiempo de poblar modelo con 800 usuarios
    tabla = QTableView()
    modelo = ModeloUsuarios()
    proxy = ProxyUsuarios()
    proxy.setSourceModel(modelo)
    tabla.setModel(proxy)
    
    # Calentamiento
    modelo.actualizar_datos(usuarios[:10])
    
    # Medición real de carga de 800 usuarios
    tiempos_poblado = []
    for _ in range(5):
        t0 = time.perf_counter()
        modelo.actualizar_datos(usuarios)
        t1 = time.perf_counter()
        tiempos_poblado.append((t1 - t0) * 1000.0) # ms
        
    t_poblado_ms = sum(tiempos_poblado) / len(tiempos_poblado)
    
    # 2. Medir tiempo de filtrado por estado (pestañas)
    tiempos_filtro_estado = []
    estados = ["activos", "inactivos", "pendientes", "todos"]
    for estado in estados * 3:
        t0 = time.perf_counter()
        proxy.set_filtro_estado(estado)
        # forzar evaluación de filas
        _ = proxy.rowCount()
        t1 = time.perf_counter()
        tiempos_filtro_estado.append((t1 - t0) * 1000.0)
        
    t_filtro_estado_ms = sum(tiempos_filtro_estado) / len(tiempos_filtro_estado)
    
    # 3. Medir tiempo de búsqueda inteligente + filtrado proxy
    terminos = ["700000", "000050", "PRUEBA 50", "SD-", "M-1050"]
    tiempos_busqueda = []
    for term in terminos * 2:
        t0 = time.perf_counter()
        encontrados = codigos.buscar(term, usuarios)
        ids = {str(u.get("id_usuario") or u.get("_id") or "") for u in encontrados}
        proxy.set_ids_busqueda(ids)
        _ = proxy.rowCount()
        t1 = time.perf_counter()
        tiempos_busqueda.append((t1 - t0) * 1000.0)
        
    t_busqueda_ms = sum(tiempos_busqueda) / len(tiempos_busqueda)
    
    print("--- RESULTADOS BENCHMARK FASE D2 ---")
    print(f"1. Poblar tabla con 800 usuarios: {t_poblado_ms:.2f} ms (Meta: < 300 ms)")
    print(f"2. Filtrado por estado/pestañas: {t_filtro_estado_ms:.2f} ms (Meta: < 100 ms)")
    print(f"3. Búsqueda inteligente + proxy: {t_busqueda_ms:.2f} ms (Meta: < 100 ms)")
    
if __name__ == "__main__":
    run_benchmarks()
