package com.caapd.lecturas

import java.text.Normalizer

// ═════════════════════════════════════════════════════════════════════════════
// LÓGICA PURA — sin dependencias de Android ni Firebase
// Todas las funciones son deterministas y testeables con JUnit/Robolectric.
// ═════════════════════════════════════════════════════════════════════════════

/**
 * Calcula el consumo de UN medidor según las reglas del sistema.
 * - actual >= anterior  → consumo = actual - anterior
 * - actual < anterior y novedad = CAMBIO_MEDIDOR → consumo = actual (nuevo desde cero)
 * - cualquier otro caso → null (lectura inválida)
 */
fun calcularConsumoDeMedidor(actual: Long?, anterior: Long, novedad: String): Long? {
    if (actual == null) return null
    return when {
        actual >= anterior            -> actual - anterior
        novedad == "CAMBIO_MEDIDOR"   -> actual
        else                          -> null
    }
}

/**
 * Suma los consumos de todos los medidores de un usuario.
 * Devuelve null si algún medidor aún no tiene lectura.
 */
fun calcularConsumoTotal(medidores: List<EntradaMedidor>): Long? {
    var suma = 0L
    for (m in medidores) {
        val c = calcularConsumoDeMedidor(m.lecturaActual, m.lecturaAnterior, m.novedad)
            ?: return null
        suma += c
    }
    return suma
}

/**
 * Búsqueda inteligente:
 * - Solo dígitos con menos de 6 chars → busca con ceros a la izq. primero, luego contiene.
 * - 6 o más dígitos → busca tal cual (sin agregar ceros).
 * - Con letras → busca en nombre, sin tildes/mayúsculas, todas las palabras en cualquier orden.
 */
fun buscar(consulta: String, documentos: List<DocumentoMes>): List<DocumentoMes> {
    val q = consulta.trim()
    if (q.isEmpty()) return documentos

    val soloDigitos = q.all { it.isDigit() }
    return if (soloDigitos) {
        val MIN = 6
        if (q.length < MIN) {
            val conCeros  = q.padStart(MIN, '0')
            val exactos   = documentos.filter { d ->
                d.nroConexion == conCeros || d.medidores.any { m -> m.nroMedidor == conCeros }
            }
            val contienen = documentos.filter { d ->
                d !in exactos && (
                    d.nroConexion.contains(q) || d.medidores.any { m -> m.nroMedidor.contains(q) }
                )
            }
            exactos + contienen
        } else {
            documentos.filter { d ->
                d.nroConexion == q || d.nroConexion.contains(q) ||
                d.medidores.any { m -> m.nroMedidor == q || m.nroMedidor.contains(q) }
            }
        }
    } else {
        val palabras = q.lowercase().sinTildes().split(" ").filter { it.isNotBlank() }
        documentos.filter { d ->
            val nombreNorm = d.nombre.lowercase().sinTildes()
            palabras.all { p -> nombreNorm.contains(p) }
        }
    }
}

fun String.sinTildes(): String {
    val nfd = Normalizer.normalize(this, Normalizer.Form.NFD)
    return nfd.replace(Regex("\\p{InCombiningDiacriticalMarks}+"), "")
}

/**
 * Devuelve el siguiente usuario con algún medidor PENDIENTE,
 * ordenado alfabéticamente, excluyendo al usuario actual.
 */
fun siguientePendiente(docs: List<DocumentoMes>, idActual: String? = null): DocumentoMes? =
    docs.filter { d ->
        d.idUsuario != idActual && d.medidores.any { m -> m.estadoLectura == "PENDIENTE" }
    }.sortedBy { it.nombre }.firstOrNull()

/**
 * True si el consumo es mayor a 3× el promedio del historial o mayor a 100 m³.
 */
fun esConsumoAtipico(consumo: Long, historial: List<Long>): Boolean {
    if (consumo > 100L) return true
    if (historial.isEmpty()) return false
    return consumo > historial.average() * 3
}
