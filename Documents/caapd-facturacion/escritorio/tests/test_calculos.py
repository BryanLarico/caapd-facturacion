"""
tests/test_calculos.py — Pruebas pytest del módulo calculos.py (Fase 1D).

Cubre:
  - Caso 1 y Caso 2 históricos de facturación
  - Función pura consumo_medidor (normal, CAMBIO_MEDIDOR, error si menor)
  - modo_rangos ("unico" y "tramos")
  - Los 10 casos obligatorios de numero_a_letras y redondeo de centavos
  - calcular_nivel_mora (color None si pagado)
  - Formatos e identificadores reexportados desde calculos
  - Fechas y temporadas
  - Tarifas por defecto en Rango Único (Etapa 1.3)
"""

import pytest
from calculos import (
    consumo_medidor,
    calcular_monto_agua,
    calcular_recibo,
    calcular_nivel_mora,
    numero_a_letras,
    periodo_a_temporada,
    fecha_a_es,
    normalizar_medidor,
    normalizar_conexion,
    normalizar_recibo,
    normalizar_dni,
    generar_id_usuario,
    es_id_pendiente,
)

# ---------------------------------------------------------------------------
# Config de prueba
# ---------------------------------------------------------------------------

CATEGORIA_A = {
    "nombre": "Doméstico",
    "tarifa_desague": 0.0,
    "cargo_fijo": 1.5,
    "modo_rangos": "unico",
    "rangos": [
        {"m3_desde": 0, "m3_hasta": None, "precio_m3": 1.0}
    ],
}

CONFIG_MORA = [
    {"meses_min": 1, "nombre": "AZUL",    "color": "#1E88E5", "corte": False},
    {"meses_min": 2, "nombre": "NARANJA", "color": "#FB8C00", "corte": False},
    {"meses_min": 3, "nombre": "ROJO",    "color": "#E53935", "corte": True},
]


# ---------------------------------------------------------------------------
# CASO 1: un medidor, sin deuda, IGV apagado
# ---------------------------------------------------------------------------

class TestCaso1:
    """Medidor 42→58, precio 1.00, desagüe 0, cargo fijo 1.50, sin deuda, sin IGV."""

    def setup_method(self):
        self.medidores = [
            {"nro_medidor": "000100", "lectura_anterior": 42, "lectura_actual": 58}
        ]
        self.result = calcular_recibo(
            medidores=self.medidores,
            categoria=CATEGORIA_A,
            igv_activo=False,
            igv_porcentaje=0.18,
            recibo_anterior=None,
        )

    def test_consumo(self):
        assert self.result["consumo_total_m3"] == 16.0

    def test_monto_agua(self):
        assert self.result["monto_agua"] == 16.0

    def test_cargo_fijo(self):
        assert self.result["cargo_fijo"] == 1.5

    def test_deuda_anterior(self):
        assert self.result["deuda_anterior"] == 0.0

    def test_igv_cero(self):
        assert self.result["igv"] == 0.0

    def test_redondeo_cero(self):
        # 16.00 + 1.50 = 17.50 → múltiplo exacto de 0.10 → redondeo = 0
        assert self.result["redondeo"] == 0.0

    def test_total(self):
        assert self.result["total_a_pagar"] == 17.5

    def test_meses_adeudados(self):
        assert self.result["meses_adeudados"] == 1

    def test_nivel_mora(self):
        nivel = calcular_nivel_mora(
            self.result["meses_adeudados"],
            self.result["monto_pagado"],
            self.result["total_a_pagar"],
            CONFIG_MORA,
        )
        assert nivel["nombre"] == "AZUL"

    def test_numero_a_letras(self):
        assert numero_a_letras(self.result["total_a_pagar"]) == "DIECISIETE 50/100 SOLES"


# ---------------------------------------------------------------------------
# CASO 2: 2 medidores, con IGV, con deuda anterior
# ---------------------------------------------------------------------------

