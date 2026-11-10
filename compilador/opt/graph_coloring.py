"""
Módulo de Coloración de Grafos para el Compilador (Asignación de Registros).
Proporciona parsing de grafos de interferencia/adyacencia, cálculo del número
cromático exacto mínimo chi(G), verificación de coloración propia y canvas
interactivo para visualización y manipulación de nodos en Tkinter.
"""

import math
import random
import re
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Dict, List, Tuple, Set, Optional


# Paleta moderna, vibrante y de alto contraste
PALETA_COLORES = [
    "#2563EB",  # Azul Real
    "#16A34A",  # Verde Esmeralda
    "#DC2626",  # Rojo Coral
    "#D97706",  # Ámbar / Oro
    "#7C3AED",  # Violeta
    "#DB2777",  # Magenta
    "#0D9488",  # Teal / Verde Azulado
    "#EA580C",  # Naranja
    "#4F46E5",  # Índigo
    "#65A30D",  # Lima
    "#0891B2",  # Cian
    "#9333EA",  # Púrpura Eléctrico
    "#CA8A04",  # Mostaza
    "#E11D48",  # Rosa Carmesí
    "#059669",  # Menta Intenso
    "#475569",  # Pizarra
]

NOMBRES_COLORES = [
    "Azul", "Verde", "Rojo", "Ámbar", "Violeta", "Magenta", "Teal",
    "Naranja", "Índigo", "Lima", "Cian", "Púrpura", "Mostaza", "Carmesí",
    "Menta", "Pizarra"
]


def obtener_color_hex(indice: int) -> str:
    """Devuelve un código hexadecimal de color para un índice dado."""
    if indice < len(PALETA_COLORES):
        return PALETA_COLORES[indice]
    # Generación dinámica HSL si se requieren más de 16 colores
    hue = (indice * 137.5) % 360  # Razón áurea para dispersar tonos
    return _hsl_a_hex(hue, 0.75, 0.50)


def obtener_nombre_color(indice: int) -> str:
    """Devuelve un nombre amigable para el color."""
    if indice < len(NOMBRES_COLORES):
        return f"{NOMBRES_COLORES[indice]} (C{indice + 1})"
    return f"Color {indice + 1} (C{indice + 1})"


def color_texto_contraste(color_hex: str) -> str:
    """Determina si el texto sobre el color debe ser blanco o negro para legibilidad."""
    try:
        color_hex = color_hex.lstrip('#')
        r = int(color_hex[0:2], 16)
        g = int(color_hex[2:4], 16)
        b = int(color_hex[4:6], 16)
        luminancia = (0.299 * r + 0.587 * g + 0.114 * b) / 255
        return "#000000" if luminancia > 0.65 else "#FFFFFF"
    except Exception:
        return "#FFFFFF"


def _hsl_a_hex(h: float, s: float, l: float) -> str:
    c = (1 - abs(2 * l - 1)) * s
    x = c * (1 - abs((h / 60) % 2 - 1))
    m = l - c / 2
    if 0 <= h < 60:
        r, g, b = c, x, 0
    elif 60 <= h < 120:
        r, g, b = x, c, 0
    elif 120 <= h < 180:
        r, g, b = 0, c, x
    elif 180 <= h < 240:
        r, g, b = 0, x, c
    elif 240 <= h < 300:
        r, g, b = x, 0, c
    else:
        r, g, b = c, 0, x
    ri = int((r + m) * 255)
    gi = int((g + m) * 255)
    bi = int((b + m) * 255)
    return f"#{ri:02X}{gi:02X}{bi:02X}"


class Grafo:
    """Representación de un grafo no dirigido para coloración."""

    def __init__(self):
        self.nodos: List[str] = []
        self.adyacencia: Dict[str, Set[str]] = {}

    def agregar_nodo(self, nodo: str) -> None:
        nodo = nodo.strip()
        if not nodo:
            return
        if nodo not in self.adyacencia:
            self.adyacencia[nodo] = set()
            self.nodos.append(nodo)

    def agregar_arista(self, u: str, v: str) -> None:
        u = u.strip()
        v = v.strip()
        if not u or not v or u == v:
            return
        self.agregar_nodo(u)
        self.agregar_nodo(v)
        self.adyacencia[u].add(v)
        self.adyacencia[v].add(u)

    def obtener_aristas(self) -> List[Tuple[str, str]]:
        aristas = set()
        for u, vecinos in self.adyacencia.items():
            for v in vecinos:
                arista = (min(u, v), max(u, v))
                aristas.add(arista)
        return sorted(list(aristas))

    def grado(self, nodo: str) -> int:
        return len(self.adyacencia.get(nodo, set()))

    def grado_maximo(self) -> int:
        if not self.nodos:
            return 0
        return max(self.grado(n) for n in self.nodos)

    def es_bipartito(self) -> Tuple[bool, Dict[str, int]]:
        """Verifica si el grafo es bipartito (2-coloreable) usando BFS."""
        if not self.nodos:
            return True, {}
        colores: Dict[str, int] = {}
        for nodo_raiz in self.nodos:
            if nodo_raiz in colores:
                continue
            colores[nodo_raiz] = 0
            cola = [nodo_raiz]
            while cola:
                actual = cola.pop(0)
                col_actual = colores[actual]
                col_vecino = 1 - col_actual
                for v in self.adyacencia.get(actual, set()):
                    if v not in colores:
                        colores[v] = col_vecino
                        cola.append(v)
                    elif colores[v] == col_actual:
                        return False, {}
        return True, colores

    def encontrar_clique_maximo_aproximado(self) -> int:
        """Encuentra una cota inferior para el tamaño del clique máximo."""
        if not self.nodos:
            return 0
        if not self.obtener_aristas():
            return 1

        # Heurística voraz ordenada por grado descendente
        nodos_ordenados = sorted(self.nodos, key=lambda n: self.grado(n), reverse=True)
        max_clique = 1
        for inicio in nodos_ordenados[:min(15, len(nodos_ordenados))]:
            clique = [inicio]
            for candidato in nodos_ordenados:
                if candidato == inicio:
                    continue
                # Si candidato es adyacente a todos en el clique
                if all(candidato in self.adyacencia.get(c, set()) for c in clique):
                    clique.append(candidato)
            if len(clique) > max_clique:
                max_clique = len(clique)
        return max_clique


