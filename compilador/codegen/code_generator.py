"""
Módulo Generador de Código Objeto Ensamblador (.asm).
Traduce las cuádruplas optimizadas a instrucciones estándar de ensamblador x86 (IA-32)
utilizando la asignación óptima de registros por coloración de grafos.
100% compatible con Turbo Assembler (TASM) y emuladores x86.
Produce un archivo ensamblador completo, ordenado, comentado y ejecutable.
"""

from typing import List, Dict, Set, Tuple, Optional
import re
import datetime

from compilador.ir.generator import Cuadruplo
from compilador.codegen.register_allocator import RegisterAllocator, RegistroInfo


class CodeGenerator:
    """
    Generador de Código Objeto Ensamblador x86 compatible con Turbo Assembler (TASM).
    Traduce operaciones aritméticas, asignaciones, comparaciones relacionales,
    saltos de control de flujo e instrucciones de E/S aprovechando al máximo
    los registros asignados mediante coloración de grafos.
    """

    def __init__(self, cuadruplos: List[Cuadruplo], allocator: RegisterAllocator):
        self.cuadruplos = list(cuadruplos)
        self.allocator = allocator
        self.mapa_regs = allocator.mapa_variable_registro

        # Cadenas y constantes para .DATA
        self.cadenas_data: Dict[str, str] = {}
        self.contador_cadenas = 0

        # Variables de usuario para .DATA (memoria principal)
        self.variables_bss: Set[str] = set()
        self._identificar_variables_bss()

    def _identificar_variables_bss(self) -> None:
        """Identifica todas las variables de usuario que deben residir en memoria principal."""
        etiquetas = set()
        for c in self.cuadruplos:
            if c.op.upper() == "LABEL" and c.resultado:
                etiquetas.add(c.resultado.strip())

        for c in self.cuadruplos:
            for campo in (c.arg1, c.arg2, c.resultado):
                if campo and not campo.startswith('"') and not campo.startswith("'"):
                    if not re.match(r'^-?\d+(\.\d+)?$', campo) and campo not in etiquetas:
                        if campo.isidentifier() and campo.lower() not in ('true', 'false', 'null', 'void'):
                            # Solo variables que no sean temporales t1, t2
                            if not (campo.startswith('t') and campo[1:].isdigit()):
                                self.variables_bss.add(campo)

    def _registrar_cadena(self, texto: str) -> str:
        """Registra un literal de cadena en .DATA y retorna su etiqueta simbólica."""
        texto_limpio = texto.strip('"').strip("'")
        for lbl, val in self.cadenas_data.items():
            if val == texto_limpio:
                return lbl
        lbl = f"str_{self.contador_cadenas}"
        self.contador_cadenas += 1
        self.cadenas_data[lbl] = texto_limpio
        return lbl

    def _loc_operando(self, token: str) -> str:
        """Retorna la representación ensamblador de un operando (registro, número o memoria)."""
        if not token:
            return ""
        token = token.strip()

        # Número directo
        if re.match(r'^-?\d+$', token):
            return token

        # Cadena
        if (token.startswith('"') and token.endswith('"')) or (token.startswith("'") and token.endswith("'")):
            return self._registrar_cadena(token)

        # Mapeado a registro o spill
        if token in self.mapa_regs:
            reg = self.mapa_regs[token]
            if reg.startswith("["):
                return f"dword ptr {reg}"
            return reg

        # Variable en memoria .DATA
        if token in self.variables_bss:
            return f"dword ptr [{token}]"

        return token

    def _reg_o_scratch(self, var: str, scratch_default: str = "eax") -> str:
        """Retorna el registro asignado a una variable o un registro de trabajo por defecto."""
        if var in self.mapa_regs:
            r = self.mapa_regs[var]
            if not r.startswith("["):
                return r
        return scratch_default

    def generar_codigo(self) -> str:
        """Genera el texto completo del archivo objeto .asm estructurado en secciones compatibles con TASM."""
        lineas_text: List[str] = []

        # Prólogo estándar de función main
        lineas_text.append("    push bp")
        lineas_text.append("    mov bp, sp")

        # Reserva de espacio en pila para derrames si existen
        n_spills = len(self.allocator.spills)
        espacio_pila = max(16, (n_spills + 2) * 4)
        lineas_text.append(f"    sub sp, {espacio_pila:<16} ; Espacio reservado para marco de pila y derrames")
        lineas_text.append("")

        # Traducción secuencial de cuádruplos
        for c in self.cuadruplos:
            comentario_ir = f"; {c.to_ir_tuple()}"
            op_up = c.op.upper()
            op = c.op

            # 1. ETIQUETAS
            if op_up == "LABEL":
                lbl = c.resultado.strip()
                lineas_text.append(f"{lbl}:")
                continue

            # 2. SALTOS INCONDICIONALES
            elif op_up == "GOTO":
                target = c.resultado.strip()
                lineas_text.append(f"    jmp {target:<20} {comentario_ir}")
                continue

            # 3. SALTOS CONDICIONALES
            elif op_up in ("IF_FALSE", "IFFALSE"):
                cond_loc = self._loc_operando(c.arg1)
                target = c.resultado.strip()
                lineas_text.append(f"    cmp {cond_loc}, 0")
                lineas_text.append(f"    je {target:<21} {comentario_ir}")
                continue

            elif op_up in ("IF_TRUE", "IFTRUE"):
                cond_loc = self._loc_operando(c.arg1)
                target = c.resultado.strip()
                lineas_text.append(f"    cmp {cond_loc}, 0")
                lineas_text.append(f"    jne {target:<20} {comentario_ir}")
                continue

            # 4. ASIGNACIÓN DIRECTA
            elif op == "=":
                res = c.resultado.strip()
                arg = c.arg1.strip()
                dest_loc = self._loc_operando(res)
                src_loc = self._loc_operando(arg)

                # Si ambos son la misma ubicación (reutilización)
                if dest_loc == src_loc:
                    lineas_text.append(f"    ; mov {dest_loc}, {src_loc} (mismo registro asignado por coloración) {comentario_ir}")
                elif "dword ptr [" in dest_loc and "dword ptr [" in src_loc:
                    # Memoria a memoria requiere registro intermedio
                    scratch = "eax"
                    lineas_text.append(f"    mov {scratch}, {src_loc}")
                    lineas_text.append(f"    mov {dest_loc}, {scratch}     {comentario_ir}")
                else:
                    lineas_text.append(f"    mov {dest_loc}, {src_loc}     {comentario_ir}")

                if res in self.variables_bss and not dest_loc.startswith("dword ptr ["):
                    lineas_text.append(f"    mov dword ptr [{res}], {dest_loc}")
                continue

            # 5. OPERACIONES ARITMÉTICAS
            elif op in ("+", "-", "*", "/", "%"):
                res = c.resultado.strip()
                arg1 = c.arg1.strip()
                arg2 = c.arg2.strip()
                dest_reg = self._reg_o_scratch(res, "eax")
                arg1_loc = self._loc_operando(arg1)
                arg2_loc = self._loc_operando(arg2)

                if op == "+":
                    if dest_reg != arg1_loc:
                        lineas_text.append(f"    mov {dest_reg}, {arg1_loc}")
                    lineas_text.append(f"    add {dest_reg}, {arg2_loc}    {comentario_ir}")

                elif op == "-":
                    if dest_reg != arg1_loc:
                        lineas_text.append(f"    mov {dest_reg}, {arg1_loc}")
                    lineas_text.append(f"    sub {dest_reg}, {arg2_loc}    {comentario_ir}")

                elif op == "*":
                    if dest_reg != arg1_loc:
                        lineas_text.append(f"    mov {dest_reg}, {arg1_loc}")
                    lineas_text.append(f"    imul {dest_reg}, {arg2_loc}   {comentario_ir}")

                elif op in ("/", "%"):
                    if arg1_loc != "eax":
                        lineas_text.append(f"    mov eax, {arg1_loc}")
                    lineas_text.append("    cdq")
                    if re.match(r'^-?\d+$', arg2_loc):
                        lineas_text.append(f"    push dword ptr {arg2_loc}")
                        lineas_text.append("    idiv dword ptr [esp]")
                        lineas_text.append("    add sp, 4")
                    else:
                        lineas_text.append(f"    idiv {arg2_loc}")

                    res_orig = "eax" if op == "/" else "edx"
                    if dest_reg != res_orig:
                        lineas_text.append(f"    mov {dest_reg}, {res_orig}    {comentario_ir}")

                    # Restaurar variables mapeadas a eax o edx si fueron pisadas por idiv
                    var_eax = next((v for v, r in self.mapa_regs.items() if r == "eax"), None)
                    var_edx = next((v for v, r in self.mapa_regs.items() if r == "edx"), None)
                    if var_eax and var_eax != res and var_eax in self.variables_bss and dest_reg != "eax":
                        lineas_text.append(f"    mov eax, dword ptr [{var_eax}]")
                    if var_edx and var_edx != res and var_edx in self.variables_bss and dest_reg != "edx":
                        lineas_text.append(f"    mov edx, dword ptr [{var_edx}]")

                # Guardar resultado en destino final si es memoria
                dest_loc = self._loc_operando(res)
                if dest_loc.startswith("dword ptr ["):
                    lineas_text.append(f"    mov {dest_loc}, {dest_reg}")
                elif res in self.variables_bss:
                    lineas_text.append(f"    mov dword ptr [{res}], {dest_reg}")

                continue

            # 6. NEGACIÓN UNARIA
            elif op == "neg":
                res = c.resultado.strip()
                arg1 = c.arg1.strip()
                dest_reg = self._reg_o_scratch(res, "eax")
                arg1_loc = self._loc_operando(arg1)
                if dest_reg != arg1_loc:
                    lineas_text.append(f"    mov {dest_reg}, {arg1_loc}")
                lineas_text.append(f"    neg {dest_reg}             {comentario_ir}")
                dest_loc = self._loc_operando(res)
                if dest_loc.startswith("dword ptr ["):
                    lineas_text.append(f"    mov {dest_loc}, {dest_reg}")
                elif res in self.variables_bss:
                    lineas_text.append(f"    mov dword ptr [{res}], {dest_reg}")
                continue

            # 7. COMPARACIONES RELACIONALES (==, !=, <, <=, >, >=)
            elif op in ("==", "!=", "<", "<=", ">", ">="):
                res = c.resultado.strip()
                arg1 = c.arg1.strip()
                arg2 = c.arg2.strip()
                arg1_loc = self._loc_operando(arg1)
                arg2_loc = self._loc_operando(arg2)
                dest_reg = self._reg_o_scratch(res, "ecx")

                mapa_set = {
                    "==": "sete", "!=": "setne",
                    "<": "setl", "<=": "setle",
                    ">": "setg", ">=": "setge"
                }
                set_instr = mapa_set[op]

                # Comparación x86
                if "dword ptr [" in arg1_loc and "dword ptr [" in arg2_loc:
                    lineas_text.append(f"    mov edx, {arg1_loc}")
                    lineas_text.append(f"    cmp edx, {arg2_loc}        {comentario_ir}")
                else:
                    lineas_text.append(f"    cmp {arg1_loc}, {arg2_loc}        {comentario_ir}")

                # Determinar registro de 8 bits para setcc evitando pisar operandos
                mapa_reg8 = {"eax": "al", "ebx": "bl", "ecx": "cl", "edx": "dl"}
                if dest_reg in mapa_reg8:
                    reg8 = mapa_reg8[dest_reg]
                    lineas_text.append(f"    {set_instr} {reg8}")
                    lineas_text.append(f"    movzx {dest_reg}, {reg8}")
                else:
                    reg_scratch = "ecx" if (arg1_loc != "ecx" and arg2_loc != "ecx") else "edx"
                    reg8 = mapa_reg8[reg_scratch]
                    lineas_text.append(f"    {set_instr} {reg8}")
                    lineas_text.append(f"    movzx {dest_reg}, {reg8}")

                dest_loc = self._loc_operando(res)
                if dest_loc.startswith("dword ptr ["):
                    lineas_text.append(f"    mov {dest_loc}, {dest_reg}")
                elif res in self.variables_bss:
                    lineas_text.append(f"    mov dword ptr [{res}], {dest_reg}")
                continue

            # 8. OPERACIONES LÓGICAS (&&, ||, !)
            elif op in ("&&", "||", "!"):
                res = c.resultado.strip()
                dest_reg = self._reg_o_scratch(res, "eax")

                if op == "&&":
                    arg1_loc = self._loc_operando(c.arg1)
                    arg2_loc = self._loc_operando(c.arg2)
                    if dest_reg != arg1_loc:
                        lineas_text.append(f"    mov {dest_reg}, {arg1_loc}")
                    lineas_text.append(f"    and {dest_reg}, {arg2_loc}    {comentario_ir}")

                elif op == "||":
                    arg1_loc = self._loc_operando(c.arg1)
                    arg2_loc = self._loc_operando(c.arg2)
                    if dest_reg != arg1_loc:
                        lineas_text.append(f"    mov {dest_reg}, {arg1_loc}")
                    lineas_text.append(f"    or {dest_reg}, {arg2_loc}     {comentario_ir}")

                elif op == "!":
                    arg1_loc = self._loc_operando(c.arg1)
                    lineas_text.append(f"    cmp {arg1_loc}, 0")
                    lineas_text.append(f"    sete al")
                    lineas_text.append(f"    movzx {dest_reg}, al        {comentario_ir}")

                dest_loc = self._loc_operando(res)
                if dest_loc.startswith("dword ptr ["):
                    lineas_text.append(f"    mov {dest_loc}, {dest_reg}")
                elif res in self.variables_bss:
                    lineas_text.append(f"    mov dword ptr [{res}], {dest_reg}")
                continue

            # 9. IMPRESIÓN (print / cout)
            elif op == "print":
                arg = c.arg1.strip()
                if (arg.startswith('"') and arg.endswith('"')) or (arg.startswith("'") and arg.endswith("'")):
                    cad_lbl = self._registrar_cadena(arg)
                    lineas_text.append(f"    push dx")
                    lineas_text.append(f"    mov dx, offset {cad_lbl}")
                    lineas_text.append(f"    call PRINT_STR             {comentario_ir}")
                    lineas_text.append(f"    pop dx")
                else:
                    val_loc = self._loc_operando(arg)
                    if val_loc == "eax":
                        lineas_text.append(f"    call PRINT_INT             {comentario_ir}")
                    else:
                        lineas_text.append(f"    push eax")
                        lineas_text.append(f"    mov eax, {val_loc}")
                        lineas_text.append(f"    call PRINT_INT             {comentario_ir}")
                        lineas_text.append(f"    pop eax")
                continue

            # 10. LECTURA (read / cin)
            elif op == "read":
                dest = c.resultado or c.arg1
                dest_loc = self._loc_operando(dest)
                lineas_text.append(f"    call READ_INT              {comentario_ir}")
                if dest_loc != "eax":
                    lineas_text.append(f"    mov {dest_loc}, eax")
                continue

            # 11. RETORNO DE FUNCIÓN
            elif op == "return":
                if c.arg1:
                    ret_loc = self._loc_operando(c.arg1)
                    if ret_loc != "eax":
                        lineas_text.append(f"    mov eax, {ret_loc}         {comentario_ir}")
                    # Si no hubo print previo en el programa, imprimir el valor de retorno
                    # para que en tiempo de ejecución en DOS se observe el resultado
                    if not any(cd.op.lower() in ("print", "write") for cd in self.cuadruplos):
                        lineas_text.append("    call PRINT_INT             ; Mostrar valor de retorno en pantalla")
                lineas_text.append("    mov sp, bp")
                lineas_text.append("    pop bp")
                lineas_text.append("    mov ax, 4C00h")
                lineas_text.append("    int 21h")
                continue

            # Por defecto / instrucción no reconocida
            lineas_text.append(f"    ; [NO_TRADUCIDA] {comentario_ir}")

        # Si el programa no contiene ninguna instrucción explícita de print/write,
        # imprimir automáticamente el resultado de la última variable asignada para mostrar
        # el cálculo en pantalla al ejecutar el .asm en GUI Turbo Assembler.
        hay_salida_explicita = any(c.op.lower() in ("print", "write") for c in self.cuadruplos)
        if not hay_salida_explicita:
            ultima_var = None
            for c in reversed(self.cuadruplos):
                if c.resultado and c.resultado.isidentifier():
                    ultima_var = c.resultado.strip()
                    break
            if ultima_var:
                loc = self._loc_operando(ultima_var)
                lineas_text.append("")
                lineas_text.append("; --- Mostrar resultado del programa en pantalla ---")
                if loc != "eax":
                    lineas_text.append(f"    mov eax, {loc}")
                lineas_text.append("    call PRINT_INT")

        # Epílogo de salida estándar DOS
        lineas_text.append("")
        lineas_text.append("; --- Epílogo de terminación exitosa ---")
        lineas_text.append("    mov sp, bp")
        lineas_text.append("    pop bp")
        lineas_text.append("    mov ax, 4C00h               ; Retorno a DOS (EXIT_SUCCESS)")
        lineas_text.append("    int 21h")

        # Ensamblar el archivo completo estructurado compatible con TASM
        fecha_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        m = self.allocator.obtener_metricas()

        cabecera = [
            "; ============================================================================",
            "; ARCHIVO OBJETO GENERADO (.ASM) - COMPATIBLE CON TURBO ASSEMBLER (TASM)",
            "; Arquitectura: x86 (IA-32 / 80386) - Modo DOS Real / Protegido",
            "; Compilador C++: Generación de Código Objeto con Asignación de Registros",
            f"; Algoritmo: Coloración Mínima de Grafos de Interferencia (chi = {m['numero_cromatico']})",
            f"; Fecha de Generación: {fecha_str}",
            f"; Registros x86 Asignados: {m['registros_utilizados']} / {m['registros_disponibles']}",
            "; ============================================================================",
            "",
            ".MODEL SMALL",
            ".386",
            ".STACK 1000h",
            ""
        ]

        seccion_data = [
            ".DATA",
            "    ; Búferes y constantes para E/S del sistema",
            "    buffer_num   DB 16 DUP('$')",
            "    str_cero     DB '0', '$'",
            "    newline_str  DB 13, 10, '$'",
            "    ; Variables del programa almacenadas en memoria principal"
        ]
        if self.variables_bss:
            for v in sorted(self.variables_bss):
                seccion_data.append(f"    {v:<12} DD 0")
        else:
            seccion_data.append("    ; (Todas las variables residen óptimamente en registros)")

        for sp in self.allocator.spills:
            seccion_data.append(f"    spill_{sp:<6} DD 0")

        if self.cadenas_data:
            seccion_data.append("")
            seccion_data.append("    ; Cadenas de texto del programa")
            for lbl, val in sorted(self.cadenas_data.items()):
                seccion_data.append(f'    {lbl:<12} DB "{val}", 13, 10, "$"')

        seccion_data.append("")

        seccion_code_header = [
            ".CODE",
            "",
            "; --- Entrada principal del programa ---",
            "START:",
            "main:",
            "    mov ax, @data",
            "    mov ds, ax",
            "    mov es, ax",
            ""
        ]

        seccion_procedimientos_aux = [
            "",
            "; ============================================================================",
            "; RUTINAS AUXILIARES DE ENTRADA / SALIDA (DOS INT 21h)",
            "; ============================================================================",
            "",
            "; --- Rutina auxiliar para imprimir entero en EAX con salto de línea ---",
            "PRINT_INT PROC NEAR",
            "    push eax",
            "    push ebx",
            "    push ecx",
            "    push edx",
            "    push si",
            "    push di",
            "",
            "    cmp eax, 0",
            "    jne PI_NOT_ZERO",
            "    mov dx, offset str_cero",
            "    mov ah, 09h",
            "    int 21h",
            "    mov dx, offset newline_str",
            "    mov ah, 09h",
            "    int 21h",
            "    jmp PI_DONE",
            "",
            "PI_NOT_ZERO:",
            "    mov di, offset buffer_num + 14",
            "    mov byte ptr [di + 1], '$'",
            "    mov ecx, 0",
            "",
            "    cmp eax, 0",
            "    jge PI_DIV_LOOP",
            "    neg eax",
            "    mov ecx, 1",
            "",
            "PI_DIV_LOOP:",
            "    mov edx, 0",
            "    mov ebx, 10",
            "    div ebx",
            "    add dl, '0'",
            "    mov [di], dl",
            "    dec di",
            "    cmp eax, 0",
            "    jne PI_DIV_LOOP",
            "",
            "    cmp ecx, 1",
            "    jne PI_SHOW",
            "    mov byte ptr [di], '-'",
            "    dec di",
            "",
            "PI_SHOW:",
            "    inc di",
            "    mov dx, di",
            "    mov ah, 09h",
            "    int 21h",
            "",
            "    mov dx, offset newline_str",
            "    mov ah, 09h",
            "    int 21h",
            "",
            "PI_DONE:",
            "    pop di",
            "    pop si",
            "    pop edx",
            "    pop ecx",
            "    pop ebx",
            "    pop eax",
            "    ret",
            "PRINT_INT ENDP",
            "",
            "; --- Rutina auxiliar para imprimir cadena terminada en '$' (offset en DX) ---",
            "PRINT_STR PROC NEAR",
            "    push ax",
            "    mov ah, 09h",
            "    int 21h",
            "    pop ax",
            "    ret",
            "PRINT_STR ENDP",
            "",
            "; --- Rutina auxiliar para leer un entero desde teclado a EAX ---",
            "READ_INT PROC NEAR",
            "    push ebx",
            "    push ecx",
            "    push edx",
            "    mov ebx, 0",
            "    mov ecx, 0",
            "RI_READ:",
            "    mov ah, 01h",
            "    int 21h",
            "    cmp al, 13",
            "    je RI_END",
            "    cmp al, 10",
            "    je RI_END",
            "    cmp al, ' '",
            "    je RI_END",
            "    cmp al, '-'",
            "    jne RI_DIGIT",
            "    mov ecx, 1",
            "    jmp RI_READ",
            "RI_DIGIT:",
            "    sub al, '0'",
            "    movzx edx, al",
            "    imul ebx, 10",
            "    add ebx, edx",
            "    jmp RI_READ",
            "RI_END:",
            "    cmp ecx, 1",
            "    jne RI_DONE",
            "    neg ebx",
            "RI_DONE:",
            "    mov eax, ebx",
            "    pop edx",
            "    pop ecx",
            "    pop ebx",
            "    ret",
            "READ_INT ENDP",
            "",
            "END START"
        ]

        documento_completo = (
            "\n".join(cabecera) + "\n" +
            "\n".join(seccion_data) + "\n" +
            "\n".join(seccion_code_header) + "\n" +
            "\n".join(lineas_text) + "\n" +
            "\n".join(seccion_procedimientos_aux) + "\n"
        )

        return documento_completo
