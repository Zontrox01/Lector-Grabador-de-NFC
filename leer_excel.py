import pandas as pd

def limpiar_texto(texto):
    # Convertir None o NaN en cadena vacía
    if texto is None or pd.isna(texto):
        return ""

    texto = str(texto)

    # Eliminamos solo lo que puede romper el formato
    texto = texto.replace("\n", " ")
    texto = texto.replace("\r", " ")
    texto = texto.replace("|", " ")   # separador de campos
    texto = texto.replace(":", " ")   # separador clave-valor (solo afecta a texto legible)

    return texto

def limpiar_nan_para_legible(valor):
    if valor is None or pd.isna(valor):
        return ""
    return str(valor)

def formatear_fila(fila, grabar_vacios=True):
    columnas = list(fila.items())

    texto_legible  = ""
    texto_compacto = ""

    for columna, valor in columnas:
        columna_limpia = limpiar_texto(columna)
        valor_limpio   = limpiar_texto(valor)

        # Texto legible siempre muestra todo
        texto_legible += f"[B]{columna}[/B]: {limpiar_nan_para_legible(valor)}\n"

        # Texto compacto: omitir campo si valor vacío y grabar_vacios=False
        if not grabar_vacios and valor_limpio == "":
            continue

        texto_compacto += f"{columna_limpia}|{valor_limpio}|"

    texto_compacto = texto_compacto.rstrip("|")

    return texto_legible.strip(), texto_compacto