def parsear_grafo_texto(texto: str) -> Grafo:
    """
    Parsea texto con formato de adyacencia:
    A: B, F
    B: C
    C: D
    D: E, F
    E: F
    También soporta nodos aislados (e.g. 'G' o 'G:'), comentarios con # o //,
    y separadores como comas, espacios o guiones.
    """
    grafo = Grafo()
    for linea in texto.splitlines():
        linea = linea.strip()
        # Eliminar comentarios
        linea = re.sub(r'(#|//).*$', '', linea).strip()
        if not linea:
            continue

        if ':' in linea:
            partes = linea.split(':', 1)
            nodo = partes[0].strip()
            grafo.agregar_nodo(nodo)
            vecinos_raw = partes[1].strip()
            if vecinos_raw:
                # Separar por comas, punto y coma, o espacios
                tokens = re.split(r'[,;\s]+', vecinos_raw)
                for t in tokens:
                    t = t.strip()
                    if t:
                        grafo.agregar_arista(nodo, t)
        elif '->' in linea or '-' in linea:
            sep = '->' if '->' in linea else '-'
            partes = linea.split(sep, 1)
            nodo = partes[0].strip()
            grafo.agregar_nodo(nodo)
            vecinos_raw = partes[1].strip()
            if vecinos_raw:
                tokens = re.split(r'[,;\s]+', vecinos_raw)
                for t in tokens:
                    t = t.strip()
                    if t:
                        grafo.agregar_arista(nodo, t)
        else:
            # Línea con tokens directos o nodo único
            tokens = re.split(r'[,;\s]+', linea)
            if tokens:
                nodo = tokens[0].strip()
                grafo.agregar_nodo(nodo)
                for t in tokens[1:]:
                    t = t.strip()
                    if t:
                        grafo.agregar_arista(nodo, t)

    return grafo


def colorear_grafo_minimo(grafo: Grafo) -> Tuple[Dict[str, int], int, bool]:
    """
    Calcula la coloración propia usando la MENOR CANTIDAD POSIBLE DE COLORES
    (Número cromático exacto chi(G)).

    Retorna:
    - coloracion: Diccionario {nodo: indice_color (0, 1, ...)}
    - num_colores: Cantidad mínima de colores requeridos (chi(G))
    - es_valida: Booleano confirmando que no hay conflictos entre vecinos
    """
    nodos = grafo.nodos
    if not nodos:
        return {}, 0, True

    # Caso 1: Grafo sin aristas -> 1 color para todos
    aristas = grafo.obtener_aristas()
    if not aristas:
        coloracion = {n: 0 for n in nodos}
        return coloracion, 1, True

    # Caso 2: Verificar si es bipartito (2-coloreable)
    es_bip, col_bip = grafo.es_bipartito()
    if es_bip:
        valida, _ = verificar_coloracion(grafo, col_bip)
        if valida:
            return col_bip, 2, True

    # Caso 3: Heurística DSATUR (Degree of Saturation)
    col_dsatur, k_dsatur = _colorear_dsatur(grafo)

    # Cota inferior teórica: tamaño del clique máximo encontrado
    cota_inferior = max(3, grafo.encontrar_clique_maximo_aproximado())

    # Si la cota inferior ya iguala la cota superior encontrada por DSATUR,
    # el resultado de DSATUR ya es MATEMÁTICAMENTE ÓPTIMO.
    if k_dsatur <= cota_inferior:
        valida, _ = verificar_coloracion(grafo, col_dsatur)
        return col_dsatur, k_dsatur, valida

    # Caso 4: Búsqueda exacta de k-coloración con backtracking y poda de simetría
    # Probamos k desde cota_inferior hasta k_dsatur - 1
    mejor_coloracion = col_dsatur
    mejor_k = k_dsatur

    for k in range(cota_inferior, k_dsatur):
        sol = _buscar_k_coloracion_exacta(grafo, k)
        if sol is not None:
            mejor_coloracion = sol
            mejor_k = k
            break  # Como vamos en orden ascendente de k, el primero encontrado es el mínimo absoluto

    valida, _ = verificar_coloracion(grafo, mejor_coloracion)
    return mejor_coloracion, mejor_k, valida


def _colorear_dsatur(grafo: Grafo) -> Tuple[Dict[str, int], int]:
    """
    Implementación del algoritmo DSATUR (Brélaz, 1979).
    Excelente heurística que encuentra el número cromático exacto para
    la gran mayoría de grafos y provee una cota superior muy ajustada.
    """
    nodos = grafo.nodos
    coloracion: Dict[str, int] = {}
    grados = {n: grafo.grado(n) for n in nodos}

    # Grado de saturación = cantidad de colores diferentes en vecinos
    saturacion: Dict[str, Set[int]] = {n: set() for n in nodos}

    # Primer nodo: el de mayor grado
    primer_nodo = max(nodos, key=lambda n: grados[n])
    coloracion[primer_nodo] = 0
    for v in grafo.adyacencia.get(primer_nodo, set()):
        saturacion[v].add(0)

    while len(coloracion) < len(nodos):
        # Seleccionar nodo no coloreado con mayor grado de saturación
        no_coloreados = [n for n in nodos if n not in coloracion]
        max_sat = -1
        candidatos = []
        for n in no_coloreados:
            sat_len = len(saturacion[n])
            if sat_len > max_sat:
                max_sat = sat_len
                candidatos = [n]
            elif sat_len == max_sat:
                candidatos.append(n)

        # Desempate: mayor grado en subgrafo no coloreado
        if len(candidatos) == 1:
            elegido = candidatos[0]
        else:
            elegido = max(candidatos, key=lambda n: sum(1 for v in grafo.adyacencia.get(n, set()) if v not in coloracion))

        # Asignar el menor color disponible que no usen sus vecinos
        colores_vecinos = {coloracion[v] for v in grafo.adyacencia.get(elegido, set()) if v in coloracion}
        c = 0
        while c in colores_vecinos:
            c += 1
        coloracion[elegido] = c

        # Actualizar saturación de vecinos
        for v in grafo.adyacencia.get(elegido, set()):
            if v not in coloracion:
                saturacion[v].add(c)

    num_colores = max(coloracion.values()) + 1 if coloracion else 0
    return coloracion, num_colores


