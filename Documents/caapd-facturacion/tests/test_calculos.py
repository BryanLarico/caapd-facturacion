"""
tests/test_calculos.py — Pruebas pytest del módulo calculos.py.

Cubre:
  - Caso 1: medidor 42→58, sin deuda, sin IGV → total 17.50, AZUL
  - Caso 2: 2 medidores (42→61, 120→124), IGV 18%, recibo anterior
            sin pagar → total 47.40, NARANJA
  - Formatos: medidor, conexión, recibo, DNI, id_usuario
  - Número a letras
  - Nivel de mora
"""

import pytest
from calculos import (
    normalizar_medidor,
    normalizar_conexion,
    normalizar_recibo,
    normalizar_dni,
    generar_id_usuario,
    es_id_pendiente,
    calcular_monto_agua,
    calcular_recibo,
    calcular_nivel_mora,
    numero_a_letras,
    periodo_a_temporada,
    fecha_a_es,
)

# ---------------------------------------------------------------------------
# Config de prueba
# ---------------------------------------------------------------------------

CATEGORIA_A = {
    "nombre": "Doméstico",
    "tarifa_desague": 0.0,
    "cargo_fijo": 1.5,
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
        assert numero_a_letras(17.5) == "DIECISIETE 50/100 SOLES"


# ---------------------------------------------------------------------------
# CASO 2: dos medidores, IGV activo, recibo anterior sin pagar
# ---------------------------------------------------------------------------

class TestCaso2:
    """
    Medidor 1: 42→61 (+19), Medidor 2: 120→124 (+4) → consumo 23 m³
    IGV 18%, recibo anterior total=18.50 sin pagar (meses_adeudados=1).
    """

    def setup_method(self):
        self.medidores = [
            {"nro_medidor": "000100", "lectura_anterior": 42,  "lectura_actual": 61},
            {"nro_medidor": "003200", "lectura_anterior": 120, "lectura_actual": 124},
        ]
        recibo_anterior = {
            "total_a_pagar": 18.50,
            "monto_pagado": 0.0,
            "meses_adeudados": 1,
        }
        self.result = calcular_recibo(
            medidores=self.medidores,
            categoria=CATEGORIA_A,
            igv_activo=True,
            igv_porcentaje=0.18,
            recibo_anterior=recibo_anterior,
        )

    def test_consumo(self):
        assert self.result["consumo_total_m3"] == 23.0

    def test_monto_agua(self):
        assert self.result["monto_agua"] == 23.0

    def test_deuda_anterior(self):
        assert self.result["deuda_anterior"] == 18.5

    def test_igv(self):
        # subtotal_afecto = 23 + 0 + 1.50 = 24.50; IGV = 24.50 * 0.18 = 4.41
        assert self.result["igv"] == 4.41

    def test_redondeo(self):
        # total_antes = 24.50 + 18.50 + 4.41 = 47.41 → redondeo = 0.01
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
        assert numero_a_letras(47.40) == "CUARENTA Y SIETE 40/100 SOLES"


# ---------------------------------------------------------------------------
# Casos de formato
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


# ---------------------------------------------------------------------------
# ID de usuario
# ---------------------------------------------------------------------------

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
# Nivel de mora
# ---------------------------------------------------------------------------

class TestNivelMora:
    def test_azul(self):
        n = calcular_nivel_mora(1, 0, 17.50, CONFIG_MORA)
        assert n["nombre"] == "AZUL"
        assert n["corte"] is False

    def test_naranja(self):
        n = calcular_nivel_mora(2, 0, 47.40, CONFIG_MORA)
        assert n["nombre"] == "NARANJA"
        assert n["corte"] is False

    def test_rojo(self):
        n = calcular_nivel_mora(3, 0, 30.00, CONFIG_MORA)
        assert n["nombre"] == "ROJO"
        assert n["corte"] is True

    def test_rojo_4_meses(self):
        n = calcular_nivel_mora(4, 0, 30.00, CONFIG_MORA)
        assert n["nombre"] == "ROJO"

    def test_pagado(self):
        n = calcular_nivel_mora(2, 47.40, 47.40, CONFIG_MORA)
        assert n["nombre"] == "PAGADO"
        assert n["corte"] is False


# ---------------------------------------------------------------------------
# Número a letras
# ---------------------------------------------------------------------------

class TestNumeroALetras:
    def test_17_50(self):
        assert numero_a_letras(17.50) == "DIECISIETE 50/100 SOLES"

    def test_47_40(self):
        assert numero_a_letras(47.40) == "CUARENTA Y SIETE 40/100 SOLES"

    def test_23_50(self):
        assert numero_a_letras(23.50) == "VEINTITRÉS 50/100 SOLES"

    def test_1_00(self):
        assert numero_a_letras(1.0) == "UNO 00/100 SOLES"

    def test_cero(self):
        assert numero_a_letras(0.0) == "CERO 00/100 SOLES"

    def test_100(self):
        assert numero_a_letras(100.0) == "CIEN 00/100 SOLES"

    def test_1000(self):
        assert numero_a_letras(1000.0) == "MIL 00/100 SOLES"


# ---------------------------------------------------------------------------
# Utilidades de fecha
# ---------------------------------------------------------------------------

class TestFechas:
    def test_periodo_a_temporada(self):
        assert periodo_a_temporada("2026-08") == "AGOSTO 2026"

    def test_periodo_a_temporada_sep(self):
        assert periodo_a_temporada("2026-09") == "SEPTIEMBRE 2026"

    def test_fecha_a_es(self):
        assert fecha_a_es("2026-08-08") == "08-08-2026"

    def test_fecha_vacia(self):
        assert fecha_a_es("") == ""


# ---------------------------------------------------------------------------
# Calcular monto agua con rangos
# ---------------------------------------------------------------------------

class TestCalcularMontoAgua:
    def test_rango_unico(self):
        rangos = [{"m3_desde": 0, "m3_hasta": None, "precio_m3": 1.0}]
        assert calcular_monto_agua(16, rangos) == 16.0

    def test_rango_precio_unico_no_tramos(self):
        # 25 m³ cae en el segundo rango → todo a 1.50
        rangos = [
            {"m3_desde": 0,  "m3_hasta": 10, "precio_m3": 1.0},
            {"m3_desde": 11, "m3_hasta": None, "precio_m3": 1.5},
        ]
        assert calcular_monto_agua(25, rangos) == 37.5

    def test_consumo_cero(self):
        rangos = [{"m3_desde": 0, "m3_hasta": None, "precio_m3": 1.0}]
        assert calcular_monto_agua(0, rangos) == 0.0

    def test_sin_rangos(self):
        assert calcular_monto_agua(10, []) == 0.0


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
        assert calcular_monto_agua(10.5, self.rangos) == 15.75
        res = calcular_recibo(
            medidores=[{"nro_medidor": "0001", "lectura_anterior": 0, "lectura_actual": 10.5}],
            categoria=self.categoria,
            igv_activo=False,
            igv_porcentaje=0.18,
            recibo_anterior=None,
        )
        assert res["monto_agua"] == 15.75
