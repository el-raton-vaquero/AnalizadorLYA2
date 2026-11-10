
from typing import List, Dict, Set, Tuple, Optional, Any
import copy
import re

try:
    from compilador.ir.generator import Cuadruplo
except ImportError:
    from ..ir.generator import Cuadruplo

from .basic_block import (
    BasicBlock,
    identificar_bloques_basicos,
    es_salto,
    es_salto_condicional,
    es_salto_incondicional,
    es_retorno
)
from .cfg import ControlFlowGraph


class Transformacion:
    def __init__(self, numero: int, bloque: str, tecnica: str,
                 original: str, optimizado: str, justificacion: str):
        self.numero = numero
        self.bloque = bloque
        self.tecnica = tecnica
        self.original = original
        self.optimizado = optimizado
        self.justificacion = justificacion

    def to_dict(self) -> Dict[str, Any]:
        return {
            "numero": self.numero,
            "bloque": self.bloque,
            "tecnica": self.tecnica,
            "original": self.original,
            "optimizado": self.optimizado,
            "justificacion": self.justificacion
        }

    def __repr__(self) -> str:
        return f"Transformacion(#{self.numero}, {self.bloque}, {self.tecnica}: {self.original} -> {self.optimizado})"


def es_literal_constante(val: str) -> bool:
    if val is None or val == "":
        return False
    val = str(val).strip()
    if val in ("true", "false", "True", "False"):
        return True
    try:
        int(val)
        return True
    except ValueError:
        pass
    try:
        float(val)
        return True
    except ValueError:
        pass
    return False


def parsear_constante(val: str) -> Any:
    val = str(val).strip()
    if val in ("true", "True"):
        return 1
    if val in ("false", "False"):
        return 0
    try:
        return int(val)
    except ValueError:
        pass
    try:
        return float(val)
    except ValueError:
        return val


def formatear_constante(val: Any) -> str:
    if isinstance(val, bool):
        return "1" if val else "0"
    if isinstance(val, float):
        if val.is_integer():
            return str(int(val))
        return f"{val:.4g}"
    return str(val)


def evaluar_operacion_binaria(op: str, val1: Any, val2: Any) -> Optional[Any]:
    try:
        if op == "+":
            return val1 + val2
        elif op == "-":
            return val1 - val2
        elif op == "*":
            return val1 * val2
        elif op == "/":
            if val2 == 0:
                return None
            if isinstance(val1, int) and isinstance(val2, int):
                return val1 // val2
            return val1 / val2
        elif op == "%":
            if val2 == 0:
                return None
            return val1 % val2
        elif op in ("==", "EQ"):
            return 1 if val1 == val2 else 0
        elif op in ("!=", "NE"):
            return 1 if val1 != val2 else 0
        elif op in ("<", "LT"):
            return 1 if val1 < val2 else 0
        elif op in ("<=", "LE"):
            return 1 if val1 <= val2 else 0
        elif op in (">", "GT"):
            return 1 if val1 > val2 else 0
        elif op in (">=", "GE"):
            return 1 if val1 >= val2 else 0
        elif op in ("&&", "AND"):
            return 1 if (val1 and val2) else 0
        elif op in ("||", "OR"):
            return 1 if (val1 or val2) else 0
    except Exception:
        return None
    return None


def evaluar_operacion_unaria(op: str, val: Any) -> Optional[Any]:
    try:
        if op in ("neg", "-"):
            return -val
        elif op in ("!", "NOT"):
            return 0 if val else 1
    except Exception:
        return None
    return None


