import tkinter as tk
from tkinter import messagebox
import smartcard.System
from smartcard.util import toHexString

# ============================================================
#   FUNCIONES NFC (las mismas que ya usas)
# ============================================================

def conectar():
    readers = smartcard.System.readers()
    if not readers:
        raise Exception("No hay lectores PC/SC disponibles.")
    conn = readers[0].createConnection()
    conn.connect()
    return conn

def read_page(conn, page):
    apdu = [0xFF, 0xB0, 0x00, page, 4]
    return conn.transmit(apdu)

def write_page(conn, page, data4):
    apdu = [0xFF, 0xD6, 0x00, page, 0x04] + data4
    return conn.transmit(apdu)

def bloquear_ntag():
    try:
        conn = conectar()

        # Leer UID
        uid, sw1, sw2 = conn.transmit([0xFF, 0xCA, 0x00, 0x00, 0x00])
        uid_hex = toHexString(uid)
        
        # Leer Dynamic Lock Bytes (página 40 = 0x28)
        lock40, sw1, sw2 = read_page(conn, 0x28)

        # Crear nuevos lock bytes (bloqueo total)
        new_lock40 = [0xFF, 0xFF, lock40[2], lock40[3]]

        # Escribir bloqueo
        _, sw1, sw2 = write_page(conn, 0x28, new_lock40)

        # Verificar
        lock40_after, sw1, sw2 = read_page(conn, 0x28)

        messagebox.showinfo(
            "Bloqueo completado",
            f"NTAG bloqueado permanentemente.\n\nUID: {uid_hex}\n\n"
            f"Lock bytes antes: {lock40}\n"
            f"Lock bytes después: {lock40_after}\n\n"
            "⚠ Esta acción es irreversible."
        )

    except Exception as e:
        messagebox.showerror("Error", f"No se pudo bloquear la etiqueta:\n{e}")

# ============================================================
#   INTERFAZ GRÁFICA
# ============================================================

def confirmar_bloqueo():
    respuesta = messagebox.askquestion(
        "Advertencia",
        "⚠ ATENCIÓN ⚠\n\n"
        "Vas a BLOQUEAR PERMANENTEMENTE este NTAG.\n"
        "La acción es IRREVERSIBLE.\n\n"
        "El contenido actual quedará de solo lectura para siempre.\n\n"
        "¿Deseas continuar?",
        icon="warning"
    )

    if respuesta == "yes":
        bloquear_ntag()

def crear_ventana():
    root = tk.Tk()
    root.title("Bloqueo permanente NTAG")
    root.geometry("350x200")

    tk.Label(root, text="Herramienta de bloqueo NTAG", font=("Arial", 14, "bold")).pack(pady=20)

    tk.Button(
        root,
        text="Bloquear permanentemente un NTAG",
        font=("Arial", 11),
        width=30,
        command=confirmar_bloqueo
    ).pack(pady=10)

    tk.Button(
        root,
        text="Salir",
        font=("Arial", 11),
        width=30,
        command=root.destroy
    ).pack(pady=10)

    root.mainloop()

if __name__ == "__main__":
    crear_ventana()