class TestCaso2:
    """Medidores 42→61 y 120→124, IGV 18%, recibo anterior 18.50 sin pagar con 1 mes."""

    def setup_method(self):
        self.medidores = [
            {"nro_medidor": "000100", "lectura_anterior": 42, "lectura_actual": 61},
            {"nro_medidor": "003200", "lectura_anterior": 120, "lectura_actual": 124},
        ]
        self.recibo_anterior = {
            "total_a_pagar": 18.50,
            "monto_pagado": 0.0,
            "meses_adeudados": 1,
        }
        self.result = calcular_recibo(
            medidores=self.medidores,
            categoria=CATEGORIA_A,
            igv_activo=True,
            igv_porcentaje=0.18,
            recibo_anterior=self.recibo_anterior,
        )

    def test_consumo(self):
        # (61 - 42) + (124 - 120) = 19 + 4 = 23
        assert self.result["consumo_total_m3"] == 23.0

    def test_monto_agua(self):
        assert self.result["monto_agua"] == 23.0

    def test_igv(self):
        # agua 23.00 + desagüe 0.00 + cargo fijo 1.50 = 24.50
        # igv = round(24.50 * 0.18, 2) = round(4.41, 2) = 4.41
        assert self.result["igv"] == 4.41

    def test_deuda_anterior(self):
        assert self.result["deuda_anterior"] == 18.50

    def test_redondeo(self):
        # total_antes = 24.50 (subtotal) + 18.50 (deuda) + 4.41 (igv) = 47.41
        # redondeo = 0.01 → total = 47.40
        assert self.result["redondeo"] == 0.01

    def test_total(self):
        assert self.result["total_a_pagar"] == 47.40

    def test_meses_adeudados(self):
        assert self.result["meses_adeudados"] == 2

    def test_nivel_mora(self):
        nivel = calcular_nivel_mora(
            self.result["meses_adeudados"],
            self.result["monto_pagado"],
            self.result["total_a_pagar"],
            CONFIG_MORA,
        )
        assert nivel["nombre"] == "NARANJA"

    def test_numero_a_letras(self):
        assert numero_a_letras(self.result["total_a_pagar"]) == "CUARENTA Y SIETE 40/100 SOLES"


# ---------------------------------------------------------------------------
# Validaciones de cálculo de recibo
# ---------------------------------------------------------------------------

class TestValidacionesRecibo:
    def test_medidor_sin_lectura_actual_lanza_error(self):
        with pytest.raises(ValueError) as excinfo:
            calcular_recibo(
                medidores=[{"nro_medidor": "000100", "lectura_anterior": 42, "lectura_actual": None}],
                categoria=CATEGORIA_A,
                igv_activo=False,
                igv_porcentaje=0.18,
                recibo_anterior=None,
            )
        assert "sin lectura_actual" in str(excinfo.value)

    def test_recibo_anterior_pagado_reinicia_meses_a_uno(self):
        recibo_anterior = {
            "total_a_pagar": 30.00,
            "monto_pagado": 30.00,
            "meses_adeudados": 3,
        }
        res = calcular_recibo(
            medidores=[{"nro_medidor": "000100", "lectura_anterior": 0, "lectura_actual": 10}],
            categoria=CATEGORIA_A,
            igv_activo=False,
            igv_porcentaje=0.18,
            recibo_anterior=recibo_anterior,
        )
        assert res["deuda_anterior"] == 0.0
        assert res["meses_adeudados"] == 1


# ---------------------------------------------------------------------------
# Consumo de un medidor (Función pura)
# ---------------------------------------------------------------------------

class TestConsumoMedidor:
    def test_consumo_normal(self):
        assert consumo_medidor(42, 58) == 16.0
        assert consumo_medidor(100, 100) == 0.0

    def test_consumo_con_cambio_medidor(self):
        # El medidor nuevo empieza en 0, consumo = actual
        assert consumo_medidor(950, 12, novedad="CAMBIO_MEDIDOR") == 12.0
        assert consumo_medidor(150, 0, novedad="CAMBIO_MEDIDOR") == 0.0

    def test_consumo_negativo_sin_cambio_medidor_lanza_error(self):
        with pytest.raises(ValueError) as excinfo:
            consumo_medidor(950, 12, novedad=None)
        assert "menor a la anterior" in str(excinfo.value)

        with pytest.raises(ValueError):
            consumo_medidor(100, 95, novedad="MEDIDOR_DANADO")


# ---------------------------------------------------------------------------
# Modo de rangos ("unico" y "tramos")
# ---------------------------------------------------------------------------

