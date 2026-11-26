import ast
import contextlib
import importlib
import importlib.util
import inspect
import io
import linecache
import sys
import textwrap
import traceback
from collections import Counter
from datetime import date
from pathlib import Path
import pprint
import random
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter import font as tkfont

import matplotlib.pyplot as plt
from matplotlib import colormaps
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.colors import to_hex, to_rgb
from wordcloud import WordCloud

SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

NOMBRE_UTILES = "whatsapp_utiles.py"
NOMBRE_TESTS = "whatsapp_utiles_test.py"


def _frames_de(exc, nombre_fichero):
    """Frames de la traza de una excepción que pertenecen al fichero indicado."""
    return [f for f in traceback.extract_tb(exc.__traceback__) if Path(f.filename).name == nombre_fichero]


def describir_excepcion(exc, fichero=NOMBRE_UTILES):
    """
    Devuelve (resumen, detalle) de una excepción señalando la línea del fichero
    indicado en la que se produjo (útil para que el alumno localice el fallo).
    """
    if isinstance(exc, SyntaxError) and exc.lineno:
        nombre = Path(exc.filename).name if exc.filename else fichero
        resumen = f"{type(exc).__name__}: {exc.msg} ({nombre}, línea {exc.lineno})"
        detalle = f"{type(exc).__name__}: {exc.msg}\n→ {nombre}, línea {exc.lineno}"
        if exc.text and exc.text.strip():
            detalle += f":\n    {exc.text.strip()}"
        return resumen, detalle

    cabecera = f"{type(exc).__name__}: {exc}"
    frames = _frames_de(exc, fichero)
    if not frames:
        return cabecera, cabecera
    f = frames[-1]
    resumen = f"{cabecera} ({fichero}, línea {f.lineno})"
    detalle = f"{cabecera}\n→ {fichero}, línea {f.lineno}, en {f.name}()"
    if f.line:
        detalle += f":\n    {f.line.strip()}"
    return resumen, detalle


# Importaciones de los módulos locales del proyecto. Si whatsapp_utiles.py tiene
# un error (p. ej. de sintaxis), se informa de la línea en lugar de fallar en silencio.
try:
    import whatsapp_utiles as utiles
    from whatsapp_loader import leer_log_whatsapp
except Exception as _exc:
    _, _detalle = describir_excepcion(_exc)
    _raiz = tk.Tk()
    _raiz.withdraw()
    messagebox.showerror(
        "Error en whatsapp_utiles.py",
        f"No se puede iniciar la aplicación porque el código tiene un error:\n\n{_detalle}"
    )
    _raiz.destroy()
    raise SystemExit(1)


def activar_dpi_windows():
    """Activa el soporte High-DPI en Windows para evitar que la interfaz se vea borrosa."""
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            import ctypes
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


activar_dpi_windows()

# Rutas del proyecto
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CHAT_PATH = PROJECT_ROOT / "data" / "grupo_fp1.txt"

# Paleta de colores inspirada en WhatsApp
COL_WA_DARK = "#075E54"
COL_WA_TEAL = "#128C7E"
COL_WA_GREEN = "#25D366"
COL_WA_LIGHT_GREEN = "#DCF8C6"
COL_BG = "#F0F2F5"
COL_CARD = "#FFFFFF"
COL_BORDER = "#DCE1E7"
COL_TEXT = "#1F2937"
COL_MUTED = "#6B7280"
COL_WARN_BG = "#FFF8E1"
COL_WARN_FG = "#8D6E00"
COL_ERR_BG = "#FADBD8"
COL_ERR_FG = "#922B21"
COL_OK_BG = "#DCF8C6"
COL_OK_FG = "#075E54"
COL_PEND_BG = "#EAECEF"
COL_PEND_FG = "#4B5563"
COL_TEST_BG = "#FFE8D6"
COL_TEST_FG = "#9A3412"

# Fuentes de la interfaz. Segoe UI y Consolas solo existen en Windows; al arrancar,
# elegir_fuentes() las sustituye por equivalentes disponibles en macOS / Linux.
FUENTE = "Segoe UI"
FUENTE_MONO = "Consolas"


def elegir_fuentes(root):
    """Elige la primera fuente disponible de cada lista (o la del sistema si no hay ninguna)."""
    global FUENTE, FUENTE_MONO
    disponibles = set(tkfont.families(root))

    def primera(candidatas, nombre_tk):
        for nombre in candidatas:
            if nombre in disponibles:
                return nombre
        return tkfont.nametofont(nombre_tk).actual("family")

    FUENTE = primera(["Segoe UI", "SF Pro Text", "Helvetica Neue", "Ubuntu", "Cantarell",
                      "Noto Sans", "DejaVu Sans"], "TkDefaultFont")
    FUENTE_MONO = primera(["Consolas", "Menlo", "SF Mono", "DejaVu Sans Mono",
                           "Liberation Mono", "Courier New"], "TkFixedFont")


# Estados posibles de cada función: icono, texto, fondo, texto
ESTADOS = {
    "unloaded": ("⚪", "Sin archivo cargado", COL_PEND_BG, COL_PEND_FG),
    "pending": ("⏳", "Pendiente de implementar", COL_WARN_BG, COL_WARN_FG),
    "warn": ("⚠", "Devuelve datos, pero no pasa su test", COL_TEST_BG, COL_TEST_FG),
    "ok": ("✅", "Operativa", COL_OK_BG, COL_OK_FG),
    "error": ("❌", "Error", COL_ERR_BG, COL_ERR_FG),
}

CHART_PALETTE = [
    "#075E54", "#128C7E", "#25D366", "#34B7F1",
    "#FF9F1C", "#E76F51", "#7209B7", "#4361EE",
    "#F72585", "#2A9D8F",
]


def _paleta_usuarios():
    """
    Colores de usuario: CHART_PALETTE reordenada para que colores consecutivos
    contrasten (los más activos no quedan todos en tonos verdes), ampliada con
    tab20 para grupos grandes.
    """
    colores = ["#075E54", "#FF9F1C", "#34B7F1", "#E76F51", "#25D366",
               "#7209B7", "#F72585", "#4361EE", "#2A9D8F", "#128C7E"]
    for c in colormaps["tab20"].colors:
        h = to_hex(c).upper()
        if h not in colores:
            colores.append(h)
    return colores


PALETA_USUARIOS = _paleta_usuarios()
COL_USUARIO_DESCONOCIDO = "#9CA3AF"
COL_USUARIO_OTROS = "#B8BEC8"

# Número de usuarios que se muestran por separado en las gráficas (el resto, "Otros")
TOP_USUARIOS = 8
# Máximo de filas en el explorador (insertar decenas de miles bloquea la interfaz)
MAX_FILAS_EXPLORADOR = 5000

# Colores de la nube de palabras (tonos oscuros de WhatsApp, legibles sobre blanco)
PALETA_NUBE = ["#075E54", "#128C7E", "#0B7A75", "#1A9E50", "#2A9D8F", "#1E88B5", "#0E6E8C"]


def color_palabra_whatsapp(word, font_size, position, orientation, random_state=None, **kwargs):
    """color_func para WordCloud: elige un color de PALETA_NUBE (reproducible con random_state)."""
    generador = random_state or random
    return PALETA_NUBE[generador.randint(0, len(PALETA_NUBE) - 1)]


def aclarar_color(color, factor=0.82):
    """Mezcla un color con blanco (factor 0 = igual, 1 = blanco)."""
    r, g, b = to_rgb(color)
    return to_hex((r + (1 - r) * factor, g + (1 - g) * factor, b + (1 - b) * factor))

FUNCIONES_LAB = [
    ("calcula_rango_fechas", "Ej. 1", "Ej.1 rango_fechas", "Rango de fechas del chat"),
    ("filtra_mensajes_por_fechas", "Ej. 2", "Ej.2 filtra_fechas", "Filtrado por intervalo de fechas"),
    ("cuenta_mensajes_por_usuario", "Ej. 3.1", "Ej.3.1 por_usuario", "Conteo de mensajes por usuario"),
    ("cuenta_mensajes_por_hora", "Ej. 3.2", "Ej.3.2 por_hora", "Conteo de mensajes por hora (0-23h)"),
    ("cuenta_mensajes_por_dia_semana", "Ej. 3.3", "Ej.3.3 por_dia_sem", "Conteo de mensajes por día de semana"),
    ("calcula_longitud_media_por_usuario", "Ej. 4", "Ej.4 long_media", "Longitud media por usuario"),
    ("detecta_dia_mas_activo", "Ej. 5", "Ej.5 dia_activo", "Detección del día más activo"),
    ("analiza_palabras_caracteristicas", "Ej. 6", "Ej.6 palabras", "Palabras características por usuario"),
]


# -----------------------------------------------------------------------------
# CLASE: RangeSlider (deslizador doble redimensionable, con ratón y teclado)
# -----------------------------------------------------------------------------
class RangeSlider(tk.Canvas):
    """
    Deslizador doble de valores enteros (en la aplicación, días como ordinales).

    - Arrastrar un tirador lo mueve; los dos pueden coincidir (rango de un solo día).
    - Un clic en la pista mueve el tirador más cercano a ese punto.
    - Con el foco, las flechas ←/→ mueven el último tirador usado una unidad.
    """

    def __init__(self, master, min_val, max_val, width=320, height=26, escala=1.0,
                 line_color="#D1D5DB", active_color=COL_WA_DARK, handle_color=COL_WA_TEAL,
                 command_update=None, command_drag=None, **kwargs):
        super().__init__(master, width=width, height=height, highlightthickness=0,
                         bg=COL_CARD, takefocus=1, **kwargs)

        self.min_val = min_val
        self.max_val = max_val
        self.val_left = min_val
        self.val_right = max_val
        self.enabled = True

        # Dimensiones proporcionales a la escala de la pantalla (High-DPI)
        self.radio = max(7, round(7 * escala))
        self.grosor = max(4, round(4 * escala))
        self.borde = max(2, round(2 * escala))
        self.padding = self.radio + max(5, round(5 * escala))

        self.col_line = line_color
        self.col_active = active_color
        self.col_handle = handle_color
        self.col_disabled = "#BDBDBD"

        self.command_update = command_update
        self.command_drag = command_drag

        self.line_y = height // 2
        self.line_start = self.padding
        self.line_end = max(width - self.padding, self.padding + 1)

        self._dragging = None          # "left" / "right" mientras se arrastra
        self._por_decidir = False      # tiradores superpuestos: se decide al moverse
        self._x_inicio = 0
        self._valores_al_pulsar = None
        self._after_teclado = None
        self.activo = "right"          # último tirador usado (el que mueven las flechas)

        self.bg_line = self.create_line(
            self.line_start, self.line_y, self.line_end, self.line_y,
            fill=self.col_line, width=self.grosor, capstyle=tk.ROUND
        )
        self.active_line = self.create_line(
            self.line_start, self.line_y, self.line_end, self.line_y,
            fill=self.col_active, width=self.grosor, capstyle=tk.ROUND
        )
        self.handle_left = self.create_oval(0, 0, 0, 0, fill=self.col_handle, outline="white", width=self.borde)
        self.handle_right = self.create_oval(0, 0, 0, 0, fill=self.col_handle, outline="white", width=self.borde)

        self.update_graphics()

        self.bind("<Button-1>", self.on_press)
        self.bind("<B1-Motion>", self.on_motion)
        self.bind("<ButtonRelease-1>", self.on_release)
        self.bind("<Configure>", self.on_resize)
        self.bind("<Left>", lambda e: self.mover_con_teclado(-1))
        self.bind("<Right>", lambda e: self.mover_con_teclado(+1))
        self.bind("<FocusIn>", lambda e: self.update_graphics())
        self.bind("<FocusOut>", lambda e: self.update_graphics())

    # --- Utilidades -----------------------------------------------------------
    @property
    def pixel_range(self):
        return max(self.line_end - self.line_start, 1)

    def _interactivo(self):
        return self.enabled and self.max_val > self.min_val

    def pixel_to_value(self, pixel):
        if self.max_val <= self.min_val:
            return self.min_val
        ratio = min(max((pixel - self.line_start) / self.pixel_range, 0.0), 1.0)
        return int(round(self.min_val + (self.max_val - self.min_val) * ratio))

    def value_to_pixel(self, value):
        if self.max_val <= self.min_val:
            return self.line_start
        ratio = min(max((value - self.min_val) / (self.max_val - self.min_val), 0.0), 1.0)
        return self.line_start + ratio * self.pixel_range

    def set_state(self, state="normal"):
        """Habilita o deshabilita la interacción y actualiza colores."""
        self.enabled = (state == "normal")
        color_line = self.col_active if self.enabled else self.col_disabled
        color_handle = self.col_handle if self.enabled else self.col_disabled
        self.itemconfig(self.active_line, fill=color_line)
        self.itemconfig(self.handle_left, fill=color_handle)
        self.itemconfig(self.handle_right, fill=color_handle)
        self.config(cursor="hand2" if self.enabled else "arrow")
        self.update_graphics()

    def on_resize(self, event):
        self.line_y = max(event.height, 20) // 2
        self.line_end = max(event.width - self.padding, self.line_start + 1)
        self.coords(self.bg_line, self.line_start, self.line_y, self.line_end, self.line_y)
        self.update_graphics()

    # --- Ratón ----------------------------------------------------------------
    def on_press(self, event):
        if not self._interactivo():
            return
        self.focus_set()
        self._valores_al_pulsar = (self.val_left, self.val_right)
        x_izq = self.value_to_pixel(self.val_left)
        x_der = self.value_to_pixel(self.val_right)
        d_izq, d_der = abs(event.x - x_izq), abs(event.x - x_der)

        if min(d_izq, d_der) <= self.radio + 2:
            if abs(x_der - x_izq) < 1:
                # Tiradores superpuestos: se decide por la dirección del primer movimiento
                self._dragging = None
                self._por_decidir = True
                self._x_inicio = event.x
            else:
                self._dragging = "left" if d_izq < d_der else "right"
        else:
            # Clic en la pista: se mueve el tirador más cercano a ese punto
            # (si están superpuestos, el del lado en que se ha hecho clic)
            if abs(x_der - x_izq) < 1:
                self._dragging = "left" if event.x < x_izq else "right"
            else:
                self._dragging = "left" if d_izq < d_der else "right"
            self._mover(self._dragging, self.pixel_to_value(event.x))

        if self._dragging:
            self.activo = self._dragging
        self.update_graphics()

    def on_motion(self, event):
        if not self._interactivo():
            return
        if self._por_decidir:
            if abs(event.x - self._x_inicio) < 2:
                return
            self._dragging = "left" if event.x < self._x_inicio else "right"
            self.activo = self._dragging
            self._por_decidir = False
        if self._dragging:
            self._mover(self._dragging, self.pixel_to_value(event.x))

    def on_release(self, event):
        self._dragging = None
        self._por_decidir = False
        cambiado = self._valores_al_pulsar not in (None, (self.val_left, self.val_right))
        self._valores_al_pulsar = None
        if cambiado and self._interactivo() and self.command_update:
            self.command_update(self.val_left, self.val_right)

    # --- Teclado --------------------------------------------------------------
    def mover_con_teclado(self, delta):
        if not self._interactivo():
            return "break"
        actual = self.val_left if self.activo == "left" else self.val_right
        self._mover(self.activo, actual + delta)
        # Se recalcula cuando se deja de pulsar la tecla, no en cada pulsación
        if self._after_teclado:
            self.after_cancel(self._after_teclado)
        self._after_teclado = self.after(350, self._notificar_teclado)
        return "break"

    def _notificar_teclado(self):
        self._after_teclado = None
        if self.command_update:
            self.command_update(self.val_left, self.val_right)

    # --- Estado ---------------------------------------------------------------
    def _mover(self, lado, valor):
        if lado == "left":
            self.val_left = min(max(valor, self.min_val), self.val_right)
        else:
            self.val_right = max(min(valor, self.max_val), self.val_left)
        self.update_graphics()
        if self.command_drag:
            self.command_drag(self.val_left, self.val_right)

    def update_graphics(self):
        r = self.radio
        x_izq = self.value_to_pixel(self.val_left)
        x_der = self.value_to_pixel(self.val_right)
        self.coords(self.handle_left, x_izq - r, self.line_y - r, x_izq + r, self.line_y + r)
        self.coords(self.handle_right, x_der - r, self.line_y - r, x_der + r, self.line_y + r)
        self.coords(self.active_line, x_izq, self.line_y, x_der, self.line_y)

        try:
            con_foco = self.focus_get() is self
        except (KeyError, tk.TclError):
            con_foco = False
        for lado, tirador in (("left", self.handle_left), ("right", self.handle_right)):
            resaltado = con_foco and self.enabled and lado == self.activo
            self.itemconfig(tirador, outline=COL_WA_GREEN if resaltado else "white")
        self.tag_raise(self.handle_left if self.activo == "left" else self.handle_right)

    def get_values(self):
        return [self.val_left, self.val_right]

    def set_range(self, min_v, max_v):
        self.min_val = min_v
        self.max_val = max_v
        self.val_left = min_v
        self.val_right = max_v
        self.update_graphics()

    def set_values(self, left, right):
        """Coloca los tiradores en los valores indicados (acotados al rango actual)."""
        self.val_left = min(max(left, self.min_val), self.max_val)
        self.val_right = min(max(right, self.val_left), self.max_val)
        self.update_graphics()