class IROptimizer:
    def __init__(self, instrucciones_originales: List[Cuadruplo]):
        self.instrucciones_originales: List[Cuadruplo] = [copy.copy(i) for i in instrucciones_originales]
        self.transformaciones: List[Transformacion] = []
        self._contador_transf = 0

        self.bloques_originales = identificar_bloques_basicos(self.instrucciones_originales)
        self.cfg_original = ControlFlowGraph(self.bloques_originales)

        self.instrucciones_optimizadas: List[Cuadruplo] = []
        self.bloques_optimizados: List[BasicBlock] = []
        self.cfg_optimizado: Optional[ControlFlowGraph] = None

    def _registrar(self, bloque: str, tecnica: str, original: str, optimizado: str, justificacion: str):
        self._contador_transf += 1
        t = Transformacion(self._contador_transf, bloque, tecnica, original, optimizado, justificacion)
        self.transformaciones.append(t)

    def _pase_cse_local(self, instrucciones: List[Cuadruplo], bloque_id: str) -> Tuple[List[Cuadruplo], bool]:
        hubo_cambio = False
        resultado = []
        expresiones: Dict[Tuple[str, str, str], str] = {}

        ops_conmutativos = {"+", "*", "==", "!="}

        for inst in instrucciones:
            op = (inst.op or "")
            a1 = str(inst.arg1) if inst.arg1 else ""
            a2 = str(inst.arg2) if inst.arg2 else ""
            res = str(inst.resultado) if inst.resultado else ""

            if op in ("+", "-", "*", "/", "%", "==", "!=", "<", ">", "<=", ">=", "&&", "||") and a1 and a2 and res:
                clave = (op, a1, a2)
                clave_conmutativa = (op, a2, a1) if op in ops_conmutativos else None

                prev_temp = expresiones.get(clave) or (expresiones.get(clave_conmutativa) if clave_conmutativa else None)

                if prev_temp and prev_temp != res:
                    orig_3ac = inst.to_3ac()
                    nueva_inst = Cuadruplo(inst.numero, "=", prev_temp, "", res)
                    resultado.append(nueva_inst)
                    self._registrar(
                        bloque=bloque_id,
                        tecnica="Eliminación de Subexpresiones Comunes (CSE)",
                        original=orig_3ac,
                        optimizado=nueva_inst.to_3ac(),
                        justificacion=f"Reutilización del cálculo de '{a1} {op} {a2}' ya almacenado en '{prev_temp}'"
                    )
                    hubo_cambio = True
                    continue
                else:
                    expresiones[clave] = res
                    if clave_conmutativa:
                        expresiones[clave_conmutativa] = res

            if res:
                claves_a_borrar = [k for k in expresiones if k[1] == res or k[2] == res]
                for k in claves_a_borrar:
                    del expresiones[k]

            resultado.append(inst)

        return resultado, hubo_cambio

    def _pase_propagacion_y_folding(self, instrucciones: List[Cuadruplo], bloque_id: str) -> Tuple[List[Cuadruplo], bool]:
        hubo_cambio = False
        resultado = []
        mapa_constantes: Dict[str, Any] = {}
        mapa_copias: Dict[str, str] = {}

        for inst in instrucciones:
            op = (inst.op or "")
            op_upper = op.upper()
            a1 = str(inst.arg1) if inst.arg1 else ""
            a2 = str(inst.arg2) if inst.arg2 else ""
            res = str(inst.resultado) if inst.resultado else ""
            orig_3ac = inst.to_3ac()

            nuevo_a1 = a1
            nuevo_a2 = a2

            if a1 in mapa_constantes:
                nuevo_a1 = formatear_constante(mapa_constantes[a1])
                if nuevo_a1 != a1:
                    hubo_cambio = True
            elif a1 in mapa_copias:
                nuevo_a1 = mapa_copias[a1]
                if nuevo_a1 != a1:
                    hubo_cambio = True

            if a2 in mapa_constantes:
                nuevo_a2 = formatear_constante(mapa_constantes[a2])
                if nuevo_a2 != a2:
                    hubo_cambio = True
            elif a2 in mapa_copias:
                nuevo_a2 = mapa_copias[a2]
                if nuevo_a2 != a2:
                    hubo_cambio = True

            if (nuevo_a1 != a1 or nuevo_a2 != a2) and op_upper not in ("LABEL", "GOTO"):
                inst = Cuadruplo(inst.numero, op, nuevo_a1, nuevo_a2, res)
                self._registrar(
                    bloque=bloque_id,
                    tecnica="Propagación de Constantes",
                    original=orig_3ac,
                    optimizado=inst.to_3ac(),
                    justificacion=f"Sustitución de operandos por valores constantes conocidos ({a1}->{nuevo_a1}, {a2}->{nuevo_a2})"
                )
                a1, a2 = nuevo_a1, nuevo_a2
                orig_3ac = inst.to_3ac()

            if op in ("+", "-", "*", "/", "%", "==", "!=", "<", ">", "<=", ">=", "&&", "||") and es_literal_constante(a1) and es_literal_constante(a2):
                v1 = parsear_constante(a1)
                v2 = parsear_constante(a2)
                eval_res = evaluar_operacion_binaria(op, v1, v2)
                if eval_res is not None:
                    res_str = formatear_constante(eval_res)
                    nueva_inst = Cuadruplo(inst.numero, "=", res_str, "", res)
                    mapa_constantes[res] = eval_res
                    if res in mapa_copias:
                        del mapa_copias[res]
                    self._registrar(
                        bloque=bloque_id,
                        tecnica="Constant Folding (Plegado de Constantes)",
                        original=orig_3ac,
                        optimizado=nueva_inst.to_3ac(),
                        justificacion=f"Cálculo en compilación de '{a1} {op} {a2}' = {res_str}"
                    )
                    resultado.append(nueva_inst)
                    hubo_cambio = True
                    continue

            elif op in ("neg", "!") and es_literal_constante(a1):
                v1 = parsear_constante(a1)
                eval_res = evaluar_operacion_unaria(op, v1)
                if eval_res is not None:
                    res_str = formatear_constante(eval_res)
                    nueva_inst = Cuadruplo(inst.numero, "=", res_str, "", res)
                    mapa_constantes[res] = eval_res
                    if res in mapa_copias:
                        del mapa_copias[res]
                    self._registrar(
                        bloque=bloque_id,
                        tecnica="Constant Folding (Plegado de Constantes)",
                        original=orig_3ac,
                        optimizado=nueva_inst.to_3ac(),
                        justificacion=f"Cálculo en compilación de '{op}{a1}' = {res_str}"
                    )
                    resultado.append(nueva_inst)
                    hubo_cambio = True
                    continue

            elif op == "=" and es_literal_constante(a1) and res:
                val = parsear_constante(a1)
                mapa_constantes[res] = val
                if res in mapa_copias:
                    del mapa_copias[res]

            elif op == "=" and a1 and not es_literal_constante(a1) and res:
                mapa_copias[res] = a1
                if res in mapa_constantes:
                    del mapa_constantes[res]

            elif res and res in mapa_constantes:
                del mapa_constantes[res]
                if res in mapa_copias:
                    del mapa_copias[res]

            resultado.append(inst)

        return resultado, hubo_cambio

    def _pase_simplificacion_saltos(self, instrucciones: List[Cuadruplo]) -> Tuple[List[Cuadruplo], bool]:
        hubo_cambio = False
        resultado = []

        const_global: Dict[str, Any] = {}
        for inst in instrucciones:
            if inst.op == "=" and es_literal_constante(inst.arg1) and inst.resultado:
                var = inst.resultado
                cuantas_asignaciones = sum(1 for i in instrucciones if i.resultado == var and i.op in ("=", "+", "-", "*", "/", "%"))
                if cuantas_asignaciones == 1:
                    const_global[var] = parsear_constante(inst.arg1)

        for idx, inst in enumerate(instrucciones):
            op = (inst.op or "").upper()
            a1 = inst.arg1
            orig_3ac = inst.to_3ac()

            if op in ("IF_FALSE", "IFFALSE"):
                val_cond = None
                if es_literal_constante(a1):
                    val_cond = parsear_constante(a1)
                elif a1 in const_global:
                    val_cond = const_global[a1]

                if val_cond is not None:
                    es_verdadera = bool(val_cond != 0 and str(val_cond).lower() != "false")
                    if es_verdadera:
                        self._registrar(
                            bloque="CFG",
                            tecnica="Evaluación de Condición Constante / Simplificación de Saltos",
                            original=orig_3ac,
                            optimizado="(salto eliminado)",
                            justificacion=f"La condición '{a1}' es verdadera ({val_cond}). El salto condicional 'ifFalse' nunca se ejecutará"
                        )
                        hubo_cambio = True
                        continue
                    else:
                        dest = inst.resultado or inst.arg1
                        nueva_inst = Cuadruplo(inst.numero, "GOTO", "", "", dest)
                        self._registrar(
                            bloque="CFG",
                            tecnica="Evaluación de Condición Constante / Simplificación de Saltos",
                            original=orig_3ac,
                            optimizado=nueva_inst.to_3ac(),
                            justificacion=f"La condición '{a1}' es falsa ({val_cond}). Se convierte a salto incondicional 'goto {dest}'"
                        )
                        resultado.append(nueva_inst)
                        hubo_cambio = True
                        continue

            elif op in ("IF", "IF_TRUE", "IFTRUE"):
                val_cond = None
                if es_literal_constante(a1):
                    val_cond = parsear_constante(a1)
                elif a1 in const_global:
                    val_cond = const_global[a1]

                if val_cond is not None:
                    es_verdadera = bool(val_cond != 0 and str(val_cond).lower() != "false")
                    dest = inst.resultado or inst.arg2
                    if es_verdadera:
                        nueva_inst = Cuadruplo(inst.numero, "GOTO", "", "", dest)
                        self._registrar(
                            bloque="CFG",
                            tecnica="Evaluación de Condición Constante / Simplificación de Saltos",
                            original=orig_3ac,
                            optimizado=nueva_inst.to_3ac(),
                            justificacion=f"La condición '{a1}' es siempre verdadera. Se simplifica a salto incondicional 'goto {dest}'"
                        )
                        resultado.append(nueva_inst)
                        hubo_cambio = True
                        continue
                    else:
                        self._registrar(
                            bloque="CFG",
                            tecnica="Evaluación de Condición Constante / Simplificación de Saltos",
                            original=orig_3ac,
                            optimizado="(salto eliminado)",
                            justificacion=f"La condición '{a1}' es siempre falsa. La bifurcación condicional nunca se tomará"
                        )
                        hubo_cambio = True
                        continue

            if op == "GOTO":
                dest_label = inst.resultado or inst.arg1
                if idx + 1 < len(instrucciones):
                    sig = instrucciones[idx + 1]
                    if (sig.op or "").upper() == "LABEL" and (sig.resultado == dest_label or sig.arg1 == dest_label):
                        self._registrar(
                            bloque="CFG",
                            tecnica="Simplificación de Saltos Innecesarios",
                            original=orig_3ac,
                            optimizado="(salto eliminado)",
                            justificacion=f"Salto redundante 'goto {dest_label}' hacia la instrucción inmediatamente contigua"
                        )
                        hubo_cambio = True
                        continue

            resultado.append(inst)

        return resultado, hubo_cambio

    def _pase_bloques_inalcanzables(self, instrucciones: List[Cuadruplo]) -> Tuple[List[Cuadruplo], bool]:
        bloques = identificar_bloques_basicos(instrucciones)
        if not bloques:
            return instrucciones, False

        cfg = ControlFlowGraph(bloques)
        alcanzables, inalcanzables = cfg.analizar_alcanzabilidad()

        if not inalcanzables:
            return instrucciones, False

        hubo_cambio = False
        resultado = []

        for b in bloques:
            if b.id in inalcanzables:
                hubo_cambio = True
                texto_b = "\n".join(i.to_3ac() for i in b.instrucciones)
                self._registrar(
                    bloque=b.nombre_completo,
                    tecnica="Eliminación de Bloques Inalcanzables",
                    original=texto_b,
                    optimizado="(bloque eliminado)",
                    justificacion=f"El bloque {b.nombre_completo} no posee rutas de ejecución activas en el Grafo de Flujo de Control"
                )
            else:
                resultado.extend(b.instrucciones)

        return resultado, hubo_cambio

    def _pase_codigo_muerto(self, instrucciones: List[Cuadruplo]) -> Tuple[List[Cuadruplo], bool]:
        hubo_cambio = False

        ops_protegidas = {
            "print", "cout", "read", "cin", "call", "[]=", "return",
            "label", "goto", "if_false", "iffalse", "if_true", "iftrue", "if"
        }

        variables_leidas: Set[str] = set()
        for inst in instrucciones:
            op_lower = (inst.op or "").lower()
            a1 = inst.arg1
            a2 = inst.arg2

            if a1 and not es_literal_constante(a1):
                variables_leidas.add(a1)
            if a2 and not es_literal_constante(a2):
                variables_leidas.add(a2)

            if op_lower in ("return", "print", "cout", "param") and a1:
                variables_leidas.add(a1)

        tiene_return = any((i.op or "").lower() == "return" for i in instrucciones)
        if not tiene_return:
            for inst in instrucciones:
                res = inst.resultado
                if res and not (res.startswith("t") and res[1:].isdigit()):
                    variables_leidas.add(res)

        resultado = []
        for inst in instrucciones:
            op_lower = (inst.op or "").lower()
            res = inst.resultado

            if op_lower in ops_protegidas:
                resultado.append(inst)
                continue

            if inst.op == "=" and inst.arg1 == res and res:
                self._registrar(
                    bloque="DCE",
                    tecnica="Eliminación de Código Muerto",
                    original=inst.to_3ac(),
                    optimizado="(eliminada)",
                    justificacion=f"Asignación idéntica redundante ({res} = {res})"
                )
                hubo_cambio = True
                continue

            if res and res not in variables_leidas:
                self._registrar(
                    bloque="DCE",
                    tecnica="Eliminación de Código Muerto",
                    original=inst.to_3ac(),
                    optimizado="(eliminada)",
                    justificacion=f"La variable o temporal '{res}' nunca es leída ni referenciada posteriormente (sin efectos secundarios)"
                )
                hubo_cambio = True
                continue

            resultado.append(inst)

        return resultado, hubo_cambio

    def _pase_limpieza_etiquetas(self, instrucciones: List[Cuadruplo]) -> Tuple[List[Cuadruplo], bool]:
        hubo_cambio = False
        etiquetas_referenciadas = set()

        for inst in instrucciones:
            op = (inst.op or "").upper()
            if es_salto(inst):
                dest = inst.resultado or inst.arg1
                if dest:
                    etiquetas_referenciadas.add(dest)

        resultado = []
        for inst in instrucciones:
            if (inst.op or "").upper() == "LABEL":
                lbl = inst.resultado or inst.arg1
                if lbl not in etiquetas_referenciadas:
                    self._registrar(
                        bloque="CFG",
                        tecnica="Limpieza de Etiquetas Huérfanas",
                        original=inst.to_3ac(),
                        optimizado="(etiqueta eliminada)",
                        justificacion=f"La etiqueta '{lbl}' no recibe ningún salto condicional ni incondicional"
                    )
                    hubo_cambio = True
                    continue
            resultado.append(inst)

        return resultado, hubo_cambio

    def optimizar(self, max_iteraciones: int = 15) -> List[Cuadruplo]:
        self.transformaciones.clear()
        self._contador_transf = 0

        insts_actuales = [copy.copy(i) for i in self.instrucciones_originales]

        for iter_num in range(max_iteraciones):
            cambios_en_ronda = False

            bloques_temp = identificar_bloques_basicos(insts_actuales)
            nuevas_insts = []
            for b in bloques_temp:
                insts_b, c1 = self._pase_cse_local(b.instrucciones, b.id)
                insts_b, c2 = self._pase_propagacion_y_folding(insts_b, b.id)
                if c1 or c2:
                    cambios_en_ronda = True
                nuevas_insts.extend(insts_b)

            insts_actuales = nuevas_insts

            insts_actuales, c3 = self._pase_simplificacion_saltos(insts_actuales)
            if c3:
                cambios_en_ronda = True

            insts_actuales, c4 = self._pase_bloques_inalcanzables(insts_actuales)
            if c4:
                cambios_en_ronda = True

            insts_actuales, c5 = self._pase_codigo_muerto(insts_actuales)
            if c5:
                cambios_en_ronda = True

            insts_actuales, c6 = self._pase_limpieza_etiquetas(insts_actuales)
            if c6:
                cambios_en_ronda = True

            if not cambios_en_ronda:
                break

        insts_finales = []
        for idx, inst in enumerate(insts_actuales, 1):
            insts_finales.append(Cuadruplo(idx, inst.op, inst.arg1, inst.arg2, inst.resultado))

        self.instrucciones_optimizadas = insts_finales
        self.bloques_optimizados = identificar_bloques_basicos(self.instrucciones_optimizadas)
        self.cfg_optimizado = ControlFlowGraph(self.bloques_optimizados)

        return self.instrucciones_optimizadas

    def obtener_tabla_transformaciones(self) -> List[Dict[str, Any]]:
        return [t.to_dict() for t in self.transformaciones]

    def obtener_tabla_comparativa_cfg(self) -> List[Dict[str, str]]:
        met_orig = self.cfg_original.calcular_metricas()
        met_opt = self.cfg_optimizado.calcular_metricas() if self.cfg_optimizado else met_orig

        tabla = []

        ram_orig = "Sí" if met_orig["decisiones"] > 0 else "No"
        ram_opt = "Sí" if met_opt["decisiones"] > 0 else "No"
        tabla.append({
            "elemento": "Bifurcaciones / Rama condicional",
            "cfg_original": f"{met_orig['decisiones']} (Activas)",
            "cfg_optimizado": f"{met_opt['decisiones']} (Activas)",
            "optimizacion": "Evaluación de condición constante y simplificación de flujo"
        })

        inalc_orig = met_orig["nodos_inalcanzables"]
        inalc_opt = met_opt["nodos_inalcanzables"]
        tabla.append({
            "elemento": "Bloques inalcanzables",
            "cfg_original": f"{inalc_orig} detectado(s)" if inalc_orig > 0 else "Ninguno",
            "cfg_optimizado": "0 (eliminados)",
            "optimizacion": "Eliminación de código inalcanzable tras return o ramas podadas"
        })

        tabla.append({
            "elemento": "Número de caminos",
            "cfg_original": str(met_orig["caminos_count"]),
            "cfg_optimizado": str(met_opt["caminos_count"]),
            "optimizacion": "Simplificación del flujo de ejecución"
        })

        tabla.append({
            "elemento": "Complejidad ciclomática",
            "cfg_original": str(met_orig["complejidad_ciclomatica"]),
            "cfg_optimizado": str(met_opt["complejidad_ciclomatica"]),
            "optimizacion": "Reducción de decisiones y aristas lógicas"
        })

        tabla.append({
            "elemento": "Total de instrucciones IR",
            "cfg_original": str(len(self.instrucciones_originales)),
            "cfg_optimizado": str(len(self.instrucciones_optimizadas)),
            "optimizacion": f"Reducción neta del {self.calcular_porcentaje_reduccion():.1f}% de instrucciones"
        })

        return tabla

    def calcular_porcentaje_reduccion(self) -> float:
        orig = len(self.instrucciones_originales)
        opt = len(self.instrucciones_optimizadas)
        if orig == 0:
            return 0.0
        return max(0.0, ((orig - opt) / orig) * 100.0)

    def generar_arbol_optimizaciones_texto(self) -> str:
        lineas = ["Código Original"]
        tecnicas_vistas = set()

        for t in self.transformaciones:
            resumen = f"{t.tecnica} en {t.bloque}: {t.original} -> {t.optimizado}"
            lineas.append(f"  ├── {resumen}")

        if not self.transformaciones:
            lineas.append("  └── (Código ya óptimo o sin oportunidades de reducción directa)")

        return "\n".join(lineas)
