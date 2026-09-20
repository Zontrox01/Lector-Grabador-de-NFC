from smartcard.System import readers

# Información de memoria de cada NTAG
NTAG_INFO = {
    "NTAG213": {"start": 4, "end": 39},
    "NTAG215": {"start": 4, "end": 129},
    "NTAG216": {"start": 4, "end": 225},
}

# ---------------------------------------------------------
#   CONSTRUCCIÓN DEL MENSAJE NDEF (TLV + TextRecord)
# ---------------------------------------------------------

def construir_tlv_ndef_texto(texto):
    payload_text = texto.encode("utf-8")
    lang = b"es"
    status = len(lang)
    payload = bytes([status]) + lang + payload_text
    payload_len = len(payload)

    if payload_len <= 255:
        ndef = bytes([0xD1, 0x01, payload_len, 0x54]) + payload
    else:
        ndef = bytes([
            0xC1, 0x01,
            (payload_len >> 24) & 0xFF,
            (payload_len >> 16) & 0xFF,
            (payload_len >> 8) & 0xFF,
            payload_len & 0xFF,
            0x54
        ]) + payload

    ndef_len = len(ndef)

    if ndef_len <= 255:
        tlv = bytes([0x03, ndef_len]) + ndef + bytes([0xFE])
    else:
        tlv = bytes([
            0x03, 0xFF,
            (ndef_len >> 8) & 0xFF,
            ndef_len & 0xFF
        ]) + ndef + bytes([0xFE])

    return tlv

# ---------------------------------------------------------
#   FUNCIONES DE ESCRITURA APDU
# ---------------------------------------------------------

def conectar_lector():
    r = readers()
    if not r:
        raise Exception("No se encontró ningún lector NFC.")
    return r[0].createConnection()

def enviar_apdu(conexion, apdu):
    data, sw1, sw2 = conexion.transmit(apdu)
    return data, sw1, sw2

# ---------------------------------------------------------
#   FUNCIÓN PRINCIPAL: ESCRIBIR TEXTO NDEF EN NTAG
# ---------------------------------------------------------

def escribir_nfc(texto, tipo_tag="NTAG216"):
    if tipo_tag not in NTAG_INFO:
        raise Exception("Tipo de NTAG no válido.")

    info = NTAG_INFO[tipo_tag]
    bloque_inicio = info["start"]
    bloque_fin = info["end"]

    tlv = construir_tlv_ndef_texto(texto)

    capacidad_bytes = (bloque_fin - bloque_inicio + 1) * 4
    if len(tlv) > capacidad_bytes:
        raise Exception(
            f"El mensaje NDEF ({len(tlv)} bytes) excede la capacidad "
            f"de {tipo_tag} ({capacidad_bytes} bytes)."
        )

    while len(tlv) % 4 != 0:
        tlv += b"\x00"

    bloques = [tlv[i:i+4] for i in range(0, len(tlv), 4)]

    conexion = conectar_lector()
    conexion.connect()

    pwd_bytes = [0x4C, 0x4D, 0x52, 0x42]

    # Reconectar tag
    CMD = [0xFF, 0x00, 0x00, 0x00, 0x04, 0xD4, 0x4A, 0x01, 0x00]
    conexion.transmit(CMD)

    # Intentar AUTH con LMRB
    AUTH = [0xFF, 0x00, 0x00, 0x00, 0x07,
            0xD4, 0x42, 0x1B,
            pwd_bytes[0], pwd_bytes[1],
            pwd_bytes[2], pwd_bytes[3]]
    response, sw1, sw2 = conexion.transmit(AUTH)

    auth_ok = (sw1 == 0x90 and sw2 == 0x00
               and len(response) >= 3
               and response[2] == 0x00)

    # Escritura bloque a bloque
    errores = 0
    bloque_actual = bloque_inicio

    for bloque in bloques:
        if auth_ok:
            # Tag con LMRB — sin reconexión para mantener sesión auth
            apdu = [0xFF, 0x00, 0x00, 0x00, 0x08,
                    0xD4, 0x42, 0xA2,
                    bloque_actual] + list(bloque)
            data, sw1, sw2 = conexion.transmit(apdu)
            ok = (sw1 == 0x90 and sw2 == 0x00
                  and len(data) >= 3
                  and data[2] in [0x00, 0x02])
        else:
            # Tag nuevo sin protección — reconexión + FF D6
            CMD_RECON = [0xFF, 0x00, 0x00, 0x00, 0x04, 0xD4, 0x4A, 0x01, 0x00]
            conexion.transmit(CMD_RECON)
            apdu = [0xFF, 0xD6, 0x00, bloque_actual, 0x04] + list(bloque)
            data, sw1, sw2 = conexion.transmit(apdu)
            ok = (sw1 == 0x90 and sw2 == 0x00)

        if not ok:
            errores += 1
        bloque_actual += 1
        if bloque_actual > bloque_fin:
            break

    if errores > 0:
        raise Exception(f"Escritura con {errores} errores.")
