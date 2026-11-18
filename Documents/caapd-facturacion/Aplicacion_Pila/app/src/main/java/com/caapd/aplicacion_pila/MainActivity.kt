package com.caapd.aplicacion_pila

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedCard
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.navigation.NavController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.caapd.aplicacion_pila.ui.theme.Aplicacion_PilaTheme

// 1. Modelo de Datos del Curso
data class Curso(
    val id: Int,
    val nombre: String,
    val profesor: String,
    val creditos: Int,
    val descripcion: String,
    val libros: String
)

// 2. Fuente de Datos con los 3 Cursos Reales
object CursoRepository {
    val listaCursos = listOf(
        Curso(
            id = 1,
            nombre = "Física Computacional",
            profesor = "Edwin Llamoca",
            creditos = 4,
            descripcion = "Simulación y modelado numérico de sistemas físicos complejos mediante algoritmos y métodos computacionales avanzados.",
            libros = "Física Computacional (Rubin H. Landau), Numerical Recipes (William H. Press)"
        ),
        Curso(
            id = 2,
            nombre = "Teoría de la Computación",
            profesor = "Leticia Oviedo",
            creditos = 3,
            descripcion = "Estudio de los modelos matemáticos de la computación, autómatas finitos, lenguajes formales y la teoría de la complejidad.",
            libros = "Introduction to the Theory of Computation (Michael Sipser), Automata Theory (Hopcroft & Ullman)"
        ),
        Curso(
            id = 3,
            nombre = "Diseño de Arquitectura de Software",
            profesor = "Percy Huertas",
            creditos = 4,
            descripcion = "Principios, patrones y estilos arquitectónicos para el diseño de sistemas de software robustos, escalables y mantenibles.",
            libros = "Clean Architecture (Robert C. Martin), Software Architecture in Practice (Len Bass)"
        )
    )

    fun obtenerCursoPorId(id: Int): Curso? {
        return listaCursos.find { it.id == id }
    }
}

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            Aplicacion_PilaTheme {
                Scaffold(modifier = Modifier.fillMaxSize()) { innerPadding ->
                    AppNavegacion(modifier = Modifier.padding(innerPadding))
                }
            }
        }
    }
}

@Composable
fun AppNavegacion(modifier: Modifier = Modifier) {
    val navController = rememberNavController()

    NavHost(
        navController = navController,
        startDestination = "inicio",
        modifier = modifier
    ) {
        // 1. Pantalla Inicio
        composable("inicio") {
            PantallaInicio(navController = navController)
        }

        // 2. Pantalla Cursos (Lista de tarjetas)
        composable("curso") {
            PantallaCurso(navController = navController)
        }

        // 3. Pantalla Detalle (Obtiene cursoId entero)
        composable(
            route = "detalle/{cursoId}",
            arguments = listOf(
                navArgument("cursoId") { type = NavType.IntType }
            )
        ) { backStackEntry ->
            val cursoId = backStackEntry.arguments?.getInt("cursoId") ?: 1
            val cursoEncontrado = CursoRepository.obtenerCursoPorId(cursoId)

            PantallaDetalle(
                navController = navController,
                curso = cursoEncontrado
            )
        }

        // 4. Pantalla Mensaje
        composable("mensaje") {
            PantallaMensaje(navController = navController)
        }
    }
}

// -----------------------------------------------------------------------------
// 1. PANTALLA INICIO
// -----------------------------------------------------------------------------
@Composable
fun PantallaInicio(navController: NavController) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        Text(
            text = "Inicio",
            fontSize = 32.sp,
            fontWeight = FontWeight.Bold,
            color = MaterialTheme.colorScheme.primary
        )

        Spacer(modifier = Modifier.height(24.dp))

        Button(onClick = { navController.navigate("curso") }) {
            Text("Ir a Cursos")
        }
    }
}

// -----------------------------------------------------------------------------
// 2. PANTALLA CURSO (Tarjetas para cada curso)
// -----------------------------------------------------------------------------
@Composable
fun PantallaCurso(navController: NavController) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        Text(
            text = "Cursos",
            fontSize = 32.sp,
            fontWeight = FontWeight.Bold,
            color = MaterialTheme.colorScheme.primary
        )

        // Cajas/Tarjetas interactiva para cada curso
        CursoRepository.listaCursos.forEach { curso ->
            OutlinedCard(
                onClick = {
                    navController.navigate("detalle/${curso.id}")
                },
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text(
                        text = curso.nombre,
                        fontSize = 20.sp,
                        fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.onSurface
                    )
                    Spacer(modifier = Modifier.height(4.dp))
                    Text(
                        text = "Profesor: ${curso.profesor}",
                        fontSize = 16.sp,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
        }

        Spacer(modifier = Modifier.height(8.dp))

        OutlinedButton(onClick = { navController.popBackStack() }) {
            Text("Volver")
        }
    }
}

// -----------------------------------------------------------------------------
// 3. PANTALLA DETALLE (Información completa)
// -----------------------------------------------------------------------------
@Composable
fun PantallaDetalle(
    navController: NavController,
    curso: Curso?
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        Text(
            text = "Detalle del Curso",
            fontSize = 32.sp,
            fontWeight = FontWeight.Bold,
            color = MaterialTheme.colorScheme.primary
        )

        if (curso != null) {
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)
            ) {
                Column(
                    modifier = Modifier.padding(20.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    Text(
                        text = curso.nombre,
                        fontSize = 22.sp,
                        fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.primary
                    )

                    Text(
                        text = "👨‍🏫 Profesor: ${curso.profesor}",
                        fontSize = 16.sp,
                        fontWeight = FontWeight.Medium
                    )

                    Text(
                        text = "🎓 Créditos: ${curso.creditos}",
                        fontSize = 16.sp,
                        fontWeight = FontWeight.Medium
                    )

                    HorizontalDivider()

                    Text(
                        text = "📝 Descripción:",
                        fontSize = 16.sp,
                        fontWeight = FontWeight.Bold
                    )
                    Text(
                        text = curso.descripcion,
                        fontSize = 15.sp,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )

                    Text(
                        text = "📚 Libros Recomendados:",
                        fontSize = 16.sp,
                        fontWeight = FontWeight.Bold
                    )
                    Text(
                        text = curso.libros,
                        fontSize = 15.sp,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
        } else {
            Text(text = "Curso no encontrado")
        }

        Button(onClick = { navController.navigate("mensaje") }) {
            Text("Ir a Mensaje")
        }

        OutlinedButton(onClick = { navController.popBackStack() }) {
            Text("Volver")
        }
    }
}

// -----------------------------------------------------------------------------
// 4. PANTALLA MENSAJE
// -----------------------------------------------------------------------------
@Composable
fun PantallaMensaje(navController: NavController) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        Text(
            text = "Mensaje",
            fontSize = 32.sp,
            fontWeight = FontWeight.Bold,
            color = MaterialTheme.colorScheme.primary
        )

        Spacer(modifier = Modifier.height(24.dp))

        Button(
            onClick = {
                navController.navigate("inicio") {
                    popUpTo("inicio") { inclusive = true }
                }
            }
        ) {
            Text("Ir a Inicio")
        }

        Spacer(modifier = Modifier.height(12.dp))

        OutlinedButton(onClick = { navController.popBackStack() }) {
            Text("Volver")
        }
    }
}
