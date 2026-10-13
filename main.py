import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import re
import os
import sys

# Asegurar importación del paquete compilador.ir
_base_dir = os.path.dirname(os.path.abspath(__file__))
if _base_dir not in sys.path:
    sys.path.insert(0, _base_dir)

from compilador.ir.generator import IRGenerator, Cuadruplo, generar_ir
from compilador.opt import (
    BasicBlock, identificar_bloques_basicos, ControlFlowGraph,
    IROptimizer, CFGCanvas, OptimizationReport, optimizar_ir_completo
)

class Token:
    def __init__(self, type, value, pos_start, pos_end):
        self.type = type
        self.value = value
        self.pos_start = pos_start
        self.pos_end = pos_end

class NodoAST:
    def __init__(self, etiqueta, valor=""):
        self.etiqueta = etiqueta
        self.valor = valor
        self.hijos = []
        self.linea = None   # se rellena durante el parseo (para errores semánticos)
        self.tipo = None    # tipo de dato asociado (declaraciones, parámetros)

    def agregar_hijo(self, nodo_hijo):
        if nodo_hijo:
            self.hijos.append(nodo_hijo)
    

class Lexer:
    def __init__(self, code):
        self.code = code
        self.tokens = []
        
        # Reglas léxicas
        rules = [
            ('BLOQUE_COMENTARIO', r'/\*.*?\*/'),
            ('LINEA_COMENTARIO', r'//[^\n]*'),
            ('RESERVADA', r'\b(int|cout|cin|float|void|char|double|string|boolean|if|else|while|for|return|break|continue|true|false)\b'),
            ('NUMERO',   r'\d+(\.\d*)?'),
            ('IDENTIFICADOR',       r'[A-Za-z_][A-Za-z0-9_]*'),
            ('CADENA',   r'".*?"'),
            ('OP_INCREMENTO', r'\+\+|--'),
            ('OP_FLUJO',        r'<<|>>'),
            ('OP_RELACIONAL',   r'==|!=|<=|>=|<|>'),
            ('OP_LOGICO', r'&&|\|\||!'),
            ('OP_ARITMETICO',  r'[+\-*/%]'),
            ('ASIGNACION',    r'='),
            ('PARENTESIS_IZQ',   r'\('),
            ('PARENTESIS_DER',   r'\)'),
            ('LLAVE_IZQ',   r'\{'),
            ('LLAVE_DER',   r'\}'),
            ('CORCHETE_IZQ', r'\['),
            ('CORCHETE_DER', r'\]'),
            ('PUNTO_Y_COMA',     r';'),
            ('COMA',    r','),
            ('PUNTO',      r'\.'),
            ('TERNARIO',  r'\?|:'),
            ('ESPACIO',    r'[ \t\n]+'),
            ('NO_COINCIDE', r'.'),
        ]
        
        self.regex = re.compile('|'.join(f'(?P<{name}>{pattern})' for name, pattern in rules), re.DOTALL)
        
    def tokenize(self):
        self.tokens = []
        for match in self.regex.finditer(self.code):
            kind = match.lastgroup
            value = match.group()
            pos_start = match.start()
            pos_end = match.end()
            
            if kind == 'ESPACIO':
                continue
            elif kind == 'NO_COINCIDE':
                self.tokens.append(Token('ERROR', value, pos_start, pos_end))
                #aqui tambien necesito añadirlo a la lista para que lo muestre 
            else:
                self.tokens.append(Token(kind, value, pos_start, pos_end))
        return self.tokens

class ParseError:
    def __init__(self, message, pos_start, pos_end):
        self.message = message
        self.pos_start = pos_start
        self.pos_end = pos_end

    def __str__(self):
        return self.message


TIPOS_DATO = ['int', 'float', 'void', 'char', 'double', 'string', 'boolean']
VALUE_TOKEN_TYPES = ('IDENTIFICADOR', 'NUMERO', 'CADENA')
TIPOS_NUMERICOS = ('int', 'float')


