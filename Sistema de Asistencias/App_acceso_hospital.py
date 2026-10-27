"""
Sistema de control de acceso para personal médico mediante reconocimiento facial
-------------------------------------------------------------------------------
Interfaz de escritorio (Tkinter) que integra:
  - Control de acceso en tiempo real con cámara web   (antes: Programa_asistencia.py)
  - Comparación de dos imágenes                        (antes: reconocimiento_facial.py)
  - Gestión del personal autorizado (carpeta Empleados)
  - Consulta del registro de ingresos (registro.csv)

Uso:  python App_acceso_hospital.py
"""

import csv
import os
import re
import sys
import time
import unicodedata
from datetime import datetime

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

import cv2
import numpy as np
import face_recognition as fr
from PIL import Image, ImageDraw, ImageTk

# ----------------------------- Configuración -----------------------------
NOMBRE_HOSPITAL = "Hospital Central"

BASE = os.path.dirname(os.path.abspath(__file__))
RUTA = os.path.join(BASE, "Empleados")           # Una foto por persona: Nombre_Apellido.jpg
ARCHIVO_REGISTRO = os.path.join(BASE, "registro.csv")
EXTENSIONES = (".jpg", ".jpeg", ".png")

# Caché: guarda el código facial de cada foto ya analizada, así al agregar
# a una persona nueva solo se analiza SU foto y no la de todo el personal.
# Clave: (ruta, fecha de modificación del archivo) -> código facial
CACHE_CODIGOS = {}
LADO_CODIFICAR = 600          # Las fotos se reducen a este tamaño para analizarlas (más rápido)

UMBRAL = 0.6                  # Distancia máxima para aceptar una coincidencia
ESCALA = 0.5                  # Se reconoce sobre una imagen reducida (más rápido)
CADA_N_FRAMES = 3             # Se analiza 1 de cada N cuadros
FRAMES_CONFIRMACION = 3       # Detecciones seguidas para confirmar a una persona
ESPERA_PERMITIDO = 60         # Segundos antes de volver a registrar a la misma persona
ESPERA_DENEGADO = 10          # Segundos antes de volver a registrar un desconocido

ESTADO_OK = "ACCESO PERMITIDO"
ESTADO_NO = "ACCESO DENEGADO"

# Colores de la interfaz
AZUL = "#0b5c8a"
FONDO = "#f3f7fa"
VERDE = "#1e9e5a"
ROJO = "#d64545"
NEUTRO = "#dfe8ee"
TEXTO = "#1c2b36"


# ----------------------------- Utilidades -----------------------------
def sin_tildes(texto):
    """cv2.putText no dibuja tildes ni ñ: se las quitamos solo para dibujar."""
    return "".join(c for c in unicodedata.normalize("NFD", texto)
                   if unicodedata.category(c) != "Mn")


def leer_imagen(ruta):
    """Lee una imagen en BGR. Funciona aunque la ruta tenga tildes (cv2.imread falla en Windows)."""
    try:
        datos = np.fromfile(ruta, dtype=np.uint8)
        return cv2.imdecode(datos, cv2.IMREAD_COLOR)
    except Exception:
        return None


def guardar_imagen(ruta, imagen):
    ok, buf = cv2.imencode(".jpg", imagen)
    if ok:
        buf.tofile(ruta)
    return ok


def achicar(imagen, lado_max=1000):
    alto, ancho = imagen.shape[:2]
    mayor = max(alto, ancho)
    if mayor <= lado_max:
        return imagen
    f = lado_max / mayor
    return cv2.resize(imagen, (int(ancho * f), int(alto * f)))


def cargar_base():
    """Lee la carpeta Empleados y codifica una cara por foto (reusa lo ya calculado)."""
    os.makedirs(RUTA, exist_ok=True)
    codificadas, nombres, rutas, avisos = [], [], [], []
    for archivo in sorted(os.listdir(RUTA)):
        if not archivo.lower().endswith(EXTENSIONES):
            continue
        ruta = os.path.join(RUTA, archivo)
        nombre = os.path.splitext(archivo)[0].replace("_", " ")
        clave = (ruta, os.path.getmtime(ruta))

        if clave in CACHE_CODIGOS:                      # esta foto ya estaba analizada
            codigo = CACHE_CODIGOS[clave]
        else:
            imagen = leer_imagen(ruta)
            if imagen is None:
                avisos.append(f"{archivo}: no se pudo leer la imagen")
                continue
            rgb = cv2.cvtColor(achicar(imagen, LADO_CODIFICAR), cv2.COLOR_BGR2RGB)   # OpenCV lee en BGR
            codigos = fr.face_encodings(rgb)
            if not codigos:
                avisos.append(f"{archivo}: no se detectó ninguna cara")
                continue
            codigo = codigos[0]
            CACHE_CODIGOS[clave] = codigo

        codificadas.append(codigo)
        nombres.append(nombre)
        rutas.append(ruta)
    return codificadas, nombres, rutas, avisos


