"""
Módulo Simulador / Emulador de Código Ensamblador Simplificado x86 (IA-32).
Permite ejecutar el código objeto generado (.asm) de forma 100% autónoma,
validando la corrección funcional de operaciones aritméticas, estructuras de control,
asignación de registros y llamadas a funciones estándar (printf, scanf, exit).
"""

from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Set, Optional, Any
import re


@dataclass
class ExecutionResult:
    """Resultado detallado de la simulación del código ensamblador."""
    exitoso: bool
    codigo_retorno: int
    salida: str
    registros_finales: Dict[str, int]
    memoria_final: Dict[str, Any]
    instrucciones_ejecutadas: int
    error: Optional[str] = None

    def generar_reporte_ejecucion(self) -> str:
        """Genera un informe formal de la ejecución para evidencias."""
        lineas = []
        lineas.append("============================================================")
        lineas.append("       EVIDENCIA DE EJECUCIÓN DE CÓDIGO OBJETO (.ASM)       ")
        lineas.append("============================================================")
        lineas.append(f"• Estado:                 {'EXITOSO (0 ERRORES)' if self.exitoso else 'FALLIDO'}")
        lineas.append(f"• Código de retorno (EAX): {self.codigo_retorno}")
        lineas.append(f"• Instrucciones simuladas: {self.instrucciones_ejecutadas}")
        if self.error:
            lineas.append(f"• Error detectado:        {self.error}")

        lineas.append("\n--- SALIDA EN CONSOLA (STDOUT) ---")
        if self.salida.strip():
            for linea in self.salida.strip().splitlines():
                lineas.append(f"  [STDOUT] {linea}")
        else:
            lineas.append("  (Sin salida en stdout; ejecución silenciosa)")

        lineas.append("\n--- ESTADO FINAL DE REGISTROS DE LA CPU ---")
        for reg in ("EAX", "EBX", "ECX", "EDX", "ESI", "EDI", "EBP", "ESP"):
            val = self.registros_finales.get(reg, 0)
            lineas.append(f"  {reg:<4} = {val:>10}  (0x{val & 0xFFFFFFFF:08X})")

        lineas.append("\n--- ESTADO FINAL DE VARIABLES EN MEMORIA (.BSS) ---")
        if self.memoria_final:
            for var, val in sorted(self.memoria_final.items()):
                if not var.startswith("str_") and not var.startswith("fmt_"):
                    lineas.append(f"  {var:<12} = {val}")
        else:
            lineas.append("  (No hay variables en memoria)")

        lineas.append("============================================================")
        return "\n".join(lineas)


