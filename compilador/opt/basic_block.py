"""
Módulo de Identificación y Gestión de Bloques Básicos (Basic Blocks).
Materia: Lenguajes y Autómatas II - Unidad 3.

Un bloque básico es una secuencia lineal de instrucciones de código intermedio
que se ejecuta de principio a fin, con una única entrada (primer instrucción)
y una única salida (última instrucción), sin posibilidad de bifurcación interna.
"""

from typing import List, Optional
import copy

try:
    from compilador.ir.generator import Cuadruplo
except ImportError:
    from ..ir.generator import Cuadruplo


class BasicBlock:
    """
    Representa un Bloque Básico (BB) dentro del Grafo de Flujo de Control.
    """
    def __init__(self, id_bloque: str, instrucciones: Optional[List[Cuadruplo]] = None, etiqueta: str = ""):
        self.id = id_bloque                       # Ej: 'B1', 'B2', 'B3'
        self.instrucciones: List[Cuadruplo] = list(instrucciones or [])
        self.etiqueta: str = etiqueta             # Etiqueta destino si inicia con una (Ej: 'L1')
        self.es_inalcanzable: bool = False        # Marcado tras análisis de alcanzabilidad
        self.es_entrada: bool = False             # Si es el bloque de entrada
        self.es_salida: bool = False              # Si termina en return o fin de función

    @property
    def primera_instruccion(self) -> Optional[Cuadruplo]:
        return self.instrucciones[0] if self.instrucciones else None

    @property
    def ultima_instruccion(self) -> Optional[Cuadruplo]:
        return self.instrucciones[-1] if self.instrucciones else None

    @property
    def nombre_completo(self) -> str:
        if self.etiqueta:
            return f"{self.id} ({self.etiqueta})"
        return self.id

    def clonar(self) -> 'BasicBlock':
        nuevo = BasicBlock(self.id, [copy.copy(i) for i in self.instrucciones], self.etiqueta)
        nuevo.es_inalcanzable = self.es_inalcanzable
        nuevo.es_entrada = self.es_entrada
        nuevo.es_salida = self.es_salida
        return nuevo

    def obtener_texto_3ac(self) -> str:
        """Devuelve el código del bloque en formato 3AC legible."""
        lineas = []
        for inst in self.instrucciones:
            lineas.append(inst.to_3ac())
        return "\n".join(lineas)

    def obtener_texto_bloque(self) -> str:
        """Formato con encabezado de bloque como en el diseño de compiladores."""
        encabezado = self.nombre_completo
        if self.es_inalcanzable:
            encabezado += " [Inalcanzable]"
        lineas = [encabezado]
        for inst in self.instrucciones:
            lineas.append(f"  {inst.numero}: {inst.to_3ac()}")
        return "\n".join(lineas)

    def __repr__(self) -> str:
        return f"BasicBlock({self.nombre_completo!r}, insts={len(self.instrucciones)}, inalcanzable={self.es_inalcanzable})"


def es_salto(inst: Cuadruplo) -> bool:
    """Indica si la instrucción altera el flujo de control secuencial."""
    op = (inst.op or "").upper()
    return op in ("GOTO", "IF_FALSE", "IFFALSE", "IF_TRUE", "IFTRUE", "IF", "RETURN")


def es_salto_condicional(inst: Cuadruplo) -> bool:
    """Indica si la instrucción es una bifurcación condicional."""
    op = (inst.op or "").upper()
    return op in ("IF_FALSE", "IFFALSE", "IF_TRUE", "IFTRUE", "IF")


def es_salto_incondicional(inst: Cuadruplo) -> bool:
    """Indica si la instrucción es un salto incondicional."""
    op = (inst.op or "").upper()
    return op == "GOTO"


def es_retorno(inst: Cuadruplo) -> bool:
    """Indica si la instrucción termina la ejecución de la función/programa."""
    op = (inst.op or "").lower()
    return op == "return"


def identificar_bloques_basicos(instrucciones: List[Cuadruplo]) -> List[BasicBlock]:
    """
    Identifica los bloques básicos a partir de la lista de cuádruplos de acuerdo
    al algoritmo estándar del dragón (Aho, Lam, Sethi, Ullman):

    1. Determinar los líderes:
       a) La primera instrucción es un líder.
       b) Cualquier instrucción que sea el destino de un salto (LABEL) es un líder.
       c) Cualquier instrucción que siga inmediatamente a un salto o return es un líder.
    2. Cada líder inicia un bloque básico que se extiende hasta justo antes del
       siguiente líder o hasta el final del programa.
    """
    if not instrucciones:
        return []

    n = len(instrucciones)
    es_lider = [False] * n

    # Regla 1a: La primera instrucción es un líder
    es_lider[0] = True

    # Mapa de etiquetas a su posición en la lista de instrucciones
    mapa_etiquetas = {}
    for idx, inst in enumerate(instrucciones):
        op = (inst.op or "").upper()
        if op == "LABEL":
            etq = inst.resultado or inst.arg1
            if etq:
                mapa_etiquetas[etq] = idx

    # Reglas 1b y 1c:
    for idx, inst in enumerate(instrucciones):
        op = (inst.op or "").upper()
        if op == "LABEL":
            # La propia etiqueta marca el inicio de un bloque
            es_lider[idx] = True

        elif es_salto(inst):
            # El destino del salto es un líder
            destino = inst.resultado or inst.arg1
            if destino in mapa_etiquetas:
                es_lider[mapa_etiquetas[destino]] = True

            # La instrucción siguiente a un salto/return es un líder
            if idx + 1 < n:
                es_lider[idx + 1] = True

    # Paso 2: Particionar en bloques básicos
    bloques: List[BasicBlock] = []
    bloque_actual_insts: List[Cuadruplo] = []
    bloque_num = 1
    etiqueta_actual = ""

    for idx, inst in enumerate(instrucciones):
        if es_lider[idx] and bloque_actual_insts:
            # Cerrar el bloque anterior
            b = BasicBlock(f"B{bloque_num}", bloque_actual_insts, etiqueta_actual)
            bloques.append(b)
            bloque_num += 1
            bloque_actual_insts = []
            etiqueta_actual = ""

        # Si esta instrucción es una LABEL, registramos la etiqueta del bloque
        if (inst.op or "").upper() == "LABEL":
            etiqueta_actual = inst.resultado or inst.arg1

        bloque_actual_insts.append(inst)

    # Cerrar el último bloque
    if bloque_actual_insts:
        b = BasicBlock(f"B{bloque_num}", bloque_actual_insts, etiqueta_actual)
        bloques.append(b)

    # Identificar entrada y salidas
    if bloques:
        bloques[0].es_entrada = True
        for b in bloques:
            if b.instrucciones and es_retorno(b.instrucciones[-1]):
                b.es_salida = True
        # Si el último bloque no tiene return pero termina el programa, también es salida
        if not any(b.es_salida for b in bloques):
            bloques[-1].es_salida = True

    return bloques
