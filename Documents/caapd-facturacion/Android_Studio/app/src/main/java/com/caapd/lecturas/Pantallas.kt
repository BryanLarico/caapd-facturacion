package com.caapd.lecturas

import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.caapd.lecturas.ui.theme.*
import kotlinx.coroutines.launch
import java.net.InetSocketAddress
import java.net.Socket
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

// ─── Funciones utilitarias ───────────────────────────────────────────────────

fun fechaHoy(): String = SimpleDateFormat("yyyy-MM-dd", Locale.US).format(Date())

suspend fun hayInternet(): Boolean = runCatching {
    Socket().use { s -> s.connect(InetSocketAddress("8.8.8.8", 53), 1000); true }
}.getOrDefault(false)

// ═════════════════════════════════════════════════════════════════════════════
// NAVEGACIÓN PRINCIPAL
// ═════════════════════════════════════════════════════════════════════════════

@Composable
fun AppPrincipal() {
    val authVm: AuthViewModel = viewModel()
    val estado by authVm.estado.collectAsState()

    when (estado) {
        is AuthViewModel.Estado.Cargando -> {
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                CircularProgressIndicator(color = AzulPrimario)
            }
        }
        is AuthViewModel.Estado.NoAutenticado,
        is AuthViewModel.Estado.Error -> PantallaLogin(authVm)
        is AuthViewModel.Estado.Autenticado -> {
            val sectoresVm: SectoresViewModel = viewModel()
            val nav = rememberNavController()
            NavHost(navController = nav, startDestination = "sectores") {
                composable("sectores") {
                    PantallaSectores(nav, authVm, sectoresVm)
                }
                composable(
                    route = "lista/{sector}",
                    arguments = listOf(navArgument("sector") { type = NavType.StringType }),
                ) { back ->
                    PantallaListaSector(nav, sectoresVm, back.arguments?.getString("sector") ?: "")
                }
                composable(
                    route = "lectura/{sector}/{idUsuario}/{indice}",
                    arguments = listOf(
                        navArgument("sector")   { type = NavType.StringType },
                        navArgument("idUsuario"){ type = NavType.StringType },
                        navArgument("indice")   { type = NavType.IntType },
                    ),
                ) { back ->
                    PantallaLectura(
                        nav          = nav,
                        authVm       = authVm,
                        sectoresVm   = sectoresVm,
                        sector       = back.arguments?.getString("sector")    ?: "",
                        idUsuario    = back.arguments?.getString("idUsuario") ?: "",
                        indiceMedidor = back.arguments?.getInt("indice")       ?: 0,
                    )
                }
            }
        }
    }
}

// ═════════════════════════════════════════════════════════════════════════════
// PANTALLA 1 — LOGIN
// ═════════════════════════════════════════════════════════════════════════════

