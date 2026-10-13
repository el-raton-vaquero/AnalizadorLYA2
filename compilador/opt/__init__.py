"""
Módulo de Optimización de Código Intermedio mediante Grafo de Flujo de Control (CFG / GFG).
Materia: Lenguajes y Autómatas II - Unidad 3.
"""

from .basic_block import BasicBlock, identificar_bloques_basicos, es_salto, es_salto_condicional, es_salto_incondicional, es_retorno
from .cfg import ControlFlowGraph, CFGEdge
from .optimizer import IROptimizer, Transformacion
from .visualizer import CFGCanvas
from .metrics import OptimizationReport

__all__ = [
    "BasicBlock",
    "identificar_bloques_basicos",
    "es_salto",
    "es_salto_condicional",
    "es_salto_incondicional",
    "es_retorno",
    "ControlFlowGraph",
    "CFGEdge",
    "IROptimizer",
    "Transformacion",
    "CFGCanvas",
    "OptimizationReport",
    "optimizar_ir_completo"
]


def optimizar_ir_completo(instrucciones):
    """
    Función de alto nivel que toma una lista de cuádruplos y retorna el optimizador ejecutado.
    """
    opt = IROptimizer(instrucciones)
    opt.optimizar()
    return opt
