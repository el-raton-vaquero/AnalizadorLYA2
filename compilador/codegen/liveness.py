"""
Módulo de Análisis de Variables Vivas (Liveness Analysis) y Grafo de Interferencia.
Implementa el análisis de flujo de datos hacia atrás (backward dataflow) sobre
cuádruplos de código intermedio para determinar el rango de vida de cada variable
y construir el grafo de interferencia formal para asignación de registros.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Set, Tuple, Optional
import re

from compilador.ir.generator import Cuadruplo
from compilador.opt.graph_coloring import Grafo


def es_identificador_variable(token: str, etiquetas_conocidas: Optional[Set[str]] = None) -> bool:
    """
    Determina si un operando de cuádruplo corresponde a una variable o temporal,
    descartando números, constantes de texto, booleanos y etiquetas de salto.
    """
    if not token or not isinstance(token, str):
        return False
    token = token.strip()
    if not token:
        return False

    # Descartar literales de cadena y caracteres
    if (token.startswith('"') and token.endswith('"')) or (token.startswith("'") and token.endswith("'")):
        return False

    # Descartar números enteros y flotantes (incluyendo signos)
    if re.match(r'^-?\d+(\.\d+)?$', token):
        return False

    # Descartar palabras reservadas o constantes comunes
    if token.lower() in ('true', 'false', 'null', 'nullptr', 'endl', 'void'):
        return False

    # Descartar etiquetas de salto si se conocen
    if etiquetas_conocidas and token in etiquetas_conocidas:
        return False

    # Validar formato estándar de identificador
    return bool(re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', token))


@dataclass
class LiveRange:
    """Representa el intervalo o rango de vida útil de una variable."""
    variable: str
    inicio: int
    fin: int
    es_temporal: bool

    @property
    def duracion(self) -> int:
        return max(1, self.fin - self.inicio + 1)

    def se_solapa_con(self, otro: 'LiveRange') -> bool:
        """Determina si dos rangos de vida se intersecan en alguna instrucción."""
        return not (self.fin < otro.inicio or otro.fin < self.inicio)


@dataclass
class LivenessResult:
    """Resultado estructurado del análisis de variables vivas e interferencia."""
    cuadruplos: List[Cuadruplo]
    variables: List[str]
    temporales: List[str]
    live_in: List[Set[str]]
    live_out: List[Set[str]]
    def_sets: List[Set[str]]
    use_sets: List[Set[str]]
    rangos_vida: Dict[str, LiveRange]
    grafo_interferencia: Grafo
    interferencias_por_variable: Dict[str, Set[str]]

    def generar_texto_adyacencia(self) -> str:
        """Genera el texto de lista de adyacencia estándar para el módulo de coloración."""
        lineas = []
        for v in self.variables:
            vecinos = sorted(list(self.interferencias_por_variable.get(v, set())))
            lineas.append(f"{v}: {', '.join(vecinos)}")
        return "\n".join(lineas)


class LivenessAnalyzer:
    r"""
    Analizador formal de variables vivas mediante ecuaciones de flujo de datos hacia atrás:
      In[i]  = Use[i] ∪ (Out[i] \ Def[i])
      Out[i] = ∪ { In[s] | s ∈ Succ[i] }
    """

    def __init__(self, cuadruplos: List[Cuadruplo]):
        self.cuadruplos = list(cuadruplos)
        self.n = len(self.cuadruplos)

        # 1. Identificar etiquetas
        self.etiquetas: Set[str] = set()
        self.mapa_etiquetas: Dict[str, int] = {}
        for idx, c in enumerate(self.cuadruplos):
            op_up = c.op.upper()
            if op_up == "LABEL" and c.resultado:
                lbl = c.resultado.strip()
                self.etiquetas.add(lbl)
                self.mapa_etiquetas[lbl] = idx

        # También registrar destinos de saltos
        for c in self.cuadruplos:
            op_up = c.op.upper()
            if op_up in ("GOTO", "IF_FALSE", "IFFALSE", "IF_TRUE", "IFTRUE") and c.resultado:
                self.etiquetas.add(c.resultado.strip())

        # 2. Extraer todas las variables y temporales
        self.variables_set: Set[str] = set()
        for c in self.cuadruplos:
            for campo in (c.arg1, c.arg2, c.resultado):
                if es_identificador_variable(campo, self.etiquetas):
                    self.variables_set.add(campo.strip())

        self.variables: List[str] = sorted(
            list(self.variables_set),
            key=lambda x: (0 if not x.startswith('t') else 1, x)
        )

    def _computar_def_use(self) -> Tuple[List[Set[str]], List[Set[str]]]:
        """Calcula los conjuntos Def[i] y Use[i] para cada cuádruplo."""
        def_sets: List[Set[str]] = []
        use_sets: List[Set[str]] = []

        for c in self.cuadruplos:
            d_set: Set[str] = set()
            u_set: Set[str] = set()

            op_up = c.op.upper()
            op = c.op

            if op_up == "LABEL":
                pass
            elif op_up == "GOTO":
                pass
            elif op_up in ("IF_FALSE", "IFFALSE", "IF_TRUE", "IFTRUE"):
                if es_identificador_variable(c.arg1, self.etiquetas):
                    u_set.add(c.arg1.strip())
            elif op == "=":
                if es_identificador_variable(c.arg1, self.etiquetas):
                    u_set.add(c.arg1.strip())
                if es_identificador_variable(c.resultado, self.etiquetas):
                    d_set.add(c.resultado.strip())
            elif op in ("+", "-", "*", "/", "%", "==", "!=", "<", ">", "<=", ">=", "&&", "||"):
                if es_identificador_variable(c.arg1, self.etiquetas):
                    u_set.add(c.arg1.strip())
                if es_identificador_variable(c.arg2, self.etiquetas):
                    u_set.add(c.arg2.strip())
                if es_identificador_variable(c.resultado, self.etiquetas):
                    d_set.add(c.resultado.strip())
            elif op in ("neg", "!"):
                if es_identificador_variable(c.arg1, self.etiquetas):
                    u_set.add(c.arg1.strip())
                if es_identificador_variable(c.resultado, self.etiquetas):
                    d_set.add(c.resultado.strip())
            elif op == "[]":
                if es_identificador_variable(c.arg1, self.etiquetas):
                    u_set.add(c.arg1.strip())
                if es_identificador_variable(c.arg2, self.etiquetas):
                    u_set.add(c.arg2.strip())
                if es_identificador_variable(c.resultado, self.etiquetas):
                    d_set.add(c.resultado.strip())
            elif op == "[]=":
                if es_identificador_variable(c.arg1, self.etiquetas):
                    u_set.add(c.arg1.strip())
                if es_identificador_variable(c.arg2, self.etiquetas):
                    u_set.add(c.arg2.strip())
                if es_identificador_variable(c.resultado, self.etiquetas):
                    u_set.add(c.resultado.strip())
            elif op == "print":
                if es_identificador_variable(c.arg1, self.etiquetas):
                    u_set.add(c.arg1.strip())
            elif op == "read":
                dest = c.resultado or c.arg1
                if es_identificador_variable(dest, self.etiquetas):
                    d_set.add(dest.strip())
            elif op == "param":
                if es_identificador_variable(c.arg1, self.etiquetas):
                    u_set.add(c.arg1.strip())
            elif op == "call":
                if es_identificador_variable(c.resultado, self.etiquetas):
                    d_set.add(c.resultado.strip())
            elif op == "return":
                if es_identificador_variable(c.arg1, self.etiquetas):
                    u_set.add(c.arg1.strip())
            else:
                # Caso genérico
                if es_identificador_variable(c.arg1, self.etiquetas):
                    u_set.add(c.arg1.strip())
                if es_identificador_variable(c.arg2, self.etiquetas):
                    u_set.add(c.arg2.strip())
                if es_identificador_variable(c.resultado, self.etiquetas):
                    d_set.add(c.resultado.strip())

            def_sets.append(d_set)
            use_sets.append(u_set)

        return def_sets, use_sets

    def _computar_sucesores(self) -> List[List[int]]:
        """Determina los sucesores de flujo de control para cada instrucción."""
        sucesores: List[List[int]] = []

        for idx, c in enumerate(self.cuadruplos):
            succ_idx: List[int] = []
            op_up = c.op.upper()

            if op_up == "GOTO":
                lbl = c.resultado.strip()
                if lbl in self.mapa_etiquetas:
                    succ_idx.append(self.mapa_etiquetas[lbl])
            elif op_up in ("IF_FALSE", "IFFALSE", "IF_TRUE", "IFTRUE"):
                # Bifurcación: caída al siguiente + salto a etiqueta
                if idx + 1 < self.n:
                    succ_idx.append(idx + 1)
                lbl = c.resultado.strip()
                if lbl in self.mapa_etiquetas:
                    succ_idx.append(self.mapa_etiquetas[lbl])
            elif c.op == "return":
                # Fin de control de flujo
                pass
            else:
                # Instrucción secuencial
                if idx + 1 < self.n:
                    succ_idx.append(idx + 1)

            sucesores.append(succ_idx)

        return sucesores

    def analizar(self) -> LivenessResult:
        """
        Ejecuta el análisis de liveness punto fijo y construye el grafo de interferencia.
        """
        if self.n == 0:
            return LivenessResult(
                cuadruplos=[],
                variables=[],
                temporales=[],
                live_in=[],
                live_out=[],
                def_sets=[],
                use_sets=[],
                rangos_vida={},
                grafo_interferencia=Grafo(),
                interferencias_por_variable={}
            )

        def_sets, use_sets = self._computar_def_use()
        sucesores = self._computar_sucesores()

        live_in: List[Set[str]] = [set() for _ in range(self.n)]
        live_out: List[Set[str]] = [set() for _ in range(self.n)]

        # Punto fijo iterativo hacia atrás
        cambio = True
        max_iter = self.n * 5 + 10
        iteraciones = 0

        while cambio and iteraciones < max_iter:
            cambio = False
            iteraciones += 1

            for i in range(self.n - 1, -1, -1):
                # Out[i] = U In[s] para s en Sucesores[i]
                nuevo_out: Set[str] = set()
                for s in sucesores[i]:
                    nuevo_out.update(live_in[s])

                # In[i] = Use[i] U (Out[i] \ Def[i])
                nuevo_in: Set[str] = set(use_sets[i]).union(nuevo_out - def_sets[i])

                if nuevo_out != live_out[i]:
                    live_out[i] = nuevo_out
                    cambio = True

                if nuevo_in != live_in[i]:
                    live_in[i] = nuevo_in
                    cambio = True

        # Calcular rangos de vida (Live Ranges)
        rangos: Dict[str, Tuple[int, int]] = {}
        for var in self.variables:
            primero = -1
            ultimo = -1
            for i in range(self.n):
                if var in def_sets[i] or var in use_sets[i] or var in live_in[i] or var in live_out[i]:
                    if primero == -1:
                        primero = i + 1  # 1-indexed para presentación amigable
                    ultimo = i + 1
            if primero == -1:
                primero = 1
                ultimo = 1
            rangos[var] = (primero, ultimo)

        rangos_vida: Dict[str, LiveRange] = {
            var: LiveRange(
                variable=var,
                inicio=rangos[var][0],
                fin=rangos[var][1],
                es_temporal=var.startswith('t') and var[1:].isdigit()
            )
            for var in self.variables
        }

        # Construir Grafo de Interferencia
        grafo = Grafo()
        for var in self.variables:
            grafo.agregar_nodo(var)

        interferencias: Dict[str, Set[str]] = {v: set() for v in self.variables}

        # Regla estándar de compilador:
        # 1. Si d se define en i, d interfiere con todo v en Out[i] (excepto si i es copia d = v)
        for i in range(self.n):
            c = self.cuadruplos[i]
            es_copia = (c.op == "=")
            fuente_copia = c.arg1.strip() if es_copia else None

            for d in def_sets[i]:
                for v in live_out[i]:
                    if v != d:
                        if es_copia and v == fuente_copia:
                            continue
                        grafo.agregar_arista(d, v)
                        interferencias[d].add(v)
                        interferencias[v].add(d)

            # 2. Variables simultáneamente vivas en Out[i]
            vars_en_out = list(live_out[i])
            for idx_a in range(len(vars_en_out)):
                for idx_b in range(idx_a + 1, len(vars_en_out)):
                    va = vars_en_out[idx_a]
                    vb = vars_en_out[idx_b]
                    grafo.agregar_arista(va, vb)
                    interferencias[va].add(vb)
                    interferencias[vb].add(va)

        temporales = [v for v in self.variables if v.startswith('t') and v[1:].isdigit()]

        return LivenessResult(
            cuadruplos=self.cuadruplos,
            variables=self.variables,
            temporales=temporales,
            live_in=live_in,
            live_out=live_out,
            def_sets=def_sets,
            use_sets=use_sets,
            rangos_vida=rangos_vida,
            grafo_interferencia=grafo,
            interferencias_por_variable=interferencias
        )


def construir_grafo_interferencia(cuadruplos: List[Cuadruplo]) -> LivenessResult:
    """Función de conveniencia para ejecutar el análisis de variables vivas e interferencia."""
    analyzer = LivenessAnalyzer(cuadruplos)
    return analyzer.analizar()