class TestModoRangos:
    def setup_method(self):
        # Rangos: 0–10 a 1.00 y 10 en adelante a 1.50
        self.rangos = [
            {"m3_desde": 0, "m3_hasta": 10, "precio_m3": 1.00},
            {"m3_desde": 10, "m3_hasta": None, "precio_m3": 1.50},
        ]

    def test_caso_obligatorio_tramos_vs_unico(self):
        # Consumo 16 m3:
        # En 'tramos': 10 m3 a 1.00 + 6 m3 a 1.50 = 10.00 + 9.00 = 19.00
        assert calcular_monto_agua(16, self.rangos, modo_rangos="tramos") == 19.00

        # En 'unico': todo a 1.50 = 16 * 1.50 = 24.00
        assert calcular_monto_agua(16, self.rangos, modo_rangos="unico") == 24.00

    def test_recibo_con_categoria_tramos(self):
        cat_tramos = {
            "nombre": "Doméstico Tramos",
            "tarifa_desague": 0.0,
            "cargo_fijo": 0.0,
            "modo_rangos": "tramos",
            "rangos": self.rangos,
        }
        res = calcular_recibo(
            medidores=[{"nro_medidor": "000100", "lectura_anterior": 0, "lectura_actual": 16}],
            categoria=cat_tramos,
            igv_activo=False,
            igv_porcentaje=0.18,
            recibo_anterior=None,
        )
        assert res["monto_agua"] == 19.00
        assert res["total_a_pagar"] == 19.00

    def test_consumo_cero(self):
        assert calcular_monto_agua(0, self.rangos) == 0.0

    def test_sin_rangos(self):
        assert calcular_monto_agua(10, []) == 0.0


# ---------------------------------------------------------------------------
# Nivel de mora
# ---------------------------------------------------------------------------

class TestNivelMora:
    def test_azul(self):
        n = calcular_nivel_mora(1, 0, 17.50, CONFIG_MORA)
        assert n["nombre"] == "AZUL"
        assert n["color"] == "#1E88E5"
        assert n["corte"] is False

    def test_naranja(self):
        n = calcular_nivel_mora(2, 0, 47.40, CONFIG_MORA)
        assert n["nombre"] == "NARANJA"
        assert n["color"] == "#FB8C00"
        assert n["corte"] is False

    def test_rojo(self):
        n = calcular_nivel_mora(3, 0, 30.00, CONFIG_MORA)
        assert n["nombre"] == "ROJO"
        assert n["color"] == "#E53935"
        assert n["corte"] is True

    def test_rojo_4_meses(self):
        n = calcular_nivel_mora(4, 0, 30.00, CONFIG_MORA)
        assert n["nombre"] == "ROJO"
        assert n["color"] == "#E53935"
        assert n["corte"] is True

    def test_pagado_devuelve_color_none(self):
        # CONTEXTO y FASE_1D: pagado debe devolver color None para usar el color base de la interfaz
        n = calcular_nivel_mora(2, 47.40, 47.40, CONFIG_MORA)
        assert n["nombre"] == "PAGADO"
        assert n["color"] is None
        assert n["corte"] is False


# ---------------------------------------------------------------------------
# Número a letras (10 casos obligatorios de FASE_1D)
# ---------------------------------------------------------------------------

class TestNumeroALetrasObligatorios:
    def test_17_50(self):
        assert numero_a_letras(17.50) == "DIECISIETE 50/100 SOLES"

    def test_21_00(self):
        assert numero_a_letras(21.00) == "VEINTIUNO 00/100 SOLES"

    def test_31_00(self):
        assert numero_a_letras(31.00) == "TREINTA Y UNO 00/100 SOLES"

    def test_100_00(self):
        assert numero_a_letras(100.00) == "CIEN 00/100 SOLES"

    def test_101_00(self):
        assert numero_a_letras(101.00) == "CIENTO UNO 00/100 SOLES"

    def test_1001_00(self):
        assert numero_a_letras(1001.00) == "MIL UNO 00/100 SOLES"

    def test_21000_00(self):
        assert numero_a_letras(21000.00) == "VEINTIÚN MIL 00/100 SOLES"

    def test_2000_00(self):
        assert numero_a_letras(2000.00) == "DOS MIL 00/100 SOLES"

    def test_0_50(self):
        assert numero_a_letras(0.50) == "CERO 50/100 SOLES"

    def test_1234_00(self):
        assert numero_a_letras(1234.00) == "MIL DOSCIENTOS TREINTA Y CUATRO 00/100 SOLES"

    def test_redondeo_centavos_seguro(self):
        # 2.999 no debe dar "100/100" sino redondearse a 3.00
        assert numero_a_letras(2.999) == "TRES 00/100 SOLES"

    def test_monto_negativo(self):
        assert numero_a_letras(-15.50) == "MENOS QUINCE 50/100 SOLES"


# ---------------------------------------------------------------------------
# Utilidades de fecha
# ---------------------------------------------------------------------------

class TestFechas:
    def test_periodo_a_temporada(self):
        assert periodo_a_temporada("2026-08") == "AGOSTO 2026"
        assert periodo_a_temporada("2026-09") == "SEPTIEMBRE 2026"

    def test_fecha_a_es(self):
        assert fecha_a_es("2026-08-08") == "08-08-2026"
        assert fecha_a_es("") == ""


# ---------------------------------------------------------------------------
# Formatos e identificadores (reexportados desde calculos)
# ---------------------------------------------------------------------------

