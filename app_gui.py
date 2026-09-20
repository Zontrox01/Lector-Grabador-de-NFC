import tkinter as tk
from tkinter import filedialog, messagebox
import pandas as pd
from leer_excel import formatear_fila
from nfc_writer_apdu import escribir_nfc, construir_tlv_ndef_texto
from nfc_reader_apdu import leer_nfc
from bloquear_ntag import confirmar_bloqueo
import smartcard.System as system
from smartcard.util import toHexString
import sys
import os

def resource_path(relative_path):
    """Obtiene la ruta correcta tanto en desarrollo como en el .exe"""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

class AppNFC:
    def __init__(self, root):
        self.root = root
        self.root.title("Grabador de tarjetas NFC")
        self.root.geometry("400x280")

        # Icono en barra de títulos y barra de tareas
        try:
            icono_path = resource_path(os.path.join("datos", "icono.png"))
            img = tk.PhotoImage(file=icono_path)
            self.root.iconphoto(True, img)
        except Exception:
            pass

        self.df = None
        self.fila_actual = 0
        self.capacidad_actual = 504
        self.tipo_tag = tk.StringVar(value="NTAG215")

        tk.Label(root, text="Seleccione una opción", font=("Arial", 14)).pack(pady=20)

        tk.Button(root, text="Lectura", width=20, command=self.abrir_lectura).pack(pady=5)
        tk.Button(root, text="Escritura", width=20, command=self.abrir_escritura).pack(pady=5)
        tk.Button(root, text="Bloquear NTAG", width=20, command=self.abrir_bloqueo,bg="#cc0000", fg="white").pack(pady=5)
        tk.Button(root, text="Salir", width=20, command=self.salir).pack(pady=20)

        self.menu_bar = tk.Menu(self.root)
        self.menu_archivo = tk.Menu(self.menu_bar, tearoff=0)
        self.menu_archivo.add_command(label="Salir", command=self.salir)
        self.menu_bar.add_cascade(label="Archivo", menu=self.menu_archivo)

        self.menu_ayuda = tk.Menu(self.menu_bar, tearoff=0)
        self.menu_ayuda.add_command(label="Acerca de…", command=self.mostrar_acerca_de)
        self.menu_ayuda.add_command(label="Manual rápido", command=self.mostrar_manual)
        self.menu_ayuda.add_command(label="Información sobre NTAGs", command=self.mostrar_info_ntag)
        self.menu_bar.add_cascade(label="Ayuda", menu=self.menu_ayuda)

        self.root.config(menu=self.menu_bar)

    # ============================================================
    #              HELPERS NFC — LÓGICA PROBADA
    # ============================================================

    def _reconectar_tag(self, conn):
        """Despierta el tag usando InListPassiveTarget."""
        CMD = [0xFF, 0x00, 0x00, 0x00, 0x04, 0xD4, 0x4A, 0x01, 0x00]
        conn.transmit(CMD)

    def _escribir_pagina(self, conn, pagina, datos_4bytes):
        """Escribe 4 bytes en una página con reconexión previa."""
        self._reconectar_tag(conn)
        WRITE = [0xFF, 0xD6, 0x00, pagina, 0x04] + datos_4bytes
        response, sw1, sw2 = conn.transmit(WRITE)
        return sw1 == 0x90 and sw2 == 0x00

    def _autenticar(self, conn, pwd_bytes):
        """PWD_AUTH via wrapper PN532. Devuelve True si OK."""
        AUTH = [0xFF, 0x00, 0x00, 0x00, 0x07,
                0xD4, 0x42, 0x1B,
                pwd_bytes[0], pwd_bytes[1],
                pwd_bytes[2], pwd_bytes[3]]
        response, sw1, sw2 = conn.transmit(AUTH)
        if sw1 == 0x90 and sw2 == 0x00 and len(response) >= 3:
            return response[2] == 0x00
        return False

    def _configurar_proteccion(self, conn, pagina_pwd, pagina_pack, pagina_cfg0, pagina_cfg1):
        """Escribe PWD, PACK, AUTH0 y CFG1."""
        pwd_bytes  = [0x4C, 0x4D, 0x52, 0x42]  # LMRB
        pack_bytes = [0xAB, 0xCD, 0x00, 0x00]

        if not self._escribir_pagina(conn, pagina_pwd, pwd_bytes):
            return False, "Error escribiendo PWD"
        if not self._escribir_pagina(conn, pagina_pack, pack_bytes):
            return False, "Error escribiendo PACK"
        if not self._escribir_pagina(conn, pagina_cfg0, [0x00, 0x00, 0x00, 0x04]):
            return False, "Error configurando AUTH0"
        if not self._escribir_pagina(conn, pagina_cfg1, [0x00, 0x00, 0x00, 0x00]):
            return False, "Error configurando CFG1"
        return True, "OK"

    # ============================================================
    #                       VENTANA LECTURA
    # ============================================================

    def abrir_lectura(self):
        self._sincronizar_root()        
        self.root.withdraw()
        self.win_lectura = tk.Toplevel(self.root)
        self._colocar_en_pantalla_actual(self.win_lectura)
        self.win_lectura.title("Lectura NFC")
        self.win_lectura.geometry("600x400")

        self.texto_lectura = tk.Text(self.win_lectura, width=70, height=15, font=("Arial", 10))
        self.texto_lectura.pack(pady=10)

        fila = tk.Frame(self.win_lectura)
        fila.pack(pady=10)

        tk.Button(fila, text="Leer",   width=15, command=self.leer_nfc).grid(row=0, column=0, padx=10)
        tk.Button(fila, text="Volver", width=15, command=self.volver_desde_lectura).grid(row=0, column=1, padx=10)
        tk.Button(fila, text="Salir",  width=15, command=self.salir).grid(row=0, column=2, padx=10)

    def leer_nfc(self):
        self._sincronizar_root()
        try:
            uid = self.leer_uid_pcsc()
            if not uid:
                messagebox.showerror("Error", "No se pudo leer el UID de la tarjeta.")
                return

            ruta_excel = self.buscar_en_indice(uid)
            if not ruta_excel:
                messagebox.showwarning("No encontrado", f"El UID {uid} no está en el índice.")
                self.mostrar_contenido_raw(uid)
                return

            fila = self.buscar_fila_en_excel(ruta_excel, uid)
            if fila is None:
                messagebox.showwarning("No encontrado",
                                       f"El UID {uid} no aparece dentro del archivo:\n{ruta_excel}")

            # Siempre muestra el contenido físico de la tarjeta
            self.mostrar_contenido_raw(uid)

        except Exception as e:
            messagebox.showerror("Error", f"No se pudo leer la tarjeta:\n{e}")


    def mostrar_contenido_raw(self, uid):
        self._sincronizar_root()
        try:
            readers = system.readers()
            if not readers:
                self.texto_lectura.delete("1.0", tk.END)
                self.texto_lectura.insert("1.0", "No hay lectores PC/SC disponibles.")
                return

            conn = readers[0].createConnection()
            conn.connect()

            GET_DATA = [0xFF, 0xB0, 0x00, 0x03, 0x04]
            datos, sw1, sw2 = conn.transmit(GET_DATA)

            if sw1 != 0x90:
                self.texto_lectura.delete("1.0", tk.END)
                self.texto_lectura.insert("1.0", "Error al leer el Capability Container del tag.")
                return

            capacidad_byte = datos[2]
            if capacidad_byte == 0x12:
                tipo_ntag = "NTAG213"
                pagina_fin = 39
            elif capacidad_byte == 0x3E:
                tipo_ntag = "NTAG215"
                pagina_fin = 129
            elif capacidad_byte == 0x6D:
                tipo_ntag = "NTAG216"
                pagina_fin = 225
            else:
                tipo_ntag = f"Desconocido (CC[2]=0x{capacidad_byte:02X})"
                pagina_fin = 39

            todos_los_bytes = []
            for page in range(4, pagina_fin + 1):
                READ = [0xFF, 0xB0, 0x00, page, 0x04]
                response, sw1, sw2 = conn.transmit(READ)
                if sw1 != 0x90 or sw2 != 0x00:
                    break
                todos_los_bytes.extend(response)

            texto_extraido = None
            try:
                data = bytes(todos_los_bytes)
                idx = data.index(0x03)
                if data[idx + 1] == 0xFF:
                    ndef_len = (data[idx + 2] << 8) | data[idx + 3]
                    ndef_msg = data[idx + 4: idx + 4 + ndef_len]
                else:
                    ndef_len = data[idx + 1]
                    ndef_msg = data[idx + 2: idx + 2 + ndef_len]

                flags = ndef_msg[0]
                sr = (flags & 0x10) != 0
                if sr:
                    payload_len = ndef_msg[2]
                    payload = ndef_msg[4: 4 + payload_len]
                else:
                    payload_len = ((ndef_msg[2] << 24) | (ndef_msg[3] << 16) |
                                   (ndef_msg[4] << 8) | ndef_msg[5])
                    payload = ndef_msg[7: 7 + payload_len]

                lang_len = payload[0] & 0x3F
                texto_extraido = payload[1 + lang_len:].decode("utf-8", errors="replace")
            except Exception:
                texto_extraido = None

            self.texto_lectura.delete("1.0", tk.END)
            self.texto_lectura.tag_configure("bold", font=("Arial", 10, "bold"))

            # Línea de cabecera en negrita
            self.texto_lectura.insert(tk.END, f"UID: {uid}  —  Tipo: {tipo_ntag}\n\n", "bold")

            if texto_extraido:
                try:
                    partes = texto_extraido.split("|")
                    if partes and partes[-1].strip() == "":
                        partes = partes[:-1]

                    if len(partes) >= 2:
                        # Procesa pares, ignora el último elemento si el total es impar
                        for i in range(0, len(partes) - 1, 2):
                            columna = partes[i].strip()
                            valor = partes[i + 1].strip()
                            self.texto_lectura.insert(tk.END, columna, "bold")
                            self.texto_lectura.insert(tk.END, f": {valor}\n")
                    else:
                        self.texto_lectura.insert(tk.END, texto_extraido)
                except Exception:
                    self.texto_lectura.insert(tk.END, texto_extraido)
            else:
                self.texto_lectura.insert(tk.END, "No se pudo extraer el contenido NDEF del tag.")

        except Exception as e:
            self.texto_lectura.delete("1.0", tk.END)
            self.texto_lectura.insert("1.0", f"Error leyendo contenido:\n{e}")


    def limpiar_uid(self, uid):
        if not uid:
            return ""
        return str(uid).replace("'", "").strip().upper()

    def volver_desde_lectura(self):
        self.win_lectura.destroy()
        self.root.deiconify()

    def buscar_en_indice(self, uid):
        import openpyxl
        from pathlib import Path

        if not hasattr(self, "indice") or self.indice is None:
            ruta_indice = Path("Datos") / "indice.xlsx"
            wb = openpyxl.load_workbook(ruta_indice)
            ws = wb.active
            self.indice = {str(row[0]).strip().upper(): row[1]
                           for row in ws.iter_rows(min_row=2, values_only=True)}

        uid = self.limpiar_uid(uid)
        return self.indice.get(uid, None)

    def buscar_fila_en_excel(self, ruta_excel, uid):
        df = pd.read_excel(ruta_excel, dtype=str)
        for i, fila in df.iterrows():
            uid_fila = self.limpiar_uid(fila.iloc[0])
            if uid_fila == self.limpiar_uid(uid):
                return fila
        return None

    # ============================================================
    #                       VENTANA ESCRITURA
    # ============================================================

    def abrir_escritura(self):
        self._sincronizar_root()
        self.root.withdraw()
        self.mostrar_ventana_seleccion_excel()

    def mostrar_ventana_seleccion_excel(self):
        self._sincronizar_root()
        self.win_excel = tk.Toplevel(self.root)
        self._colocar_en_pantalla_actual(self.win_excel)   # ← la ventana correcta
        self.win_excel.title("Escritura NFC")
        self.win_excel.geometry("500x350")

        tk.Label(self.win_excel, text="Tipo de NTAG:", font=("Arial", 12, "bold")).pack(pady=5)

        fila_ntag = tk.Frame(self.win_excel)
        fila_ntag.pack(pady=5)

        self.tipo_tag = tk.StringVar(value="NTAG215")

        tk.Radiobutton(fila_ntag, text="NTAG213", variable=self.tipo_tag, value="NTAG213",
                       command=lambda: self.cambiar_capacidad(self.tipo_tag.get())).pack(side="left", padx=10)
        tk.Radiobutton(fila_ntag, text="NTAG215", variable=self.tipo_tag, value="NTAG215",
                       command=lambda: self.cambiar_capacidad(self.tipo_tag.get())).pack(side="left", padx=10)
        tk.Radiobutton(fila_ntag, text="NTAG216", variable=self.tipo_tag, value="NTAG216",
                       command=lambda: self.cambiar_capacidad(self.tipo_tag.get())).pack(side="left", padx=10)

        tk.Label(self.win_excel, text="Archivo Excel:", font=("Arial", 12, "bold")).pack(pady=5)

        self.ruta_excel = tk.StringVar()
        from pathlib import Path
        ruta_archivo = Path("Datos") / "ultimo_archivo.txt"
        if ruta_archivo.exists():
            ultima_ruta = ruta_archivo.read_text(encoding="utf-8").strip()
            self.ruta_excel.set(ultima_ruta)

        tk.Entry(self.win_excel, textvariable=self.ruta_excel, width=40).pack()
        tk.Button(self.win_excel, text="Seleccionar archivo", command=self.seleccionar_excel).pack(pady=5)

        tk.Label(self.win_excel, text="Registro inicial:", font=("Arial", 12, "bold")).pack(pady=5)

        self.entry_fila = tk.Entry(self.win_excel)
        self.entry_fila.insert(0, "1")
        self.entry_fila.pack()

        tk.Button(self.win_excel, text="Iniciar proceso", command=self.iniciar_proceso, bg="#00aa55", fg="white").pack(pady=15)

        fila_botones = tk.Frame(self.win_excel)
        fila_botones.pack(pady=10)
        tk.Button(fila_botones, text="Volver", width=15, command=self.volver_desde_escritura).grid(row=0, column=0, padx=10)
        tk.Button(fila_botones, text="Salir",  width=15, command=self.salir).grid(row=0, column=1, padx=10)

    def cambiar_capacidad(self, seleccion):
        if seleccion == "NTAG213":
            self.capacidad_actual = 144
        elif seleccion == "NTAG215":
            self.capacidad_actual = 504
        else:
            self.capacidad_actual = 888

    def volver_desde_escritura(self):
        self._sincronizar_root()
        self.win_excel.destroy()
        self.root.deiconify()

    def seleccionar_excel(self):
        self._sincronizar_root()
        from pathlib import Path
        ruta = filedialog.askopenfilename(
            title="Seleccionar archivo Excel",
            filetypes=[("Archivos Excel", "*.xlsx *.xls")]
        )
        if ruta:
            self.ruta_excel.set(ruta)
            ruta_archivo = Path("Datos") / "ultimo_archivo.txt"
            ruta_archivo.write_text(ruta, encoding="utf-8")

    def iniciar_proceso(self):
        self._sincronizar_root()
        ruta = self.ruta_excel.get()
        if not ruta:
            messagebox.showerror("Error", "Selecciona un archivo Excel.")
            return
        try:
            self.df = pd.read_excel(ruta, dtype=str)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo leer el Excel:\n{e}")
            return
        try:
            fila = int(self.entry_fila.get()) - 1
        except:
            messagebox.showerror("Error", "Introduce un número de fila válido.")
            return
        if fila < 0 or fila >= len(self.df):
            messagebox.showerror("Error", "Fila fuera de rango.")
            return
        self.fila_actual = fila
        self.win_excel.destroy()
        self.mostrar_ventana_grabacion()

    # ============================================================
    #                 VENTANA DE GRABACIÓN
    # ============================================================

    def mostrar_ventana_grabacion(self):
        self._sincronizar_root()
        self.win = tk.Toplevel(self.root)
        self._colocar_en_pantalla_actual(self.win)         # ← la ventana correcta
        self.win.title("Grabación de tarjetas")
        self.win.geometry("600x570")

        tk.Label(self.win, text="Ventana de datos:", font=("Arial", 12, "bold")).pack(pady=5)

        self.texto_datos = tk.Text(self.win, width=70, height=15, font=("Arial", 10))
        self.texto_datos.pack(pady=10)

        fila_info = tk.Frame(self.win)
        fila_info.pack(pady=5)

        self.label_tamano = tk.Label(fila_info, text=f"Tamaño: - / {self.capacidad_actual} bytes", font=("Arial", 10))
        self.label_tamano.grid(row=0, column=0, padx=10)

        self.label_contador = tk.Label(fila_info, text="Registro - de -", font=("Arial", 10))
        self.label_contador.grid(row=0, column=1, padx=10)

        self.var_grabar_vacios = tk.BooleanVar(value=False)
        tk.Checkbutton(
            fila_info,
            text="Grabar encabezados de campos vacíos",
            variable=self.var_grabar_vacios,
            command=self.actualizar_texto
        ).grid(row=0, column=2, padx=10)

        self.label_registro = tk.Label(self.win, text="", font=("Arial", 11, "bold"))
        self.label_registro.pack(pady=5)

        fila1 = tk.Frame(self.win)
        fila1.pack(pady=5)
        tk.Button(fila1, text="Registro Anterior",  width=18, command=self.anterior).grid(row=0, column=0, padx=10)
        tk.Button(fila1, text="Registro Siguiente", width=18, command=self.siguiente).grid(row=0, column=1, padx=10)
        self.entry_ir = tk.Entry(fila1, width=5, font=("Arial", 11))
        self.entry_ir.grid(row=0, column=2, padx=10)
        tk.Button(fila1, text="Ir al registro", width=10, command=self.ir_a_registro).grid(row=0, column=3, padx=5)

        fila2 = tk.Frame(self.win)
        fila2.pack(pady=10)
        tk.Button(fila2, text="Grabar tarjeta", width=20,
                  command=self.grabar_etiqueta,
                  bg="#00aa55", fg="white").pack()

        fila3 = tk.Frame(self.win)
        fila3.pack(pady=10)
        tk.Button(fila3, text="Cambiar Archivo Excel",   width=20, command=self.ir_a_seleccion_excel).grid(row=0, column=0, padx=10)
        tk.Button(fila3, text="Volver al Menú Principal", width=20, command=self.volver_a_principal).grid(row=0, column=1, padx=10)

        fila4 = tk.Frame(self.win)
        fila4.pack(pady=10)
        tk.Button(fila4, text="Salir de la App", width=15, command=self.salir).pack()

        self.actualizar_texto()

    def ir_a_registro(self):
        valor = self.entry_ir.get()
        if not valor.isdigit():
            messagebox.showerror("Error", "Debe introducir un número de registro válido.")
            return
        numero = int(valor)
        total = len(self.df)
        if numero < 1 or numero > total:
            messagebox.showerror("Error", f"El registro debe estar entre 1 y {total}.")
            return
        self.fila_actual = numero - 1
        self.actualizar_texto()
        self.entry_ir.delete(0, tk.END)

    def ir_a_seleccion_excel(self):
        self._sincronizar_root()        
        self.win.destroy()
        self.mostrar_ventana_seleccion_excel()

    def volver_a_principal(self):
        self._sincronizar_root()
        self.win.destroy()
        self.root.deiconify()

    def actualizar_texto(self):
        fila = self.df.iloc[self.fila_actual]
        uid_actual = str(fila.iloc[0]).strip() if pd.notna(fila.iloc[0]) else ""

        if uid_actual == "":
            mensaje = "Tarjeta NUEVA — no existe en la base de datos"
            color_msg = "green"
        else:
            mensaje = f"Tarjeta EXISTENTE — UID: {uid_actual}"
            color_msg = "red"

        self.label_registro.config(text=mensaje, fg=color_msg)

        fila_sin_uid = fila.iloc[1:]
        texto_legible, texto_compacto = formatear_fila(
            fila_sin_uid,
            grabar_vacios=self.var_grabar_vacios.get()
        )

        self.texto_datos.delete("1.0", tk.END)
        texto_sin_tags = texto_legible.replace("[B]", "").replace("[/B]", "")
        self.texto_datos.insert("1.0", texto_sin_tags)
        self.texto_datos.tag_configure("bold", font=("Arial", 10, "bold"))

        pos = "1.0"
        while True:
            start = self.texto_datos.search(":", pos, tk.END)
            if not start:
                break
            line_start = f"{start.split('.')[0]}.0"
            self.texto_datos.tag_add("bold", line_start, start)
            pos = f"{start}+1c"

        self.data_url_actual = texto_compacto
        tlv = construir_tlv_ndef_texto(texto_compacto)
        tam = len(tlv)
        registro_actual = self.fila_actual + 1
        total = len(self.df)
        self.label_tamano.config(text=f"Tamaño: {tam} / {self.capacidad_actual} bytes")
        self.label_contador.config(text=f"Registro {registro_actual} de {total}")

        if tam > self.capacidad_actual:
            color = "red"
        elif tam > self.capacidad_actual * 0.85:
            color = "orange"
        else:
            color = "green"
        self.label_tamano.config(fg=color)

    def escribir_en_indice(self, uid, ruta_archivo):
        import openpyxl
        from pathlib import Path

        ruta_indice = Path("Datos") / "indice.xlsx"
        if not ruta_indice.exists():
            wb = openpyxl.Workbook()
            ws = wb.active
            ws["A1"] = "UID"
            ws["B1"] = "ruta"
            wb.save(ruta_indice)

        wb = openpyxl.load_workbook(ruta_indice)
        ws = wb.active
        ws.append([uid, ruta_archivo])
        wb.save(ruta_indice)

    def escribir_uid_en_excel(self, uid):
        import openpyxl
        ruta = self.ruta_excel.get()
        wb = openpyxl.load_workbook(ruta)
        ws = wb.active
        fila_excel = self.fila_actual + 2
        ws[f"A{fila_excel}"] = uid
        wb.save(ruta)

    # ============================================================
    #                 GRABAR ETIQUETA — LÓGICA CORREGIDA
    # ============================================================

    def grabar_etiqueta(self):
        try:
            tipo = self.tipo_tag.get()

            # Páginas según tipo de NTAG
            if tipo == "NTAG213":
                pagina_pwd  = 43
                pagina_pack = 44
                pagina_cfg0 = 41
                pagina_cfg1 = 42
            elif tipo == "NTAG215":
                pagina_pwd  = 133
                pagina_pack = 134
                pagina_cfg0 = 130
                pagina_cfg1 = 131
            else:  # NTAG216
                pagina_pwd  = 229
                pagina_pack = 230
                pagina_cfg0 = 227
                pagina_cfg1 = 228

            pwd_bytes = [0x4C, 0x4D, 0x52, 0x42]  # LMRB

            readers = system.readers()
            if not readers:
                messagebox.showerror("Error", "No hay lectores PC/SC disponibles.")
                return

            # ==============================
            # LEER UID PRIMERO
            # ==============================
            uid = self.leer_uid_pcsc()
            if not uid:
                messagebox.showerror("Error", "No se pudo leer el UID de la tarjeta.")
                return

            conn = readers[0].createConnection()
            conn.connect()

            # ==============================
            # DETECCIÓN: nuevo o con LMRB
            # ==============================
            auth_ok = self._autenticar(conn, pwd_bytes)

            if auth_ok:
                # ==============================
                # CASO 1: tag con LMRB — reescribir
                # ==============================
                conn.disconnect()
                escribir_nfc(self.data_url_actual, tipo)

            else:
                # Comprobar si es tag nuevo o contraseña desconocida
                CMD_RECON = [0xFF, 0x00, 0x00, 0x00, 0x04, 0xD4, 0x4A, 0x01, 0x00]
                conn.transmit(CMD_RECON)
                TEST = [0xFF, 0xD6, 0x00, 4, 0x04, 0x00, 0x00, 0x00, 0x00]
                data, sw1, sw2 = conn.transmit(TEST)
                conn.disconnect()

                if sw1 == 0x90 and sw2 == 0x00:
                    # ==============================
                    # CASO 2: tag nuevo — escribir y proteger
                    # ==============================
                    escribir_nfc(self.data_url_actual, tipo)

                    conn = readers[0].createConnection()
                    conn.connect()
                    ok, msg = self._configurar_proteccion(
                        conn, pagina_pwd, pagina_pack, pagina_cfg0, pagina_cfg1
                    )
                    conn.disconnect()
                    if not ok:
                        messagebox.showwarning("Aviso", f"Datos escritos pero: {msg}")
                else:
                    # ==============================
                    # CASO 3: contraseña desconocida
                    # ==============================
                    messagebox.showwarning(
                        "Contraseña desconocida",
                        "La tarjeta tiene una contraseña desconocida.\n\n"
                        "No es posible grabar esta tarjeta.\nOperación cancelada."
                    )
                    return

            # ==============================
            # ACTUALIZAR EXCEL E ÍNDICE
            # ==============================
            self.escribir_uid_en_excel(uid)
            self.df = pd.read_excel(self.ruta_excel.get(), dtype=str)
            self.escribir_en_indice(uid, self.ruta_excel.get())
            self.indice = None

            messagebox.showinfo("NFC", f"Tarjeta grabada correctamente.\n\nUID: {uid}\nTipo: {tipo}")
            self.siguiente()

        except Exception as e:
            messagebox.showerror("Error", f"No se pudo grabar la tarjeta, asegurese de tener el excel de datos cerrado:\n{e}")


    # ============================================================
    #                       LEER UID
    # ============================================================

    def leer_uid_pcsc(self):
        readers_list = system.readers()
        if not readers_list:
            raise Exception("No hay lectores PC/SC disponibles.")

        connection = readers_list[0].createConnection()
        try:
            connection.connect()
        except:
            raise Exception("No se detecta ninguna tarjeta. Acércala al lector.")

        GET_UID = [0xFF, 0xCA, 0x00, 0x00, 0x00]
        data, sw1, sw2 = connection.transmit(GET_UID)

        if sw1 == 0x90 and sw2 == 0x00:
            return toHexString(data).replace(" ", "")
        else:
            raise Exception(f"Error leyendo UID: SW1={sw1:02X} SW2={sw2:02X}")

    # ============================================================
    #                   NAVEGACIÓN REGISTROS
    # ============================================================

    def siguiente(self):
        if self.fila_actual < len(self.df) - 1:
            self.fila_actual += 1
            self.actualizar_texto()
        else:
            messagebox.showinfo("Fin", "No quedan más registros.")

    def anterior(self):
        if self.fila_actual > 0:
            self.fila_actual -= 1
            self.actualizar_texto()
        else:
            messagebox.showinfo("Aviso", "Ya estás en el primer registro.")

    def salir(self):
        self.root.destroy()

    # ============================================================
    #                       MENÚ AYUDA
    # ============================================================

    def mostrar_acerca_de(self):
        self._sincronizar_root()        
        messagebox.showinfo("Acerca de",
            "Grabador de tarjetas NFC\n"
            "Desarrollado por Luis Miguel Ramos Bersabé\n"
            "Versión 1.0\nMarzo 2026")

    def mostrar_manual(self):
        self._sincronizar_root()
        messagebox.showinfo("Manual rápido",
            "Seleccione Lectura o Escritura\n"
            "___________________________________________\n"
            "Lectura\n"
            "___________________________________________\n"
            "1. Acerque la tarjeta al lector\n"
            "2. Pulse 'Leer'\n"
            "___________________________________________\n"
            "Escritura\n"
            "___________________________________________\n"
            "1. Seleccione tipo de NTAG\n"
            "2. Seleccione archivo Excel\n"
            "3. Seleccione el registro que quiera grabar\n"
            "4. Revise el registro que quiere grabar\n"
            "5. Pulse 'Grabar tarjeta' para cada una")

    def mostrar_info_ntag(self):
        self._sincronizar_root()
        messagebox.showinfo("Información sobre NTAGs",
            "Capacidades en bytes de las distintas tarjetas\n"
            "_______________________________________________\n"
            "NTAG213: 144 bytes\n"
            "NTAG215: 504 bytes\n"
            "NTAG216: 888 bytes")

    def abrir_bloqueo(self):
        self._sincronizar_root()
        try:
            confirmar_bloqueo()
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo bloquear el NTAG:\n{e}")

    def _sincronizar_root(self):
        """Mueve root a la posición de la ventana activa."""
        ventana_activa = None
        for attr in ["win", "win_lectura", "win_excel"]:
            v = getattr(self, attr, None)
            if v and v.winfo_exists():
                ventana_activa = v
                break
        if ventana_activa:
            ventana_activa.update_idletasks()
            x = ventana_activa.winfo_x()
            y = ventana_activa.winfo_y()
            self.root.geometry(f"+{x}+{y}")

    def _colocar_en_pantalla_actual(self, ventana):
        """Coloca una ventana Toplevel recién creada donde está root."""
        self.root.update_idletasks()
        x = self.root.winfo_x() + 20
        y = max(30, self.root.winfo_y())
        ventana.geometry(f"+{x}+{y}")


if __name__ == "__main__":
    root = tk.Tk()
    app = AppNFC(root)
    root.mainloop()