def registrar_ingreso(persona, estado):
    """Agrega una fila al CSV. Devuelve False si el archivo está bloqueado (ej. abierto en Excel)."""
    ahora = datetime.now()
    nuevo = not os.path.exists(ARCHIVO_REGISTRO) or os.path.getsize(ARCHIVO_REGISTRO) == 0
    try:
        with open(ARCHIVO_REGISTRO, "a", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            if nuevo:
                w.writerow(["nombre", "fecha", "hora", "estado"])
            w.writerow([persona, ahora.strftime("%Y-%m-%d"), ahora.strftime("%H:%M:%S"), estado])
        return True
    except PermissionError:
        return False


def leer_registro():
    if not os.path.exists(ARCHIVO_REGISTRO):
        return []
    with open(ARCHIVO_REGISTRO, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


# ----------------------------- Aplicación -----------------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{NOMBRE_HOSPITAL} — Control de acceso del personal médico")
        self.geometry("1180x740")
        self.minsize(1050, 680)
        self.configure(bg=FONDO)

        # Estado interno
        self.cap = None
        self.after_id = None
        self.frame_n = 0
        self.resultados = []          # [(caja, nombre|None, distancia)]
        self.contadores = {}
        self.ultimo_registro = {}
        self.ultimo_frame = None

        # Variables para la ventana de captura de personal
        self.ventana_captura = None
        self.foto_after_id = None
        self.foto_cap = None
        self.foto_usa_camara_principal = False
        self.foto_frame_actual = None
        self.foto_captura = None
        self.lbl_vista_captura = None
        self.lbl_instrucciones_captura = None
        self.btn_tomar_foto = None
        self.btn_aceptar_foto = None
        self.btn_repetir_foto = None

        self.estado_hasta = 0
        self.codificadas, self.nombres, self.rutas = [], [], []
        self.comp = {"A": None, "B": None}
        self.var_auto = tk.BooleanVar(value=True)

        self._estilos()
        self._cabecera()
        self._pestanas()
        self.recargar_base()
        self.cargar_registro()
        self._reloj()
        self.protocol("WM_DELETE_WINDOW", self.cerrar)

    # ------------------------- Construcción de la UI -------------------------
    def _estilos(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("TNotebook", background=FONDO, borderwidth=0)
        s.configure("TNotebook.Tab", padding=(18, 8), font=("Segoe UI", 10, "bold"))
        s.configure("TFrame", background=FONDO)
        s.configure("TLabel", background=FONDO, foreground=TEXTO, font=("Segoe UI", 10))
        s.configure("TCheckbutton", background=FONDO, foreground=TEXTO, font=("Segoe UI", 10))
        s.configure("TButton", font=("Segoe UI", 10), padding=6)
        s.configure("Accent.TButton", font=("Segoe UI", 10, "bold"),
                    background=AZUL, foreground="white", padding=8)
        s.map("Accent.TButton", background=[("active", "#094a70")])
        s.configure("Treeview", rowheight=26, font=("Segoe UI", 10))
        s.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))

    def _cabecera(self):
        barra = tk.Frame(self, bg=AZUL, height=64)
        barra.pack(fill="x")
        barra.pack_propagate(False)
        tk.Label(barra, text="✚", bg=AZUL, fg="white",
                 font=("Segoe UI", 26, "bold")).pack(side="left", padx=(18, 8))
        caja = tk.Frame(barra, bg=AZUL)
        caja.pack(side="left")
        tk.Label(caja, text=NOMBRE_HOSPITAL, bg=AZUL, fg="white",
                 font=("Segoe UI", 15, "bold")).pack(anchor="w")
        tk.Label(caja, text="Control de acceso del personal médico", bg=AZUL, fg="#cfe6f5",
                 font=("Segoe UI", 10)).pack(anchor="w")
        self.lbl_reloj = tk.Label(barra, bg=AZUL, fg="white", font=("Segoe UI", 12))
        self.lbl_reloj.pack(side="right", padx=20)

    def _pestanas(self):
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=10, pady=10)
        tabs = {}
        for clave, titulo in [("acceso", "Control de acceso"), ("registro", "Registro de ingresos"),
                              ("personal", "Personal autorizado"), ("comparar", "Comparar imágenes")]:
            tabs[clave] = ttk.Frame(nb)
            nb.add(tabs[clave], text=titulo)
        self._tab_acceso(tabs["acceso"])
        self._tab_registro(tabs["registro"])
        self._tab_personal(tabs["personal"])
        self._tab_comparar(tabs["comparar"])

    # ---- Pestaña 1: control de acceso ----
    def _tab_acceso(self, tab):
        izq = ttk.Frame(tab)
        izq.pack(side="left", padx=12, pady=12, anchor="n")

        self.img_apagada = self._placeholder("Cámara apagada")
        self.lbl_video = tk.Label(izq, image=self.img_apagada, bg="#101820", bd=0)
        self.lbl_video.pack()

        der = ttk.Frame(tab)
        der.pack(side="left", fill="both", expand=True, padx=(4, 12), pady=12)

        # Tarjeta de estado
        self.card = tk.Frame(der, bg=NEUTRO, height=150)
        self.card.pack(fill="x")
        self.card.pack_propagate(False)
        self.lbl_estado = tk.Label(self.card, bg=NEUTRO, fg=TEXTO, font=("Segoe UI", 22, "bold"))
        self.lbl_estado.pack(expand=True, pady=(18, 0))
        self.lbl_detalle = tk.Label(self.card, bg=NEUTRO, fg=TEXTO, font=("Segoe UI", 12),
                                    wraplength=330)
        self.lbl_detalle.pack(expand=True, pady=(0, 18))
        self._estado_neutro()

        # Controles
        ctrl = ttk.Frame(der)
        ctrl.pack(fill="x", pady=12)
        self.btn_cam = ttk.Button(ctrl, text="▶  Iniciar cámara", style="Accent.TButton",
                                  command=self.alternar_camara)
        self.btn_cam.pack(fill="x")
        ttk.Checkbutton(ctrl, text="Registrar ingresos automáticamente",
                        variable=self.var_auto).pack(anchor="w", pady=(10, 4))
        ttk.Button(ctrl, text="Registrar ingreso manualmente",
                   command=self.registro_manual).pack(fill="x")

        # Últimos movimientos
        ttk.Label(der, text="Últimos movimientos",
                  font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(8, 4))
        cols = ("hora", "nombre", "estado")
        self.tree_recientes = ttk.Treeview(der, columns=cols, show="headings", height=8)
        for c, t, w in [("hora", "Hora", 70), ("nombre", "Nombre", 140), ("estado", "Estado", 130)]:
            self.tree_recientes.heading(c, text=t)
            self.tree_recientes.column(c, width=w, anchor="w")
        self.tree_recientes.tag_configure("ok", foreground=VERDE)
        self.tree_recientes.tag_configure("no", foreground=ROJO)
        self.tree_recientes.pack(fill="both", expand=True)

    # ---- Pestaña 2: registro ----
    def _tab_registro(self, tab):
        barra = ttk.Frame(tab)
        barra.pack(fill="x", padx=12, pady=(12, 6))
        ttk.Label(barra, text="Buscar por nombre:").pack(side="left")
        self.var_buscar = tk.StringVar()
        ttk.Entry(barra, textvariable=self.var_buscar, width=24).pack(side="left", padx=(6, 16))
        ttk.Label(barra, text="Estado:").pack(side="left")
        self.var_filtro = tk.StringVar(value="Todos")
        combo = ttk.Combobox(barra, textvariable=self.var_filtro, state="readonly", width=20,
                             values=["Todos", ESTADO_OK, ESTADO_NO])
        combo.pack(side="left", padx=6)
        ttk.Button(barra, text="Actualizar", command=self.cargar_registro).pack(side="left", padx=6)
        ttk.Button(barra, text="Abrir CSV", command=self.abrir_csv).pack(side="left")

        cols = ("nombre", "fecha", "hora", "estado")
        marco = ttk.Frame(tab)
        marco.pack(fill="both", expand=True, padx=12, pady=6)
        self.tree_registro = ttk.Treeview(marco, columns=cols, show="headings")
        for c, t, w in [("nombre", "Nombre", 280), ("fecha", "Fecha", 120),
                        ("hora", "Hora", 120), ("estado", "Estado", 200)]:
            self.tree_registro.heading(c, text=t)
            self.tree_registro.column(c, width=w, anchor="w")
        self.tree_registro.tag_configure("ok", foreground=VERDE)
        self.tree_registro.tag_configure("no", foreground=ROJO)
        sb = ttk.Scrollbar(marco, orient="vertical", command=self.tree_registro.yview)
        self.tree_registro.configure(yscrollcommand=sb.set)
        self.tree_registro.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        self.lbl_totales = ttk.Label(tab, text="", font=("Segoe UI", 10, "bold"))
        self.lbl_totales.pack(anchor="w", padx=12, pady=(0, 10))

        self.var_buscar.trace_add("write", lambda *a: self.cargar_registro())
        combo.bind("<<ComboboxSelected>>", lambda e: self.cargar_registro())

    # ---- Pestaña 3: personal ----
    def _tab_personal(self, tab):
        izq = ttk.Frame(tab)
        izq.pack(side="left", fill="y", padx=12, pady=12)
        self.lbl_cant = ttk.Label(izq, text="", font=("Segoe UI", 11, "bold"))
        self.lbl_cant.pack(anchor="w", pady=(0, 6))
        self.lista = tk.Listbox(izq, width=34, height=22, font=("Segoe UI", 11),
                                activestyle="none", selectbackground=AZUL, exportselection=False)
        self.lista.pack(fill="y", expand=True)
        self.lista.bind("<<ListboxSelect>>", self.mostrar_foto_personal)

        der = ttk.Frame(tab)
        der.pack(side="left", fill="both", expand=True, padx=12, pady=12)
        self.lbl_foto_personal = tk.Label(der, bg="#101820", width=44, height=18)
        self.lbl_foto_personal.pack(anchor="w")

        botones = ttk.Frame(der)
        botones.pack(anchor="w", pady=14)
        ttk.Button(botones, text="Agregar desde cámara", style="Accent.TButton",
                   command=self.agregar_desde_camara).grid(row=0, column=0, padx=(0, 8), pady=4)
        ttk.Button(botones, text="Agregar desde archivo",
                   command=self.agregar_desde_archivo).grid(row=0, column=1, padx=(0, 8), pady=4)
        ttk.Button(botones, text="Eliminar seleccionado",
                   command=self.eliminar_personal).grid(row=1, column=0, padx=(0, 8), pady=4)
        ttk.Button(botones, text="Recargar base",
                   command=self.recargar_base).grid(row=1, column=1, padx=(0, 8), pady=4)
        ttk.Label(der, text="«Agregar desde cámara» abre una vista previa propia, "
                            "no hace falta iniciar la cámara en «Control de acceso».",
                  wraplength=480).pack(anchor="w")

    # ---- Pestaña 4: comparar ----
    def _tab_comparar(self, tab):
        fila = ttk.Frame(tab)
        fila.pack(pady=14)
        self.lbl_comp = {}
        for col, (clave, titulo) in enumerate([("A", "Foto de control"), ("B", "Foto de prueba")]):
            marco = ttk.Frame(fila)
            marco.grid(row=0, column=col, padx=18)
            ttk.Button(marco, text=f"Elegir {titulo.lower()}",
                       command=lambda k=clave: self.elegir_foto(k)).pack(pady=(0, 8))
            self.lbl_comp[clave] = tk.Label(marco, bg="#101820", width=48, height=19)
            self.lbl_comp[clave].pack()

        ttk.Button(tab, text="Comparar rostros", style="Accent.TButton",
                   command=self.comparar).pack(pady=6)
        self.lbl_resultado = tk.Label(tab, text="", bg=FONDO, fg=TEXTO, font=("Segoe UI", 16, "bold"))
        self.lbl_resultado.pack(pady=8)

    # ------------------------- Utilidades de UI -------------------------
    def _placeholder(self, texto, tam=(640, 480)):
        img = Image.new("RGB", tam, "#101820")
        d = ImageDraw.Draw(img)
        d.text((tam[0] // 2 - 45, tam[1] // 2), texto, fill="#8aa0b0")
        return ImageTk.PhotoImage(img)

    def _reloj(self):
        self.lbl_reloj.config(text=datetime.now().strftime("%d/%m/%Y   %H:%M:%S"))
        self.after(1000, self._reloj)

    def _pintar_estado(self, titulo, detalle, fondo, fg):
        self.card.config(bg=fondo)
        self.lbl_estado.config(text=titulo, bg=fondo, fg=fg)
        self.lbl_detalle.config(text=detalle, bg=fondo, fg=fg)

    def _estado_neutro(self):
        self._pintar_estado("EN ESPERA", "Acercate a la cámara para registrar tu ingreso", NEUTRO, TEXTO)

    def mostrar_estado(self, titulo, detalle, color):
        self._pintar_estado(titulo, detalle, color, "white")
        self.estado_hasta = time.time() + 2.5

    def mostrar_en(self, label, imagen_bgr, max_size):
        rgb = cv2.cvtColor(imagen_bgr, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb)
        img.thumbnail(max_size)
        foto = ImageTk.PhotoImage(img)
        label.config(image=foto, width=foto.width(), height=foto.height())
        label.image = foto   # evita que Python borre la imagen

    # ------------------------- Cámara y reconocimiento -------------------------
    def alternar_camara(self):
        if self.cap:
            self.detener_camara()
        else:
            self.iniciar_camara()

    def iniciar_camara(self):
        if not self.codificadas:
            messagebox.showwarning("Sin personal",
                                   "No hay personal cargado. Agregá al menos una foto en la "
                                   "pestaña «Personal autorizado» (o en la carpeta Empleados).")
            return
        if sys.platform.startswith("win"):
            self.cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        else:
            self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            self.cap = None
            messagebox.showerror("Cámara", "No se pudo abrir la cámara web.")
            return
        self.frame_n = 0
        self.resultados = []
        self.contadores.clear()
        self.btn_cam.config(text="■  Detener cámara")
        self._bucle()

    def detener_camara(self):
        if self.after_id:
            self.after_cancel(self.after_id)
            self.after_id = None
        if self.cap:
            self.cap.release()
            self.cap = None
        self.resultados = []
        self.ultimo_frame = None
        self.lbl_video.config(image=self.img_apagada)
        self.lbl_video.image = self.img_apagada
        self.btn_cam.config(text="▶  Iniciar cámara")
        self._estado_neutro()

    def _bucle(self):
        if not self.cap:
            return
        ok, frame = self.cap.read()
        if ok:
            frame = cv2.flip(frame, 1)               # efecto espejo
            self.ultimo_frame = frame.copy()          # copia limpia (sin dibujos)

            if self.frame_n % CADA_N_FRAMES == 0:
                self.resultados = self.reconocer(frame)
                self.procesar_resultados()
            self.frame_n += 1

            if self.estado_hasta and time.time() > self.estado_hasta:
                self.estado_hasta = 0
                self._estado_neutro()

            self._dibujar(frame)
            self.mostrar_en(self.lbl_video, frame, (640, 480))
        self.after_id = self.after(10, self._bucle)

    def reconocer(self, frame):
        """Devuelve [(caja, nombre o None, distancia)] para cada cara del cuadro."""
        chico = cv2.resize(frame, (0, 0), fx=ESCALA, fy=ESCALA)
        rgb = cv2.cvtColor(chico, cv2.COLOR_BGR2RGB)
        ubicaciones = fr.face_locations(rgb)
        codigos = fr.face_encodings(rgb, ubicaciones)
        resultados = []
        for codigo, (top, right, bottom, left) in zip(codigos, ubicaciones):
            distancias = fr.face_distance(self.codificadas, codigo)
            i = int(np.argmin(distancias))
            nombre = self.nombres[i] if distancias[i] <= UMBRAL else None
            k = 1 / ESCALA
            caja = (int(top * k), int(right * k), int(bottom * k), int(left * k))
            resultados.append((caja, nombre, float(distancias[i])))
        return resultados

    def _dibujar(self, frame):
        for (top, right, bottom, left), nombre, _ in self.resultados:
            color = (90, 158, 30) if nombre else (69, 69, 214)      # BGR
            etiqueta = sin_tildes(nombre) if nombre else "DENEGADO"
            cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
            cv2.rectangle(frame, (left, bottom - 32), (right, bottom), color, cv2.FILLED)
            cv2.putText(frame, etiqueta, (left + 6, bottom - 9),
                        cv2.FONT_HERSHEY_DUPLEX, 0.65, (255, 255, 255), 1)

    def procesar_resultados(self):
        """Confirma a cada persona tras varias detecciones seguidas y la registra."""
        if not self.resultados:
            self.contadores.clear()
            return
        vistos = set()
        for _, nombre, _ in self.resultados:
            clave = nombre or "Desconocido"
            vistos.add(clave)
            self.contadores[clave] = self.contadores.get(clave, 0) + 1
            if self.contadores[clave] >= FRAMES_CONFIRMACION and self.var_auto.get():
                self.intentar_registro(clave, nombre is not None)
        for clave in list(self.contadores):
            if clave not in vistos:
                del self.contadores[clave]

    def intentar_registro(self, clave, permitido, forzar=False):
        espera = ESPERA_PERMITIDO if permitido else ESPERA_DENEGADO
        ahora = time.time()
        titulo = ESTADO_OK if permitido else ESTADO_NO
        color = VERDE if permitido else ROJO

        if not forzar and ahora - self.ultimo_registro.get(clave, 0) < espera:
            detalle = f"{clave}\nIngreso ya registrado" if permitido else "Persona no registrada"
            self.mostrar_estado(titulo, detalle, color)
            return

        if registrar_ingreso(clave, titulo):
            self.ultimo_registro[clave] = ahora
            hora = datetime.now().strftime("%H:%M:%S")
            self.tree_recientes.insert("", 0, values=(hora, clave, titulo),
                                       tags=("ok" if permitido else "no",))
            detalle = f"Bienvenido/a\n{clave}" if permitido else "Persona no registrada en el sistema"
            self.mostrar_estado(titulo, detalle, color)
            self.cargar_registro()
        else:
            self.mostrar_estado("ERROR", "No se pudo escribir registro.csv.\n¿Está abierto en Excel?", "#8a6d1c")

    def registro_manual(self):
        if not self.cap or not self.resultados:
            messagebox.showinfo("Registro manual", "No hay ningún rostro detectado en la cámara.")
            return
        for _, nombre, _ in self.resultados:
            self.intentar_registro(nombre or "Desconocido", nombre is not None, forzar=True)

    # ------------------------- Registro de ingresos -------------------------
    def cargar_registro(self):
        filas = leer_registro()
        texto = self.var_buscar.get().strip().lower()
        filtro = self.var_filtro.get()
        for item in self.tree_registro.get_children():
            self.tree_registro.delete(item)
        permitidos = denegados = 0
        for fila in reversed(filas):                    # más recientes primero
            estado = fila.get("estado", "")
            nombre = fila.get("nombre", "")
            if filtro != "Todos" and estado != filtro:
                continue
            if texto and texto not in nombre.lower():
                continue
            ok = estado == ESTADO_OK
            permitidos += ok
            denegados += not ok
            self.tree_registro.insert("", "end",
                                      values=(nombre, fila.get("fecha", ""), fila.get("hora", ""), estado),
                                      tags=("ok" if ok else "no",))
        self.lbl_totales.config(
            text=f"Mostrando {permitidos + denegados} registros  |  "
                 f"Permitidos: {permitidos}  |  Denegados: {denegados}")

    def abrir_csv(self):
        if not os.path.exists(ARCHIVO_REGISTRO):
            messagebox.showinfo("Registro", "Todavía no hay ingresos registrados.")
            return
        try:
            os.startfile(ARCHIVO_REGISTRO)
        except AttributeError:
            messagebox.showinfo("Registro", f"El archivo está en:\n{ARCHIVO_REGISTRO}")

    # ------------------------- Personal autorizado -------------------------
    def recargar_base(self):
        self.config(cursor="watch")
        self.update_idletasks()
        self.codificadas, self.nombres, self.rutas, avisos = cargar_base()
        self.config(cursor="")
        self.lista.delete(0, "end")
        for n in self.nombres:
            self.lista.insert("end", n)
        self.lbl_cant.config(text=f"Personal autorizado: {len(self.nombres)}")
        self.lbl_foto_personal.config(image="", width=44, height=18)
        if avisos:
            messagebox.showwarning("Fotos omitidas", "Estas fotos no se cargaron:\n\n" + "\n".join(avisos))

    def mostrar_foto_personal(self, _evento=None):
        sel = self.lista.curselection()
        if not sel:
            return
        img = leer_imagen(self.rutas[sel[0]])
        if img is not None:
            self.mostrar_en(self.lbl_foto_personal, img, (420, 320))

    def _guardar_nuevo(self, imagen_bgr):
        self.config(cursor="watch")
        self.update_idletasks()
        rgb = cv2.cvtColor(achicar(imagen_bgr, LADO_CODIFICAR), cv2.COLOR_BGR2RGB)
        caras = fr.face_locations(rgb)
        self.config(cursor="")
        if len(caras) == 0:
            messagebox.showerror("Sin rostro", "No se detectó ninguna cara en la imagen.")
            return
        if len(caras) > 1:
            messagebox.showerror("Varios rostros", "La foto debe tener una sola persona.")
            return
        nombre = simpledialog.askstring("Nuevo personal", "Nombre y apellido:", parent=self)
        if not nombre or not nombre.strip():
            return
        archivo = re.sub(r"[^\w\- ]", "", nombre.strip()).replace(" ", "_")
        if not archivo:
            messagebox.showerror("Nombre inválido", "El nombre tiene caracteres no permitidos.")
            return
        ruta = os.path.join(RUTA, archivo + ".jpg")
        if os.path.exists(ruta) and not messagebox.askyesno(
                "Ya existe", "Ya hay una foto con ese nombre. ¿Reemplazarla?"):
            return
        guardar_imagen(ruta, achicar(imagen_bgr))
        self.recargar_base()        # gracias a la caché, solo analiza la foto nueva

    def agregar_desde_camara(self):
        """Abre una vista previa en vivo y permite elegir cuándo capturar la foto."""
        if self.ventana_captura is not None:
            try:
                if self.ventana_captura.winfo_exists():
                    self.ventana_captura.lift()
                    self.ventana_captura.focus_force()
                    return
            except tk.TclError:
                self.ventana_captura = None

        # Si Control de acceso ya está usando la cámara, reutilizamos sus cuadros.
        # Así evitamos intentar abrir el mismo dispositivo dos veces.
        self.foto_usa_camara_principal = bool(
            self.cap is not None and self.cap.isOpened()
        )
        self.foto_cap = None

        if not self.foto_usa_camara_principal:
            if sys.platform.startswith("win"):
                self.foto_cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
            else:
                self.foto_cap = cv2.VideoCapture(0)

            if not self.foto_cap.isOpened():
                self.foto_cap.release()
                self.foto_cap = None
                messagebox.showerror(
                    "Cámara",
                    "No se pudo abrir la cámara web. Comprueba que esté conectada "
                    "y que ninguna otra aplicación la esté usando."
                )
                return

        self.foto_frame_actual = None
        self.foto_captura = None

        ventana = tk.Toplevel(self)
        self.ventana_captura = ventana
        ventana.title("Agregar personal — Vista previa de cámara")
        ventana.transient(self)
        ventana.resizable(False, False)
        ventana.protocol("WM_DELETE_WINDOW", self._cerrar_ventana_captura)

        contenedor = ttk.Frame(ventana, padding=12)
        contenedor.pack(fill="both", expand=True)

        placeholder = self._placeholder("Iniciando cámara...", (800, 600))
        self.lbl_vista_captura = tk.Label(
            contenedor, image=placeholder, bg="#101820", bd=0
        )
        self.lbl_vista_captura.image = placeholder
        self.lbl_vista_captura.pack(pady=(0, 10))

        self.lbl_instrucciones_captura = ttk.Label(
            contenedor,
            text="Ubícate frente a la cámara. Cuando estés listo, pulsa «Tomar foto».",
            anchor="center",
            justify="center"
        )
        self.lbl_instrucciones_captura.pack(fill="x", pady=(0, 10))

        botones = ttk.Frame(contenedor)
        botones.pack()

        self.btn_tomar_foto = ttk.Button(
            botones, text="Tomar foto", style="Accent.TButton",
            command=self._capturar_foto_personal
        )
        self.btn_tomar_foto.pack(side="left", padx=4)

        self.btn_aceptar_foto = ttk.Button(
            botones, text="Usar esta foto", style="Accent.TButton",
            command=self._confirmar_foto_personal
        )

        self.btn_repetir_foto = ttk.Button(
            botones, text="Volver a tomar", command=self._repetir_foto_personal
        )

        ttk.Button(
            botones, text="Cancelar", command=self._cerrar_ventana_captura
        ).pack(side="left", padx=4)

        ventana.update_idletasks()
        ventana.grab_set()
        self._actualizar_vista_captura()

    def _actualizar_vista_captura(self):
        """Actualiza la vista previa mientras todavía no se tomó una foto."""
        ventana = self.ventana_captura
        if ventana is None:
            return
        try:
            if not ventana.winfo_exists():
                return
        except tk.TclError:
            return

        # Una vez capturada la imagen, se congela la vista para poder revisarla.
        if self.foto_captura is not None:
            self.foto_after_id = None
            return

        frame = None
        if self.foto_usa_camara_principal:
            if self.ultimo_frame is not None:
                frame = self.ultimo_frame.copy()
        elif self.foto_cap is not None:
            ok, frame = self.foto_cap.read()
            if ok:
                frame = cv2.flip(frame, 1)  # Vista tipo espejo
            else:
                frame = None

        if frame is not None:
            self.foto_frame_actual = frame.copy()
            self.mostrar_en(self.lbl_vista_captura, frame, (800, 600))

        self.foto_after_id = ventana.after(20, self._actualizar_vista_captura)

    def _capturar_foto_personal(self):
        if self.foto_frame_actual is None:
            messagebox.showinfo(
                "Cámara", "Todavía no hay imagen disponible. Espera un momento e inténtalo de nuevo.",
                parent=self.ventana_captura
            )
            return

        self.foto_captura = self.foto_frame_actual.copy()
        self.mostrar_en(self.lbl_vista_captura, self.foto_captura, (800, 600))
        self.lbl_instrucciones_captura.config(
            text="Revisa la foto. Si te gusta, pulsa «Usar esta foto»; también puedes repetirla."
        )
        self.btn_tomar_foto.pack_forget()
        self.btn_aceptar_foto.pack(side="left", padx=4)
        self.btn_repetir_foto.pack(side="left", padx=4)

    def _repetir_foto_personal(self):
        self.foto_captura = None
        self.lbl_instrucciones_captura.config(
            text="Ubícate frente a la cámara. Cuando estés listo, pulsa «Tomar foto»."
        )
        self.btn_aceptar_foto.pack_forget()
        self.btn_repetir_foto.pack_forget()
        self.btn_tomar_foto.pack(side="left", padx=4)
        if self.foto_after_id is None and self.ventana_captura is not None:
            self.foto_after_id = self.ventana_captura.after(
                20, self._actualizar_vista_captura
            )

    def _confirmar_foto_personal(self):
        if self.foto_captura is None:
            return
        imagen = self.foto_captura.copy()
        self._cerrar_ventana_captura()
        self._guardar_nuevo(imagen)

    def _cerrar_ventana_captura(self):
        """Cierra la vista previa y libera solo la cámara que abrió esta ventana."""
        ventana = self.ventana_captura
        if self.foto_after_id is not None and ventana is not None:
            try:
                ventana.after_cancel(self.foto_after_id)
            except tk.TclError:
                pass
        self.foto_after_id = None

        if self.foto_cap is not None:
            self.foto_cap.release()
            self.foto_cap = None

        if ventana is not None:
            try:
                if ventana.winfo_exists():
                    try:
                        ventana.grab_release()
                    except tk.TclError:
                        pass
                    ventana.destroy()
            except tk.TclError:
                pass

        self.ventana_captura = None
        self.foto_usa_camara_principal = False
        self.foto_frame_actual = None
        self.foto_captura = None
        self.lbl_vista_captura = None
        self.lbl_instrucciones_captura = None
        self.btn_tomar_foto = None
        self.btn_aceptar_foto = None
        self.btn_repetir_foto = None

    def agregar_desde_archivo(self):
        ruta = filedialog.askopenfilename(title="Elegir foto",
                                          filetypes=[("Imágenes", "*.jpg *.jpeg *.png")])
        if not ruta:
            return
        img = leer_imagen(ruta)
        if img is None:
            messagebox.showerror("Error", "No se pudo leer la imagen.")
            return
        self._guardar_nuevo(img)

    def eliminar_personal(self):
        sel = self.lista.curselection()
        if not sel:
            messagebox.showinfo("Eliminar", "Elegí a una persona de la lista.")
            return
        nombre = self.nombres[sel[0]]
        if messagebox.askyesno("Eliminar", f"¿Quitar a {nombre} del personal autorizado?"):
            os.remove(self.rutas[sel[0]])
            self.recargar_base()

    # ------------------------- Comparar imágenes -------------------------
    def elegir_foto(self, clave):
        ruta = filedialog.askopenfilename(title="Elegir foto",
                                          filetypes=[("Imágenes", "*.jpg *.jpeg *.png")])
        if not ruta:
            return
        img = leer_imagen(ruta)
        if img is None:
            messagebox.showerror("Error", "No se pudo leer la imagen.")
            return
        self.comp[clave] = img
        self.mostrar_en(self.lbl_comp[clave], img, (440, 340))
        self.lbl_resultado.config(text="")

    def comparar(self):
        a, b = self.comp["A"], self.comp["B"]
        if a is None or b is None:
            messagebox.showinfo("Comparar", "Elegí las dos fotos primero.")
            return
        datos = []
        for nombre, img in (("de control", a), ("de prueba", b)):
            rgb = cv2.cvtColor(achicar(img), cv2.COLOR_BGR2RGB)
            ubic = fr.face_locations(rgb)
            if not ubic:
                messagebox.showerror("Sin rostro", f"No se detectó ninguna cara en la foto {nombre}.")
                return
            datos.append((achicar(img), ubic[0], fr.face_encodings(rgb, [ubic[0]])[0]))

        coinciden = bool(fr.compare_faces([datos[0][2]], datos[1][2], UMBRAL)[0])
        distancia = float(fr.face_distance([datos[0][2]], datos[1][2])[0])

        color = (90, 158, 30) if coinciden else (69, 69, 214)
        for clave, (img, (top, right, bottom, left), _) in zip(("A", "B"), datos):
            marcada = img.copy()
            cv2.rectangle(marcada, (left, top), (right, bottom), color, 3)
            self.mostrar_en(self.lbl_comp[clave], marcada, (440, 340))

        self.lbl_resultado.config(
            text=f"{'COINCIDEN' if coinciden else 'NO COINCIDEN'}   —   distancia: {distancia:.2f}",
            fg=VERDE if coinciden else ROJO)

    # ------------------------- Cierre -------------------------
    def cerrar(self):
        self._cerrar_ventana_captura()
        self.detener_camara()
        self.destroy()


if __name__ == "__main__":
    App().mainloop()