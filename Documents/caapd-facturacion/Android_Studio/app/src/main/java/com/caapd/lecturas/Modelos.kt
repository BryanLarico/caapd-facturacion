package com.caapd.lecturas

// ═════════════════════════════════════════════════════════════════════════════
// MODELOS DE DATOS
// ═════════════════════════════════════════════════════════════════════════════

data class Observacion(
    val codigo: String = "",
    val texto: String  = "",
    val alerta: Boolean = false,
)

/** Catálogo de respaldo si Firestore no carga las observaciones. */
val OBSERVACIONES_FALLBACK = listOf(
    Observacion("NORMAL",           "Normal",                    false),
    Observacion("MEDIDOR_DANADO",   "Medidor dañado",            true),
    Observacion("MEDIDOR_EMPANADO", "Medidor empañado/ilegible", true),
    Observacion("FUGA_VISIBLE",     "Fuga visible",              true),
    Observacion("SIN_MEDIDOR",      "Sin medidor",               true),
    Observacion("CASA_CERRADA",     "Casa cerrada",              true),
    Observacion("LECTURA_ESTIMADA", "Lectura estimada",          true),
    Observacion("CAMBIO_MEDIDOR",   "Cambio de medidor",         true),
    Observacion("OTRO",             "Otro",                      true),
)

data class EntradaMedidor(
    val nroMedidor: String   = "",
    val lecturaAnterior: Long = 0L,
    val fechaAnterior: String = "",
    val consumoAnterior: Long = 0L,
    val lecturaActual: Long?  = null,
    val fechaLectura: String? = null,
    val estadoLectura: String = "PENDIENTE", // PENDIENTE | LEIDO | SIN_ACCESO
    val novedad: String       = "NORMAL",
    val nota: String          = "",
    val registradoPor: String = "",
)

data class DocumentoMes(
    val idUsuario: String               = "",
    val nroConexion: String             = "",
    val nombre: String                  = "",
    val sector: String                  = "",
    val direccion: String               = "",
    val medidores: List<EntradaMedidor> = emptyList(),
    val consumoTotalM3: Long?           = null,
    val historialM3: List<Long>         = emptyList(),
)

data class EstadoSector(
    val nombre: String = "",
    val total: Int     = 0,
    val leidos: Int    = 0,
    val sinAcceso: Int = 0,
)

data class ConfigApp(
    val periodo: String                  = "",
    val estadoMes: String                = "CERRADO",
    val sectores: List<String>           = emptyList(),
    val observaciones: List<Observacion> = OBSERVACIONES_FALLBACK,
)
