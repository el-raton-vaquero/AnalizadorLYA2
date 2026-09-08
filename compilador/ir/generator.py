"""
==============================================================================
  COMPILADOR - GENERADOR DE CÓDIGO INTERMEDIO (IR)
  Del AST validado a instrucciones simples (IR)
  Materia: Lenguajes y Autómatas II (SCD-1016)
==============================================================================

Formatos soportados:
  - Cuádruplos numerados: #N (operador, arg1, arg2, resultado)
  - Triplos: (operador, arg1, arg2, resultado)
  - Código de Tres Direcciones (3AC): instrucciones simples tipo 't1 = 4 * 2'
  - Notación Postfija (RPN): recorrido en postorden del AST
"""

import sys
import os

# Asegurar que la raíz del proyecto esté en sys.path para importar módulos hermanos
_raiz_proyecto = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _raiz_proyecto not in sys.path:
    sys.path.insert(0, _raiz_proyecto)

class Cuadruplo:
    """
    Representa una instrucción de cuatro partes (cuádruplo/triplo numerado).
    Campos: #, operador, arg1, arg2, resultado.
    """
    def __init__(self, numero, op, arg1="", arg2="", resultado=""):
        self.numero = numero
        self.op = str(op) if op is not None else ""
        self.arg1 = str(arg1) if arg1 is not None and arg1 != "" else ""
        self.arg2 = str(arg2) if arg2 is not None and arg2 != "" else ""
        self.resultado = str(resultado) if resultado is not None and resultado != "" else ""

    def to_ir_tuple(self):
        """
        Formato oficial .ir:
        #1 (*, 4, 2, t1)
        #2 (+, 3, t1, t2)
        #3 (=, t2, , x)
        """
        return f"#{self.numero} ({self.op}, {self.arg1}, {self.arg2}, {self.resultado})"

    def to_triplo(self):
        """Formato triplo sin número: (op, arg1, arg2, res)."""
        return f"({self.op}, {self.arg1}, {self.arg2}, {self.resultado})"

    def to_3ac(self):
        """
        Representación en Código de Tres Direcciones (3AC) legible.
        """
        op = self.op
        a1 = self.arg1
        a2 = self.arg2
        res = self.resultado

        if op == "label":
            return f"{res}:"
        elif op == "goto":
            return f"goto {res}"
        elif op == "ifFalse":
            return f"ifFalse {a1} goto {res}"
        elif op == "ifTrue":
            return f"if {a1} goto {res}"
        elif op == "=":
            return f"{res} = {a1}"
        elif op in ("+", "-", "*", "/", "%", "==", "!=", "<", ">", "<=", ">=", "&&", "||"):
            return f"{res} = {a1} {op} {a2}"
        elif op == "!":
            return f"{res} = !{a1}"
        elif op == "neg":
            return f"{res} = -{a1}"
        elif op == "[]":
            return f"{res} = {a1}[{a2}]"
        elif op == "[]=":
            return f"{res}[{a2}] = {a1}"
        elif op == "return":
            return f"return {a1}" if a1 else "return"
        elif op == "print":
            return f"print {a1}"
        elif op == "read":
            return f"read {res or a1}"
        elif op == "param":
            return f"param {a1}"
        elif op == "call":
            return f"{res} = call {a1}, {a2}"
        elif op == "func_begin":
            return f"function {a1}:"
        elif op == "func_end":
            return f"end function {a1}"
        else:
            return f"{res} = {op} {a1} {a2}".strip()

    def __str__(self):
        return self.to_ir_tuple()

    def __repr__(self):
        return f"Cuadruplo({self.numero}, {self.op!r}, {self.arg1!r}, {self.arg2!r}, {self.resultado!r})"