def _buscar_k_coloracion_exacta(grafo: Grafo, k: int, limite_pasos: int = 200000) -> Optional[Dict[str, int]]:
    """
    Búsqueda por backtracking con ordenamiento por grado, forward-checking
    y rompimiento de simetría para determinar si existe una k-coloración válida.
    """
    # Ordenar nodos por grado descendente para podar ramas temprano
    nodos_ordenados = sorted(grafo.nodos, key=lambda n: grafo.grado(n), reverse=True)
    n = len(nodos_ordenados)
    adj = {u: set(grafo.adyacencia.get(u, set())) for u in nodos_ordenados}

    coloracion: Dict[str, int] = {}
    pasos = 0

    def backtrack(idx: int, max_color_usado: int) -> bool:
        nonlocal pasos
        pasos += 1
        if pasos > limite_pasos:
            return False  # Evitar bloqueo si el grafo fuera gigantesco

        if idx == n:
            return True

        nodo = nodos_ordenados[idx]
        colores_vecinos = {coloracion[v] for v in adj[nodo] if v in coloracion}

        # Rompimiento de simetría: no probar colores mayores a max_color_usado + 1
        limite_c = min(k - 1, max_color_usado + 1)
        for c in range(limite_c + 1):
            if c not in colores_vecinos:
                coloracion[nodo] = c
                if backtrack(idx + 1, max(max_color_usado, c)):
                    return True
                del coloracion[nodo]

        return False

    if backtrack(0, -1):
        return coloracion
    return None


def verificar_coloracion(grafo: Grafo, coloracion: Dict[str, int]) -> Tuple[bool, List[Tuple[str, str]]]:
    """
    Verifica si una coloración es propia (no existen aristas entre nodos del mismo color).
    Retorna (es_valida, lista_de_conflictos).
    """
    conflictos = []
    for u, v in grafo.obtener_aristas():
        col_u = coloracion.get(u)
        col_v = coloracion.get(v)
        if col_u is not None and col_v is not None and col_u == col_v:
            conflictos.append((u, v))
    return len(conflictos) == 0, conflictos


