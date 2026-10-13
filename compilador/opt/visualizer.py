"""
Componente visual interactivo para el Grafo de Flujo de Control (CFG / GFG).
Materia: Lenguajes y Autómatas II - Unidad 3.

Renderiza el grafo de flujo utilizando Tkinter Canvas puro (sin dependencias externas).
Incluye disposición automática por capas (hierarchical layout), soporte para zoom,
desplazamiento (pan/scroll) y coloreado según el tipo de nodo y arista.
"""

import tkinter as tk
from tkinter import ttk
from typing import Dict, List, Tuple, Optional, Set
from collections import deque

from .basic_block import BasicBlock
from .cfg import ControlFlowGraph, CFGEdge


class CFGCanvas(tk.Frame):
    """
    Widget de Tkinter que dibuja el Grafo de Flujo de Control de manera gráfica.
    """
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)

        self.cfg: Optional[ControlFlowGraph] = None
        self.escala = 1.0

        # Barra de controles superior
        self.toolbar = tk.Frame(self, bg="#F0F0F0", pady=3)
        self.toolbar.pack(fill=tk.X, side=tk.TOP)

        tk.Label(self.toolbar, text="Visualizador GFG / CFG", font=("Arial", 9, "bold"), bg="#F0F0F0", fg="#333").pack(side=tk.LEFT, padx=8)

        btn_zoom_in = ttk.Button(self.toolbar, text="🔍 +", width=4, command=self.zoom_in)
        btn_zoom_in.pack(side=tk.LEFT, padx=2)

        btn_zoom_out = ttk.Button(self.toolbar, text="🔍 −", width=4, command=self.zoom_out)
        btn_zoom_out.pack(side=tk.LEFT, padx=2)

        btn_zoom_reset = ttk.Button(self.toolbar, text="100%", width=5, command=self.zoom_reset)
        btn_zoom_reset.pack(side=tk.LEFT, padx=2)

        # Leyenda de colores
        leyenda_frame = tk.Frame(self.toolbar, bg="#F0F0F0")
        leyenda_frame.pack(side=tk.RIGHT, padx=10)

        self._crear_indicador(leyenda_frame, "#2E7D32", "Rama Sí")
        self._crear_indicador(leyenda_frame, "#C62828", "Rama No")
        self._crear_indicador(leyenda_frame, "#1565C0", "Salto (goto)")
        self._crear_indicador(leyenda_frame, "#D32F2F", "Inalcanzable")

        # Frame con Canvas y Scrollbars
        canvas_frame = tk.Frame(self)
        canvas_frame.pack(fill=tk.BOTH, expand=True)

        self.v_scroll = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL)
        self.h_scroll = ttk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL)

        self.canvas = tk.Canvas(
            canvas_frame,
            bg="#FFFFFF",
            xscrollcommand=self.h_scroll.set,
            yscrollcommand=self.v_scroll.set,
            highlightthickness=0
        )

        self.v_scroll.config(command=self.canvas.yview)
        self.h_scroll.config(command=self.canvas.xview)

        self.v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.h_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Soporte para arrastre con el mouse (Pan)
        self.canvas.bind("<ButtonPress-1>", self._iniciar_arrastre)
        self.canvas.bind("<B1-Motion>", self._arrastrar)

        # Dimensiones estimadas de nodos
        self.posiciones_nodos: Dict[str, Tuple[float, float, float, float]] = {}

    def _crear_indicador(self, parent, color, texto):
        f = tk.Frame(parent, bg="#F0F0F0")
        f.pack(side=tk.LEFT, padx=5)
        c = tk.Canvas(f, width=12, height=12, bg="#F0F0F0", highlightthickness=0)
        c.pack(side=tk.LEFT)
        c.create_rectangle(1, 1, 11, 11, fill=color, outline="")
        tk.Label(f, text=texto, font=("Arial", 8), bg="#F0F0F0", fg="#444").pack(side=tk.LEFT, padx=2)

    def _iniciar_arrastre(self, event):
        self.canvas.scan_mark(event.x, event.y)

    def _arrastrar(self, event):
        self.canvas.scan_dragto(event.x, event.y, gain=1)

    def zoom_in(self):
        self.escala = min(2.5, self.escala * 1.2)
        self.dibujar_cfg(self.cfg)

    def zoom_out(self):
        self.escala = max(0.4, self.escala / 1.2)
        self.dibujar_cfg(self.cfg)

    def zoom_reset(self):
        self.escala = 1.0
        self.dibujar_cfg(self.cfg)

    def dibujar_cfg(self, cfg: Optional[ControlFlowGraph]):
        """Dibuja el Grafo de Flujo de Control completo en el canvas."""
        self.cfg = cfg
        self.canvas.delete("all")
        self.posiciones_nodos.clear()

        if not cfg or not cfg.bloques:
            self.canvas.create_text(
                300, 200,
                text="No hay grafo de flujo disponible.\nGenere o ejecute código intermedio para visualizar.",
                font=("Arial", 12), fill="#888888", justify=tk.CENTER
            )
            return

        # 1. Asignar capas (niveles jerárquicos) mediante BFS
        niveles: Dict[str, int] = {}
        cola = deque([(cfg.bloques[0].id, 0)])
        visitados_niv = {cfg.bloques[0].id}

        while cola:
            b_id, niv = cola.popleft()
            niveles[b_id] = max(niveles.get(b_id, 0), niv)

            for suc in cfg.sucesores.get(b_id, []):
                if suc != "Exit" and suc not in visitados_niv:
                    visitados_niv.add(suc)
                    cola.append((suc, niv + 1))

        # Bloques inalcanzables se ubican al final
        max_nivel = max(niveles.values(), default=0)
        for b in cfg.bloques:
            if b.id not in niveles:
                max_nivel += 1
                niveles[b.id] = max_nivel

        niveles["Exit"] = max_nivel + 1

        # Agrupar bloques por capa
        capas: Dict[int, List[str]] = {}
        for nodo_id, niv in niveles.items():
            capas.setdefault(niv, []).append(nodo_id)

        # 2. Calcular coordenadas físicas (X, Y)
        nodo_ancho = int(220 * self.escala)
        espacio_x = int(60 * self.escala)
        espacio_y = int(70 * self.escala)
        margen_x = 50
        margen_y = 40

        max_ancho_canvas = 0
        y_actual = margen_y

        for niv in sorted(capas.keys()):
            nodos_en_capa = capas[niv]
            total_ancho_capa = len(nodos_en_capa) * nodo_ancho + (len(nodos_en_capa) - 1) * espacio_x
            max_ancho_canvas = max(max_ancho_canvas, total_ancho_capa)

            x_inicio = margen_x
            max_alto_en_capa = 0

            for i, n_id in enumerate(nodos_en_capa):
                x = x_inicio + i * (nodo_ancho + espacio_x)

                # Calcular altura según líneas de instrucciones
                if n_id == "Exit":
                    n_lines = 1
                else:
                    b_obj = cfg.mapa_bloques.get(n_id)
                    n_lines = max(1, len(b_obj.instrucciones)) if b_obj else 1

                nodo_alto = int((40 + n_lines * 18) * self.escala)
                max_alto_en_capa = max(max_alto_en_capa, nodo_alto)

                self.posiciones_nodos[n_id] = (x, y_actual, x + nodo_ancho, y_actual + nodo_alto)

            y_actual += max_alto_en_capa + espacio_y

        max_alto_canvas = y_actual + margen_y

        # 3. Dibujar aristas primero (para que queden por debajo de las cajas)
        for arista in cfg.aristas:
            if arista.origen in self.posiciones_nodos and arista.destino in self.posiciones_nodos:
                self._dibujar_arista(arista)

        # 4. Dibujar nodos
        for b in cfg.bloques:
            if b.id in self.posiciones_nodos:
                self._dibujar_bloque(b)

        # Dibujar nodo Exit
        if "Exit" in self.posiciones_nodos:
            self._dibujar_nodo_exit()

        # Ajustar región de scroll
        self.canvas.config(scrollregion=(0, 0, max(max_ancho_canvas + 150, 900), max_alto_canvas))

    def _dibujar_bloque(self, b: BasicBlock):
        x1, y1, x2, y2 = self.posiciones_nodos[b.id]
        r = int(8 * self.escala)  # radio esquina

        # Colores según el rol
        if b.es_inalcanzable:
            color_header = "#757575"
            color_bg = "#F5F5F5"
            color_borde = "#BDBDBD"
            titulo_extra = " [Inalcanzable]"
        elif b.es_entrada:
            color_header = "#2E7D32"
            color_bg = "#F1F8E9"
            color_borde = "#388E3C"
            titulo_extra = " (Entrada)"
        else:
            color_header = "#1565C0"
            color_bg = "#FFFFFF"
            color_borde = "#1976D2"
            titulo_extra = ""

        # Fondo del nodo
        self.canvas.create_rectangle(x1, y1, x2, y2, fill=color_bg, outline=color_borde, width=2)

        # Franja del encabezado
        alto_header = int(26 * self.escala)
        self.canvas.create_rectangle(x1, y1, x2, y1 + alto_header, fill=color_header, outline="")

        # Texto del encabezado
        fuente_header = ("Arial", max(8, int(9 * self.escala)), "bold")
        titulo = f"{b.nombre_completo}{titulo_extra}"
        self.canvas.create_text(
            x1 + 8, y1 + alto_header / 2,
            text=titulo, font=fuente_header, fill="white", anchor="w"
        )

        # Instrucciones dentro del bloque
        fuente_codigo = ("Consolas", max(7, int(8 * self.escala)))
        y_texto = y1 + alto_header + int(8 * self.escala)
        line_height = int(16 * self.escala)

        for inst in b.instrucciones:
            t3ac = inst.to_3ac()
            texto_linea = f"{inst.numero}: {t3ac}"
            self.canvas.create_text(
                x1 + 10, y_texto,
                text=texto_linea, font=fuente_codigo, fill="#212121", anchor="w"
            )
            y_texto += line_height

    def _dibujar_nodo_exit(self):
        x1, y1, x2, y2 = self.posiciones_nodos["Exit"]
        self.canvas.create_rectangle(x1, y1, x2, y2, fill="#F3E5F5", outline="#7B1FA2", width=2)
        alto_header = int(24 * self.escala)
        self.canvas.create_rectangle(x1, y1, x2, y1 + alto_header, fill="#6A1B9A", outline="")

        fuente_header = ("Arial", max(8, int(9 * self.escala)), "bold")
        self.canvas.create_text(
            (x1 + x2) / 2, y1 + alto_header / 2,
            text="Exit (Fin)", font=fuente_header, fill="white", anchor="center"
        )
        self.canvas.create_text(
            (x1 + x2) / 2, y1 + alto_header + int(10 * self.escala),
            text="[Retorno del programa]", font=("Consolas", max(7, int(8 * self.escala))),
            fill="#4A148C", anchor="center"
        )

    def _dibujar_arista(self, arista: CFGEdge):
        ox1, oy1, ox2, oy2 = self.posiciones_nodos[arista.origen]
        dx1, dy1, dx2, dy2 = self.posiciones_nodos[arista.destino]

        # Determinar color de la arista según tipo y etiqueta
        etq = arista.etiqueta.lower()
        if "sí" in etq or "true" in etq:
            color = "#2E7D32"   # Verde
        elif "no" in etq or "false" in etq:
            color = "#C62828"   # Rojo
        elif "goto" in etq:
            color = "#1565C0"   # Azul
        elif "return" in etq:
            color = "#6A1B9A"   # Púrpura
        else:
            color = "#616161"   # Gris oscuro

        # Puntos de conexión
        # Si el destino está debajo del origen
        if dy1 > oy2:
            x_start = (ox1 + ox2) / 2
            y_start = oy2
            x_end = (dx1 + dx2) / 2
            y_end = dy1

            # Desplazar ligeramente si hay múltiples aristas hacia destinos distintos
            if "sí" in etq or "true" in etq:
                x_start = ox1 + (ox2 - ox1) * 0.3
            elif "no" in etq or "false" in etq:
                x_start = ox1 + (ox2 - ox1) * 0.7

            # Dibujar línea quebrada o curva con flecha
            puntos = [x_start, y_start, x_start, (y_start + y_end) / 2, x_end, (y_start + y_end) / 2, x_end, y_end]
            self.canvas.create_line(puntos, fill=color, width=2, arrow=tk.LAST, smooth=True)

            # Etiqueta en el punto medio
            if arista.etiqueta:
                mx = (x_start + x_end) / 2
                my = (y_start + y_end) / 2 - 8
                self._dibujar_badge_etiqueta(mx, my, arista.etiqueta, color)

        # Si el destino está arriba (ciclo / bucle / salto hacia atrás)
        elif dy2 <= oy1:
            # Salir por el lateral izquierdo o derecho
            x_start = ox2
            y_start = (oy1 + oy2) / 2
            x_end = dx2
            y_end = (dy1 + dy2) / 2
            loop_offset = 40 * self.escala

            puntos = [x_start, y_start, x_start + loop_offset, y_start,
                      x_start + loop_offset, y_end, x_end, y_end]
            self.canvas.create_line(puntos, fill=color, width=2, arrow=tk.LAST)

            if arista.etiqueta:
                self._dibujar_badge_etiqueta(x_start + loop_offset / 2, (y_start + y_end) / 2, arista.etiqueta, color)

        # Destinos adyacentes o mismo nivel
        else:
            x_start = ox2 if dx1 > ox1 else ox1
            y_start = (oy1 + oy2) / 2
            x_end = dx1 if dx1 > ox1 else dx2
            y_end = (dy1 + dy2) / 2
            self.canvas.create_line(x_start, y_start, x_end, y_end, fill=color, width=2, arrow=tk.LAST)
            if arista.etiqueta:
                self._dibujar_badge_etiqueta((x_start + x_end) / 2, (y_start + y_end) / 2 - 10, arista.etiqueta, color)

    def _dibujar_badge_etiqueta(self, x: float, y: float, texto: str, color: str):
        fuente = ("Arial", max(7, int(8 * self.escala)), "bold")
        ancho_tag = len(texto) * 7 * self.escala + 8
        alto_tag = 14 * self.escala
        self.canvas.create_rectangle(
            x - ancho_tag / 2, y - alto_tag / 2,
            x + ancho_tag / 2, y + alto_tag / 2,
            fill="white", outline=color, width=1
        )
        self.canvas.create_text(x, y, text=texto, font=fuente, fill=color, anchor="center")
