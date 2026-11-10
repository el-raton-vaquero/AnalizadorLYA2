"""
Módulo de Asignación de Registros mediante Coloración de Grafos de Interferencia.
Implementa el algoritmo óptimo de coloración mínima chi(G) para asignar registros
físicos (EAX, EBX, ECX, EDX, ESI, EDI) y virtuales (R0..Rn) a todas las variables
y temporales del compilador, minimizando el número de registros y evitando colisiones.
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple, Set, Optional

from compilador.opt.graph_coloring import Grafo, colorear_grafo_minimo, verificar_coloracion
from compilador.codegen.liveness import LivenessResult, LiveRange, LivenessAnalyzer


REGISTROS_X86 = ["EAX", "EBX", "ECX", "EDX", "ESI", "EDI"]
REGISTROS_VIRTUALES = [f"R{i}" for i in range(32)]


@dataclass
class RegistroInfo:
    """Información completa de asignación de registro para una variable o temporal."""
    variable: str
    es_temporal: bool
    rango_vida: Tuple[int, int]
    interferencias: List[str]
    grado: int
    color: int
    registro_virtual: str
    registro_fisico: str
    ubicacion: str
    es_spill: bool


class RegisterAllocator:
    """
    Asignador formal de registros basado en coloración de grafos.
    Construye la asignación óptima garantizando que ninguna pareja de variables
    con interferencia (simultáneamente vivas) comparta el mismo registro.
    """

    def __init__(self, liveness: LivenessResult, k_fisicos: int = 6):
        self.liveness = liveness
        self.k_fisicos = k_fisicos
        self.registros_x86_disponibles = REGISTROS_X86[:k_fisicos]

        self.coloracion: Dict[str, int] = {}
        self.chi: int = 0
        self.es_valida: bool = True
        self.tabla_asignacion: Dict[str, RegistroInfo] = {}
        self.mapa_variable_registro: Dict[str, str] = {}
        self.spills: List[str] = []

        self._asignar()

    def _asignar(self) -> None:
        grafo = self.liveness.grafo_interferencia

        if not grafo.nodos:
            self.coloracion = {}
            self.chi = 0
            self.es_valida = True
            return

        # 1. Coloración de grafos mínima exacta
        self.coloracion, self.chi, self.es_valida = colorear_grafo_minimo(grafo)

        # 2. Mapear colores a registros físicos y virtuales
        for var in self.liveness.variables:
            color = self.coloracion.get(var, 0)
            reg_virt = f"R{color}"

            es_temp = var.startswith('t') and var[1:].isdigit()
            rango = (1, 1)
            if var in self.liveness.rangos_vida:
                lr = self.liveness.rangos_vida[var]
                rango = (lr.inicio, lr.fin)

            vecinos = sorted(list(self.liveness.interferencias_por_variable.get(var, set())))
            grado = len(vecinos)

            if color < len(self.registros_x86_disponibles):
                reg_fis = self.registros_x86_disponibles[color]
                ubicacion = f"Registro {reg_fis}"
                es_spill = False
                self.mapa_variable_registro[var] = reg_fis.lower()
            else:
                spill_idx = color - len(self.registros_x86_disponibles)
                reg_fis = f"MEM_S{spill_idx + 1}"
                ubicacion = f"Memoria [bp-{4 * (spill_idx + 1)}]"
                es_spill = True
                self.spills.append(var)
                self.mapa_variable_registro[var] = f"[bp-{4 * (spill_idx + 1)}]"

            self.tabla_asignacion[var] = RegistroInfo(
                variable=var,
                es_temporal=es_temp,
                rango_vida=rango,
                interferencias=vecinos,
                grado=grado,
                color=color,
                registro_virtual=reg_virt,
                registro_fisico=reg_fis,
                ubicacion=ubicacion,
                es_spill=es_spill
            )

    def obtener_filas_tabla(self) -> List[Tuple]:
        """
        Retorna las filas para poblar un Treeview de GUI o reporte estructurado.
        Columnas: (Variable, Tipo, Rango de Vida, Grado, Interferencias, Color, Reg. Virtual, Reg. x86, Ubicación)
        """
        filas = []
        for var in self.liveness.variables:
            info = self.tabla_asignacion.get(var)
            if not info:
                continue
            tipo_desc = "Temporal" if info.es_temporal else "Variable"
            rango_str = f"[{info.rango_vida[0]}, {info.rango_vida[1]}]"
            inter_str = ", ".join(info.interferencias) if info.interferencias else "—"
            filas.append((
                info.variable,
                tipo_desc,
                rango_str,
                str(info.grado),
                inter_str,
                f"Color {info.color + 1} (C{info.color + 1})",
                info.registro_virtual,
                info.registro_fisico,
                info.ubicacion
            ))
        return filas

    def generar_tabla_texto(self) -> str:
        """Genera una tabla ASCII formal para consola, reportes y documentación."""
        lineas = []
        sep = "+" + "-" * 12 + "+" + "-" * 12 + "+" + "-" * 14 + "+" + "-" * 8 + "+" + "-" * 26 + "+" + "-" * 10 + "+" + "-" * 12 + "+" + "-" * 12 + "+" + "-" * 22 + "+"
        header = f"| {'Variable':<10} | {'Tipo':<10} | {'Rango Vida':<12} | {'Grado':<6} | {'Interfiere Con':<24} | {'Color':<8} | {'Virtual':<10} | {'Reg. x86':<10} | {'Ubicación':<20} |"

        lineas.append(sep)
        lineas.append(header)
        lineas.append(sep)

        for f in self.obtener_filas_tabla():
            var, tipo, rango, grado, inters, color, reg_v, reg_x, ub = f
            if len(inters) > 24:
                inters = inters[:21] + "..."
            lineas.append(
                f"| {var:<10} | {tipo:<10} | {rango:<12} | {grado:<6} | {inters:<24} | {color:<8} | {reg_v:<10} | {reg_x:<10} | {ub:<20} |"
            )

        lineas.append(sep)
        return "\n".join(lineas)

    def obtener_metricas(self) -> Dict[str, object]:
        """Calcula métricas globales de la asignación de registros."""
        total_vars = len(self.liveness.variables)
        total_temps = len(self.liveness.temporales)
        total_user = total_vars - total_temps
        aristas = len(self.liveness.grafo_interferencia.obtener_aristas())

        max_aristas = (total_vars * (total_vars - 1)) // 2 if total_vars > 1 else 1
        densidad = (aristas / max_aristas) * 100 if max_aristas > 0 else 0.0

        colores_usados = set(self.coloracion.values())
        regs_utilizados = min(len(colores_usados), self.k_fisicos)

        # Reutilización: variables que comparten registro con al menos otra
        conteo_colores: Dict[int, int] = {}
        for c in self.coloracion.values():
            conteo_colores[c] = conteo_colores.get(c, 0) + 1
        vars_reutilizadas = sum(cnt for cnt in conteo_colores.values() if cnt > 1)

        return {
            "total_variables": total_vars,
            "variables_usuario": total_user,
            "temporales": total_temps,
            "numero_cromatico": self.chi,
            "registros_disponibles": self.k_fisicos,
            "registros_utilizados": regs_utilizados,
            "total_interferencias": aristas,
            "densidad_grafo": round(densidad, 2),
            "spills": len(self.spills),
            "variables_con_reutilizacion": vars_reutilizadas,
            "coloracion_valida": self.es_valida
        }

    def generar_resumen_metricas_texto(self) -> str:
        m = self.obtener_metricas()
        return (
            f"============================================================\n"
            f"  RESUMEN DE ASIGNACIÓN DE REGISTROS (COLORACIÓN DE GRAFOS)\n"
            f"============================================================\n"
            f"• Total de variables / temporales analizados: {m['total_variables']}\n"
            f"  - Variables de usuario:                     {m['variables_usuario']}\n"
            f"  - Temporales del compilador:                {m['temporales']}\n"
            f"• Aristas de interferencia identificadas:     {m['total_interferencias']}\n"
            f"• Densidad del grafo de interferencia:        {m['densidad_grafo']}%\n"
            f"• Número cromático mínimo exacto chi(G):      {m['numero_cromatico']}\n"
            f"• Registros físicos disponibles:              {m['registros_disponibles']} (EAX, EBX, ECX, EDX, ESI, EDI)\n"
            f"• Registros físicos asignados:                {m['registros_utilizados']}\n"
            f"• Variables con reutilización de registros:   {m['variables_con_reutilizacion']}\n"
            f"• Derrames en memoria (Spills):               {m['spills']}\n"
            f"• Estado de validez de coloración:            {'100% VÁLIDA (SIN CONFLICTOS)' if m['coloracion_valida'] else 'CONFLICTO DETECTADO'}\n"
            f"============================================================"
        )