# -----------------------------------------------------------------------------
# VENTANA: Inspector Interactivo de Retorno de Funciones
# -----------------------------------------------------------------------------
class FunctionInspectorWindow(tk.Toplevel):
    def __init__(self, app, initial_key=None):
        super().__init__(app.root)
        self.app = app
        self.scale = app.dpi_scale
        self.title("🔍 Inspector de Funciones — whatsapp_utiles.py")
        w = int(940 * self.scale)
        h = int(640 * self.scale)
        self.geometry(f"{w}x{h}")
        self.minsize(int(720 * self.scale), int(420 * self.scale))
        self.configure(bg=COL_BG)

        self.selected_key = initial_key or FUNCIONES_LAB[0][0]
        self.item_buttons = {}

        self._construir_ui()
        self.refrescar(self.selected_key)

    def _construir_ui(self):
        header = tk.Frame(self, bg=COL_WA_DARK, padx=14, pady=10)
        header.pack(fill=tk.X)
        tk.Label(
            header,
            text="🔍 Inspector de retorno de tus funciones (whatsapp_utiles.py)",
            bg=COL_WA_DARK, fg="white", font=(FUENTE, 11, "bold")
        ).pack(side=tk.LEFT)
        tk.Button(
            header, text="🔄 Recargar código", command=self.app.recargar_actual,
            bg=COL_WA_TEAL, fg="white", activebackground=COL_WA_GREEN, activeforeground="white",
            relief=tk.FLAT, padx=10, pady=3, font=(FUENTE, 9, "bold"), cursor="hand2"
        ).pack(side=tk.RIGHT)

        body = tk.Frame(self, bg=COL_BG, padx=10, pady=10)
        body.pack(fill=tk.BOTH, expand=True)
        body.columnconfigure(0, weight=0)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        sidebar = tk.Frame(body, bg=COL_CARD, highlightbackground=COL_BORDER, highlightthickness=1, padx=8, pady=8)
        sidebar.grid(row=0, column=0, sticky="ns", padx=(0, 10))
        tk.Label(
            sidebar, text="Funciones del laboratorio", bg=COL_CARD, fg=COL_TEXT,
            font=(FUENTE, 10, "bold")
        ).pack(anchor="w", pady=(0, 6), padx=4)

        for key, ej, _, _ in FUNCIONES_LAB:
            btn = tk.Button(
                sidebar, text=f"{ej}: {key}", anchor="w",
                relief=tk.FLAT, padx=8, pady=5, width=34,
                font=(FUENTE, 9), cursor="hand2",
                command=lambda k=key: self.seleccionar(k)
            )
            btn.pack(fill=tk.X, pady=2)
            self.item_buttons[key] = btn

        detail = tk.Frame(body, bg=COL_CARD, highlightbackground=COL_BORDER, highlightthickness=1, padx=12, pady=10)
        detail.grid(row=0, column=1, sticky="nsew")
        detail.columnconfigure(0, weight=1)
        detail.rowconfigure(5, weight=1)

        top_row = tk.Frame(detail, bg=COL_CARD)
        top_row.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        self.lbl_titulo = tk.Label(top_row, text="", bg=COL_CARD, fg=COL_WA_DARK, font=(FUENTE, 12, "bold"))
        self.lbl_titulo.pack(side=tk.LEFT)
        self.lbl_badge = tk.Label(top_row, text="", padx=8, pady=2, font=(FUENTE, 9, "bold"))
        self.lbl_badge.pack(side=tk.RIGHT)

        # Docstring de la función (se ajusta al ancho del panel)
        self.lbl_desc = tk.Label(
            detail, text="", bg=COL_CARD, fg=COL_MUTED, font=(FUENTE_MONO, 8),
            anchor="w", justify=tk.LEFT
        )
        self.lbl_desc.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        detail.bind("<Configure>", lambda e: self.lbl_desc.config(wraplength=max(e.width - 30, 200)))

        tk.Label(detail, text="Llamada ejecutada:", bg=COL_CARD, fg=COL_TEXT, font=(FUENTE, 9, "bold")).grid(row=2, column=0, sticky="w")
        self.lbl_llamada = tk.Label(
            detail, text="", bg="#F8FAFC", fg="#0F172A", font=(FUENTE_MONO, 9),
            anchor="w", justify=tk.LEFT, padx=8, pady=5,
            highlightbackground=COL_BORDER, highlightthickness=1
        )
        self.lbl_llamada.grid(row=3, column=0, sticky="ew", pady=(2, 8))

        info_tipo = tk.Frame(detail, bg=COL_CARD)
        info_tipo.grid(row=4, column=0, sticky="ew", pady=(0, 6))
        filas_info = [
            ("Tipo esperado:", "lbl_esperado", COL_TEXT, (FUENTE_MONO, 9)),
            ("Tipo devuelto:", "lbl_tipo", COL_WA_TEAL, (FUENTE_MONO, 9, "bold")),
            ("Test unitario:", "lbl_test", COL_MUTED, (FUENTE, 9, "bold")),
        ]
        for fila, (texto, atributo, color, fuente) in enumerate(filas_info):
            tk.Label(info_tipo, text=texto, bg=COL_CARD, fg=COL_TEXT, font=(FUENTE, 9, "bold")).grid(row=fila, column=0, sticky="w", padx=(0, 6))
            etiqueta = tk.Label(info_tipo, text="", bg=COL_CARD, fg=color, font=fuente, anchor="w")
            etiqueta.grid(row=fila, column=1, sticky="w")
            setattr(self, atributo, etiqueta)

        txt_frame = tk.Frame(detail, bg=COL_CARD)
        txt_frame.grid(row=5, column=0, sticky="nsew")
        txt_frame.rowconfigure(0, weight=1)
        txt_frame.columnconfigure(0, weight=1)

        self.txt_valor = tk.Text(
            txt_frame, wrap=tk.WORD, font=(FUENTE_MONO, 9),
            bg="#F8FAFC", fg="#0F172A", relief=tk.FLAT,
            highlightbackground=COL_BORDER, highlightthickness=1, padx=8, pady=8
        )
        scroll_y = ttk.Scrollbar(txt_frame, orient=tk.VERTICAL, command=self.txt_valor.yview)
        self.txt_valor.configure(yscrollcommand=scroll_y.set)
        self.txt_valor.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")

    def seleccionar(self, key):
        self.selected_key = key
        self.refrescar(key)

    def refrescar(self, key=None):
        if key:
            self.selected_key = key

        for k, ej, _, _ in FUNCIONES_LAB:
            info = self.app.registro_funciones.get(k, {})
            est = info.get("estado", "unloaded")
            icon = ESTADOS.get(est, ESTADOS["unloaded"])[0]
            is_sel = (k == self.selected_key)
            bg = "#E6F4EA" if is_sel else COL_CARD
            fg = COL_WA_DARK if is_sel else COL_TEXT
            font_btn = (FUENTE, 9, "bold") if is_sel else (FUENTE, 9)
            self.item_buttons[k].config(text=f"{icon}  {ej} · {k}", bg=bg, fg=fg, font=font_btn)

        info = self.app.registro_funciones.get(self.selected_key, {})
        est = info.get("estado", "unloaded")
        ej = info.get("ejercicio", "")
        desc = info.get("descripcion", "")
        test = self.app.resultados_tests.get(self.selected_key)

        self.lbl_titulo.config(text=f"{ej} — {self.selected_key}")
        icon, badge_txt, badge_bg, badge_fg = ESTADOS.get(est, ESTADOS["unloaded"])
        if est == "ok" and test is None:
            badge_txt = "Operativa (sin test disponible)"
        self.lbl_badge.config(text=f"{icon} {badge_txt}", bg=badge_bg, fg=badge_fg)
        func = getattr(utiles, self.selected_key, None)
        self.lbl_desc.config(text=(inspect.getdoc(func) if func else None) or desc)
        self.lbl_esperado.config(text=self._tipo_esperado(func))
        self.lbl_llamada.config(text=info.get("llamada") or "Carga primero un chat para ejecutar esta función.")
        self.lbl_tipo.config(text=info.get("tipo") or "-")

        if test is None:
            texto_test = "— no disponible"
            if self.app.error_modulo_tests:
                texto_test += f" (error en {NOMBRE_TESTS})"
            self.lbl_test.config(text=texto_test, fg=COL_MUTED)
        elif test["ok"]:
            self.lbl_test.config(text="pasa", fg=COL_OK_FG)
        else:
            self.lbl_test.config(text="falla (detalle abajo)", fg=COL_ERR_FG)

        valor_txt = self._formatear_valor(info.get("valor"))
        if est == "unloaded":
            cuerpo = "Aún no se ha cargado ningún archivo de chat (.txt)."
        elif est == "error":
            cuerpo = f"Se produjo un error:\n{info.get('detalle') or info.get('error', '')}"
            if info.get("valor") is not None:
                cuerpo += f"\n\nValor devuelto:\n{valor_txt}"
        elif est == "pending":
            cuerpo = (
                "La función todavía no está implementada (su cuerpo solo contiene 'pass').\n"
                f"Impleméntala en src/{NOMBRE_UTILES}, guarda el fichero y pulsa '🔄 Recargar código'."
            )
        elif est == "warn":
            cuerpo = (
                f"Con los datos del chat la función devuelve un valor del tipo esperado, "
                f"pero no pasa la prueba {test['nombre']}:\n\n{test['detalle']}\n\n"
                f"Valor devuelto con los datos del chat:\n{valor_txt}"
            )
        else:
            cuerpo = valor_txt
        if self.app.error_modulo_tests and est != "unloaded":
            cuerpo += f"\n\n(No se pudieron ejecutar las pruebas de {NOMBRE_TESTS}:\n{self.app.error_modulo_tests})"

        self.txt_valor.config(state=tk.NORMAL)
        self.txt_valor.delete("1.0", tk.END)
        self.txt_valor.insert(tk.END, cuerpo)
        self.txt_valor.config(state=tk.DISABLED)

    @staticmethod
    def _tipo_esperado(func):
        """Tipo de retorno anotado en la firma, sin prefijos de módulo (p. ej. dict[str, int])."""
        if func is None:
            return "-"
        try:
            anotacion = inspect.signature(func).return_annotation
        except (TypeError, ValueError):
            return "-"
        if anotacion is inspect.Signature.empty:
            return "(sin anotación)"
        texto = anotacion if isinstance(anotacion, str) else inspect.formatannotation(anotacion)
        for prefijo in ("whatsapp_utiles.", "datetime.", "collections."):
            texto = texto.replace(prefijo, "")
        return texto

    @staticmethod
    def _formatear_valor(valor):
        if isinstance(valor, list):
            total = len(valor)
            if total > 50:
                muestra = pprint.pformat(valor[:50], width=90)
                return f"{muestra}\n\n... (mostrando los primeros 50 de {total} elementos)"
            return pprint.pformat(valor, width=90)
        if isinstance(valor, dict):
            return pprint.pformat(dict(valor), width=90, sort_dicts=False)
        return pprint.pformat(valor, width=90)


