"""
app.py — Servidor Flask principal del sistema CAAPD Ispacas.

Punto de entrada: python app.py
O vía iniciar.bat
"""

from __future__ import annotations
import os
from flask import Flask, render_template, redirect, url_for, g, request, flash

try:
    from config_local import PUERTO, DEBUG
except ImportError:
    PUERTO = 5000
    DEBUG = False

import firebase_client as fb
import codigos

app = Flask(__name__)
app.secret_key = os.urandom(24)


# ---------------------------------------------------------------------------
# Contexto global para cada petición
# ---------------------------------------------------------------------------

@app.before_request
def cargar_contexto_global():
    """Carga config en memoria si no está ya cargada."""
    try:
        g.config = fb.cargar_config()
    except Exception as e:
        g.config = {}
        g.config_error = str(e)


@app.context_processor
def inyectar_globals():
    """Pone variables disponibles en todos los templates."""
    ops = fb.get_ops()
    avisos_ops = fb.hay_aviso_ops()
    config = getattr(g, "config", {})
    mes_actual = config.get("mes_actual", {})
    return {
        "ops": ops,
        "avisos_ops": avisos_ops,
        "mes_actual": mes_actual,
        "config": config,
    }


# ---------------------------------------------------------------------------
# Rutas principales (solo estructura en Fase 1)
# ---------------------------------------------------------------------------

@app.route("/")
def inicio():
    from firebase_client import cargar_usuarios, cargar_mes
    config = getattr(g, "config", {})
    mes_actual = config.get("mes_actual", {})
    periodo = mes_actual.get("periodo")

    # Estadísticas de lecturas y recibos
    stats_sectores = []
    stats_recibos = {"generados": 0, "pagados": 0, "pendientes": 0}
    usuarios = {}
    mes = {}

    if periodo:
        try:
            usuarios = cargar_usuarios()
            mes = cargar_mes(periodo)
        except Exception:
            pass

        sectores = config.get("sectores", [])
        for sector in sectores:
            total = sum(
                1 for u in usuarios.values()
                if u.get("sector") == sector and u.get("activo", True)
            )
            leidos = 0
            for uid, doc in mes.items():
                u = usuarios.get(uid, {})
                if u.get("sector") != sector:
                    continue
                # Todos los medidores del usuario tienen lectura_actual
                medidores_doc = doc.get("medidores", [])
                if medidores_doc and all(
                    m.get("lectura_actual") is not None for m in medidores_doc
                ):
                    leidos += 1
            stats_sectores.append({
                "sector": sector,
                "total": total,
                "leidos": leidos,
            })

        for uid, doc in mes.items():
            if doc.get("nro_recibo"):
                stats_recibos["generados"] += 1
                if doc.get("monto_pagado", 0) >= doc.get("total_a_pagar", 0) > 0:
                    stats_recibos["pagados"] += 1
                else:
                    stats_recibos["pendientes"] += 1

    return render_template(
        "inicio.html",
        stats_sectores=stats_sectores,
        stats_recibos=stats_recibos,
        periodo=periodo,
    )


# ---------------------------------------------------------------------------
# Usuarios (Fase 2)
# ---------------------------------------------------------------------------