@Composable
fun PantallaLogin(authVm: AuthViewModel) {
    var correo by remember { mutableStateOf("") }
    var clave  by remember { mutableStateOf("") }
    val estado by authVm.estado.collectAsState()

    Box(
        modifier = Modifier.fillMaxSize().background(FondoGris),
        contentAlignment = Alignment.Center,
    ) {
        Card(
            modifier  = Modifier.fillMaxWidth().padding(24.dp),
            shape     = RoundedCornerShape(16.dp),
            colors    = CardDefaults.cardColors(containerColor = SuperficieBlanca),
            elevation = CardDefaults.cardElevation(4.dp),
        ) {
            Column(
                modifier = Modifier.padding(24.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(14.dp),
            ) {
                Image(
                    painter = painterResource(R.drawable.ic_launcher_con_fondo),
                    contentDescription = "CAAPD Ispacas",
                    modifier = Modifier.size(80.dp).clip(RoundedCornerShape(18.dp)),
                )
                Text("CAAPD Ispacas", style = MaterialTheme.typography.titleLarge, color = AzulPrimario)
                Text("Lecturas de medidores", style = MaterialTheme.typography.bodyMedium, color = TextoSecundario)
                Spacer(Modifier.height(4.dp))

                OutlinedTextField(
                    value = correo, onValueChange = { correo = it },
                    label = { Text("Correo electrónico") }, singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email),
                    modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    value = clave, onValueChange = { clave = it },
                    label = { Text("Contraseña") }, singleLine = true,
                    visualTransformation = PasswordVisualTransformation(),
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
                    modifier = Modifier.fillMaxWidth(),
                )

                if (estado is AuthViewModel.Estado.Error) {
                    Text(
                        (estado as AuthViewModel.Estado.Error).mensaje,
                        color = RojoError,
                        style = MaterialTheme.typography.bodySmall,
                    )
                }

                Button(
                    onClick = { authVm.iniciarSesion(correo, clave) },
                    enabled = estado !is AuthViewModel.Estado.Cargando,
                    modifier = Modifier.fillMaxWidth().height(52.dp),
                    shape  = RoundedCornerShape(10.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = AzulPrimario),
                ) {
                    if (estado is AuthViewModel.Estado.Cargando)
                        CircularProgressIndicator(color = Color.White, modifier = Modifier.size(22.dp), strokeWidth = 2.dp)
                    else
                        Text("Entrar", style = MaterialTheme.typography.labelLarge, color = Color.White)
                }
            }
        }
    }
}

// ═════════════════════════════════════════════════════════════════════════════
// PANTALLA 2 — SECTORES
// ═════════════════════════════════════════════════════════════════════════════

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PantallaSectores(nav: NavHostController, authVm: AuthViewModel, sectoresVm: SectoresViewModel) {
    val estado by sectoresVm.estado.collectAsState()
    var menuAbierto    by remember { mutableStateOf(false) }
    var confirmarSalir by remember { mutableStateOf(false) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(10.dp),
                    ) {
                        Image(
                            painter = painterResource(R.drawable.ic_gota_agua),
                            contentDescription = null,
                            modifier = Modifier.size(24.dp),
                        )
                        Text("CAAPD Ispacas", color = Color.White)
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = AzulPrimario),
                actions = {
                    IconButton(onClick = { menuAbierto = true }) {
                        Icon(Icons.Default.MoreVert, "Menú", tint = Color.White)
                    }
                    DropdownMenu(expanded = menuAbierto, onDismissRequest = { menuAbierto = false }) {
                        DropdownMenuItem(
                            text = { Text("Actualizar datos") },
                            onClick = { menuAbierto = false; sectoresVm.cargar() },
                        )
                        DropdownMenuItem(
                            text = { Text("Cerrar sesión", color = RojoError) },
                            onClick = { menuAbierto = false; confirmarSalir = true },
                        )
                    }
                }
            )
        },
        containerColor = FondoGris,
    ) { padding ->

        if (confirmarSalir) {
            AlertDialog(
                onDismissRequest = { confirmarSalir = false },
                title = { Text("¿Cerrar sesión?") },
                text  = { Text("Tendrás que volver a ingresar tu contraseña con internet.") },
                confirmButton = {
                    TextButton(onClick = { confirmarSalir = false; authVm.cerrarSesion() }) {
                        Text("Sí, salir", color = RojoError)
                    }
                },
                dismissButton = {
                    TextButton(onClick = { confirmarSalir = false }) { Text("Cancelar") }
                }
            )
        }

        Box(Modifier.fillMaxSize().padding(padding)) {
            when (val e = estado) {
                is SectoresViewModel.Estado.Cargando ->
                    CircularProgressIndicator(Modifier.align(Alignment.Center), color = AzulPrimario)

                is SectoresViewModel.Estado.Error ->
                    Column(Modifier.align(Alignment.Center).padding(24.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                        Text(e.mensaje, color = RojoError)
                        Spacer(Modifier.height(12.dp))
                        Button(onClick = { sectoresVm.cargar() }) { Text("Reintentar") }
                    }

                is SectoresViewModel.Estado.Listo -> {
                    val mesAbierto = e.config.estadoMes == "ABIERTO"
                    LazyColumn(
                        Modifier.fillMaxSize(),
                        contentPadding = PaddingValues(16.dp),
                        verticalArrangement = Arrangement.spacedBy(12.dp),
                    ) {
                        if (!mesAbierto) {
                            item {
                                Card(
                                    Modifier.fillMaxWidth(),
                                    colors = CardDefaults.cardColors(containerColor = Color(0xFFFFF3E0)),
                                    shape  = RoundedCornerShape(10.dp),
                                ) {
                                    Text(
                                        "⚠ El mes está ${e.config.estadoMes}. Solo puedes consultar, no ingresar lecturas.",
                                        Modifier.padding(14.dp), color = NaranjaAviso,
                                        style = MaterialTheme.typography.bodyMedium,
                                    )
                                }
                            }
                        }
                        item {
                            Text(
                                "Periodo: ${e.config.periodo.ifEmpty { "Sin mes activo" }}  •  ${e.config.estadoMes}",
                                style = MaterialTheme.typography.bodySmall,
                                color = TextoSecundario,
                                modifier = Modifier.padding(horizontal = 4.dp),
                            )
                        }
                        items(e.sectores) { sector ->
                            TarjetaSector(sector) { nav.navigate("lista/${sector.nombre}") }
                        }
                    }
                }
            }
        }
    }
}