class IRGenerator:
    """
    Generador de Código Intermedio (IR) que recorre el AST validado
    y produce cuádruplos, triplos, código 3AC y notación postfija.
    """
    def __init__(self):
        self.instrucciones = []
        self.temp_count = 0
        self.label_count = 0
        self.postfijas = []  # Lista de dicts: {'expr': str, 'postfija': str, 'linea': int}

    def reset(self):
        self.instrucciones.clear()
        self.temp_count = 0
        self.label_count = 0
        self.postfijas.clear()

    def nuevo_temporal(self):
        """Genera variables temporales ficticias t1, t2, t3..."""
        self.temp_count += 1
        return f"t{self.temp_count}"

    def nueva_etiqueta(self):
        """Genera etiquetas de salto L1, L2, L3..."""
        self.label_count += 1
        return f"L{self.label_count}"

    def emitir(self, op, arg1="", arg2="", resultado=""):
        """Emite un nuevo cuádruplo numerado."""
        numero = len(self.instrucciones) + 1
        c = Cuadruplo(numero, op, arg1, arg2, resultado)
        self.instrucciones.append(c)
        return c

    # ========================================================================
    #  NOTACIÓN POSTFIJA
    #  Recorrido postorden: hijos primero, raíz al final
    # ========================================================================
    def obtener_tokens_postfija(self, nodo):
        """
        Recorre el AST de una expresión en postorden devolviendo una lista
        de tokens en notación postfija (RPN).
        """
        if nodo is None:
            return []

        et = getattr(nodo, "etiqueta", "")
        val = getattr(nodo, "valor", "")
        hijos = getattr(nodo, "hijos", [])

        if et in ("Num", "Id", "Bool"):
            return [str(val)]
        elif et == "Cadena":
            return [str(val)]
        elif et == "BinOp":
            izq = self.obtener_tokens_postfija(hijos[0]) if len(hijos) > 0 else []
            der = self.obtener_tokens_postfija(hijos[1]) if len(hijos) > 1 else []
            return izq + der + [str(val)]
        elif et == "UnOp":
            operando = self.obtener_tokens_postfija(hijos[0]) if len(hijos) > 0 else []
            op_sym = f"u{val}" if val == "-" else str(val)
            return operando + [op_sym]
        elif et == "Assign":
            der = self.obtener_tokens_postfija(hijos[1]) if len(hijos) > 1 else []
            izq_val = hijos[0].valor if hijos and hasattr(hijos[0], 'valor') else "x"
            return der + [str(izq_val), "="]
        elif et == "PostIncDec":
            op_val = hijos[0].valor if hijos and hasattr(hijos[0], 'valor') else ""
            return [op_val, str(val)]
        elif et == "AccesoArreglo":
            idx = self.obtener_tokens_postfija(hijos[0]) if hijos else []
            return [str(val)] + idx + ["[]"]
        elif et == "Llamada":
            args = []
            for h in hijos:
                args.extend(self.obtener_tokens_postfija(h))
            return args + [f"call {val}"]
        elif et == "Ternario":
            c = self.obtener_tokens_postfija(hijos[0]) if len(hijos) > 0 else []
            si = self.obtener_tokens_postfija(hijos[1]) if len(hijos) > 1 else []
            no = self.obtener_tokens_postfija(hijos[2]) if len(hijos) > 2 else []
            return c + si + no + ["?:"]
        elif et in ("Inicializador", "Condición", "Inicialización", "Actualización"):
            if hijos:
                return self.obtener_tokens_postfija(hijos[0])
            return []
        else:
            res = []
            for h in hijos:
                res.extend(self.obtener_tokens_postfija(h))
            return res

    def expr_a_texto(self, nodo):
        """Reconstruye una expresión infija simple para mostrar junto a la postfija."""
        if nodo is None:
            return ""
        et = getattr(nodo, "etiqueta", "")
        val = getattr(nodo, "valor", "")
        hijos = getattr(nodo, "hijos", [])

        if et in ("Num", "Id", "Bool", "Cadena"):
            return str(val)
        elif et == "BinOp" and len(hijos) >= 2:
            return f"({self.expr_a_texto(hijos[0])} {val} {self.expr_a_texto(hijos[1])})"
        elif et == "UnOp" and len(hijos) >= 1:
            return f"{val}{self.expr_a_texto(hijos[0])}"
        elif et == "Assign" and len(hijos) >= 2:
            return f"{self.expr_a_texto(hijos[0])} = {self.expr_a_texto(hijos[1])}"
        elif et == "PostIncDec" and len(hijos) >= 1:
            return f"{self.expr_a_texto(hijos[0])}{val}"
        elif et == "AccesoArreglo" and hijos:
            return f"{val}[{self.expr_a_texto(hijos[0])}]"
        elif et == "Llamada":
            args_str = ", ".join(self.expr_a_texto(h) for h in hijos)
            return f"{val}({args_str})"
        elif et == "Ternario" and len(hijos) >= 3:
            return f"{self.expr_a_texto(hijos[0])} ? {self.expr_a_texto(hijos[1])} : {self.expr_a_texto(hijos[2])}"
        elif hijos:
            return self.expr_a_texto(hijos[0])
        return str(val)

    def registrar_postfija(self, nodo_expr):
        """Registra la conversión infija -> postfija de una expresión si tiene contenido."""
        if nodo_expr is None:
            return
        tokens = self.obtener_tokens_postfija(nodo_expr)
        if tokens:
            texto_infija = self.expr_a_texto(nodo_expr)
            texto_post = " ".join(tokens)
            linea = getattr(nodo_expr, "linea", None) or 1
            self.postfijas.append({
                "linea": linea,
                "infija": texto_infija,
                "postfija": texto_post
            })

    # ========================================================================
    #  GENERACIÓN DE CÓDIGO INTERMEDIO (Visitor)
    # ========================================================================
    def generar(self, nodo_raiz):
        """
        Punto de entrada: recibe el nodo raíz del AST y devuelve:
        (instrucciones_cuadruplos, lista_postfijas, texto_ir)
        """
        self.reset()
        if nodo_raiz:
            self.visitar(nodo_raiz)
        return self.instrucciones, self.postfijas, self.obtener_texto_ir()

    def obtener_texto_ir(self):
        """Devuelve el contenido completo en formato de archivo .ir."""
        return "\n".join(inst.to_ir_tuple() for inst in self.instrucciones)

    def obtener_texto_3ac(self):
        """Devuelve el contenido en formato de tres direcciones (3AC)."""
        return "\n".join(inst.to_3ac() for inst in self.instrucciones)

    def visitar(self, nodo):
        if nodo is None:
            return

        et = getattr(nodo, "etiqueta", "")

        if et == "Programa":
            for hijo in nodo.hijos:
                self.visitar(hijo)

        elif et == "Función":
            nombre_func = nodo.valor
            self.emitir("func_begin", nombre_func, "", "")
            for hijo in nodo.hijos:
                if hijo.etiqueta == "Bloque":
                    self.visitar(hijo)
            self.emitir("func_end", nombre_func, "", "")

        elif et in ("Varaible Global", "Declaración Local"):
            nombre_var = nodo.valor
            for hijo in nodo.hijos:
                if hijo.etiqueta == "Inicializador" and hijo.hijos:
                    expr_nodo = hijo.hijos[0]
                    self.registrar_postfija(expr_nodo)
                    val = self.visitar_expr(expr_nodo)
                    self.emitir("=", val, "", nombre_var)

        elif et == "Bloque":
            for hijo in nodo.hijos:
                self.visitar(hijo)

        elif et == "Estructura de Control":
            if nodo.valor == "if":
                self.visitar_if(nodo)

        elif et == "Ciclo":
            if nodo.valor == "while":
                self.visitar_while(nodo)
            elif nodo.valor == "for":
                self.visitar_for(nodo)

        elif et == "Instrucción":
            if nodo.valor == "return":
                if nodo.hijos:
                    self.registrar_postfija(nodo.hijos[0])
                    val = self.visitar_expr(nodo.hijos[0])
                    self.emitir("return", val, "", "")
                else:
                    self.emitir("return", "", "", "")

        elif et == "Salida por Consola":  # cout
            for hijo in nodo.hijos:
                self.registrar_postfija(hijo)
                val = self.visitar_expr(hijo)
                self.emitir("print", val, "", "")

        elif et == "Entrada por Consola":  # cin
            for hijo in nodo.hijos:
                var_destino = getattr(hijo, "valor", "x")
                self.emitir("read", "", "", var_destino)

        elif et in ("Assign", "BinOp", "UnOp", "PostIncDec", "Llamada", "Ternario"):
            self.registrar_postfija(nodo)
            self.visitar_expr(nodo)

        else:
            # Si contiene hijos no clasificados, recorrerlos
            for hijo in getattr(nodo, "hijos", []):
                self.visitar(hijo)

    # ========================================================================
    #  ESTRUCTURAS DE CONTROL DE FLUJO
    # ========================================================================
    def visitar_if(self, nodo):
        """
        Genera el patrón if / else:
          t1 = (x > 5)
          ifFalse t1 goto L1
          [rama then]
          goto L2
          L1:
          [rama else]
          L2:
        """
        cond_nodo = None
        then_nodo = None
        else_nodo = None

        for hijo in nodo.hijos:
            if hijo.etiqueta == "Condición" and hijo.hijos:
                cond_nodo = hijo.hijos[0]
            elif hijo.etiqueta == "Estructura de Control" and hijo.valor == "else":
                else_nodo = hijo
            elif then_nodo is None and hijo.etiqueta != "Condición":
                then_nodo = hijo

        # 1. Evaluar condición
        if cond_nodo:
            self.registrar_postfija(cond_nodo)
            cond_res = self.visitar_expr(cond_nodo)
        else:
            cond_res = "true"

        label_else = self.nueva_etiqueta()
        label_fin = self.nueva_etiqueta()

        if else_nodo is not None:
            # Caso if - else
            self.emitir("ifFalse", cond_res, "", label_else)
            if then_nodo:
                self.visitar(then_nodo)
            self.emitir("goto", "", "", label_fin)
            self.emitir("label", "", "", label_else)
            # El hijo de else_nodo contiene el cuerpo de la rama else
            for h in else_nodo.hijos:
                self.visitar(h)
            self.emitir("label", "", "", label_fin)
        else:
            # Caso if simple sin else
            self.emitir("ifFalse", cond_res, "", label_fin)
            if then_nodo:
                self.visitar(then_nodo)
            self.emitir("label", "", "", label_fin)

    def visitar_while(self, nodo):
        """
        Genera el ciclo while:
          L_inicio:
          t1 = condición
          ifFalse t1 goto L_fin
          [cuerpo]
          goto L_inicio
          L_fin:
        """
        cond_nodo = None
        cuerpo_nodo = None

        for hijo in nodo.hijos:
            if hijo.etiqueta == "Condición" and hijo.hijos:
                cond_nodo = hijo.hijos[0]
            elif cuerpo_nodo is None and hijo.etiqueta != "Condición":
                cuerpo_nodo = hijo

        label_inicio = self.nueva_etiqueta()
        label_fin = self.nueva_etiqueta()

        self.emitir("label", "", "", label_inicio)

        if cond_nodo:
            self.registrar_postfija(cond_nodo)
            cond_res = self.visitar_expr(cond_nodo)
        else:
            cond_res = "true"

        self.emitir("ifFalse", cond_res, "", label_fin)
        if cuerpo_nodo:
            self.visitar(cuerpo_nodo)
        self.emitir("goto", "", "", label_inicio)
        self.emitir("label", "", "", label_fin)

    def visitar_for(self, nodo):
        """
        Genera el ciclo for:
          [init]
          L_cond:
          t1 = condición
          ifFalse t1 goto L_fin
          [cuerpo]
          L_upd:
          [update]
          goto L_cond
          L_fin:
        """
        init_nodo = None
        cond_nodo = None
        upd_nodo = None
        cuerpo_nodo = None

        for hijo in nodo.hijos:
            if hijo.etiqueta == "Inicialización" and hijo.hijos:
                init_nodo = hijo.hijos[0]
            elif hijo.etiqueta == "Condición" and hijo.hijos:
                cond_nodo = hijo.hijos[0]
            elif hijo.etiqueta == "Actualización" and hijo.hijos:
                upd_nodo = hijo.hijos[0]
            elif cuerpo_nodo is None and hijo.etiqueta not in ("Inicialización", "Condición", "Actualización"):
                cuerpo_nodo = hijo

        # 1. Inicialización
        if init_nodo:
            self.registrar_postfija(init_nodo)
            self.visitar_expr(init_nodo)

        label_cond = self.nueva_etiqueta()
        label_upd = self.nueva_etiqueta()
        label_fin = self.nueva_etiqueta()

        self.emitir("label", "", "", label_cond)

        # 2. Condición
        if cond_nodo:
            self.registrar_postfija(cond_nodo)
            cond_res = self.visitar_expr(cond_nodo)
            self.emitir("ifFalse", cond_res, "", label_fin)

        # 3. Cuerpo
        if cuerpo_nodo:
            self.visitar(cuerpo_nodo)

        # 4. Actualización
        self.emitir("label", "", "", label_upd)
        if upd_nodo:
            self.registrar_postfija(upd_nodo)
            self.visitar_expr(upd_nodo)

        self.emitir("goto", "", "", label_cond)
        self.emitir("label", "", "", label_fin)

    # ========================================================================
    #  EXPRESIONES Y OPERACIONES
    # ========================================================================
    def visitar_expr(self, nodo):
        """
        Evalúa un nodo de expresión en el AST y devuelve el nombre de la variable,
        literal o temporal (t1, t2...) que contiene su resultado.
        """
        if nodo is None:
            return ""

        et = getattr(nodo, "etiqueta", "")
        val = getattr(nodo, "valor", "")
        hijos = getattr(nodo, "hijos", [])

        # Literales y valores simples
        if et in ("Num", "Id", "Bool", "Cadena"):
            return str(val)

        # Acceso a arreglo: a[i]
        elif et == "AccesoArreglo":
            idx = self.visitar_expr(hijos[0]) if hijos else "0"
            t = self.nuevo_temporal()
            self.emitir("[]", str(val), idx, t)
            return t

        # Operación Binaria: +, -, *, /, %, <, >, <=, >=, ==, !=, &&, ||
        elif et == "BinOp":
            izq = self.visitar_expr(hijos[0]) if len(hijos) > 0 else ""
            der = self.visitar_expr(hijos[1]) if len(hijos) > 1 else ""
            t = self.nuevo_temporal()
            self.emitir(str(val), izq, der, t)
            return t

        # Operación Unaria: !, -
        elif et == "UnOp":
            operando = self.visitar_expr(hijos[0]) if len(hijos) > 0 else ""
            t = self.nuevo_temporal()
            op = "neg" if str(val) == "-" else str(val)
            self.emitir(op, operando, "", t)
            return t

        # Asignación: x = expr
        elif et == "Assign":
            der = self.visitar_expr(hijos[1]) if len(hijos) > 1 else ""
            izq_nodo = hijos[0] if len(hijos) > 0 else None
            if izq_nodo and getattr(izq_nodo, "etiqueta", "") == "AccesoArreglo":
                idx = self.visitar_expr(izq_nodo.hijos[0]) if izq_nodo.hijos else "0"
                self.emitir("[]=", der, idx, str(izq_nodo.valor))
                return str(izq_nodo.valor)
            else:
                dest = getattr(izq_nodo, "valor", "x")
                self.emitir("=", der, "", dest)
                return dest

        # Incremento / Decremento posterior: x++, x--
        elif et == "PostIncDec":
            var_nombre = getattr(hijos[0], "valor", "x") if hijos else "x"
            op_arit = "+" if str(val) == "++" else "-"
            t = self.nuevo_temporal()
            self.emitir(op_arit, var_nombre, "1", t)
            self.emitir("=", t, "", var_nombre)
            return var_nombre

        # Operador Ternario: cond ? entonces : sino
        elif et == "Ternario":
            cond_res = self.visitar_expr(hijos[0]) if len(hijos) > 0 else "true"
            l_else = self.nueva_etiqueta()
            l_fin = self.nueva_etiqueta()
            res_temp = self.nuevo_temporal()

            self.emitir("ifFalse", cond_res, "", l_else)
            then_res = self.visitar_expr(hijos[1]) if len(hijos) > 1 else ""
            self.emitir("=", then_res, "", res_temp)
            self.emitir("goto", "", "", l_fin)
            self.emitir("label", "", "", l_else)
            else_res = self.visitar_expr(hijos[2]) if len(hijos) > 2 else ""
            self.emitir("=", else_res, "", res_temp)
            self.emitir("label", "", "", l_fin)
            return res_temp

        # Llamada a función: f(a, b)
        elif et == "Llamada":
            args_evaluados = []
            for h in hijos:
                args_evaluados.append(self.visitar_expr(h))
            for a in args_evaluados:
                self.emitir("param", a, "", "")
            t = self.nuevo_temporal()
            self.emitir("call", str(val), str(len(args_evaluados)), t)
            return t

        elif hijos:
            return self.visitar_expr(hijos[0])

        return str(val)