@app.route("/usuarios")
def usuarios():
    q = request.args.get("q", "").strip()
    filtro = request.args.get("filtro", "todos").strip().lower()
    try:
        pagina = max(1, int(request.args.get("pagina", 1)))
    except (ValueError, TypeError):
        pagina = 1

    por_pagina = 40

    try:
        todos_dict = fb.cargar_usuarios()
    except Exception as e:
        flash(f"Error al cargar usuarios de Firestore: {e}", "peligro")
        todos_dict = {}

    lista_usuarios = []
    total_activos = 0
    total_inactivos = 0
    total_pendientes = 0

    for uid, u in todos_dict.items():
        doc = dict(u)
        doc["_id"] = uid
        doc["id_usuario"] = uid
        es_pend = codigos.es_id_pendiente(uid)
        doc["es_pendiente"] = es_pend
        es_act = doc.get("activo", True)

        if es_act:
            total_activos += 1
        else:
            total_inactivos += 1

        if es_pend:
            total_pendientes += 1

        lista_usuarios.append(doc)

    # Filtrar según pestaña
    if filtro == "activos":
        filtrados = [u for u in lista_usuarios if u.get("activo", True)]
    elif filtro == "inactivos":
        filtrados = [u for u in lista_usuarios if not u.get("activo", True)]
    elif filtro == "pendientes":
        filtrados = [u for u in lista_usuarios if u["es_pendiente"]]
    else:
        filtrados = list(lista_usuarios)

    # Búsqueda inteligente si hay consulta
    if q:
        filtrados = codigos.buscar(q, filtrados)
    else:
        # Ordenar por conexión
        def clave_orden(u):
            c = str(u.get("nro_conexion") or "")
            return int(c) if c.isdigit() else 999999
        filtrados.sort(key=clave_orden)

    total_filtrados = len(filtrados)
    total_paginas = max(1, (total_filtrados + por_pagina - 1) // por_pagina)
    pagina = min(pagina, total_paginas)
    inicio_idx = (pagina - 1) * por_pagina
    fin_idx = inicio_idx + por_pagina
    usuarios_pagina = filtrados[inicio_idx:fin_idx]

    # Datos auxiliares para modales
    cfg = getattr(g, "config", {})
    sectores = cfg.get("sectores", [
        "BARRIO DE CHAUPI", "BARRIO DE PACHAYZA", "BARRIO DE LUCMANI",
        "HUAQUILLO", "CHAUPICERCA", "AYACUCHO"
    ])
    categorias = cfg.get("categorias", {"A": {"nombre": "Doméstico"}})
    mes_actual = cfg.get("mes_actual", {})
    mes_abierto = mes_actual.get("estado") == "ABIERTO"

    try:
        sug_conexion = fb.obtener_siguiente_conexion_libre()
        sug_id_sd = fb.obtener_siguiente_id_sd()
    except Exception:
        sug_conexion = "000800"
        sug_id_sd = "SD-026"

    return render_template(
        "usuarios.html",
        usuarios=usuarios_pagina,
        total_filtrados=total_filtrados,
        total_todos=len(lista_usuarios),
        total_activos=total_activos,
        total_inactivos=total_inactivos,
        total_pendientes=total_pendientes,
        filtro=filtro,
        q=q,
        pagina=pagina,
        total_paginas=total_paginas,
        sectores=sectores,
        categorias=categorias,
        mes_abierto=mes_abierto,
        sug_conexion=sug_conexion,
        sug_id_sd=sug_id_sd,
    )


@app.route("/usuarios/guardar", methods=["POST"])
def usuarios_guardar():
    from respaldo import on_datos_cambiados

    es_edicion = request.form.get("es_edicion") == "1"
    id_usuario = request.form.get("id_usuario", "").strip()
    sin_dni = request.form.get("sin_dni") == "1"
    nombre = request.form.get("nombre", "").strip().upper()
    nro_conexion = request.form.get("nro_conexion", "").strip()
    sector = request.form.get("sector", "").strip()
    direccion = request.form.get("direccion", "").strip().upper()
    codigo_categoria = request.form.get("codigo_categoria", "A").strip()
    activo = request.form.get("activo") == "1"
    agregar_al_mes = request.form.get("agregar_al_mes") == "1"

    # Procesar medidores
    medidores_raw = request.form.get("medidores", "").split(",")
    medidores = []
    for m in medidores_raw:
        m_limpio = m.strip()
        if m_limpio:
            med_norm = codigos.normalizar_medidor(m_limpio)
            if med_norm not in medidores:
                medidores.append(med_norm)

    # Validar ID
    if not es_edicion:
        if sin_dni or not id_usuario:
            id_usuario = fb.obtener_siguiente_id_sd()
        else:
            if id_usuario.isdigit() and len(id_usuario) in (7, 8):
                id_usuario = codigos.normalizar_dni(id_usuario)

        # Verificar existencia
        if fb.obtener_usuario(id_usuario) is not None:
            flash(f"Error: ya existe un usuario con el ID '{id_usuario}'.", "peligro")
            return redirect(url_for("usuarios"))
    else:
        if not id_usuario:
            flash("Error: Falta el ID del usuario a editar.", "peligro")
            return redirect(url_for("usuarios"))

    # Validar medidores únicos entre distintas personas
    valido, err_msg = fb.validar_medidores_unicos(medidores, id_usuario_actual=id_usuario if es_edicion else None)
    if not valido:
        flash(f"Error en medidores: {err_msg}", "peligro")
        return redirect(url_for("usuarios"))

    con_norm = codigos.normalizar_conexion(nro_conexion) if nro_conexion else fb.obtener_siguiente_conexion_libre()

    datos = {
        "nro_conexion": con_norm,
        "nombre": nombre,
        "sector": sector,
        "direccion": direccion,
        "codigo_categoria": codigo_categoria,
        "activo": activo,
        "medidores": medidores,
    }

    try:
        fb.guardar_usuario(id_usuario, datos)
        if agregar_al_mes:
            fb.agregar_usuario_al_mes_actual(id_usuario, datos)

        on_datos_cambiados("usuario_guardado", {"id_usuario": id_usuario, "es_edicion": es_edicion})
        flash(f"Usuario '{nombre}' ({id_usuario}) guardado correctamente.", "exito")
    except Exception as e:
        flash(f"Error al guardar usuario: {e}", "peligro")

    return redirect(url_for("usuarios"))


@app.route("/usuarios/cambiar-estado", methods=["POST"])
def usuarios_cambiar_estado():
    from respaldo import on_datos_cambiados

    id_usuario = request.form.get("id_usuario", "").strip()
    nuevo_estado = request.form.get("activo") == "1"

    if not id_usuario:
        flash("ID de usuario no proporcionado.", "peligro")
        return redirect(url_for("usuarios"))

    try:
        fb.actualizar_usuario(id_usuario, {"activo": nuevo_estado})
        on_datos_cambiados("usuario_estado", {"id_usuario": id_usuario, "activo": nuevo_estado})
        estado_txt = "activado" if nuevo_estado else "desactivado"
        flash(f"Usuario '{id_usuario}' {estado_txt} correctamente.", "info")
    except Exception as e:
        flash(f"Error al cambiar estado: {e}", "peligro")

    return redirect(request.referrer or url_for("usuarios"))


@app.route("/usuarios/corregir-dni", methods=["POST"])
def usuarios_corregir_dni():
    from respaldo import on_datos_cambiados

    id_viejo = request.form.get("id_viejo", "").strip()
    dni_nuevo_raw = request.form.get("id_nuevo", "").strip()

    if not id_viejo or not dni_nuevo_raw:
        flash("Debes indicar tanto el ID actual como el nuevo DNI.", "peligro")
        return redirect(url_for("usuarios"))

    # Validar que sea un DNI numérico de 7 u 8 dígitos
    if not dni_nuevo_raw.isdigit() or len(dni_nuevo_raw) not in (7, 8):
        flash(f"El DNI ingresado ('{dni_nuevo_raw}') no es válido. Debe contener 8 dígitos numéricos.", "peligro")
        return redirect(url_for("usuarios"))

    id_nuevo = codigos.normalizar_dni(dni_nuevo_raw)

    try:
        res = fb.corregir_dni_usuario(id_viejo, id_nuevo)
        on_datos_cambiados("corregir_dni", res)
        meses_txt = f" (Actualizado en {len(res['meses_actualizados'])} meses)" if res['meses_actualizados'] else ""
        flash(f"DNI corregido con éxito: '{id_viejo}' ahora es '{id_nuevo}'.{meses_txt}", "exito")
    except ValueError as ve:
        flash(str(ve), "peligro")
    except Exception as e:
        flash(f"Error durante la corrección de DNI: {e}", "peligro")

    return redirect(url_for("usuarios"))


@app.route("/api/usuarios/<id_usuario>")
def api_usuario_detalle(id_usuario: str):
    u = fb.obtener_usuario(id_usuario)
    if u is None:
        return {"error": "Usuario no encontrado"}, 404
    u_copia = dict(u)
    u_copia["id_usuario"] = id_usuario
    return u_copia


@app.route("/lecturas")
def lecturas():
    return render_template("lecturas.html")


@app.route("/recibos")
def recibos():
    return render_template("recibos.html")


@app.route("/cobros")
def cobros():
    return render_template("cobros.html")


@app.route("/configuracion")
def configuracion():
    return render_template("configuracion.html")


# ---------------------------------------------------------------------------
# API: actualizar caché
# ---------------------------------------------------------------------------

@app.route("/api/actualizar", methods=["POST"])
def api_actualizar():
    """Limpia la caché y fuerza recarga desde Firestore."""
    fb.limpiar_cache(limpiar_config=True)
    return redirect(request.referrer or url_for("inicio"))


# ---------------------------------------------------------------------------
# Manejo de errores
# ---------------------------------------------------------------------------

@app.errorhandler(404)
def pagina_no_encontrada(e):
    return render_template("error.html", codigo=404,
                           mensaje="Página no encontrada"), 404


@app.errorhandler(500)
def error_interno(e):
    return render_template("error.html", codigo=500,
                           mensaje="Error interno del servidor"), 500


# ---------------------------------------------------------------------------
# Inicio
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print(f"\n{'='*50}")
    print("  CAAPD Ispacas — Sistema de facturación")
    print(f"  Abre en tu navegador: http://127.0.0.1:{PUERTO}")
    print(f"{'='*50}\n")
    app.run(host="127.0.0.1", port=PUERTO, debug=DEBUG)