# ============================================================================
#  ExprParser: mini parser de expresiones (precedencia de operadores) que
#  convierte una lista de tokens YA VALIDADA sintácticamente (viene de
#  scan_expression, que ya comprobó que no hay errores) en un árbol de
#  verdad: Assign, BinOp, UnOp, Id, Num, Bool, Cadena, Ternario, etc.
#  Este árbol es lo que consume después el analizador semántico.
# ============================================================================
class ExprParser:
    def __init__(self, tokens, line_of):
        self.tokens = tokens
        self.pos = 0
        self.line_of = line_of  # función pos -> número de línea

    def current(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def advance(self):
        tok = self.current()
        self.pos += 1
        return tok

    def parse(self):
        if not self.tokens:
            return None
        return self.parse_asignacion()

    def _nodo(self, etiqueta, valor, pos_ref):
        n = NodoAST(etiqueta, valor)
        n.linea = self.line_of(pos_ref)
        return n

    def parse_asignacion(self):
        izq = self.parse_ternario()
        tok = self.current()
        if tok and tok.type == 'ASIGNACION':
            self.advance()
            der = self.parse_asignacion()
            nodo = self._nodo("Assign", "=", tok.pos_start)
            nodo.agregar_hijo(izq)
            nodo.agregar_hijo(der)
            return nodo
        return izq

    def parse_ternario(self):
        cond = self.parse_or()
        tok = self.current()
        if tok and tok.type == 'TERNARIO' and tok.value == '?':
            self.advance()
            entonces = self.parse_asignacion()
            tok2 = self.current()
            if tok2 and tok2.type == 'TERNARIO' and tok2.value == ':':
                self.advance()
                sino = self.parse_asignacion()
                nodo = self._nodo("Ternario", "?:", tok.pos_start)
                nodo.agregar_hijo(cond)
                nodo.agregar_hijo(entonces)
                nodo.agregar_hijo(sino)
                return nodo
        return cond

    def parse_or(self):
        izq = self.parse_and()
        while self.current() and self.current().type == 'OP_LOGICO' and self.current().value == '||':
            tok = self.advance()
            der = self.parse_and()
            izq = self._binop(tok, izq, der)
        return izq

    def parse_and(self):
        izq = self.parse_igualdad()
        while self.current() and self.current().type == 'OP_LOGICO' and self.current().value == '&&':
            tok = self.advance()
            der = self.parse_igualdad()
            izq = self._binop(tok, izq, der)
        return izq

    def parse_igualdad(self):
        izq = self.parse_relacional()
        while self.current() and self.current().type == 'OP_RELACIONAL' and self.current().value in ('==', '!='):
            tok = self.advance()
            der = self.parse_relacional()
            izq = self._binop(tok, izq, der)
        return izq

    def parse_relacional(self):
        izq = self.parse_aditiva()
        while self.current() and self.current().type == 'OP_RELACIONAL' and self.current().value in ('<', '>', '<=', '>='):
            tok = self.advance()
            der = self.parse_aditiva()
            izq = self._binop(tok, izq, der)
        return izq

    def parse_aditiva(self):
        izq = self.parse_multiplicativa()
        while self.current() and self.current().type == 'OP_ARITMETICO' and self.current().value in ('+', '-'):
            tok = self.advance()
            der = self.parse_multiplicativa()
            izq = self._binop(tok, izq, der)
        return izq

    def parse_multiplicativa(self):
        izq = self.parse_unaria()
        while self.current() and self.current().type == 'OP_ARITMETICO' and self.current().value in ('*', '/', '%'):
            tok = self.advance()
            der = self.parse_unaria()
            izq = self._binop(tok, izq, der)
        return izq

    def parse_unaria(self):
        tok = self.current()
        if tok and ((tok.type == 'OP_LOGICO' and tok.value == '!') or (tok.type == 'OP_ARITMETICO' and tok.value == '-')):
            self.advance()
            operando = self.parse_unaria()
            nodo = self._nodo("UnOp", tok.value, tok.pos_start)
            nodo.agregar_hijo(operando)
            return nodo
        return self.parse_primaria()

    def parse_primaria(self):
        tok = self.current()
        if not tok:
            return None
        if tok.type == 'NUMERO':
            self.advance()
            return self._nodo("Num", tok.value, tok.pos_start)
        if tok.type == 'CADENA':
            self.advance()
            return self._nodo("Cadena", tok.value, tok.pos_start)
        if tok.type == 'RESERVADA' and tok.value in ('true', 'false'):
            self.advance()
            return self._nodo("Bool", tok.value, tok.pos_start)
        if tok.type == 'IDENTIFICADOR':
            self.advance()
            nodo = self._nodo("Id", tok.value, tok.pos_start)
            # acceso a arreglo: id[expr]
            if self.current() and self.current().type == 'CORCHETE_IZQ':
                self.advance()
                indice = self.parse_asignacion()
                if self.current() and self.current().type == 'CORCHETE_DER':
                    self.advance()
                acceso = self._nodo("AccesoArreglo", tok.value, tok.pos_start)
                acceso.agregar_hijo(indice)
                nodo = acceso
            # llamada a función: id(args)
            elif self.current() and self.current().type == 'PARENTESIS_IZQ':
                self.advance()
                llamada = self._nodo("Llamada", tok.value, tok.pos_start)
                while self.current() and self.current().type != 'PARENTESIS_DER':
                    arg = self.parse_asignacion()
                    if arg:
                        llamada.agregar_hijo(arg)
                    if self.current() and self.current().type == 'COMA':
                        self.advance()
                    else:
                        break
                if self.current() and self.current().type == 'PARENTESIS_DER':
                    self.advance()
                nodo = llamada
                
            if self.current() and self.current().type == 'OP_INCREMENTO':
                op_tok = self.advance()
                nodo_inc = self._nodo("PostIncDec", op_tok.value, op_tok.pos_start)
                nodo_inc.agregar_hijo(nodo)
                return nodo_inc

            return nodo
        if tok.type == 'PARENTESIS_IZQ':
            self.advance()
            interior = self.parse_asignacion()
            if self.current() and self.current().type == 'PARENTESIS_DER':
                self.advance()
            return interior
        # token que no encaja: lo saltamos sin tronar (no debería pasar si
        # scan_expression ya validó todo, pero por si acaso)
        self.advance()
        return self._nodo("ErrorExpr", tok.value, tok.pos_start)

    def _binop(self, tok, izq, der):
        nodo = self._nodo("BinOp", tok.value, tok.pos_start)
        nodo.agregar_hijo(izq)
        nodo.agregar_hijo(der)
        return nodo


class Parser:
    def __init__(self, tokens, source_code):
        self.tokens = [t for t in tokens if t.type not in ('BLOQUE_COMENTARIO', 'LINEA_COMENTARIO', 'ERROR')]
        self.source_code = source_code
        self.pos = 0
        self.errors = []  # aquí se acumulan TODOS los errores encontrados

    def current(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def advance(self):
        if self.pos < len(self.tokens):
            self.pos += 1

    def add_error(self, message, pos_start, pos_end):
        self.errors.append(ParseError(message, pos_start, pos_end))

    def line_of(self, pos):
        return self.source_code[:pos].count('\n') + 1

    def synchronize(self, sync_types=('PUNTO_Y_COMA',), stop_types=('LLAVE_DER',), consume_sync=True):
        while self.current() and self.current().type not in sync_types and self.current().type not in stop_types:
            self.advance()
        if self.current() and self.current().type in sync_types and consume_sync:
            self.advance()

    def is_value_token(self, tok):
        if tok is None:
            return False
        if tok.type in VALUE_TOKEN_TYPES:
            return True
        if tok.type == 'RESERVADA' and tok.value in ('true', 'false'):
            return True
        return False

    STOP_KEYWORDS = set(TIPOS_DATO) | {'if', 'else', 'while', 'for', 'return'}

    def scan_expression(self, stop_types=('PUNTO_Y_COMA',), also_stop_on_brace=True, also_stop_on_keyword=True):
       
        stops = set(stop_types)
        if also_stop_on_brace:
            stops.add('LLAVE_IZQ')

        parens = 0
        brackets = 0
        prev_value_end = None

        while self.current() and self.current().type not in stops:
            t = self.current()
            if also_stop_on_keyword and t.type == 'RESERVADA' and t.value in self.STOP_KEYWORDS:
                # nos topamos con el inicio de OTRA instrucción (return/if/while/
                # for/un tipo de dato) sin haber cerrado la actual con ';'
                break
            if t.type == 'PARENTESIS_IZQ':
                parens += 1
                prev_value_end = None
            elif t.type == 'PARENTESIS_DER':
                parens -= 1
                prev_value_end = t.pos_end  # el resultado "f(x)" puede actuar como un valor
            elif t.type == 'CORCHETE_IZQ':
                brackets += 1
                prev_value_end = None
            elif t.type == 'CORCHETE_DER':
                brackets -= 1
                prev_value_end = t.pos_end
            elif self.is_value_token(t):
                if prev_value_end is not None:
                    self.add_error(
                        f"Falta un operador antes de '{t.value}' "
                        f"(palabra reservada mal escrita o token de más).",
                        prev_value_end, t.pos_end)
                prev_value_end = t.pos_end
            else:
                # operador, coma, asignación, etc. -> reinicia la cadena de valores
                prev_value_end = None
            self.advance()

        stopped_by = self.current().type if self.current() else None
        return parens, brackets, stopped_by

    def parse_expr_tokens(self, tokens):
        """Convierte una lista de tokens (ya validada por scan_expression) en
        un árbol de expresión de verdad, usando ExprParser."""
        if not tokens:
            return None
        ep = ExprParser(tokens, self.line_of)
        nodo = ep.parse()
        if ep.pos < len(tokens):
            tok_sobrante = tokens[ep.pos]
            self.add_error(f"Sintaxis inválida cerca de '{tok_sobrante.value}'.", tok_sobrante.pos_start, tok_sobrante.pos_end)
            return NodoAST("ErrorExpr", "error")
        return nodo

    def _partir_por_flujo(self, tokens):
        """Divide una lista de tokens de 'cout << a << b' en sub-listas por cada '<<'."""
        partes = []
        actual = []
        for t in tokens:
            if t.type == 'OP_FLUJO':
                if actual:
                    partes.append(actual)
                    actual = []
            else:
                actual.append(t)
        if actual:
            partes.append(actual)
        return partes

    def parse(self):
        nodo_raiz = NodoAST("Programa")
        while self.pos < len(self.tokens):
            start_pos = self.pos
            nodo_hijo = self.parse_global()
            if nodo_hijo:
                nodo_raiz.agregar_hijo(nodo_hijo)
            # Salvaguarda anti-bucle-infinito: si un método no consumió ningún
            # token (p. ej. porque hubo un error raro), forzamos avanzar uno.
            if self.pos == start_pos:
                self.advance()
        return nodo_raiz

    def parse_global(self):

        tok = self.current()
        if not tok:
            return

        if tok.type == 'RESERVADA' and tok.value in TIPOS_DATO:
            tipo_dato = tok.value
            self.advance()  # consume tipo

            tok_id = self.current()
            if tok_id and tok_id.type == 'IDENTIFICADOR':
                nombre_id = tok_id.value
                self.advance()  # consume ID
            else:
                pos = tok.pos_end
                self.add_error("Se esperaba un identificador después del tipo de dato.", pos, pos + 1)
                self.synchronize()
                return

            tok_next = self.current()
            if tok_next and tok_next.type == 'PARENTESIS_IZQ':
                nodo_func = NodoAST("Función", nombre_id)
                nodo_func.tipo = tipo_dato  # tipo de retorno
                nodo_func.linea = self.line_of(tok.pos_start)
                # Función
                self.advance()  # consume '('
                params = self.parse_params()

                tok_close = self.current()
                if tok_close and tok_close.type == 'PARENTESIS_DER':
                    self.advance()  # consume ')'
                else:
                    pos = tok_next.pos_end
                    self.add_error("Falta cerrar el paréntesis ')' en los parámetros de la función.", pos, pos + 1)
                    # buscamos la llave que abre el cuerpo para seguir desde ahí
                    self.synchronize(sync_types=('LLAVE_IZQ',), stop_types=(), consume_sync=False)

                # Soporte para sintaxis clásica de C: declaraciones de tipos antes de la llave
                tipos_clasicos = self.parse_classical_decls()

                # Con los nombres capturados en '(...)' y los tipos de las
                # declaraciones clásicas "float x", armamos los nodos de
                # Parámetro para que el semántico los pueda declarar.
                for tipo_p, nombre_p, pos_p in params:
                    tipo_final = tipo_p or tipos_clasicos.get(nombre_p) or "desconocido"
                    nodo_param = NodoAST("Parámetro", nombre_p)
                    nodo_param.tipo = tipo_final
                    nodo_param.linea = self.line_of(pos_p)
                    nodo_func.agregar_hijo(nodo_param)

                tok_brace = self.current()
                if tok_brace and tok_brace.type == 'LLAVE_IZQ':
                    nodo_bloque = self.parse_block()
                    nodo_func.agregar_hijo(nodo_bloque)
                else:
                    pos = self.current().pos_start if self.current() else len(self.source_code)
                    self.add_error("Se esperaba '{' para iniciar el cuerpo de la función.", pos, pos + 1)
                    self.advance()
                return nodo_func
            else:
                nodo_var = NodoAST("Varaible Global", nombre_id)
                nodo_var.tipo = tipo_dato
                nodo_var.linea = self.line_of(tok.pos_start)
                # Declaración de variable global
                nodo_init = self.parse_var_tail()
                if nodo_init:
                    contenedor = NodoAST("Inicializador")
                    contenedor.agregar_hijo(nodo_init)
                    nodo_var.agregar_hijo(contenedor)
                return nodo_var
        else:
            return self.parse_statement()

    def parse_params(self):
        """Devuelve una lista de (tipo_o_None, nombre, posicion) por cada
        parámetro. Soporta tanto '(int x, int y)' como el estilo clásico
        '(x) int x' (donde aquí el tipo llega como None y se resuelve
        después con parse_classical_decls)."""
        params = []
        while self.current() and self.current().type != 'PARENTESIS_DER':
            tok = self.current()
            if tok.type == 'RESERVADA' and tok.value in TIPOS_DATO:
                tipo = tok.value
                self.advance()
                if self.current() and self.current().type == 'IDENTIFICADOR':
                    nombre_tok = self.current()
                    params.append((tipo, nombre_tok.value, nombre_tok.pos_start))
                    self.advance()
            elif tok.type == 'IDENTIFICADOR':
                params.append((None, tok.value, tok.pos_start))
                self.advance()
            else:
                self.advance()  # comas u otros separadores
        return params

    def parse_classical_decls(self):
        """Declaraciones de tipo estilo K&R antes de la '{' (ej. 'float x').
        Devuelve un diccionario {nombre: tipo}."""
        tipos_params = {}
        while self.current() and self.current().type != 'LLAVE_IZQ':
            tok = self.current()
            if tok.type == 'RESERVADA' and tok.value in TIPOS_DATO:
                tipo = tok.value
                self.advance()  # consume type
                if self.current() and self.current().type == 'IDENTIFICADOR':
                    tipos_params[self.current().value] = tipo
                while self.current() and self.current().type not in ['PUNTO_Y_COMA', 'LLAVE_IZQ']:
                    self.advance()

                if self.current() and self.current().type == 'PUNTO_Y_COMA':
                    self.advance()
            else:
                pos = tok.pos_start
                self.add_error(
                    "Se esperaba un tipo de dato válido o '{' (posible palabra reservada mal escrita "
                    "en la declaración de parámetros).",
                    pos, tok.pos_end)
                
                while self.current() and self.current().type not in ['PUNTO_Y_COMA', 'LLAVE_IZQ']:
                    self.advance()
                if self.current() and self.current().type == 'PUNTO_Y_COMA':
                    self.advance()
        return tipos_params

    def parse_var_tail(self):
        """Analiza lo que sigue a 'tipo nombre': puede ser sólo ';' o
        '= expresión ;'. Devuelve el nodo de la expresión inicializadora
        (o None si no hay inicializador)."""
        start_tok = self.tokens[self.pos - 1] if self.pos > 0 else None
        inicio_scan = self.pos
        parens, brackets, stopped_by = self.scan_expression(stop_types=('PUNTO_Y_COMA',))
        tokens_expr = self.tokens[inicio_scan:self.pos]
        nodo_init = None

        if stopped_by == 'PUNTO_Y_COMA':
            if tokens_expr and tokens_expr[0].type == 'ASIGNACION':
                if len(tokens_expr) == 1:
                    pos = tokens_expr[0].pos_start
                    self.add_error("falta expresión después de '='", pos, pos + 1)
                else:
                    nodo_init = self.parse_expr_tokens(tokens_expr[1:])
            self.advance()
        elif stopped_by == 'LLAVE_IZQ':
            pos = start_tok.pos_start if start_tok else self.current().pos_start
            self.add_error(
                "Se encontró '{' inesperado en una declaración; falta el punto y coma ';' o hay "
                "un error de escritura antes de este punto (revisa si algún tipo o palabra "
                "reservada está mal escrita).",
                pos, self.current().pos_start)
            self.parse_block()  # seguimos analizando el bloque para no perder errores de adentro
        elif stopped_by == 'RESERVADA':
            kw = self.current().value
            pos = start_tok.pos_start if start_tok else self.current().pos_start
            self.add_error(f"Falta punto y coma ';' antes de '{kw}'.", pos, self.current().pos_start)
        else:
            pos = start_tok.pos_start if start_tok else len(self.source_code)
            self.add_error("Falta punto y coma ';' al final de la declaración.", pos, pos + 1)

        return nodo_init

    def parse_block(self):
        nodo_bloque = NodoAST("Bloque")
        start_tok = self.current()
        self.advance()  # consume '{'

        while self.current() and self.current().type != 'LLAVE_DER':
            start_pos = self.pos
            nodo_instruccion = self.parse_statement()

            if nodo_instruccion:
                nodo_bloque.agregar_hijo(nodo_instruccion)
            if self.pos == start_pos:
                self.advance()

        if self.current() and self.current().type == 'LLAVE_DER':
            self.advance()
        else:
            pos = start_tok.pos_start
            self.add_error("Falta cerrar la llave '}' del bloque.", pos, pos + 1)
        return nodo_bloque

    def parse_condition(self):
        """Analiza '(expr)'. Devuelve el nodo de la expresión de la condición
        (o None si hubo un error de sintaxis)."""
        tok = self.current()
        if not (tok and tok.type == 'PARENTESIS_IZQ'):
            pos = tok.pos_start if tok else len(self.source_code)
            self.add_error("Se esperaba '(' para la condición.", pos, pos + 1)
            return None

        self.advance()  # consume '('
        inicio = self.pos
        parens = 1
        while self.current() and parens > 0:
            t = self.current()
            if t.type == 'PARENTESIS_IZQ':
                parens += 1
            elif t.type == 'PARENTESIS_DER':
                parens -= 1
                if parens == 0:
                    break
            self.advance()

        tokens_cond = self.tokens[inicio:self.pos]

        if parens > 0:
            self.add_error("Falta cerrar paréntesis ')' en la condición.", tok.pos_start, tok.pos_start + 1)
        else:
            self.advance()  # consume ')'

        return self.parse_expr_tokens(tokens_cond)

    def parse_statement(self):
        tok = self.current()
        if not tok:
            return None

        
        if tok.type == 'LLAVE_DER':
            self.add_error("Se encontró una llave de cierre '}' inesperada. ¿Olvidaste abrir '{'?", tok.pos_start, tok.pos_end)
            self.advance()
            return None # No construimos nodo para un error


        if tok.type == 'LLAVE_IZQ':
            return self.parse_block()
            
        elif tok.type == 'RESERVADA' and tok.value == 'if':
            nodo_if = NodoAST("Estructura de Control", "if")
            nodo_if.linea = self.line_of(tok.pos_start)
            self.advance()
            nodo_cond = self.parse_condition()
            if nodo_cond:
                contenedor = NodoAST("Condición")
                contenedor.agregar_hijo(nodo_cond)
                nodo_if.agregar_hijo(contenedor)

            nodo_cuerpo = self.parse_statement()
            if nodo_cuerpo: 
                nodo_if.agregar_hijo(nodo_cuerpo)
                
            if self.current() and self.current().type == 'RESERVADA' and self.current().value == 'else':
                nodo_else = NodoAST("Estructura de Control", "else")
                nodo_else.linea = self.line_of(self.current().pos_start)
                self.advance()
                nodo_cuerpo_else = self.parse_statement()
                if nodo_cuerpo_else: 
                    nodo_else.agregar_hijo(nodo_cuerpo_else)
                nodo_if.agregar_hijo(nodo_else)
                
            return nodo_if
            
        elif tok.type == 'RESERVADA' and tok.value in ['while', 'for']:
            es_for = (tok.value == 'for')
            nodo_ciclo = NodoAST("Ciclo", tok.value)
            nodo_ciclo.linea = self.line_of(tok.pos_start)
            self.advance()
            
            if not es_for:
                nodo_cond = self.parse_condition()
                if nodo_cond:
                    contenedor = NodoAST("Condición")
                    contenedor.agregar_hijo(nodo_cond)
                    nodo_ciclo.agregar_hijo(contenedor)
            else:
                tok_paren = self.current()
                if not (tok_paren and tok_paren.type == 'PARENTESIS_IZQ'):
                    pos = tok_paren.pos_start if tok_paren else len(self.source_code)
                    self.add_error("Se esperaba '(' para el ciclo for.", pos, pos + 1)
                else:
                    self.advance()
                    inicio = self.pos
                    parens = 1
                    while self.current() and parens > 0:
                        t = self.current()
                        if t.type == 'PARENTESIS_IZQ':
                            parens += 1
                        elif t.type == 'PARENTESIS_DER':
                            parens -= 1
                            if parens == 0:
                                break
                        self.advance()
                        
                    tokens_for = self.tokens[inicio:self.pos]
                    if parens > 0:
                        self.add_error("Falta cerrar paréntesis ')' en el for.", tok_paren.pos_start, tok_paren.pos_start + 1)
                    else:
                        self.advance()
                        
                    partes = []
                    actual = []
                    for t in tokens_for:
                        if t.type == 'PUNTO_Y_COMA':
                            partes.append(actual)
                            actual = []
                        else:
                            actual.append(t)
                    partes.append(actual)
                    
                    if len(partes) != 3:
                        self.add_error("La estructura del for debe tener 3 partes separadas por ';'.", tok_paren.pos_start, tok_paren.pos_end)
                    else:
                        nodo_init = self.parse_expr_tokens(partes[0])
                        nodo_cond = self.parse_expr_tokens(partes[1])
                        nodo_upd = self.parse_expr_tokens(partes[2])
                        
                        if nodo_init:
                            cont_init = NodoAST("Inicialización")
                            cont_init.agregar_hijo(nodo_init)
                            nodo_ciclo.agregar_hijo(cont_init)
                        if nodo_cond:
                            cont_cond = NodoAST("Condición")
                            cont_cond.agregar_hijo(nodo_cond)
                            nodo_ciclo.agregar_hijo(cont_cond)
                        if nodo_upd:
                            cont_upd = NodoAST("Actualización")
                            cont_upd.agregar_hijo(nodo_upd)
                            nodo_ciclo.agregar_hijo(cont_upd)

            nodo_cuerpo = self.parse_statement()
            if nodo_cuerpo: 
                nodo_ciclo.agregar_hijo(nodo_cuerpo)
                
            return nodo_ciclo
            
        elif tok.type == 'RESERVADA' and tok.value == 'return':
            nodo_ret = NodoAST("Instrucción", "return")
            nodo_ret.linea = self.line_of(tok.pos_start)
            self.advance()
            inicio_scan = self.pos
            parens, brackets, stopped_by = self.scan_expression(stop_types=('PUNTO_Y_COMA', 'LLAVE_DER'))
            tokens_expr = self.tokens[inicio_scan:self.pos]
            
            if stopped_by == 'PUNTO_Y_COMA':
                self.advance()
                nodo_valor = self.parse_expr_tokens(tokens_expr)
                if nodo_valor:
                    nodo_ret.agregar_hijo(nodo_valor)
            elif stopped_by == 'LLAVE_IZQ':
                pos = tok.pos_start
                self.add_error("Se encontró '{' inesperado dentro de la instrucción return; falta ';'.", pos, self.current().pos_start)
                self.parse_block()
            elif stopped_by == 'RESERVADA':
                kw = self.current().value
                pos = tok.pos_start
                self.add_error(f"Falta punto y coma ';' antes de '{kw}'.", pos, self.current().pos_start)
            else:
                pos = tok.pos_start
                self.add_error("Falta punto y coma ';' después del return.", pos, pos + 1)
                
            return nodo_ret
            
        
        elif tok.type == 'RESERVADA' and tok.value == 'cin':
            nodo_cin = NodoAST("Entrada por Consola", "cin")
            nodo_cin.linea = self.line_of(tok.pos_start)
            self.advance()
            
            inicio_scan = self.pos
            parens, brackets, stopped_by = self.scan_expression(stop_types=('PUNTO_Y_COMA', 'LLAVE_DER'))
            tokens_expr = self.tokens[inicio_scan:self.pos]
            
            if stopped_by == 'PUNTO_Y_COMA':
                self.advance()
                for parte in self._partir_por_flujo(tokens_expr):
                    nodo_parte = self.parse_expr_tokens(parte)
                    if nodo_parte:
                        nodo_cin.agregar_hijo(nodo_parte)
            else:
                self.add_error("Falta punto y coma ';' al final del cin.", tok.pos_start, tok.pos_end)
                
            return nodo_cin
            
        elif tok.type == 'RESERVADA' and tok.value == 'cout':
            nodo_cout = NodoAST("Salida por Consola", "cout")
            nodo_cout.linea = self.line_of(tok.pos_start)
            self.advance() # Consumimos la palabra cout
            
            inicio_scan = self.pos
            # Le pedimos que analice todo lo que sigue (los << y la cadena) hasta topar con un ;
            parens, brackets, stopped_by = self.scan_expression(stop_types=('PUNTO_Y_COMA', 'LLAVE_DER'))
            tokens_expr = self.tokens[inicio_scan:self.pos]
            
            if stopped_by == 'PUNTO_Y_COMA':
                self.advance() # Todo perfecto, consumimos el ;
                for parte in self._partir_por_flujo(tokens_expr):
                    nodo_parte = self.parse_expr_tokens(parte)
                    if nodo_parte:
                        nodo_cout.agregar_hijo(nodo_parte)
            else:
                self.add_error("Falta punto y coma ';' al final del cout.", tok.pos_start, tok.pos_end)
                
            return nodo_cout
            
        elif tok.type == 'RESERVADA' and tok.value in TIPOS_DATO:
            tipo_dato = tok.value
            linea_decl = self.line_of(tok.pos_start)
            self.advance()
            
            identificador = "desconocido"
            if self.current() and self.current().type == 'IDENTIFICADOR':
                identificador = self.current().value
                self.advance()  # FIX: antes no se consumía el identificador aquí
                
            nodo_var = NodoAST("Declaración Local", identificador)
            nodo_var.tipo = tipo_dato
            nodo_var.linea = linea_decl
            nodo_init = self.parse_var_tail()
            if nodo_init:
                contenedor = NodoAST("Inicializador")
                contenedor.agregar_hijo(nodo_init)
                nodo_var.agregar_hijo(contenedor)
            
            return nodo_var
            
        else:
            # Expresiones generales (como x = 5;)
            start_tok = tok
            inicio_scan = self.pos
            parens, brackets, stopped_by = self.scan_expression(stop_types=('PUNTO_Y_COMA', 'LLAVE_DER'))
            tokens_expr = self.tokens[inicio_scan:self.pos]
            nodo_expr = None

            if stopped_by == 'PUNTO_Y_COMA':
                if parens > 0:
                    self.add_error("Paréntesis sin cerrar '(' en la expresión.", start_tok.pos_start, start_tok.pos_end)
                elif parens < 0:
                    self.add_error("Paréntesis de más ')' en la expresión.", start_tok.pos_start, start_tok.pos_end)
                self.advance()
                if parens == 0:
                    nodo_expr = self.parse_expr_tokens(tokens_expr)
            elif stopped_by == 'LLAVE_IZQ':
                pos = start_tok.pos_start
                self.add_error("Se encontró '{' donde no se esperaba.", pos, self.current().pos_start)
                self.parse_block()
            elif stopped_by == 'RESERVADA':
                kw = self.current().value
                pos = start_tok.pos_start
                self.add_error(f"Falta punto y coma ';' antes de '{kw}'.", pos, self.current().pos_start)
            else:
                pos = start_tok.pos_start
                self.add_error("Falta punto y coma ';' al final de la instrucción.", pos, pos + 1)

            if nodo_expr is None:
                # hubo algún problema: dejamos un nodo "placeholder" para no
                # romper el árbol (el semántico no llegará a correr de
                # todos modos si parser.errors no está vacío)
                nodo_expr = NodoAST("Expresión", start_tok.value)
                nodo_expr.linea = self.line_of(start_tok.pos_start)
            return nodo_expr


# ============================================================================
#  Tabla de símbolos: pila de ámbitos (scopes). El tope de la pila es el
#  ámbito activo.
# ============================================================================
class SymbolTable:
    def __init__(self):
        self.scopes = [{}]
        self.scope_labels = ["global"]
        self.historial = []  # TODO lo declarado alguna vez, para mostrarlo en la tabla final

    def enter_scope(self, label):
        self.scopes.append({})
        self.scope_labels.append(label)

    def exit_scope(self):
        self.scopes.pop()
        self.scope_labels.pop()

    def scope_actual(self):
        return self.scope_labels[-1]

    def declare(self, nombre, tipo, linea):
        """Declara en el ámbito ACTUAL. Devuelve False si ya existía ahí
        mismo (redeclaración)."""
        ambito_actual = self.scopes[-1]
        if nombre in ambito_actual:
            return False
        info = {"nombre": nombre, "tipo": tipo, "ambito": self.scope_actual(), "linea": linea}
        ambito_actual[nombre] = info
        self.historial.append(info)
        return True

    def lookup(self, nombre):
        """Busca desde el ámbito más interno hacia afuera (insert/lookup)."""
        for ambito in reversed(self.scopes):
            if nombre in ambito:
                return ambito[nombre]
        return None


# ============================================================================
#  Analizador semántico: recorre el AST (patrón Visitor) y
#  valida: variables declaradas, redeclaraciones, y compatibilidad de tipos.
#  Los errores siguen el formato: "Error semántico línea N: motivo".
# ============================================================================
class SemanticAnalyzer:
    def __init__(self):
        self.tabla = SymbolTable()
        self.errores = []
        self.tipo_retorno_actual = None

    def error(self, linea, motivo):
        self.errores.append(f"Error semántico línea {linea}: {motivo}")

    def analizar(self, nodo_raiz):
        for hijo in nodo_raiz.hijos:
            self.visitar_global(hijo)
        return self.errores, self.tabla

    # -- nivel global ------------------------------------------------------
    def visitar_global(self, nodo):
        if nodo.etiqueta == "Función":
            self.visitar_funcion(nodo)
        elif nodo.etiqueta == "Varaible Global":
            self.visitar_decl(nodo)
        else:
            self.visitar_statement(nodo)

    def visitar_funcion(self, nodo):
        nombre = nodo.valor
        tipo_retorno = nodo.tipo
        linea = nodo.linea or 1
        bloque = None
        parametros = []
        for hijo in nodo.hijos:
            if hijo.etiqueta == "Parámetro":
                parametros.append(hijo)
            elif hijo.etiqueta == "Bloque":
                bloque = hijo

        ok = self.tabla.declare(nombre, f"función → {tipo_retorno}", linea)
        if not ok:
            self.error(linea, f"la función '{nombre}' ya fue declarada (redeclaración)")

        self.tabla.enter_scope(f"función {nombre}")
        for p in parametros:
            ok_p = self.tabla.declare(p.valor, p.tipo, p.linea or linea)
            if not ok_p:
                self.error(p.linea or linea, f"el parámetro '{p.valor}' ya fue declarado (redeclaración)")

        tipo_anterior = self.tipo_retorno_actual
        self.tipo_retorno_actual = tipo_retorno
        if bloque:
            # el cuerpo de la función COMPARTE el ámbito con sus parámetros
            # (no se abre un scope adicional para él)
            for hijo in bloque.hijos:
                self.visitar_statement(hijo)
        self.tipo_retorno_actual = tipo_anterior
        self.tabla.exit_scope()

    # -- sentencias ----------------------------------------------------------
    def visitar_bloque(self, nodo):
        self.tabla.enter_scope("bloque")
        for hijo in nodo.hijos:
            self.visitar_statement(hijo)
        self.tabla.exit_scope()

    def visitar_statement(self, nodo):
        if nodo is None:
            return
        et = nodo.etiqueta

        if et == "Declaración Local":
            self.visitar_decl(nodo)
        elif et == "Bloque":
            self.visitar_bloque(nodo)
        elif et in ("Estructura de Control", "Ciclo"):
            for hijo in nodo.hijos:
                if hijo.etiqueta == "Condición":
                    if hijo.hijos:
                        t = self.tipo_de(hijo.hijos[0])
                        if t is not None and t != 'bool':
                            self.error(hijo.hijos[0].linea or nodo.linea or 1,
                                       f"la condición debe ser de tipo bool, no {t}")
                else:
                    self.visitar_statement(hijo)
        elif et == "Instrucción":  # return
            linea = nodo.linea or 1
            if nodo.hijos:
                if self.tipo_retorno_actual == 'void':
                    self.error(linea, f"una función void no puede devolver un valor")
                else:
                    t = self.tipo_de(nodo.hijos[0])
                    if (t is not None and self.tipo_retorno_actual
                            and t != self.tipo_retorno_actual
                            and not (t in TIPOS_NUMERICOS and self.tipo_retorno_actual in TIPOS_NUMERICOS)):
                        self.error(linea, f"el valor de return es {t} pero la función devuelve {self.tipo_retorno_actual}")
            elif self.tipo_retorno_actual and self.tipo_retorno_actual != 'void':
                self.error(linea, f"falta un valor de return para una función que devuelve {self.tipo_retorno_actual}")
        elif et == "Entrada por Consola":
            for hijo in nodo.hijos:
                tipo = self.tipo_de(hijo)
                if hijo.etiqueta not in ("Id", "AccesoArreglo"):
                    self.error(hijo.linea or nodo.linea or 1, "cin solo puede leer en variables o accesos a arreglos")
        elif et == "Salida por Consola":
            for hijo in nodo.hijos:
                self.tipo_de(hijo)
        elif et in ("Inicialización", "Actualización"):
            for h in nodo.hijos:
                self.tipo_de(h)
        elif et in ("Assign", "BinOp", "UnOp", "Id", "Num", "Bool", "Cadena",
                    "Ternario", "AccesoArreglo", "Llamada", "PostIncDec"):
            # sentencia-expresión, p. ej. "x = 5;"
            self.tipo_de(nodo)
        # cualquier otra etiqueta (p. ej. "Expresión" placeholder, "ErrorExpr") se ignora

    def visitar_decl(self, nodo):
        tipo = nodo.tipo
        nombre = nodo.valor
        linea = nodo.linea or 1
        ok = self.tabla.declare(nombre, tipo, linea)
        if not ok:
            self.error(linea, f"variable '{nombre}' ya fue declarada (redeclaración)")

        for hijo in nodo.hijos:
            if hijo.etiqueta == "Inicializador" and hijo.hijos:
                tipo_expr = self.tipo_de(hijo.hijos[0])
                if tipo_expr is not None and tipo is not None and tipo_expr != tipo \
                        and not (tipo_expr in TIPOS_NUMERICOS and tipo in TIPOS_NUMERICOS):
                    self.error(linea, f"no se puede asignar {tipo_expr} a {tipo}")

    # -- expresiones (calcula Y valida el tipo) ------------------------------
    def tipo_de(self, nodo):
        if nodo is None:
            return None
        et = nodo.etiqueta
        linea = nodo.linea or 1

        if et == "Num":
            return "float" if '.' in nodo.valor else "int"
        if et == "Bool":
            return "bool"
        if et == "Cadena":
            return "string"

        if et == "Id":
            info = self.tabla.lookup(nodo.valor)
            if info is None:
                self.error(linea, f"variable '{nodo.valor}' no declarada")
                return None
            return info["tipo"]

        if et == "AccesoArreglo":
            info = self.tabla.lookup(nodo.valor)
            if nodo.hijos:
                self.tipo_de(nodo.hijos[0])
            if info is None:
                self.error(linea, f"variable '{nodo.valor}' no declarada")
                return None
            return info["tipo"]

        if et == "Llamada":
            info = self.tabla.lookup(nodo.valor)
            if info is None:
                self.error(linea, f"función '{nodo.valor}' no declarada")
            for arg in nodo.hijos:
                self.tipo_de(arg)
            if info and isinstance(info["tipo"], str) and info["tipo"].startswith("función"):
                return info["tipo"].split("→")[-1].strip()
            return None

        if et == "UnOp":
            if len(nodo.hijos) < 1:
                return None
            tipo_operando = self.tipo_de(nodo.hijos[0])
            if tipo_operando is None:
                return None
            if nodo.valor == '!' and tipo_operando != 'bool':
                self.error(linea, f"el operador '!' solo aplica a bool, no a {tipo_operando}")
                return None
            if nodo.valor == '-' and tipo_operando not in TIPOS_NUMERICOS:
                self.error(linea, f"el operador '-' unario solo aplica a int/float, no a {tipo_operando}")
                return None
            return tipo_operando

        if et == "BinOp":
            if len(nodo.hijos) < 2:
                return None
            izq = self.tipo_de(nodo.hijos[0])
            der = self.tipo_de(nodo.hijos[1])
            if izq is None or der is None:
                return None
            op = nodo.valor
            if op in ('+', '-', '*', '/', '%'):
                if izq in TIPOS_NUMERICOS and der in TIPOS_NUMERICOS and izq == der:
                    return izq
                if izq == 'bool' or der == 'bool':
                    self.error(linea, f"el operador '{op}' no aplica a bool")
                else:
                    self.error(linea, f"el operador '{op}' no aplica a {izq} y {der}")
                return None
            if op in ('<', '>', '<=', '>='):
                if izq in TIPOS_NUMERICOS and der in TIPOS_NUMERICOS and izq == der:
                    return "bool"
                self.error(linea, f"el operador '{op}' no aplica a {izq} y {der}")
                return None
            if op in ('==', '!='):
                if izq == der or (izq in TIPOS_NUMERICOS and der in TIPOS_NUMERICOS):
                    return "bool"
                self.error(linea, f"el operador '{op}' no aplica a {izq} y {der}")
                return None
            if op in ('&&', '||'):
                if izq == 'bool' and der == 'bool':
                    return 'bool'
                self.error(linea, f"el operador '{op}' solo aplica a bool, no a {izq} y {der}")
                return None
            return None

        if et == "Ternario":
            if len(nodo.hijos) < 3:
                return None
            tipo_cond = self.tipo_de(nodo.hijos[0])
            tipo_si = self.tipo_de(nodo.hijos[1])
            tipo_no = self.tipo_de(nodo.hijos[2])
            if tipo_cond is not None and tipo_cond != 'bool':
                self.error(linea, f"la condición del operador ternario debe ser bool, no {tipo_cond}")
            if tipo_si is None or tipo_no is None:
                return None
            if tipo_si == tipo_no:
                return tipo_si
            if tipo_si in TIPOS_NUMERICOS and tipo_no in TIPOS_NUMERICOS:
                return "float"  # promoción numérica implícita entre int y float
            self.error(linea, f"las dos ramas del operador ternario tienen tipos incompatibles ({tipo_si} vs {tipo_no})")
            return None

        if et == "Assign":
            if len(nodo.hijos) < 2:
                self.error(linea, "expresión incompleta en asignación")
                return None
            nodo_izq = nodo.hijos[0]
            tipo_der = self.tipo_de(nodo.hijos[1])
            tipo_izq = self.tipo_de(nodo_izq)
            if tipo_izq is None or tipo_der is None:
                return None
            if tipo_izq != tipo_der and not (tipo_izq in TIPOS_NUMERICOS and tipo_der in TIPOS_NUMERICOS):
                self.error(linea, f"no se puede asignar {tipo_der} a {tipo_izq}")
                return None
            return tipo_izq

        if et == "PostIncDec":
            tipo_operando = self.tipo_de(nodo.hijos[0])
            if tipo_operando is None:
                return None
            if tipo_operando not in TIPOS_NUMERICOS:
                self.error(linea, f"el operador '{nodo.valor}' solo aplica a tipos numéricos, no a {tipo_operando}")
                return None
            return tipo_operando

        return None


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Compilador C++ | Léxico, Sintáctico, Semántico y Código Intermedio (IR)")
        self.root.geometry("980x740")
        self.root.minsize(800, 600)

        self.ultimo_ast = None  # guardamos el último árbol generado para poder verlo cuando el usuario quiera
        self.ultimo_optimizador = None  # último optimizador ejecutado (Unidad 3)
        self.ultimo_cfg_vista = "original"  # vista actual de CFG: 'original' o 'optimizado'
        
        # Frame superior para el editor de código
        top_frame = tk.Frame(self.root)
        top_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        header_editor = tk.Frame(top_frame)
        header_editor.pack(fill=tk.X, pady=(0, 5))

        tk.Label(header_editor, text="Código Fuente (C++):", font=("Arial", 11, "bold"), fg="#1A237E").pack(side=tk.LEFT)

        # Diccionario de ejemplos para evaluación rápida
        self.ejemplos = {
            "1. Aritmética básica (x = 3 + 4 * 2;)": "int x = 3 + 4 * 2;",
            "2. Precedencia con resta (y = 8 - 2 * 3;)": "y = 8 - 2 * 3;",
            "3. Paréntesis modifican precedencia ((8 - 2) * 3)": "res = (8 - 2) * 3;",
            "4. Condicional (if - else)": "if (a > b) {\n    x = 1;\n} else {\n    x = 2;\n}",
            "5. Ciclo While": "while (x < 10) {\n    x = x + 1;\n}",
            "6. Ciclo For con salida": "for (i = 0; i < 5; i = i + 1) {\n    cout << i;\n}",
            "7. Operador Ternario": "res = (x > 0) ? 10 : 20;",
            "8. Función con retorno": "int suma(int a, int b) {\n    return a + b;\n}",
            "9. Ejemplo original (cuadradoLimitado)": """float cuadradoLimitado(x) float x {\n    /* devuelve x al cuadrado, pero nunca más de 100 */\n    return (x<=-10.0||x>=10.0)?100:x*x;\n}""",
            "10. Optimización CFG (Integrador U3)": """int a = 5;
int b = 10;
int t1 = a + b;
int t2 = a + b;
int x;
if (t1 > 10) {
    x = 1;
} else {
    x = 0;
}
int y = x;
int z = 20 + 30;
int w = 100;
return y;
w = 200;""",
            "11. Plegado y Subexpresiones (CSE)": """int a = 2 + 3;
int b = 4 * 5;
int c = a + b;
int d = a + b;
int e = c * 2;""",
            "12. Control de Flujo y Código Inalcanzable": """int x = 10;
if (x > 5) {
    y = 100;
} else {
    y = 200;
}
return y;
y = 999;"""
        }

        tk.Label(header_editor, text="Cargar caso de prueba:", font=("Arial", 10), fg="#555").pack(side=tk.RIGHT, padx=(5, 5))
        self.combo_ejemplos = ttk.Combobox(header_editor, values=list(self.ejemplos.keys()), state="readonly", width=38)
        self.combo_ejemplos.pack(side=tk.RIGHT)
        self.combo_ejemplos.set("1. Aritmética básica (x = 3 + 4 * 2;)")
        self.combo_ejemplos.bind("<<ComboboxSelected>>", self.cargar_ejemplo_seleccionado)
        
        self.text_area = tk.Text(top_frame, height=13, font=("Consolas", 12))
        self.text_area.pack(fill=tk.BOTH, expand=True)
        self.text_area.tag_configure("error", background="red", foreground="white")
        
        # Cargar ejemplo por defecto
        self.text_area.insert(tk.END, self.ejemplos["1. Aritmética básica (x = 3 + 4 * 2;)"])
        
        # Frame intermedio para los botones
        mid_frame = tk.Frame(self.root)
        mid_frame.pack(fill=tk.X, padx=10, pady=5)
        
        btn_lexico = tk.Button(mid_frame, text="Análisis Léxico", command=self.analisis_lexico, bg="#4CAF50", fg="white", font=("Arial", 10, "bold"))
        btn_lexico.pack(side=tk.LEFT, padx=4)
        
        btn_sintactico = tk.Button(mid_frame, text="Análisis Sintáctico", command=self.analisis_sintactico, bg="#2196F3", fg="white", font=("Arial", 10, "bold"))
        btn_sintactico.pack(side=tk.LEFT, padx=4)

        btn_semantico = tk.Button(mid_frame, text="Análisis Semántico", command=self.analisis_semantico, bg="#FF9800", fg="white", font=("Arial", 10, "bold"))
        btn_semantico.pack(side=tk.LEFT, padx=4)

        self.btn_arbol = tk.Button(mid_frame, text="Ver AST", command=self.ver_arbol_sintactico,
                                    bg="#9C27B0", fg="white", font=("Arial", 10, "bold"), state=tk.DISABLED)
        self.btn_arbol.pack(side=tk.LEFT, padx=4)

        btn_ir = tk.Button(mid_frame, text="Código Intermedio (IR)", command=self.analisis_codigo_intermedio,
                           bg="#673AB7", fg="white", font=("Arial", 10, "bold"))
        btn_ir.pack(side=tk.LEFT, padx=4)

        btn_opt = tk.Button(mid_frame, text="Optimización (CFG / IR)", command=self.analisis_optimizacion,
                            bg="#E91E63", fg="white", font=("Arial", 10, "bold"))
        btn_opt.pack(side=tk.LEFT, padx=4)
        
        # Frame inferior: Notebook con pestañas de resultados integrados
        bottom_frame = tk.Frame(self.root)
        bottom_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.main_notebook = ttk.Notebook(bottom_frame)
        self.main_notebook.pack(fill=tk.BOTH, expand=True)

        # --- Pestaña 1: Tokens Léxicos ---
        self.tab_tokens = ttk.Frame(self.main_notebook)
        self.main_notebook.add(self.tab_tokens, text=" 📋 Tokens Léxicos ")

        columns = ("Lexema", "Token", "Posición")
        self.tree = ttk.Treeview(self.tab_tokens, columns=columns, show="headings")
        self.tree.heading("Lexema", text="Lexema")
        self.tree.heading("Token", text="Token (Tipo)")
        self.tree.heading("Posición", text="Posición (Inicio - Fin)")
        self.tree.column("Lexema", width=180)
        self.tree.column("Token", width=180)
        self.tree.column("Posición", width=120)
        self.tree.tag_configure("error_lexico", background="#ffcccc", foreground="red")

        scroll_tree_y = ttk.Scrollbar(self.tab_tokens, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll_tree_y.set)
        scroll_tree_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.pack(fill=tk.BOTH, expand=True)

        # --- Pestaña 2: Cuádruplos (Código Intermedio) ---
        self.tab_cuads = ttk.Frame(self.main_notebook)
        self.main_notebook.add(self.tab_cuads, text=" ⚡ Cuádruplos (IR) ")

        cols_cuad = ("#", "Operador", "Argumento 1", "Argumento 2", "Resultado / Destino")
        self.tv_main_cuads = ttk.Treeview(self.tab_cuads, columns=cols_cuad, show="headings")
        for c in cols_cuad:
            self.tv_main_cuads.heading(c, text=c)
        self.tv_main_cuads.column("#", width=60, anchor="center")
        self.tv_main_cuads.column("Operador", width=120, anchor="center")
        self.tv_main_cuads.column("Argumento 1", width=150, anchor="center")
        self.tv_main_cuads.column("Argumento 2", width=150, anchor="center")
        self.tv_main_cuads.column("Resultado / Destino", width=180, anchor="center")

        scroll_cuads_y = ttk.Scrollbar(self.tab_cuads, orient=tk.VERTICAL, command=self.tv_main_cuads.yview)
        self.tv_main_cuads.configure(yscrollcommand=scroll_cuads_y.set)
        scroll_cuads_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.tv_main_cuads.pack(fill=tk.BOTH, expand=True)

        # --- Pestaña 3: Tres Direcciones (3AC) ---
        self.tab_3ac = ttk.Frame(self.main_notebook)
        self.main_notebook.add(self.tab_3ac, text=" 🔤 Tres Direcciones (3AC) ")
        
        scroll_3ac_y = ttk.Scrollbar(self.tab_3ac)
        scroll_3ac_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.txt_main_3ac = tk.Text(self.tab_3ac, font=("Consolas", 11), yscrollcommand=scroll_3ac_y.set, bg="#FAFAFA")
        self.txt_main_3ac.pack(fill=tk.BOTH, expand=True)
        scroll_3ac_y.config(command=self.txt_main_3ac.yview)

        # --- Pestaña 4: Notación Postfija (RPN) ---
        self.tab_post = ttk.Frame(self.main_notebook)
        self.main_notebook.add(self.tab_post, text=" 🏷️ Notación Postfija ")

        cols_post = ("Línea", "Expresión Infija", "Notación Postfija (RPN)")
        self.tv_main_post = ttk.Treeview(self.tab_post, columns=cols_post, show="headings")
        for c in cols_post:
            self.tv_main_post.heading(c, text=c)
        self.tv_main_post.column("Línea", width=60, anchor="center")
        self.tv_main_post.column("Expresión Infija", width=280, anchor="w")
        self.tv_main_post.column("Notación Postfija (RPN)", width=350, anchor="w")

        scroll_post_y = ttk.Scrollbar(self.tab_post, orient=tk.VERTICAL, command=self.tv_main_post.yview)
        self.tv_main_post.configure(yscrollcommand=scroll_post_y.set)
        scroll_post_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.tv_main_post.pack(fill=tk.BOTH, expand=True)

        # --- Pestaña 5: Tabla de Símbolos ---
        self.tab_simbolos = ttk.Frame(self.main_notebook)
        self.main_notebook.add(self.tab_simbolos, text=" 📊 Tabla de Símbolos ")

        cols_simb = ("Nombre", "Tipo", "Ámbito", "Línea")
        self.tv_main_simbolos = ttk.Treeview(self.tab_simbolos, columns=cols_simb, show="headings")
        for c in cols_simb:
            self.tv_main_simbolos.heading(c, text=c)
            self.tv_main_simbolos.column(c, width=80 if c == "Línea" else 160)

        scroll_simb_y = ttk.Scrollbar(self.tab_simbolos, orient=tk.VERTICAL, command=self.tv_main_simbolos.yview)
        self.tv_main_simbolos.configure(yscrollcommand=scroll_simb_y.set)
        scroll_simb_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.tv_main_simbolos.pack(fill=tk.BOTH, expand=True)

        # --- Pestaña 6: Bloques Básicos (BB) ---
        self.tab_bb = ttk.Frame(self.main_notebook)
        self.main_notebook.add(self.tab_bb, text=" 🧱 Bloques Básicos ")

        cols_bb = ("Bloque", "Etiqueta", "Instrucciones (3AC)", "Estado")
        self.tv_main_bb = ttk.Treeview(self.tab_bb, columns=cols_bb, show="headings")
        self.tv_main_bb.heading("Bloque", text="Bloque (BB)")
        self.tv_main_bb.heading("Etiqueta", text="Etiqueta Líder")
        self.tv_main_bb.heading("Instrucciones (3AC)", text="Instrucciones Contenidas")
        self.tv_main_bb.heading("Estado", text="Alcanzabilidad / Tipo")
        self.tv_main_bb.column("Bloque", width=100, anchor="center")
        self.tv_main_bb.column("Etiqueta", width=120, anchor="center")
        self.tv_main_bb.column("Instrucciones (3AC)", width=480, anchor="w")
        self.tv_main_bb.column("Estado", width=160, anchor="center")

        scroll_bb_y = ttk.Scrollbar(self.tab_bb, orient=tk.VERTICAL, command=self.tv_main_bb.yview)
        self.tv_main_bb.configure(yscrollcommand=scroll_bb_y.set)
        scroll_bb_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.tv_main_bb.pack(fill=tk.BOTH, expand=True)

        # --- Pestaña 7: Grafo de Flujo de Control (CFG / GFG) ---
        self.tab_cfg = ttk.Frame(self.main_notebook)
        self.main_notebook.add(self.tab_cfg, text=" 🕸️ Grafo de Flujo (CFG) ")

        cfg_ctrl_frame = tk.Frame(self.tab_cfg, bg="#EEEEEE", pady=4, padx=8)
        cfg_ctrl_frame.pack(fill=tk.X)

        self.btn_toggle_cfg_orig = tk.Button(
            cfg_ctrl_frame, text="🔵 Ver CFG Original",
            command=lambda: self._conmutar_vista_cfg("original"),
            bg="#1565C0", fg="white", font=("Arial", 9, "bold"), padx=8
        )
        self.btn_toggle_cfg_orig.pack(side=tk.LEFT, padx=3)

        self.btn_toggle_cfg_opt = tk.Button(
            cfg_ctrl_frame, text="🟢 Ver CFG Optimizado",
            command=lambda: self._conmutar_vista_cfg("optimizado"),
            bg="#2E7D32", fg="white", font=("Arial", 9, "bold"), padx=8
        )
        self.btn_toggle_cfg_opt.pack(side=tk.LEFT, padx=3)

        self.lbl_cfg_estado = tk.Label(
            cfg_ctrl_frame, text="Mostrando: CFG Original",
            font=("Arial", 9, "italic"), bg="#EEEEEE", fg="#333"
        )
        self.lbl_cfg_estado.pack(side=tk.LEFT, padx=12)

        self.main_cfg_canvas = CFGCanvas(self.tab_cfg)
        self.main_cfg_canvas.pack(fill=tk.BOTH, expand=True)

        # --- Pestaña 8: Tabla de Sucesores ---
        self.tab_sucesores = ttk.Frame(self.main_notebook)
        self.main_notebook.add(self.tab_sucesores, text=" 📑 Tabla de Sucesores ")

        cols_suc = ("Bloque", "Sucesores en el Grafo", "Condición / Flujo")
        self.tv_main_sucesores = ttk.Treeview(self.tab_sucesores, columns=cols_suc, show="headings")
        self.tv_main_sucesores.heading("Bloque", text="Bloque")
        self.tv_main_sucesores.heading("Sucesores en el Grafo", text="Sucesores Directos")
        self.tv_main_sucesores.heading("Condición / Flujo", text="Estado de Ejecución")
        self.tv_main_sucesores.column("Bloque", width=140, anchor="center")
        self.tv_main_sucesores.column("Sucesores en el Grafo", width=350, anchor="w")
        self.tv_main_sucesores.column("Condición / Flujo", width=220, anchor="center")

        scroll_suc_y = ttk.Scrollbar(self.tab_sucesores, orient=tk.VERTICAL, command=self.tv_main_sucesores.yview)
        self.tv_main_sucesores.configure(yscrollcommand=scroll_suc_y.set)
        scroll_suc_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.tv_main_sucesores.pack(fill=tk.BOTH, expand=True)

        # --- Pestaña 9: IR Optimizado ---
        self.tab_ir_opt = ttk.Frame(self.main_notebook)
        self.main_notebook.add(self.tab_ir_opt, text=" ✨ IR Optimizado ")

        sub_nb_opt = ttk.Notebook(self.tab_ir_opt)
        sub_nb_opt.pack(fill=tk.BOTH, expand=True)

        # Subpestaña 9.1: Cuádruplos Optimizados
        tab_opt_cuads = ttk.Frame(sub_nb_opt)
        sub_nb_opt.add(tab_opt_cuads, text=" Cuádruplos Optimizados ")
        self.tv_main_opt_cuads = ttk.Treeview(tab_opt_cuads, columns=cols_cuad, show="headings")
        for c in cols_cuad:
            self.tv_main_opt_cuads.heading(c, text=c)
        self.tv_main_opt_cuads.column("#", width=60, anchor="center")
        self.tv_main_opt_cuads.column("Operador", width=120, anchor="center")
        self.tv_main_opt_cuads.column("Argumento 1", width=150, anchor="center")
        self.tv_main_opt_cuads.column("Argumento 2", width=150, anchor="center")
        self.tv_main_opt_cuads.column("Resultado / Destino", width=180, anchor="center")
        scroll_opt_c_y = ttk.Scrollbar(tab_opt_cuads, orient=tk.VERTICAL, command=self.tv_main_opt_cuads.yview)
        self.tv_main_opt_cuads.configure(yscrollcommand=scroll_opt_c_y.set)
        scroll_opt_c_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.tv_main_opt_cuads.pack(fill=tk.BOTH, expand=True)

        # Subpestaña 9.2: 3AC Optimizado
        tab_opt_3ac = ttk.Frame(sub_nb_opt)
        sub_nb_opt.add(tab_opt_3ac, text=" 3AC Optimizado ")
        scroll_opt_3ac = ttk.Scrollbar(tab_opt_3ac)
        scroll_opt_3ac.pack(side=tk.RIGHT, fill=tk.Y)
        self.txt_main_opt_3ac = tk.Text(tab_opt_3ac, font=("Consolas", 11), yscrollcommand=scroll_opt_3ac.set, bg="#F9FBE7")
        self.txt_main_opt_3ac.pack(fill=tk.BOTH, expand=True)
        scroll_opt_3ac.config(command=self.txt_main_opt_3ac.yview)

        # Subpestaña 9.3: Comparativa Lado a Lado (Antes vs Después)
        tab_opt_diff = ttk.Frame(sub_nb_opt)
        sub_nb_opt.add(tab_opt_diff, text=" Comparativa (Antes vs Después) ")
        scroll_opt_diff = ttk.Scrollbar(tab_opt_diff)
        scroll_opt_diff.pack(side=tk.RIGHT, fill=tk.Y)
        self.txt_main_diff = tk.Text(tab_opt_diff, font=("Consolas", 10), yscrollcommand=scroll_opt_diff.set, bg="#FAFAFA")
        self.txt_main_diff.pack(fill=tk.BOTH, expand=True)
        scroll_opt_diff.config(command=self.txt_main_diff.yview)

        # --- Pestaña 10: Tabla de Transformaciones ---
        self.tab_transf = ttk.Frame(self.main_notebook)
        self.main_notebook.add(self.tab_transf, text=" 📋 Tabla de Transformaciones ")

        cols_transf = ("#", "Bloque", "Técnica Aplicada", "Código Original", "Código Optimizado", "Justificación Técnica")
        self.tv_main_transf = ttk.Treeview(self.tab_transf, columns=cols_transf, show="headings")
        for c in cols_transf:
            self.tv_main_transf.heading(c, text=c)
        self.tv_main_transf.column("#", width=45, anchor="center")
        self.tv_main_transf.column("Bloque", width=80, anchor="center")
        self.tv_main_transf.column("Técnica Aplicada", width=220, anchor="w")
        self.tv_main_transf.column("Código Original", width=180, anchor="w")
        self.tv_main_transf.column("Código Optimizado", width=160, anchor="w")
        self.tv_main_transf.column("Justificación Técnica", width=280, anchor="w")

        scroll_transf_y = ttk.Scrollbar(self.tab_transf, orient=tk.VERTICAL, command=self.tv_main_transf.yview)
        scroll_transf_x = ttk.Scrollbar(self.tab_transf, orient=tk.HORIZONTAL, command=self.tv_main_transf.xview)
        self.tv_main_transf.configure(yscrollcommand=scroll_transf_y.set, xscrollcommand=scroll_transf_x.set)
        scroll_transf_y.pack(side=tk.RIGHT, fill=tk.Y)
        scroll_transf_x.pack(side=tk.BOTTOM, fill=tk.X)
        self.tv_main_transf.pack(fill=tk.BOTH, expand=True)

        # --- Pestaña 11: Métricas y Análisis ---
        self.tab_metricas = ttk.Frame(self.main_notebook)
        self.main_notebook.add(self.tab_metricas, text=" 📈 Métricas y Análisis ")

        scroll_met_y = ttk.Scrollbar(self.tab_metricas)
        scroll_met_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.txt_main_metricas = tk.Text(self.tab_metricas, font=("Consolas", 10), yscrollcommand=scroll_met_y.set, bg="#FFFFFF")
        self.txt_main_metricas.pack(fill=tk.BOTH, expand=True)
        scroll_met_y.config(command=self.txt_main_metricas.yview)

    def cargar_ejemplo_seleccionado(self, event=None):
        clave = self.combo_ejemplos.get()
        if clave in self.ejemplos:
            self.text_area.delete("1.0", tk.END)
            self.text_area.insert(tk.END, self.ejemplos[clave])
            self.limpiar_resaltado()

    def obtener_codigo(self):
        return self.text_area.get("1.0", tk.END)

    def limpiar_resaltado(self):
        self.text_area.tag_remove("error", "1.0", tk.END)

    def analisis_lexico(self):
        self.limpiar_resaltado()
        self.main_notebook.select(self.tab_tokens)
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        codigo = self.obtener_codigo()
        lexer = Lexer(codigo)
        tokens = lexer.tokenize()
        
        for t in tokens:
            if t.type =="ERROR":
                self.tree.insert("", tk.END, values=(t.value, t.type, f"{t.pos_start} - {t.pos_end}"), tags=("error_lexico",))
            else:
                self.tree.insert("", tk.END, values=(t.value, t.type, f"{t.pos_start} - {t.pos_end}"))
            
        return tokens

    def _parsear(self):
        """Corre léxico + sintáctico. Deja todo listo (AST + errores de
        sintaxis) tanto para el botón sintáctico como para el semántico."""
        tokens = self.analisis_lexico()
        codigo = self.obtener_codigo()

        parser = Parser(tokens, codigo)
        arbol_ast = parser.parse()

        self.ultimo_ast = arbol_ast
        self.btn_arbol.config(state=tk.NORMAL)

        return codigo, parser, arbol_ast

    def analisis_sintactico(self):
        self.limpiar_resaltado()
        codigo, parser, arbol_ast = self._parsear()

        if not parser.errors:
            messagebox.showinfo("Análisis Sintáctico", "¡Análisis sintáctico correcto! No se encontraron errores.")
            return

        # Resaltamos TODOS los errores encontrados en el editor
        for err in parser.errors:
            self.resaltar_error(codigo, err.pos_start, err.pos_end)

        # Armamos un mensaje con la lista completa de errores
        mensaje = f"Se encontraron {len(parser.errors)} error(es):\n\n"
        for i, err in enumerate(parser.errors, 1):
            fila_col = self.index_to_tk_public(codigo, err.pos_start)
            mensaje += f"{i}. (línea {fila_col}) {err.message}\n"
        messagebox.showerror("Errores de Sintaxis", mensaje)

    def analisis_semantico(self):
        """Fase 3 del pipeline: sólo corre si el código ya pasó léxico +
        sintáctico sin errores."""
        self.limpiar_resaltado()
        codigo, parser, arbol_ast = self._parsear()

        if parser.errors:
            for err in parser.errors:
                self.resaltar_error(codigo, err.pos_start, err.pos_end)

            mensaje = ("El código tiene errores de sintaxis; corrígelos antes de poder "
                       "correr el análisis semántico:\n\n")
            for i, err in enumerate(parser.errors, 1):
                fila_col = self.index_to_tk_public(codigo, err.pos_start)
                mensaje += f"{i}. (línea {fila_col}) {err.message}\n"
            messagebox.showerror("Corrige la sintaxis primero", mensaje)
            return

        analizador = SemanticAnalyzer()
        errores_sem, tabla = analizador.analizar(arbol_ast)
        self.mostrar_resultado_semantico(errores_sem, tabla)

    def mostrar_resultado_semantico(self, errores, tabla):
        ventana = tk.Toplevel(self.root)
        ventana.title("Análisis Semántico")
        ventana.geometry("650x600")

        if errores:
            color_estado = "#F44336"
            texto_estado = f"Se encontraron {len(errores)} error(es) semántico(s)"
        else:
            color_estado = "#4CAF50"
            texto_estado = "¡Análisis semántico correcto! No se encontraron errores."

        tk.Label(ventana, text=texto_estado, font=("Arial", 12, "bold"), fg=color_estado).pack(pady=10)

        if errores:
            tk.Label(ventana, text="Errores:", font=("Arial", 10, "bold")).pack(anchor="w", padx=15)
            frame_err = tk.Frame(ventana)
            frame_err.pack(fill=tk.BOTH, expand=False, padx=15, pady=(0, 10))
            scroll_err = tk.Scrollbar(frame_err)
            scroll_err.pack(side=tk.RIGHT, fill=tk.Y)
            lista_err = tk.Listbox(frame_err, height=min(8, len(errores)), yscrollcommand=scroll_err.set, fg="#B71C1C")
            lista_err.pack(fill=tk.BOTH, expand=True)
            scroll_err.config(command=lista_err.yview)
            for e in errores:
                lista_err.insert(tk.END, e)

        tk.Label(ventana, text="Tabla de símbolos:", font=("Arial", 10, "bold")).pack(anchor="w", padx=15)
        frame_tabla = tk.Frame(ventana)
        frame_tabla.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 15))

        columnas = ("Nombre", "Tipo", "Ámbito", "Línea")
        tv = ttk.Treeview(frame_tabla, columns=columnas, show="headings")
        for c in columnas:
            tv.heading(c, text=c)
            tv.column(c, width=60 if c == "Línea" else 150)
        tv.pack(fill=tk.BOTH, expand=True)

        for info in tabla.historial:
            tv.insert("", tk.END, values=(info["nombre"], info["tipo"], info["ambito"], info["linea"]))

        # Actualizar también la tabla de símbolos en la ventana principal
        for item in self.tv_main_simbolos.get_children():
            self.tv_main_simbolos.delete(item)
        for info in tabla.historial:
            self.tv_main_simbolos.insert("", tk.END, values=(info["nombre"], info["tipo"], info["ambito"], info["linea"]))
        self.main_notebook.select(self.tab_simbolos)

    def analisis_codigo_intermedio(self):
        """Fase 4 del pipeline: Generación de Código Intermedio (IR)
        a partir del AST validado."""
        self.limpiar_resaltado()
        codigo, parser, arbol_ast = self._parsear()

        if parser.errors:
            for err in parser.errors:
                self.resaltar_error(codigo, err.pos_start, err.pos_end)

            mensaje = ("El código tiene errores de sintaxis; corrígelos antes de poder "
                       "generar código intermedio:\n\n")
            for i, err in enumerate(parser.errors, 1):
                fila_col = self.index_to_tk_public(codigo, err.pos_start)
                mensaje += f"{i}. (línea {fila_col}) {err.message}\n"
            messagebox.showerror("Corrige la sintaxis primero", mensaje)
            return

        # Validación semántica previa al código intermedio
        analizador = SemanticAnalyzer()
        errores_sem, tabla = analizador.analizar(arbol_ast)
        if errores_sem:
            resp = messagebox.askyesno(
                "Advertencias Semánticas",
                f"El código contiene {len(errores_sem)} error(es) semántico(s):\n\n" +
                "\n".join(errores_sem[:5]) +
                ("\n..." if len(errores_sem) > 5 else "") +
                "\n\n¿Deseas generar el código intermedio (IR) de todas formas para pruebas?"
            )
            if not resp:
                self.mostrar_resultado_semantico(errores_sem, tabla)
                return

        generador = IRGenerator()
        instrucciones, postfijas, texto_ir = generador.generar(arbol_ast)

        # Actualizar pestaña de cuádruplos en la ventana principal
        for item in self.tv_main_cuads.get_children():
            self.tv_main_cuads.delete(item)
        for inst in instrucciones:
            self.tv_main_cuads.insert("", tk.END, values=(
                f"#{inst.numero}",
                inst.op,
                inst.arg1 or "—",
                inst.arg2 or "—",
                inst.resultado or "—"
            ))

        # Actualizar pestaña 3AC en la ventana principal
        self.txt_main_3ac.config(state=tk.NORMAL)
        self.txt_main_3ac.delete("1.0", tk.END)
        self.txt_main_3ac.insert(tk.END, generador.obtener_texto_3ac())
        self.txt_main_3ac.config(state=tk.DISABLED)

        # Actualizar pestaña de postfijas en la ventana principal
        for item in self.tv_main_post.get_children():
            self.tv_main_post.delete(item)
        if postfijas:
            for p in postfijas:
                self.tv_main_post.insert("", tk.END, values=(p["linea"], p["infija"], p["postfija"]))
        else:
            self.tv_main_post.insert("", tk.END, values=("—", "Sin expresiones evaluadas", "—"))

        # Cambiar automáticamente a la pestaña de Cuádruplos en la ventana principal
        self.main_notebook.select(self.tab_cuads)

        # Mostrar además la ventana flotante completa con opciones de guardado
        self.mostrar_resultado_ir(instrucciones, postfijas, generador)

    def mostrar_resultado_ir(self, instrucciones, postfijas, generador):
        ventana = tk.Toplevel(self.root)
        ventana.title("Generación de Código Intermedio (IR)")
        ventana.geometry("860x660")

        # Encabezado
        header_frame = tk.Frame(ventana, bg="#EDE7F6", padx=15, pady=10)
        header_frame.pack(fill=tk.X)
        tk.Label(header_frame, text="Código Intermedio (IR)", font=("Arial", 13, "bold"),
                 bg="#EDE7F6", fg="#4A148C").pack(anchor="w")
        tk.Label(header_frame, text="Del AST validado a instrucciones simples (Triplos, Cuádruplos y Postfija)",
                 font=("Arial", 9), bg="#EDE7F6", fg="#6A1B9A").pack(anchor="w")

        # Pestañas
        notebook = ttk.Notebook(ventana)
        notebook.pack(fill=tk.BOTH, expand=True, padx=15, pady=10)

        # ------------------------------------------------------------------
        # Pestaña 1: Tabla de Cuádruplos
        # ------------------------------------------------------------------
        tab_cuadruplos = ttk.Frame(notebook)
        notebook.add(tab_cuadruplos, text=" Tabla de Cuádruplos ")

        tk.Label(tab_cuadruplos, text="Instrucciones en formato Cuádruplo (#, op, arg1, arg2, res):",
                 font=("Arial", 10, "bold"), fg="#333").pack(anchor="w", pady=(8, 4))

        frame_tabla = tk.Frame(tab_cuadruplos)
        frame_tabla.pack(fill=tk.BOTH, expand=True)

        scroll_y = ttk.Scrollbar(frame_tabla, orient=tk.VERTICAL)
        scroll_x = ttk.Scrollbar(frame_tabla, orient=tk.HORIZONTAL)

        cols = ("#", "Operador", "Argumento 1", "Argumento 2", "Resultado / Destino")
        tv_cuads = ttk.Treeview(frame_tabla, columns=cols, show="headings",
                                yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        scroll_y.config(command=tv_cuads.yview)
        scroll_x.config(command=tv_cuads.xview)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        scroll_x.pack(side=tk.BOTTOM, fill=tk.X)
        tv_cuads.pack(fill=tk.BOTH, expand=True)

        tv_cuads.heading("#", text="#")
        tv_cuads.heading("Operador", text="Operador (op)")
        tv_cuads.heading("Argumento 1", text="Argumento 1 (arg1)")
        tv_cuads.heading("Argumento 2", text="Argumento 2 (arg2)")
        tv_cuads.heading("Resultado / Destino", text="Resultado / Destino (res)")

        tv_cuads.column("#", width=60, anchor="center")
        tv_cuads.column("Operador", width=120, anchor="center")
        tv_cuads.column("Argumento 1", width=140, anchor="center")
        tv_cuads.column("Argumento 2", width=140, anchor="center")
        tv_cuads.column("Resultado / Destino", width=160, anchor="center")

        for inst in instrucciones:
            tv_cuads.insert("", tk.END, values=(
                f"#{inst.numero}",
                inst.op,
                inst.arg1 or "—",
                inst.arg2 or "—",
                inst.resultado or "—"
            ))

        # ------------------------------------------------------------------
        # Pestaña 2: Formato .ir
        # ------------------------------------------------------------------
        tab_ir = ttk.Frame(notebook)
        notebook.add(tab_ir, text=" Formato .ir ")

        tk.Label(tab_ir, text="Formato de archivo .ir (#N (op, arg1, arg2, res)):",
                 font=("Arial", 10, "bold"), fg="#333").pack(anchor="w", pady=(8, 4))

        frame_txt_ir = tk.Frame(tab_ir)
        frame_txt_ir.pack(fill=tk.BOTH, expand=True)

        scroll_ir = ttk.Scrollbar(frame_txt_ir)
        scroll_ir.pack(side=tk.RIGHT, fill=tk.Y)
        txt_ir = tk.Text(frame_txt_ir, font=("Consolas", 11), yscrollcommand=scroll_ir.set, bg="#F9F9F9")
        txt_ir.pack(fill=tk.BOTH, expand=True)
        scroll_ir.config(command=txt_ir.yview)

        texto_ir_completo = generador.obtener_texto_ir()
        txt_ir.insert(tk.END, texto_ir_completo)
        txt_ir.config(state=tk.DISABLED)

        # ------------------------------------------------------------------
        # Pestaña 3: Código de Tres Direcciones (3AC)
        # ------------------------------------------------------------------
        tab_3ac = ttk.Frame(notebook)
        notebook.add(tab_3ac, text=" Tres Direcciones (3AC) ")

        tk.Label(tab_3ac, text="Representación en código de tres direcciones (3AC):",
                 font=("Arial", 10, "bold"), fg="#333").pack(anchor="w", pady=(8, 4))

        frame_txt_3ac = tk.Frame(tab_3ac)
        frame_txt_3ac.pack(fill=tk.BOTH, expand=True)

        scroll_3ac = ttk.Scrollbar(frame_txt_3ac)
        scroll_3ac.pack(side=tk.RIGHT, fill=tk.Y)
        txt_3ac = tk.Text(frame_txt_3ac, font=("Consolas", 11), yscrollcommand=scroll_3ac.set, bg="#F9F9F9")
        txt_3ac.pack(fill=tk.BOTH, expand=True)
        scroll_3ac.config(command=txt_3ac.yview)

        texto_3ac_completo = generador.obtener_texto_3ac()
        txt_3ac.insert(tk.END, texto_3ac_completo)
        txt_3ac.config(state=tk.DISABLED)

        # ------------------------------------------------------------------
        # Pestaña 4: Notación Postfija
        # ------------------------------------------------------------------
        tab_postfija = ttk.Frame(notebook)
        notebook.add(tab_postfija, text=" Notación Postfija ")

        tk.Label(tab_postfija, text="Recorrido postorden del AST de expresiones (hijos -> padre):",
                 font=("Arial", 10, "bold"), fg="#333").pack(anchor="w", pady=(8, 4))

        frame_post = tk.Frame(tab_postfija)
        frame_post.pack(fill=tk.BOTH, expand=True)

        scroll_post = ttk.Scrollbar(frame_post)
        scroll_post.pack(side=tk.RIGHT, fill=tk.Y)
        cols_post = ("Línea", "Expresión Infija", "Notación Postfija (RPN)")
        tv_post = ttk.Treeview(frame_post, columns=cols_post, show="headings", yscrollcommand=scroll_post.set)
        scroll_post.config(command=tv_post.yview)
        tv_post.pack(fill=tk.BOTH, expand=True)

        tv_post.heading("Línea", text="Línea")
        tv_post.heading("Expresión Infija", text="Expresión Infija")
        tv_post.heading("Notación Postfija (RPN)", text="Notación Postfija (RPN)")

        tv_post.column("Línea", width=60, anchor="center")
        tv_post.column("Expresión Infija", width=280, anchor="w")
        tv_post.column("Notación Postfija (RPN)", width=340, anchor="w")

        if postfijas:
            for p in postfijas:
                tv_post.insert("", tk.END, values=(p["linea"], p["infija"], p["postfija"]))
        else:
            tv_post.insert("", tk.END, values=("—", "Sin expresiones evaluadas", "—"))

        # ------------------------------------------------------------------
        # Barra inferior de acciones
        # ------------------------------------------------------------------
        bottom_frame = tk.Frame(ventana, pady=10, padx=15)
        bottom_frame.pack(fill=tk.X)

        def guardar_archivo_ir():
            ruta = filedialog.asksaveasfilename(
                title="Guardar archivo de Código Intermedio (.ir)",
                defaultextension=".ir",
                filetypes=[("Código Intermedio (*.ir)", "*.ir"), ("Todos los archivos", "*.*")]
            )
            if ruta:
                try:
                    with open(ruta, "w", encoding="utf-8") as f:
                        f.write(texto_ir_completo + "\n")
                    messagebox.showinfo("Guardado exitoso", f"Archivo guardado correctamente en:\n{ruta}")
                except Exception as ex:
                    messagebox.showerror("Error al guardar", f"No se pudo guardar el archivo:\n{ex}")

        def copiar_al_portapapeles():
            self.root.clipboard_clear()
            self.root.clipboard_append(texto_ir_completo)
            messagebox.showinfo("Copiado", "¡Código IR copiado al portapapeles!")

        btn_guardar = tk.Button(bottom_frame, text="💾 Guardar archivo .ir", command=guardar_archivo_ir,
                                bg="#4CAF50", fg="white", font=("Arial", 10, "bold"), padx=10, pady=4)
        btn_guardar.pack(side=tk.LEFT, padx=5)

        btn_copiar = tk.Button(bottom_frame, text="📋 Copiar código .ir", command=copiar_al_portapapeles,
                               bg="#2196F3", fg="white", font=("Arial", 10, "bold"), padx=10, pady=4)
        btn_copiar.pack(side=tk.LEFT, padx=5)

        btn_opt_ir = tk.Button(bottom_frame, text="🚀 Optimizar IR (CFG / U3)",
                               command=lambda: [ventana.destroy(), self.analisis_optimizacion()],
                               bg="#E91E63", fg="white", font=("Arial", 10, "bold"), padx=10, pady=4)
        btn_opt_ir.pack(side=tk.LEFT, padx=5)

        btn_cerrar = tk.Button(bottom_frame, text="Cerrar", command=ventana.destroy,
                               bg="#757575", fg="white", font=("Arial", 10), padx=10, pady=4)
        btn_cerrar.pack(side=tk.RIGHT, padx=5)

    def ver_arbol_sintactico(self):
        if self.ultimo_ast is None:
            messagebox.showinfo("Árbol Sintáctico", "Primero ejecuta un Análisis Sintáctico para poder ver el árbol.")
            return
        self.mostrar_arbol_sintactico(self.ultimo_ast)

    def mostrar_arbol_sintactico(self, nodo_raiz):
        ventana_arbol = tk.Toplevel(self.root)
        ventana_arbol.title("Árbol de Sintaxis Abstracta (AST)")
        ventana_arbol.geometry("500x600")

        tk.Label(ventana_arbol, text="Estructura Lógica del Código", font=("Arial", 12, "bold"), fg="#2196F3").pack(pady=10)

        tree = ttk.Treeview(ventana_arbol)
        tree.pack(fill=tk.BOTH, expand=True, padx=15, pady=10)
        tree.heading("#0", text="AST (Abstract Syntax Tree)", anchor='w')

        
        def poblar_arbol(parent_id, nodo):
            if not nodo:
                return
                
            texto_nodo = nodo.etiqueta
            if nodo.valor:
                texto_nodo += f" : {nodo.valor}"
            if getattr(nodo, 'tipo', None):
                texto_nodo += f"  [{nodo.tipo}]"
            if getattr(nodo, 'linea', None):
                texto_nodo += f"  (línea {nodo.linea})"
                
            item_id = tree.insert(parent_id, tk.END, text=texto_nodo, open=True)
            for hijo in nodo.hijos:
                poblar_arbol(item_id, hijo)
        if nodo_raiz:
            poblar_arbol("", nodo_raiz)
        
    def index_to_tk_public(self, codigo, idx):
        lines = codigo[:idx].split('\n')
        row = len(lines)
        col = len(lines[-1])
        return f"{row}:{col}"

    def resaltar_error(self, codigo, start_idx, end_idx):
        def index_to_tk(idx):
            lines = codigo[:idx].split('\n')
            row = len(lines)
            col = len(lines[-1])
            return f"{row}.{col}"
            
        if start_idx == end_idx:
            end_idx += 1
            
        start_tk = index_to_tk(start_idx)
        end_tk = index_to_tk(end_idx)
        
        self.text_area.tag_add("error", start_tk, end_tk)
        self.text_area.see(start_tk)

    def _conmutar_vista_cfg(self, vista):
        self.ultimo_cfg_vista = vista
        if not self.ultimo_optimizador:
            return
        if vista == "original":
            self.main_cfg_canvas.dibujar_cfg(self.ultimo_optimizador.cfg_original)
            self.lbl_cfg_estado.config(text="Mostrando: CFG Original", fg="#1565C0")
        else:
            self.main_cfg_canvas.dibujar_cfg(self.ultimo_optimizador.cfg_optimizado)
            self.lbl_cfg_estado.config(text="Mostrando: CFG Optimizado", fg="#2E7D32")

    def analisis_optimizacion(self):
        """
        Ejecuta el pipeline completo de Optimización de Código Intermedio (Unidad 3):
        Identificación de Bloques Básicos, Construcción del GFG/CFG, Aplicación
        de Técnicas de Optimización, Tabla de Transformaciones y Métricas.
        """
        self.limpiar_resaltado()

        codigo, parser, arbol_ast = self._parsear()

        if parser.errors:
            for err in parser.errors:
                self.resaltar_error(codigo, err.pos_start, err.pos_end)

            mensaje = ("El código tiene errores de sintaxis; corrígelos antes de optimizar:\n\n")
            for i, err in enumerate(parser.errors, 1):
                fila_col = self.index_to_tk_public(codigo, err.pos_start)
                mensaje += f"{i}. (línea {fila_col}) {err.message}\n"
            messagebox.showerror("Corrige la sintaxis primero", mensaje)
            return

        if not arbol_ast or not getattr(arbol_ast, "hijos", []):
            messagebox.showwarning("Sin código", "No hay código o instrucciones para optimizar.")
            return

        # Validación semántica previa
        analizador = SemanticAnalyzer()
        errores_sem, tabla = analizador.analizar(arbol_ast)
        if errores_sem:
            resp = messagebox.askyesno(
                "Advertencias Semánticas",
                f"El código contiene {len(errores_sem)} error(es) semántico(s):\n\n" +
                "\n".join(errores_sem[:5]) +
                ("\n..." if len(errores_sem) > 5 else "") +
                "\n\n¿Deseas continuar con la optimización de todas formas para pruebas?"
            )
            if not resp:
                self.mostrar_resultado_semantico(errores_sem, tabla)
                return

        generador = IRGenerator()
        instrucciones, postfijas, texto_ir = generador.generar(arbol_ast)

        if not instrucciones:
            messagebox.showwarning("Sin instrucciones", "No se generaron instrucciones de código intermedio para optimizar.")
            return

        # Crear y ejecutar el optimizador
        opt = IROptimizer(instrucciones)
        opt.optimizar()
        self.ultimo_optimizador = opt

        # Actualizar pestañas integradas en la ventana principal
        self._actualizar_pestanas_optimizacion(opt)

        # Seleccionar automáticamente la pestaña del Grafo de Flujo en la ventana principal
        self.main_notebook.select(self.tab_cfg)

        # Abrir ventana completa de Optimización y Grafo de Flujo
        self.mostrar_resultado_optimizacion(opt)

    def _actualizar_pestanas_optimizacion(self, opt: IROptimizer):
        # 1. Pestaña Bloques Básicos
        for item in self.tv_main_bb.get_children():
            self.tv_main_bb.delete(item)
        for b in opt.bloques_originales:
            estado = "Inalcanzable" if b.es_inalcanzable else ("Entrada" if b.es_entrada else ("Salida" if b.es_salida else "Normal"))
            texto_3ac = " ; ".join(i.to_3ac() for i in b.instrucciones)
            self.tv_main_bb.insert("", tk.END, values=(
                b.id,
                b.etiqueta or "—",
                texto_3ac,
                estado
            ))

        # 2. Grafo de Flujo (Canvas)
        self.main_cfg_canvas.dibujar_cfg(opt.cfg_original if self.ultimo_cfg_vista == "original" else opt.cfg_optimizado)

        # 3. Tabla de Sucesores
        for item in self.tv_main_sucesores.get_children():
            self.tv_main_sucesores.delete(item)
        for fila in opt.cfg_original.obtener_tabla_sucesores():
            estado = "Inalcanzable" if fila["es_inalcanzable"] else "Flujo Activo"
            self.tv_main_sucesores.insert("", tk.END, values=(
                fila["bloque"],
                fila["sucesores"],
                estado
            ))

        # 4. IR Optimizado (Cuádruplos)
        for item in self.tv_main_opt_cuads.get_children():
            self.tv_main_opt_cuads.delete(item)
        for inst in opt.instrucciones_optimizadas:
            self.tv_main_opt_cuads.insert("", tk.END, values=(
                f"#{inst.numero}",
                inst.op,
                inst.arg1 or "—",
                inst.arg2 or "—",
                inst.resultado or "—"
            ))

        # 3AC Optimizado
        self.txt_main_opt_3ac.config(state=tk.NORMAL)
        self.txt_main_opt_3ac.delete("1.0", tk.END)
        for inst in opt.instrucciones_optimizadas:
            self.txt_main_opt_3ac.insert(tk.END, f"{inst.numero}: {inst.to_3ac()}\n")
        self.txt_main_opt_3ac.config(state=tk.DISABLED)

        # Comparativa lado a lado
        self.txt_main_diff.config(state=tk.NORMAL)
        self.txt_main_diff.delete("1.0", tk.END)
        self.txt_main_diff.insert(tk.END, f"{'=== CÓDIGO IR ORIGINAL (before.ir) ===':<42} | {'=== CÓDIGO IR OPTIMIZADO (after.ir) ==='}\n")
        self.txt_main_diff.insert(tk.END, "-" * 90 + "\n")
        n_orig = len(opt.instrucciones_originales)
        n_opt = len(opt.instrucciones_optimizadas)
        max_len = max(n_orig, n_opt)
        for idx in range(max_len):
            str_orig = opt.instrucciones_originales[idx].to_ir_tuple() if idx < n_orig else ""
            str_opt = opt.instrucciones_optimizadas[idx].to_ir_tuple() if idx < n_opt else ""
            self.txt_main_diff.insert(tk.END, f"{str_orig:<45} | {str_opt}\n")
        self.txt_main_diff.config(state=tk.DISABLED)

        # 5. Tabla de Transformaciones
        for item in self.tv_main_transf.get_children():
            self.tv_main_transf.delete(item)
        for t in opt.transformaciones:
            self.tv_main_transf.insert("", tk.END, values=(
                t.numero,
                t.bloque,
                t.tecnica,
                t.original,
                t.optimizado,
                t.justificacion
            ))

        # 6. Métricas y Análisis
        reporte = OptimizationReport(opt)
        self.txt_main_metricas.config(state=tk.NORMAL)
        self.txt_main_metricas.delete("1.0", tk.END)
        self.txt_main_metricas.insert(tk.END, reporte.generar_reporte_texto())
        self.txt_main_metricas.config(state=tk.DISABLED)

    def mostrar_resultado_optimizacion(self, opt: IROptimizer):
        """
        Abre una ventana completa e interactiva con todas las vistas de optimización y CFG.
        """
        ventana = tk.Toplevel(self.root)
        ventana.title("Optimización de Código Intermedio (CFG / GFG)")
        ventana.geometry("1020x720")
        ventana.minsize(850, 600)

        # Encabezado
        header_frame = tk.Frame(ventana, bg="#FCE4EC", padx=15, pady=10)
        header_frame.pack(fill=tk.X)
        tk.Label(
            header_frame, text="Optimización de Código Intermedio mediante Grafo de Flujo de Control",
            font=("Arial", 13, "bold"), bg="#FCE4EC", fg="#880E4F"
        ).pack(anchor="w")
        tk.Label(
            header_frame,
            text="Constant Folding, Propagación de Constantes, CSE, Eliminación de Código Muerto, Bloques Inalcanzables y Saltos",
            font=("Arial", 9), bg="#FCE4EC", fg="#AD1457"
        ).pack(anchor="w")

        notebook = ttk.Notebook(ventana)
        notebook.pack(fill=tk.BOTH, expand=True, padx=12, pady=8)

        # --------------------------------------------------------------------
        # Pestaña 1: Grafo de Flujo de Control (Canvas con controles)
        # --------------------------------------------------------------------
        tab_grafo = ttk.Frame(notebook)
        notebook.add(tab_grafo, text=" 🕸️ Grafo de Flujo (CFG) ")

        ctrl_bar = tk.Frame(tab_grafo, bg="#ECEFF1", pady=5, padx=8)
        ctrl_bar.pack(fill=tk.X)

        canvas_modal = CFGCanvas(tab_grafo)
        canvas_modal.pack(fill=tk.BOTH, expand=True)

        lbl_modal_info = tk.Label(ctrl_bar, text="Vista activa: CFG Original", font=("Arial", 9, "bold"), bg="#ECEFF1", fg="#1565C0")

        def ver_orig():
            canvas_modal.dibujar_cfg(opt.cfg_original)
            lbl_modal_info.config(text="Vista activa: CFG Original", fg="#1565C0")

        def ver_opt():
            canvas_modal.dibujar_cfg(opt.cfg_optimizado)
            lbl_modal_info.config(text="Vista activa: CFG Optimizado", fg="#2E7D32")

        btn_ver_orig = tk.Button(ctrl_bar, text="🔵 CFG Original", command=ver_orig,
                                 bg="#1565C0", fg="white", font=("Arial", 9, "bold"), padx=10, pady=2)
        btn_ver_orig.pack(side=tk.LEFT, padx=3)

        btn_ver_opt = tk.Button(ctrl_bar, text="🟢 CFG Optimizado", command=ver_opt,
                                bg="#2E7D32", fg="white", font=("Arial", 9, "bold"), padx=10, pady=2)
        btn_ver_opt.pack(side=tk.LEFT, padx=3)
        lbl_modal_info.pack(side=tk.LEFT, padx=15)

        # Dibujar por defecto el original
        canvas_modal.dibujar_cfg(opt.cfg_original)

        # --------------------------------------------------------------------
        # Pestaña 2: Bloques Básicos y Tabla de Sucesores
        # --------------------------------------------------------------------
        tab_bb_suc = ttk.Frame(notebook)
        notebook.add(tab_bb_suc, text=" 🧱 Bloques Básicos y Sucesores ")

        paned_bb = ttk.PanedWindow(tab_bb_suc, orient=tk.HORIZONTAL)
        paned_bb.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        # Sub-panel izquierdo: Bloques Básicos
        frame_bb_izq = ttk.LabelFrame(paned_bb, text="Bloques Básicos Identificados (Límites)")
        paned_bb.add(frame_bb_izq, weight=3)

        txt_bb_list = tk.Text(frame_bb_izq, font=("Consolas", 10), bg="#FAFAFA")
        sb_bb_l = ttk.Scrollbar(frame_bb_izq, orient=tk.VERTICAL, command=txt_bb_list.yview)
        txt_bb_list.config(yscrollcommand=sb_bb_l.set)
        sb_bb_l.pack(side=tk.RIGHT, fill=tk.Y)
        txt_bb_list.pack(fill=tk.BOTH, expand=True)

        for b in opt.bloques_originales:
            txt_bb_list.insert(tk.END, b.obtener_texto_bloque() + "\n\n")
        txt_bb_list.config(state=tk.DISABLED)

        # Sub-panel derecho: Tabla de Sucesores
        frame_suc_der = ttk.LabelFrame(paned_bb, text="Tabla de Sucesores del GFG")
        paned_bb.add(frame_suc_der, weight=2)

        cols_s = ("Bloque", "Sucesores")
        tv_modal_suc = ttk.Treeview(frame_suc_der, columns=cols_s, show="headings")
        tv_modal_suc.heading("Bloque", text="Bloque")
        tv_modal_suc.heading("Sucesores", text="Sucesores")
        tv_modal_suc.column("Bloque", width=110, anchor="center")
        tv_modal_suc.column("Sucesores", width=220, anchor="w")
        tv_modal_suc.pack(fill=tk.BOTH, expand=True)

        for row in opt.cfg_original.obtener_tabla_sucesores():
            tv_modal_suc.insert("", tk.END, values=(row["bloque"], row["sucesores"]))

        # --------------------------------------------------------------------
        # Pestaña 3: Tabla de Transformaciones Detallada
        # --------------------------------------------------------------------
        tab_transf_modal = ttk.Frame(notebook)
        notebook.add(tab_transf_modal, text=" 📋 Tabla de Transformaciones ")

        cols_t = ("#", "Bloque", "Técnica Aplicada", "Código Original", "Código Optimizado", "Justificación")
        tv_t_modal = ttk.Treeview(tab_transf_modal, columns=cols_t, show="headings")
        for c in cols_t:
            tv_t_modal.heading(c, text=c)
        tv_t_modal.column("#", width=45, anchor="center")
        tv_t_modal.column("Bloque", width=75, anchor="center")
        tv_t_modal.column("Técnica Aplicada", width=220, anchor="w")
        tv_t_modal.column("Código Original", width=180, anchor="w")
        tv_t_modal.column("Código Optimizado", width=160, anchor="w")
        tv_t_modal.column("Justificación", width=300, anchor="w")

        sb_t_y = ttk.Scrollbar(tab_transf_modal, orient=tk.VERTICAL, command=tv_t_modal.yview)
        sb_t_x = ttk.Scrollbar(tab_transf_modal, orient=tk.HORIZONTAL, command=tv_t_modal.xview)
        tv_t_modal.configure(yscrollcommand=sb_t_y.set, xscrollcommand=sb_t_x.set)
        sb_t_y.pack(side=tk.RIGHT, fill=tk.Y)
        sb_t_x.pack(side=tk.BOTTOM, fill=tk.X)
        tv_t_modal.pack(fill=tk.BOTH, expand=True)

        for t in opt.transformaciones:
            tv_t_modal.insert("", tk.END, values=(
                t.numero, t.bloque, t.tecnica, t.original, t.optimizado, t.justificacion
            ))

        # --------------------------------------------------------------------
        # Pestaña 4: Tabla Comparativa CFG (Original vs Optimizado)
        # --------------------------------------------------------------------
        tab_comp_modal = ttk.Frame(notebook)
        notebook.add(tab_comp_modal, text=" 📊 Tabla Comparativa CFG ")

        cols_c = ("Elemento", "CFG Original", "CFG Optimizado", "Optimización Realizada")
        tv_c_modal = ttk.Treeview(tab_comp_modal, columns=cols_c, show="headings")
        for c in cols_c:
            tv_c_modal.heading(c, text=c)
        tv_c_modal.column("Elemento", width=220, anchor="w")
        tv_c_modal.column("CFG Original", width=160, anchor="center")
        tv_c_modal.column("CFG Optimizado", width=160, anchor="center")
        tv_c_modal.column("Optimización Realizada", width=360, anchor="w")
        tv_c_modal.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        for row in opt.obtener_tabla_comparativa_cfg():
            tv_c_modal.insert("", tk.END, values=(
                row["elemento"], row["cfg_original"], row["cfg_optimizado"], row["optimizacion"]
            ))

        # --------------------------------------------------------------------
        # Pestaña 5: Comparativa IR (before.ir vs after.ir)
        # --------------------------------------------------------------------
        tab_diff_modal = ttk.Frame(notebook)
        notebook.add(tab_diff_modal, text=" ⚡ IR Antes / Después ")

        txt_ir_side = tk.Text(tab_diff_modal, font=("Consolas", 10), bg="#FAFAFA")
        sb_ir_s = ttk.Scrollbar(tab_diff_modal, orient=tk.VERTICAL, command=txt_ir_side.yview)
        txt_ir_side.config(yscrollcommand=sb_ir_s.set)
        sb_ir_s.pack(side=tk.RIGHT, fill=tk.Y)
        txt_ir_side.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        txt_ir_side.insert(tk.END, f"{'=== CÓDIGO ORIGINAL (before.ir) ===':<45} | {'=== CÓDIGO OPTIMIZADO (after.ir) ==='}\n")
        txt_ir_side.insert(tk.END, "=" * 95 + "\n")
        n_orig = len(opt.instrucciones_originales)
        n_opt = len(opt.instrucciones_optimizadas)
        for idx in range(max(n_orig, n_opt)):
            s_or = opt.instrucciones_originales[idx].to_ir_tuple() if idx < n_orig else ""
            s_op = opt.instrucciones_optimizadas[idx].to_ir_tuple() if idx < n_opt else ""
            txt_ir_side.insert(tk.END, f"{s_or:<48} | {s_op}\n")
        txt_ir_side.config(state=tk.DISABLED)

        # --------------------------------------------------------------------
        # Pestaña 6: Reporte Completo y Conclusiones
        # --------------------------------------------------------------------
        tab_rep_modal = ttk.Frame(notebook)
        notebook.add(tab_rep_modal, text=" 📑 Reporte y Conclusiones ")

        txt_rep_full = tk.Text(tab_rep_modal, font=("Consolas", 10), bg="#FFFFFF")
        sb_rep = ttk.Scrollbar(tab_rep_modal, orient=tk.VERTICAL, command=txt_rep_full.yview)
        txt_rep_full.config(yscrollcommand=sb_rep.set)
        sb_rep.pack(side=tk.RIGHT, fill=tk.Y)
        txt_rep_full.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        reporte = OptimizationReport(opt)
        txt_rep_full.insert(tk.END, reporte.generar_reporte_texto())
        txt_rep_full.config(state=tk.DISABLED)

        # --------------------------------------------------------------------
        # Barra Inferior: Acciones y Exportaciones
        # --------------------------------------------------------------------
        bot_bar = tk.Frame(ventana, bg="#F5F5F5", padx=15, pady=8)
        bot_bar.pack(fill=tk.X)

        def guardar_before_ir():
            ruta = filedialog.asksaveasfilename(
                title="Guardar before.ir", defaultextension=".ir",
                initialfile="before.ir",
                filetypes=[("Código Intermedio (*.ir)", "*.ir"), ("Todos los archivos", "*.*")]
            )
            if ruta:
                try:
                    with open(ruta, "w", encoding="utf-8") as f:
                        for i in opt.instrucciones_originales:
                            f.write(i.to_ir_tuple() + "\n")
                    messagebox.showinfo("Guardado", f"before.ir guardado en:\n{ruta}")
                except Exception as ex:
                    messagebox.showerror("Error", str(ex))

        def guardar_after_ir():
            ruta = filedialog.asksaveasfilename(
                title="Guardar after.ir", defaultextension=".ir",
                initialfile="after.ir",
                filetypes=[("Código Intermedio (*.ir)", "*.ir"), ("Todos los archivos", "*.*")]
            )
            if ruta:
                try:
                    with open(ruta, "w", encoding="utf-8") as f:
                        for i in opt.instrucciones_optimizadas:
                            f.write(i.to_ir_tuple() + "\n")
                    messagebox.showinfo("Guardado", f"after.ir guardado en:\n{ruta}")
                except Exception as ex:
                    messagebox.showerror("Error", str(ex))

        def guardar_reporte():
            ruta = filedialog.asksaveasfilename(
                title="Guardar Reporte de Optimización", defaultextension=".txt",
                initialfile="reporte_optimizacion_u3.txt",
                filetypes=[("Reporte Texto (*.txt)", "*.txt"), ("Todos los archivos", "*.*")]
            )
            if ruta:
                try:
                    with open(ruta, "w", encoding="utf-8") as f:
                        f.write(reporte.generar_reporte_texto() + "\n")
                    messagebox.showinfo("Guardado", f"Reporte guardado en:\n{ruta}")
                except Exception as ex:
                    messagebox.showerror("Error", str(ex))

        def copiar_after_ir():
            texto = "\n".join(i.to_ir_tuple() for i in opt.instrucciones_optimizadas)
            self.root.clipboard_clear()
            self.root.clipboard_append(texto)
            messagebox.showinfo("Copiado", "¡Código after.ir copiado al portapapeles!")

        btn_g_b = tk.Button(bot_bar, text="💾 Guardar before.ir", command=guardar_before_ir,
                            bg="#1565C0", fg="white", font=("Arial", 9, "bold"), padx=8, pady=3)
        btn_g_b.pack(side=tk.LEFT, padx=3)

        btn_g_a = tk.Button(bot_bar, text="💾 Guardar after.ir", command=guardar_after_ir,
                            bg="#2E7D32", fg="white", font=("Arial", 9, "bold"), padx=8, pady=3)
        btn_g_a.pack(side=tk.LEFT, padx=3)

        btn_g_r = tk.Button(bot_bar, text="📄 Guardar Reporte (.txt)", command=guardar_reporte,
                            bg="#6A1B9A", fg="white", font=("Arial", 9, "bold"), padx=8, pady=3)
        btn_g_r.pack(side=tk.LEFT, padx=3)

        btn_c_a = tk.Button(bot_bar, text="📋 Copiar after.ir", command=copiar_after_ir,
                            bg="#00838F", fg="white", font=("Arial", 9, "bold"), padx=8, pady=3)
        btn_c_a.pack(side=tk.LEFT, padx=3)

        btn_close = tk.Button(bot_bar, text="Cerrar", command=ventana.destroy,
                              bg="#757575", fg="white", font=("Arial", 9), padx=10, pady=3)
        btn_close.pack(side=tk.RIGHT, padx=3)

if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()