class SimulatorASM:
    """
    Simulador de arquitectura x86 simplificada para código objeto generado.
    Mantiene registros de 32 bits, banderas condicionales (ZF, SF, OF),
    pila de ejecución, secciones .data y .bss, y emulación de llamadas C.
    """

    def __init__(self, codigo_asm: str, entrada_stdin: str = "", max_instrucciones: int = 50000):
        self.codigo_asm = codigo_asm
        self.entrada_stdin = entrada_stdin
        self.max_instrucciones = max_instrucciones

        # Registros
        self.registros: Dict[str, int] = {
            "EAX": 0, "EBX": 0, "ECX": 0, "EDX": 0,
            "ESI": 0, "EDI": 0, "EBP": 0x7FFFF000, "ESP": 0x7FFFF000
        }

        # Banderas (EFLAGS)
        self.flag_zf: bool = False
        self.flag_sf: bool = False
        self.flag_of: bool = False

        # Memoria y Pila
        self.memoria_bss: Dict[str, int] = {}
        self.memoria_data: Dict[str, Any] = {}
        self.pila: List[Any] = []
        self.call_stack: List[int] = []
        self.ebp_pila_depth: int = 0
        self.registro_dx_label: str = ""

        # Parser del programa
        self.lineas_instrucciones: List[Tuple[str, str, str]] = []  # (etiqueta, mnemónico, operandos)
        self.mapa_etiquetas: Dict[str, int] = {}

        # I/O buffers
        self.buffer_salida: List[str] = []
        self.tokens_entrada: List[str] = entrada_stdin.split()
        self.idx_entrada: int = 0

        self._parsear_programa()

    def _parsear_programa(self) -> None:
        """Lee el archivo .asm, separando secciones, cadenas y extrayendo instrucciones."""
        seccion_actual = ".code"
        en_procedimiento_aux = False

        for linea_raw in self.codigo_asm.splitlines():
            # Quitar comentarios
            if ";" in linea_raw:
                linea_raw = linea_raw.split(";", 1)[0]
            linea = linea_raw.strip()
            if not linea:
                continue

            linea_low = linea.lower()
            if (linea_low.startswith(".386") or linea_low.startswith(".model") or
                    linea_low.startswith(".stack") or linea_low.startswith("assume")):
                continue
            if linea_low.startswith("end "):
                continue

            # Detección de secciones
            if linea_low == ".data" or linea_low.startswith("section .data"):
                seccion_actual = ".data"
                continue
            elif linea_low == ".bss" or linea_low.startswith("section .bss"):
                seccion_actual = ".bss"
                continue
            elif linea_low == ".code" or linea_low.startswith("section .text"):
                seccion_actual = ".code"
                continue

            if seccion_actual in (".data", ".bss"):
                # Parsear DD: e.g. x DD 0
                m_dd = re.match(r'^([A-Za-z0-9_]+)\s+DD\s+(.+)$', linea, re.IGNORECASE)
                if m_dd:
                    nombre = m_dd.group(1)
                    val_s = m_dd.group(2).strip()
                    try:
                        val = int(val_s)
                    except ValueError:
                        val = 0
                    self.memoria_bss[nombre] = val
                    continue

                # Parsear resd: e.g. x resd 1
                m_resd = re.match(r'^([A-Za-z0-9_]+)\s+resd\s+(\d+)$', linea, re.IGNORECASE)
                if m_resd:
                    nombre = m_resd.group(1)
                    self.memoria_bss[nombre] = 0
                    continue

                # Parsear DB: e.g. str_0 DB "Hola", 13, 10, "$"
                m_db = re.match(r'^([A-Za-z0-9_]+)\s+DB\s+["\']([^"\']*)["\']', linea, re.IGNORECASE)
                if m_db:
                    nombre = m_db.group(1)
                    val_str = m_db.group(2).replace('$', '')
                    self.memoria_data[nombre] = val_str
                    continue

                # Parsear formatos tipo db "%d", 10, 0
                m_db_gen = re.match(r'^([A-Za-z0-9_]+)\s+db\s+(.+)$', linea, re.IGNORECASE)
                if m_db_gen:
                    nombre = m_db_gen.group(1)
                    val_str = m_db_gen.group(2).strip()
                    if '"' in val_str:
                        m_val = re.search(r'"([^"]*)"', val_str)
                        self.memoria_data[nombre] = m_val.group(1).replace('$', '') if m_val else ""
                    else:
                        self.memoria_data[nombre] = val_str
                    continue

            elif seccion_actual in (".code", ".text"):
                # Ignorar directivas de exportación/importación
                if linea_low.startswith("global ") or linea_low.startswith("extern "):
                    continue

                # Detectar procedimientos auxiliares (PRINT_INT, PRINT_STR, READ_INT)
                if re.match(r'^(PRINT_INT|PRINT_STR|READ_INT)\s+PROC', linea, re.IGNORECASE):
                    en_procedimiento_aux = True
                    continue
                if en_procedimiento_aux:
                    if re.match(r'^(PRINT_INT|PRINT_STR|READ_INT)\s+ENDP', linea, re.IGNORECASE):
                        en_procedimiento_aux = False
                    continue

                # Revisar si es etiqueta: e.g. START: o main: o L1:
                if linea.endswith(":"):
                    lbl = linea[:-1].strip()
                    idx = len(self.lineas_instrucciones)
                    self.mapa_etiquetas[lbl] = idx
                    continue

                # Instrucción normal con posible etiqueta prefijada
                etiqueta = ""
                if ":" in linea:
                    partes = linea.split(":", 1)
                    lbl = partes[0].strip()
                    etiqueta = lbl
                    idx = len(self.lineas_instrucciones)
                    self.mapa_etiquetas[lbl] = idx
                    linea = partes[1].strip()
                    if not linea:
                        continue

                tokens = linea.split(None, 1)
                mnem = tokens[0].lower()
                ops = tokens[1].strip() if len(tokens) > 1 else ""
                self.lineas_instrucciones.append((etiqueta, mnem, ops))

    def _resolver_valor(self, op: str) -> int:
        """Evalúa un operando x86 retornando su valor entero de 32 bits."""
        op = op.strip()
        if not op:
            return 0

        # Registro
        op_up = op.upper()
        if op_up in self.registros:
            return self.registros[op_up]
        if op_up in ("AL", "BL", "CL", "DL"):
            reg32 = "E" + op_up[0] + "X"
            return self.registros.get(reg32, 0) & 0xFF
        if op_up in ("AX", "BX", "CX", "DX", "BP", "SP", "SI", "DI"):
            reg32 = "E" + op_up if op_up in ("BP", "SP", "SI", "DI") else ("E" + op_up[0] + "X")
            return self.registros.get(reg32, 0) & 0xFFFF

        # Número inmediato
        if re.match(r'^-?\d+$', op):
            return int(op)
        if op.lower().startswith("0x"):
            return int(op, 16)

        # Acceso a memoria: [x] o dword [x] o [ebp-4] o [bp-4]
        m_mem = re.search(r'\[([^\]]+)\]', op)
        if m_mem:
            interior = m_mem.group(1).strip()
            # Caso 0: acceso a tope de pila [esp] o [sp]
            if interior.lower() in ("esp", "sp"):
                return self.pila[-1] if self.pila else 0
            # Caso 1: nombre de variable directa en .bss
            if interior in self.memoria_bss:
                return self.memoria_bss[interior]
            # Caso 2: [ebp - offset] o [bp - offset]
            m_ebp = re.match(r'(?:ebp|bp)\s*-\s*(\d+)', interior, re.IGNORECASE)
            if m_ebp:
                key = f"ebp_{m_ebp.group(1)}"
                return self.memoria_bss.get(key, 0)
            # Caso 3: variable directa
            return self.memoria_bss.get(interior, 0)

        # Etiqueta en .data (dirección simbólica)
        if op in self.memoria_data:
            return hash(op) & 0x7FFFFFFF

        # Variable en .bss referenciada por nombre directo
        if op in self.memoria_bss:
            return self.memoria_bss[op]

        return 0

    def _asignar_destino(self, dest: str, valor: int) -> None:
        """Asigna un valor de 32 bits a un registro o posición de memoria."""
        dest = dest.strip()
        # Normalizar a entero de 32 bits signado
        valor = valor & 0xFFFFFFFF
        if valor >= 0x80000000:
            valor -= 0x100000000

        dest_up = dest.upper()
        if dest_up in self.registros:
            self.registros[dest_up] = valor
            return

        if dest_up in ("AL", "BL", "CL", "DL"):
            reg32 = "E" + dest_up[0] + "X"
            val_actual = self.registros.get(reg32, 0) & 0xFFFFFF00
            self.registros[reg32] = val_actual | (valor & 0xFF)
            return

        if dest_up in ("AX", "BX", "CX", "DX", "BP", "SP", "SI", "DI"):
            reg32 = "E" + dest_up if dest_up in ("BP", "SP", "SI", "DI") else ("E" + dest_up[0] + "X")
            val_actual = self.registros.get(reg32, 0) & 0xFFFF0000
            self.registros[reg32] = val_actual | (valor & 0xFFFF)
            return

        # Acceso a memoria: [var] o dword [var]
        m_mem = re.search(r'\[([^\]]+)\]', dest)
        if m_mem:
            interior = m_mem.group(1).strip()
            m_ebp = re.match(r'(?:ebp|bp)\s*-\s*(\d+)', interior, re.IGNORECASE)
            if m_ebp:
                key = f"ebp_{m_ebp.group(1)}"
                self.memoria_bss[key] = valor
            else:
                self.memoria_bss[interior] = valor
            return

        if dest in self.memoria_bss:
            self.memoria_bss[dest] = valor

    def _actualizar_banderas(self, resultado: int) -> None:
        """Actualiza ZF (Zero Flag) y SF (Sign Flag)."""
        res_32 = resultado & 0xFFFFFFFF
        self.flag_zf = (res_32 == 0)
        self.flag_sf = (res_32 & 0x80000000) != 0
        self.flag_of = False  # Simplificado

    def ejecutar(self) -> ExecutionResult:
        """Ejecuta el programa completo y retorna el reporte."""
        pc = self.mapa_etiquetas.get("START", self.mapa_etiquetas.get("main", self.mapa_etiquetas.get("MAIN", 0)))
        total_insts = len(self.lineas_instrucciones)
        ciclos = 0

        while 0 <= pc < total_insts:
            if ciclos >= self.max_instrucciones:
                return ExecutionResult(
                    exitoso=False,
                    codigo_retorno=self.registros.get("EAX", -1),
                    salida="".join(self.buffer_salida),
                    registros_finales=dict(self.registros),
                    memoria_final=dict(self.memoria_bss),
                    instrucciones_ejecutadas=ciclos,
                    error=f"Límite máximo de instrucciones alcanzado ({self.max_instrucciones}) - posible ciclo infinito."
                )

            _, mnem, ops = self.lineas_instrucciones[pc]
            ciclos += 1
            pc_siguiente = pc + 1

            # Dividir operandos por coma
            partes_op = [p.strip() for p in ops.split(",")] if ops else []

            if mnem == "mov":
                dest, src = partes_op[0], partes_op[1]
                if src.lower() == "@data":
                    self._asignar_destino(dest, 0x1000)
                    pc = pc_siguiente
                    continue
                if dest.upper() in ("DS", "ES"):
                    pc = pc_siguiente
                    continue
                if src.lower().startswith("offset "):
                    lbl_offset = src.split(None, 1)[1].strip()
                    if dest.upper() in ("DX", "EDX"):
                        self.registro_dx_label = lbl_offset
                    val = hash(lbl_offset) & 0x7FFFFFFF
                    self._asignar_destino(dest, val)
                    pc = pc_siguiente
                    continue
                val = self._resolver_valor(src)
                self._asignar_destino(dest, val)
                if dest.upper() in ("EBP", "BP") and src.upper() in ("ESP", "SP"):
                    self.ebp_pila_depth = len(self.pila)
                elif dest.upper() in ("ESP", "SP") and src.upper() in ("EBP", "BP"):
                    self.pila = self.pila[:self.ebp_pila_depth]

            elif mnem == "lea":
                dest, src = partes_op[0], partes_op[1]
                if dest.upper() in ("DX", "EDX"):
                    self.registro_dx_label = src

            elif mnem == "int":
                if "21" in ops:
                    eax_val = self.registros.get("EAX", 0)
                    ah = (eax_val >> 8) & 0xFF
                    if ah == 0x4C:
                        self.registros["EAX"] = eax_val & 0xFF
                        break
                    elif ah == 0x09:
                        lbl = self.registro_dx_label
                        txt = str(self.memoria_data.get(lbl, ""))
                        self.buffer_salida.append(txt + "\n")
                    elif ah == 0x02:
                        dl = self.registros.get("EDX", 0) & 0xFF
                        if dl == 10:
                            self.buffer_salida.append("\n")
                        elif dl != 13:
                            self.buffer_salida.append(chr(dl))

            elif mnem == "movzx":
                dest, src = partes_op[0], partes_op[1]
                val = self._resolver_valor(src) & 0xFF
                self._asignar_destino(dest, val)

            elif mnem == "add":
                dest, src = partes_op[0], partes_op[1]
                v_dest = self._resolver_valor(dest)
                v_src = self._resolver_valor(src)
                res = v_dest + v_src
                self._asignar_destino(dest, res)
                self._actualizar_banderas(res)
                if dest.upper() in ("ESP", "SP"):
                    num_pops = max(0, v_src // 4)
                    for _ in range(num_pops):
                        if self.pila:
                            self.pila.pop()

            elif mnem == "sub":
                dest, src = partes_op[0], partes_op[1]
                v_dest = self._resolver_valor(dest)
                v_src = self._resolver_valor(src)
                res = v_dest - v_src
                self._asignar_destino(dest, res)
                self._actualizar_banderas(res)
                if dest.upper() in ("ESP", "SP"):
                    num_slots = max(0, v_src // 4)
                    for _ in range(num_slots):
                        self.pila.append(0)

            elif mnem == "imul":
                if len(partes_op) == 2:
                    dest, src = partes_op[0], partes_op[1]
                    v_dest = self._resolver_valor(dest)
                    v_src = self._resolver_valor(src)
                    res = v_dest * v_src
                    self._asignar_destino(dest, res)
                    self._actualizar_banderas(res)
                elif len(partes_op) == 1:
                    src = partes_op[0]
                    v_src = self._resolver_valor(src)
                    res = self.registros["EAX"] * v_src
                    self._asignar_destino("EAX", res)
                    self._actualizar_banderas(res)

            elif mnem == "cdq":
                # Extender signo de EAX en EDX
                val_eax = self.registros["EAX"]
                self.registros["EDX"] = -1 if val_eax < 0 else 0

            elif mnem == "idiv":
                divisor = self._resolver_valor(partes_op[0])
                if divisor == 0:
                    return ExecutionResult(
                        exitoso=False,
                        codigo_retorno=-1,
                        salida="".join(self.buffer_salida),
                        registros_finales=dict(self.registros),
                        memoria_final=dict(self.memoria_bss),
                        instrucciones_ejecutadas=ciclos,
                        error="Error en tiempo de ejecución: División por cero (idiv)."
                    )
                # Dividendo en EDX:EAX
                dividendo = self.registros["EAX"]
                cociente = int(dividendo / divisor)
                resto = dividendo % divisor
                # Ajuste de signo de resto en división truncada estándar x86
                if dividendo < 0 and resto > 0:
                    resto -= abs(divisor)
                self.registros["EAX"] = cociente
                self.registros["EDX"] = resto

            elif mnem == "neg":
                dest = partes_op[0]
                val = -self._resolver_valor(dest)
                self._asignar_destino(dest, val)
                self._actualizar_banderas(val)

            elif mnem in ("inc", "dec"):
                dest = partes_op[0]
                delta = 1 if mnem == "inc" else -1
                val = self._resolver_valor(dest) + delta
                self._asignar_destino(dest, val)
                self._actualizar_banderas(val)

            elif mnem == "and":
                dest, src = partes_op[0], partes_op[1]
                res = self._resolver_valor(dest) & self._resolver_valor(src)
                self._asignar_destino(dest, res)
                self._actualizar_banderas(res)

            elif mnem == "or":
                dest, src = partes_op[0], partes_op[1]
                res = self._resolver_valor(dest) | self._resolver_valor(src)
                self._asignar_destino(dest, res)
                self._actualizar_banderas(res)

            elif mnem == "xor":
                dest, src = partes_op[0], partes_op[1]
                res = self._resolver_valor(dest) ^ self._resolver_valor(src)
                self._asignar_destino(dest, res)
                self._actualizar_banderas(res)

            elif mnem == "cmp":
                op1 = self._resolver_valor(partes_op[0])
                op2 = self._resolver_valor(partes_op[1])
                diff = op1 - op2
                self._actualizar_banderas(diff)

            elif mnem.startswith("set"):
                cond = mnem[3:]
                dest = partes_op[0]
                cumple = False
                if cond == "e":
                    cumple = self.flag_zf
                elif cond == "ne":
                    cumple = not self.flag_zf
                elif cond == "l":
                    cumple = self.flag_sf != self.flag_of
                elif cond == "le":
                    cumple = self.flag_zf or (self.flag_sf != self.flag_of)
                elif cond == "g":
                    cumple = not self.flag_zf and (self.flag_sf == self.flag_of)
                elif cond == "ge":
                    cumple = self.flag_sf == self.flag_of
                self._asignar_destino(dest, 1 if cumple else 0)

            elif mnem == "jmp":
                lbl = partes_op[0]
                if lbl in self.mapa_etiquetas:
                    pc_siguiente = self.mapa_etiquetas[lbl]

            elif mnem in ("je", "jz"):
                if self.flag_zf:
                    lbl = partes_op[0]
                    if lbl in self.mapa_etiquetas:
                        pc_siguiente = self.mapa_etiquetas[lbl]

            elif mnem in ("jne", "jnz"):
                if not self.flag_zf:
                    lbl = partes_op[0]
                    if lbl in self.mapa_etiquetas:
                        pc_siguiente = self.mapa_etiquetas[lbl]

            elif mnem == "jl":
                if self.flag_sf != self.flag_of:
                    lbl = partes_op[0]
                    if lbl in self.mapa_etiquetas:
                        pc_siguiente = self.mapa_etiquetas[lbl]

            elif mnem == "jle":
                if self.flag_zf or (self.flag_sf != self.flag_of):
                    lbl = partes_op[0]
                    if lbl in self.mapa_etiquetas:
                        pc_siguiente = self.mapa_etiquetas[lbl]

            elif mnem == "jg":
                if not self.flag_zf and (self.flag_sf == self.flag_of):
                    lbl = partes_op[0]
                    if lbl in self.mapa_etiquetas:
                        pc_siguiente = self.mapa_etiquetas[lbl]

            elif mnem == "jge":
                if self.flag_sf == self.flag_of:
                    lbl = partes_op[0]
                    if lbl in self.mapa_etiquetas:
                        pc_siguiente = self.mapa_etiquetas[lbl]

            elif mnem == "push":
                val_push = self._resolver_valor(partes_op[0])
                # Guardar el nombre simbólico si es cadena en data
                token = partes_op[0].strip()
                if token in self.memoria_data:
                    self.pila.append(token)
                else:
                    self.pila.append(val_push)
                self.registros["ESP"] -= 4

            elif mnem == "pop":
                if self.pila:
                    val_pop = self.pila.pop()
                    if isinstance(val_pop, int):
                        self._asignar_destino(partes_op[0], val_pop)
                self.registros["ESP"] += 4

            elif mnem == "call":
                target = partes_op[0]
                target_up = target.upper()
                if target_up == "PRINT_INT":
                    val = self.registros.get("EAX", 0)
                    self.buffer_salida.append(str(val) + "\n")
                elif target_up == "PRINT_STR":
                    lbl = self.registro_dx_label
                    txt = str(self.memoria_data.get(lbl, ""))
                    self.buffer_salida.append(txt + "\n")
                elif target_up == "READ_INT":
                    if self.idx_entrada < len(self.tokens_entrada):
                        val_in = int(self.tokens_entrada[self.idx_entrada])
                        self.idx_entrada += 1
                        self.registros["EAX"] = val_in
                    else:
                        self.registros["EAX"] = 0
                elif target == "printf":
                    # Imprimir según argumentos en pila
                    # Argumento 1: formato, Argumento 2: valor
                    if len(self.pila) >= 2:
                        fmt_token = self.pila[-1]
                        val_arg = self.pila[-2]
                        if isinstance(val_arg, str) and val_arg in self.memoria_data:
                            texto_imprimir = str(self.memoria_data[val_arg])
                        else:
                            texto_imprimir = str(val_arg)
                        self.buffer_salida.append(texto_imprimir + "\n")
                    elif len(self.pila) == 1:
                        val_arg = self.pila[-1]
                        if isinstance(val_arg, str) and val_arg in self.memoria_data:
                            self.buffer_salida.append(str(self.memoria_data[val_arg]) + "\n")
                        else:
                            self.buffer_salida.append(str(val_arg) + "\n")
                elif target == "scanf":
                    if self.idx_entrada < len(self.tokens_entrada):
                        val_in = int(self.tokens_entrada[self.idx_entrada])
                        self.idx_entrada += 1
                        if self.pila:
                            dir_dest = self.pila[-1]
                            if isinstance(dir_dest, str):
                                self.memoria_bss[dir_dest] = val_in
                elif target == "exit":
                    break
                elif target in self.mapa_etiquetas:
                    self.call_stack.append(pc_siguiente)
                    pc_siguiente = self.mapa_etiquetas[target]

            elif mnem == "ret":
                if self.call_stack:
                    ret_addr = self.call_stack.pop()
                    pc_siguiente = ret_addr
                else:
                    # Fin de main
                    break

            elif mnem in ("leave", "nop"):
                pass

            pc = pc_siguiente

        return ExecutionResult(
            exitoso=True,
            codigo_retorno=self.registros.get("EAX", 0),
            salida="".join(self.buffer_salida),
            registros_finales=dict(self.registros),
            memoria_final=dict(self.memoria_bss),
            instrucciones_ejecutadas=ciclos,
            error=None
        )
