"""
Módulo del Grafo de Flujo de Control (GFG / CFG - Control Flow Graph).
Materia: Lenguajes y Autómatas II - Unidad 3.

Construye y modela el grafo orientado donde los nodos son los Bloques Básicos
y las aristas representan el flujo de ejecución del programa.
Permite análisis de alcanzabilidad, cálculo de caminos y complejidad ciclomática.
"""

from typing import List, Dict, Set, Tuple, Optional
from collections import deque
from .basic_block import BasicBlock, es_salto_condicional, es_salto_incondicional, es_retorno


class CFGEdge:
    """Arista dirigida entre dos bloques en el CFG."""
    def __init__(self, origen: str, destino: str, etiqueta: str = "", tipo: str = "normal"):
        self.origen = origen      # Ej: 'B1'
        self.destino = destino    # Ej: 'B2', o 'Exit'
        self.etiqueta = etiqueta  # Ej: 'Sí', 'No', 'goto', 'ret'
        self.tipo = tipo          # 'cond_true', 'cond_false', 'jump', 'fallthrough', 'exit'

    def __repr__(self) -> str:
        tag = f" [{self.etiqueta}]" if self.etiqueta else ""
        return f"{self.origen} -> {self.destino}{tag}"


class ControlFlowGraph:
    """
    Grafo de Flujo de Control (CFG / GFG).
    """
    def __init__(self, bloques: List[BasicBlock]):
        self.bloques: List[BasicBlock] = list(bloques)
        self.mapa_bloques: Dict[str, BasicBlock] = {b.id: b for b in self.bloques}
        self.mapa_etiquetas: Dict[str, BasicBlock] = {}
        for b in self.bloques:
            if b.etiqueta:
                self.mapa_etiquetas[b.etiqueta] = b
            for inst in b.instrucciones:
                if (inst.op or "").upper() == "LABEL":
                    etq = inst.resultado or inst.arg1
                    if etq and etq not in self.mapa_etiquetas:
                        self.mapa_etiquetas[etq] = b

        self.aristas: List[CFGEdge] = []
        self.sucesores: Dict[str, List[str]] = {b.id: [] for b in self.bloques}
        self.predecesores: Dict[str, List[str]] = {b.id: [] for b in self.bloques}
        self.sucesores["Exit"] = []
        self.predecesores["Exit"] = []

        self._construir()
        self.analizar_alcanzabilidad()

    def _agregar_arista(self, origen: str, destino: str, etiqueta: str = "", tipo: str = "normal"):
        arista = CFGEdge(origen, destino, etiqueta, tipo)
        self.aristas.append(arista)
        if destino not in self.sucesores[origen]:
            self.sucesores[origen].append(destino)
        if origen not in self.predecesores.setdefault(destino, []):
            self.predecesores[destino].append(origen)

    def _construir(self):
        """Conecta los bloques analizando la última instrucción de cada uno."""
        n = len(self.bloques)
        for i, b in enumerate(self.bloques):
            sig_bloque = self.bloques[i + 1] if i + 1 < n else None
            ultima = b.ultima_instruccion

            if not ultima:
                if sig_bloque:
                    self._agregar_arista(b.id, sig_bloque.id, "", "fallthrough")
                else:
                    self._agregar_arista(b.id, "Exit", "", "exit")
                continue

            op = (ultima.op or "").upper()

            # 1. Instrucción RETURN
            if es_retorno(ultima):
                self._agregar_arista(b.id, "Exit", "return", "exit")

            # 2. Salto incondicional: GOTO L
            elif es_salto_incondicional(ultima):
                dest_label = ultima.resultado or ultima.arg1
                if dest_label in self.mapa_etiquetas:
                    dest_block = self.mapa_etiquetas[dest_label]
                    self._agregar_arista(b.id, dest_block.id, "goto", "jump")
                else:
                    self._agregar_arista(b.id, "Exit", "goto", "jump")

            # 3. Salto condicional: IF_FALSE cond goto L
            elif op in ("IF_FALSE", "IFFALSE"):
                dest_label = ultima.resultado or ultima.arg1
                dest_block = self.mapa_etiquetas.get(dest_label)

                # Si es falso, salta a la etiqueta dest_label (rama "No" o false)
                if dest_block:
                    self._agregar_arista(b.id, dest_block.id, "No", "cond_false")

                # Si es verdadero, continúa al bloque siguiente (rama "Sí" o true)
                if sig_bloque:
                    self._agregar_arista(b.id, sig_bloque.id, "Sí", "cond_true")
                else:
                    self._agregar_arista(b.id, "Exit", "Sí", "exit")

            # 4. Salto condicional: IF cond goto L / IF_TRUE
            elif op in ("IF", "IF_TRUE", "IFTRUE"):
                dest_label = ultima.resultado or ultima.arg1
                dest_block = self.mapa_etiquetas.get(dest_label)

                # Si es verdadero, salta a dest_label (rama "Sí" o true)
                if dest_block:
                    self._agregar_arista(b.id, dest_block.id, "Sí", "cond_true")

                # Si es falso, continúa al bloque siguiente (rama "No" o false)
                if sig_bloque:
                    self._agregar_arista(b.id, sig_bloque.id, "No", "cond_false")
                else:
                    self._agregar_arista(b.id, "Exit", "No", "exit")

            # 5. Flujo secuencial ordinario (caída al bloque contiguo)
            else:
                if sig_bloque:
                    self._agregar_arista(b.id, sig_bloque.id, "", "fallthrough")
                else:
                    self._agregar_arista(b.id, "Exit", "", "exit")

    def analizar_alcanzabilidad(self) -> Tuple[List[str], List[str]]:
        """
        Determina qué bloques son alcanzables desde el nodo de entrada.
        Cualquier bloque sin ruta desde el inicio se marca como inalcanzable.
        """
        if not self.bloques:
            return [], []

        entrada_id = self.bloques[0].id
        visitados: Set[str] = set()
        cola = deque([entrada_id])

        while cola:
            curr = cola.popleft()
            if curr in visitados:
                continue
            visitados.add(curr)

            for suc in self.sucesores.get(curr, []):
                if suc != "Exit" and suc not in visitados:
                    cola.append(suc)

        alcanzables = []
        inalcanzables = []

        for b in self.bloques:
            if b.id in visitados:
                b.es_inalcanzable = False
                alcanzables.append(b.id)
            else:
                b.es_inalcanzable = True
                inalcanzables.append(b.id)

        return alcanzables, inalcanzables

    def obtener_tabla_sucesores(self) -> List[Dict[str, str]]:
        """
        Genera la Tabla de Sucesores en formato formal:
        Bloque | Sucesores
        """
        tabla = []
        for b in self.bloques:
            sucs = self.sucesores.get(b.id, [])
            if b.es_inalcanzable:
                sucs_texto = "Ninguno (inalcanzable)"
            elif not sucs:
                sucs_texto = "Fin"
            else:
                formateados = []
                for s in sucs:
                    if s == "Exit":
                        formateados.append("Fin")
                    else:
                        formateados.append(s)
                sucs_texto = ", ".join(formateados)

            tabla.append({
                "bloque": b.nombre_completo,
                "id": b.id,
                "sucesores": sucs_texto,
                "es_inalcanzable": b.es_inalcanzable
            })
        return tabla

    def calcular_caminos(self, max_caminos: int = 50) -> List[List[str]]:
        """
        Encuentra todos los caminos de ejecución posibles desde Entry hasta Exit.
        Usa DFS para evitar ciclos infinitos en loops.
        """
        if not self.bloques:
            return []

        inicio = self.bloques[0].id
        caminos: List[List[str]] = []

        def dfs(actual: str, camino: List[str], visitados_en_camino: Set[str]):
            if len(caminos) >= max_caminos:
                return
            if actual == "Exit":
                caminos.append(list(camino))
                return

            sucs = self.sucesores.get(actual, [])
            if not sucs:
                caminos.append(camino + ["Exit"])
                return

            for s in sucs:
                # Evitar loops infinitos en el mismo camino
                if s not in visitados_en_camino:
                    visitados_en_camino.add(s)
                    dfs(s, camino + [s], visitados_en_camino)
                    visitados_en_camino.remove(s)

        dfs(inicio, [inicio], {inicio})
        return caminos

    def calcular_metricas(self) -> Dict[str, any]:
        """
        Calcula las métricas estándar del Grafo de Flujo de Control:
        - N: Número de nodos (bloques alcanzables + Exit)
        - E: Número de aristas entre bloques alcanzables
        - P: Componentes conexas (1)
        - Complejidad Ciclomática: V(G) = E - N + 2P
        - Nodos de decisión (predicados D, V(G) = D + 1)
        - Total de caminos válidos
        """
        alcanzables, inalcanzables = self.analizar_alcanzabilidad()
        nodos_activos = set(alcanzables) | {"Exit"}
        n = len(nodos_activos)

        aristas_activas = [a for a in self.aristas if a.origen in alcanzables and a.destino in nodos_activos]
        e = len(aristas_activas)
        p = 1

        # Complejidad ciclomática mediante fórmula de McCabe
        v_g = max(1, e - n + 2 * p) if n > 1 else 1

        # También verificar por nodos de decisión (out-degree >= 2)
        decisiones = 0
        for b_id in alcanzables:
            sucs = [s for s in self.sucesores.get(b_id, []) if s in nodos_activos]
            if len(sucs) >= 2:
                decisiones += 1

        caminos = self.calcular_caminos()

        return {
            "nodos_total": len(self.bloques),
            "nodos_alcanzables": len(alcanzables),
            "nodos_inalcanzables": len(inalcanzables),
            "aristas": e,
            "complejidad_ciclomatica": v_g,
            "decisiones": decisiones,
            "caminos_count": len(caminos),
            "caminos": caminos
        }

    def generar_diagrama_ascii(self) -> str:
        """
        Genera una vista esquemática y clara del flujo entre bloques básicos.
        """
        lineas = ["=== Estructura del Grafo de Flujo (CFG) ==="]
        for b in self.bloques:
            estado = " [Inalcanzable]" if b.es_inalcanzable else ""
            lineas.append(f"\n[{b.nombre_completo}{estado}]")
            for inst in b.instrucciones:
                lineas.append(f"   │  {inst.to_3ac()}")

            sucs = self.sucesores.get(b.id, [])
            if sucs and not b.es_inalcanzable:
                aristas_salientes = [a for a in self.aristas if a.origen == b.id]
                for a in aristas_salientes:
                    tag = f" ({a.etiqueta})" if a.etiqueta else ""
                    dest_nom = "Fin (Exit)" if a.destino == "Exit" else a.destino
                    lineas.append(f"   └──> {dest_nom}{tag}")
            elif b.es_inalcanzable:
                lineas.append("   └──x (Sin flujo activo)")
            else:
                lineas.append("   └──> Fin (Exit)")

        return "\n".join(lineas)
