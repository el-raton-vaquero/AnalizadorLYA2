import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import re
import os
import sys

_base_dir = os.path.dirname(os.path.abspath(__file__))
if _base_dir not in sys.path:
    sys.path.insert(0, _base_dir)

from compilador.ir.generator import IRGenerator, Cuadruplo, generar_ir
from compilador.opt import (
    BasicBlock, identificar_bloques_basicos, ControlFlowGraph,
    IROptimizer, CFGCanvas, OptimizationReport, optimizar_ir_completo,
    SeccionColoracionGrafos
)
from compilador.codegen import (
    LivenessAnalyzer, LiveRange, LivenessResult,
    construir_grafo_interferencia, RegisterAllocator,
    RegistroInfo, CodeGenerator, SimulatorASM, ExecutionResult,
    ResultadoCompilacionObjeto, generar_codigo_objeto_completo
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
        self.linea = None
        self.tipo = None

    def agregar_hijo(self, nodo_hijo):
        if nodo_hijo:
            self.hijos.append(nodo_hijo)


class Lexer:
    def __init__(self, code):
        self.code = code
        self.tokens = []

        rules = [
            ('BLOQUE_COMENTARIO', r'/\*[\s\S]*?\*/'),
            ('LINEA_COMENTARIO', r'//[^\n]*'),
            ('DIRECTIVA', r'#[^\n]*'),
            ('RESERVADA', r'\b(int|cout|cin|float|void|char|double|string|boolean|bool|if|else|while|for|return|break|continue|true|false|class|struct|public|private|protected|static|const|inline|virtual|using|namespace|endl)\b'),
            ('NUMERO',   r'\d+(\.\d*)?'),
            ('IDENTIFICADOR',       r'[A-Za-z_][A-Za-z0-9_]*'),
            ('CADENA',   r'".*?"'),
            ('OP_INCREMENTO', r'\+\+|--'),
            ('OP_FLUJO',        r'<<|>>'),
            ('OP_RESOLUCION',   r'::'),
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
            ('ESPACIO',    r'[ \t\r\n]+'),
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


TIPOS_DATO = ['int', 'float', 'void', 'char', 'double', 'string', 'boolean', 'bool']
VALUE_TOKEN_TYPES = ('IDENTIFICADOR', 'NUMERO', 'CADENA')
TIPOS_NUMERICOS = ('int', 'float')


class ExprParser:
    def __init__(self, tokens, line_of):
        self.tokens = tokens
        self.pos = 0
        self.line_of = line_of

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
        if tok.type == 'RESERVADA' and tok.value == 'endl':
            self.advance()
            return self._nodo("Id", "endl", tok.pos_start)
        if tok.type == 'IDENTIFICADOR':
            nombre_id = tok.value
            pos_id = tok.pos_start
            self.advance()
            while self.current() and self.current().type == 'OP_RESOLUCION':
                self.advance()
                if self.current() and self.current().type in ('IDENTIFICADOR', 'RESERVADA'):
                    nombre_id = f"{nombre_id}::{self.current().value}"
                    self.advance()
            nodo = self._nodo("Id", nombre_id, pos_id)
            if self.current() and self.current().type == 'CORCHETE_IZQ':
                self.advance()
                indice = self.parse_asignacion()
                if self.current() and self.current().type == 'CORCHETE_DER':
                    self.advance()
                acceso = self._nodo("AccesoArreglo", nombre_id, pos_id)
                acceso.agregar_hijo(indice)
                nodo = acceso
            elif self.current() and self.current().type == 'PARENTESIS_IZQ':
                self.advance()
                llamada = self._nodo("Llamada", nombre_id, pos_id)
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
        self.errors = []

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
        if tok.type == 'RESERVADA' and tok.value in ('true', 'false', 'endl'):
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
                break
            if t.type == 'PARENTESIS_IZQ':
                parens += 1
                prev_value_end = None
            elif t.type == 'PARENTESIS_DER':
                parens -= 1
                prev_value_end = t.pos_end
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
                prev_value_end = None
            self.advance()

        stopped_by = self.current().type if self.current() else None
        return parens, brackets, stopped_by

    def parse_expr_tokens(self, tokens):
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
            if self.pos == start_pos:
                self.advance()
        return nodo_raiz

    def parse_global(self):

        tok = self.current()
        if not tok:
            return

        if tok.type == 'DIRECTIVA':
            nodo_dir = NodoAST("Directiva", tok.value)
            nodo_dir.linea = self.line_of(tok.pos_start)
            self.advance()
            return nodo_dir

        if tok.type == 'RESERVADA' and tok.value == 'using':
            while self.current() and self.current().type != 'PUNTO_Y_COMA':
                self.advance()
            if self.current() and self.current().type == 'PUNTO_Y_COMA':
                self.advance()
            return None

        if tok.type == 'RESERVADA' and tok.value in ('class', 'struct'):
            self.advance()
            tok_id = self.current()
            nombre_clase = "Anonima"
            if tok_id and tok_id.type == 'IDENTIFICADOR':
                nombre_clase = tok_id.value
                self.advance()
            nodo_clase = NodoAST("Clase", nombre_clase)
            nodo_clase.linea = self.line_of(tok.pos_start)
            if self.current() and self.current().type == 'LLAVE_IZQ':
                self.advance()
                while self.current() and self.current().type != 'LLAVE_DER':
                    if self.current().type == 'DIRECTIVA':
                        self.advance()
                        continue
                    if self.current().type == 'RESERVADA' and self.current().value in ('public', 'private', 'protected'):
                        self.advance()
                        if self.current() and self.current().type in ('TERNARIO',) and self.current().value == ':':
                            self.advance()
                        continue
                    if self.current().type == 'PUNTO_Y_COMA':
                        self.advance()
                        continue
                    pos_antes = self.pos
                    miembro = self.parse_global()
                    if miembro:
                        nodo_clase.agregar_hijo(miembro)
                    if self.pos == pos_antes:
                        self.advance()
                if self.current() and self.current().type == 'LLAVE_DER':
                    self.advance()
                if self.current() and self.current().type == 'PUNTO_Y_COMA':
                    self.advance()
            return nodo_clase

        while self.current() and self.current().type == 'RESERVADA' and self.current().value in ('static', 'const', 'inline', 'virtual'):
            self.advance()

        tok = self.current()
        if not tok:
            return

        if tok.type == 'RESERVADA' and tok.value in TIPOS_DATO:
            tipo_dato = tok.value
            self.advance()

            tok_id = self.current()
            if tok_id and tok_id.type == 'IDENTIFICADOR':
                nombre_id = tok_id.value
                self.advance()
            else:
                pos = tok.pos_end
                self.add_error("Se esperaba un identificador después del tipo de dato.", pos, pos + 1)
                self.synchronize()
                return

            tok_next = self.current()
            if tok_next and tok_next.type == 'PARENTESIS_IZQ':
                nodo_func = NodoAST("Función", nombre_id)
                nodo_func.tipo = tipo_dato
                nodo_func.linea = self.line_of(tok.pos_start)
                self.advance()
                params = self.parse_params()

                tok_close = self.current()
                if tok_close and tok_close.type == 'PARENTESIS_DER':
                    self.advance()
                else:
                    pos = tok_next.pos_end
                    self.add_error("Falta cerrar el paréntesis ')' en los parámetros de la función.", pos, pos + 1)
                    self.synchronize(sync_types=('LLAVE_IZQ',), stop_types=(), consume_sync=False)

                tipos_clasicos = self.parse_classical_decls()

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
                nodo_init = self.parse_var_tail()
                if nodo_init:
                    contenedor = NodoAST("Inicializador")
                    contenedor.agregar_hijo(nodo_init)
                    nodo_var.agregar_hijo(contenedor)
                return nodo_var
        else:
            return self.parse_statement()

    def parse_params(self):
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
                self.advance()
        return params

    def parse_classical_decls(self):
        tipos_params = {}
        while self.current() and self.current().type != 'LLAVE_IZQ':
            tok = self.current()
            if tok.type == 'RESERVADA' and tok.value in TIPOS_DATO:
                tipo = tok.value
                self.advance()
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
            self.parse_block()
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
        self.advance()

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
        tok = self.current()
        if not (tok and tok.type == 'PARENTESIS_IZQ'):
            pos = tok.pos_start if tok else len(self.source_code)
            self.add_error("Se esperaba '(' para la condición.", pos, pos + 1)
            return None

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

        tokens_cond = self.tokens[inicio:self.pos]

        if parens > 0:
            self.add_error("Falta cerrar paréntesis ')' en la condición.", tok.pos_start, tok.pos_start + 1)
        else:
            self.advance()

        return self.parse_expr_tokens(tokens_cond)

    def parse_statement(self):
        tok = self.current()
        if not tok:
            return None

        if tok.type == 'DIRECTIVA':
            self.advance()
            return None

        if tok.type == 'RESERVADA' and tok.value == 'using':
            while self.current() and self.current().type != 'PUNTO_Y_COMA':
                self.advance()
            if self.current() and self.current().type == 'PUNTO_Y_COMA':
                self.advance()
            return None

        if tok.type == 'LLAVE_DER':
            self.add_error("Se encontró una llave de cierre '}' inesperada. ¿Olvidaste abrir '{'?", tok.pos_start, tok.pos_end)
            self.advance()
            return None


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


        es_std_cin = False
        es_std_cout = False
        if tok.type == 'IDENTIFICADOR' and tok.value == 'std':
            if self.pos + 2 < len(self.tokens) and self.tokens[self.pos + 1].type == 'OP_RESOLUCION':
                if self.tokens[self.pos + 2].value == 'cout':
                    es_std_cout = True
                elif self.tokens[self.pos + 2].value == 'cin':
                    es_std_cin = True

        if (tok.type == 'RESERVADA' and tok.value == 'cin') or es_std_cin:
            nodo_cin = NodoAST("Entrada por Consola", "cin")
            nodo_cin.linea = self.line_of(tok.pos_start)
            if es_std_cin:
                self.advance()  # std
                self.advance()  # ::
                self.advance()  # cin
            else:
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

        elif (tok.type == 'RESERVADA' and tok.value == 'cout') or es_std_cout:
            nodo_cout = NodoAST("Salida por Consola", "cout")
            nodo_cout.linea = self.line_of(tok.pos_start)
            if es_std_cout:
                self.advance()  # std
                self.advance()  # ::
                self.advance()  # cout
            else:
                self.advance()

            inicio_scan = self.pos
            parens, brackets, stopped_by = self.scan_expression(stop_types=('PUNTO_Y_COMA', 'LLAVE_DER'))
            tokens_expr = self.tokens[inicio_scan:self.pos]

            if stopped_by == 'PUNTO_Y_COMA':
                self.advance()
                for parte in self._partir_por_flujo(tokens_expr):
                    nodo_parte = self.parse_expr_tokens(parte)
                    if nodo_parte:
                        nodo_cout.agregar_hijo(nodo_parte)
            else:
                self.add_error("Falta punto y coma ';' al final del cout.", tok.pos_start, tok.pos_end)

            return nodo_cout

        while tok and tok.type == 'RESERVADA' and tok.value in ('static', 'const', 'inline', 'virtual'):
            self.advance()
            tok = self.current()

        if not tok:
            return None

        if tok.type == 'RESERVADA' and tok.value in TIPOS_DATO:
            tipo_dato = tok.value
            linea_decl = self.line_of(tok.pos_start)
            self.advance()

            identificador = "desconocido"
            if self.current() and self.current().type == 'IDENTIFICADOR':
                identificador = self.current().value
                self.advance()

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
                nodo_expr = NodoAST("Expresión", start_tok.value)
                nodo_expr.linea = self.line_of(start_tok.pos_start)
            return nodo_expr


class SymbolTable:
    def __init__(self):
        self.scopes = [{}]
        self.scope_labels = ["global"]
        self.historial = []

    def enter_scope(self, label):
        self.scopes.append({})
        self.scope_labels.append(label)

    def exit_scope(self):
        self.scopes.pop()
        self.scope_labels.pop()

    def scope_actual(self):
        return self.scope_labels[-1]

    def declare(self, nombre, tipo, linea):
        ambito_actual = self.scopes[-1]
        if nombre in ambito_actual:
            return False
        info = {"nombre": nombre, "tipo": tipo, "ambito": self.scope_actual(), "linea": linea}
        ambito_actual[nombre] = info
        self.historial.append(info)
        return True

    def lookup(self, nombre):
        for ambito in reversed(self.scopes):
            if nombre in ambito:
                return ambito[nombre]
        return None


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

    def visitar_global(self, nodo):
        if nodo.etiqueta == "Función":
            self.visitar_funcion(nodo)
        elif nodo.etiqueta in ("Varaible Global", "Variable Global"):
            self.visitar_decl(nodo)
        elif nodo.etiqueta == "Clase":
            self.visitar_clase(nodo)
        elif nodo.etiqueta == "Directiva":
            pass
        else:
            self.visitar_statement(nodo)

    def visitar_clase(self, nodo):
        nombre_clase = nodo.valor
        self.tabla.enter_scope(f"clase {nombre_clase}")
        for hijo in nodo.hijos:
            if hijo.etiqueta == "Función":
                self.visitar_funcion(hijo, prefijo_clase=nombre_clase)
            elif hijo.etiqueta in ("Varaible Global", "Variable Global", "Declaración Local"):
                self.visitar_decl(hijo)
            elif hijo.etiqueta == "Directiva":
                pass
            else:
                self.visitar_statement(hijo)
        self.tabla.exit_scope()

    def visitar_funcion(self, nodo, prefijo_clase=None):
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

        if prefijo_clase:
            nombre_calificado = f"{prefijo_clase}::{nombre}"
            self.tabla.scopes[0][nombre_calificado] = {
                "nombre": nombre_calificado,
                "tipo": f"función → {tipo_retorno}",
                "ambito": "global",
                "linea": linea
            }
            self.tabla.historial.append({
                "nombre": nombre_calificado,
                "tipo": f"función → {tipo_retorno}",
                "ambito": "global",
                "linea": linea
            })

        self.tabla.enter_scope(f"función {nombre}")
        for p in parametros:
            ok_p = self.tabla.declare(p.valor, p.tipo, p.linea or linea)
            if not ok_p:
                self.error(p.linea or linea, f"el parámetro '{p.valor}' ya fue declarado (redeclaración)")

        tipo_anterior = self.tipo_retorno_actual
        self.tipo_retorno_actual = tipo_retorno
        if bloque:
            for hijo in bloque.hijos:
                self.visitar_statement(hijo)
        self.tipo_retorno_actual = tipo_anterior
        self.tabla.exit_scope()

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
        elif et == "Instrucción":
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
            self.tipo_de(nodo)

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
            if nodo.valor in ("endl", "std::endl"):
                return "string"
            info = self.tabla.lookup(nodo.valor)
            if info is None and "::" in nodo.valor:
                info = self.tabla.lookup(nodo.valor.split("::")[-1])
            if info is None:
                self.error(linea, f"variable '{nodo.valor}' no declarada")
                return None
            return info["tipo"]

        if et == "AccesoArreglo":
            info = self.tabla.lookup(nodo.valor)
            if info is None and "::" in nodo.valor:
                info = self.tabla.lookup(nodo.valor.split("::")[-1])
            if nodo.hijos:
                self.tipo_de(nodo.hijos[0])
            if info is None:
                self.error(linea, f"variable '{nodo.valor}' no declarada")
                return None
            return info["tipo"]

        if et == "Llamada":
            info = self.tabla.lookup(nodo.valor)
            if info is None and "::" in nodo.valor:
                info = self.tabla.lookup(nodo.valor.split("::")[-1])
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
                return "float"
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


def formatear_texto_conclusiones(text_widget, texto_raw):
    text_widget.config(state=tk.NORMAL)
    text_widget.delete("1.0", tk.END)

    text_widget.tag_configure("titulo_principal", font=("Segoe UI", 12, "bold"), foreground="#0D47A1", spacing1=8, spacing3=6)
    text_widget.tag_configure("seccion", font=("Segoe UI", 11, "bold"), foreground="#1565C0", spacing1=12, spacing3=4)
    text_widget.tag_configure("subseccion", font=("Segoe UI", 10, "bold"), foreground="#2E7D32", spacing1=8, spacing3=2)
    text_widget.tag_configure("vinetas", font=("Segoe UI", 10), foreground="#263238", spacing2=3)
    text_widget.tag_configure("explicacion", font=("Segoe UI", 10), foreground="#455A64", spacing2=3)
    text_widget.tag_configure("separador", font=("Segoe UI", 9), foreground="#CFD8DC")
    text_widget.tag_configure("normal", font=("Segoe UI", 10), foreground="#212121", spacing2=3)

    secciones_clave = {
        "RESUMEN DE LA OPTIMIZACIÓN",
        "IMPACTO EN EL RENDIMIENTO Y USO DE RECURSOS",
        "TÉCNICAS DE OPTIMIZACIÓN APLICADAS Y JUSTIFICACIÓN",
        "APORTE DEL GRAFO DE FLUJO DE CONTROL (CFG)",
        "CONCLUSIÓN FORMAL"
    }

    subsecciones_prefijos = (
        "1. Plegado", "2. Propagación", "3. Eliminación de Subexpresiones",
        "4. Eliminación de Código Muerto", "5. Eliminación de Bloques",
        "• Inspección completada"
    )

    lineas = texto_raw.split("\n")
    for linea in lineas:
        linea_strip = linea.strip()
        if "PRESENTACIÓN DE RESULTADOS" in linea or "CONCLUSIONES" in linea:
            text_widget.insert(tk.END, "  " + linea_strip + "\n", "titulo_principal")
        elif linea_strip.startswith("===") or linea_strip.startswith("---"):
            text_widget.insert(tk.END, "  " + "—" * 65 + "\n", "separador")
        elif linea_strip in secciones_clave:
            text_widget.insert(tk.END, "\n  " + linea_strip + "\n", "seccion")
        elif any(linea_strip.startswith(p) for p in subsecciones_prefijos):
            text_widget.insert(tk.END, "  " + linea_strip + "\n", "subseccion")
        elif linea.startswith("     "):
            text_widget.insert(tk.END, "    " + linea_strip + "\n", "explicacion")
        elif linea.startswith("  •") or linea.startswith("  1.") or linea.startswith("  2.") or linea.startswith("  3."):
            text_widget.insert(tk.END, "    " + linea_strip + "\n", "vinetas")
        else:
            if linea_strip:
                text_widget.insert(tk.END, "    " + linea_strip + "\n", "normal")
            else:
                text_widget.insert(tk.END, "\n")

    text_widget.config(state=tk.DISABLED)


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Compilador C++ | Léxico, Sintáctico, Semántico y Código Intermedio (IR)")
        self.root.geometry("1060x780")
        self.root.minsize(920, 640)

        self.ultimo_ast = None
        self.ultimo_optimizador = None
        self.ultimo_cfg_vista = "original"
        self.ultimo_resultado_objeto = None

        top_frame = tk.Frame(self.root)
        top_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        header_editor = tk.Frame(top_frame)
        header_editor.pack(fill=tk.X, pady=(0, 5))

        tk.Label(header_editor, text="Código Fuente (C++):", font=("Arial", 11, "bold"), fg="#1A237E").pack(side=tk.LEFT)

        self.ejemplos = {
            "1. Aritmética básica (x = 3 + 4 * 2;)": "int x = 3 + 4 * 2;\ncout << x;",
            "2. Precedencia con resta (y = 8 - 2 * 3;)": "int y = 8 - 2 * 3;\ncout << y;",
            "3. Paréntesis modifican precedencia ((8 - 2) * 3)": "int res = (8 - 2) * 3;\ncout << res;",
            "4. Condicional (if - else)": "int a = 10;\nint b = 5;\nint x;\nif (a > b) {\n    x = 1;\n} else {\n    x = 2;\n}\ncout << x;",
            "5. Ciclo While": "int x = 0;\nwhile (x < 10) {\n    x = x + 1;\n}\ncout << x;",
            "6. Ciclo For con salida": "int i;\nfor (i = 0; i < 5; i = i + 1) {\n    cout << i;\n}",
            "7. Operador Ternario": "int x = 5;\nint res = (x > 0) ? 10 : 20;\ncout << res;",
            "8. Función con retorno": "int a = 3;\nint b = 4;\nint res = a + b;\ncout << res;\nreturn res;",
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
cout << y;
return y;
w = 200;""",
            "11. Plegado y Subexpresiones (CSE)": """int a = 2 + 3;
int b = 4 * 5;
int c = a + b;
int d = a + b;
int e = c * 2;
cout << e;""",
            "12. Control de Flujo y Código Inalcanzable": """int x = 10;
int y;
if (x > 5) {
    y = 100;
} else {
    y = 200;
}
cout << y;
return y;
y = 999;""",
            "13. Clase y Función (CodigoIntermedio)": """#include <iostream>

class CodigoIntermedio {
public:
    static int ejecutar() {
        int a = 5;
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
        cout << y;
        return y;
        // Código inalcanzable:
        // w = 200;
    }
};

int main() {
    std::cout << CodigoIntermedio::ejecutar() << std::endl;
    return 0;
}""",
            "14. Código Objeto y Ciclo While (U4)": """int sum = 0;
int i = 1;
while (i <= 5) {
    sum = sum + i;
    i = i + 1;
}
cout << sum;""",
            "15. Reutilización de Registros (Coloración Óptima)": """int a = 5;
int b = 10;
int c = a + b;
int d = c * 2;
int e = d - 5;
cout << e;"""
        }

        tk.Label(header_editor, text="Cargar caso de prueba:", font=("Arial", 10), fg="#555").pack(side=tk.RIGHT, padx=(5, 5))
        self.combo_ejemplos = ttk.Combobox(header_editor, values=list(self.ejemplos.keys()), state="readonly", width=38)
        self.combo_ejemplos.pack(side=tk.RIGHT)
        self.combo_ejemplos.set("1. Aritmética básica (x = 3 + 4 * 2;)")
        self.combo_ejemplos.bind("<<ComboboxSelected>>", self.cargar_ejemplo_seleccionado)

        self.text_area = tk.Text(top_frame, height=13, font=("Consolas", 12))
        self.text_area.pack(fill=tk.BOTH, expand=True)
        self.text_area.tag_configure("error", background="red", foreground="white")

        self.text_area.insert(tk.END, self.ejemplos["1. Aritmética básica (x = 3 + 4 * 2;)"])

        mid_frame = tk.Frame(self.root, bg="#F5F5F5", relief=tk.GROOVE, bd=1, padx=6, pady=4)
        mid_frame.pack(fill=tk.X, padx=10, pady=4)

        # Fila 1: Análisis y Código Intermedio
        row1_frame = tk.Frame(mid_frame, bg="#F5F5F5")
        row1_frame.pack(fill=tk.X, pady=(2, 3))

        lbl_r1 = tk.Label(row1_frame, text="Análisis & IR:", font=("Segoe UI", 9, "bold"), fg="#37474F", bg="#F5F5F5", width=18, anchor="w")
        lbl_r1.pack(side=tk.LEFT, padx=(4, 6))

        btn_lexico = tk.Button(row1_frame, text="Análisis Léxico", command=self.analisis_lexico,
                               bg="#4CAF50", fg="white", font=("Segoe UI", 9, "bold"), padx=8, pady=2, relief=tk.RAISED, cursor="hand2")
        btn_lexico.pack(side=tk.LEFT, padx=3)

        btn_sintactico = tk.Button(row1_frame, text="Análisis Sintáctico", command=self.analisis_sintactico,
                                   bg="#2196F3", fg="white", font=("Segoe UI", 9, "bold"), padx=8, pady=2, relief=tk.RAISED, cursor="hand2")
        btn_sintactico.pack(side=tk.LEFT, padx=3)

        btn_semantico = tk.Button(row1_frame, text="Análisis Semántico", command=self.analisis_semantico,
                                  bg="#FF9800", fg="white", font=("Segoe UI", 9, "bold"), padx=8, pady=2, relief=tk.RAISED, cursor="hand2")
        btn_semantico.pack(side=tk.LEFT, padx=3)

        self.btn_arbol = tk.Button(row1_frame, text="Ver AST", command=self.ver_arbol_sintactico,
                                    bg="#9C27B0", fg="white", font=("Segoe UI", 9, "bold"), padx=8, pady=2, state=tk.DISABLED, relief=tk.RAISED, cursor="hand2")
        self.btn_arbol.pack(side=tk.LEFT, padx=3)

        btn_ir = tk.Button(row1_frame, text="Código Intermedio (IR)", command=self.analisis_codigo_intermedio,
                           bg="#673AB7", fg="white", font=("Segoe UI", 9, "bold"), padx=8, pady=2, relief=tk.RAISED, cursor="hand2")
        btn_ir.pack(side=tk.LEFT, padx=3)

        # Fila 2: Optimización y Código Objeto
        row2_frame = tk.Frame(mid_frame, bg="#F5F5F5")
        row2_frame.pack(fill=tk.X, pady=(2, 2))

        lbl_r2 = tk.Label(row2_frame, text="Optimización & Objeto:", font=("Segoe UI", 9, "bold"), fg="#37474F", bg="#F5F5F5", width=18, anchor="w")
        lbl_r2.pack(side=tk.LEFT, padx=(4, 6))

        btn_opt = tk.Button(row2_frame, text="Optimización (CFG / IR)", command=self.analisis_optimizacion,
                            bg="#E91E63", fg="white", font=("Segoe UI", 9, "bold"), padx=8, pady=2, relief=tk.RAISED, cursor="hand2")
        btn_opt.pack(side=tk.LEFT, padx=3)

        btn_col = tk.Button(row2_frame, text="Coloración de Grafos", command=self.mostrar_coloracion_grafos,
                            bg="#00897B", fg="white", font=("Segoe UI", 9, "bold"), padx=8, pady=2, relief=tk.RAISED, cursor="hand2")
        btn_col.pack(side=tk.LEFT, padx=3)

        btn_codegen = tk.Button(row2_frame, text="Código Objeto (.asm)", command=self.generar_codigo_objeto,
                                bg="#3F51B5", fg="white", font=("Segoe UI", 9, "bold"), padx=8, pady=2, relief=tk.RAISED, cursor="hand2")
        btn_codegen.pack(side=tk.LEFT, padx=3)

        btn_exec = tk.Button(row2_frame, text="Ejecutar Objeto", command=self.ejecutar_codigo_objeto,
                             bg="#00796B", fg="white", font=("Segoe UI", 9, "bold"), padx=8, pady=2, relief=tk.RAISED, cursor="hand2")
        btn_exec.pack(side=tk.LEFT, padx=3)

        btn_full = tk.Button(row2_frame, text="Compilar Todo", command=self.compilar_todo_completo,
                             bg="#C2185B", fg="white", font=("Segoe UI", 9, "bold"), padx=10, pady=2, relief=tk.RAISED, cursor="hand2")
        btn_full.pack(side=tk.LEFT, padx=3)

        bottom_frame = tk.Frame(self.root)
        bottom_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.main_notebook = ttk.Notebook(bottom_frame)
        self.main_notebook.pack(fill=tk.BOTH, expand=True)

        self.tab_tokens = ttk.Frame(self.main_notebook)
        self.main_notebook.add(self.tab_tokens, text=" Tokens Léxicos ")

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

        self.tab_cuads = ttk.Frame(self.main_notebook)
        self.main_notebook.add(self.tab_cuads, text=" Cuádruplos (IR) ")

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

        self.tab_3ac = ttk.Frame(self.main_notebook)
        self.main_notebook.add(self.tab_3ac, text=" Tres Direcciones (3AC) ")

        scroll_3ac_y = ttk.Scrollbar(self.tab_3ac)
        scroll_3ac_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.txt_main_3ac = tk.Text(self.tab_3ac, font=("Consolas", 11), yscrollcommand=scroll_3ac_y.set, bg="#FAFAFA")
        self.txt_main_3ac.pack(fill=tk.BOTH, expand=True)
        scroll_3ac_y.config(command=self.txt_main_3ac.yview)

        self.tab_post = ttk.Frame(self.main_notebook)
        self.main_notebook.add(self.tab_post, text=" Notación Postfija ")

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

        self.tab_simbolos = ttk.Frame(self.main_notebook)
        self.main_notebook.add(self.tab_simbolos, text=" Tabla de Símbolos ")

        cols_simb = ("Nombre", "Tipo", "Ámbito", "Línea")
        self.tv_main_simbolos = ttk.Treeview(self.tab_simbolos, columns=cols_simb, show="headings")
        for c in cols_simb:
            self.tv_main_simbolos.heading(c, text=c)
            self.tv_main_simbolos.column(c, width=80 if c == "Línea" else 160)

        scroll_simb_y = ttk.Scrollbar(self.tab_simbolos, orient=tk.VERTICAL, command=self.tv_main_simbolos.yview)
        self.tv_main_simbolos.configure(yscrollcommand=scroll_simb_y.set)
        scroll_simb_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.tv_main_simbolos.pack(fill=tk.BOTH, expand=True)

        self.tab_bb = ttk.Frame(self.main_notebook)
        self.main_notebook.add(self.tab_bb, text=" Bloques Básicos ")

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

        self.tab_cfg = ttk.Frame(self.main_notebook)
        self.main_notebook.add(self.tab_cfg, text=" Grafo de Flujo (CFG) ")

        cfg_ctrl_frame = tk.Frame(self.tab_cfg, bg="#EEEEEE", pady=4, padx=8)
        cfg_ctrl_frame.pack(fill=tk.X)

        self.btn_toggle_cfg_orig = tk.Button(
            cfg_ctrl_frame, text="Ver CFG Original",
            command=lambda: self._conmutar_vista_cfg("original"),
            bg="#1565C0", fg="white", font=("Arial", 9, "bold"), padx=8
        )
        self.btn_toggle_cfg_orig.pack(side=tk.LEFT, padx=3)

        self.btn_toggle_cfg_opt = tk.Button(
            cfg_ctrl_frame, text="Ver CFG Optimizado",
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

        self.tab_sucesores = ttk.Frame(self.main_notebook)
        self.main_notebook.add(self.tab_sucesores, text=" Tabla de Sucesores ")

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

        self.tab_ir_opt = ttk.Frame(self.main_notebook)
        self.main_notebook.add(self.tab_ir_opt, text=" IR Optimizado ")

        sub_nb_opt = ttk.Notebook(self.tab_ir_opt)
        sub_nb_opt.pack(fill=tk.BOTH, expand=True)

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

        tab_opt_3ac = ttk.Frame(sub_nb_opt)
        sub_nb_opt.add(tab_opt_3ac, text=" 3AC Optimizado ")
        scroll_opt_3ac = ttk.Scrollbar(tab_opt_3ac)
        scroll_opt_3ac.pack(side=tk.RIGHT, fill=tk.Y)
        self.txt_main_opt_3ac = tk.Text(tab_opt_3ac, font=("Consolas", 11), yscrollcommand=scroll_opt_3ac.set, bg="#F9FBE7")
        self.txt_main_opt_3ac.pack(fill=tk.BOTH, expand=True)
        scroll_opt_3ac.config(command=self.txt_main_opt_3ac.yview)

        tab_opt_diff = ttk.Frame(sub_nb_opt)
        sub_nb_opt.add(tab_opt_diff, text=" Comparativa (Antes vs Después) ")
        scroll_opt_diff = ttk.Scrollbar(tab_opt_diff)
        scroll_opt_diff.pack(side=tk.RIGHT, fill=tk.Y)
        self.txt_main_diff = tk.Text(tab_opt_diff, font=("Consolas", 10), yscrollcommand=scroll_opt_diff.set, bg="#FAFAFA")
        self.txt_main_diff.pack(fill=tk.BOTH, expand=True)
        scroll_opt_diff.config(command=self.txt_main_diff.yview)

        self.tab_transf = ttk.Frame(self.main_notebook)
        self.main_notebook.add(self.tab_transf, text=" Tabla de Transformaciones ")

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

        self.tab_metricas = ttk.Frame(self.main_notebook)
        self.main_notebook.add(self.tab_metricas, text=" Métricas y Análisis ")

        cards_frame_main = tk.Frame(self.tab_metricas, bg="#ECEFF1", padx=8, pady=6)
        cards_frame_main.pack(fill=tk.X)

        def _crear_card_main(parent, titulo, col="#1565C0"):
            c = tk.Frame(parent, bg="#FFFFFF", relief=tk.SOLID, bd=1, padx=10, pady=5)
            c.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4)
            tk.Label(c, text=titulo.upper(), font=("Segoe UI", 8, "bold"), fg="#78909C", bg="#FFFFFF").pack(anchor="w")
            val = tk.Label(c, text="—", font=("Segoe UI", 14, "bold"), fg=col, bg="#FFFFFF")
            val.pack(anchor="w")
            sub = tk.Label(c, text="Sin datos", font=("Segoe UI", 8), fg="#90A4AE", bg="#FFFFFF")
            sub.pack(anchor="w")
            return val, sub

        self.card_main_red_val, self.card_main_red_sub = _crear_card_main(cards_frame_main, "Reducción", "#2E7D32")
        self.card_main_inst_val, self.card_main_inst_sub = _crear_card_main(cards_frame_main, "Instrucciones", "#1565C0")
        self.card_main_temps_val, self.card_main_temps_sub = _crear_card_main(cards_frame_main, "Temporales", "#6A1B9A")
        self.card_main_cfg_val, self.card_main_cfg_sub = _crear_card_main(cards_frame_main, "Caminos CFG", "#00838F")

        sub_nb_met = ttk.Notebook(self.tab_metricas)
        sub_nb_met.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        tab_sub_human = ttk.Frame(sub_nb_met)
        sub_nb_met.add(tab_sub_human, text=" Conclusiones y Resumen ")

        frame_human = tk.Frame(tab_sub_human)
        frame_human.pack(fill=tk.BOTH, expand=True)
        sb_human_y = ttk.Scrollbar(frame_human, orient=tk.VERTICAL)
        sb_human_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.txt_main_conclusiones = tk.Text(
            frame_human, font=("Segoe UI", 10), yscrollcommand=sb_human_y.set,
            bg="#FFFFFF", padx=15, pady=10, relief=tk.FLAT
        )
        self.txt_main_conclusiones.pack(fill=tk.BOTH, expand=True)
        sb_human_y.config(command=self.txt_main_conclusiones.yview)

        tab_sub_formal = ttk.Frame(sub_nb_met)
        sub_nb_met.add(tab_sub_formal, text=" Reporte Formal y Tablas ")

        frame_formal = tk.Frame(tab_sub_formal)
        frame_formal.pack(fill=tk.BOTH, expand=True)
        sb_formal_y = ttk.Scrollbar(frame_formal, orient=tk.VERTICAL)
        sb_formal_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.txt_main_metricas = tk.Text(
            frame_formal, font=("Consolas", 10), yscrollcommand=sb_formal_y.set,
            bg="#FAFAFA", padx=10, pady=8
        )
        self.txt_main_metricas.pack(fill=tk.BOTH, expand=True)
        sb_formal_y.config(command=self.txt_main_metricas.yview)

        # Pestaña de Coloración de Grafos
        self.tab_coloracion = ttk.Frame(self.main_notebook)
        self.main_notebook.add(self.tab_coloracion, text=" Coloración de Grafos ")
        self.seccion_coloracion = SeccionColoracionGrafos(self.tab_coloracion, root_app=self)
        self.seccion_coloracion.pack(fill=tk.BOTH, expand=True)

        # -------------------------------------------------------------
        # Pestaña: Tabla de Asignación de Registros (Unidad 4)
        # -------------------------------------------------------------
        self.tab_registros = ttk.Frame(self.main_notebook)
        self.main_notebook.add(self.tab_registros, text=" Tabla de Registros ")

        cards_frame_reg = tk.Frame(self.tab_registros, bg="#EDE7F6", padx=8, pady=6)
        cards_frame_reg.pack(fill=tk.X)

        def _crear_card_reg(parent, titulo, col="#512DA8"):
            c = tk.Frame(parent, bg="#FFFFFF", relief=tk.SOLID, bd=1, padx=10, pady=5)
            c.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4)
            tk.Label(c, text=titulo.upper(), font=("Segoe UI", 8, "bold"), fg="#7E57C2", bg="#FFFFFF").pack(anchor="w")
            val = tk.Label(c, text="—", font=("Segoe UI", 14, "bold"), fg=col, bg="#FFFFFF")
            val.pack(anchor="w")
            sub = tk.Label(c, text="Sin datos", font=("Segoe UI", 8), fg="#9E9E9E", bg="#FFFFFF")
            sub.pack(anchor="w")
            return val, sub

        self.card_reg_vars_val, self.card_reg_vars_sub = _crear_card_reg(cards_frame_reg, "Total Variables", "#311B92")
        self.card_reg_chi_val, self.card_reg_chi_sub = _crear_card_reg(cards_frame_reg, "Número Cromático", "#00796B")
        self.card_reg_regs_val, self.card_reg_regs_sub = _crear_card_reg(cards_frame_reg, "Registros x86 Usados", "#1565C0")
        self.card_reg_spills_val, self.card_reg_spills_sub = _crear_card_reg(cards_frame_reg, "Derrames (Spills)", "#D84315")

        frame_tabla_reg = tk.Frame(self.tab_registros)
        frame_tabla_reg.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        cols_reg = ("Variable", "Tipo", "Rango de Vida", "Grado", "Interfiere Con", "Color", "Virtual", "Reg. x86", "Ubicación")
        self.tv_main_registros = ttk.Treeview(frame_tabla_reg, columns=cols_reg, show="headings")
        self.tv_main_registros.heading("Variable", text="Variable / Temporal")
        self.tv_main_registros.heading("Tipo", text="Tipo")
        self.tv_main_registros.heading("Rango de Vida", text="Rango de Vida")
        self.tv_main_registros.heading("Grado", text="Grado")
        self.tv_main_registros.heading("Interfiere Con", text="Variables con Interferencia")
        self.tv_main_registros.heading("Color", text="Color chi")
        self.tv_main_registros.heading("Virtual", text="Reg. Virtual")
        self.tv_main_registros.heading("Reg. x86", text="Reg. Físico x86")
        self.tv_main_registros.heading("Ubicación", text="Ubicación Asignada")

        self.tv_main_registros.column("Variable", width=120, anchor="center")
        self.tv_main_registros.column("Tipo", width=100, anchor="center")
        self.tv_main_registros.column("Rango de Vida", width=110, anchor="center")
        self.tv_main_registros.column("Grado", width=60, anchor="center")
        self.tv_main_registros.column("Interfiere Con", width=220, anchor="w")
        self.tv_main_registros.column("Color", width=110, anchor="center")
        self.tv_main_registros.column("Virtual", width=90, anchor="center")
        self.tv_main_registros.column("Reg. x86", width=100, anchor="center")
        self.tv_main_registros.column("Ubicación", width=160, anchor="center")

        sb_reg_y = ttk.Scrollbar(frame_tabla_reg, orient=tk.VERTICAL, command=self.tv_main_registros.yview)
        sb_reg_x = ttk.Scrollbar(frame_tabla_reg, orient=tk.HORIZONTAL, command=self.tv_main_registros.xview)
        self.tv_main_registros.configure(yscrollcommand=sb_reg_y.set, xscrollcommand=sb_reg_x.set)
        sb_reg_y.pack(side=tk.RIGHT, fill=tk.Y)
        sb_reg_x.pack(side=tk.BOTTOM, fill=tk.X)
        self.tv_main_registros.pack(fill=tk.BOTH, expand=True)

        bar_bot_reg = tk.Frame(self.tab_registros, bg="#F5F5F5", padx=8, pady=5)
        bar_bot_reg.pack(fill=tk.X)
        btn_g_reg = tk.Button(bar_bot_reg, text="Guardar Tabla (.txt)", command=self.guardar_tabla_registros,
                              bg="#4A148C", fg="white", font=("Arial", 9, "bold"))
        btn_g_reg.pack(side=tk.LEFT, padx=4)
        btn_c_reg = tk.Button(bar_bot_reg, text="Copiar Tabla", command=self.copiar_tabla_registros,
                              bg="#5C6BC0", fg="white", font=("Arial", 9, "bold"))
        btn_c_reg.pack(side=tk.LEFT, padx=4)
        btn_ver_grafo = tk.Button(bar_bot_reg, text="Ver Grafo en Coloración", command=self.mostrar_coloracion_grafos,
                                  bg="#00695C", fg="white", font=("Arial", 9, "bold"))
        btn_ver_grafo.pack(side=tk.LEFT, padx=4)

        # -------------------------------------------------------------
        # Pestaña: Código Objeto Ensamblador (.asm) (Unidad 4)
        # -------------------------------------------------------------
        self.tab_asm = ttk.Frame(self.main_notebook)
        self.main_notebook.add(self.tab_asm, text=" Código Objeto (.asm) ")

        bar_top_asm = tk.Frame(self.tab_asm, bg="#E8EAF6", padx=8, pady=5)
        bar_top_asm.pack(fill=tk.X)

        btn_g_asm = tk.Button(bar_top_asm, text="Guardar Archivo .asm", command=self.guardar_codigo_asm,
                              bg="#283593", fg="white", font=("Arial", 9, "bold"))
        btn_g_asm.pack(side=tk.LEFT, padx=4)

        btn_run_asm = tk.Button(bar_top_asm, text="Ejecutar en Simulador", command=self.ejecutar_codigo_objeto,
                                bg="#2E7D32", fg="white", font=("Arial", 9, "bold"))
        btn_run_asm.pack(side=tk.LEFT, padx=4)

        btn_c_asm = tk.Button(bar_top_asm, text="Copiar Código .asm", command=self.copiar_codigo_asm,
                              bg="#455A64", fg="white", font=("Arial", 9, "bold"))
        btn_c_asm.pack(side=tk.LEFT, padx=4)

        self.lbl_asm_status = tk.Label(bar_top_asm, text="Listo para compilar código objeto.", font=("Segoe UI", 9), bg="#E8EAF6", fg="#37474F")
        self.lbl_asm_status.pack(side=tk.RIGHT, padx=6)

        frame_txt_asm = tk.Frame(self.tab_asm)
        frame_txt_asm.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        sb_asm_y = ttk.Scrollbar(frame_txt_asm, orient=tk.VERTICAL)
        sb_asm_x = ttk.Scrollbar(frame_txt_asm, orient=tk.HORIZONTAL)
        self.txt_main_asm = tk.Text(
            frame_txt_asm, font=("Consolas", 11), yscrollcommand=sb_asm_y.set, xscrollcommand=sb_asm_x.set,
            bg="#212121", fg="#ECEFF1", insertbackground="white", padx=10, pady=8, wrap="none"
        )
        sb_asm_y.config(command=self.txt_main_asm.yview)
        sb_asm_x.config(command=self.txt_main_asm.xview)
        sb_asm_y.pack(side=tk.RIGHT, fill=tk.Y)
        sb_asm_x.pack(side=tk.BOTTOM, fill=tk.X)
        self.txt_main_asm.pack(fill=tk.BOTH, expand=True)

        # -------------------------------------------------------------
        # Pestaña: Evidencia de Ejecución (Unidad 4)
        # -------------------------------------------------------------
        self.tab_ejecucion = ttk.Frame(self.main_notebook)
        self.main_notebook.add(self.tab_ejecucion, text=" Evidencia de Ejecución ")

        cards_frame_exec = tk.Frame(self.tab_ejecucion, bg="#E0F2F1", padx=8, pady=6)
        cards_frame_exec.pack(fill=tk.X)

        self.card_exec_status_val, self.card_exec_status_sub = _crear_card_reg(cards_frame_exec, "Estado de Ejecución", "#00796B")
        self.card_exec_ret_val, self.card_exec_ret_sub = _crear_card_reg(cards_frame_exec, "Código de Retorno", "#1565C0")
        self.card_exec_steps_val, self.card_exec_steps_sub = _crear_card_reg(cards_frame_exec, "Instrucciones Simuladas", "#E65100")

        paned_exec = ttk.PanedWindow(self.tab_ejecucion, orient=tk.HORIZONTAL)
        paned_exec.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        frame_left_exec = tk.Frame(paned_exec, bg="#121212")
        paned_exec.add(frame_left_exec, weight=3)

        tk.Label(frame_left_exec, text="Consola de Salida Estándar (STDOUT):", font=("Segoe UI", 9, "bold"),
                 bg="#1E1E1E", fg="#A7FFEB", padx=8, pady=4).pack(fill=tk.X)

        sb_out_y = ttk.Scrollbar(frame_left_exec, orient=tk.VERTICAL)
        self.txt_main_salida_stdout = tk.Text(
            frame_left_exec, font=("Consolas", 11, "bold"), yscrollcommand=sb_out_y.set,
            bg="#0A0E17", fg="#00E676", insertbackground="white", padx=10, pady=8
        )
        sb_out_y.config(command=self.txt_main_salida_stdout.yview)
        sb_out_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.txt_main_salida_stdout.pack(fill=tk.BOTH, expand=True)

        frame_right_exec = tk.Frame(paned_exec)
        paned_exec.add(frame_right_exec, weight=2)

        nb_cpu_mem = ttk.Notebook(frame_right_exec)
        nb_cpu_mem.pack(fill=tk.BOTH, expand=True)

        tab_cpu = ttk.Frame(nb_cpu_mem)
        nb_cpu_mem.add(tab_cpu, text=" Registros CPU ")
        cols_cpu = ("Registro", "Valor Decimal", "Hexadecimal")
        self.tv_regs_cpu = ttk.Treeview(tab_cpu, columns=cols_cpu, show="headings")
        self.tv_regs_cpu.heading("Registro", text="Registro")
        self.tv_regs_cpu.heading("Valor Decimal", text="Valor")
        self.tv_regs_cpu.heading("Hexadecimal", text="Hexadecimal")
        self.tv_regs_cpu.column("Registro", width=70, anchor="center")
        self.tv_regs_cpu.column("Valor Decimal", width=90, anchor="center")
        self.tv_regs_cpu.column("Hexadecimal", width=110, anchor="center")
        sb_cpu_y = ttk.Scrollbar(tab_cpu, orient=tk.VERTICAL, command=self.tv_regs_cpu.yview)
        self.tv_regs_cpu.configure(yscrollcommand=sb_cpu_y.set)
        sb_cpu_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.tv_regs_cpu.pack(fill=tk.BOTH, expand=True)

        tab_mem = ttk.Frame(nb_cpu_mem)
        nb_cpu_mem.add(tab_mem, text=" Memoria (.BSS) ")
        cols_mem = ("Variable", "Valor")
        self.tv_mem_bss = ttk.Treeview(tab_mem, columns=cols_mem, show="headings")
        self.tv_mem_bss.heading("Variable", text="Variable")
        self.tv_mem_bss.heading("Valor", text="Valor en Memoria")
        self.tv_mem_bss.column("Variable", width=120, anchor="center")
        self.tv_mem_bss.column("Valor", width=120, anchor="center")
        sb_mem_y = ttk.Scrollbar(tab_mem, orient=tk.VERTICAL, command=self.tv_mem_bss.yview)
        self.tv_mem_bss.configure(yscrollcommand=sb_mem_y.set)
        sb_mem_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.tv_mem_bss.pack(fill=tk.BOTH, expand=True)

        tab_full_rep = ttk.Frame(nb_cpu_mem)
        nb_cpu_mem.add(tab_full_rep, text=" Informe Formal ")
        sb_rep_exec_y = ttk.Scrollbar(tab_full_rep, orient=tk.VERTICAL)
        self.txt_reporte_ejecucion = tk.Text(
            tab_full_rep, font=("Consolas", 9), yscrollcommand=sb_rep_exec_y.set,
            bg="#FAFAFA", padx=8, pady=6
        )
        sb_rep_exec_y.config(command=self.txt_reporte_ejecucion.yview)
        sb_rep_exec_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.txt_reporte_ejecucion.pack(fill=tk.BOTH, expand=True)

        bar_bot_exec = tk.Frame(self.tab_ejecucion, bg="#F5F5F5", padx=8, pady=5)
        bar_bot_exec.pack(fill=tk.X)
        btn_exp_u4 = tk.Button(bar_bot_exec, text="Exportar Evidencias (.txt)", command=self.exportar_evidencias_u4,
                               bg="#00695C", fg="white", font=("Arial", 9, "bold"))
        btn_exp_u4.pack(side=tk.LEFT, padx=4)
        btn_c_out = tk.Button(bar_bot_exec, text="Copiar Salida", command=self.copiar_salida_consola,
                              bg="#546E7A", fg="white", font=("Arial", 9, "bold"))
        btn_c_out.pack(side=tk.LEFT, padx=4)

    def mostrar_coloracion_grafos(self):
        self.main_notebook.select(self.tab_coloracion)

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

        for err in parser.errors:
            self.resaltar_error(codigo, err.pos_start, err.pos_end)

        mensaje = f"Se encontraron {len(parser.errors)} error(es):\n\n"
        for i, err in enumerate(parser.errors, 1):
            fila_col = self.index_to_tk_public(codigo, err.pos_start)
            mensaje += f"{i}. (línea {fila_col}) {err.message}\n"
        messagebox.showerror("Errores de Sintaxis", mensaje)

    def analisis_semantico(self):
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

        for item in self.tv_main_simbolos.get_children():
            self.tv_main_simbolos.delete(item)
        for info in tabla.historial:
            self.tv_main_simbolos.insert("", tk.END, values=(info["nombre"], info["tipo"], info["ambito"], info["linea"]))
        self.main_notebook.select(self.tab_simbolos)

    def analisis_codigo_intermedio(self):
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

        self.txt_main_3ac.config(state=tk.NORMAL)
        self.txt_main_3ac.delete("1.0", tk.END)
        self.txt_main_3ac.insert(tk.END, generador.obtener_texto_3ac())
        self.txt_main_3ac.config(state=tk.DISABLED)

        for item in self.tv_main_post.get_children():
            self.tv_main_post.delete(item)
        if postfijas:
            for p in postfijas:
                self.tv_main_post.insert("", tk.END, values=(p["linea"], p["infija"], p["postfija"]))
        else:
            self.tv_main_post.insert("", tk.END, values=("—", "Sin expresiones evaluadas", "—"))

        self.main_notebook.select(self.tab_cuads)

        self.mostrar_resultado_ir(instrucciones, postfijas, generador)

    def mostrar_resultado_ir(self, instrucciones, postfijas, generador):
        ventana = tk.Toplevel(self.root)
        ventana.title("Generación de Código Intermedio (IR)")
        ventana.geometry("900x570")
        ventana.minsize(780, 460)

        header_frame = tk.Frame(ventana, bg="#EDE7F6", padx=15, pady=8)
        header_frame.pack(side=tk.TOP, fill=tk.X)
        tk.Label(header_frame, text="Código Intermedio (IR)", font=("Arial", 12, "bold"),
                 bg="#EDE7F6", fg="#4A148C").pack(anchor="w")
        tk.Label(header_frame, text="Del AST validado a instrucciones simples (Triplos, Cuádruplos y Postfija)",
                 font=("Arial", 8), bg="#EDE7F6", fg="#6A1B9A").pack(anchor="w")

        texto_ir_completo = generador.obtener_texto_ir()

        bottom_frame = tk.Frame(ventana, bg="#F5F5F5", pady=6, padx=12)
        bottom_frame.pack(side=tk.BOTTOM, fill=tk.X)

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

        btn_guardar = tk.Button(bottom_frame, text="Guardar archivo .ir", command=guardar_archivo_ir,
                                bg="#4CAF50", fg="white", font=("Arial", 9, "bold"), width=18, pady=4)
        btn_guardar.pack(side=tk.LEFT, padx=4)

        btn_copiar = tk.Button(bottom_frame, text="Copiar código .ir", command=copiar_al_portapapeles,
                               bg="#2196F3", fg="white", font=("Arial", 9, "bold"), width=18, pady=4)
        btn_copiar.pack(side=tk.LEFT, padx=4)

        btn_opt_ir = tk.Button(bottom_frame, text="Optimizar IR (CFG)",
                               command=lambda: [ventana.destroy(), self.analisis_optimizacion()],
                               bg="#E91E63", fg="white", font=("Arial", 9, "bold"), width=18, pady=4)
        btn_opt_ir.pack(side=tk.LEFT, padx=4)

        btn_cerrar = tk.Button(bottom_frame, text="Cerrar", command=ventana.destroy,
                               bg="#757575", fg="white", font=("Arial", 9, "bold"), width=10, pady=4)
        btn_cerrar.pack(side=tk.RIGHT, padx=4)

        notebook = ttk.Notebook(ventana)
        notebook.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=(2, 4))

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

        opt = IROptimizer(instrucciones)
        opt.optimizar()
        self.ultimo_optimizador = opt

        self._actualizar_pestanas_optimizacion(opt)

        self.main_notebook.select(self.tab_cfg)

        self.mostrar_resultado_optimizacion(opt)

    def _actualizar_pestanas_optimizacion(self, opt: IROptimizer):
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

        self.main_cfg_canvas.dibujar_cfg(opt.cfg_original if self.ultimo_cfg_vista == "original" else opt.cfg_optimizado)

        for item in self.tv_main_sucesores.get_children():
            self.tv_main_sucesores.delete(item)
        for fila in opt.cfg_original.obtener_tabla_sucesores():
            estado = "Inalcanzable" if fila["es_inalcanzable"] else "Flujo Activo"
            self.tv_main_sucesores.insert("", tk.END, values=(
                fila["bloque"],
                fila["sucesores"],
                estado
            ))

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

        self.txt_main_opt_3ac.config(state=tk.NORMAL)
        self.txt_main_opt_3ac.delete("1.0", tk.END)
        for inst in opt.instrucciones_optimizadas:
            self.txt_main_opt_3ac.insert(tk.END, f"{inst.numero}: {inst.to_3ac()}\n")
        self.txt_main_opt_3ac.config(state=tk.DISABLED)

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

        reporte = OptimizationReport(opt)
        stats = reporte.obtener_resumen_estadistico()

        red = stats["porcentaje_reduccion"]
        col_red = "#2E7D32" if red > 0 else "#546E7A"
        signo = f"-{red:.1f}%" if red > 0 else "0.0%"
        self.card_main_red_val.config(text=signo, fg=col_red)
        self.card_main_red_sub.config(
            text=f"{stats['instrucciones_eliminadas']} eliminadas" if red > 0 else "Código ya óptimo"
        )

        self.card_main_inst_val.config(text=f"{stats['instrucciones_originales']} → {stats['instrucciones_optimizadas']}")
        self.card_main_inst_sub.config(text="Antes vs Después")

        self.card_main_temps_val.config(text=f"{stats['temporales_originales']} → {stats['temporales_optimizados']}")
        self.card_main_temps_sub.config(text="Variables en memoria")

        self.card_main_cfg_val.config(text=f"{stats['caminos_originales']} → {stats['caminos_optimizados']}")
        self.card_main_cfg_sub.config(text=f"Complejidad: {stats['complejidad_original']} → {stats['complejidad_optimizada']}")

        formatear_texto_conclusiones(self.txt_main_conclusiones, reporte.generar_conclusiones_humanizadas())

        self.txt_main_metricas.config(state=tk.NORMAL)
        self.txt_main_metricas.delete("1.0", tk.END)
        self.txt_main_metricas.insert(tk.END, reporte.generar_reporte_texto())
        self.txt_main_metricas.config(state=tk.DISABLED)

    def mostrar_resultado_optimizacion(self, opt: IROptimizer):
        ventana = tk.Toplevel(self.root)
        ventana.title("Optimización de Código Intermedio (CFG / GFG)")
        ventana.geometry("1060x580")
        ventana.minsize(850, 480)

        header_frame = tk.Frame(ventana, bg="#FCE4EC", padx=15, pady=6)
        header_frame.pack(side=tk.TOP, fill=tk.X)
        tk.Label(
            header_frame, text="Optimización de Código Intermedio mediante Grafo de Flujo de Control",
            font=("Arial", 12, "bold"), bg="#FCE4EC", fg="#880E4F"
        ).pack(anchor="w")
        tk.Label(
            header_frame,
            text="Constant Folding, Propagación de Constantes, CSE, Eliminación de Código Muerto, Bloques Inalcanzables y Saltos",
            font=("Arial", 8), bg="#FCE4EC", fg="#AD1457"
        ).pack(anchor="w")

        reporte = OptimizationReport(opt)

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
                initialfile="reporte_optimizacion.txt",
                filetypes=[("Reporte Texto (*.txt)", "*.txt"), ("Todos los archivos", "*.*")]
            )
            if ruta:
                try:
                    with open(ruta, "w", encoding="utf-8") as f:
                        f.write(reporte.generar_reporte_texto() + "\n")
                    messagebox.showinfo("Guardado", f"Reporte guardado en:\n{ruta}")
                except Exception as ex:
                    messagebox.showerror("Error", str(ex))

        def copiar_conclusiones():
            texto = reporte.generar_conclusiones_humanizadas()
            self.root.clipboard_clear()
            self.root.clipboard_append(texto)
            messagebox.showinfo("Copiado", "¡Conclusiones copiadas al portapapeles!")

        def copiar_after_ir():
            texto = "\n".join(i.to_ir_tuple() for i in opt.instrucciones_optimizadas)
            self.root.clipboard_clear()
            self.root.clipboard_append(texto)
            messagebox.showinfo("Copiado", "¡Código after.ir copiado al portapapeles!")

        # Barra inferior de acciones (empaquetada en BOTTOM antes del notebook para que nunca se reduzca)
        bot_bar = tk.Frame(ventana, bg="#F5F5F5", padx=12, pady=6)
        bot_bar.pack(side=tk.BOTTOM, fill=tk.X)

        btn_c_c = tk.Button(bot_bar, text="Copiar Conclusiones", command=copiar_conclusiones,
                            bg="#F57C00", fg="white", font=("Arial", 9, "bold"), width=18, pady=5)
        btn_c_c.pack(side=tk.LEFT, padx=4)

        btn_g_b = tk.Button(bot_bar, text="Guardar before.ir", command=guardar_before_ir,
                            bg="#1565C0", fg="white", font=("Arial", 9, "bold"), width=16, pady=5)
        btn_g_b.pack(side=tk.LEFT, padx=4)

        btn_g_a = tk.Button(bot_bar, text="Guardar after.ir", command=guardar_after_ir,
                            bg="#2E7D32", fg="white", font=("Arial", 9, "bold"), width=16, pady=5)
        btn_g_a.pack(side=tk.LEFT, padx=4)

        btn_g_r = tk.Button(bot_bar, text="Guardar Reporte (.txt)", command=guardar_reporte,
                            bg="#6A1B9A", fg="white", font=("Arial", 9, "bold"), width=20, pady=5)
        btn_g_r.pack(side=tk.LEFT, padx=4)

        btn_c_a = tk.Button(bot_bar, text="Copiar after.ir", command=copiar_after_ir,
                            bg="#00838F", fg="white", font=("Arial", 9, "bold"), width=16, pady=5)
        btn_c_a.pack(side=tk.LEFT, padx=4)

        btn_close = tk.Button(bot_bar, text="Cerrar", command=ventana.destroy,
                              bg="#757575", fg="white", font=("Arial", 9, "bold"), width=10, pady=5)
        btn_close.pack(side=tk.RIGHT, padx=4)

        notebook = ttk.Notebook(ventana)
        notebook.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=(2, 4))

        tab_grafo = ttk.Frame(notebook)
        notebook.add(tab_grafo, text=" Grafo de Flujo (CFG) ")

        ctrl_bar = tk.Frame(tab_grafo, bg="#ECEFF1", pady=3, padx=8)
        ctrl_bar.pack(fill=tk.X)

        canvas_modal = CFGCanvas(tab_grafo, height=260)
        canvas_modal.pack(fill=tk.BOTH, expand=True)

        lbl_modal_info = tk.Label(ctrl_bar, text="Vista activa: CFG Original", font=("Arial", 9, "bold"), bg="#ECEFF1", fg="#1565C0")

        def ver_orig():
            canvas_modal.dibujar_cfg(opt.cfg_original)
            lbl_modal_info.config(text="Vista activa: CFG Original", fg="#1565C0")

        def ver_opt():
            canvas_modal.dibujar_cfg(opt.cfg_optimizado)
            lbl_modal_info.config(text="Vista activa: CFG Optimizado", fg="#2E7D32")

        btn_ver_orig = tk.Button(ctrl_bar, text="CFG Original", command=ver_orig,
                                 bg="#1565C0", fg="white", font=("Arial", 9, "bold"), padx=16, pady=4)
        btn_ver_orig.pack(side=tk.LEFT, padx=4)

        btn_ver_opt = tk.Button(ctrl_bar, text="CFG Optimizado", command=ver_opt,
                                bg="#2E7D32", fg="white", font=("Arial", 9, "bold"), padx=16, pady=4)
        btn_ver_opt.pack(side=tk.LEFT, padx=4)
        lbl_modal_info.pack(side=tk.LEFT, padx=15)

        canvas_modal.dibujar_cfg(opt.cfg_original)

        tab_bb_suc = ttk.Frame(notebook)
        notebook.add(tab_bb_suc, text=" Bloques Básicos y Sucesores ")

        paned_bb = ttk.PanedWindow(tab_bb_suc, orient=tk.HORIZONTAL)
        paned_bb.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

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

        tab_transf_modal = ttk.Frame(notebook)
        notebook.add(tab_transf_modal, text=" Tabla de Transformaciones ")

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

        tab_comp_modal = ttk.Frame(notebook)
        notebook.add(tab_comp_modal, text=" Tabla Comparativa CFG ")

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

        tab_diff_modal = ttk.Frame(notebook)
        notebook.add(tab_diff_modal, text=" IR Antes / Después ")

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

        tab_rep_modal = ttk.Frame(notebook)
        notebook.add(tab_rep_modal, text=" Conclusiones y Reporte ")

        reporte = OptimizationReport(opt)
        stats = reporte.obtener_resumen_estadistico()

        cards_frame_modal = tk.Frame(tab_rep_modal, bg="#ECEFF1", padx=8, pady=6)
        cards_frame_modal.pack(fill=tk.X)

        def _crear_card_modal(parent, titulo, val_txt, sub_txt, col="#1565C0"):
            c = tk.Frame(parent, bg="#FFFFFF", relief=tk.SOLID, bd=1, padx=10, pady=5)
            c.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4)
            tk.Label(c, text=titulo.upper(), font=("Segoe UI", 8, "bold"), fg="#78909C", bg="#FFFFFF").pack(anchor="w")
            tk.Label(c, text=val_txt, font=("Segoe UI", 14, "bold"), fg=col, bg="#FFFFFF").pack(anchor="w")
            tk.Label(c, text=sub_txt, font=("Segoe UI", 8), fg="#90A4AE", bg="#FFFFFF").pack(anchor="w")

        red_m = stats["porcentaje_reduccion"]
        col_m = "#2E7D32" if red_m > 0 else "#546E7A"
        signo_m = f"-{red_m:.1f}%" if red_m > 0 else "0.0%"
        sub_red_m = f"{stats['instrucciones_eliminadas']} eliminadas" if red_m > 0 else "Código ya óptimo"

        _crear_card_modal(cards_frame_modal, "Reducción", signo_m, sub_red_m, col_m)
        _crear_card_modal(cards_frame_modal, "Instrucciones", f"{stats['instrucciones_originales']} → {stats['instrucciones_optimizadas']}", "Antes vs Después", "#1565C0")
        _crear_card_modal(cards_frame_modal, "Temporales", f"{stats['temporales_originales']} → {stats['temporales_optimizados']}", "Variables en memoria", "#6A1B9A")
        _crear_card_modal(cards_frame_modal, "Caminos CFG", f"{stats['caminos_originales']} → {stats['caminos_optimizados']}", f"Complejidad: {stats['complejidad_original']} → {stats['complejidad_optimizada']}", "#00838F")

        sub_nb_modal = ttk.Notebook(tab_rep_modal)
        sub_nb_modal.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        tab_modal_human = ttk.Frame(sub_nb_modal)
        sub_nb_modal.add(tab_modal_human, text=" Conclusiones y Resumen ")

        frame_m_human = tk.Frame(tab_modal_human)
        frame_m_human.pack(fill=tk.BOTH, expand=True)
        sb_m_human = ttk.Scrollbar(frame_m_human, orient=tk.VERTICAL)
        sb_m_human.pack(side=tk.RIGHT, fill=tk.Y)
        txt_rep_human = tk.Text(
            frame_m_human, font=("Segoe UI", 10), yscrollcommand=sb_m_human.set,
            bg="#FFFFFF", padx=15, pady=10, relief=tk.FLAT
        )
        txt_rep_human.pack(fill=tk.BOTH, expand=True)
        sb_m_human.config(command=txt_rep_human.yview)

        formatear_texto_conclusiones(txt_rep_human, reporte.generar_conclusiones_humanizadas())

        tab_modal_formal = ttk.Frame(sub_nb_modal)
        sub_nb_modal.add(tab_modal_formal, text=" Reporte Formal y Tablas ")

        frame_m_formal = tk.Frame(tab_modal_formal)
        frame_m_formal.pack(fill=tk.BOTH, expand=True)
        sb_rep = ttk.Scrollbar(frame_m_formal, orient=tk.VERTICAL)
        sb_rep.pack(side=tk.RIGHT, fill=tk.Y)
        txt_rep_full = tk.Text(
            frame_m_formal, font=("Consolas", 10), yscrollcommand=sb_rep.set,
            bg="#FAFAFA", padx=10, pady=8
        )
        txt_rep_full.pack(fill=tk.BOTH, expand=True)
        sb_rep.config(command=txt_rep_full.yview)

        txt_rep_full.insert(tk.END, reporte.generar_reporte_texto())
        txt_rep_full.config(state=tk.DISABLED)

    def generar_codigo_objeto(self):
        self.limpiar_resaltado()

        codigo, parser, arbol_ast = self._parsear()

        if parser.errors:
            for err in parser.errors:
                self.resaltar_error(codigo, err.pos_start, err.pos_end)
            mensaje = "El código tiene errores de sintaxis; corrígelos antes de generar código objeto:\n\n"
            for i, err in enumerate(parser.errors, 1):
                fila_col = self.index_to_tk_public(codigo, err.pos_start)
                mensaje += f"{i}. (línea {fila_col}) {err.message}\n"
            messagebox.showerror("Corrige la sintaxis primero", mensaje)
            return None

        if not arbol_ast or not getattr(arbol_ast, "hijos", []):
            messagebox.showwarning("Sin código", "No hay código o instrucciones para generar código objeto.")
            return None

        analizador = SemanticAnalyzer()
        errores_sem, tabla = analizador.analizar(arbol_ast)
        if errores_sem:
            resp = messagebox.askyesno(
                "Advertencias Semánticas",
                f"El código contiene {len(errores_sem)} advertencia(s) semántica(s):\n\n" +
                "\n".join(errores_sem[:5]) +
                ("\n..." if len(errores_sem) > 5 else "") +
                "\n\n¿Deseas continuar con la generación de código objeto?"
            )
            if not resp:
                self.mostrar_resultado_semantico(errores_sem, tabla)
                return None

        # 1. Obtener cuádruplos optimizados
        if hasattr(self, "ultimo_optimizador") and self.ultimo_optimizador:
            opt = self.ultimo_optimizador
            cuads_optimizados = opt.instrucciones_optimizadas
            cuads_originales = opt.instrucciones_originales
        else:
            generador = IRGenerator()
            instrucciones, postfijas, texto_ir = generador.generar(arbol_ast)
            if not instrucciones:
                messagebox.showwarning("Sin instrucciones", "No se generaron instrucciones de código intermedio.")
                return None
            opt = IROptimizer(instrucciones)
            opt.optimizar()
            self.ultimo_optimizador = opt
            self._actualizar_pestanas_optimizacion(opt)
            cuads_optimizados = opt.instrucciones_optimizadas
            cuads_originales = opt.instrucciones_originales

        # 2. Pipeline completo: Liveness -> Asignación Registros por Coloración -> Generación ASM
        liveness = construir_grafo_interferencia(cuads_optimizados)
        allocator = RegisterAllocator(liveness)
        gen = CodeGenerator(cuads_optimizados, allocator)
        codigo_asm = gen.generar_codigo()

        # 3. Guardar estado
        res_objeto = ResultadoCompilacionObjeto(
            cuadruplos_originales=cuads_originales,
            cuadruplos_optimizados=cuads_optimizados,
            liveness=liveness,
            allocator=allocator,
            codigo_asm=codigo_asm,
            resultado_ejecucion=ExecutionResult(
                exitoso=True, codigo_retorno=0, salida="", registros_finales={}, memoria_final={}, instrucciones_ejecutadas=0
            ),
            optimizador=opt
        )
        self.ultimo_resultado_objeto = res_objeto

        # 4. Actualizar interfaz gráfica
        self._actualizar_pestanas_objeto(res_objeto)

        # 5. Sincronizar visualizador de coloración de grafos
        texto_ady = liveness.generar_texto_adyacencia()
        if texto_ady:
            self.seccion_coloracion.txt_grafo.delete("1.0", tk.END)
            self.seccion_coloracion.txt_grafo.insert(tk.END, texto_ady)
            self.seccion_coloracion.ejecutar_coloracion()

        self.main_notebook.select(self.tab_asm)
        self.lbl_asm_status.config(
            text=f"ASM x86 generado: {len(cuads_optimizados)} cuádruplas, chi={allocator.chi}, {allocator.obtener_metricas()['registros_utilizados']} registros x86.",
            fg="#1B5E20"
        )

        messagebox.showinfo(
            "Generación Exitosa de Código Objeto",
            f"¡Código objeto ensamblador x86 (.asm) generado correctamente!\n\n"
            f"• Cuádruplas optimizadas traducidas: {len(cuads_optimizados)}\n"
            f"• Variables / temporales en grafo:    {len(liveness.variables)}\n"
            f"• Número cromático mínimo chi(G):     {allocator.chi}\n"
            f"• Registros físicos asignados:        {allocator.obtener_metricas()['registros_utilizados']} / 6\n"
            f"• Derrames en memoria (Spills):       {len(allocator.spills)}\n"
            f"• Coloración libre de conflictos:     {'SÍ (100% VÁLIDA)' if allocator.es_valida else 'NO'}"
        )
        return res_objeto

    def _actualizar_pestanas_objeto(self, res: ResultadoCompilacionObjeto):
        alloc = res.allocator
        m = alloc.obtener_metricas()

        # Actualizar cards de registro
        self.card_reg_vars_val.config(text=str(m["total_variables"]))
        self.card_reg_vars_sub.config(text=f"{m['variables_usuario']} usuario, {m['temporales']} temp")

        self.card_reg_chi_val.config(text=f"chi = {m['numero_cromatico']}")
        self.card_reg_chi_sub.config(text="Coloración mínima propia")

        self.card_reg_regs_val.config(text=f"{m['registros_utilizados']} / {m['registros_disponibles']}")
        self.card_reg_regs_sub.config(text="Registros x86 asignados")

        self.card_reg_spills_val.config(text=str(m["spills"]))
        self.card_reg_spills_sub.config(text="Cero derrames requeridos" if m["spills"] == 0 else f"{m['spills']} en memoria")

        # Poblar Treeview de registros
        for item in self.tv_main_registros.get_children():
            self.tv_main_registros.delete(item)
        for fila in alloc.obtener_filas_tabla():
            self.tv_main_registros.insert("", tk.END, values=fila)

        # Poblar visor de texto .asm
        self.txt_main_asm.delete("1.0", tk.END)
        self.txt_main_asm.insert(tk.END, res.codigo_asm)

    def ejecutar_codigo_objeto(self):
        if not self.ultimo_resultado_objeto:
            res = self.generar_codigo_objeto()
            if not res:
                return

        codigo_asm = self.ultimo_resultado_objeto.codigo_asm
        sim = SimulatorASM(codigo_asm)
        res_exec = sim.ejecutar()
        self.ultimo_resultado_objeto.resultado_ejecucion = res_exec

        # Actualizar pestaña de ejecución
        col_st = "#00796B" if res_exec.exitoso else "#D32F2F"
        self.card_exec_status_val.config(text="EXITOSO" if res_exec.exitoso else "FALLIDO", fg=col_st)
        self.card_exec_status_sub.config(text="0 errores en simulación" if res_exec.exitoso else "Error en ejecución")

        self.card_exec_ret_val.config(text=f"EAX = {res_exec.codigo_retorno}")
        self.card_exec_ret_sub.config(text="Código de retorno estándar")

        self.card_exec_steps_val.config(text=f"{res_exec.instrucciones_ejecutadas} pasos")
        self.card_exec_steps_sub.config(text="Instrucciones x86 procesadas")

        # Salida STDOUT
        self.txt_main_salida_stdout.delete("1.0", tk.END)
        if res_exec.salida:
            self.txt_main_salida_stdout.insert(tk.END, res_exec.salida)
        else:
            self.txt_main_salida_stdout.insert(tk.END, "(Ejecución finalizada sin salidas por stdout)")

        # Treeview Registros CPU
        for item in self.tv_regs_cpu.get_children():
            self.tv_regs_cpu.delete(item)
        for reg in ("EAX", "EBX", "ECX", "EDX", "ESI", "EDI", "EBP", "ESP"):
            val = res_exec.registros_finales.get(reg, 0)
            hex_val = f"0x{val & 0xFFFFFFFF:08X}"
            self.tv_regs_cpu.insert("", tk.END, values=(reg, val, hex_val))

        # Treeview Memoria BSS
        for item in self.tv_mem_bss.get_children():
            self.tv_mem_bss.delete(item)
        for var, val in sorted(res_exec.memoria_final.items()):
            if not var.startswith("str_") and not var.startswith("fmt_"):
                self.tv_mem_bss.insert("", tk.END, values=(var, val))

        # Reporte formal
        self.txt_reporte_ejecucion.delete("1.0", tk.END)
        self.txt_reporte_ejecucion.insert(tk.END, res_exec.generar_reporte_ejecucion())

        self.main_notebook.select(self.tab_ejecucion)

        salida_corta = res_exec.salida.strip()
        msg_salida = f"\n\nSalida en consola:\n{salida_corta}" if salida_corta else ""
        messagebox.showinfo(
            "Simulación de Código Objeto",
            f"¡Código ensamblador ejecutado exitosamente!\n\n"
            f"• Estado: { 'EXITOSO' if res_exec.exitoso else 'ERROR' }\n"
            f"• Código de retorno (EAX): {res_exec.codigo_retorno}\n"
            f"• Instrucciones simuladas: {res_exec.instrucciones_ejecutadas}" + msg_salida
        )

    def compilar_todo_completo(self):
        """Ejecuta todas las fases del compilador en un solo flujo integrado."""
        self.limpiar_resaltado()
        res = self.generar_codigo_objeto()
        if res:
            self.ejecutar_codigo_objeto()

    def guardar_codigo_asm(self):
        if not self.ultimo_resultado_objeto:
            messagebox.showwarning("Sin código objeto", "Genera primero el código objeto (.asm).")
            return
        ruta = filedialog.asksaveasfilename(
            title="Guardar Código Objeto (.asm)",
            defaultextension=".asm",
            initialfile="programa_objeto.asm",
            filetypes=[("Ensamblador (*.asm)", "*.asm"), ("Todos los archivos", "*.*")]
        )
        if ruta:
            try:
                with open(ruta, "w", encoding="utf-8") as f:
                    f.write(self.ultimo_resultado_objeto.codigo_asm)
                messagebox.showinfo("Archivo Guardado", f"Archivo ensamblador guardado en:\n{ruta}")
            except Exception as ex:
                messagebox.showerror("Error al guardar", str(ex))

    def copiar_codigo_asm(self):
        if not self.ultimo_resultado_objeto:
            messagebox.showwarning("Sin código objeto", "Genera primero el código objeto (.asm).")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(self.ultimo_resultado_objeto.codigo_asm)
        messagebox.showinfo("Copiado", "¡Código objeto (.asm) copiado al portapapeles!")

    def guardar_tabla_registros(self):
        if not self.ultimo_resultado_objeto:
            messagebox.showwarning("Sin datos", "Genera primero el código objeto para obtener la tabla de registros.")
            return
        ruta = filedialog.asksaveasfilename(
            title="Guardar Tabla de Asignación de Registros",
            defaultextension=".txt",
            initialfile="tabla_asignacion_registros.txt",
            filetypes=[("Texto (*.txt)", "*.txt"), ("Todos los archivos", "*.*")]
        )
        if ruta:
            try:
                alloc = self.ultimo_resultado_objeto.allocator
                with open(ruta, "w", encoding="utf-8") as f:
                    f.write(alloc.generar_resumen_metricas_texto() + "\n\n")
                    f.write(alloc.generar_tabla_texto() + "\n")
                messagebox.showinfo("Archivo Guardado", f"Tabla de asignación de registros guardada en:\n{ruta}")
            except Exception as ex:
                messagebox.showerror("Error al guardar", str(ex))

    def copiar_tabla_registros(self):
        if not self.ultimo_resultado_objeto:
            messagebox.showwarning("Sin datos", "Genera primero el código objeto para obtener la tabla de registros.")
            return
        alloc = self.ultimo_resultado_objeto.allocator
        texto = alloc.generar_resumen_metricas_texto() + "\n\n" + alloc.generar_tabla_texto()
        self.root.clipboard_clear()
        self.root.clipboard_append(texto)
        messagebox.showinfo("Copiado", "¡Tabla de asignación de registros copiada al portapapeles!")

    def copiar_salida_consola(self):
        texto = self.txt_main_salida_stdout.get("1.0", tk.END)
        self.root.clipboard_clear()
        self.root.clipboard_append(texto)
        messagebox.showinfo("Copiado", "¡Salida de consola copiada al portapapeles!")

    def exportar_evidencias_u4(self):
        if not self.ultimo_resultado_objeto:
            messagebox.showwarning("Sin datos", "Genera y ejecuta primero el código objeto para exportar evidencias.")
            return
        ruta = filedialog.asksaveasfilename(
            title="Exportar Evidencias Completas U4",
            defaultextension=".txt",
            initialfile="evidencias_completas_u4.txt",
            filetypes=[("Texto (*.txt)", "*.txt"), ("Todos los archivos", "*.*")]
        )
        if ruta:
            try:
                res = self.ultimo_resultado_objeto
                codigo_fuente = self.obtener_codigo()
                with open(ruta, "w", encoding="utf-8") as f:
                    f.write("==============================================================================\n")
                    f.write("        REPORTE TÉCNICO Y EVIDENCIAS DE GENERACIÓN DE CÓDIGO OBJETO           \n")
                    f.write("==============================================================================\n\n")
                    f.write("1. CÓDIGO FUENTE (C++):\n")
                    f.write("-" * 60 + "\n")
                    f.write(codigo_fuente.strip() + "\n\n")

                    f.write("2. CÓDIGO INTERMEDIO ORIGINAL (CUÁDRUPLOS):\n")
                    f.write("-" * 60 + "\n")
                    for c in res.cuadruplos_originales:
                        f.write(c.to_ir_tuple() + "\n")
                    f.write("\n")

                    f.write("3. CÓDIGO INTERMEDIO OPTIMIZADO (CUÁDRUPLOS):\n")
                    f.write("-" * 60 + "\n")
                    for c in res.cuadruplos_optimizados:
                        f.write(c.to_ir_tuple() + "\n")
                    f.write("\n")

                    f.write("4. ANÁLISIS DE VARIABLES VIVAS (LIVENESS) Y GRAFO DE INTERFERENCIA:\n")
                    f.write("-" * 60 + "\n")
                    f.write("Lista de Adyacencia del Grafo de Interferencia:\n")
                    f.write(res.liveness.generar_texto_adyacencia() + "\n\n")

                    f.write("5. TABLA FORMAL DE ASIGNACIÓN DE REGISTROS:\n")
                    f.write("-" * 60 + "\n")
                    f.write(res.allocator.generar_resumen_metricas_texto() + "\n\n")
                    f.write(res.allocator.generar_tabla_texto() + "\n\n")

                    f.write("6. CÓDIGO OBJETO ENSAMBLADOR GENERADO (.ASM):\n")
                    f.write("-" * 60 + "\n")
                    f.write(res.codigo_asm + "\n\n")

                    f.write("7. EVIDENCIA DE EJECUCIÓN (SIMULADOR):\n")
                    f.write("-" * 60 + "\n")
                    f.write(res.resultado_ejecucion.generar_reporte_ejecucion() + "\n")

                messagebox.showinfo("Evidencias Exportadas", f"Evidencias técnicas guardadas exitosamente en:\n{ruta}")
            except Exception as ex:
                messagebox.showerror("Error al exportar", str(ex))


if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()
