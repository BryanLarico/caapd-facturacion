package com.caapd.lecturas.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.material3.Typography
import androidx.compose.runtime.Composable
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

// ─── Esquema de color fijo (sin dynamic color ni dark theme para uso exterior) ───
private val EsquemaCAAPD = lightColorScheme(
    primary          = AzulPrimario,
    onPrimary        = SuperficieBlanca,
    primaryContainer = AzulClaro,
    secondary        = VerdeGuardar,
    onSecondary      = SuperficieBlanca,
    tertiary         = AmbarSiguiente,
    background       = FondoGris,
    surface          = SuperficieBlanca,
    onBackground     = TextoPrimario,
    onSurface        = TextoPrimario,
    error            = RojoError,
    onError          = SuperficieBlanca,
)

// ─── Tipografía: letras y botones grandes (uso al aire libre) ───
val TipografiaCAAPD = Typography(
    // Títulos de pantalla (nombre del sector en la barra)
    titleLarge = TextStyle(
        fontWeight = FontWeight.Bold,
        fontSize   = 20.sp,
        lineHeight = 26.sp,
    ),
    titleMedium = TextStyle(
        fontWeight = FontWeight.SemiBold,
        fontSize   = 17.sp,
    ),
    // Nombre del usuario en la tarjeta
    bodyLarge = TextStyle(
        fontWeight = FontWeight.Bold,
        fontSize   = 16.sp,
        lineHeight = 22.sp,
    ),
    bodyMedium = TextStyle(
        fontWeight = FontWeight.Normal,
        fontSize   = 14.sp,
    ),
    bodySmall = TextStyle(
        fontWeight = FontWeight.Normal,
        fontSize   = 13.sp,
    ),
    // Números grandes (lectura anterior / actual)
    displayMedium = TextStyle(
        fontWeight = FontWeight.Bold,
        fontSize   = 48.sp,
    ),
    // Consumo m³
    displaySmall = TextStyle(
        fontWeight = FontWeight.Bold,
        fontSize   = 34.sp,
    ),
    // Botones
    labelLarge = TextStyle(
        fontWeight = FontWeight.SemiBold,
        fontSize   = 16.sp,
    ),
)

// ─── Tema principal (siempre claro: mejor legibilidad al aire libre) ───
@Composable
fun LecturasCAAPDTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = EsquemaCAAPD,
        typography  = TipografiaCAAPD,
        content     = content,
    )
}