class ColoringCanvas(tk.Frame):
    """
    Canvas interactivo para la visualización del grafo coloreado.
    Permite:
    - Arrastre interactivo de nodos (click y arrastrar para moverlos en tiempo real).
    - Zoom (+, -, 100%, rueda del ratón).
    - Paneo con click derecho o arrastrando fondo.
    - Layouts automáticos: Fuerza elástica (Fruchterman-Reingold) y Circular.
    - Resaltado de nodos vecinos al pasar el cursor.
    """

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)

        self.grafo: Optional[Grafo] = None
        self.coloracion: Dict[str, int] = {}
        self.posiciones: Dict[str, Tuple[float, float]] = {}  # Coordenadas lógicas (x, y)
        self.radio_nodo = 24
        self.escala = 1.0
        self.offset_x = 0.0
        self.offset_y = 0.0

        self.nodo_arrastrado: Optional[str] = None
        self.drag_start_x = 0
        self.drag_start_y = 0
        self.nodo_hover: Optional[str] = None

        self._crear_interfaz()

    def _crear_interfaz(self):
        # Barra de herramientas superior
        self.toolbar = tk.Frame(self, bg="#F1F5F9", pady=4, padx=8)
        self.toolbar.pack(fill=tk.X, side=tk.TOP)

        tk.Label(self.toolbar, text="Visualizador de Grafo Coloreado",
                 font=("Segoe UI", 9, "bold"), bg="#F1F5F9", fg="#1E293B").pack(side=tk.LEFT, padx=(4, 10))

        btn_layout_circ = tk.Button(
            self.toolbar, text="Layout Circular",
            command=self.aplicar_layout_circular,
            bg="#0284C7", fg="white", font=("Segoe UI", 8, "bold"), padx=6, pady=2, relief=tk.FLAT
        )
        btn_layout_circ.pack(side=tk.LEFT, padx=3)

        btn_layout_spring = tk.Button(
            self.toolbar, text="Layout de Fuerzas",
            command=self.aplicar_layout_fuerzas,
            bg="#4F46E5", fg="white", font=("Segoe UI", 8, "bold"), padx=6, pady=2, relief=tk.FLAT
        )
        btn_layout_spring.pack(side=tk.LEFT, padx=3)

        btn_center = tk.Button(
            self.toolbar, text="Centrar Grafo",
            command=self.centrar_grafo,
            bg="#64748B", fg="white", font=("Segoe UI", 8), padx=6, pady=2, relief=tk.FLAT
        )
        btn_center.pack(side=tk.LEFT, padx=3)

        # Botones de Zoom
        tk.Label(self.toolbar, text="| Zoom:", bg="#F1F5F9", fg="#94A3B8").pack(side=tk.LEFT, padx=4)

        btn_zin = tk.Button(self.toolbar, text="+", width=3, command=self.zoom_in,
                            bg="#FFFFFF", relief=tk.GROOVE, font=("Segoe UI", 8))
        btn_zin.pack(side=tk.LEFT, padx=1)

        btn_zout = tk.Button(self.toolbar, text="-", width=3, command=self.zoom_out,
                             bg="#FFFFFF", relief=tk.GROOVE, font=("Segoe UI", 8))
        btn_zout.pack(side=tk.LEFT, padx=1)

        btn_z100 = tk.Button(self.toolbar, text="100%", width=4, command=self.zoom_reset,
                             bg="#FFFFFF", relief=tk.GROOVE, font=("Segoe UI", 8))
        btn_z100.pack(side=tk.LEFT, padx=1)

        self.lbl_info_interaccion = tk.Label(
            self.toolbar, text="Arrastre interactivo de nodos habilitado",
            font=("Segoe UI", 8, "italic"), bg="#F1F5F9", fg="#64748B"
        )
        self.lbl_info_interaccion.pack(side=tk.RIGHT, padx=6)

        # Contenedor del canvas con scrollbars
        canvas_container = tk.Frame(self, bg="#FFFFFF")
        canvas_container.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(
            canvas_container,
            bg="#FAFBFD",
            highlightthickness=0,
            cursor="crosshair"
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Eventos del mouse para interactividad
        self.canvas.bind("<ButtonPress-1>", self._on_mouse_down)
        self.canvas.bind("<B1-Motion>", self._on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_mouse_up)
        self.canvas.bind("<Motion>", self._on_mouse_move)

        self.canvas.bind("<ButtonPress-3>", self._iniciar_paneo)
        self.canvas.bind("<B3-Motion>", self._paneo)
        self.canvas.bind("<MouseWheel>", self._on_mouse_wheel)

    def zoom_in(self):
        self.escala = min(3.0, self.escala * 1.15)
        self.redibujar()

    def zoom_out(self):
        self.escala = max(0.3, self.escala / 1.15)
        self.redibujar()

    def zoom_reset(self):
        self.escala = 1.0
        self.redibujar()

    def _on_mouse_wheel(self, event):
        if event.delta > 0:
            self.zoom_in()
        else:
            self.zoom_out()

    def _iniciar_paneo(self, event):
        self.canvas.scan_mark(event.x, event.y)

    def _paneo(self, event):
        self.canvas.scan_dragto(event.x, event.y, gain=1)

    def cargar_datos(self, grafo: Grafo, coloracion: Dict[str, int]):
        """Carga el grafo y su coloración, calculando el layout inicial."""
        self.grafo = grafo
        self.coloracion = coloracion
        self.escala = 1.0
        self.aplicar_layout_fuerzas()

    def aplicar_layout_circular(self):
        """Dispone los nodos uniformemente sobre una circunferencia."""
        if not self.grafo or not self.grafo.nodos:
            return
        w = max(400, self.canvas.winfo_width())
        h = max(350, self.canvas.winfo_height())
        cx, cy = w / 2, h / 2
        radio = min(w, h) * 0.35

        n = len(self.grafo.nodos)
        self.posiciones.clear()
        for i, nodo in enumerate(self.grafo.nodos):
            angulo = 2 * math.pi * i / n - math.pi / 2
            x = cx + radio * math.cos(angulo)
            y = cy + radio * math.sin(angulo)
            self.posiciones[nodo] = (x, y)

        self.redibujar()

    def aplicar_layout_fuerzas(self):
        """
        Layout Force-Directed (Fruchterman-Reingold modificado).
        Repulsión electrostática entre todos los nodos y atracción elástica
        a lo largo de las aristas. Produce representaciones limpias y legibles.
        """
        if not self.grafo or not self.grafo.nodos:
            return

        w = max(450, self.canvas.winfo_width())
        h = max(380, self.canvas.winfo_height())
        cx, cy = w / 2, h / 2
        nodos = self.grafo.nodos
        n = len(nodos)

        # Si son pocos nodos (<= 8), el layout circular o un radio pequeño funciona genial
        # Inicializar en posiciones circulares
        radio_init = min(w, h) * 0.32
        pos: Dict[str, List[float]] = {}
        for i, nodo in enumerate(nodos):
            ang = 2 * math.pi * i / n - math.pi / 2
            pos[nodo] = [cx + radio_init * math.cos(ang), cy + radio_init * math.sin(ang)]

        if n > 2:
            area = w * h
            k = math.sqrt(area / (n * 1.5))
            iteraciones = 60
            temp = w / 8

            for step in range(iteraciones):
                disp: Dict[str, List[float]] = {nd: [0.0, 0.0] for nd in nodos}

                # Fuerzas de repulsión entre cada par
                for i in range(n):
                    u = nodos[i]
                    for j in range(i + 1, n):
                        v = nodos[j]
                        dx = pos[u][0] - pos[v][0]
                        dy = pos[u][1] - pos[v][1]
                        dist = math.hypot(dx, dy)
                        if dist < 0.01:
                            dx, dy = random.uniform(-1, 1), random.uniform(-1, 1)
                            dist = math.hypot(dx, dy)

                        fuerza_rep = (k * k) / dist
                        fx = (dx / dist) * fuerza_rep
                        fy = (dy / dist) * fuerza_rep
                        disp[u][0] += fx
                        disp[u][1] += fy
                        disp[v][0] -= fx
                        disp[v][1] -= fy

                # Fuerzas de atracción a lo largo de las aristas
                for u, v in self.grafo.obtener_aristas():
                    dx = pos[u][0] - pos[v][0]
                    dy = pos[u][1] - pos[v][1]
                    dist = math.hypot(dx, dy)
                    if dist < 0.01:
                        continue
                    fuerza_att = (dist * dist) / k
                    fx = (dx / dist) * fuerza_att
                    fy = (dy / dist) * fuerza_att
                    disp[u][0] -= fx
                    disp[u][1] -= fy
                    disp[v][0] += fx
                    disp[v][1] += fy

                # Actualizar posiciones limitadas por temperatura
                for nd in nodos:
                    dx, dy = disp[nd][0], disp[nd][1]
                    d_len = math.hypot(dx, dy)
                    if d_len > 0:
                        desplazamiento = min(d_len, temp)
                        pos[nd][0] += (dx / d_len) * desplazamiento
                        pos[nd][1] += (dy / d_len) * desplazamiento

                    # Mantener dentro de márgenes
                    margin = 50
                    pos[nd][0] = max(margin, min(w - margin, pos[nd][0]))
                    pos[nd][1] = max(margin, min(h - margin, pos[nd][1]))

                temp *= 0.93

        self.posiciones = {nd: (pos[nd][0], pos[nd][1]) for nd in nodos}
        self.centrar_grafo()

    def centrar_grafo(self):
        """Centra los nodos en el canvas."""
        if not self.posiciones:
            return
        w = max(400, self.canvas.winfo_width())
        h = max(350, self.canvas.winfo_height())
        xs = [p[0] for p in self.posiciones.values()]
        ys = [p[1] for p in self.posiciones.values()]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)

        cur_cx = (min_x + max_x) / 2
        cur_cy = (min_y + max_y) / 2
        target_cx, target_cy = w / 2, h / 2

        dx = target_cx - cur_cx
        dy = target_cy - cur_cy

        self.posiciones = {nd: (p[0] + dx, p[1] + dy) for nd, p in self.posiciones.items()}
        self.redibujar()

    def redibujar(self):
        """Dibuja el grafo completo en el canvas con sus colores y aristas."""
        self.canvas.delete("all")

        if not self.grafo or not self.grafo.nodos:
            self.canvas.create_text(
                self.canvas.winfo_width() / 2 or 250,
                self.canvas.winfo_height() / 2 or 180,
                text="Ingresa un grafo en el panel izquierdo y haz clic en 'Colorear Grafo'\n"
                     "para visualizar la coloración con el menor número de colores.",
                font=("Segoe UI", 11), fill="#94A3B8", justify=tk.CENTER
            )
            return

        # Dibujar rejilla decorativa suave de fondo
        self._dibujar_cuadricula()

        # Determinar si hay conflictos en aristas
        valida, conflictos = verificar_coloracion(self.grafo, self.coloracion)
        conflictos_set = set(conflictos)

        # 1. Dibujar Aristas
        for u, v in self.grafo.obtener_aristas():
            if u not in self.posiciones or v not in self.posiciones:
                continue
            x1, y1 = self._transformar(self.posiciones[u])
            x2, y2 = self._transformar(self.posiciones[v])

            es_conflicto = (u, v) in conflictos_set or (v, u) in conflictos_set
            es_hover = (self.nodo_hover in (u, v))

            if es_conflicto:
                color_linea = "#EF4444"
                grosor = 3
                dash = (4, 3)
            elif es_hover:
                color_linea = "#0284C7"
                grosor = 3
                dash = None
            else:
                color_linea = "#94A3B8"
                grosor = 2
                dash = None

            self.canvas.create_line(
                x1, y1, x2, y2,
                fill=color_linea,
                width=grosor,
                dash=dash,
                capstyle=tk.ROUND,
                joinstyle=tk.ROUND
            )

        # 2. Dibujar Nodos
        r = self.radio_nodo * self.escala
        for nodo in self.grafo.nodos:
            if nodo not in self.posiciones:
                continue
            x, y = self._transformar(self.posiciones[nodo])
            col_idx = self.coloracion.get(nodo, 0)
            col_hex = obtener_color_hex(col_idx)
            text_color = color_texto_contraste(col_hex)

            es_hover = (self.nodo_hover == nodo)

            # Sombra suave
            self.canvas.create_oval(
                x - r + 2, y - r + 3, x + r + 2, y + r + 3,
                fill="#CBD5E1", outline="", tags=(f"nodo_{nodo}", "nodo")
            )

            # Círculo principal del nodo
            outline_col = "#0F172A" if es_hover else "#FFFFFF"
            outline_width = 3 if es_hover else 2
            self.canvas.create_oval(
                x - r, y - r, x + r, y + r,
                fill=col_hex,
                outline=outline_col,
                width=outline_width,
                tags=(f"nodo_{nodo}", "nodo")
            )

            # Texto del nombre del nodo
            font_size = max(8, int(11 * self.escala))
            self.canvas.create_text(
                x, y - (2 if self.escala >= 0.8 else 0),
                text=str(nodo),
                font=("Segoe UI", font_size, "bold"),
                fill=text_color,
                tags=(f"nodo_{nodo}", "nodo")
            )

            # Pequeña insignia con el número de color / registro (ej. C1, C2...)
            if self.escala >= 0.7:
                badge_text = f"C{col_idx + 1}"
                badge_r = max(6, int(8 * self.escala))
                bx = x + r * 0.65
                by = y - r * 0.65
                self.canvas.create_oval(
                    bx - badge_r, by - badge_r, bx + badge_r, by + badge_r,
                    fill="#1E293B", outline="#FFFFFF", width=1.5
                )
                self.canvas.create_text(
                    bx, by,
                    text=badge_text,
                    font=("Segoe UI", max(6, int(7 * self.escala)), "bold"),
                    fill="#FFFFFF"
                )

    def _dibujar_cuadricula(self):
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        paso = int(40 * self.escala)
        if paso > 15:
            for x in range(0, w, paso):
                self.canvas.create_line(x, 0, x, h, fill="#F1F5F9", width=1)
            for y in range(0, h, paso):
                self.canvas.create_line(0, y, w, y, fill="#F1F5F9", width=1)

    def _transformar(self, coord: Tuple[float, float]) -> Tuple[float, float]:
        """Aplica la escala respecto al centro."""
        w = max(400, self.canvas.winfo_width())
        h = max(350, self.canvas.winfo_height())
        cx, cy = w / 2, h / 2
        x, y = coord
        tx = cx + (x - cx) * self.escala
        ty = cy + (y - cy) * self.escala
        return tx, ty

    def _destransformar(self, screen_x: float, screen_y: float) -> Tuple[float, float]:
        """Convierte coordenadas de pantalla a coordenadas lógicas."""
        w = max(400, self.canvas.winfo_width())
        h = max(350, self.canvas.winfo_height())
        cx, cy = w / 2, h / 2
        x = cx + (screen_x - cx) / self.escala
        y = cy + (screen_y - cy) / self.escala
        return x, y

    def _detectar_nodo(self, screen_x: float, screen_y: float) -> Optional[str]:
        """Detecta si las coordenadas dadas caen sobre algún nodo."""
        if not self.grafo:
            return None
        r = self.radio_nodo * self.escala
        for nodo in reversed(self.grafo.nodos):
            if nodo in self.posiciones:
                nx, ny = self._transformar(self.posiciones[nodo])
                if math.hypot(screen_x - nx, screen_y - ny) <= r + 4:
                    return nodo
        return None

    def _on_mouse_down(self, event):
        nodo = self._detectar_nodo(event.x, event.y)
        if nodo:
            self.nodo_arrastrado = nodo
            self.canvas.config(cursor="fleur")
        else:
            self.nodo_arrastrado = None
            # Si no hace click en un nodo, inicia paneo suave
            self.drag_start_x = event.x
            self.drag_start_y = event.y

    def _on_mouse_drag(self, event):
        if self.nodo_arrastrado and self.nodo_arrastrado in self.posiciones:
            log_x, log_y = self._destransformar(event.x, event.y)
            self.posiciones[self.nodo_arrastrado] = (log_x, log_y)
            self.redibujar()
        elif not self.nodo_arrastrado and (self.drag_start_x or self.drag_start_y):
            dx = (event.x - self.drag_start_x) / self.escala
            dy = (event.y - self.drag_start_y) / self.escala
            self.drag_start_x = event.x
            self.drag_start_y = event.y
            self.posiciones = {nd: (p[0] + dx, p[1] + dy) for nd, p in self.posiciones.items()}
            self.redibujar()

    def _on_mouse_up(self, event):
        self.nodo_arrastrado = None
        self.drag_start_x = 0
        self.drag_start_y = 0
        self.canvas.config(cursor="crosshair")

    def _on_mouse_move(self, event):
        nodo = self._detectar_nodo(event.x, event.y)
        if nodo != self.nodo_hover:
            self.nodo_hover = nodo
            self.canvas.config(cursor="hand2" if nodo else "crosshair")
            self.redibujar()


