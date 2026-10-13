"""

  COMPILADOR - GENERADOR DE CÓDIGO INTERMEDIO (IR)
  Materia: Lenguajes y Autómatas II
  Lenguaje Fuente Analizado: C++
  Implementación: Python 3


Este módulo implementa el Generador de Código Intermedio (IR) a partir del análisis
de código fuente en C++. Es completamente autónomo y autosuficiente.

Genera cuádruplas en el formato requerido:
  #N (operador, argumento1, argumento2, resultado)
donde:
  - Operadores aritméticos: *, /, %, +, -, neg
  - Asignación: =
  - Relacionales: >, <, >=, <=, ==, !=
  - Control de flujo: IF_FALSE, GOTO, LABEL
  - Temporales: t1, t2, t3, ...
  - Etiquetas: L1, L2, L3, ...
"""

import re
import sys
import os


#  1. REPRESENTACIÓN DE TOKENS Y ÁRBOL SINTÁCTICO ABSTRACTO (AST)

class Token:
    """Representa un token léxico identificado en el código fuente C++."""
    def __init__(self, tipo, valor, pos_inicio=0, pos_fin=0, linea=1):
        self.type = tipo
        self.value = valor
        self.pos_start = pos_inicio
        self.pos_end = pos_fin
        self.linea = linea

    def __repr__(self):
        return f"Token({self.type!r}, {self.value!r}, L{self.linea})"


class NodoAST:
    """Nodo genérico para la construcción del Árbol Sintáctico Abstracto (AST)."""
    def __init__(self, etiqueta, valor=""):
        self.etiqueta = etiqueta  # Ej. 'BinOp', 'Num', 'Id', 'Assign', 'Estructura de Control'
        self.valor = valor        # Ej. '+', '*', '5', 'x', 'if'
        self.hijos = []
        self.linea = 1
        self.tipo = None

    def agregar_hijo(self, nodo_hijo):
        if nodo_hijo is not None:
            self.hijos.append(nodo_hijo)

    def __repr__(self):
        return f"NodoAST({self.etiqueta!r}, {self.valor!r}, hijos={len(self.hijos)})"



#  2. ANALIZADOR LÉXICO (LEXER) PARA C++


class LexerCPP:
    """Analizador léxico enfocado en la sintaxis de C++."""
    def __init__(self, codigo):
        self.codigo = codigo
        self.tokens = []

        # Especificación de reglas léxicas mediante expresiones regulares
        reglas = [
            ('COMENTARIO_BLOQUE', r'/\*[\s\S]*?\*/'),
            ('COMENTARIO_LINEA',  r'//[^\n]*'),
            ('RESERVADA', r'\b(int|float|double|char|void|bool|string|if|else|while|for|return|cout|cin|endl|true|false)\b'),
            ('NUMERO',    r'\d+(\.\d+)?'),
            ('IDENTIFICADOR', r'[A-Za-z_][A-Za-z0-9_]*'),
            ('CADENA',    r'".*?"'),
            ('OP_INCDEC', r'\+\+|--'),
            ('OP_FLUJO',  r'<<|>>'),
            ('OP_REL',    r'==|!=|<=|>=|<|>'),
            ('OP_LOGICO', r'&&|\|\||!'),
            ('OP_ARIT',   r'[+\-*/%]'),
            ('ASIGNACION',r'='),
            ('PAR_IZQ',   r'\('),
            ('PAR_DER',   r'\)'),
            ('LLAVE_IZQ', r'\{'),
            ('LLAVE_DER', r'\}'),
            ('COR_IZQ',   r'\['),
            ('COR_DER',   r'\]'),
            ('PUNTOCOMA', r';'),
            ('COMA',      r','),
            ('TERNARIO',  r'\?|:'),
            ('ESPACIO',   r'[ \t\r\n]+'),
            ('ERROR',     r'.'),
        ]

        patron = '|'.join(f'(?P<{nombre}>{regex})' for nombre, regex in reglas)
        self.regex = re.compile(patron)

    def tokenizar(self):
        self.tokens = []
        for match in self.regex.finditer(self.codigo):
            tipo = match.lastgroup
            valor = match.group()
            pos = match.start()
            linea = self.codigo[:pos].count('\n') + 1

            if tipo in ('ESPACIO', 'COMENTARIO_BLOQUE', 'COMENTARIO_LINEA'):
                continue
            elif tipo == 'ERROR':
                # Carácter no reconocido, se ignora o registra
                continue
            else:
                self.tokens.append(Token(tipo, valor, pos, match.end(), linea))
        return self.tokens



