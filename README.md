# Lector Grabador NFC

Aplicación de escritorio para Windows que permite **leer y grabar tarjetas NFC (NTAG213/215/216)** a partir de los datos de un archivo Excel, mediante un lector/escritor NFC conectado por USB.

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Platform](https://img.shields.io/badge/platform-Windows-lightgrey)
![License](https://img.shields.io/badge/license-MIT-yellow)

---

## Características

- Lectura del contenido NDEF almacenado en una tarjeta NFC y visualización en formato de tabla.
- Escritura en tarjetas NTAG a partir de los registros de un archivo Excel de datos.
- Indicador de tamaño (bytes) de los datos frente a la capacidad de la tarjeta, con aviso visual si el registro no cabe.
- Detección automática de si una tarjeta es **nueva** o **ya ha sido grabada** previamente con la aplicación (mediante un índice interno).
- Navegación entre registros del Excel (anterior / siguiente / ir a un registro concreto).
- Opción de grabar o no los encabezados de campos vacíos.
- Bloqueo permanente de una tarjeta NTAG (solo lectura), para casos muy específicos, ya que la propia aplicación protege la escritura con contraseña.
- Menú de ayuda con manual rápido e información sobre capacidades de las tarjetas NTAG.

## Requisitos

- Windows
- Python 3.9+ (si se ejecuta desde código fuente)
- Un lector/escritor NFC de escritorio compatible con **PC/SC**, conectado por USB
- Tarjetas NFC compatibles: **NTAG213**, **NTAG215** o **NTAG216**
- Driver PC/SC del lector instalado en el equipo

### Dependencias Python

```
pandas>=2.0.0
openpyxl>=3.1.0
pyscard>=2.0.7
```

Instalación:

```bash
pip install -r requirements.txt
```

## Estructura del proyecto

```
Lector_grabador_NFC/
├── app_gui.py              # Punto de entrada, interfaz gráfica (tkinter)
├── leer_excel.py           # Formateo de registros del Excel al formato NDEF
├── nfc_reader_apdu.py      # Lectura de tarjetas NFC vía comandos APDU
├── nfc_writer_apdu.py      # Escritura de tarjetas NFC vía comandos APDU
├── bloquear_ntag.py        # Bloqueo permanente de una tarjeta NTAG
├── datos/
│   ├── icono.ico / icono.png
│   ├── indice.xlsx         # Índice UID → archivo Excel de origen (se genera automáticamente)
│   └── ultimo_archivo.txt  # Recuerda el último Excel de datos utilizado
└── requirements.txt
```

## Formato del archivo Excel de datos

- En la **primera fila** van los encabezados o títulos de cada campo.
- A partir de la **segunda fila**, cada registro es el grupo de datos que se grabará en una tarjeta.
- El encabezado de la **primera columna** debe ser siempre `UID`, y ese campo debe dejarse en blanco en los registros: la aplicación lo rellena automáticamente al grabar la tarjeta, para vincular el registro con la tarjeta física.
- Si uno de los campos a introducir es una URL, la última columna debe tener el encabezado `URL`.
- El número de columnas no está limitado, pero sí el contenido total de todos los campos, ya que debe caber en la memoria de la tarjeta (por ejemplo, 504 bytes para NTAG215).
- El archivo Excel debe permanecer **cerrado** mientras se usa la aplicación.

## Uso

Al ejecutar la aplicación se muestra un menú principal con 4 opciones:

### Lectura

1. Acercar al lector una tarjeta con contenido.
2. Pulsar **Leer**: se muestra el contenido en formato de tabla.
   - Si la tarjeta no fue grabada con esta aplicación, aparecerá un aviso de "No encontrado" (no está registrada en el índice interno), pero igualmente se mostrará el contenido físico de la tarjeta.
3. **Volver** regresa al menú principal, **Salir** cierra la aplicación.

### Escritura

1. Seleccionar el **tipo de NTAG** (por defecto NTAG215).
2. Seleccionar el **archivo Excel** con los datos (por defecto, el último utilizado).
3. Indicar el **registro inicial** desde el que empezar (por defecto 1).
4. Pulsar **Iniciar proceso** para abrir la ventana de grabación, que muestra:
   - El contenido del registro actual.
   - El **tamaño** en bytes frente a la capacidad de la tarjeta (verde si cabe, rojo si excede la capacidad).
   - El número de **registro x de y**.
   - La opción de grabar o no los encabezados de campos vacíos.
   - Si la tarjeta es **nueva** (verde) o **ya existente** (rojo, con su UID).
   - Botones para moverse entre registros (**Registro anterior / siguiente / ir al registro**).
   - **Grabar tarjeta**: graba los datos del registro actual en la tarjeta y avanza automáticamente al siguiente registro.
   - **Cambiar archivo Excel** y **Volver al Menú Principal**.

### Bloquear NTAG

Bloquea permanentemente una tarjeta para escritura, desde cualquier dispositivo (a partir de ese momento solo podrá leerse). La propia aplicación ya protege por contraseña la escritura de las tarjetas que graba, por lo que esta opción está pensada solo para casos muy específicos.

### Salir

Cierra la aplicación.

## Compilar como ejecutable (.exe)

El proyecto se compila con [PyInstaller](https://pyinstaller.org/):

```bash
python -m PyInstaller --onefile --windowed --icon=datos\icono.ico --add-data "datos;datos" ^
  --hidden-import=bloquear_ntag ^
  --hidden-import=leer_excel ^
  --hidden-import=nfc_reader_apdu ^
  --hidden-import=pandas ^
  --hidden-import=openpyxl ^
  --hidden-import=nfc_writer_apdu ^
  app_gui.py
```

El ejecutable resultante se genera en la carpeta `dist/`.

## Autor

Luis Miguel Ramos Bersabé

## 📝 Licencia

[MIT](LICENSE)