def generar_ir(arbol_ast):
    """
    Función de conveniencia para generar el código intermedio a partir de un AST.
    Devuelve: (instrucciones, postfijas, texto_ir)
    """
    gen = IRGenerator()
    return gen.generar(arbol_ast)


# ============================================================================
#  EJECUCIÓN CLI DIRECTA (Para pruebas y automatización)
# ============================================================================
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python generator.py <archivo_fuente.cpp> [archivo_salida.ir]")
        print("\nEjecutando demostración interna con x = 3 + 4 * 2:")
        # Demostración manual
        from AnalisisSema import Lexer, Parser, SemanticAnalyzer
        demo_code = "int x = 3 + 4 * 2;"
        lexer = Lexer(demo_code)
        tokens = lexer.tokenize()
        parser = Parser(tokens, demo_code)
        ast = parser.parse()
        gen = IRGenerator()
        insts, posts, texto = gen.generar(ast)
        print("\n=== Formato .ir ===")
        print(texto)
        print("\n=== Formato 3AC ===")
        print(gen.obtener_texto_3ac())
        print("\n=== Notación Postfija ===")
        for p in posts:
            print(f"{p['infija']} -> {p['postfija']}")
    else:
        fuente = sys.argv[1]
        salida = sys.argv[2] if len(sys.argv) > 2 else os.path.splitext(fuente)[0] + ".ir"

        with open(fuente, "r", encoding="utf-8") as f:
            codigo = f.read()

        # Importar lexer y parser
        try:
            from AnalisisSema import Lexer, Parser, SemanticAnalyzer
        except ImportError:
            sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
            from AnalisisSema import Lexer, Parser, SemanticAnalyzer

        lexer = Lexer(codigo)
        tokens = lexer.tokenize()
        parser = Parser(tokens, codigo)
        ast = parser.parse()

        if parser.errors:
            print(f"Error: se encontraron {len(parser.errors)} errores de sintaxis.")
            for e in parser.errors:
                print(f" - {e.message}")
            sys.exit(1)

        gen = IRGenerator()
        insts, posts, texto = gen.generar(ast)

        with open(salida, "w", encoding="utf-8") as f:
            f.write(texto + "\n")

        print(f"Código IR generado exitosamente en: {salida}")
        print(f"Total instrucciones generadas: {len(insts)}")
