package com.caapd.lecturas

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.auth.ktx.auth
import com.google.firebase.ktx.Firebase
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.tasks.await

// ═════════════════════════════════════════════════════════════════════════════
// AuthViewModel — login con correo/contraseña, sesión persistente sin internet
// ═════════════════════════════════════════════════════════════════════════════

class AuthViewModel : ViewModel() {

    private val auth: FirebaseAuth = Firebase.auth

    sealed class Estado {
        data object Cargando      : Estado()
        data object Autenticado   : Estado()
        data object NoAutenticado : Estado()
        data class  Error(val mensaje: String) : Estado()
    }

    private val _estado = MutableStateFlow<Estado>(Estado.Cargando)
    val estado: StateFlow<Estado> = _estado.asStateFlow()

    init {
        // Si Firebase ya tiene sesión activa (token guardado) → entra directo, incluso offline
        _estado.value = if (auth.currentUser != null) Estado.Autenticado else Estado.NoAutenticado
    }

    fun iniciarSesion(correo: String, clave: String) {
        if (correo.isBlank() || clave.isBlank()) {
            _estado.value = Estado.Error("Completa el correo y la contraseña.")
            return
        }
        _estado.value = Estado.Cargando
        viewModelScope.launch {
            try {
                auth.signInWithEmailAndPassword(correo.trim(), clave).await()
                _estado.value = Estado.Autenticado
            } catch (e: Exception) {
                _estado.value = Estado.Error(mensajeAmigable(e))
            }
        }
    }

    /** Solo se llama por acción explícita del usuario (menú → "Cerrar sesión"). */
    fun cerrarSesion() {
        auth.signOut()
        _estado.value = Estado.NoAutenticado
    }

    val correoActual: String? get() = auth.currentUser?.email

    private fun mensajeAmigable(e: Exception): String = when {
        e.message?.contains("INVALID_EMAIL")     == true -> "El correo no es válido."
        e.message?.contains("WRONG_PASSWORD")    == true -> "Contraseña incorrecta."
        e.message?.contains("TOO_MANY_REQUESTS") == true -> "Demasiados intentos. Espera un momento."
        e.message?.contains("USER_NOT_FOUND")    == true -> "No existe una cuenta con ese correo."
        e.message?.contains("network")           == true -> "Sin conexión. Verifica el Wi-Fi o los datos."
        else -> "Error al iniciar sesión. Intenta de nuevo."
    }
}

// ═════════════════════════════════════════════════════════════════════════════
// SectoresViewModel — carga única, caché en memoria, filtro local
// ═════════════════════════════════════════════════════════════════════════════

class SectoresViewModel : ViewModel() {

    sealed class Estado {
        data object Cargando : Estado()
        data class  Listo(val config: ConfigApp, val sectores: List<EstadoSector>) : Estado()
        data class  Error(val mensaje: String) : Estado()
    }

    private val _estado = MutableStateFlow<Estado>(Estado.Cargando)
    val estado: StateFlow<Estado> = _estado.asStateFlow()

    // Caché en memoria — se filtra localmente, sin volver a Firestore
    private val _docsCache = mutableMapOf<String, DocumentoMes>()
    val docsCache: Map<String, DocumentoMes> get() = _docsCache

    private var _config: ConfigApp = ConfigApp()

    init { cargar() }

    fun cargar() {
        _estado.value = Estado.Cargando
        viewModelScope.launch {
            try {
                val config = Repositorio.cargarConfig()
                _config = config

                if (config.periodo.isNotEmpty()) {
                    val docs = Repositorio.cargarMes(config.periodo)
                    _docsCache.clear()
                    _docsCache.putAll(docs)
                }

                val estadosSectores = config.sectores.map { sector ->
                    val docs = _docsCache.values.filter { it.sector == sector }
                    EstadoSector(
                        nombre    = sector,
                        total     = docs.size,
                        leidos    = docs.count { d -> d.medidores.all { m -> m.estadoLectura != "PENDIENTE" } },
                        sinAcceso = docs.count { d -> d.medidores.any { m -> m.estadoLectura == "SIN_ACCESO" } },
                    )
                }

                _estado.value = Estado.Listo(config, estadosSectores)
            } catch (e: Exception) {
                _estado.value = Estado.Error("No se pudo cargar: ${e.message}")
            }
        }
    }

    /** Documentos del sector, ordenados alfabéticamente por nombre. */
    fun docsDelSector(sector: String): List<DocumentoMes> =
        _docsCache.values.filter { it.sector == sector }.sortedBy { it.nombre }

    /** Actualiza la caché local sin volver a Firestore. */
    fun actualizarEnCache(doc: DocumentoMes) {
        _docsCache[doc.idUsuario] = doc
    }
}

// ═════════════════════════════════════════════════════════════════════════════
// LecturaViewModel — guardar la lectura de un medidor (offline-first)
// ═════════════════════════════════════════════════════════════════════════════

class LecturaViewModel : ViewModel() {

    sealed class Resultado {
        data object Nada    : Resultado()
        data object Guardado: Resultado()
        data class  Error(val mensaje: String) : Resultado()
    }

    private val _resultado = MutableStateFlow<Resultado>(Resultado.Nada)
    val resultado: StateFlow<Resultado> = _resultado.asStateFlow()

    private val _guardando = MutableStateFlow(false)
    val guardando: StateFlow<Boolean> = _guardando.asStateFlow()

    fun resetResultado() { _resultado.value = Resultado.Nada }

    fun guardarLectura(
        periodo: String,
        doc: DocumentoMes,
        medidorActualizado: EntradaMedidor,
        indice: Int,
        correoLector: String,
    ) {
        _guardando.value = true
        viewModelScope.launch {
            try {
                val nuevaLista = doc.medidores.toMutableList().apply {
                    set(indice, medidorActualizado.copy(registradoPor = correoLector))
                }
                val consumoTotal = calcularConsumoTotal(nuevaLista)

                // Sin await → Firestore encola y sincroniza cuando hay internet
                Repositorio.guardarLectura(periodo, doc.idUsuario, nuevaLista, consumoTotal)

                _resultado.value = Resultado.Guardado
            } catch (e: Exception) {
                _resultado.value = Resultado.Error("Error al guardar: ${e.message}")
            } finally {
                _guardando.value = false
            }
        }
    }
}