#  3. PARSER SINTÁCTICO DE C++ CON PRECEDENCIA DE OPERADORES

class ParserCPP:
    """
    Analizador sintáctico para C++ que genera el AST respetando la
    precedencia formal de operadores:
      1. Paréntesis y llamadas
      2. Unarios (+, -, !)
      3. Multiplicativos (*, /, %)
      4. Aditivos (+, -)
      5. Relacionales (<, >, <=, >=)
      6. Igualdad (==, !=)
      7. Lógicos (&&, luego ||)
      8. Asignación (=)
    """
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    def actual(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def avanzar(self):
        tok = self.actual()
        if self.pos < len(self.tokens):
            self.pos += 1
        return tok

    def coincidir(self, tipo, valor=None):
        tok = self.actual()
        if tok and tok.type == tipo:
            if valor is None or tok.value == valor:
                return self.avanzar()
        return None

    def parse(self):
        """Parsea un programa completo o secuencia de instrucciones C++."""
        nodo_raiz = NodoAST("Programa")
        while self.actual():
            pos_antes = self.pos
            nodo = self.parse_instruccion_o_declaracion()
            if nodo:
                nodo_raiz.agregar_hijo(nodo)
            if self.pos == pos_antes:
                self.avanzar()  # Evitar bucles infinitos en errores sintácticos
        return nodo_raiz

    def parse_instruccion_o_declaracion(self):
        tok = self.actual()
        if not tok:
            return None

        # Bloque con llaves { ... }
        if tok.type == 'LLAVE_IZQ':
            return self.parse_bloque()

        # Estructura if / else
        if tok.type == 'RESERVADA' and tok.value == 'if':
            return self.parse_if()

        # Ciclo while
        if tok.type == 'RESERVADA' and tok.value == 'while':
            return self.parse_while()

        # Ciclo for
        if tok.type == 'RESERVADA' and tok.value == 'for':
            return self.parse_for()

        # Instrucción return
        if tok.type == 'RESERVADA' and tok.value == 'return':
            self.avanzar()
            nodo_ret = NodoAST("Instrucción", "return")
            if self.actual() and self.actual().type != 'PUNTOCOMA':
                nodo_ret.agregar_hijo(self.parse_expresion())
            self.coincidir('PUNTOCOMA')
            return nodo_ret

        # cout << ... ;
        if tok.type == 'RESERVADA' and tok.value == 'cout':
            return self.parse_cout()

        # cin >> ... ;
        if tok.type == 'RESERVADA' and tok.value == 'cin':
            return self.parse_cin()

        # Declaración de variable o función: tipo id ...
        if tok.type == 'RESERVADA' and tok.value in ('int', 'float', 'double', 'char', 'void', 'bool', 'string'):
            tipo_dato = self.avanzar().value
            if self.actual() and self.actual().type == 'IDENTIFICADOR':
                nombre_id = self.avanzar().value

                # Si sigue '(', es definición de función: int suma(int a, int b) { ... }
                if self.actual() and self.actual().type == 'PAR_IZQ':
                    return self.parse_funcion(tipo_dato, nombre_id)

                # Declaración de variable: int x = expr; ó int x;
                nodo_decl = NodoAST("Declaración Local", nombre_id)
                nodo_decl.tipo = tipo_dato
                if self.coincidir('ASIGNACION'):
                    expr = self.parse_expresion()
                    nodo_init = NodoAST("Inicializador")
                    nodo_init.agregar_hijo(expr)
                    nodo_decl.agregar_hijo(nodo_init)
                self.coincidir('PUNTOCOMA')
                return nodo_decl

        # Expresión general o asignación directa (ej. x = 3 + 4 * 2;)
        expr = self.parse_expresion()
        self.coincidir('PUNTOCOMA')
        return expr

    def parse_bloque(self):
        self.coincidir('LLAVE_IZQ')
        nodo_bloque = NodoAST("Bloque")
        while self.actual() and self.actual().type != 'LLAVE_DER':
            pos_antes = self.pos
            instr = self.parse_instruccion_o_declaracion()
            if instr:
                nodo_bloque.agregar_hijo(instr)
            if self.pos == pos_antes:
                self.avanzar()
        self.coincidir('LLAVE_DER')
        return nodo_bloque

    def parse_if(self):
        self.avanzar()  # consume 'if'
        self.coincidir('PAR_IZQ')
        cond = self.parse_expresion()
        self.coincidir('PAR_DER')

        nodo_if = NodoAST("Estructura de Control", "if")
        nodo_cond = NodoAST("Condición")
        nodo_cond.agregar_hijo(cond)
        nodo_if.agregar_hijo(nodo_cond)

        cuerpo_then = self.parse_instruccion_o_declaracion()
        nodo_if.agregar_hijo(cuerpo_then)

        if self.actual() and self.actual().type == 'RESERVADA' and self.actual().value == 'else':
            self.avanzar()  # consume 'else'
            nodo_else = NodoAST("Estructura de Control", "else")
            cuerpo_else = self.parse_instruccion_o_declaracion()
            nodo_else.agregar_hijo(cuerpo_else)
            nodo_if.agregar_hijo(nodo_else)

        return nodo_if

    def parse_while(self):
        self.avanzar()  # consume 'while'
        self.coincidir('PAR_IZQ')
        cond = self.parse_expresion()
        self.coincidir('PAR_DER')

        nodo_while = NodoAST("Ciclo", "while")
        nodo_cond = NodoAST("Condición")
        nodo_cond.agregar_hijo(cond)
        nodo_while.agregar_hijo(nodo_cond)

        cuerpo = self.parse_instruccion_o_declaracion()
        nodo_while.agregar_hijo(cuerpo)
        return nodo_while

    def parse_for(self):
        self.avanzar()  # consume 'for'
        self.coincidir('PAR_IZQ')

        # Inicialización
        nodo_for = NodoAST("Ciclo", "for")
        if self.actual() and self.actual().type != 'PUNTOCOMA':
            init_nodo = self.parse_expresion()
            c_init = NodoAST("Inicialización")
            c_init.agregar_hijo(init_nodo)
            nodo_for.agregar_hijo(c_init)
        self.coincidir('PUNTOCOMA')

        # Condición
        if self.actual() and self.actual().type != 'PUNTOCOMA':
            cond_nodo = self.parse_expresion()
            c_cond = NodoAST("Condición")
            c_cond.agregar_hijo(cond_nodo)
            nodo_for.agregar_hijo(c_cond)
        self.coincidir('PUNTOCOMA')

        # Actualización
        if self.actual() and self.actual().type != 'PAR_DER':
            upd_nodo = self.parse_expresion()
            c_upd = NodoAST("Actualización")
            c_upd.agregar_hijo(upd_nodo)
            nodo_for.agregar_hijo(c_upd)
        self.coincidir('PAR_DER')

        cuerpo = self.parse_instruccion_o_declaracion()
        nodo_for.agregar_hijo(cuerpo)
        return nodo_for

    def parse_cout(self):
        self.avanzar()  # consume 'cout'
        nodo_cout = NodoAST("Salida por Consola", "cout")
        while self.actual() and self.actual().type == 'OP_FLUJO' and self.actual().value == '<<':
            self.avanzar()  # consume '<<'
            if self.actual() and self.actual().type == 'RESERVADA' and self.actual().value == 'endl':
                self.avanzar()
                nodo_cout.agregar_hijo(NodoAST("Cadena", '"\\n"'))
            else:
                nodo_cout.agregar_hijo(self.parse_expresion())
        self.coincidir('PUNTOCOMA')
        return nodo_cout

    def parse_cin(self):
        self.avanzar()  # consume 'cin'
        nodo_cin = NodoAST("Entrada por Consola", "cin")
        while self.actual() and self.actual().type == 'OP_FLUJO' and self.actual().value == '>>':
            self.avanzar()  # consume '>>'
            tok = self.coincidir('IDENTIFICADOR')
            if tok:
                nodo_cin.agregar_hijo(NodoAST("Id", tok.value))
        self.coincidir('PUNTOCOMA')
        return nodo_cin

    def parse_funcion(self, tipo_ret, nombre):
        self.coincidir('PAR_IZQ')
        nodo_func = NodoAST("Función", nombre)
        nodo_func.tipo = tipo_ret

        # Parámetros (ej. int a, int b)
        while self.actual() and self.actual().type != 'PAR_DER':
            if self.actual().type == 'RESERVADA':
                t_param = self.avanzar().value
                if self.actual() and self.actual().type == 'IDENTIFICADOR':
                    nom_param = self.avanzar().value
                    p_nodo = NodoAST("Parámetro", nom_param)
                    p_nodo.tipo = t_param
                    nodo_func.agregar_hijo(p_nodo)
            elif self.actual().type == 'IDENTIFICADOR':
                nom_param = self.avanzar().value
                p_nodo = NodoAST("Parámetro", nom_param)
                nodo_func.agregar_hijo(p_nodo)
            self.coincidir('COMA')

        self.coincidir('PAR_DER')
        cuerpo = self.parse_bloque()
        nodo_func.agregar_hijo(cuerpo)
        return nodo_func

   
    # Jerarquía de Expresiones (Precedencia)
    
    def parse_expresion(self):
        return self.parse_asignacion()

    def parse_asignacion(self):
        nodo = self.parse_ternario()
        if self.actual() and self.actual().type == 'ASIGNACION':
            tok = self.avanzar()
            der = self.parse_asignacion()
            nodo_asig = NodoAST("Assign", "=")
            nodo_asig.agregar_hijo(nodo)
            nodo_asig.agregar_hijo(der)
            return nodo_asig
        return nodo

    def parse_ternario(self):
        cond = self.parse_or()
        if self.actual() and self.actual().type == 'TERNARIO' and self.actual().value == '?':
            self.avanzar()
            entonces = self.parse_asignacion()
            if self.actual() and self.actual().type == 'TERNARIO' and self.actual().value == ':':
                self.avanzar()
                sino = self.parse_asignacion()
                nodo_tern = NodoAST("Ternario", "?:")
                nodo_tern.agregar_hijo(cond)
                nodo_tern.agregar_hijo(entonces)
                nodo_tern.agregar_hijo(sino)
                return nodo_tern
        return cond

    def parse_or(self):
        izq = self.parse_and()
        while self.actual() and self.actual().type == 'OP_LOGICO' and self.actual().value == '||':
            tok = self.avanzar()
            der = self.parse_and()
            nodo = NodoAST("BinOp", tok.value)
            nodo.agregar_hijo(izq)
            nodo.agregar_hijo(der)
            izq = nodo
        return izq

    def parse_and(self):
        izq = self.parse_igualdad()
        while self.actual() and self.actual().type == 'OP_LOGICO' and self.actual().value == '&&':
            tok = self.avanzar()
            der = self.parse_igualdad()
            nodo = NodoAST("BinOp", tok.value)
            nodo.agregar_hijo(izq)
            nodo.agregar_hijo(der)
            izq = nodo
        return izq

    def parse_igualdad(self):
        izq = self.parse_relacional()
        while self.actual() and self.actual().type == 'OP_REL' and self.actual().value in ('==', '!='):
            tok = self.avanzar()
            der = self.parse_relacional()
            nodo = NodoAST("BinOp", tok.value)
            nodo.agregar_hijo(izq)
            nodo.agregar_hijo(der)
            izq = nodo
        return izq

    def parse_relacional(self):
        izq = self.parse_aditivo()
        while self.actual() and self.actual().type == 'OP_REL' and self.actual().value in ('<', '>', '<=', '>='):
            tok = self.avanzar()
            der = self.parse_aditivo()
            nodo = NodoAST("BinOp", tok.value)
            nodo.agregar_hijo(izq)
            nodo.agregar_hijo(der)
            izq = nodo
        return izq

    def parse_aditivo(self):
        izq = self.parse_multiplicativo()
        while self.actual() and self.actual().type == 'OP_ARIT' and self.actual().value in ('+', '-'):
            tok = self.avanzar()
            der = self.parse_multiplicativo()
            nodo = NodoAST("BinOp", tok.value)
            nodo.agregar_hijo(izq)
            nodo.agregar_hijo(der)
            izq = nodo
        return izq

    def parse_multiplicativo(self):
        izq = self.parse_unario()
        while self.actual() and self.actual().type == 'OP_ARIT' and self.actual().value in ('*', '/', '%'):
            tok = self.avanzar()
            der = self.parse_unario()
            nodo = NodoAST("BinOp", tok.value)
            nodo.agregar_hijo(izq)
            nodo.agregar_hijo(der)
            izq = nodo
        return izq

    def parse_unario(self):
        if self.actual() and (self.actual().value in ('-', '+', '!')):
            tok = self.avanzar()
            operando = self.parse_unario()
            nodo = NodoAST("UnOp", tok.value)
            nodo.agregar_hijo(operando)
            return nodo
        return self.parse_primario()

    def parse_primario(self):
        tok = self.actual()
        if not tok:
            return NodoAST("Error", "EOF")

        # Paréntesis (expr)
        if tok.type == 'PAR_IZQ':
            self.avanzar()
            expr = self.parse_expresion()
            self.coincidir('PAR_DER')
            return expr

        # Número
        if tok.type == 'NUMERO':
            self.avanzar()
            return NodoAST("Num", tok.value)

        # Cadena
        if tok.type == 'CADENA':
            self.avanzar()
            return NodoAST("Cadena", tok.value)

        # Booleanos
        if tok.type == 'RESERVADA' and tok.value in ('true', 'false'):
            self.avanzar()
            return NodoAST("Bool", tok.value)

        # Identificador (variable, arreglo o llamada)
        if tok.type == 'IDENTIFICADOR':
            self.avanzar()
            nodo_base = NodoAST("Id", tok.value)

            # Acceso a arreglo: a[idx]
            if self.actual() and self.actual().type == 'COR_IZQ':
                self.avanzar()
                idx = self.parse_expresion()
                self.coincidir('COR_DER')
                nodo_arr = NodoAST("AccesoArreglo", tok.value)
                nodo_arr.agregar_hijo(idx)
                nodo_base = nodo_arr

            # Llamada a función: foo(arg1, arg2)
            elif self.actual() and self.actual().type == 'PAR_IZQ':
                self.avanzar()
                nodo_call = NodoAST("Llamada", tok.value)
                while self.actual() and self.actual().type != 'PAR_DER':
                    nodo_call.agregar_hijo(self.parse_expresion())
                    self.coincidir('COMA')
                self.coincidir('PAR_DER')
                nodo_base = nodo_call

            # Post-incremento o decremento: x++, x--
            if self.actual() and self.actual().type == 'OP_INCDEC':
                op_inc = self.avanzar()
                nodo_inc = NodoAST("PostIncDec", op_inc.value)
                nodo_inc.agregar_hijo(nodo_base)
                return nodo_inc

            return nodo_base

        # Token inesperado
        self.avanzar()
        return NodoAST("Error", tok.value)



#  4. CLASE CUÁDRUPLO


class Cuadruplo:
    """
    Representa una instrucción de código intermedio en formato cuádruplo:
      #N (operador, argumento1, argumento2, resultado)
    """
    def __init__(self, numero, op, arg1="", arg2="", resultado=""):
        self.numero = numero
        self.op = str(op) if op is not None else ""
        self.arg1 = str(arg1) if arg1 is not None and arg1 != "" else ""
        self.arg2 = str(arg2) if arg2 is not None and arg2 != "" else ""
        self.resultado = str(resultado) if resultado is not None and resultado != "" else ""

    def to_ir_tuple(self):
        """
        Formato estándar de cuádruplos:
          #1 (*, 4, 2, t1)
          #2 (+, 3, t1, t2)
          #3 (=, t2, , x)
        """
        return f"#{self.numero} ({self.op}, {self.arg1}, {self.arg2}, {self.resultado})"

    def to_triplo(self):
        """Formato triplo sin número de instrucción."""
        return f"({self.op}, {self.arg1}, {self.arg2}, {self.resultado})"

    def to_3ac(self):
        """Representación en Código de Tres Direcciones (3AC) equivalente."""
        op_upper = self.op.upper()
        a1 = self.arg1
        a2 = self.arg2
        res = self.resultado

        if op_upper == "LABEL":
            return f"{res}:"
        elif op_upper == "GOTO":
            return f"goto {res}"
        elif op_upper in ("IF_FALSE", "IFFALSE"):
            return f"ifFalse {a1} goto {res}"
        elif op_upper in ("IF_TRUE", "IFTRUE"):
            return f"if {a1} goto {res}"
        elif self.op == "=":
            return f"{res} = {a1}"
        elif self.op in ("+", "-", "*", "/", "%", "==", "!=", "<", ">", "<=", ">=", "&&", "||"):
            return f"{res} = {a1} {self.op} {a2}"
        elif self.op == "neg":
            return f"{res} = -{a1}"
        elif self.op == "!":
            return f"{res} = !{a1}"
        elif self.op == "[]":
            return f"{res} = {a1}[{a2}]"
        elif self.op == "[]=":
            return f"{res}[{a2}] = {a1}"
        elif self.op == "return":
            return f"return {a1}" if a1 else "return"
        elif self.op == "print":
            return f"print {a1}"
        elif self.op == "read":
            return f"read {res or a1}"
        elif self.op == "param":
            return f"param {a1}"
        elif self.op == "call":
            return f"{res} = call {a1}, {a2}"
        else:
            return f"{res} = {self.op} {a1} {a2}".strip()

    def __str__(self):
        return self.to_ir_tuple()

    def __repr__(self):
        return f"Cuadruplo({self.numero}, {self.op!r}, {self.arg1!r}, {self.arg2!r}, {self.resultado!r})"



#  5. GENERADOR DE CÓDIGO INTERMEDIO (IR GENERATOR)


class IRGenerator:
    """
    Genera instrucciones intermedias (cuádruplos) a partir del AST de C++.
    
    """
    def __init__(self):
        self.instrucciones = []
        self.temp_count = 0
        self.label_count = 0
        self.postfijas = []

    def reset(self):
        self.instrucciones.clear()
        self.temp_count = 0
        self.label_count = 0
        self.postfijas.clear()

    def nuevo_temporal(self):
        """Genera temporales secuenciales t1, t2, t3..."""
        self.temp_count += 1
        return f"t{self.temp_count}"

    def nueva_etiqueta(self):
        """Genera etiquetas secuenciales L1, L2, L3..."""
        self.label_count += 1
        return f"L{self.label_count}"

    def emitir(self, op, arg1="", arg2="", resultado=""):
        """Agrega un nuevo cuádruplo numerado a la secuencia."""
        num = len(self.instrucciones) + 1
        c = Cuadruplo(num, op, arg1, arg2, resultado)
        self.instrucciones.append(c)
        return c

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
    
    def generar(self, codigo_o_ast):
        """
        Punto de entrada principal. Acepta una cadena con código fuente C++ o un nodo AST.
        Devuelve: (instrucciones, postfijas, texto_ir)
        """
        self.reset()
        if isinstance(codigo_o_ast, tuple):
            # Desenvolver si se pasa la tupla (codigo, parser, arbol_ast) de _parsear()
            codigo_o_ast = codigo_o_ast[2] if len(codigo_o_ast) >= 3 else codigo_o_ast[0]

        if isinstance(codigo_o_ast, str):
            lexer = LexerCPP(codigo_o_ast)
            tokens = lexer.tokenizar()
            parser = ParserCPP(tokens)
            ast = parser.parse()
        else:
            ast = codigo_o_ast

        if ast:
            self.visitar(ast)
        return self.instrucciones, self.postfijas, self.obtener_texto_ir()

    def obtener_texto_ir(self):
        """Retorna el código completo"""
        return "\n".join(inst.to_ir_tuple() for inst in self.instrucciones)

    def obtener_texto_3ac(self):
        """Retorna la representación equivalente en Código de Tres Direcciones."""
        return "\n".join(inst.to_3ac() for inst in self.instrucciones)

    
    # Patrón Visitor sobre el AST
    
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

        elif et in ("Declaración Local", "Varaible Global", "Variable Global"):
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
                var_dest = getattr(hijo, "valor", "x")
                self.emitir("read", "", "", var_dest)

        elif et in ("Assign", "BinOp", "UnOp", "PostIncDec", "Llamada", "Ternario"):
            self.registrar_postfija(nodo)
            self.visitar_expr(nodo)

        else:
            for hijo in getattr(nodo, "hijos", []):
                self.visitar(hijo)

    
    # Control de Flujo (if-else, while, for)
    
    def visitar_if(self, nodo):
        """
        Genera el patrón if / else:
          #1 (condición relacional, arg1, arg2, t1)
          #2 (IF_FALSE, t1, , L1)
          #3 ... rama then ...
          #4 (GOTO, , , L2)
          #5 (LABEL, , , L1)
          #6 ... rama else ...
          #7 (LABEL, , , L2)
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

        # 1. Evaluar la condición
        cond_res = self.visitar_expr(cond_nodo) if cond_nodo else "true"

        if else_nodo is not None:
            # Caso con rama else
            label_else = self.nueva_etiqueta()
            label_fin = self.nueva_etiqueta()

            self.emitir("IF_FALSE", cond_res, "", label_else)
            if then_nodo:
                self.visitar(then_nodo)
            self.emitir("GOTO", "", "", label_fin)
            self.emitir("LABEL", "", "", label_else)
            for h in else_nodo.hijos:
                self.visitar(h)
            self.emitir("LABEL", "", "", label_fin)
        else:
            # Caso if simple (sin else)
            label_fin = self.nueva_etiqueta()
            self.emitir("IF_FALSE", cond_res, "", label_fin)
            if then_nodo:
                self.visitar(then_nodo)
            self.emitir("LABEL", "", "", label_fin)

    def visitar_while(self, nodo):
        """
        Genera el ciclo while:
          L1:
          t1 = condición
          (IF_FALSE, t1, , L2)
          ... cuerpo ...
          (GOTO, , , L1)
          L2:
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

        self.emitir("LABEL", "", "", label_inicio)
        cond_res = self.visitar_expr(cond_nodo) if cond_nodo else "true"
        self.emitir("IF_FALSE", cond_res, "", label_fin)
        if cuerpo_nodo:
            self.visitar(cuerpo_nodo)
        self.emitir("GOTO", "", "", label_inicio)
        self.emitir("LABEL", "", "", label_fin)

    def visitar_for(self, nodo):
        """
        Genera el ciclo for:
          [inicialización]
          L_cond:
          t1 = condición
          (IF_FALSE, t1, , L_fin)
          [cuerpo]
          L_upd:
          [actualización]
          (GOTO, , , L_cond)
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

        if init_nodo:
            self.visitar_expr(init_nodo)

        label_cond = self.nueva_etiqueta()
        label_upd = self.nueva_etiqueta()
        label_fin = self.nueva_etiqueta()

        self.emitir("LABEL", "", "", label_cond)
        if cond_nodo:
            self.registrar_postfija(cond_nodo)
            cond_res = self.visitar_expr(cond_nodo)
            self.emitir("IF_FALSE", cond_res, "", label_fin)

        if cuerpo_nodo:
            self.visitar(cuerpo_nodo)

        self.emitir("LABEL", "", "", label_upd)
        if upd_nodo:
            self.visitar_expr(upd_nodo)

        self.emitir("GOTO", "", "", label_cond)
        self.emitir("LABEL", "", "", label_fin)

    # ------------------------------------------------------------------------
    # Expresiones Aritméticas, Lógicas y Asignaciones
    # ------------------------------------------------------------------------
    def visitar_expr(self, nodo):
        """
        Evalúa recursivamente un nodo de expresión en el AST y genera
        las cuádruplas necesarias, retornando el nombre del operando resultante
        (literal, identificador o temporal t1, t2...).
        """
        if nodo is None:
            return ""

        et = getattr(nodo, "etiqueta", "")
        val = getattr(nodo, "valor", "")
        hijos = getattr(nodo, "hijos", [])

        # Literales y variables simples
        if et in ("Num", "Id", "Bool", "Cadena"):
            return str(val)

        # Acceso a arreglos a[idx]
        elif et == "AccesoArreglo":
            idx = self.visitar_expr(hijos[0]) if hijos else "0"
            t = self.nuevo_temporal()
            self.emitir("[]", str(val), idx, t)
            return t

        # Operaciones Binarias (+, -, *, /, %, <, >, <=, >=, ==, !=, &&, ||)
        elif et == "BinOp":
            izq = self.visitar_expr(hijos[0]) if len(hijos) > 0 else ""
            der = self.visitar_expr(hijos[1]) if len(hijos) > 1 else ""
            t = self.nuevo_temporal()
            self.emitir(str(val), izq, der, t)
            return t

        # Operaciones Unarias (negación aritmética -, negación lógica !)
        elif et == "UnOp":
            operando = self.visitar_expr(hijos[0]) if len(hijos) > 0 else ""
            t = self.nuevo_temporal()
            op = "neg" if str(val) == "-" else str(val)
            self.emitir(op, operando, "", t)
            return t

        # Asignación (dest = expr)
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

        # Post-incremento o decremento (x++, x--)
        elif et == "PostIncDec":
            var_nom = getattr(hijos[0], "valor", "x") if hijos else "x"
            op_arit = "+" if str(val) == "++" else "-"
            t = self.nuevo_temporal()
            self.emitir(op_arit, var_nom, "1", t)
            self.emitir("=", t, "", var_nom)
            return var_nom

        # Operador Ternario (cond ? entonces : sino)
        elif et == "Ternario":
            cond_res = self.visitar_expr(hijos[0]) if len(hijos) > 0 else "true"
            l_else = self.nueva_etiqueta()
            l_fin = self.nueva_etiqueta()
            res_temp = self.nuevo_temporal()

            self.emitir("IF_FALSE", cond_res, "", l_else)
            then_res = self.visitar_expr(hijos[1]) if len(hijos) > 1 else ""
            self.emitir("=", then_res, "", res_temp)
            self.emitir("GOTO", "", "", l_fin)
            self.emitir("LABEL", "", "", l_else)
            else_res = self.visitar_expr(hijos[2]) if len(hijos) > 2 else ""
            self.emitir("=", else_res, "", res_temp)
            self.emitir("LABEL", "", "", l_fin)
            return res_temp

        # Llamada a funciones: func(arg1, arg2)
        elif et == "Llamada":
            args = [self.visitar_expr(h) for h in hijos]
            for a in args:
                self.emitir("param", a, "", "")
            t = self.nuevo_temporal()
            self.emitir("call", str(val), str(len(args)), t)
            return t

        elif hijos:
            return self.visitar_expr(hijos[0])

        return str(val)



#  6. FUNCIÓN FACADE DE GENERACIÓN COMPLETA


def generar_ir(codigo_o_ast):
    """
    Función de alto nivel que genera el código intermedio a partir de:
      - Una cadena con código fuente en C++ (ej. "x = 3 + 4 * 2;")
      - O directamente un nodo AST previamente construido.

    Retorna: (lista_instrucciones, lista_postfijas, texto_ir)
    """
    if isinstance(codigo_o_ast, str):
        lexer = LexerCPP(codigo_o_ast)
        tokens = lexer.tokenizar()
        parser = ParserCPP(tokens)
        ast = parser.parse()
    else:
        ast = codigo_o_ast

    generador = IRGenerator()
    return generador.generar(ast)

# ============================================================================
#  EJECUCIÓN DIRECTA
#  - Sin argumentos: Inicia la Interfaz Gráfica (GUI) para evaluación interactiva
#  - Con argumentos: Modo CLI para compilar archivos .cpp a .ir
# ============================================================================
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Iniciando la Interfaz Gráfica (GUI) del Compilador...")
        try:
            _raiz = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
            if _raiz not in sys.path:
                sys.path.insert(0, _raiz)
            import AnalisisSema
            root = AnalisisSema.tk.Tk()
            app = AnalisisSema.App(root)
            root.mainloop()
        except Exception as e:
            print(f"No se pudo iniciar el entorno gráfico ({e}). Mostrando demo en terminal:")
            demo_code = "int x = 3 + 4 * 2;"
            insts, posts, texto = generar_ir(demo_code)
            print("\n=== Formato .ir ===")
            print(texto)
            gen = IRGenerator()
            gen.generar(demo_code)
            print("\n=== Formato 3AC ===")
            print(gen.obtener_texto_3ac())
    else:
        fuente = sys.argv[1]
        salida = sys.argv[2] if len(sys.argv) > 2 else os.path.splitext(fuente)[0] + ".ir"
        try:
            with open(fuente, "r", encoding="utf-8") as f:
                codigo = f.read()
            insts, posts, texto = generar_ir(codigo)
            with open(salida, "w", encoding="utf-8") as f:
                f.write(texto + "\n")
            print(f"Código IR generado exitosamente en: {salida}")
            print(f"Total instrucciones generadas: {len(insts)}")
        except Exception as err:
            print(f"Error al procesar {fuente}: {err}")
            sys.exit(1)
