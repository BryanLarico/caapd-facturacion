"""
scripts/generar_plantilla_mes.py — Genera el archivo Excel modelo de plantilla para carga mensual.
"""
from pathlib import Path
import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

BASE_DIR = Path(__file__).resolve().parent.parent

def crear_plantilla():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Lecturas del Mes"

    # Encabezados
    headers = [
        "NRO_CONEXION",
        "DNI_ID",
        "NOMBRE",
        "SECTOR",
        "DIRECCION",
        "CATEGORIA",
        "NRO_MEDIDOR",
        "LECTURA_ANTERIOR",
        "LECTURA_ACTUAL",
        "NOVEDAD",
        "NOTA",
    ]

    fill_header = PatternFill(start_color="0369A1", end_color="0369A1", fill_type="solid")
    font_header = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    align_center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    align_left = Alignment(horizontal="left", vertical="center")
    align_right = Alignment(horizontal="right", vertical="center")

    thin_border = Border(
        left=Side(style="thin", color="CBD5E1"),
        right=Side(style="thin", color="CBD5E1"),
        top=Side(style="thin", color="CBD5E1"),
        bottom=Side(style="thin", color="CBD5E1"),
    )

    ws.append(headers)

    # Filas de ejemplo
    ejemplos = [
        [
            "000001",
            "70112233",
            "QUISPE MAMANI, JUAN CARLOS",
            "BARRIO DE CHAUPI",
            "CALLE 5 DE AGOSTO S/N",
            "A",
            "001001",
            120,
            135,
            "NORMAL",
            "Lectura conforme",
        ],
        [
            "000002",
            "70223344",
            "FLORES CHUQUIYANQUI, MARIA",
            "BARRIO DE PACHAYZA",
            "AV CENTRAL 120",
            "A",
            "002001",
            85,
            98,
            "NORMAL",
            "",
        ],
        [
            "000003",
            "70334455",
            "LOPEZ SERRANO, PEDRO",
            "BARRIO DE LUCMANI",
            "AUCAYPATA S/N",
            "A",
            "003001",
            450,
            450,
            "CASA_CERRADA",
            "Reja con candado",
        ],
        [
            "000004",
            "SD-001",
            "HUAMANI CONDORI, CARMEN (SIN DNI)",
            "HUAQUILLO",
            "SECTOR 2 S/N",
            "A",
            "004001",
            210,
            210,
            "MEDIDOR_DANADO",
            "Vidrio empañado",
        ],
        [
            "000005",
            "70556677",
            "MONTALVO ALVAREZ, LUIS (CAMBIO MEDIDOR)",
            "AYACUCHO",
            "CALLE UNION 45",
            "B",
            "005001",
            980,
            12,
            "CAMBIO_MEDIDOR",
            "Nuevo medidor instalado inicia en 0",
        ],
        [
            "000006",
            "70667788",
            "ZAMBRANO DIAZ, ROSA (MEDIDOR 1 DE 2)",
            "CHAUPICERCA",
            "MZ B LOTE 4",
            "A",
            "006001",
            40,
            52,
            "NORMAL",
            "Medidor principal casa",
        ],
        [
            "000006",
            "70667788",
            "ZAMBRANO DIAZ, ROSA (MEDIDOR 2 DE 2)",
            "CHAUPICERCA",
            "MZ B LOTE 4",
            "A",
            "006002",
            15,
            20,
            "NORMAL",
            "Medidor patio trasero",
        ],
    ]

    for fila in ejemplos:
        ws.append(fila)

    # Estilar encabezados
    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = fill_header
        cell.font = font_header
        cell.alignment = align_center
        cell.border = thin_border

    # Estilar datos
    fill_alt = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
    font_data = Font(name="Calibri", size=10)

    for row_idx in range(2, len(ejemplos) + 2):
        es_par = (row_idx % 2 == 0)
        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            cell.font = font_data
            cell.border = thin_border
            if es_par:
                cell.fill = fill_alt

            # Alineación
            if col_idx in (1, 2, 6, 7):
                cell.alignment = align_center
            elif col_idx in (8, 9):
                cell.alignment = align_right
            else:
                cell.alignment = align_left

    # Anchos de columna automáticos
    anchos = {
        1: 16, # NRO_CONEXION
        2: 14, # DNI_ID
        3: 38, # NOMBRE
        4: 24, # SECTOR
        5: 28, # DIRECCION
        6: 12, # CATEGORIA
        7: 16, # NRO_MEDIDOR
        8: 18, # LECTURA_ANTERIOR
        9: 16, # LECTURA_ACTUAL
        10: 20, # NOVEDAD
        11: 30, # NOTA
    }
    for col_idx, ancho in anchos.items():
        letra = get_column_letter(col_idx)
        ws.column_dimensions[letra].width = ancho

    ws.row_dimensions[1].height = 28

    # Hoja 2: Guía de Uso
    ws_guia = wb.create_sheet(title="Instrucciones")
    ws_guia.append(["GUÍA PARA IMPORTAR O LIMPIAR EXCEL DE MESES PASADOS"])
    ws_guia.append([""])
    ws_guia.append(["1. NRO_CONEXION: Código de 6 dígitos del usuario (ej. 000001). Si tiene menos, el sistema completará con ceros a la izquierda."])
    ws_guia.append(["2. DNI_ID: DNI de 8 dígitos. Si no tiene DNI, usar código provisional SD-001, SD-002, etc."])
    ws_guia.append(["3. NOMBRE: Apellidos y nombres completos en mayúsculas."])
    ws_guia.append(["4. SECTOR: Nombre del barrio o sector (ej. BARRIO DE CHAUPI, BARRIO DE PACHAYZA, etc.)."])
    ws_guia.append(["5. CATEGORIA: A (Doméstico), B (Comercial) o C (Estatal). Por defecto es A."])
    ws_guia.append(["6. NRO_MEDIDOR: Número del medidor (mínimo 6 dígitos). Si un usuario tiene 2 medidores, colocar 2 filas con el mismo usuario."])
    ws_guia.append(["7. LECTURA_ANTERIOR: Lectura en m³ con la que inició el mes."])
    ws_guia.append(["8. LECTURA_ACTUAL: Lectura en m³ registrada al final del mes."])
    ws_guia.append(["9. NOVEDAD: NORMAL, CAMBIO_MEDIDOR, MEDIDOR_DANADO, FUGA, CASA_CERRADA, LECTURA_ESTIMADA, OTRO."])
    ws_guia.append(["10. NOTA: Observaciones adicionales opcionales de la secretaria o del lector."])
    ws_guia.append([""])
    ws_guia.append(["HISTOGRAMA DE 6 MESES: Al subir los meses históricos pasados uno por uno (ej. 2026-05, 2026-06, etc.), el sistema encadenará los consumos automáticamente en el historial de cada usuario."])

    ws_guia.column_dimensions["A"].width = 110
    ws_guia.cell(row=1, column=1).font = Font(name="Calibri", size=14, bold=True, color="0369A1")

    destino = BASE_DIR / "datos" / "PLANTILLA_IMPORTAR_MES.xlsx"
    destino.parent.mkdir(parents=True, exist_ok=True)
    wb.save(destino)
    print(f"[OK] Plantilla generada con exito en: {destino}")

if __name__ == "__main__":
    crear_plantilla()