# -----------------------------------------------------------------------------
# CLASE: Aplicación Principal
# -----------------------------------------------------------------------------
class WhatsAppAnalyzerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("WhatsApp Analytics — Laboratorio FP1")
        elegir_fuentes(self.root)

        # Detección de DPI real para asegurar nitidez y proporciones consistentes
        try:
            real_dpi = float(self.root.winfo_fpixels("1i"))
        except Exception:
            real_dpi = 96.0
        self.dpi_scale = max(1.0, real_dpi / 96.0)
        self.fig_dpi = int(round(max(96.0, min(real_dpi, 160.0))))

        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        win_w = min(int(1240 * self.dpi_scale), int(screen_w * 0.94))
        win_h = min(int(820 * self.dpi_scale), int(screen_h * 0.90))
        self.root.geometry(f"{win_w}x{win_h}")
        self.root.minsize(min(int(980 * self.dpi_scale), screen_w - 40), min(int(640 * self.dpi_scale), screen_h - 60))
        self.root.configure(bg=COL_BG)

        self.mensajes_todos = []
        self.mensajes = []
        self._mensajes_vista_map = {}
        self.filepath = None
        self.filename = None

        self.rango_fechas_actual = None
        self.dia_top_actual = None
        self.inspector_win = None

        # Resultados de las funciones del alumno con los mensajes filtrados: key -> (valor, estado)
        self.res = {}
        self.res_palabras = None
        # Dibujado diferido: pestañas pendientes de redibujar y elementos clicables de cada figura
        self._pestanas = {}
        self._pestanas_pendientes = set()
        self._clicables = {"users": [], "time": []}
        self._notas_interaccion = {}
        # Explorador: filtros extra (dia, hora, dia_semana, palabra), orden y formato de hora
        self.filtros_explorador = {}
        self._orden_explorador = None
        self._formato_hora = "%H:%M:%S"
        self._after_busqueda = None
        self._after_nube = None

        self.registro_funciones = {
            key: {
                "ejercicio": ej,
                "nombre": key,
                "etiqueta_corta": corta,
                "descripcion": desc,
                "estado": "unloaded",
                "llamada": "",
                "tipo": "-",
                "valor": None,
                "error": "",
                "detalle": "",
            }
            for key, ej, corta, desc in FUNCIONES_LAB
        }
        self.pill_buttons = {}

        # Resultados de las pruebas de whatsapp_utiles_test.py: key -> dict | ausente
        self.resultados_tests = {}
        self.error_modulo_tests = ""

        # Color fijo por usuario (el mismo en todas las gráficas y en el explorador)
        self.color_usuario = {}
        self.tag_usuario = {}

        self._configurar_estilos()
        self._construir_cabecera()
        self._construir_barra_progreso()
        self._construir_panel_filtro_y_kpis()
        self._construir_notebook()

        self.toggle_interface(enable=False)
        self._ejecutar_tests()

    # -------------------------------------------------------------------------
    # Configuración de estilos y construcción de interfaz compacta
    # -------------------------------------------------------------------------
    def _s(self, px):
        """Escala dimensiones en píxeles de forma proporcional al DPI actual."""
        return int(round(px * self.dpi_scale))

    def _configurar_estilos(self):
        style = ttk.Style()
        style.theme_use("clam")

        style.configure("TFrame", background=COL_BG)
        style.configure("Card.TFrame", background=COL_CARD)
        style.configure("TLabel", background=COL_BG, foreground=COL_TEXT, font=(FUENTE, 9))
        style.configure("Card.TLabel", background=COL_CARD, foreground=COL_TEXT, font=(FUENTE, 9))

        style.configure("TNotebook", background=COL_BG, borderwidth=0)
        style.configure(
            "TNotebook.Tab",
            background="#E2E8F0", foreground=COL_TEXT,
            padding=[self._s(12), self._s(5)], font=(FUENTE, 9, "bold")
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", COL_CARD), ("active", "#CBD5E1")],
            foreground=[("selected", COL_WA_DARK)]
        )

        style.configure(
            "Treeview",
            background=COL_CARD, fieldbackground=COL_CARD, foreground=COL_TEXT,
            rowheight=self._s(24), font=(FUENTE, 9)
        )
        style.configure(
            "Treeview.Heading",
            background="#E8ECEF", foreground=COL_WA_DARK,
            font=(FUENTE, 9, "bold"), relief="flat"
        )

    def _construir_cabecera(self):
        header = tk.Frame(self.root, bg=COL_WA_DARK, padx=self._s(12), pady=self._s(6))
        header.pack(fill=tk.X)

        left = tk.Frame(header, bg=COL_WA_DARK)
        left.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Label(
            left, text="💬 WhatsApp Analytics",
            bg=COL_WA_DARK, fg="white", font=(FUENTE, 12, "bold")
        ).pack(side=tk.LEFT)
        tk.Label(
            left, text="  ·  ",
            bg=COL_WA_DARK, fg="#A7F3D0", font=(FUENTE, 11)
        ).pack(side=tk.LEFT)
        self.lbl_status = tk.Label(
            left,
            text="Ningún archivo cargado (pulsa 'Cargar ejemplo' o abre un .txt)",
            bg=COL_WA_DARK, fg="#D1FAE5", font=(FUENTE, 9)
        )
        self.lbl_status.pack(side=tk.LEFT)

        right = tk.Frame(header, bg=COL_WA_DARK)
        right.pack(side=tk.RIGHT)

        self.btn_sample = tk.Button(
            right, text="⚡ Cargar ejemplo (grupo_fp1.txt)",
            command=self.cargar_ejemplo,
            bg=COL_WA_GREEN, fg="#064E3B", activebackground="#1EBE5D", activeforeground="#064E3B",
            relief=tk.FLAT, padx=self._s(10), pady=self._s(3), font=(FUENTE, 9, "bold"), cursor="hand2"
        )
        self.btn_sample.pack(side=tk.LEFT, padx=(0, self._s(5)))

        self.btn_load = tk.Button(
            right, text="📂 Abrir archivo (.txt)",
            command=self.cargar_fichero,
            bg=COL_WA_TEAL, fg="white", activebackground="#0E7266", activeforeground="white",
            relief=tk.FLAT, padx=self._s(10), pady=self._s(3), font=(FUENTE, 9, "bold"), cursor="hand2"
        )
        self.btn_load.pack(side=tk.LEFT, padx=(0, self._s(5)))

        self.btn_reload = tk.Button(
            right, text="🔄 Recargar código",
            command=self.recargar_actual,
            bg="#0B4F46", fg="white", activebackground=COL_WA_TEAL, activeforeground="white",
            disabledforeground="#9CA3AF",
            relief=tk.FLAT, padx=self._s(8), pady=self._s(3), font=(FUENTE, 9), cursor="hand2"
        )
        self.btn_reload.pack(side=tk.LEFT, padx=(0, self._s(5)))

        self.btn_inspector = tk.Button(
            right, text="🔍 Inspector",
            command=lambda: self.abrir_inspector(),
            bg="white", fg=COL_WA_DARK, activebackground="#E5E7EB", activeforeground=COL_WA_DARK,
            relief=tk.FLAT, padx=self._s(9), pady=self._s(3), font=(FUENTE, 9, "bold"), cursor="hand2"
        )
        self.btn_inspector.pack(side=tk.LEFT)

    def _construir_barra_progreso(self):
        card = tk.Frame(
            self.root, bg=COL_CARD, highlightbackground=COL_BORDER,
            highlightthickness=1, padx=self._s(8), pady=self._s(4)
        )
        card.pack(fill=tk.X, padx=self._s(10), pady=(self._s(5), self._s(3)))

        row = tk.Frame(card, bg=COL_CARD)
        row.pack(fill=tk.X)

        left = tk.Frame(row, bg=COL_CARD)
        left.pack(side=tk.LEFT, padx=(0, self._s(8)))
        tk.Label(
            left, text="🧩 Funciones:",
            bg=COL_CARD, fg=COL_TEXT, font=(FUENTE, 8, "bold")
        ).pack(side=tk.LEFT)
        self.lbl_progreso = tk.Label(
            left, text="0/8",
            bg=COL_PEND_BG, fg=COL_PEND_FG, padx=self._s(6), pady=self._s(1), font=(FUENTE, 8, "bold")
        )
        self.lbl_progreso.pack(side=tk.LEFT, padx=(self._s(5), 0))

        pills_frame = tk.Frame(row, bg=COL_CARD)
        pills_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
        for col in range(len(FUNCIONES_LAB)):
            pills_frame.columnconfigure(col, weight=1, uniform="pills")

        for idx, (key, _, corta, _) in enumerate(FUNCIONES_LAB):
            btn = tk.Button(
                pills_frame,
                text=f"⚪ {corta}",
                command=lambda k=key: self.abrir_inspector(k),
                bg=COL_PEND_BG, fg=COL_PEND_FG,
                activebackground="#D1D5DB",
                relief=tk.FLAT, anchor="w", padx=self._s(5), pady=self._s(2),
                font=(FUENTE, 8, "bold"), cursor="hand2"
            )
            btn.grid(row=0, column=idx, sticky="ew", padx=self._s(2))
            self.pill_buttons[key] = btn

    def _construir_panel_filtro_y_kpis(self):
        card = tk.Frame(
            self.root, bg=COL_CARD, highlightbackground=COL_BORDER,
            highlightthickness=1, padx=self._s(8), pady=self._s(4)
        )
        card.pack(fill=tk.X, padx=self._s(10), pady=(0, self._s(4)))

        main_row = tk.Frame(card, bg=COL_CARD)
        main_row.pack(fill=tk.X)

        # Izquierda: Filtro de fechas compacto en una sola fila
        filter_zone = tk.Frame(main_row, bg=COL_CARD)
        filter_zone.pack(side=tk.LEFT, fill=tk.X, expand=True)

        tk.Label(
            filter_zone, text="📅 Rango (Ej.1-2):",
            bg=COL_CARD, fg=COL_TEXT, font=(FUENTE, 8, "bold")
        ).pack(side=tk.LEFT, padx=(0, self._s(6)))

        self.str_fecha_inicio = tk.StringVar(value="--/--/----")
        self.str_fecha_fin = tk.StringVar(value="--/--/----")

        tk.Label(
            filter_zone, textvariable=self.str_fecha_inicio,
            bg=COL_CARD, fg=COL_WA_DARK, font=(FUENTE, 9, "bold"), width=10
        ).pack(side=tk.LEFT)

        self.range_slider = RangeSlider(
            filter_zone, min_val=0, max_val=100, height=self._s(26), width=self._s(180),
            escala=self.dpi_scale,
            command_drag=self.actualizar_etiquetas_drag,
            command_update=self.ejecutar_filtro_release
        )
        self.range_slider.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=self._s(4))

        tk.Label(
            filter_zone, textvariable=self.str_fecha_fin,
            bg=COL_CARD, fg=COL_WA_DARK, font=(FUENTE, 9, "bold"), width=10
        ).pack(side=tk.LEFT)

        self.btn_reset_range = tk.Button(
            filter_zone, text="↺",
            command=self.restablecer_rango,
            bg=COL_PEND_BG, fg=COL_TEXT, relief=tk.FLAT,
            padx=self._s(6), pady=self._s(1), font=(FUENTE, 8, "bold"), cursor="hand2", state=tk.DISABLED
        )
        self.btn_reset_range.pack(side=tk.LEFT, padx=(self._s(4), self._s(6)))

        # Derecha: KPIs en línea separados por divisores finos
        kpi_zone = tk.Frame(main_row, bg=COL_CARD)
        kpi_zone.pack(side=tk.RIGHT)

        self.var_kpi_msgs = tk.StringVar(value="✉️ -")
        self.var_kpi_users = tk.StringVar(value="👥 -")
        self.var_kpi_top = tk.StringVar(value="🏆 -")

        self._add_inline_kpi(kpi_zone, "Ej.2:", self.var_kpi_msgs)
        self._add_vdiv(kpi_zone)
        self._add_inline_kpi(kpi_zone, "Ej.3.1:", self.var_kpi_users)
        self._add_vdiv(kpi_zone)

        top_kpi = tk.Frame(kpi_zone, bg=COL_CARD, padx=self._s(6))
        top_kpi.pack(side=tk.LEFT)
        tk.Label(top_kpi, text="Ej.5:", bg=COL_CARD, fg=COL_MUTED, font=(FUENTE_MONO, 8)).pack(side=tk.LEFT)
        tk.Label(top_kpi, textvariable=self.var_kpi_top, bg=COL_CARD, fg=COL_WA_DARK, font=(FUENTE, 9, "bold")).pack(side=tk.LEFT, padx=(self._s(3), self._s(5)))
        self.btn_ver_dia_kpi = tk.Button(
            top_kpi, text="💬 Ver día", command=self.ver_mensajes_dia_activo,
            bg=COL_WA_LIGHT_GREEN, fg=COL_WA_DARK, relief=tk.FLAT,
            padx=self._s(6), pady=self._s(1), font=(FUENTE, 8, "bold"), cursor="hand2", state=tk.DISABLED
        )
        self.btn_ver_dia_kpi.pack(side=tk.LEFT)

        self.lbl_aviso_filtro = tk.Label(
            card, text="", bg=COL_WARN_BG, fg=COL_WARN_FG,
            font=(FUENTE, 8, "bold"), anchor="w", justify=tk.LEFT, padx=self._s(8), pady=self._s(2)
        )
        card.bind("<Configure>", lambda e: self.lbl_aviso_filtro.config(wraplength=max(e.width - self._s(30), 200)))

    def _add_vdiv(self, parent):
        tk.Frame(parent, bg=COL_BORDER, width=1, height=self._s(18)).pack(side=tk.LEFT, padx=self._s(4))

    def _add_inline_kpi(self, parent, etiqueta_ej, var_valor):
        box = tk.Frame(parent, bg=COL_CARD, padx=self._s(6))
        box.pack(side=tk.LEFT)
        tk.Label(box, text=etiqueta_ej, bg=COL_CARD, fg=COL_MUTED, font=(FUENTE_MONO, 8)).pack(side=tk.LEFT)
        tk.Label(box, textvariable=var_valor, bg=COL_CARD, fg=COL_WA_DARK, font=(FUENTE, 9, "bold")).pack(side=tk.LEFT, padx=(self._s(3), 0))

    def _construir_notebook(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=self._s(10), pady=(0, self._s(8)))

        self.tab_users = ttk.Frame(self.notebook, style="Card.TFrame")
        self.tab_time = ttk.Frame(self.notebook, style="Card.TFrame")
        self.tab_words = ttk.Frame(self.notebook, style="Card.TFrame")
        self.tab_messages = ttk.Frame(self.notebook, style="Card.TFrame")

        self.notebook.add(self.tab_users, text="👥 Actividad por Usuario")
        self.notebook.add(self.tab_time, text="🕒 Análisis Temporal")
        self.notebook.add(self.tab_words, text="☁️ Nube de Palabras")
        self.notebook.add(self.tab_messages, text="💬 Explorador de Mensajes")

        self._pestanas = {
            str(self.tab_users): "users",
            str(self.tab_time): "time",
            str(self.tab_words): "words",
            str(self.tab_messages): "messages",
        }
        self.notebook.bind("<<NotebookTabChanged>>", self._al_cambiar_pestana)

        self.crear_panel_usuarios()
        self.crear_panel_tiempo()
        self.crear_panel_palabras()
        self.crear_panel_explorador()

    def _crear_banner(self, tab, texto):
        """Barra superior de una pestaña con el texto que indica qué ejercicio(s) se visualizan."""
        banner = tk.Frame(tab, bg="#F8FAFC", padx=self._s(8), pady=self._s(3), highlightbackground=COL_BORDER, highlightthickness=1)
        banner.pack(fill=tk.X, padx=self._s(8), pady=(self._s(6), self._s(2)))
        tk.Label(banner, text=texto, bg="#F8FAFC", fg=COL_WA_DARK, font=(FUENTE_MONO, 8, "bold")).pack(side=tk.LEFT)
        return banner

    def _boton_png(self, parent, pestana):
        """Botón para guardar como imagen la figura de una pestaña."""
        btn = tk.Button(
            parent, text="💾 PNG", command=lambda: self.exportar_png(pestana),
            bg=COL_PEND_BG, fg=COL_WA_DARK, relief=tk.FLAT,
            padx=self._s(7), pady=self._s(1), font=(FUENTE, 8, "bold"), cursor="hand2"
        )
        btn.pack(side=tk.RIGHT, padx=(self._s(6), 0))
        return btn

    def _crear_figura(self, master, figsize, nombre):
        """Crea una figura de matplotlib en un canvas Tk con nota de interacción y clics conectados."""
        fig = plt.Figure(figsize=figsize, dpi=self.fig_dpi, facecolor=COL_CARD)
        canvas = FigureCanvasTkAgg(fig, master=master)
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=self._s(8), pady=(0, self._s(6)))
        nota = fig.text(
            0.99, 0.01, "Haz clic en un sector o en una barra para ver sus mensajes en el Explorador",
            ha="right", va="bottom", fontsize=7.5, color=COL_MUTED, visible=False
        )
        self._notas_interaccion[nombre] = nota
        self._conectar_clics(canvas, nombre)
        return fig, canvas

    def crear_panel_usuarios(self):
        banner = self._crear_banner(
            self.tab_users,
            "📌 Izquierda: Ej. 3.1 cuenta_mensajes_por_usuario(mensajes)   |   📌 Derecha: Ej. 4 calcula_longitud_media_por_usuario(mensajes)"
        )
        self._boton_png(banner, "users")

        self.fig_users, self.canvas_users = self._crear_figura(self.tab_users, (11, 5.2), "users")
        self.ax_pie = self.fig_users.add_subplot(121)
        self.ax_len = self.fig_users.add_subplot(122)
        self._dibujar_placeholder(self.ax_pie, "Carga un archivo de chat para comenzar")
        self._dibujar_placeholder(self.ax_len, "Carga un archivo de chat para comenzar")
        self.fig_users.tight_layout(pad=2.0)

    def crear_panel_tiempo(self):
        banner = self._crear_banner(
            self.tab_time,
            "📌 Izquierda: Ej. 3.2 cuenta_mensajes_por_hora(mensajes)   |   📌 Derecha: Ej. 3.3 cuenta_mensajes_por_dia_semana(mensajes)"
        )
        self._boton_png(banner, "time")

        right_box = tk.Frame(banner, bg="#F8FAFC")
        right_box.pack(side=tk.RIGHT)
        self.lbl_dia_top = tk.Label(
            right_box, text="📅 Día récord (Ej. 5): -",
            bg="#F8FAFC", fg=COL_WA_DARK, font=(FUENTE, 8, "bold")
        )
        self.lbl_dia_top.pack(side=tk.LEFT, padx=(0, self._s(6)))
        self.btn_ver_dia_time = tk.Button(
            right_box, text="🔍 Ver ese día",
            command=self.ver_mensajes_dia_activo,
            bg=COL_WA_TEAL, fg="white", relief=tk.FLAT,
            padx=self._s(7), pady=self._s(1), font=(FUENTE, 8, "bold"), cursor="hand2", state=tk.DISABLED
        )
        self.btn_ver_dia_time.pack(side=tk.LEFT)

        self.fig_time, self.canvas_time = self._crear_figura(self.tab_time, (11.5, 5.2), "time")
        axes = self.fig_time.subplots(1, 2, gridspec_kw={"width_ratios": [1.45, 1]})
        self.ax_hour, self.ax_week = axes[0], axes[1]
        self._dibujar_placeholder(self.ax_hour, "Carga un archivo de chat para comenzar")
        self._dibujar_placeholder(self.ax_week, "Carga un archivo de chat para comenzar")
        self.fig_time.tight_layout(pad=2.0)

    def crear_panel_palabras(self):
        frame_ctrl = tk.Frame(self.tab_words, bg="#F8FAFC", padx=self._s(8), pady=self._s(4), highlightbackground=COL_BORDER, highlightthickness=1)
        frame_ctrl.pack(fill=tk.X, padx=self._s(8), pady=(self._s(6), self._s(4)))

        tk.Label(frame_ctrl, text="Usuario:", bg="#F8FAFC", fg=COL_TEXT, font=(FUENTE, 9, "bold")).pack(side=tk.LEFT)
        self.combo_users = ttk.Combobox(frame_ctrl, state="disabled", width=18)
        self.combo_users.pack(side=tk.LEFT, padx=(self._s(5), self._s(10)))
        self.combo_users.bind("<<ComboboxSelected>>", self.actualizar_palabras)

        tk.Label(frame_ctrl, text="Top n:", bg="#F8FAFC", fg=COL_TEXT, font=(FUENTE, 9, "bold")).pack(side=tk.LEFT)
        self.combo_n = ttk.Combobox(frame_ctrl, state="disabled", values=["10", "25", "50", "100"], width=5)
        self.combo_n.set("100")
        self.combo_n.pack(side=tk.LEFT, padx=(self._s(5), self._s(12)))
        self.combo_n.bind("<<ComboboxSelected>>", self.actualizar_palabras)

        self.lbl_words_title = tk.Label(
            frame_ctrl, text="📌 Ej. 6: utiles.analiza_palabras_caracteristicas(mensajes, usuario, n)",
            bg="#F8FAFC", fg=COL_WA_DARK, font=(FUENTE_MONO, 8, "bold")
        )
        self.lbl_words_title.pack(side=tk.LEFT)

        self._boton_png(frame_ctrl, "words")
        self.btn_inspect_ej6 = tk.Button(
            frame_ctrl, text="🔍 Ver retorno Ej. 6",
            command=lambda: self.abrir_inspector("analiza_palabras_caracteristicas"),
            bg=COL_PEND_BG, fg=COL_WA_DARK, relief=tk.FLAT,
            padx=self._s(8), pady=self._s(2), font=(FUENTE, 8, "bold"), cursor="hand2"
        )
        self.btn_inspect_ej6.pack(side=tk.RIGHT)

        content = tk.Frame(self.tab_words, bg=COL_CARD)
        content.pack(fill=tk.BOTH, expand=True, padx=self._s(8), pady=(0, self._s(6)))
        content.columnconfigure(0, weight=1)
        content.columnconfigure(1, weight=0)
        content.rowconfigure(0, weight=1)

        # Nube a la izquierda (se genera al tamaño real del panel)
        left_frame = tk.Frame(content, bg=COL_CARD, highlightbackground=COL_BORDER, highlightthickness=1)
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, self._s(6)))

        self.fig_words = plt.Figure(figsize=(9, 5.2), dpi=self.fig_dpi, facecolor=COL_CARD)
        self.ax_words = self.fig_words.add_subplot(111)
        self.ax_words.axis("off")
        self.fig_words.subplots_adjust(left=0, right=1, top=1, bottom=0)
        self.canvas_words = FigureCanvasTkAgg(self.fig_words, master=left_frame)
        self.canvas_words.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.canvas_words.get_tk_widget().bind("<Configure>", self._al_redimensionar_nube, add="+")

        # Ranking a la derecha, con ancho fijo
        right_width = self._s(258)
        right_frame = tk.Frame(
            content, bg=COL_CARD, highlightbackground=COL_BORDER, highlightthickness=1,
            padx=self._s(6), pady=self._s(6), width=right_width
        )
        right_frame.grid(row=0, column=1, sticky="nsew")
        right_frame.grid_propagate(False)
        right_frame.rowconfigure(2, weight=1)
        right_frame.columnconfigure(0, weight=1)

        tk.Label(
            right_frame, text="📊 Ranking devuelto",
            bg=COL_CARD, fg=COL_WA_DARK, font=(FUENTE, 9, "bold"), anchor="w"
        ).grid(row=0, column=0, columnspan=2, sticky="ew")

        tk.Label(
            right_frame,
            text="Saldo = usuario − resto. La nube dibuja solo saldo > 0. Clic en una palabra para ver sus mensajes.",
            bg=COL_CARD, fg=COL_MUTED, font=(FUENTE, 8), anchor="w", wraplength=self._s(235), justify=tk.LEFT
        ).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(1, 4))

        self.tree_words = ttk.Treeview(
            right_frame, columns=("pos", "palabra", "puntos"), show="headings", selectmode="browse"
        )
        self.tree_words.heading("pos", text="#")
        self.tree_words.heading("palabra", text="Palabra")
        self.tree_words.heading("puntos", text="Saldo")
        self.tree_words.column("pos", width=self._s(34), anchor="center", stretch=False)
        self.tree_words.column("palabra", width=self._s(132), anchor="w")
        self.tree_words.column("puntos", width=self._s(62), anchor="e", stretch=False)
        self.tree_words.tag_configure("pos", foreground=COL_WA_DARK)
        self.tree_words.tag_configure("nonpos", foreground=COL_MUTED)
        self.tree_words.bind("<ButtonRelease-1>", self._al_pulsar_palabra)
        self.tree_words.config(cursor="hand2")

        scroll_w = ttk.Scrollbar(right_frame, orient=tk.VERTICAL, command=self.tree_words.yview)
        self.tree_words.configure(yscrollcommand=scroll_w.set)
        self.tree_words.grid(row=2, column=0, sticky="nsew")
        scroll_w.grid(row=2, column=1, sticky="ns")

    COLUMNAS_EXPLORADOR = [
        # (id, título, ancho, alineación, estira)
        ("idx", "Nº", 52, "center", False),
        ("fecha", "Fecha", 90, "center", False),
        ("hora", "Hora", 70, "center", False),
        ("usuario", "Usuario", 120, "w", False),
        ("texto", "Texto del mensaje", 650, "w", True),
    ]

    def crear_panel_explorador(self):
        self._crear_banner(
            self.tab_messages,
            "📌 Lista de tuplas Mensaje(fecha, hora, usuario, texto) resultante de Ej. 2: filtra_mensajes_por_fechas(...)"
            "   ·   Nº = posición en esa lista   ·   Clic en una cabecera para ordenar"
        )

        ctrl = tk.Frame(self.tab_messages, bg=COL_CARD, padx=self._s(8), pady=self._s(4))
        ctrl.pack(fill=tk.X)

        tk.Label(ctrl, text="Usuario:", bg=COL_CARD, fg=COL_TEXT, font=(FUENTE, 9, "bold")).pack(side=tk.LEFT)
        self.combo_exp_user = ttk.Combobox(ctrl, state="disabled", width=16)
        self.combo_exp_user.pack(side=tk.LEFT, padx=(self._s(5), self._s(10)))
        self.combo_exp_user.bind("<<ComboboxSelected>>", lambda e: self.actualizar_explorador())

        tk.Label(ctrl, text="Buscar:", bg=COL_CARD, fg=COL_TEXT, font=(FUENTE, 9, "bold")).pack(side=tk.LEFT)
        self.var_exp_search = tk.StringVar()
        self.entry_exp_search = ttk.Entry(ctrl, textvariable=self.var_exp_search, width=24, state="disabled")
        self.entry_exp_search.pack(side=tk.LEFT, padx=(self._s(5), self._s(8)))
        self.entry_exp_search.bind("<KeyRelease>", lambda e: self._programar_busqueda())

        self.btn_exp_dia_top = tk.Button(
            ctrl, text="📅 Solo día más activo (Ej. 5)",
            command=self.ver_mensajes_dia_activo,
            bg=COL_WA_LIGHT_GREEN, fg=COL_WA_DARK, relief=tk.FLAT,
            padx=self._s(8), pady=self._s(2), font=(FUENTE, 8, "bold"), cursor="hand2", state=tk.DISABLED
        )
        self.btn_exp_dia_top.pack(side=tk.LEFT, padx=(0, self._s(6)))

        # Botón que muestra los filtros activos (día, hora, día de la semana, palabra) y los quita
        self.btn_exp_filtros = tk.Button(
            ctrl, text="",
            command=self.limpiar_filtros_explorador,
            bg=COL_WARN_BG, fg=COL_WARN_FG, relief=tk.FLAT,
            padx=self._s(8), pady=self._s(2), font=(FUENTE, 8, "bold"), cursor="hand2"
        )

        self.lbl_exp_count = tk.Label(ctrl, text="0 mensajes", bg=COL_CARD, fg=COL_MUTED, font=(FUENTE, 9, "bold"))
        self.lbl_exp_count.pack(side=tk.RIGHT)

        # Detalle del mensaje seleccionado (texto completo y tupla). Se empaqueta antes
        # que la tabla para que quede siempre visible abajo.
        detail_bar = tk.Frame(self.tab_messages, bg="#F8FAFC", padx=self._s(8), pady=self._s(4), highlightbackground=COL_BORDER, highlightthickness=1)
        detail_bar.pack(side=tk.BOTTOM, fill=tk.X, padx=self._s(8), pady=(self._s(4), self._s(6)))
        self.lbl_mensaje_texto = tk.Label(
            detail_bar, text="", bg="#F8FAFC", fg=COL_TEXT, font=(FUENTE, 9), anchor="w", justify=tk.LEFT
        )
        self.lbl_mensaje_tupla = tk.Label(
            detail_bar,
            text="Selecciona una fila para ver el texto completo y la tupla Mensaje(fecha, hora, usuario, texto) exacta en Python.",
            bg="#F8FAFC", fg=COL_TEXT, font=(FUENTE_MONO, 8), anchor="w", justify=tk.LEFT
        )
        self.lbl_mensaje_tupla.pack(fill=tk.X)
        detail_bar.bind("<Configure>", lambda e: (
            self.lbl_mensaje_texto.config(wraplength=max(e.width - self._s(20), 200)),
            self.lbl_mensaje_tupla.config(wraplength=max(e.width - self._s(20), 200)),
        ))

        table_frame = tk.Frame(self.tab_messages, bg=COL_CARD, padx=self._s(8))
        table_frame.pack(fill=tk.BOTH, expand=True)
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        self.tree_messages = ttk.Treeview(
            table_frame, columns=[c[0] for c in self.COLUMNAS_EXPLORADOR],
            show="headings", selectmode="browse"
        )
        for col, titulo, ancho, alinea, estira in self.COLUMNAS_EXPLORADOR:
            self.tree_messages.heading(col, text=titulo, command=lambda c=col: self.ordenar_explorador(c))
            self.tree_messages.column(col, width=self._s(ancho), anchor=alinea, stretch=estira)

        scroll_my = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree_messages.yview)
        self.tree_messages.configure(yscrollcommand=scroll_my.set)
        self.tree_messages.grid(row=0, column=0, sticky="nsew")
        scroll_my.grid(row=0, column=1, sticky="ns")
        self.tree_messages.bind("<<TreeviewSelect>>", self._on_select_mensaje)

    # -------------------------------------------------------------------------
    # Estado de interfaz y utilidades
    # -------------------------------------------------------------------------
    def toggle_interface(self, enable=True):
        """Habilita o deshabilita controles generales de la interfaz."""
        for tab_id in self.notebook.tabs():
            self.notebook.tab(tab_id, state="normal" if enable else "disabled")

        self.combo_users.config(state="readonly" if enable else "disabled")
        self.combo_n.config(state="readonly" if enable else "disabled")
        self.combo_exp_user.config(state="readonly" if enable else "disabled")
        self.entry_exp_search.config(state="normal" if enable else "disabled")

        if not enable:
            self.range_slider.set_state("disabled")
            self.btn_reset_range.config(state=tk.DISABLED)
            self.btn_ver_dia_kpi.config(state=tk.DISABLED)
            self.btn_ver_dia_time.config(state=tk.DISABLED)
            self.btn_exp_dia_top.config(state=tk.DISABLED)

    def _invocar_util(self, key, llamada_str, func, *args, validador=None, **kwargs):
        """Invoca una función de whatsapp_utiles.py de forma segura y registra su estado."""
        """
        Invoca una función de whatsapp_utiles.py de forma segura y registra su estado.

        Devuelve (resultado, estado_para_dibujar), donde estado_para_dibujar es "ok"
        si el resultado se puede representar (aunque no pase su test), "pending" o "error".
        En el registro, el estado puede ser además "warn" (datos válidos pero test fallido).
        """
        entry = self.registro_funciones[key]
        entry["llamada"] = llamada_str
        entry["error"] = ""
        entry["detalle"] = ""

        def marcar(estado, tipo, valor=None, error="", detalle=""):
            entry["estado"] = estado
            entry["tipo"] = tipo
            entry["valor"] = valor
            entry["error"] = error
            entry["detalle"] = detalle or error

        try:
            res = func(*args, **kwargs)
        except NotImplementedError:
            marcar("pending", "NotImplementedError")
            return None, "pending"
        except Exception as exc:
            resumen, detalle = describir_excepcion(exc)
            marcar("error", type(exc).__name__, error=resumen, detalle=detalle)
            return None, "error"

        if res is None:
            if self._es_esqueleto(func):
                marcar("pending", "NoneType")
                return None, "pending"
            marcar(
                "error", "NoneType",
                error="La función devuelve None. ¿Has olvidado el return?",
                detalle=(
                    "La función ya tiene código, pero ha devuelto None.\n"
                    "Comprueba que termina con un 'return' del resultado y que ese "
                    "return se alcanza (no está dentro de un if o de un bucle que no se ejecuta)."
                )
            )
            return None, "error"

        if key == "calcula_rango_fechas" and isinstance(res, (tuple, list)) and len(res) == 2 and res[0] is None and res[1] is None:
            marcar("pending", "tuple(None, None)", valor=res)
            return None, "pending"

        if validador is not None:
            try:
                ok_val, msg_err = validador(res)
            except Exception as exc:
                ok_val, msg_err = False, f"El valor devuelto no tiene la forma esperada ({type(exc).__name__}: {exc})."
            if not ok_val:
                marcar("error", type(res).__name__, valor=res, error=msg_err)
                return None, "error"

        if isinstance(res, (list, dict, tuple, set)):
            tipo = f"{type(res).__name__} ({len(res)} elementos)"
        else:
            tipo = type(res).__name__

        test = self.resultados_tests.get(key)
        if test is not None and not test["ok"]:
            marcar("warn", tipo, valor=res, error=f"No pasa {test['nombre']}: {test['resumen']}", detalle=test["detalle"])
        else:
            marcar("ok", tipo, valor=res)
        return res, "ok"

    @staticmethod
    def _es_esqueleto(func):
        """True si el cuerpo de la función solo contiene la docstring y 'pass' (sin implementar)."""
        try:
            arbol = ast.parse(textwrap.dedent(inspect.getsource(func)))
        except (OSError, TypeError, SyntaxError):
            return True
        cuerpo = arbol.body[0].body
        if (cuerpo and isinstance(cuerpo[0], ast.Expr)
                and isinstance(cuerpo[0].value, ast.Constant) and isinstance(cuerpo[0].value.value, str)):
            cuerpo = cuerpo[1:]
        return all(isinstance(nodo, ast.Pass) for nodo in cuerpo)

    # -------------------------------------------------------------------------
    # Recarga del código del alumno y ejecución de las pruebas
    # -------------------------------------------------------------------------
    def _recargar_codigo(self):
        """Vuelve a importar whatsapp_utiles.py (y sus pruebas) para recoger los cambios guardados."""
        linecache.checkcache()
        # Python reutiliza el .pyc si el fuente tiene el mismo tamaño y la misma fecha
        # (en segundos): un cambio rápido de un solo carácter podría no recargarse.
        for nombre in (NOMBRE_UTILES, NOMBRE_TESTS):
            try:
                Path(importlib.util.cache_from_source(str(SRC_DIR / nombre))).unlink(missing_ok=True)
            except (OSError, NotImplementedError):
                pass
        try:
            importlib.reload(utiles)
        except Exception as exc:
            _, detalle = describir_excepcion(exc)
            messagebox.showerror(
                "Error en whatsapp_utiles.py",
                f"No se ha podido recargar el código:\n\n{detalle}\n\n"
                "Corrige el error, guarda el fichero y vuelve a pulsar '🔄 Recargar código'."
            )
            return False
        self._ejecutar_tests()
        return True

    def _ejecutar_tests(self):
        """Ejecuta test_<función>() de whatsapp_utiles_test.py para cada función del laboratorio."""
        self.resultados_tests = {}
        self.error_modulo_tests = ""
        linecache.checkcache()
        salida = io.StringIO()
        try:
            with contextlib.redirect_stdout(salida):
                if "whatsapp_utiles_test" in sys.modules:
                    mod_tests = importlib.reload(sys.modules["whatsapp_utiles_test"])
                else:
                    mod_tests = importlib.import_module("whatsapp_utiles_test")
        except (Exception, SystemExit) as exc:
            fichero = NOMBRE_UTILES if _frames_de(exc, NOMBRE_UTILES) else NOMBRE_TESTS
            self.error_modulo_tests = describir_excepcion(exc, fichero)[1]
            return

        for key, *_ in FUNCIONES_LAB:
            nombre = f"test_{key}"
            test = getattr(mod_tests, nombre, None)
            if not callable(test):
                continue
            try:
                with contextlib.redirect_stdout(salida):
                    test()
            except Exception as exc:
                self.resultados_tests[key] = {"ok": False, "nombre": nombre, **self._describir_fallo_test(exc)}
            else:
                self.resultados_tests[key] = {"ok": True, "nombre": nombre, "resumen": "", "detalle": ""}

    @staticmethod
    def _describir_fallo_test(exc):
        """Describe por qué ha fallado un test: el assert que no se cumple o la línea que lanza la excepción."""
        if isinstance(exc, AssertionError):
            frames = _frames_de(exc, NOMBRE_TESTS)
            if frames:
                f = frames[-1]
                linea = (f.line or "").strip()
                return {
                    "resumen": f"no se cumple «{linea}» ({NOMBRE_TESTS}, línea {f.lineno})",
                    "detalle": f"No se cumple la comprobación:\n    {linea}\n→ {NOMBRE_TESTS}, línea {f.lineno}",
                }
        fichero = NOMBRE_UTILES if _frames_de(exc, NOMBRE_UTILES) else NOMBRE_TESTS
        resumen, detalle = describir_excepcion(exc, fichero)
        return {"resumen": resumen, "detalle": detalle}

    def _actualizar_barra_progreso(self):
        activas = 0
        total = len(FUNCIONES_LAB)
        for key, _, corta, _ in FUNCIONES_LAB:
            est = self.registro_funciones[key]["estado"]
            if est == "ok":
                activas += 1
            icon, _, bg, fg = ESTADOS.get(est, ESTADOS["unloaded"])
            self.pill_buttons[key].config(text=f"{icon} {corta}", bg=bg, fg=fg)

        if not self.mensajes_todos:
            self.lbl_progreso.config(text=f"0/{total}", bg=COL_PEND_BG, fg=COL_PEND_FG)
        elif activas == total:
            self.lbl_progreso.config(text=f"{activas}/{total} ✅", bg=COL_OK_BG, fg=COL_OK_FG)
        else:
            self.lbl_progreso.config(text=f"{activas}/{total}", bg=COL_WARN_BG, fg=COL_WARN_FG)

        if self.inspector_win and self.inspector_win.winfo_exists():
            self.inspector_win.refrescar()

    def abrir_inspector(self, key=None):
        if self.inspector_win and self.inspector_win.winfo_exists():
            self.inspector_win.refrescar(key)
            self.inspector_win.lift()
            self.inspector_win.focus_force()
        else:
            self.inspector_win = FunctionInspectorWindow(self, initial_key=key)

    # -------------------------------------------------------------------------
    # Carga de archivos y filtrado
    # -------------------------------------------------------------------------
    def cargar_ejemplo(self):
        if not DEFAULT_CHAT_PATH.exists():
            messagebox.showwarning(
                "Archivo no encontrado",
                f"No se encontró el archivo de ejemplo en:\n{DEFAULT_CHAT_PATH}"
            )
            return
        if self._recargar_codigo():
            self._procesar_fichero(str(DEFAULT_CHAT_PATH))

    def cargar_fichero(self):
        filepath = filedialog.askopenfilename(
            initialdir=str(PROJECT_ROOT),
            title="Seleccionar historial exportado de WhatsApp (.txt)",
            filetypes=[("Archivos de texto", "*.txt"), ("Todos", "*.*")]
        )
        if not filepath:
            return
        if self._recargar_codigo():
            self._procesar_fichero(filepath)

    def recargar_actual(self):
        """Recarga whatsapp_utiles.py (cambios guardados por el alumno) y vuelve a analizar el chat."""
        if not self._recargar_codigo():
            return
        if self.filepath:
            self._procesar_fichero(self.filepath, conservar_rango=True)
        else:
            self._actualizar_barra_progreso()

    def _asignar_colores_usuarios(self):
        """Asigna un color fijo a cada usuario (por orden de actividad en todo el chat)."""
        orden = [u for u, _ in Counter(m.usuario for m in self.mensajes_todos).most_common()]
        self.color_usuario = {u: PALETA_USUARIOS[i % len(PALETA_USUARIOS)] for i, u in enumerate(orden)}
        self.tag_usuario = {}
        for i, u in enumerate(orden):
            tag = f"user_{i}"
            self.tag_usuario[u] = tag
            self.tree_messages.tag_configure(tag, background=aclarar_color(self.color_usuario[u], 0.85))

    def _color_de(self, usuario):
        return self.color_usuario.get(usuario, COL_USUARIO_DESCONOCIDO)

    def _procesar_fichero(self, filepath, conservar_rango=False):
        try:
            mensajes_leidos = leer_log_whatsapp(filepath)
        except Exception as e:
            messagebox.showerror("Error", f"Error al leer el archivo:\n{e}")
            return

        if not mensajes_leidos:
            messagebox.showwarning("Aviso", "No se han encontrado mensajes válidos en el archivo.")
            return

        rango_previo = None
        if conservar_rango and filepath == self.filepath and self.rango_fechas_actual is not None:
            rango_previo = self.range_slider.get_values()

        self.filepath = filepath
        self.filename = Path(filepath).name
        self.mensajes_todos = mensajes_leidos
        self._asignar_colores_usuarios()
        # Si ningún mensaje trae segundos (Android), la hora se muestra como HH:MM
        self._formato_hora = "%H:%M:%S" if any(m.hora.second for m in self.mensajes_todos) else "%H:%M"
        self.limpiar_filtros_explorador(actualizar=False)
        self.lbl_status.config(text=f"Archivo: {self.filename} ({len(self.mensajes_todos)} mensajes leídos)")

        self.toggle_interface(enable=True)

        # Ej. 1: calcula_rango_fechas
        rango, estado_rango = self._invocar_util(
            "calcula_rango_fechas",
            f"utiles.calcula_rango_fechas(mensajes_todos)  # {len(self.mensajes_todos)} msgs",
            utiles.calcula_rango_fechas,
            self.mensajes_todos,
            validador=lambda r: self._validar_rango_fechas(r, self.mensajes_todos)
        )

        if estado_rango == "ok":
            fecha_min, fecha_max = rango
            self.rango_fechas_actual = (fecha_min, fecha_max)
            min_ord = fecha_min.toordinal()
            max_ord = fecha_max.toordinal()
            self.range_slider.set_range(min_ord, max_ord)
            if rango_previo is not None:
                self.range_slider.set_values(*rango_previo)
            self.range_slider.set_state("normal")
            self.btn_reset_range.config(state=tk.NORMAL)
            val_izq, val_der = self.range_slider.get_values()
            self.actualizar_etiquetas_drag(val_izq, val_der)
            self.ejecutar_filtro_release(val_izq, val_der)
        else:
            self.rango_fechas_actual = None
            self.range_slider.set_range(0, 100)
            self.range_slider.set_state("disabled")
            self.btn_reset_range.config(state=tk.DISABLED)
            self.str_fecha_inicio.set("--/--/----")
            self.str_fecha_fin.set("--/--/----")
            self.ejecutar_filtro_release(None, None)

    def restablecer_rango(self):
        if not self.mensajes_todos or not self.rango_fechas_actual:
            return
        fecha_min, fecha_max = self.rango_fechas_actual
        min_ord = fecha_min.toordinal()
        max_ord = fecha_max.toordinal()
        self.range_slider.set_range(min_ord, max_ord)
        self.actualizar_etiquetas_drag(min_ord, max_ord)
        self.ejecutar_filtro_release(min_ord, max_ord)

    def actualizar_etiquetas_drag(self, val_min, val_max):
        f_ini = date.fromordinal(int(val_min))
        f_fin = date.fromordinal(int(val_max))
        self.str_fecha_inicio.set(f_ini.strftime("%d/%m/%Y"))
        self.str_fecha_fin.set(f_fin.strftime("%d/%m/%Y"))

    def ejecutar_filtro_release(self, val_min, val_max):
        if not self.mensajes_todos:
            return

        if val_min is not None and val_max is not None:
            f_ini = date.fromordinal(int(val_min))
            f_fin = date.fromordinal(int(val_max))
            llamada_ej2 = (
                f"utiles.filtra_mensajes_por_fechas(mensajes_todos, "
                f"fecha_inicio={repr(f_ini)}, fecha_fin={repr(f_fin)})"
            )
        else:
            f_ini = None
            f_fin = None
            llamada_ej2 = "utiles.filtra_mensajes_por_fechas(mensajes_todos, fecha_inicio=None, fecha_fin=None)"

        filtrados, estado_filtro = self._invocar_util(
            "filtra_mensajes_por_fechas",
            llamada_ej2,
            utiles.filtra_mensajes_por_fechas,
            self.mensajes_todos,
            fecha_inicio=f_ini,
            fecha_fin=f_fin,
            validador=lambda r: self._validar_lista_mensajes(r, self.mensajes_todos, f_ini, f_fin)
        )

        avisos = []
        est_rango = self.registro_funciones["calcula_rango_fechas"]["estado"]
        if est_rango == "pending":
            avisos.append("⏳ Ej. 1 pendiente: implementa calcula_rango_fechas() para activar el deslizador.")
        elif est_rango == "error":
            avisos.append(f"❌ Error en calcula_rango_fechas() (Ej. 1): {self.registro_funciones['calcula_rango_fechas']['error']}")

        if estado_filtro == "ok":
            self.mensajes = filtrados
            self.var_kpi_msgs.set(f"✉️ {len(self.mensajes)}/{len(self.mensajes_todos)} msgs")
        else:
            self.mensajes = list(self.mensajes_todos)
            self.var_kpi_msgs.set(f"✉️ {len(self.mensajes_todos)} (sin filtrar)")
            if estado_filtro == "pending":
                avisos.append("⏳ Ej. 2 pendiente: implementa filtra_mensajes_por_fechas() para filtrar (mostrando todos).")
            else:
                avisos.append(f"❌ Error en filtra_mensajes_por_fechas() (Ej. 2): {self.registro_funciones['filtra_mensajes_por_fechas']['error']}")

        if avisos:
            self.lbl_aviso_filtro.config(text="   |   ".join(avisos))
            self.lbl_aviso_filtro.pack(fill=tk.X, pady=(self._s(3), 0))
        else:
            self.lbl_aviso_filtro.pack_forget()

        self.limpiar_filtros_explorador(actualizar=False)
        self.actualizar_graficas()

    # -------------------------------------------------------------------------
    # Validadores de tipos de retorno
    # -------------------------------------------------------------------------
    # Además del tipo, se comprueba la coherencia del resultado con los datos
    # reales del chat, para que "✅" no signifique solo "devuelve el tipo correcto".

    @staticmethod
    def _es_entero(valor):
        return isinstance(valor, int) and not isinstance(valor, bool)

    @staticmethod
    def _validar_rango_fechas(res, mensajes):
        if not isinstance(res, (tuple, list)) or len(res) != 2:
            return False, "Se esperaba una tupla (fecha_inicio, fecha_fin)."
        if not isinstance(res[0], date) or not isinstance(res[1], date):
            return False, "Los dos elementos de la tupla deben ser objetos datetime.date."
        if res[0] > res[1]:
            return False, f"La primera fecha ({res[0]:%d/%m/%Y}) es posterior a la segunda ({res[1]:%d/%m/%Y}). ¿Has invertido el orden?"
        primera, ultima = mensajes[0].fecha, mensajes[-1].fecha
        minima = min(m.fecha for m in mensajes)
        maxima = max(m.fecha for m in mensajes)
        if (res[0], res[1]) not in ((primera, ultima), (minima, maxima)):
            return False, (
                f"Se devolvió ({res[0]:%d/%m/%Y}, {res[1]:%d/%m/%Y}), pero el primer mensaje es del "
                f"{primera:%d/%m/%Y} y el último del {ultima:%d/%m/%Y}."
            )
        return True, ""

    @staticmethod
    def _validar_lista_mensajes(res, mensajes_todos, f_ini, f_fin):
        if not isinstance(res, list):
            return False, f"Se esperaba una list[Mensaje], pero devolvió {type(res).__name__}."
        for m in res:
            if not hasattr(m, "fecha"):
                return False, f"Los elementos de la lista deben ser tuplas Mensaje (se encontró {type(m).__name__})."

        def en_rango(m):
            return (f_ini is None or m.fecha >= f_ini) and (f_fin is None or m.fecha <= f_fin)

        fuera = [m for m in res if not en_rango(m)]
        if fuera:
            return False, f"Se han incluido mensajes fuera del rango (por ejemplo, uno del {fuera[0].fecha:%d/%m/%Y})."
        esperados = sum(1 for m in mensajes_todos if en_rango(m))
        if len(res) != esperados:
            return False, (
                f"Se devolvieron {len(res)} mensajes, pero hay {esperados} en el rango. "
                "Recuerda que las dos fechas límite están incluidas."
            )
        return True, ""

    @classmethod
    def _validar_conteo(cls, res, total, clave_valida, descripcion_claves):
        """Valida un diccionario de recuentos: claves correctas, valores enteros y suma = total de mensajes."""
        if not isinstance(res, dict):
            return False, f"Se esperaba un dict / Counter, pero devolvió {type(res).__name__}."
        for k, v in res.items():
            if not clave_valida(k):
                return False, f"Clave no válida: {k!r} (de tipo {type(k).__name__}). Las claves deben ser {descripcion_claves}."
            if not cls._es_entero(v):
                return False, f"El valor de la clave {k!r} es {v!r} ({type(v).__name__}); los recuentos deben ser enteros."
        suma = sum(res.values())
        if suma != total:
            return False, f"Los recuentos suman {suma}, pero hay {total} mensajes: cada mensaje debe contarse exactamente una vez."
        return True, ""

    def _validar_conteo_usuarios(self, res):
        usuarios = {m.usuario for m in self.mensajes}
        return self._validar_conteo(
            res, len(self.mensajes), lambda k: k in usuarios,
            "nombres de usuario (str) que aparecen en los mensajes"
        )

    def _validar_conteo_horas(self, res):
        return self._validar_conteo(
            res, len(self.mensajes), lambda k: self._es_entero(k) and 0 <= k <= 23,
            "enteros entre 0 y 23 (usa m.hora.hour)"
        )

    def _validar_conteo_dias(self, res):
        return self._validar_conteo(
            res, len(self.mensajes), lambda k: k in utiles.DIAS_SEMANA,
            "los nombres de DIAS_SEMANA ('Lunes', 'Martes', ..., 'Domingo')"
        )

    def _validar_longitudes(self, res):
        if not isinstance(res, dict):
            return False, f"Se esperaba un dict, pero devolvió {type(res).__name__}."
        usuarios = {m.usuario for m in self.mensajes}
        for k, v in res.items():
            if k not in usuarios:
                return False, f"Clave no válida: {k!r}. Las claves deben ser los usuarios que aparecen en los mensajes."
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                return False, f"La media de {k!r} es {v!r} ({type(v).__name__}); debe ser un número."
        faltan = sorted(usuarios - set(res))
        if faltan:
            return False, f"Falta la media de {len(faltan)} usuario(s), por ejemplo {faltan[0]!r}."
        return True, ""

    def _validar_dia_top(self, res):
        if not isinstance(res, (tuple, list)) or len(res) != 2:
            return False, "Se esperaba una tupla (fecha, numero_mensajes)."
        if not isinstance(res[0], date) or not self._es_entero(res[1]):
            return False, "La tupla debe contener (datetime.date, int)."
        por_dia = Counter(m.fecha for m in self.mensajes)
        reales = por_dia.get(res[0], 0)
        if res[1] != reales:
            return False, f"Según la función el {res[0]:%d/%m/%Y} hay {res[1]} mensajes, pero en realidad hay {reales}."
        maximo = max(por_dia.values())
        if reales < maximo:
            return False, f"El {res[0]:%d/%m/%Y} tiene {reales} mensajes, pero hay días con {maximo}."
        return True, ""

    def _validar_palabras(self, res, n):
        if not isinstance(res, list):
            return False, f"Se esperaba list[tuple[str, int]], pero devolvió {type(res).__name__}."
        if len(res) > n:
            return False, f"Se pidieron n={n} palabras, pero se devolvieron {len(res)}."
        for item in res:
            if not isinstance(item, (tuple, list)) or len(item) != 2:
                return False, f"Cada elemento debe ser una tupla (palabra, recuento); se encontró {item!r}."
            if not isinstance(item[0], str) or isinstance(item[1], bool) or not isinstance(item[1], (int, float)):
                return False, f"Cada tupla debe ser (str, int); se encontró {item!r}."
        return True, ""

    # -------------------------------------------------------------------------
    # Actualización de gráficas y paneles
    # -------------------------------------------------------------------------
    @staticmethod
    def _dibujar_placeholder(ax, texto, color_fondo="#F8FAFC", color_texto=COL_MUTED):
        ax.clear()
        ax.set_aspect("auto")
        ax.set_frame_on(True)
        ax.set_facecolor(color_fondo)
        ax.set_xticks([])
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_visible(True)
            spine.set_edgecolor(COL_BORDER)
            spine.set_linestyle("--")
        # Partimos las líneas largas (mensajes de error) para que no se salgan del recuadro
        texto = "\n".join(textwrap.fill(linea, 48) if linea else "" for linea in texto.split("\n"))
        ax.text(
            0.5, 0.5, texto,
            ha="center", va="center", transform=ax.transAxes,
            fontsize=10, color=color_texto, fontweight="bold"
        )

    def _mensaje_no_disponible(self, key, estado):
        ej = self.registro_funciones[key]["ejercicio"]
        if estado == "pending":
            return f"[Pendiente] {ej}\n\nImplementa {key}()\nen src/whatsapp_utiles.py"
        err = self.registro_funciones[key].get("error", "Error desconocido")
        return f"[Error] {key}() ({ej})\n\n{err}"

    # -------------------------------------------------------------------------
    # Cálculo (siempre) y dibujado (solo de la pestaña visible)
    # -------------------------------------------------------------------------
    # Las funciones del alumno se ejecutan siempre que cambian los mensajes, porque
    # de ellas dependen la barra de progreso y los indicadores. Dibujar es lo costoso
    # (sobre todo la nube de palabras y la tabla del explorador), así que cada pestaña
    # se marca como "pendiente" y solo se dibuja cuando está visible.

    def actualizar_graficas(self):
        self.res = {}
        if self.mensajes:
            self._calcular_resultados()
        self._actualizar_indicadores()
        self._calcular_palabras()
        self._pestanas_pendientes = set(self._pestanas.values())
        self._redibujar_visible()
        self._actualizar_barra_progreso()

    def _calcular_resultados(self):
        n_msgs = len(self.mensajes)
        llamadas = [
            ("cuenta_mensajes_por_usuario", self._validar_conteo_usuarios),
            ("calcula_longitud_media_por_usuario", self._validar_longitudes),
            ("cuenta_mensajes_por_hora", self._validar_conteo_horas),
            ("cuenta_mensajes_por_dia_semana", self._validar_conteo_dias),
            ("detecta_dia_mas_activo", self._validar_dia_top),
        ]
        for key, validador in llamadas:
            self.res[key] = self._invocar_util(
                key,
                f"utiles.{key}(mensajes)  # {n_msgs} msgs",
                getattr(utiles, key),
                self.mensajes,
                validador=validador
            )

    def _actualizar_indicadores(self):
        """KPIs, etiqueta del día récord y listas de usuarios de los desplegables."""
        botones_dia = (self.btn_ver_dia_kpi, self.btn_ver_dia_time, self.btn_exp_dia_top)
        if not self.mensajes:
            self.lbl_dia_top.config(text="📅 Día récord (Ej. 5): Sin mensajes en este rango", fg=COL_WA_DARK)
            self.var_kpi_top.set("🏆 Sin mensajes")
            self.var_kpi_users.set("👥 0 usuarios")
            for b in botones_dia:
                b.config(state=tk.DISABLED)
            self.dia_top_actual = None
            self.combo_users["values"] = []
            self.combo_users.set("")
            self.combo_exp_user["values"] = ["Todos"]
            self.combo_exp_user.set("Todos")
            return

        # Usuarios (Ej. 3.1)
        dict_msgs, est_users = self.res["cuenta_mensajes_por_usuario"]
        if est_users == "ok":
            self.var_kpi_users.set(f"👥 {len(dict_msgs)} usuarios")
        else:
            self.var_kpi_users.set("👥 Pendiente" if est_users == "pending" else "👥 Error")

        # Día más activo (Ej. 5)
        dia_top, est_top = self.res["detecta_dia_mas_activo"]
        if est_top == "ok" and dia_top:
            self.dia_top_actual = dia_top[0]
            fecha_str = dia_top[0].strftime("%d/%m/%Y")
            self.var_kpi_top.set(f"🏆 {fecha_str} ({dia_top[1]})")
            self.lbl_dia_top.config(text=f"📅 Día récord (Ej. 5): {fecha_str} ({dia_top[1]} msgs)", fg=COL_WA_DARK)
            for b in botones_dia:
                b.config(state=tk.NORMAL)
        else:
            self.dia_top_actual = None
            for b in botones_dia:
                b.config(state=tk.DISABLED)
            if est_top == "pending":
                self.var_kpi_top.set("🏆 Pendiente")
                self.lbl_dia_top.config(text="⏳ Ej. 5 pendiente: detecta_dia_mas_activo()", fg=COL_WARN_FG)
            else:
                self.var_kpi_top.set("🏆 Error")
                self.lbl_dia_top.config(text=f"❌ Error Ej. 5: {self.registro_funciones['detecta_dia_mas_activo']['error']}", fg=COL_ERR_FG)

        # Desplegables de usuarios (ordenados por actividad si el Ej. 3.1 funciona)
        if est_users == "ok" and dict_msgs:
            usuarios = [u for u, _ in sorted(dict_msgs.items(), key=lambda x: x[1], reverse=True)]
        else:
            usuarios = list(dict.fromkeys(m.usuario for m in self.mensajes))

        sel_nube = self.combo_users.get()
        self.combo_users["values"] = usuarios
        if sel_nube in usuarios:
            self.combo_users.set(sel_nube)
        elif usuarios:
            self.combo_users.current(0)
        else:
            self.combo_users.set("")

        sel_exp = self.combo_exp_user.get()
        valores_exp = ["Todos"] + usuarios
        self.combo_exp_user["values"] = valores_exp
        self.combo_exp_user.set(sel_exp if sel_exp in valores_exp else "Todos")

    def _al_cambiar_pestana(self, event=None):
        self._redibujar_visible()

    def _redibujar_visible(self):
        try:
            nombre = self._pestanas.get(self.notebook.select())
        except tk.TclError:
            return
        if nombre in self._pestanas_pendientes:
            self._dibujar_pestana(nombre)

    def _dibujar_pestana(self, nombre):
        self._pestanas_pendientes.discard(nombre)
        {
            "users": self._dibujar_usuarios,
            "time": self._dibujar_tiempo,
            "words": self._dibujar_palabras,
            "messages": self.actualizar_explorador,
        }[nombre]()

    def _agrupar_top(self, ordenados):
        """Divide una lista ordenada de (usuario, valor) en los TOP_USUARIOS primeros y el resto."""
        if len(ordenados) <= TOP_USUARIOS + 1:
            return ordenados, []
        return ordenados[:TOP_USUARIOS], ordenados[TOP_USUARIOS:]

    # --- Pestaña 1: usuarios --------------------------------------------------
    def _dibujar_usuarios(self):
        self._clicables["users"] = []
        if not self.mensajes:
            for ax in (self.ax_pie, self.ax_len):
                self._dibujar_placeholder(ax, "No hay mensajes en el rango de fechas seleccionado")
            self._notas_interaccion["users"].set_visible(False)
            self.canvas_users.draw()
            return

        # Donut de mensajes por usuario (Ej. 3.1)
        dict_msgs, est_users = self.res["cuenta_mensajes_por_usuario"]
        if est_users == "ok" and dict_msgs:
            ordenados = sorted(dict_msgs.items(), key=lambda x: x[1], reverse=True)
            visibles, otros = self._agrupar_top(ordenados)
            etiquetas = [u for u, _ in visibles]
            conteos = [c for _, c in visibles]
            colores = [self._color_de(u) for u in etiquetas]
            if otros:
                etiquetas.append(f"Otros ({len(otros)} usuarios)")
                conteos.append(sum(c for _, c in otros))
                colores.append(COL_USUARIO_OTROS)
            total = sum(conteos)

            self.ax_pie.clear()
            wedges, _, autotexts = self.ax_pie.pie(
                conteos,
                labels=None,
                colors=colores,
                autopct=lambda pct: f"{pct:.1f}%" if pct >= 4 else "",
                pctdistance=0.78,
                startangle=90,
                counterclock=False,
                wedgeprops=dict(width=0.42, edgecolor="white", linewidth=2)
            )
            self.ax_pie.set_aspect("equal")
            for at in autotexts:
                at.set_color("white")
                at.set_fontsize(8)
                at.set_fontweight("bold")
            self.ax_pie.text(0, 0, f"{total}\nmsgs", ha="center", va="center", fontsize=11, fontweight="bold", color=COL_WA_DARK)
            self.ax_pie.legend(
                wedges, [f"{u}: {c} ({c / total * 100:.1f}%)" for u, c in zip(etiquetas, conteos)],
                title="Participantes", loc="upper center", bbox_to_anchor=(0.5, -0.02),
                ncol=3 if len(etiquetas) > 6 else 2, fontsize=7.5, title_fontsize=8.5, frameon=False
            )
            self.ax_pie.set_title("Mensajes por usuario (Ej. 3.1)", fontsize=11, fontweight="bold", color=COL_WA_DARK)
            for wedge, (usuario, _) in zip(wedges, visibles):
                self._clicables["users"].append((wedge, ("usuario", usuario)))
        elif est_users == "ok":
            self._dibujar_placeholder(self.ax_pie, "El diccionario devuelto está vacío")
        else:
            self._dibujar_placeholder(self.ax_pie, self._mensaje_no_disponible("cuenta_mensajes_por_usuario", est_users))

        # Barras de longitud media (Ej. 4). Se muestran los usuarios más activos
        # y el resto se agrupa en "Otros" (media ponderada por número de mensajes).
        dict_len, est_len = self.res["calcula_longitud_media_por_usuario"]
        if est_len == "ok" and dict_len:
            actividad = Counter(m.usuario for m in self.mensajes)
            por_actividad = sorted(dict_len.items(), key=lambda x: actividad[x[0]], reverse=True)
            visibles, otros = self._agrupar_top(por_actividad)
            filas = sorted(visibles, key=lambda x: x[1])
            barras_datos = [(u, media, self._color_de(u), u) for u, media in filas]
            if otros:
                n_otros = sum(actividad[u] for u, _ in otros)
                media_otros = sum(media * actividad[u] for u, media in otros) / n_otros if n_otros else 0
                barras_datos.insert(0, (f"Otros ({len(otros)})", media_otros, COL_USUARIO_OTROS, None))

            self.ax_len.clear()
            self.ax_len.set_aspect("auto")
            self.ax_len.set_facecolor(COL_CARD)
            medias_l = [d[1] for d in barras_datos]
            bars = self.ax_len.barh([d[0] for d in barras_datos], medias_l, color=[d[2] for d in barras_datos], height=0.6)
            max_m = max(medias_l) if medias_l else 1
            self.ax_len.set_xlim(0, max_m * 1.24 if max_m > 0 else 1)
            for bar, val in zip(bars, medias_l):
                self.ax_len.text(
                    bar.get_width() + max_m * 0.02,
                    bar.get_y() + bar.get_height() / 2,
                    f"{val:.1f} car.",
                    va="center", ha="left", fontsize=8, fontweight="bold", color=COL_TEXT
                )
            self.ax_len.set_title("Longitud media por usuario (Ej. 4)", fontsize=11, fontweight="bold", color=COL_WA_DARK)
            self.ax_len.set_xlabel("Caracteres por mensaje", fontsize=9)
            self.ax_len.grid(axis="x", linestyle="--", alpha=0.4)
            self.ax_len.spines["top"].set_visible(False)
            self.ax_len.spines["right"].set_visible(False)
            for bar, datos in zip(bars, barras_datos):
                if datos[3] is not None:
                    self._clicables["users"].append((bar, ("usuario", datos[3])))
        elif est_len == "ok":
            self._dibujar_placeholder(self.ax_len, "El diccionario devuelto está vacío")
        else:
            self._dibujar_placeholder(self.ax_len, self._mensaje_no_disponible("calcula_longitud_media_por_usuario", est_len))

        self._notas_interaccion["users"].set_visible(bool(self._clicables["users"]))
        self.fig_users.tight_layout(pad=2.0, rect=(0, 0.03, 1, 1))
        self.canvas_users.draw()

    # --- Pestaña 2: análisis temporal ----------------------------------------
    def _dibujar_tiempo(self):
        self._clicables["time"] = []
        if not self.mensajes:
            for ax in (self.ax_hour, self.ax_week):
                self._dibujar_placeholder(ax, "No hay mensajes en el rango de fechas seleccionado")
            self._notas_interaccion["time"].set_visible(False)
            self.canvas_time.draw()
            return

        # Actividad por hora 0-23h (Ej. 3.2)
        dict_horas, est_horas = self.res["cuenta_mensajes_por_hora"]
        if est_horas == "ok":
            horas = list(range(24))
            conteos_h = [dict_horas.get(h, 0) for h in horas]
            max_h = max(conteos_h) if conteos_h else 0
            colores_h = [COL_WA_DARK if (c == max_h and max_h > 0) else "#74C69D" for c in conteos_h]

            self.ax_hour.clear()
            self.ax_hour.set_aspect("auto")
            self.ax_hour.set_facecolor(COL_CARD)
            bars_h = self.ax_hour.bar(horas, conteos_h, color=colores_h, edgecolor="white", width=0.78)
            self.ax_hour.set_xticks(horas)
            self.ax_hour.set_xticklabels([f"{h:02d}" for h in horas], fontsize=7.5)
            self.ax_hour.set_ylim(0, max_h * 1.16 + 1 if max_h > 0 else 5)
            for bar, c in zip(bars_h, conteos_h):
                if c > 0:
                    self.ax_hour.text(
                        bar.get_x() + bar.get_width() / 2,
                        bar.get_height() + max(max_h * 0.02, 0.15),
                        str(int(c)),
                        ha="center", va="bottom", fontsize=7.5, fontweight="bold", color=COL_TEXT
                    )
            self.ax_hour.set_title("Actividad por hora del día (Ej. 3.2)", fontsize=11, fontweight="bold", color=COL_WA_DARK)
            self.ax_hour.set_xlabel("Hora (00h – 23h)", fontsize=9)
            self.ax_hour.set_ylabel("Mensajes", fontsize=9)
            self.ax_hour.grid(axis="y", linestyle="--", alpha=0.4)
            self.ax_hour.spines["top"].set_visible(False)
            self.ax_hour.spines["right"].set_visible(False)
            for bar, h, c in zip(bars_h, horas, conteos_h):
                if c > 0:
                    self._clicables["time"].append((bar, ("hora", h)))
        else:
            self._dibujar_placeholder(self.ax_hour, self._mensaje_no_disponible("cuenta_mensajes_por_hora", est_horas))

        # Actividad por día de la semana (Ej. 3.3)
        dict_dias, est_dias = self.res["cuenta_mensajes_por_dia_semana"]
        if est_dias == "ok":
            dias_ord = list(utiles.DIAS_SEMANA)
            conteos_d = [dict_dias.get(d, 0) for d in dias_ord]
            max_d = max(conteos_d) if conteos_d else 0
            colores_d = [COL_WA_TEAL if (c == max_d and max_d > 0) else "#52B788" for c in conteos_d]

            self.ax_week.clear()
            self.ax_week.set_aspect("auto")
            self.ax_week.set_facecolor(COL_CARD)
            bars_d = self.ax_week.bar(dias_ord, conteos_d, color=colores_d, edgecolor="white", width=0.58)
            self.ax_week.set_ylim(0, max_d * 1.16 + 1 if max_d > 0 else 5)
            self.ax_week.tick_params(axis="x", labelsize=8)
            for bar, c in zip(bars_d, conteos_d):
                self.ax_week.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + max(max_d * 0.02, 0.15),
                    str(int(c)),
                    ha="center", va="bottom", fontsize=8, fontweight="bold", color=COL_TEXT
                )
            self.ax_week.set_title("Actividad por día de la semana (Ej. 3.3)", fontsize=11, fontweight="bold", color=COL_WA_DARK)
            self.ax_week.set_xlabel("Día de la semana", fontsize=9)
            self.ax_week.set_ylabel("Mensajes", fontsize=9)
            self.ax_week.grid(axis="y", linestyle="--", alpha=0.4)
            self.ax_week.spines["top"].set_visible(False)
            self.ax_week.spines["right"].set_visible(False)
            for bar, d, c in zip(bars_d, dias_ord, conteos_d):
                if c > 0:
                    self._clicables["time"].append((bar, ("dia_semana", d)))
        else:
            self._dibujar_placeholder(self.ax_week, self._mensaje_no_disponible("cuenta_mensajes_por_dia_semana", est_dias))

        self._notas_interaccion["time"].set_visible(bool(self._clicables["time"]))
        self.fig_time.tight_layout(pad=2.0, rect=(0, 0.03, 1, 1))
        self.canvas_time.draw()

    # --- Pestaña 3: nube de palabras -----------------------------------------
    def _limpiar_tabla_palabras(self):
        for item in self.tree_words.get_children():
            self.tree_words.delete(item)

    def actualizar_palabras(self, event=None):
        """Se llama al cambiar el usuario o n: recalcula el Ej. 6 y redibuja la pestaña."""
        if not self.mensajes:
            return
        self._calcular_palabras()
        self._dibujar_pestana("words")
        self._actualizar_barra_progreso()

    def _calcular_palabras(self):
        self.res_palabras = None
        user_sel = self.combo_users.get()
        if not self.mensajes or not user_sel:
            return
        try:
            n_val = int(self.combo_n.get())
        except ValueError:
            n_val = 100
        palabras, est = self._invocar_util(
            "analiza_palabras_caracteristicas",
            f"utiles.analiza_palabras_caracteristicas(mensajes, usuario={repr(user_sel)}, n={n_val})",
            utiles.analiza_palabras_caracteristicas,
            self.mensajes,
            user_sel,
            n=n_val,
            validador=lambda r: self._validar_palabras(r, n_val)
        )
        self.res_palabras = (palabras, est, user_sel, n_val)

    def _dibujar_palabras(self):
        self._limpiar_tabla_palabras()
        self.ax_words.clear()
        self.ax_words.axis("off")
        self.fig_words.subplots_adjust(left=0.04, right=0.96, top=0.96, bottom=0.04)

        if not self.mensajes:
            self._dibujar_placeholder(self.ax_words, "No hay mensajes en el rango de fechas seleccionado")
            self.canvas_words.draw()
            return
        if self.res_palabras is None:
            self._dibujar_placeholder(self.ax_words, "No hay usuarios disponibles")
            self.canvas_words.draw()
            return

        palabras_res, est_pal, user_sel, n_val = self.res_palabras
        if est_pal != "ok":
            self.lbl_words_title.config(
                text=f"📌 Ej. 6: utiles.analiza_palabras_caracteristicas(mensajes, {repr(user_sel)}, n={n_val})"
            )
            self._dibujar_placeholder(self.ax_words, self._mensaje_no_disponible("analiza_palabras_caracteristicas", est_pal))
            self.canvas_words.draw()
            return

        for idx, (palabra, puntos) in enumerate(palabras_res, start=1):
            tag = "pos" if puntos > 0 else "nonpos"
            self.tree_words.insert("", tk.END, values=(idx, palabra, puntos), tags=(tag,))

        frecuencias_positivas = {p: c for p, c in palabras_res if c > 0}
        self.lbl_words_title.config(
            text=f"📌 Ej. 6: analiza_palabras_caracteristicas(mensajes, {repr(user_sel)}, n={n_val})  —  {len(frecuencias_positivas)} positivas"
        )

        if not frecuencias_positivas:
            self._dibujar_placeholder(
                self.ax_words,
                f"Sin palabras con puntuación positiva (> 0) para {user_sel}\nen el rango seleccionado."
            )
        else:
            # La nube se genera al tamaño real del panel, con distribución reproducible
            widget = self.canvas_words.get_tk_widget()
            ancho, alto = widget.winfo_width(), widget.winfo_height()
            if ancho < 100 or alto < 100:
                ancho, alto = 1100, 620
            self._tamano_nube = (ancho, alto)
            wc = WordCloud(
                background_color="white",
                width=ancho,
                height=alto,
                margin=2,
                max_words=n_val,
                random_state=42,
                color_func=color_palabra_whatsapp
            ).generate_from_frequencies(frecuencias_positivas)
            self.ax_words.imshow(wc, interpolation="bilinear")
            self.fig_words.subplots_adjust(left=0, right=1, top=1, bottom=0)

        self.canvas_words.draw()

    def _al_redimensionar_nube(self, event):
        """Regenera la nube (con un pequeño retardo) si el panel cambia bastante de tamaño."""
        anterior = getattr(self, "_tamano_nube", None)
        if anterior is None or (abs(event.width - anterior[0]) < 40 and abs(event.height - anterior[1]) < 40):
            return
        if self._after_nube:
            self.root.after_cancel(self._after_nube)

        def regenerar():
            self._after_nube = None
            if self.mensajes and self.res_palabras:
                self._pestanas_pendientes.add("words")
                self._redibujar_visible()

        self._after_nube = self.root.after(300, regenerar)

    def _al_pulsar_palabra(self, event):
        fila = self.tree_words.identify_row(event.y)
        if not fila:
            return
        palabra = self.tree_words.item(fila)["values"][1]
        self.mostrar_en_explorador(usuario=self.combo_users.get() or "Todos", palabra=str(palabra))

    # --- Interacción con las gráficas y exportación ---------------------------
    def _conectar_clics(self, canvas, nombre):
        """Cambia el cursor sobre los elementos clicables de una figura y gestiona el clic."""
        widget = canvas.get_tk_widget()

        def buscar(event):
            if event.inaxes is None:
                return None
            for artista, accion in self._clicables.get(nombre, []):
                if artista.axes is event.inaxes and artista.contains(event)[0]:
                    return accion
            return None

        def al_mover(event):
            widget.config(cursor="hand2" if buscar(event) else "")

        def al_pulsar(event):
            if event.button != 1:
                return
            accion = buscar(event)
            if accion is None:
                return
            tipo, valor = accion
            if tipo == "usuario":
                self.mostrar_en_explorador(usuario=valor)
            elif tipo == "hora":
                self.mostrar_en_explorador(hora=valor)
            elif tipo == "dia_semana":
                self.mostrar_en_explorador(dia_semana=valor)

        canvas.mpl_connect("motion_notify_event", al_mover)
        canvas.mpl_connect("button_press_event", al_pulsar)

    def exportar_png(self, pestana):
        figuras = {"users": self.fig_users, "time": self.fig_time, "words": self.fig_words}
        nombres = {"users": "actividad_usuarios", "time": "analisis_temporal", "words": "nube_palabras"}
        if pestana in self._pestanas_pendientes:
            self._dibujar_pestana(pestana)
        base = Path(self.filename).stem if self.filename else "chat"
        ruta = filedialog.asksaveasfilename(
            parent=self.root,
            title="Guardar gráfica como imagen",
            defaultextension=".png",
            initialfile=f"{nombres[pestana]}_{base}.png",
            filetypes=[("Imagen PNG", "*.png")]
        )
        if not ruta:
            return
        try:
            figuras[pestana].savefig(ruta, dpi=150, facecolor=COL_CARD)
        except Exception as exc:
            messagebox.showerror("Error al guardar", f"No se pudo guardar la imagen:\n{exc}")

    # -------------------------------------------------------------------------
    # Pestaña 4: Explorador de Mensajes
    # -------------------------------------------------------------------------
    def mostrar_en_explorador(self, usuario="Todos", **filtros):
        """Abre el explorador con un usuario y filtros (dia, hora, dia_semana, palabra)."""
        if not self.mensajes:
            return
        self.filtros_explorador = {k: v for k, v in filtros.items() if v is not None}
        valores = self.combo_exp_user["values"]
        self.combo_exp_user.set(usuario if usuario in valores else "Todos")
        self.var_exp_search.set("")
        self._actualizar_boton_filtros()
        self._pestanas_pendientes.add("messages")
        self.notebook.select(self.tab_messages)
        self._redibujar_visible()

    def ver_mensajes_dia_activo(self):
        if self.dia_top_actual:
            self.mostrar_en_explorador(dia=self.dia_top_actual)

    def limpiar_filtros_explorador(self, actualizar=True):
        self.filtros_explorador = {}
        self._actualizar_boton_filtros()
        if actualizar:
            self.actualizar_explorador()

    def _actualizar_boton_filtros(self):
        f = self.filtros_explorador
        partes = []
        if "dia" in f:
            partes.append(f"día {f['dia']:%d/%m/%Y}")
        if "hora" in f:
            partes.append(f"de {f['hora']:02d}:00 a {f['hora']:02d}:59")
        if "dia_semana" in f:
            partes.append(f"solo {f['dia_semana'].lower()}")
        if "palabra" in f:
            partes.append(f"palabra «{f['palabra']}»")
        if partes:
            self.btn_exp_filtros.config(text="✖ Quitar filtro: " + " · ".join(partes))
            self.btn_exp_filtros.pack(side=tk.LEFT, padx=(0, self._s(6)))
        else:
            self.btn_exp_filtros.pack_forget()

    def _programar_busqueda(self):
        """Espera a que se deje de teclear antes de filtrar (evita reconstruir la tabla en cada tecla)."""
        if self._after_busqueda:
            self.root.after_cancel(self._after_busqueda)
        self._after_busqueda = self.root.after(250, self._ejecutar_busqueda)

    def _ejecutar_busqueda(self):
        self._after_busqueda = None
        self.actualizar_explorador()

    def ordenar_explorador(self, columna):
        """Ordena por la columna pulsada; si ya estaba ordenada por ella, invierte el orden."""
        if self._orden_explorador and self._orden_explorador[0] == columna:
            self._orden_explorador = (columna, not self._orden_explorador[1])
        else:
            self._orden_explorador = (columna, False)
        for col, titulo, *_ in self.COLUMNAS_EXPLORADOR:
            flecha = ""
            if col == columna:
                flecha = " ▼" if self._orden_explorador[1] else " ▲"
            self.tree_messages.heading(col, text=titulo + flecha)
        self.actualizar_explorador()

    def actualizar_explorador(self):
        self._pestanas_pendientes.discard("messages")
        self.tree_messages.delete(*self.tree_messages.get_children())
        self._mensajes_vista_map = {}

        if not self.mensajes:
            self.lbl_exp_count.config(text="0 mensajes")
            return

        user_sel = self.combo_exp_user.get()
        texto_busq = self.var_exp_search.get().strip().lower()
        f = self.filtros_explorador

        filtrados_vista = []
        for idx, m in enumerate(self.mensajes, start=1):
            if "dia" in f and m.fecha != f["dia"]:
                continue
            if "hora" in f and m.hora.hour != f["hora"]:
                continue
            if "dia_semana" in f and utiles.DIAS_SEMANA[m.fecha.weekday()] != f["dia_semana"]:
                continue
            if "palabra" in f and f["palabra"] not in m.texto.lower().split():
                continue
            if user_sel and user_sel != "Todos" and m.usuario != user_sel:
                continue
            if texto_busq and texto_busq not in m.texto.lower() and texto_busq not in m.usuario.lower():
                continue
            filtrados_vista.append((idx, m))

        if self._orden_explorador:
            columna, descendente = self._orden_explorador
            claves = {
                "idx": lambda par: par[0],
                "fecha": lambda par: (par[1].fecha, par[1].hora, par[0]),
                "hora": lambda par: (par[1].hora, par[0]),
                "usuario": lambda par: (par[1].usuario.lower(), par[0]),
                "texto": lambda par: (par[1].texto.lower(), par[0]),
            }
            filtrados_vista.sort(key=claves[columna], reverse=descendente)

        # Con chats muy grandes, insertar decenas de miles de filas bloquea la interfaz
        mostrados = filtrados_vista[:MAX_FILAS_EXPLORADOR]
        for idx_orig, m in mostrados:
            tag_u = self.tag_usuario.get(m.usuario)
            iid = self.tree_messages.insert(
                "", tk.END,
                values=(
                    idx_orig, m.fecha.strftime("%d/%m/%Y"), m.hora.strftime(self._formato_hora),
                    m.usuario, m.texto.replace("\n", " ⏎ ")
                ),
                tags=(tag_u,) if tag_u else ()
            )
            self._mensajes_vista_map[iid] = m

        texto_cuenta = f"Mostrando {len(filtrados_vista)} de {len(self.mensajes)} mensajes"
        if len(filtrados_vista) > len(mostrados):
            texto_cuenta = (
                f"Mostrando los primeros {len(mostrados)} de {len(filtrados_vista)} coincidencias "
                f"({len(self.mensajes)} mensajes) · usa los filtros para acotar"
            )
        self.lbl_exp_count.config(text=texto_cuenta)

    def _on_select_mensaje(self, event=None):
        sel = self.tree_messages.selection()
        if not sel:
            return
        m = self._mensajes_vista_map.get(sel[0])
        if m is None:
            return
        cabecera = f"{m.usuario} · {m.fecha:%d/%m/%Y} {m.hora.strftime(self._formato_hora)}"
        self.lbl_mensaje_texto.config(text=f"{cabecera}\n{m.texto}")
        self.lbl_mensaje_texto.pack(fill=tk.X, before=self.lbl_mensaje_tupla, pady=(0, self._s(4)))
        self.lbl_mensaje_tupla.config(text=f"Tupla en Python → {repr(m)}")


if __name__ == "__main__":
    root = tk.Tk()
    app = WhatsAppAnalyzerApp(root)
    root.mainloop()
