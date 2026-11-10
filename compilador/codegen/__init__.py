"""
Módulo de Generación de Código Objeto (Fase Final del Compilador).
Integra:
  - Análisis de Variables Vivas (Liveness Analysis) y Construcción del Grafo de Interferencia.
  - Asignación de Registros por Coloración de Grafos (chi mínimo, mapeo a EAX..EDI y derrames).
  - Generador de Código Ensamblador (.asm) estructurado en .data, .bss y .text.
  - Simulador de Arquitectura x86 simplificada para validación y ejecución funcional.
"""

from dataclasses import dataclass
from typing import List, Dict, Optional, Union, Any

from compilador.ir.generator import Cuadruplo, generar_ir, IRGenerator
from compilador.opt import IROptimizer, optimizar_ir_completo
from .liveness import (
    LivenessAnalyzer, LiveRange, LivenessResult,
    construir_grafo_interferencia, es_identificador_variable
)
from .register_allocator import (
    RegisterAllocator, RegistroInfo,
    REGISTROS_X86, REGISTROS_VIRTUALES
)
from .code_generator import CodeGenerator
from .simulator import SimulatorASM, ExecutionResult


@dataclass
class ResultadoCompilacionObjeto:
    """Contenedor de todos los productos y evidencias de la generación de código objeto."""
    cuadruplos_originales: List[Cuadruplo]
    cuadruplos_optimizados: List[Cuadruplo]
    liveness: LivenessResult
    allocator: RegisterAllocator
    codigo_asm: str
    resultado_ejecucion: ExecutionResult
    optimizador: Optional[IROptimizer] = None


def generar_codigo_objeto_completo(
    origen: Union[str, List[Cuadruplo]],
    optimizar: bool = True,
    entrada_stdin: str = "",
    ejecutar: bool = True
) -> ResultadoCompilacionObjeto:
    """
    Pipeline unificado de generación de código objeto:
      Código C++ / IR -> Optimización CFG -> Liveness -> Coloración -> ASM -> Ejecución
    """
    opt = None
    cuads_orig: List[Cuadruplo] = []

    if isinstance(origen, str):
        cuads_orig, _, _ = generar_ir(origen)
    elif isinstance(origen, list):
        cuads_orig = list(origen)
    else:
        raise ValueError("El origen debe ser un código fuente en C++ (str) o una lista de Cuadruplo.")

    if optimizar and cuads_orig:
        opt = optimizar_ir_completo(cuads_orig)
        cuads_trabajo = opt.instrucciones_optimizadas
    else:
        cuads_trabajo = list(cuads_orig)

    # 1. Análisis de liveness e interferencia
    liveness = construir_grafo_interferencia(cuads_trabajo)

    # 2. Asignación de registros por coloración de grafos
    allocator = RegisterAllocator(liveness)

    # 3. Generación de código objeto .asm
    gen = CodeGenerator(cuads_trabajo, allocator)
    codigo_asm = gen.generar_codigo()

    # 4. Ejecución en simulador si se solicita
    if ejecutar:
        sim = SimulatorASM(codigo_asm, entrada_stdin=entrada_stdin)
        res_exec = sim.ejecutar()
    else:
        res_exec = ExecutionResult(
            exitoso=True,
            codigo_retorno=0,
            salida="",
            registros_finales={},
            memoria_final={},
            instrucciones_ejecutadas=0
        )

    return ResultadoCompilacionObjeto(
        cuadruplos_originales=cuads_orig,
        cuadruplos_optimizados=cuads_trabajo,
        liveness=liveness,
        allocator=allocator,
        codigo_asm=codigo_asm,
        resultado_ejecucion=res_exec,
        optimizador=opt
    )


__all__ = [
    "LivenessAnalyzer",
    "LiveRange",
    "LivenessResult",
    "construir_grafo_interferencia",
    "es_identificador_variable",
    "RegisterAllocator",
    "RegistroInfo",
    "REGISTROS_X86",
    "REGISTROS_VIRTUALES",
    "CodeGenerator",
    "SimulatorASM",
    "ExecutionResult",
    "ResultadoCompilacionObjeto",
    "generar_codigo_objeto_completo"
]

