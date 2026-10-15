package com.caapd.lecturas

import com.google.firebase.firestore.FirebaseFirestore
import com.google.firebase.firestore.Source
import com.google.firebase.firestore.ktx.firestore
import com.google.firebase.ktx.Firebase
import kotlinx.coroutines.tasks.await

// ─── Parser Firestore → Modelos ───────────────────────────────────────────────

@Suppress("UNCHECKED_CAST")
fun parsearDocMes(id: String, data: Map<String, Any>): DocumentoMes {
    val medidoresRaw = data["medidores"] as? List<Map<String, Any>> ?: emptyList()
    val medidores = medidoresRaw.map { m ->
        EntradaMedidor(
            nroMedidor      = m["nro_medidor"]?.toString() ?: "",
            lecturaAnterior = (m["lectura_anterior"] as? Number)?.toLong() ?: 0L,
            fechaAnterior   = m["fecha_anterior"]?.toString() ?: "",
            consumoAnterior = (m["consumo_anterior"] as? Number)?.toLong() ?: 0L,
            lecturaActual   = (m["lectura_actual"] as? Number)?.toLong(),
            fechaLectura    = m["fecha_lectura"]?.toString(),
            estadoLectura   = m["estado_lectura"]?.toString() ?: "PENDIENTE",
            novedad         = m["novedad"]?.toString() ?: "NORMAL",
            nota            = m["nota"]?.toString() ?: "",
            registradoPor   = m["registrado_por"]?.toString() ?: "",
        )
    }
    val historial = (data["historial_m3"] as? List<*>)
        ?.mapNotNull { (it as? Number)?.toLong() } ?: emptyList()

    return DocumentoMes(
        idUsuario      = id,
        nroConexion    = data["nro_conexion"]?.toString() ?: "",
        nombre         = data["nombre"]?.toString() ?: "",
        sector         = data["sector"]?.toString() ?: "",
        direccion      = data["direccion"]?.toString() ?: "",
        medidores      = medidores,
        consumoTotalM3 = (data["consumo_total_m3"] as? Number)?.toLong(),
        historialM3    = historial,
    )
}

/** Serializa un EntradaMedidor al Map que Firestore espera. */
fun EntradaMedidor.aMap(): Map<String, Any?> = mapOf(
    "nro_medidor"      to nroMedidor,
    "lectura_anterior" to lecturaAnterior,
    "fecha_anterior"   to fechaAnterior,
    "consumo_anterior" to consumoAnterior,
    "lectura_actual"   to lecturaActual,
    "fecha_lectura"    to fechaLectura,
    "estado_lectura"   to estadoLectura,
    "novedad"          to novedad,
    "nota"             to nota,
    "registrado_por"   to registradoPor,
)

// ─── Repositorio Firebase ─────────────────────────────────────────────────────

object Repositorio {
    private val db: FirebaseFirestore get() = Firebase.firestore

    /**
     * Carga config/general. Intenta caché local primero (funciona offline),
     * si falla va al servidor.
     */
    @Suppress("UNCHECKED_CAST")
    suspend fun cargarConfig(): ConfigApp {
        val snap = try {
            db.collection("config").document("general").get(Source.CACHE).await()
                .takeIf { it.exists() }
                ?: db.collection("config").document("general").get().await()
        } catch (_: Exception) {
            db.collection("config").document("general").get().await()
        }

        val periodo   = (snap.get("mes_actual") as? Map<*, *>)?.get("periodo")?.toString() ?: ""
        val estado    = (snap.get("mes_actual") as? Map<*, *>)?.get("estado")?.toString() ?: "CERRADO"
        val sectores  = (snap.get("sectores") as? List<*>)?.map { it.toString() } ?: emptyList()

        val obsRaw = snap.get("observaciones") as? List<Map<String, Any>> ?: emptyList()
        val observaciones = if (obsRaw.isEmpty()) OBSERVACIONES_FALLBACK else
            obsRaw.map { o ->
                Observacion(
                    codigo = o["codigo"]?.toString() ?: "",
                    texto  = o["texto"]?.toString() ?: "",
                    alerta = o["alerta"] as? Boolean ?: false,
                )
            }

        return ConfigApp(periodo, estado, sectores, observaciones)
    }

    /** Carga todos los documentos del mes del sector desde Firestore. */
    suspend fun cargarMes(periodo: String): Map<String, DocumentoMes> {
        val snap = db.collection("mes_$periodo").get().await()
        return snap.documents.mapNotNull { doc ->
            doc.data?.let { data -> doc.id to parsearDocMes(doc.id, data) }
        }.toMap()
    }

    /**
     * Actualiza medidores y consumo_total_m3 en Firestore.
     * SIN await → offline-first; Firestore sincroniza cuando hay internet.
     */
    fun guardarLectura(
        periodo: String,
        idUsuario: String,
        medidores: List<EntradaMedidor>,
        consumoTotal: Long?,
    ) {
        val datos = mapOf(
            "medidores"        to medidores.map { it.aMap() },
            "consumo_total_m3" to consumoTotal,
        )
        db.collection("mes_$periodo").document(idUsuario).update(datos)
        // No llamamos .await() → el SDK encola la escritura y la envía cuando haya red
    }
}