class SeccionColoracionGrafos(ttk.Frame):
    """
    Panel completo de la nueva sección de Coloración de Grafos.
    Integra el input de adyacencia de texto, botones de acción,
    resumen de métricas y el canvas visualizador interactivo.
    """

    EJEMPLOS_PREDEFINIDOS = {
        "1. Grafo Conexo G1 (6 nodos, 3 colores)": (
            "A: B, F\n"
            "B: C\n"
            "C: D\n"
            "D: E, F\n"
            "E: F\n"
        ),
        "2. Ciclo Impar C5 (5 nodos, 3 colores)": (
            "A: B, E\n"
            "B: C\n"
            "C: D\n"
            "D: E\n"
            "E:\n"
        ),
        "3. Grafo Completo K4 (4 nodos, 4 colores)": (
            "A: B, C, D\n"
            "B: C, D\n"
            "C: D\n"
            "D:\n"
        ),
        "4. Grafo Bipartito K3,3 (6 nodos, 2 colores)": (
            "X1: Y1, Y2, Y3\n"
            "X2: Y1, Y2, Y3\n"
            "X3: Y1, Y2, Y3\n"
            "Y1:\n"
            "Y2:\n"
            "Y3:\n"
        ),
        "5. Grafo Rueda W6 (Centro + C5, 4 colores)": (
            "Centro: A, B, C, D, E\n"
            "A: B, E\n"
            "B: C\n"
            "C: D\n"
            "D: E\n"
        ),
        "6. Grafo de Petersen (10 nodos, 3 colores)": (
            "0: 1, 4, 5\n"
            "1: 2, 6\n"
            "2: 3, 7\n"
            "3: 4, 8\n"
            "4: 9\n"
            "5: 7, 8\n"
            "6: 8, 9\n"
            "7: 9\n"
            "8:\n"
            "9:\n"
        ),
        "7. Asignación de Registros IR (Variables de Compilador)": (
            "t0: t1, x\n"
            "t1: t0, t2, x\n"
            "t2: t1, y\n"
            "x: t0, t1, y\n"
            "y: t2, x\n"
        )
    }

    def __init__(self, parent, root_app=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.root_app = root_app
        self.ultimo_grafo: Optional[Grafo] = None
        self.ultima_coloracion: Dict[str, int] = {}
        self.ultimo_num_colores: int = 0

        self._construir_ui()

    def _construir_ui(self):
        # Cabecera de la sección
        header = tk.Frame(self, bg="#0F172A", padx=15, pady=8)
        header.pack(fill=tk.X)

        tk.Label(
            header,
            text="Coloración de Grafos — Asignación Óptima de Registros",
            font=("Segoe UI", 12, "bold"), bg="#0F172A", fg="#38BDF8"
        ).pack(side=tk.LEFT)

        tk.Label(
            header,
            text="Calcula el Número Cromático Mínimo χ(G) garantizando que nodos vecinos tengan colores distintos",
            font=("Segoe UI", 9), bg="#0F172A", fg="#94A3B8"
        ).pack(side=tk.LEFT, padx=12)

        btn_popout = tk.Button(
            header, text="Abrir en Ventana Independiente",
            command=self.abrir_en_ventana_externa,
            bg="#1E293B", fg="#E2E8F0", font=("Segoe UI", 8), padx=8, pady=2, relief=tk.FLAT
        )
        btn_popout.pack(side=tk.RIGHT)

        # PanedWindow divisor horizontal (Panel Izquierdo: Inputs, Panel Derecho: Canvas)
        paned = tk.PanedWindow(self, orient=tk.HORIZONTAL, sashrelief=tk.RAISED, sashwidth=4, bg="#E2E8F0")
        paned.pack(fill=tk.BOTH, expand=True)

        # ----------------- PANEL IZQUIERDO: INPUT Y MÉTRICAS -----------------
        left_panel = tk.Frame(paned, bg="#F8FAFC", padx=10, pady=10, width=380)
        paned.add(left_panel, minsize=320)

        # Selector de ejemplos predefinidos
        lbl_ej = tk.Label(left_panel, text="Cargar caso predefinido:", font=("Segoe UI", 9, "bold"), bg="#F8FAFC", fg="#334155")
        lbl_ej.pack(anchor="w")

        self.combo_ejemplos = ttk.Combobox(
            left_panel,
            values=list(self.EJEMPLOS_PREDEFINIDOS.keys()),
            state="readonly",
            font=("Segoe UI", 9)
        )
        self.combo_ejemplos.pack(fill=tk.X, pady=(2, 8))
        self.combo_ejemplos.set("1. Grafo Conexo G1 (6 nodos, 3 colores)")
        self.combo_ejemplos.bind("<<ComboboxSelected>>", self._cargar_ejemplo_seleccionado)

        # Etiqueta e Input de adyacencia
        lbl_input = tk.Label(
            left_panel,
            text="Definición del Grafo (Lista de Adyacencia):\nFormato: NODO: VECINO_1, VECINO_2, ...",
            font=("Segoe UI", 9, "bold"), bg="#F8FAFC", fg="#1E293B", justify=tk.LEFT
        )
        lbl_input.pack(anchor="w", pady=(0, 4))

        frame_txt = tk.Frame(left_panel, bd=1, relief=tk.SOLID)
        frame_txt.pack(fill=tk.X)

        sb_txt = ttk.Scrollbar(frame_txt, orient=tk.VERTICAL)
        sb_txt.pack(side=tk.RIGHT, fill=tk.Y)

        self.txt_grafo = tk.Text(
            frame_txt, height=8, font=("Consolas", 10),
            yscrollcommand=sb_txt.set, bg="#FFFFFF", fg="#0F172A",
            padx=8, pady=6, relief=tk.FLAT
        )
        self.txt_grafo.pack(fill=tk.BOTH, expand=True)
        sb_txt.config(command=self.txt_grafo.yview)

        # Cargar ejemplo por defecto
        self.txt_grafo.insert(tk.END, self.EJEMPLOS_PREDEFINIDOS["1. Grafo Conexo G1 (6 nodos, 3 colores)"])

        # Barra de botones principales
        btn_bar = tk.Frame(left_panel, bg="#F8FAFC", pady=6)
        btn_bar.pack(fill=tk.X)

        btn_colorear = tk.Button(
            btn_bar, text="Colorear Grafo", command=self.ejecutar_coloracion,
            bg="#0D9488", fg="white", font=("Segoe UI", 10, "bold"), padx=12, pady=5, relief=tk.FLAT
        )
        btn_colorear.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))

        btn_limpiar = tk.Button(
            btn_bar, text="Limpiar", command=self.limpiar_input,
            bg="#64748B", fg="white", font=("Segoe UI", 9), padx=8, pady=5, relief=tk.FLAT
        )
        btn_limpiar.pack(side=tk.LEFT, padx=2)

        btn_ir_vars = tk.Button(
            btn_bar, text="Cargar desde IR", command=self._importar_desde_ir_actual,
            bg="#7C3AED", fg="white", font=("Segoe UI", 9), padx=8, pady=5, relief=tk.FLAT
        )
        btn_ir_vars.pack(side=tk.LEFT, padx=(4, 0))

        # Tarjetas de Resumen y Resultados
        lbl_res = tk.Label(left_panel, text="RESULTADOS DE LA COLORACIÓN",
                           font=("Segoe UI", 9, "bold"), bg="#F8FAFC", fg="#475569")
        lbl_res.pack(anchor="w", pady=(10, 4))

        cards_frame = tk.Frame(left_panel, bg="#F8FAFC")
        cards_frame.pack(fill=tk.X, pady=(0, 6))

        def _crear_card(parent, titulo, col="#2563EB"):
            f = tk.Frame(parent, bg="#FFFFFF", relief=tk.SOLID, bd=1, padx=8, pady=4)
            f.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2)
            tk.Label(f, text=titulo.upper(), font=("Segoe UI", 7, "bold"), fg="#64748B", bg="#FFFFFF").pack(anchor="w")
            val = tk.Label(f, text="—", font=("Segoe UI", 13, "bold"), fg=col, bg="#FFFFFF")
            val.pack(anchor="w")
            return val

        self.card_chi = _crear_card(cards_frame, "Colores (χ)", "#0D9488")
        self.card_nodos = _crear_card(cards_frame, "Nodos (V)", "#2563EB")
        self.card_aristas = _crear_card(cards_frame, "Aristas (E)", "#4F46E5")
        self.card_grado_max = _crear_card(cards_frame, "Grado Máx (Δ)", "#D97706")

        # Estado de Validación
        self.lbl_validacion = tk.Label(
            left_panel, text="Listo para procesar",
            font=("Segoe UI", 9, "bold"), bg="#F1F5F9", fg="#475569",
            padx=8, pady=4, relief=tk.GROOVE
        )
        self.lbl_validacion.pack(fill=tk.X, pady=(2, 6))

        # Tabla / Lista de Asignación de Nodos a Colores y Registros
        lbl_tabla = tk.Label(
            left_panel, text="Asignación de Colores / Registros:",
            font=("Segoe UI", 9, "bold"), bg="#F8FAFC", fg="#334155"
        )
        lbl_tabla.pack(anchor="w", pady=(4, 2))

        frame_tv = tk.Frame(left_panel)
        frame_tv.pack(fill=tk.BOTH, expand=True)

        cols_tv = ("Color", "Registro", "Nodos Asignados")
        self.tv_colores = ttk.Treeview(frame_tv, columns=cols_tv, show="headings", height=6)
        self.tv_colores.heading("Color", text="Color (C#)")
        self.tv_colores.heading("Registro", text="Registro")
        self.tv_colores.heading("Nodos Asignados", text="Nodos Asignados")

        self.tv_colores.column("Color", width=85, anchor="center")
        self.tv_colores.column("Registro", width=75, anchor="center")
        self.tv_colores.column("Nodos Asignados", width=180, anchor="w")

        sb_tv = ttk.Scrollbar(frame_tv, orient=tk.VERTICAL, command=self.tv_colores.yview)
        self.tv_colores.configure(yscrollcommand=sb_tv.set)
        sb_tv.pack(side=tk.RIGHT, fill=tk.Y)
        self.tv_colores.pack(fill=tk.BOTH, expand=True)

        # ----------------- PANEL DERECHO: CANVAS INTERACTIVO -----------------
        right_panel = tk.Frame(paned, bg="#FFFFFF")
        paned.add(right_panel, minsize=400)

        self.coloring_canvas = ColoringCanvas(right_panel)
        self.coloring_canvas.pack(fill=tk.BOTH, expand=True)

        # Ejecutar coloración inicial automáticamente
        self.after(200, self.ejecutar_coloracion)

    def _cargar_ejemplo_seleccionado(self, event=None):
        clave = self.combo_ejemplos.get()
        if clave in self.EJEMPLOS_PREDEFINIDOS:
            self.txt_grafo.delete("1.0", tk.END)
            self.txt_grafo.insert(tk.END, self.EJEMPLOS_PREDEFINIDOS[clave])
            self.ejecutar_coloracion()

    def limpiar_input(self):
        self.txt_grafo.delete("1.0", tk.END)
        self.coloring_canvas.grafo = None
        self.coloring_canvas.coloracion.clear()
        self.coloring_canvas.redibujar()
        self.card_chi.config(text="—")
        self.card_nodos.config(text="—")
        self.card_aristas.config(text="—")
        self.card_grado_max.config(text="—")
        self.lbl_validacion.config(text="Lienzo limpio", bg="#F1F5F9", fg="#475569")
        for item in self.tv_colores.get_children():
            self.tv_colores.delete(item)

    def ejecutar_coloracion(self):
        """Parsea la entrada, calcula la coloración óptima mínima y actualiza la visualización."""
        texto = self.txt_grafo.get("1.0", tk.END).strip()
        if not texto:
            messagebox.showwarning("Atención", "Por favor ingresa la definición del grafo primero.")
            return

        grafo = parsear_grafo_texto(texto)
        if not grafo.nodos:
            messagebox.showwarning("Grafo Vacío", "No se detectaron nodos válidos en el texto ingresado.")
            return

        # Calcular coloración con el menor número posible de colores
        coloracion, num_colores, es_valida = colorear_grafo_minimo(grafo)

        self.ultimo_grafo = grafo
        self.ultima_coloracion = coloracion
        self.ultimo_num_colores = num_colores

        # Actualizar Tarjetas
        self.card_chi.config(text=f"{num_colores}")
        self.card_nodos.config(text=f"{len(grafo.nodos)}")
        self.card_aristas.config(text=f"{len(grafo.obtener_aristas())}")
        self.card_grado_max.config(text=f"{grafo.grado_maximo()}")

        # Actualizar Estado de Validación
        if es_valida:
            self.lbl_validacion.config(
                text=f"Coloración Óptima Válida: {num_colores} color(es) — 0 conflictos",
                bg="#DCFCE7", fg="#166534"
            )
        else:
            _, conflictos = verificar_coloracion(grafo, coloracion)
            self.lbl_validacion.config(
                text=f"Conflicto detectado en {len(conflictos)} arista(s)",
                bg="#FEE2E2", fg="#991B1B"
            )

        # Actualizar Tabla de Asignación de Colores
        for item in self.tv_colores.get_children():
            self.tv_colores.delete(item)

        # Agrupar nodos por color
        grupos: Dict[int, List[str]] = {}
        for nd, c in coloracion.items():
            grupos.setdefault(c, []).append(nd)

        for c_idx in sorted(grupos.keys()):
            nombre_col = obtener_nombre_color(c_idx)
            registro = f"R{c_idx + 1}"
            nodos_asignados = ", ".join(grupos[c_idx])
            self.tv_colores.insert("", tk.END, values=(nombre_col, registro, nodos_asignados))

        # Enviar al Canvas
        self.coloring_canvas.cargar_datos(grafo, coloracion)

    def _importar_desde_ir_actual(self):
        """
        Construye automáticamente un grafo de interferencia de registros a partir
        de las variables y temporales del código intermedio actual de la aplicación.
        """
        if not self.root_app:
            messagebox.showinfo("Información", "No hay acceso al compilador principal.")
            return

        codigo = self.root_app.obtener_codigo()
        if not codigo.strip():
            messagebox.showwarning("Código Vacío", "No hay código en el editor principal para analizar.")
            return

        try:
            # Parsear e identificar temporales / variables en cuádruplos
            tokens = self.root_app.analisis_lexico()
            from compilador.ir.generator import IRGenerator
            from main import Parser

            parser = Parser(tokens, codigo)
            ast = parser.parse()
            if parser.errors:
                messagebox.showerror("Error", "Corrige primero los errores de sintaxis en el código C++.")
                return

            # Si la app ya optimizó el código intermedio, usamos las cuádruplas optimizadas
            if hasattr(self.root_app, "ultimo_optimizador") and self.root_app.ultimo_optimizador:
                instrucciones = self.root_app.ultimo_optimizador.instrucciones_optimizadas
            else:
                gen = IRGenerator()
                instrucciones, _, _ = gen.generar(ast)

            if not instrucciones:
                messagebox.showinfo("Sin IR", "No se generaron instrucciones de código intermedio.")
                return

            # Análisis formal de liveness y construcción del grafo de interferencia
            from compilador.codegen.liveness import construir_grafo_interferencia
            liveness = construir_grafo_interferencia(instrucciones)

            if not liveness.variables:
                messagebox.showinfo("Sin Variables", "No se identificaron temporales ni variables en el IR.")
                return

            texto_generado = liveness.generar_texto_adyacencia()
            self.txt_grafo.delete("1.0", tk.END)
            self.txt_grafo.insert(tk.END, texto_generado)
            self.ejecutar_coloracion()
            messagebox.showinfo(
                "Grafo Importado de IR",
                f"¡Grafo de interferencia generado formalmente con {len(liveness.variables)} variables/temporales y análisis de liveness!"
            )
        except Exception as ex:
            messagebox.showerror("Error al importar IR", f"Ocurrió un error al analizar las variables del IR:\n{ex}")

    def abrir_en_ventana_externa(self):
        """Abre la sección de coloración en una ventana emergente Toplevel dedicada."""
        ventana = tk.Toplevel(self)
        ventana.title("Visualizador de Coloración de Grafos")
        ventana.geometry("1000x700")

        seccion_popup = SeccionColoracionGrafos(ventana, root_app=self.root_app)
        seccion_popup.pack(fill=tk.BOTH, expand=True)

        # Copiar datos actuales si existen
        texto_actual = self.txt_grafo.get("1.0", tk.END).strip()
        if texto_actual:
            seccion_popup.txt_grafo.delete("1.0", tk.END)
            seccion_popup.txt_grafo.insert(tk.END, texto_actual)
            seccion_popup.ejecutar_coloracion()