@Composable
fun TarjetaSector(sector: EstadoSector, onClick: () -> Unit) {
    val progreso = if (sector.total > 0) sector.leidos.toFloat() / sector.total else 0f
    Card(
        modifier  = Modifier.fillMaxWidth().clickable(onClick = onClick),
        shape     = RoundedCornerShape(12.dp),
        colors    = CardDefaults.cardColors(containerColor = SuperficieBlanca),
        elevation = CardDefaults.cardElevation(2.dp),
    ) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Text(sector.nombre, style = MaterialTheme.typography.bodyLarge)
                Text("${sector.leidos}/${sector.total}", style = MaterialTheme.typography.bodyMedium, color = AzulPrimario)
            }
            LinearProgressIndicator(
                progress    = { progreso },
                modifier    = Modifier.fillMaxWidth().height(6.dp).clip(RoundedCornerShape(3.dp)),
                color       = VerdeGuardar,
                trackColor  = GrisNeutro,
            )
            if (sector.sinAcceso > 0)
                Text("${sector.sinAcceso} sin acceso", style = MaterialTheme.typography.bodySmall, color = NaranjaAviso)
        }
    }
}

// ═════════════════════════════════════════════════════════════════════════════
// PANTALLA 3 — LISTA DEL SECTOR
// ═════════════════════════════════════════════════════════════════════════════

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PantallaListaSector(nav: NavHostController, sectoresVm: SectoresViewModel, sector: String) {
    var consulta   by remember { mutableStateOf("") }
    var filtro     by remember { mutableStateOf("Todos") }
    val estadoVm   by sectoresVm.estado.collectAsState()
    var conInternet by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()

    LaunchedEffect(Unit) { scope.launch { conInternet = hayInternet() } }

    val todos = sectoresVm.docsDelSector(sector)
    val filtrados = remember(consulta, filtro, todos) {
        val porEstado = when (filtro) {
            "Pendientes" -> todos.filter { d -> d.medidores.any { it.estadoLectura == "PENDIENTE" } }
            "Leídos"     -> todos.filter { d -> d.medidores.all { it.estadoLectura == "LEIDO" } }
            "Sin acceso" -> todos.filter { d -> d.medidores.any { it.estadoLectura == "SIN_ACCESO" } }
            else         -> todos
        }
        if (consulta.isBlank()) porEstado else buscar(consulta, porEstado)
    }
    val pendientes = todos.count { d -> d.medidores.any { it.estadoLectura == "PENDIENTE" } }
    val mesAbierto = (estadoVm as? SectoresViewModel.Estado.Listo)?.config?.estadoMes == "ABIERTO"

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text(sector, color = Color.White, style = MaterialTheme.typography.titleMedium)
                        Text(
                            "${todos.size} conexiones · $pendientes pendientes",
                            color = Color.White.copy(alpha = 0.85f),
                            style = MaterialTheme.typography.bodySmall,
                        )
                    }
                },
                navigationIcon = {
                    IconButton(onClick = { nav.popBackStack() }) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, "Volver", tint = Color.White)
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = AzulPrimario),
                actions = {
                    Box(
                        Modifier.padding(end = 12.dp).size(10.dp).clip(CircleShape)
                            .background(if (conInternet) VerdeGuardar else GrisNeutro)
                    )
                }
            )
        },
        floatingActionButton = {
            if (mesAbierto && pendientes > 0) {
                ExtendedFloatingActionButton(
                    onClick = {
                        val sig = siguientePendiente(todos)
                        if (sig != null) {
                            val idx = sig.medidores.indexOfFirst { it.estadoLectura == "PENDIENTE" }.coerceAtLeast(0)
                            nav.navigate("lectura/$sector/${sig.idUsuario}/$idx")
                        }
                    },
                    containerColor = AmbarSiguiente,
                    contentColor   = TextoPrimario,
                    shape = RoundedCornerShape(28.dp),
                ) {
                    Text("Siguiente pendiente ›", style = MaterialTheme.typography.labelLarge)
                }
            }
        },
        containerColor = FondoGris,
    ) { padding ->
        Column(Modifier.fillMaxSize().padding(padding)) {
            OutlinedTextField(
                value = consulta, onValueChange = { consulta = it },
                placeholder = { Text("Buscar nombre, conexión o medidor", color = TextoSecundario) },
                modifier   = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 8.dp),
                singleLine = true,
                shape      = RoundedCornerShape(12.dp),
                colors     = OutlinedTextFieldDefaults.colors(
                    unfocusedContainerColor = SuperficieBlanca,
                    focusedContainerColor   = SuperficieBlanca,
                    unfocusedBorderColor    = GrisNeutro,
                ),
            )
            Row(
                Modifier.horizontalScroll(rememberScrollState()).padding(horizontal = 12.dp, vertical = 4.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                listOf("Todos", "Pendientes", "Leídos", "Sin acceso").forEach { chip ->
                    FilterChip(
                        selected = filtro == chip,
                        onClick  = { filtro = chip },
                        label    = { Text(chip) },
                        colors   = FilterChipDefaults.filterChipColors(
                            selectedContainerColor = AzulPrimario,
                            selectedLabelColor     = Color.White,
                        ),
                    )
                }
            }
            LazyColumn(
                Modifier.fillMaxSize(),
                contentPadding = PaddingValues(horizontal = 12.dp, vertical = 8.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                items(filtrados, key = { it.idUsuario }) { doc ->
                    TarjetaUsuario(doc) {
                        val idx = if (mesAbierto)
                            doc.medidores.indexOfFirst { it.estadoLectura == "PENDIENTE" }.let { if (it < 0) 0 else it }
                        else 0
                        nav.navigate("lectura/$sector/${doc.idUsuario}/$idx")
                    }
                }
            }
        }
    }
}

