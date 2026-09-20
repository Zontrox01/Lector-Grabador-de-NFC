from smartcard.System import readers

# ---------------------------------------------------------
#   APDU BÁSICO
# ---------------------------------------------------------

def enviar_apdu(conexion, apdu):
    data, sw1, sw2 = conexion.transmit(apdu)
    return data, sw1, sw2

def conectar_lector():
    r = readers()
    if not r:
        raise Exception("No se encontró ningún lector NFC.")
    return r[0].createConnection()

# ---------------------------------------------------------
#   DETECCIÓN AUTOMÁTICA POR LECTURA REAL
# ---------------------------------------------------------

def detectar_tipo_tag(conexion):
    bloque = 4
    ultimo_valido = 3

    while True:
        apdu = [0xFF, 0xB0, 0x00, bloque, 0x04]
        data, sw1, sw2 = enviar_apdu(conexion, apdu)

        if sw1 != 0x90 or sw2 != 0x00:
            break

        ultimo_valido = bloque
        bloque += 1

    if ultimo_valido <= 39:
        return "NTAG213", ultimo_valido
    elif ultimo_valido <= 129:
        return "NTAG215", ultimo_valido
    elif ultimo_valido <= 225:
        return "NTAG216", ultimo_valido
    else:
        return f"DESCONOCIDA", ultimo_valido

# ---------------------------------------------------------
#   LECTURA DE BLOQUES
# ---------------------------------------------------------

def leer_bloque(conexion, bloque):
    apdu = [0xFF, 0xB0, 0x00, bloque, 0x04]
    data, sw1, sw2 = enviar_apdu(conexion, apdu)

    if sw1 != 0x90 or sw2 != 0x00:
        raise Exception(f"Error leyendo bloque {bloque}: SW1={sw1:02X} SW2={sw2:02X}")

    return bytes(data)

# ---------------------------------------------------------
#   FUNCIÓN PRINCIPAL
# ---------------------------------------------------------

def leer_nfc(tipo_tag=None):
    conexion = conectar_lector()
    conexion.connect()

    tipo_detectado, ultimo_bloque = detectar_tipo_tag(conexion)
    print(f"Etiqueta detectada: {tipo_detectado} (último bloque válido: {ultimo_bloque})")

    bloque_inicio = 4
    bloque_fin = ultimo_bloque

    datos = b""
    for bloque in range(bloque_inicio, bloque_fin + 1):
        datos += leer_bloque(conexion, bloque)

    if datos[0] != 0x03:
        raise Exception("No se encontró TLV tipo NDEF (0x03).")

    longitud_ndef = datos[1]
    ndef = datos[2:2 + longitud_ndef]

    if ndef[0] != 0xD1:
        raise Exception("El registro NDEF no es un Text Record corto (0xD1).")

    tipo_len = ndef[1]
    payload_len = ndef[2]

    payload = ndef[3 + tipo_len:3 + tipo_len + payload_len]

    status = payload[0]
    lang_len = status & 0x3F

    texto = payload[1 + lang_len:].decode("utf-8")

    return texto