class TestFormatos:
    """Pruebas de normalización de códigos según la hoja Calculo_ejemplo."""

    def test_medidor_100(self):
        assert normalizar_medidor(100) == "000100"

    def test_medidor_3200(self):
        assert normalizar_medidor(3200) == "003200"

    def test_medidor_990991(self):
        assert normalizar_medidor(990991) == "990991"

    def test_medidor_22392996(self):
        assert normalizar_medidor(22392996) == "22392996"

    def test_medidor_string(self):
        assert normalizar_medidor("100") == "000100"

    def test_dni_7_digitos(self):
        assert normalizar_dni(7654321) == "07654321"

    def test_dni_8_digitos(self):
        assert normalizar_dni(76807817) == "76807817"

    def test_conexion_796(self):
        assert normalizar_conexion(796) == "000796"

    def test_recibo_58391(self):
        assert normalizar_recibo(58391) == "000058391"


class TestIdUsuario:
    """Pruebas de generación y detección de id_usuario."""

    def test_dni_8_digitos_unico(self):
        assert generar_id_usuario(76807817) == "76807817"

    def test_dni_7_digitos_unico(self):
        assert generar_id_usuario(7654321) == "07654321"

    def test_dni_compartido_1(self):
        assert generar_id_usuario(12345678, sufijo=1) == "12345678-1"

    def test_dni_compartido_2(self):
        assert generar_id_usuario(12345678, sufijo=2) == "12345678-2"

    def test_sin_dni_001(self):
        assert generar_id_usuario(None, contador_sin_dni=1) == "SD-001"

    def test_sin_dni_025(self):
        assert generar_id_usuario(None, contador_sin_dni=25) == "SD-025"

    def test_id_pendiente_guion(self):
        assert es_id_pendiente("12345678-1") is True

    def test_id_pendiente_sd(self):
        assert es_id_pendiente("SD-001") is True

    def test_id_no_pendiente(self):
        assert es_id_pendiente("76807817") is False


# ---------------------------------------------------------------------------
# Tarifas por defecto - Rango Único (Etapa 1.3)
# ---------------------------------------------------------------------------

class TestTarifasRangoUnicoDefecto:
    """Pruebas obligatorias de Etapa 1.3:
    - Método: RANGO ÚNICO
    - Cargo fijo mensual S/ 5.00, Tarifa de desagüe 0.00, IGV False
    - Rangos: 1–10 m³ a S/ 1.00; 11–15 a S/ 1.50; 16 en adelante a S/ 4.00
    - Casos: 0 → 5.00; 10 → 15.00; 12 → 23.00; 15 → 27.50; 16 → 69.00; 17 → 73.00
    - Decimales sin huecos: 10.5 m³ cae en rango 11–15
    """
    def setup_method(self):
        self.rangos = [
            {"m3_desde": 1, "m3_hasta": 10, "precio_m3": 1.00},
            {"m3_desde": 11, "m3_hasta": 15, "precio_m3": 1.50},
            {"m3_desde": 16, "m3_hasta": None, "precio_m3": 4.00},
        ]
        self.categoria = {
            "nombre": "Doméstico",
            "cargo_fijo": 5.00,
            "tarifa_desague": 0.00,
            "modo_rangos": "unico",
            "rangos": self.rangos,
        }

    @pytest.mark.parametrize("consumo,total_esperado", [
        (0, 5.00),
        (10, 15.00),
        (12, 23.00),
        (15, 27.50),
        (16, 69.00),
        (17, 73.00),
    ])
    def test_casos_etapa1(self, consumo, total_esperado):
        res = calcular_recibo(
            medidores=[{"nro_medidor": "0001", "lectura_anterior": 0, "lectura_actual": consumo}],
            categoria=self.categoria,
            igv_activo=False,
            igv_porcentaje=0.18,
            recibo_anterior=None,
        )
        assert res["total_a_pagar"] == total_esperado

    def test_decimal_sin_huecos_10_5(self):
        # 10.5 m³ debe caer en rango 11-15 (precio 1.50)
        assert calcular_monto_agua(10.5, self.rangos, modo_rangos="unico") == 15.75
        res = calcular_recibo(
            medidores=[{"nro_medidor": "0001", "lectura_anterior": 0, "lectura_actual": 10.5}],
            categoria=self.categoria,
            igv_activo=False,
            igv_porcentaje=0.18,
            recibo_anterior=None,
        )
        # 5.00 + 15.75 = 20.75, redondeo a 0.05 -> 20.70
        assert res["monto_agua"] == 15.75
        assert res["redondeo"] == 0.05
        assert res["total_a_pagar"] == 20.70
