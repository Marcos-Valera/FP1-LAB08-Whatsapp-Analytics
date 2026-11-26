import re
from datetime import datetime
from whatsapp_utiles import Mensaje

# Marcas invisibles que WhatsApp añade a veces al principio de línea o del texto
# (BOM y marcas de dirección de texto en los adjuntos de iOS, p. ej. "‎imagen omitida").
MARCAS_INVISIBLES = '﻿‎‏'

# Patrón Regex Explicado:
# 1. ^\[?                  -> Puede empezar con corchete (iOS)
# 2. (\d{1,4}[/-]\d{1,2}[/-]\d{1,4}) -> Grupo 1: La Fecha (acepta / o -)
# 3. [,\s]+                -> Separador fecha-hora (coma o espacio)
# 4. (\d{1,2}:\d{2}(?::\d{2})?(?:\s?[apAP]\.?\s?[mM]\.?)?) -> Grupo 2: La Hora
#                             (HH:MM, segundos opcionales, AM/PM opcional, también "p. m.")
# 5. \]?:?[\s-]*           -> Cierre corchete opcional, dos puntos opcionales, guión opcional
# 6. (.*?):                -> Grupo 3: Usuario (captura todo hasta los dos puntos del mensaje)
# 7. \s(.*)$               -> Grupo 4: El texto del mensaje
PATRON_FECHA_HORA = (
    r'^\[?(\d{1,4}[/-]\d{1,2}[/-]\d{1,4})[,\s]+'
    r'(\d{1,2}:\d{2}(?::\d{2})?(?:\s?[apAP]\.?\s?[mM]\.?)?)\]?:?[\s-]*'
)
PATRON_MENSAJE = re.compile(PATRON_FECHA_HORA + r'(.*?):\s(.*)$')
PATRON_CABECERA = re.compile(PATRON_FECHA_HORA)


def leer_log_whatsapp(ruta_archivo: str) -> list[Mensaje]:
    """
    Lee un archivo de log de WhatsApp y devuelve una lista de objetos Mensaje.
    Soporta formatos típicos de Android e iOS. Los mensajes que ocupan varias
    líneas se unen en un único Mensaje (con saltos de línea en el texto).
    """
    mensajes = []

    try:
        # utf-8-sig descarta el BOM inicial si lo hay
        with open(ruta_archivo, 'r', encoding='utf-8-sig') as f:
            lineas = f.readlines()
    except FileNotFoundError:
        print(f"Error: No se encontró el archivo en {ruta_archivo}")
        return []

    # Indica si la última línea leída pertenece a un mensaje válido, para saber
    # si una línea sin fecha es la continuación de ese mensaje.
    continua_mensaje = False

    for linea in lineas:
        linea = linea.strip().lstrip(MARCAS_INVISIBLES).strip()
        if not linea:
            continue

        match = PATRON_MENSAJE.match(linea)
        if match:
            fecha_str, hora_str, usuario, texto = match.groups()
            fecha_obj, hora_obj = _convertir_fechahora(fecha_str, hora_str)

            if fecha_obj and hora_obj and len(usuario) <= 50:
                texto = texto.lstrip(MARCAS_INVISIBLES)
                mensajes.append(Mensaje(fecha_obj, hora_obj, usuario, texto))
                continua_mensaje = True
            else:
                continua_mensaje = False
        elif PATRON_CABECERA.match(linea):
            # Línea con fecha pero sin "usuario: texto": mensaje de sistema
            # (p. ej. "Laura creó el grupo..."). Se descarta.
            continua_mensaje = False
        elif continua_mensaje:
            # Línea sin fecha: continuación del mensaje anterior
            anterior = mensajes[-1]
            mensajes[-1] = anterior._replace(texto=anterior.texto + '\n' + linea)

    return mensajes


def _convertir_fechahora(fecha_str, hora_str):
    """
    Intenta convertir strings de fecha y hora a objetos date y time
    probando varios formatos comunes.
    """
    # Formatos de fecha posibles (D/M/A, M/D/A, A-M-D, años 2 o 4 dígitos)
    formatos_fecha = [
        '%d/%m/%Y', '%d/%m/%y', # España/Latam
        '%m/%d/%y', '%m/%d/%Y', # USA
        '%Y-%m-%d'
    ]

    # Formatos de hora posibles
    formatos_hora = [
        '%H:%M',          # 24h simple (14:30)
        '%H:%M:%S',       # 24h con segundos
        '%I:%M %p',       # 12h (02:30 PM)
        '%I:%M:%S %p',    # 12h con segundos
        '%H:%M %p'        # Variaciones raras
    ]

    # Normalización de la hora: "9:15 p. m.", "9:15pm" o "9:15 PM" -> "9:15 PM"
    hora_str_clean = re.sub(r'\s*([apAP])\.?\s?[mM]\.?$', r' \1M', hora_str.strip()).upper()

    fecha_dt = None
    hora_dt = None

    # Intentar parsear fecha
    for fmt in formatos_fecha:
        try:
            fecha_dt = datetime.strptime(fecha_str, fmt).date()
            break
        except ValueError:
            continue

    # Intentar parsear hora
    for fmt in formatos_hora:
        try:
            hora_dt = datetime.strptime(hora_str_clean, fmt).time()
            break
        except ValueError:
            continue

    return fecha_dt, hora_dt
