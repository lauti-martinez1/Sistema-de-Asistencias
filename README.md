# Sistema de acceso hospitalario (reconocimiento facial)

Aplicación de escritorio para control de acceso del personal médico.
Usa la cámara web, compara rostros con las fotos de la carpeta `Empleados`
y guarda ingresos en `registro.csv`.

Archivo principal: `App_acceso_hospital.py`

---

## Qué hay que hacer ANTES de ejecutar el código

Estas librerías no vienen con Python. Si no las instalás, el programa no arranca.

### 1. Instalar Python 3.10 o 3.11

`face_recognition` (y `dlib`) fallan con frecuencia en Python 3.12, 3.13 o 3.14.

- Descargá Python 3.10 u 3.11 desde [python.org](https://www.python.org/downloads/).
- En el instalador de Windows, marcá **Add Python to PATH**.
- Dejá marcado Tcl/Tk (viene por defecto). Lo usa la interfaz.

Comprobá la versión:

```bash
python --version
```

### 2. Herramientas para instalar `dlib` (Windows)

`face_recognition` depende de `dlib`. En Windows suele hacer falta compilarlo.

Instalá:

1. **CMake**  
   https://cmake.org/download/  
   En el instalador, agregalo al PATH.

2. **Visual Studio Build Tools** (compilador C++)  
   https://visualstudio.microsoft.com/visual-cpp-build-tools/  
   En el instalador, marcá **Desktop development with C++**.

Sin esto, `pip install dlib` suele terminar en error.

### 3. Crear un entorno virtual (recomendado)

Abrí una terminal **en la carpeta del proyecto** (`Sistema de Asistencias`, la que contiene `App_acceso_hospital.py`):

```bash
python -m venv venv
```

Activarlo:

- PowerShell:
  ```bash
  .\venv\Scripts\Activate.ps1
  ```
- CMD:
  ```bash
  venv\Scripts\activate.bat
  ```

Si PowerShell bloquea el script, ejecutá una vez:

```bash
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### 4. Instalar las librerías

Con el entorno virtual **activado**:

```bash
python -m pip install --upgrade pip
pip install cmake
pip install dlib
pip install face-recognition opencv-python numpy pillow
```

Si `dlib` falla, revisá el paso 2 (CMake + Build Tools) y que estés en Python 3.10/3.11.

Librerías que usa el programa:

| Paquete              | Para qué sirve                          |
|----------------------|-----------------------------------------|
| `opencv-python`      | Cámara y procesamiento de imagen        |
| `numpy`              | Arrays de las imágenes                  |
| `face-recognition`   | Detectar y comparar caras (usa `dlib`)  |
| `pillow`             | Mostrar fotos en la interfaz            |
| `tkinter`            | Interfaz (viene con Python en Windows)  |

### 5. Cámara web

Para **Control de acceso** y **Agregar desde cámara** hace falta una webcam.

- Conectala antes de abrir el programa.
- Si Windows pide permiso para la cámara, aceptalo.
- Cerrá Zoom, Teams, Discord u otra app que esté usando la cámara.
- El programa abre la cámara `0` (la predeterminada).

### 6. Carpeta de personal y registro

Tiene que existir (el programa la crea si falta):

- `Empleados/` — una foto por persona (`.jpg`, `.jpeg` o `.png`).
- `registro.csv` — se crea solo al registrar el primer ingreso.

Nombre del archivo = nombre de la persona. El `_` se muestra como espacio:

- `Ana_Garcia.jpg` → Ana Garcia

La foto tiene que mostrar **una cara clara**. Si no hay rostro, esa persona no entra a la base.

Ya hay fotos de ejemplo en `Empleados`. Podés usarlas para probar. También hay `FotoA.jpg`, `FotoB.jpg` y `FotoC.jpg` para la pestaña de comparación.

No abras `registro.csv` en Excel mientras corre el programa: Windows bloquea el archivo y no se puede escribir.

---

## Cómo ejecutar

En la carpeta del `.py`, con el entorno virtual activado:

```bash
python App_acceso_hospital.py
```

Debería abrirse la ventana **Hospital Central** con las pestañas:

1. Control de acceso  
2. Personal autorizado  
3. Comparar imágenes  
4. Registro de ingresos  

---

## Si algo falla

| Problema | Qué probar |
|----------|------------|
| `No module named 'cv2'` / `face_recognition` / `PIL` | El venv no está activado, o faltan los `pip install`. |
| Error al instalar `dlib` | Python 3.10/3.11, CMake en el PATH, Build Tools con C++. |
| `No se pudo abrir la cámara web` | Cámara conectada, permisos de Windows, ninguna otra app usándola. |
| `No se detectó ninguna cara` | Mejor luz, cara de frente, foto más nítida. |
| No se escribe el CSV | Cerrar Excel / LibreOffice si tenés `registro.csv` abierto. |

---

## Qué no hace falta

No hace falta copiar la carpeta `venv` de otra computadora. Cada uno crea la suya e instala las librerías.

No hace falta internet después de instalar los paquetes, salvo para bajar dependencias.