@Composable
fun TarjetaUsuario(doc: DocumentoMes, onClick: () -> Unit) {
    val m0        = doc.medidores.firstOrNull()
    val leido     = doc.medidores.all  { it.estadoLectura == "LEIDO" }
    val sinAcceso = doc.medidores.any  { it.estadoLectura == "SIN_ACCESO" }
    val estadoColor = when { leido -> VerdeGuardar; sinAcceso -> NaranjaAviso; else -> GrisNeutro }
    val estadoTexto = when { leido -> "Leído"; sinAcceso -> "Sin acceso"; else -> "Pendiente" }

    Card(
        modifier  = Modifier.fillMaxWidth().clickable(onClick = onClick),
        shape     = RoundedCornerShape(12.dp),
        colors    = CardDefaults.cardColors(containerColor = SuperficieBlanca),
        elevation = CardDefaults.cardElevation(2.dp),
    ) {
        Row(
            Modifier.fillMaxWidth().padding(14.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment     = Alignment.Top,
        ) {
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(doc.nombre, style = MaterialTheme.typography.bodyLarge, maxLines = 1, overflow = TextOverflow.Ellipsis)
                val medInfo = if (doc.medidores.size > 1)
                    "Conex. ${doc.nroConexion} · Med. ${m0?.nroMedidor ?: ""} +${doc.medidores.size - 1}"
                else "Conex. ${doc.nroConexion} · Med. ${m0?.nroMedidor ?: ""}"
                Text(medInfo, style = MaterialTheme.typography.bodySmall, color = TextoSecundario)
                Text(doc.direccion.ifBlank { "S/N" }, style = MaterialTheme.typography.bodySmall, color = TextoSecundario)
            }
            Spacer(Modifier.width(8.dp))
            Column(horizontalAlignment = Alignment.End, verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Surface(shape = RoundedCornerShape(20.dp), color = estadoColor.copy(alpha = 0.15f)) {
                    Text(estadoTexto, Modifier.padding(horizontal = 10.dp, vertical = 4.dp),
                        style = MaterialTheme.typography.bodySmall, color = estadoColor)
                }
                if (m0?.lecturaActual != null)
                    Text("${m0.lecturaAnterior} → ${m0.lecturaActual}",
                        style = MaterialTheme.typography.bodySmall, color = TextoSecundario)
            }
        }
    }
}

