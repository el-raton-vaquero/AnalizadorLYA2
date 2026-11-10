
from .basic_block import BasicBlock, identificar_bloques_basicos, es_salto, es_salto_condicional, es_salto_incondicional, es_retorno
from .cfg import ControlFlowGraph, CFGEdge
from .optimizer import IROptimizer, Transformacion
from .visualizer import CFGCanvas
from .metrics import OptimizationReport
from .graph_coloring import (
    Grafo, parsear_grafo_texto, colorear_grafo_minimo,
    verificar_coloracion, ColoringCanvas, SeccionColoracionGrafos
)

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
    "optimizar_ir_completo",
    "Grafo",
    "parsear_grafo_texto",
    "colorear_grafo_minimo",
    "verificar_coloracion",
    "ColoringCanvas",
    "SeccionColoracionGrafos"
]


def optimizar_ir_completo(instrucciones):
    opt = IROptimizer(instrucciones)
    opt.optimizar()
    return opt
