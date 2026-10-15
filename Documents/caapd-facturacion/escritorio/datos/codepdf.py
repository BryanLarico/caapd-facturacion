from reportlab.pdfgen import canvas
from reportlab.lib.units import cm
from reportlab.lib import colors
from datetime import date
from datetime import datetime
from histograma import Histograma
from num2words import num2words
import qrcode

# variables a ser utilizadas
ahora = datetime.now()
meses = [
    "ENERO", "FEBRERO", "MARZO", "ABRIL",
    "MAYO", "JUNIO", "JULIO", "AGOSTO",
    "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"
]
Apellido1 = "ORE "
Apellido2 = "SOTO "
Nombres = "ANDRES RAUL"

ultimo_dia_pago = date(2026, 9, 20)
monto_a_pagar = 160.00
numero_recibo = 123456789
temporada = str(meses[ahora.month - 1]) + " " + str(ahora.year)
fecha_emision = ahora.strftime("%d-%m-%Y")
conexion = 123
nombre = Apellido1 + Apellido2 + Nombres
dni_ruc = 76469789
zona = "AYACUCHO"
direccion = "S/N"
categoria = "DOMESTICO"

# tabla 1
medidor = 6593681
lectura_anterior = 42.00
fecha1 = "07-07-2026"
fecha2 = "08-08-2026"
lectura_actual = 58.00
consumo = lectura_actual - lectura_anterior

# tabla 2
codigo_servicio = {
    "001": "SERVICIO DE AGUA",
    "008": "SERVICIO DE DESAGUE",
    "407": "CARGO FIJO"
}

descripcion_a_codigo = {
    valor: clave
    for clave, valor in codigo_servicio.items()
}
servicio_agua = consumo
servicio_desague = 0.00
cargo_fijo = 1.50
deuda_anterior = 0


def definicion_deuda(deuda_anterior):
    if deuda_anterior == 0:
        return "(SIN DEUDA)"
    else:
        return "(CON DEUDA)"


inafectos = deuda_anterior
afectos = servicio_agua + servicio_desague + cargo_fijo

# variables para el histograma
consumos_historicos = {
    "ABRIL": 12,
    "MAYO": 18,
    "JUNIO": 8,
    "JULIO": 15,
    "AGOSTO": 22,
    "SEPTIEMBRE": consumo
}

# variables para la parte de subtotal
subtotal = inafectos + afectos
hay_igv = False
igv = 18 / 100 * subtotal if hay_igv else 0
valor = subtotal + igv
redondeo = (valor*100 % 10)/100
total_a_pagar = subtotal + igv - redondeo
total_entero = int(total_a_pagar)
decimales = round((total_a_pagar - total_entero) * 100)

# variables para el pdf
ancho = 14.7 * cm
alto = 20.8 * cm

pdf = canvas.Canvas("boleta.pdf", pagesize=(ancho, alto))

# Fondo
pdf.drawImage(
    "fondo.png",
    0,
    0,
    width=ancho,
    height=alto
)

# Texto principal fijo
pdf.setFont("Helvetica", 12)
pdf.setFillColor(colors.black)
pdf.drawString(0.5 * cm, 17.2 * cm, "RESOLUCION 192-2017")  # listo

# texto 2 SUPERIOR
pdf.setFont("Helvetica", 9)
pdf.drawString(7 * cm, 17.45 * cm, "Ultimo día de pago:")  # listo
pdf.drawString(9.9 * cm, 17.45 * cm, ultimo_dia_pago.strftime("%d/%m/%Y"))
pdf.drawString(7 * cm, 17 * cm, "Monto a pagar: S/.")  # listo
pdf.drawString(9.9 * cm, 17 * cm, str(monto_a_pagar))

# texto 3
pdf.setFont("Helvetica", 7)
pdf.drawString(0.5 * cm, 16.4 * cm, "Recibo Nro: ")
pdf.drawString(1.9 * cm, 16.4 * cm, str(numero_recibo))

# texto 3 misma linea
pdf.setFont("Helvetica", 9)
pdf.drawString(7 * cm, 16.4 * cm, "Temporada:")
pdf.drawString(9.9 * cm, 16.4 * cm, temporada)

# texto 4
pdf.setFont("Helvetica", 11)
pdf.drawString(0.5 * cm, 15.9 * cm, "Fecha emisión:  " + str(fecha_emision))

# texto 5
pdf.setFont("Helvetica", 12)
pdf.drawString(9.6 * cm, 15.7*cm, "Conexión: " + "000000" + str(conexion))

# texto 6
pdf.setFont("Helvetica", 8)
pdf.drawString(0.5 * cm, 15.45 * cm, "Nombre: " + nombre)
pdf.drawString(0.5 * cm, 15.1 * cm, "DNI/RUC: " + str(dni_ruc))

# texto 7
pdf.setFont("Helvetica", 8)
pdf.drawString(0.5 * cm, 14.4 * cm, "Zona: " + zona)
pdf.drawString(0.5 * cm, 14 * cm, "Dirección: " + direccion)
pdf.drawString(8 * cm, 14.3 * cm, "Categoría: " + categoria)

# tabla1
pdf.setFont("Helvetica", 8)
pdf.drawString(0.8 * cm, 13.3 * cm, "Medidor")
pdf.drawString(0.8*cm, 13*cm, str(medidor))
pdf.drawString(2.8*cm, 13.3 * cm, "L. Anterior")
pdf.drawString(2.8*cm, 13*cm, f"{lectura_anterior:.2f}")
pdf.drawString(4.8 * cm, 13.3 * cm, "Fecha")
pdf.drawString(4.8*cm, 13*cm, fecha1)
pdf.drawString(6.8 * cm, 13.3 * cm, "L. Actual")
pdf.drawString(6.8*cm, 13*cm, f"{lectura_actual:.2f}")
pdf.drawString(8.8 * cm, 13.3 * cm, "Fecha")
pdf.drawString(8.8*cm, 13*cm, fecha2)
pdf.drawString(10.8 * cm, 13.3 * cm, "Consumo")
pdf.drawString(10.8*cm, 13*cm, f"{consumo:.2f}")

