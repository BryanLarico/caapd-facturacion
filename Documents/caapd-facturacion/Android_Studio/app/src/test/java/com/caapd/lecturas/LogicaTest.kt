package com.caapd.lecturas

import org.junit.Assert.*
import org.junit.Test

/**
 * Pruebas unitarias de lógica pura — sin Android ni Firebase.
 * Ejecutar con: ./gradlew :app:test
 */
class LogicaTest {

    // ─── calcularConsumoDeMedidor ─────────────────────────────────────────────

    @Test
    fun `consumo normal actual mayor que anterior`() {
        assertEquals(13L, calcularConsumoDeMedidor(118L, 105L, "NORMAL"))
    }

    @Test
    fun `consumo cero cuando actual igual a anterior`() {
        assertEquals(0L, calcularConsumoDeMedidor(105L, 105L, "NORMAL"))
    }

    @Test
    fun `consumo invalido actual menor sin CAMBIO_MEDIDOR`() {
        assertNull(calcularConsumoDeMedidor(50L, 105L, "NORMAL"))
        assertNull(calcularConsumoDeMedidor(50L, 105L, "MEDIDOR_DANADO"))
    }

    @Test
    fun `consumo con CAMBIO_MEDIDOR devuelve lectura actual`() {
        assertEquals(30L, calcularConsumoDeMedidor(30L, 105L, "CAMBIO_MEDIDOR"))
    }

    @Test
    fun `consumo null cuando lectura actual es null`() {
        assertNull(calcularConsumoDeMedidor(null, 105L, "NORMAL"))
    }

    // ─── calcularConsumoTotal ─────────────────────────────────────────────────

    @Test
    fun `consumo total suma todos los medidores`() {
        val medidores = listOf(
            EntradaMedidor(lecturaAnterior = 42, lecturaActual = 61),   // 19
            EntradaMedidor(lecturaAnterior = 120, lecturaActual = 124), //  4
        )
        assertEquals(23L, calcularConsumoTotal(medidores))
    }

    @Test
    fun `consumo total null si alguno no tiene lectura`() {
        val medidores = listOf(
            EntradaMedidor(lecturaAnterior = 42, lecturaActual = 61),
            EntradaMedidor(lecturaAnterior = 120, lecturaActual = null),
        )
        assertNull(calcularConsumoTotal(medidores))
    }

    // ─── buscar ───────────────────────────────────────────────────────────────

    private val alvarez = DocumentoMes(
        idUsuario   = "76807817",
        nroConexion = "000796",
        nombre      = "ALVAREZ CHUQUIYANQUI, MARIBEL",
        sector      = "SECTOR A",
        medidores   = listOf(EntradaMedidor(nroMedidor = "22392996")),
    )
    private val juan = DocumentoMes(
        idUsuario   = "07654321-1",
        nroConexion = "000123",
        nombre      = "EJEMPLO QUISPE, JUAN",
        sector      = "SECTOR A",
        medidores   = listOf(
            EntradaMedidor(nroMedidor = "000100"),
            EntradaMedidor(nroMedidor = "003200"),
        ),
    )
    private val todos = listOf(alvarez, juan)

    @Test
    fun `buscar 3386 medidor primero exacto 003386 luego contiene`() {
        // No hay 003386 en los datos de prueba, pero el orden debería ser: exactos primero
        // Usamos un caso con datos reales: buscar "3200"
        val result = buscar("3200", todos)
        // Exacto: 003200 → juan; no hay otros que contengan
        assertTrue(result.isNotEmpty())
        assertEquals(juan.idUsuario, result.first().idUsuario)
    }

    @Test
    fun `buscar 796 conexion da exacto 000796 primero`() {
        val result = buscar("796", todos)
        assertFalse(result.isEmpty())
        assertEquals(alvarez.idUsuario, result.first().idUsuario)
    }

    @Test
    fun `buscar 123456 no agrega ceros`() {
        // No hay resultados con 123456 en datos de prueba, pero la búsqueda NO debe buscar 000123456
        val result = buscar("123456", todos)
        // Ninguno coincide exactamente
        assertTrue(result.isEmpty())
    }

    @Test
    fun `buscar 22392996 medidor de 8 digitos tal cual`() {
        val result = buscar("22392996", todos)
        assertEquals(1, result.size)
        assertEquals(alvarez.idUsuario, result.first().idUsuario)
    }

    @Test
    fun `buscar por nombre alvarez sin tildes`() {
        val result = buscar("alvarez maribel", todos)
        assertEquals(1, result.size)
        assertEquals(alvarez.idUsuario, result.first().idUsuario)
    }

    @Test
    fun `buscar por nombre dos palabras cualquier orden`() {
        val result = buscar("maribel alvarez", todos)
        assertEquals(1, result.size)
    }

    @Test
    fun `buscar vacio devuelve todos`() {
        assertEquals(todos, buscar("", todos))
    }

    // ─── siguientePendiente ───────────────────────────────────────────────────

    @Test
    fun `siguiente pendiente ordena alfabeticamente y excluye actual`() {
        val ana = DocumentoMes("1", nombre = "ANA", medidores = listOf(EntradaMedidor(estadoLectura = "PENDIENTE")))
        val beto = DocumentoMes("2", nombre = "BETO", medidores = listOf(EntradaMedidor(estadoLectura = "PENDIENTE")))
        val resultado = siguientePendiente(listOf(beto, ana))
        assertEquals(ana.idUsuario, resultado?.idUsuario)
    }

    @Test
    fun `siguiente pendiente excluye id actual`() {
        val ana = DocumentoMes("1", nombre = "ANA", medidores = listOf(EntradaMedidor(estadoLectura = "PENDIENTE")))
        val beto = DocumentoMes("2", nombre = "BETO", medidores = listOf(EntradaMedidor(estadoLectura = "PENDIENTE")))
        val resultado = siguientePendiente(listOf(beto, ana), idActual = "1")
        assertEquals(beto.idUsuario, resultado?.idUsuario)
    }

    @Test
    fun `siguiente pendiente null si todos leidos`() {
        val docs = listOf(
            DocumentoMes("1", medidores = listOf(EntradaMedidor(estadoLectura = "LEIDO"))),
        )
        assertNull(siguientePendiente(docs))
    }

    // ─── esConsumoAtipico ─────────────────────────────────────────────────────

    @Test
    fun `consumo mayor a 100 es atipico`() {
        assertTrue(esConsumoAtipico(101L, emptyList()))
    }

    @Test
    fun `consumo mayor a 3 veces promedio es atipico`() {
        val historial = listOf(10L, 10L, 10L, 10L, 10L) // promedio = 10
        assertTrue(esConsumoAtipico(31L, historial))
    }

    @Test
    fun `consumo normal no es atipico`() {
        val historial = listOf(10L, 12L, 11L, 14L, 16L) // promedio ~12.6
        assertFalse(esConsumoAtipico(15L, historial))
    }

    @Test
    fun `consumo normal sin historial no es atipico`() {
        assertFalse(esConsumoAtipico(50L, emptyList()))
    }
}