// ═════════════════════════════════════════════════════════════════════════════
// PANTALLA 4 — LECTURA
// ═════════════════════════════════════════════════════════════════════════════

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PantallaLectura(
    nav: NavHostController,
    authVm: AuthViewModel,
    sectoresVm: SectoresViewModel,
    sector: String,
    idUsuario: String,
    indiceMedidor: Int,
) {
    val estadoVm  by sectoresVm.estado.collectAsState()
    val lecturaVm: LecturaViewModel = viewModel()
    val resultado by lecturaVm.resultado.collectAsState()
    val guardando by lecturaVm.guardando.collectAsState()

    val config        = (estadoVm as? SectoresViewModel.Estado.Listo)?.config
    val periodo       = config?.periodo ?: ""
    val mesAbierto    = config?.estadoMes == "ABIERTO"
    val observaciones = config?.observaciones ?: OBSERVACIONES_FALLBACK
    val correo        = authVm.correoActual ?: "LECTOR"

    val doc = sectoresVm.docsCache[idUsuario]
    if (doc == null) {
        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { Text("Usuario no encontrado", color = RojoError) }
        return
    }
    val indice  = indiceMedidor.coerceIn(0, (doc.medidores.size - 1).coerceAtLeast(0))
    val medidor = doc.medidores.getOrNull(indice)
    if (medidor == null) {
        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { Text("Sin medidores", color = RojoError) }
        return
    }

    // Estado local editable
    var lecturaText by remember(indice, idUsuario) { mutableStateOf(medidor.lecturaActual?.toString() ?: "") }
    var novedad     by remember(indice, idUsuario) { mutableStateOf(medidor.novedad.ifBlank { "NORMAL" }) }
    var nota        by remember(indice, idUsuario) { mutableStateOf(medidor.nota) }
    var mostrarDialogoAtipico  by remember { mutableStateOf(false) }
    var accionPendiente: (() -> Unit)? by remember { mutableStateOf(null) }

    val lecturaLong  = lecturaText.toLongOrNull()
    val consumo      = if (lecturaLong != null) calcularConsumoDeMedidor(lecturaLong, medidor.lecturaAnterior, novedad) else null
    val consumoError = lecturaLong != null && consumo == null && novedad != "CAMBIO_MEDIDOR"

    // Al guardar con éxito → actualizar caché + navegar al siguiente pendiente
    LaunchedEffect(resultado) {
        if (resultado !is LecturaViewModel.Resultado.Guardado) return@LaunchedEffect
        lecturaVm.resetResultado()

        val nuevaLista = doc.medidores.toMutableList().apply {
            set(indice, medidor.copy(
                lecturaActual = lecturaLong, fechaLectura = fechaHoy(),
                estadoLectura = "LEIDO", novedad = novedad, nota = nota, registradoPor = correo,
            ))
        }
        sectoresVm.actualizarEnCache(doc.copy(medidores = nuevaLista, consumoTotalM3 = calcularConsumoTotal(nuevaLista)))

        val sigIndice = nuevaLista.indexOfFirst { it.estadoLectura == "PENDIENTE" }
        if (sigIndice >= 0) {
            nav.navigate("lectura/$sector/$idUsuario/$sigIndice") { popUpTo("lectura/$sector/$idUsuario/$indice") { inclusive = true } }
        } else {
            val sig = siguientePendiente(sectoresVm.docsDelSector(sector), idUsuario)
            if (sig != null) {
                val idx = sig.medidores.indexOfFirst { it.estadoLectura == "PENDIENTE" }.coerceAtLeast(0)
                nav.navigate("lectura/$sector/${sig.idUsuario}/$idx") { popUpTo("lectura/$sector/$idUsuario/$indice") { inclusive = true } }
            } else {
                nav.popBackStack()
            }
        }
    }

    fun doGuardar() {
        val la = lecturaLong ?: return
        val c  = calcularConsumoDeMedidor(la, medidor.lecturaAnterior, novedad) ?: return
        val guardarFn = {
            lecturaVm.guardarLectura(periodo, doc, medidor.copy(
                lecturaActual = la, fechaLectura = fechaHoy(),
                estadoLectura = "LEIDO", novedad = novedad, nota = nota,
            ), indice, correo)
        }
        if (esConsumoAtipico(c, doc.historialM3)) {
            accionPendiente = guardarFn; mostrarDialogoAtipico = true
        } else {
            guardarFn()
        }
    }

    if (mostrarDialogoAtipico) {
        AlertDialog(
            onDismissRequest = { mostrarDialogoAtipico = false },
            title = { Text("¿Es correcto?") },
            text  = { Text("El consumo registrado es muy alto o atípico. ¿Confirmas que la lectura es correcta?") },
            confirmButton = { TextButton(onClick = { mostrarDialogoAtipico = false; accionPendiente?.invoke(); accionPendiente = null }) { Text("Sí, es correcto") } },
            dismissButton = { TextButton(onClick = { mostrarDialogoAtipico = false; accionPendiente = null }) { Text("Revisar") } },
        )
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text(sector, color = Color.White, style = MaterialTheme.typography.titleMedium)
                        Text("Conex. ${doc.nroConexion} · Med. ${medidor.nroMedidor}",
                            color = Color.White.copy(alpha = 0.85f), style = MaterialTheme.typography.bodySmall)
                    }
                },
                navigationIcon = { IconButton(onClick = { nav.popBackStack() }) {
                    Icon(Icons.AutoMirrored.Filled.ArrowBack, "Volver", tint = Color.White)
                } },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = AzulPrimario),
            )
        },
        containerColor = FondoGris,
    ) { padding ->
        Column(
            Modifier.fillMaxSize().padding(padding).verticalScroll(rememberScrollState()).padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            // ── Tarjeta de usuario ──────────────────────────────────────────
            val chipColor = when (medidor.estadoLectura) { "LEIDO" -> VerdeGuardar; "SIN_ACCESO" -> NaranjaAviso; else -> GrisNeutro }
            Card(Modifier.fillMaxWidth(), shape = RoundedCornerShape(12.dp),
                colors = CardDefaults.cardColors(containerColor = SuperficieBlanca), elevation = CardDefaults.cardElevation(2.dp)) {
                Row(Modifier.fillMaxWidth().padding(14.dp), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.Top) {
                    Column(Modifier.weight(1f)) {
                        Text(doc.nombre, style = MaterialTheme.typography.bodyLarge)
                        Text(doc.direccion.ifBlank { "S/N" }, style = MaterialTheme.typography.bodySmall, color = TextoSecundario)
                        if (medidor.registradoPor.isNotBlank() && medidor.estadoLectura == "LEIDO") {
                            Spacer(Modifier.height(4.dp))
                            Text("Registrado por ${medidor.registradoPor}. Al guardar se reemplazará.",
                                color = NaranjaAviso, style = MaterialTheme.typography.bodySmall)
                        }
                    }
                    Surface(shape = RoundedCornerShape(20.dp), color = chipColor.copy(alpha = 0.15f)) {
                        Text(when (medidor.estadoLectura) { "LEIDO" -> "Leído"; "SIN_ACCESO" -> "Sin acceso"; else -> "Pendiente" },
                            Modifier.padding(horizontal = 10.dp, vertical = 4.dp),
                            style = MaterialTheme.typography.bodySmall, color = chipColor)
                    }
                }
            }

            // ── Selector de medidor (si hay varios) ────────────────────────
            if (doc.medidores.size > 1) {
                Text("Medidor", style = MaterialTheme.typography.bodySmall, color = TextoSecundario)
                Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    doc.medidores.forEachIndexed { idx, m ->
                        FilterChip(
                            selected = idx == indice,
                            onClick  = {
                                nav.navigate("lectura/$sector/$idUsuario/$idx") {
                                    popUpTo("lectura/$sector/$idUsuario/$indice") { inclusive = true }
                                }
                            },
                            label  = { Text("Med. ${m.nroMedidor}") },
                            colors = FilterChipDefaults.filterChipColors(selectedContainerColor = AzulPrimario, selectedLabelColor = Color.White),
                        )
                    }
                }
            }

            // ── Lecturas anterior / actual ──────────────────────────────────
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                // Anterior (solo lectura)
                Card(Modifier.weight(1f), shape = RoundedCornerShape(12.dp),
                    colors = CardDefaults.cardColors(containerColor = SuperficieBlanca), elevation = CardDefaults.cardElevation(2.dp)) {
                    Column(Modifier.padding(14.dp)) {
                        Text("LECTURA ANTERIOR", style = MaterialTheme.typography.bodySmall.copy(fontSize = 11.sp), color = TextoSecundario)
                        Text("${medidor.lecturaAnterior}", style = MaterialTheme.typography.displayMedium, color = TextoPrimario)
                        Text("Consumo anterior: ${medidor.consumoAnterior} m³", style = MaterialTheme.typography.bodySmall, color = TextoSecundario)
                    }
                }
                // Actual (editable si mes abierto)
                Card(Modifier.weight(1f), shape = RoundedCornerShape(12.dp),
                    colors = CardDefaults.cardColors(containerColor = SuperficieBlanca), elevation = CardDefaults.cardElevation(2.dp)) {
                    Column(Modifier.padding(14.dp)) {
                        Text("LECTURA ACTUAL",
                            style = MaterialTheme.typography.bodySmall.copy(fontSize = 11.sp),
                            color = if (mesAbierto) AzulPrimario else TextoSecundario)
                        if (mesAbierto) {
                            BasicTextField(
                                value = lecturaText,
                                onValueChange = { if (it.all { c -> c.isDigit() }) lecturaText = it },
                                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                                textStyle = MaterialTheme.typography.displayMedium.copy(color = AzulPrimario),
                                singleLine = true,
                                decorationBox = { inner ->
                                    Box(Modifier.defaultMinSize(minHeight = 56.dp)) {
                                        if (lecturaText.isEmpty()) Text("0", style = MaterialTheme.typography.displayMedium, color = GrisNeutro)
                                        inner()
                                    }
                                }
                            )
                        } else {
                            Text(medidor.lecturaActual?.toString() ?: "—", style = MaterialTheme.typography.displayMedium, color = TextoPrimario)
                        }
                    }
                }
            }

            if (consumoError)
                Text("La lectura actual es menor que la anterior. Si cambiaron el medidor, elige 'Cambio de medidor'.",
                    color = RojoError, style = MaterialTheme.typography.bodySmall)

            // Botón estimar
            if (mesAbierto) {
                OutlinedButton(
                    onClick = {
                        lecturaText = (medidor.lecturaAnterior + medidor.consumoAnterior).toString()
                        novedad     = "LECTURA_ESTIMADA"
                    },
                    modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(10.dp),
                    colors = ButtonDefaults.outlinedButtonColors(contentColor = AzulClaro),
                ) { Text("Estimar con consumo anterior") }
            }

            // ── Consumo calculado ───────────────────────────────────────────
            Card(Modifier.fillMaxWidth(), shape = RoundedCornerShape(12.dp),
                colors = CardDefaults.cardColors(containerColor = SuperficieBlanca), elevation = CardDefaults.cardElevation(0.dp)) {
                Column(Modifier.fillMaxWidth().padding(14.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                    Text("CONSUMO", style = MaterialTheme.typography.bodySmall.copy(fontSize = 11.sp), color = TextoSecundario)
                    Text(
                        if (consumo != null && consumo >= 0) "$consumo m³" else "—",
                        style = MaterialTheme.typography.displaySmall,
                        color = if (consumo != null && consumo >= 0) VerdeGuardar else GrisNeutro,
                    )
                }
            }

            // ── Observaciones (solo si mes abierto) ────────────────────────
            if (mesAbierto) {
                Text("Observación", style = MaterialTheme.typography.bodyMedium)
                Row(
                    Modifier.horizontalScroll(rememberScrollState()),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    observaciones.forEach { obs ->
                        FilterChip(
                            selected = novedad == obs.codigo,
                            onClick  = { novedad = obs.codigo },
                            label    = { Text(obs.texto) },
                            colors   = FilterChipDefaults.filterChipColors(
                                selectedContainerColor = AzulPrimario,
                                selectedLabelColor     = Color.White,
                            ),
                        )
                    }
                }

                // Nota libre
                OutlinedTextField(
                    value = nota, onValueChange = { nota = it },
                    placeholder = { Text("Nota libre (opcional)", color = TextoSecundario) },
                    modifier = Modifier.fillMaxWidth().height(90.dp),
                    shape = RoundedCornerShape(10.dp),
                )

                // Mensajes de estado
                when (val r = resultado) {
                    is LecturaViewModel.Resultado.Guardado ->
                        Text("✓ Guardado. Se enviará cuando haya internet.", color = VerdeGuardar)
                    is LecturaViewModel.Resultado.Error ->
                        Text(r.mensaje, color = RojoError, style = MaterialTheme.typography.bodySmall)
                    else -> {}
                }

                Spacer(Modifier.height(4.dp))

                // Botón Guardar
                Button(
                    onClick  = { doGuardar() },
                    enabled  = lecturaLong != null && !consumoError && !guardando,
                    modifier = Modifier.fillMaxWidth().height(54.dp),
                    shape    = RoundedCornerShape(10.dp),
                    colors   = ButtonDefaults.buttonColors(containerColor = VerdeGuardar),
                ) {
                    if (guardando)
                        CircularProgressIndicator(color = Color.White, modifier = Modifier.size(22.dp), strokeWidth = 2.dp)
                    else
                        Text("Guardar y siguiente pendiente", color = Color.White, style = MaterialTheme.typography.labelLarge)
                }

                // Botón Sin acceso
                OutlinedButton(
                    onClick = {
                        lecturaVm.guardarLectura(periodo, doc, medidor.copy(
                            lecturaActual = null, fechaLectura = fechaHoy(),
                            estadoLectura = "SIN_ACCESO", novedad = "CASA_CERRADA", nota = nota,
                        ), indice, correo)
                    },
                    modifier = Modifier.fillMaxWidth().height(52.dp),
                    shape    = RoundedCornerShape(10.dp),
                    colors   = ButtonDefaults.outlinedButtonColors(contentColor = AzulClaro),
                ) {
                    Text("Sin acceso / casa cerrada", style = MaterialTheme.typography.labelLarge)
                }
            }

            Spacer(Modifier.height(24.dp))
        }
    }
}