# texto 8
pdf.setFont("Helvetica", 8)
pdf.drawString(0.5 * cm, 12.6 * cm, "Periodo / Ciclo del " +
               fecha1 + "al " + fecha2)

# texto 9
pdf.setFont("Helvetica", 10)
pdf.drawString(0.6 * cm, 11.9 * cm, "DESCRIPCIÓN DE CONCEPTOS")
pdf.drawString(9 * cm, 11.9 * cm, "INAFECTOS")
pdf.drawString(12 * cm, 11.9 * cm, "AFECTOS")

# tabla 2
pdf.setFont("Helvetica", 8)
pdf.drawString(0.6 * cm, 11.5 * cm, descripcion_a_codigo["SERVICIO DE AGUA"])
pdf.drawString(1.6 * cm, 11.5 * cm, codigo_servicio["001"])
pdf.drawRightString(13.65 * cm, 11.5 * cm, f"{servicio_agua:.2f}")
pdf.drawString(0.6 * cm, 11.1 * cm,
               descripcion_a_codigo["SERVICIO DE DESAGUE"])
pdf.drawString(1.6 * cm, 11.1 * cm, codigo_servicio["008"])
pdf.drawRightString(13.65 * cm, 11.1 * cm, f"{servicio_desague:.2f}")
pdf.drawString(0.6 * cm, 10.7 * cm,
               descripcion_a_codigo["CARGO FIJO"])
pdf.drawString(1.6 * cm, 10.7 * cm, codigo_servicio["407"])
pdf.drawRightString(13.65 * cm, 10.7 * cm, f"{cargo_fijo:.2f}")
pdf.drawString(1.6*cm, 10.3*cm, "DEUDA ANTERIOR " +
               definicion_deuda(deuda_anterior))
pdf.drawString(9 * cm, 10.3 * cm, "S/." + f"{deuda_anterior:.2f}")

# histograma
Histograma.desde_dict(consumos_historicos).dibujar(
    pdf, x=0.6 * cm, y=5 * cm, ancho=6 * cm, alto=4 * cm
)

# texto10
pdf.setFont("Helvetica", 8)
pdf.drawString(9*cm, 7.8*cm, "Subtotal")
pdf.drawString(9*cm, 7.4*cm, "IGV")
pdf.drawString(9*cm, 7*cm, "Redondeo")
pdf.drawString(9*cm, 6.6*cm, "TOTAL MES")
pdf.drawRightString(13.65*cm, 7.8*cm, f"{subtotal:.2f}")
pdf.drawRightString(13.65*cm, 7.4*cm, f"{igv:.2f}")
pdf.drawRightString(13.65*cm, 7*cm, "-" + f"{redondeo:.2f}")
pdf.drawRightString(13.65*cm, 6.6*cm, f"{total_a_pagar:.2f}")

# texto11
pdf.setFont("Helvetica", 10)
pdf.drawString(9*cm, 5.9*cm, "TOTAL A PAGAR S/.")

# texto12
pdf.setFont("Helvetica", 10)
pdf.drawRightString(13.65*cm, 5.9*cm, f"{total_a_pagar:.2f}")

# texto13
pdf.setFont("Helvetica", 8)
pdf.drawString(0.5*cm, 4.7*cm, "Son: " +
               f"{num2words(total_entero, lang="es").upper()}" + " " + str(decimales) + " /100 SOLES")


# parte trozeada
pdf.setDash(5, 2)
pdf.line(0 * cm, 4.1 * cm, 14.7 * cm, 4.1 * cm)

# qr
datos = "https://api.whatsapp.com/send?phone=51983365260&text=Hola%20buenos%20dias%20quisiera%20mi%20boleta%20de%20agua"

qr = qrcode.QRCode(
    box_size=10,
    border=2
)

qr.add_data(datos)
qr.make(fit=True)

img = qr.make_image(
    fill_color="black",
    back_color="transparent"
).convert("RGBA")

img.save("qr.png")

pdf.drawImage(
    "qr.png",
    0.5 * cm,
    1.5 * cm,
    width=2 * cm,
    height=2 * cm,
    mask="auto"
)

# texto14
pdf.setFont("Helvetica", 8)
pdf.drawString(3*cm, 3*cm, "Conexión:")
pdf.drawString(4.3*cm, 3*cm, "000000" + f"{conexion}")
pdf.drawString(3*cm, 2.6*cm, "Nombre:")
pdf.drawString(4.3*cm, 2.6*cm, f"{nombre}")
pdf.drawString(0.7*cm, 1.2*cm, "Recibo Nro:")
pdf.drawString(2.4*cm, 1.2*cm, f"{numero_recibo}")
pdf.drawString(0.7*cm, 0.9*cm, "Emisión:")
pdf.drawString(2.4*cm, 0.9*cm, f"{fecha_emision}")
pdf.drawString(0.7*cm, 0.6*cm, "Vencimiento:")
pdf.drawString(2.4*cm, 0.6*cm, f"{ultimo_dia_pago.strftime("%d-%m-%Y")}")

# texto15
pdf.setFont("Helvetica", 12)
pdf.drawString(4.4*cm, 1.7*cm, "TOTAL A PAGAR S/.")
pdf.drawString(8.8*cm, 1.7*cm, f"{total_a_pagar:.2f}")

pdf.save()
