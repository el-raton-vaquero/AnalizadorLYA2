"""
Módulo de Métricas, Análisis y Generación de Reportes de Optimización.
Materia: Lenguajes y Autómatas II - Unidad 3.

Genera análisis comparativos de resultados, estadísticas de reducción de
código intermedio, métricas del Grafo de Flujo de Control y exportación de archivos
formales: before.ir, after.ir y reportes de texto/Markdown.
"""

from typing import Dict, List, Any
import os

from .cfg import ControlFlowGraph
from .optimizer import IROptimizer


class OptimizationReport:
    """
    Genera reportes técnicos y análisis formal de resultados para la optimización de IR.
    """
    def __init__(self, optimizer: IROptimizer):
        self.opt = optimizer
        self.cfg_orig = optimizer.cfg_original
        self.cfg_opt = optimizer.cfg_optimizado
        self.met_orig = self.cfg_orig.calcular_metricas()
        self.met_opt = self.cfg_opt.calcular_metricas() if self.cfg_opt else self.met_orig

    def obtener_resumen_estadistico(self) -> Dict[str, Any]:
        """Calcula el resumen comparativo cuantitativo."""
        n_inst_orig = len(self.opt.instrucciones_originales)
        n_inst_opt = len(self.opt.instrucciones_optimizadas)
        reduc_inst = max(0.0, ((n_inst_orig - n_inst_opt) / n_inst_orig * 100.0)) if n_inst_orig > 0 else 0.0

        # Conteo de temporales
        temps_orig = set()
        temps_opt = set()
        for i in self.opt.instrucciones_originales:
            for s in (i.arg1, i.arg2, i.resultado):
                if s and s.startswith("t") and s[1:].isdigit():
                    temps_orig.add(s)
        for i in self.opt.instrucciones_optimizadas:
            for s in (i.arg1, i.arg2, i.resultado):
                if s and s.startswith("t") and s[1:].isdigit():
                    temps_opt.add(s)

        return {
            "instrucciones_originales": n_inst_orig,
            "instrucciones_optimizadas": n_inst_opt,
            "instrucciones_eliminadas": n_inst_orig - n_inst_opt,
            "porcentaje_reduccion": reduc_inst,
            "temporales_originales": len(temps_orig),
            "temporales_optimizados": len(temps_opt),
            "bloques_originales": self.met_orig["nodos_total"],
            "bloques_optimizados": self.met_opt["nodos_total"],
            "complejidad_original": self.met_orig["complejidad_ciclomatica"],
            "complejidad_optimizada": self.met_opt["complejidad_ciclomatica"],
            "caminos_originales": self.met_orig["caminos_count"],
            "caminos_optimizados": self.met_opt["caminos_count"],
            "total_transformaciones": len(self.opt.transformaciones)
        }

    def generar_reporte_texto(self) -> str:
        """Genera el reporte técnico formal en formato texto estructurado."""
        stats = self.obtener_resumen_estadistico()
        lineas = []

        lineas.append("=" * 80)
        lineas.append("  REPORTE FORMAL DE OPTIMIZACIÓN DE CÓDIGO INTERMEDIO (IR)")
        lineas.append("  Materia: Lenguajes y Autómatas II - Unidad 3")
        lineas.append("  Técnica: Análisis mediante Grafo de Flujo de Control (GFG / CFG)")
        lineas.append("=" * 80)
        lineas.append("")

        # 1. Código Intermedio Original
        lineas.append("1. CÓDIGO INTERMEDIO ORIGINAL (before.ir)")
        lineas.append("-" * 80)
        for inst in self.opt.instrucciones_originales:
            lineas.append(f"  {inst.to_ir_tuple():<35} | 3AC: {inst.to_3ac()}")
        lineas.append("")

        # 2. Identificación de Bloques Básicos Originales
        lineas.append("2. IDENTIFICACIÓN DE BLOQUES BÁSICOS (CFG Original)")
        lineas.append("-" * 80)
        for b in self.opt.bloques_originales:
            lineas.append(b.obtener_texto_bloque())
            lineas.append("")

        # 3. Tabla de Sucesores Original
        lineas.append("3. TABLA DE SUCESORES (GFG Original)")
        lineas.append("-" * 80)
        lineas.append(f"  {'Bloque':<20} | {'Sucesores'}")
        lineas.append("  " + "-" * 50)
        for fila in self.cfg_orig.obtener_tabla_sucesores():
            lineas.append(f"  {fila['bloque']:<20} | {fila['sucesores']}")
        lineas.append("")

        # 4. Tabla de Transformaciones Aplicadas
        lineas.append("4. TABLA DE TRANSFORMACIONES APLICADAS")
        lineas.append("-" * 80)
        lineas.append(f"  {'#':<4} | {'Bloque':<8} | {'Técnica':<32} | {'Original':<22} | {'Optimizado'}")
        lineas.append("  " + "-" * 76)
        for t in self.opt.transformaciones:
            lineas.append(f"  {t.numero:<4} | {t.bloque:<8} | {t.tecnica:<32} | {t.original:<22} | {t.optimizado}")
            lineas.append(f"       Justificación: {t.justificacion}")
        lineas.append("")

        # 5. Tabla Comparativa de Transformaciones
        lineas.append("5. TABLA COMPARATIVA DE TRANSFORMACIONES (CFG Original vs Optimizado)")
        lineas.append("-" * 80)
        lineas.append(f"  {'Elemento':<30} | {'CFG Original':<15} | {'CFG Optimizado':<15} | {'Optimización'}")
        lineas.append("  " + "-" * 76)
        for c in self.opt.obtener_tabla_comparativa_cfg():
            lineas.append(f"  {c['elemento']:<30} | {c['cfg_original']:<15} | {c['cfg_optimizado']:<15} | {c['optimizacion']}")
        lineas.append("")

        # 6. Código Intermedio Optimizado
        lineas.append("6. CÓDIGO INTERMEDIO OPTIMIZADO (after.ir)")
        lineas.append("-" * 80)
        for inst in self.opt.instrucciones_optimizadas:
            lineas.append(f"  {inst.to_ir_tuple():<35} | 3AC: {inst.to_3ac()}")
        lineas.append("")

        # 7. Análisis de Resultados y Conclusiones
        lineas.append("7. ANÁLISIS DE RESULTADOS Y CONCLUSIONES")
        lineas.append("-" * 80)
        lineas.append(f"  • Instrucciones IR: de {stats['instrucciones_originales']} a {stats['instrucciones_optimizadas']} ({stats['instrucciones_eliminadas']} eliminadas, reducción: {stats['porcentaje_reduccion']:.1f}%).")
        lineas.append(f"  • Temporales activos: de {stats['temporales_originales']} a {stats['temporales_optimizados']}.")
        lineas.append(f"  • Complejidad ciclomática: de {stats['complejidad_original']} a {stats['complejidad_optimizada']}.")
        lineas.append(f"  • Caminos de ejecución en grafo: de {stats['caminos_originales']} a {stats['caminos_optimizados']}.")
        lineas.append("  • Contribución del GFG: El Grafo de Flujo de Control permitió aislar bloques")
        lineas.append("    básicos, identificar caminos no ejecutables (bloques inalcanzables tras return")
        lineas.append("    y ramas muertas por condiciones constantes), posibilitando la poda estructural")
        lineas.append("    del programa sin alterar la semántica ni el resultado final.")
        lineas.append("=" * 80)

        return "\n".join(lineas)

    def exportar_archivos(self, directorio: str, prefijo: str = "") -> Dict[str, str]:
        """
        Exporta before.ir, after.ir y el reporte completo de optimización.
        """
        os.makedirs(directorio, exist_ok=True)
        nombre_before = f"{prefijo}before.ir" if prefijo else "before.ir"
        nombre_after = f"{prefijo}after.ir" if prefijo else "after.ir"
        nombre_reporte = f"{prefijo}reporte_optimizacion.txt" if prefijo else "reporte_optimizacion.txt"

        ruta_before = os.path.join(directorio, nombre_before)
        ruta_after = os.path.join(directorio, nombre_after)
        ruta_reporte = os.path.join(directorio, nombre_reporte)

        # 1. before.ir
        with open(ruta_before, "w", encoding="utf-8") as f:
            for inst in self.opt.instrucciones_originales:
                f.write(inst.to_ir_tuple() + "\n")

        # 2. after.ir
        with open(ruta_after, "w", encoding="utf-8") as f:
            for inst in self.opt.instrucciones_optimizadas:
                f.write(inst.to_ir_tuple() + "\n")

        # 3. reporte
        with open(ruta_reporte, "w", encoding="utf-8") as f:
            f.write(self.generar_reporte_texto() + "\n")

        return {
            "before_ir": ruta_before,
            "after_ir": ruta_after,
            "reporte": ruta_reporte
        }
