import tkinter as tk
from tkinter import ttk, messagebox
import re

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
            ('LINEA_COMENTARIO', r'//.*'),
            ('RESERVADA', r'\b(int|cout|cin|float|void|char|double|string|boolean|if|else|while|for|return|break|continue|true|false)\b'),
            ('NUMERO',   r'\d+(\.\d*)?'),
            ('IDENTIFICADOR',       r'[A-Za-z_][A-Za-z0-9_]*'),
            ('CADENA',   r'".*?"'),
            ('OP_LOGICO', r'&&|\|\||!'),
            ('OP_FLUJO',        r'<<|>>'),
            ('OP_RELACIONAL',   r'==|!=|<=|>=|<|>'),
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
                return acceso
            # llamada a función: id(args)
            if self.current() and self.current().type == 'PARENTESIS_IZQ':
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
                return llamada
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
        return ExprParser(tokens, self.line_of).parse()

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
            nodo_ciclo = NodoAST("Ciclo", tok.value)
            nodo_ciclo.linea = self.line_of(tok.pos_start)
            self.advance()
            nodo_cond = self.parse_condition()
            if nodo_cond:
                contenedor = NodoAST("Condición")
                contenedor.agregar_hijo(nodo_cond)
                nodo_ciclo.agregar_hijo(contenedor)

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
#  ámbito activo. Ver diapositiva 7-8.
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
        """Busca desde el ámbito más interno hacia afuera (insert/lookup, ver diapositiva 6)."""
        for ambito in reversed(self.scopes):
            if nombre in ambito:
                return ambito[nombre]
        return None


# ============================================================================
#  Analizador semántico: recorre el AST (patrón Visitor, diapositiva 16) y
#  valida: variables declaradas, redeclaraciones, y compatibilidad de tipos
#  (diapositiva 9). Los errores siguen el formato obligatorio de la
#  diapositiva 12: "Error semántico línea N: motivo".
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
            # (no se abre un scope adicional para él, ver diapositiva 8)
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
                t = self.tipo_de(nodo.hijos[0])
                if (t is not None and self.tipo_retorno_actual and self.tipo_retorno_actual != 'void'
                        and t != self.tipo_retorno_actual
                        and not (t in TIPOS_NUMERICOS and self.tipo_retorno_actual in TIPOS_NUMERICOS)):
                    self.error(linea, f"el valor de return es {t} pero la función devuelve {self.tipo_retorno_actual}")
            elif self.tipo_retorno_actual and self.tipo_retorno_actual != 'void':
                self.error(linea, f"falta un valor de return para una función que devuelve {self.tipo_retorno_actual}")
        elif et == "Salida por Consola":
            for hijo in nodo.hijos:
                self.tipo_de(hijo)
        elif et in ("Assign", "BinOp", "UnOp", "Id", "Num", "Bool", "Cadena",
                    "Ternario", "AccesoArreglo", "Llamada"):
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
            nodo_izq = nodo.hijos[0]
            tipo_der = self.tipo_de(nodo.hijos[1])
            tipo_izq = self.tipo_de(nodo_izq)
            if tipo_izq is None or tipo_der is None:
                return None
            if tipo_izq != tipo_der and not (tipo_izq in TIPOS_NUMERICOS and tipo_der in TIPOS_NUMERICOS):
                self.error(linea, f"no se puede asignar {tipo_der} a {tipo_izq}")
                return None
            return tipo_izq

        return None


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Analizador Léxico y Sintáctico")
        self.root.geometry("800x680")

        self.ultimo_ast = None  # guardamos el último árbol generado para poder verlo cuando el usuario quiera
        
        # Frame superior para el editor de código
        top_frame = tk.Frame(self.root)
        top_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        tk.Label(top_frame, text="Código Fuente:", font=("Arial", 12, "bold")).pack(anchor="w")
        
        self.text_area = tk.Text(top_frame, height=15, font=("Consolas", 12))
        self.text_area.pack(fill=tk.BOTH, expand=True)
        self.text_area.tag_configure("error", background="red", foreground="white")
        
        # Cargar un código de ejemplo
        codigo_ejemplo = """float cuadradoLimitado(x) float x {
    /* devuelve x al cuadrado, pero nunca más de 100 */
    return (x<=-10.0||x>=10.0)?100:x*x;
}"""
        self.text_area.insert(tk.END, codigo_ejemplo)
        
        # Frame intermedio para los botones
        mid_frame = tk.Frame(self.root)
        mid_frame.pack(fill=tk.X, padx=10, pady=5)
        
        btn_lexico = tk.Button(mid_frame, text="Análisis Léxico", command=self.analisis_lexico, bg="#4CAF50", fg="white", font=("Arial", 10, "bold"))
        btn_lexico.pack(side=tk.LEFT, padx=5)
        
        btn_sintactico = tk.Button(mid_frame, text="Análisis Sintáctico", command=self.analisis_sintactico, bg="#2196F3", fg="white", font=("Arial", 10, "bold"))
        btn_sintactico.pack(side=tk.LEFT, padx=5)

        btn_semantico = tk.Button(mid_frame, text="Análisis Semántico", command=self.analisis_semantico, bg="#FF9800", fg="white", font=("Arial", 10, "bold"))
        btn_semantico.pack(side=tk.LEFT, padx=5)

        self.btn_arbol = tk.Button(mid_frame, text="Ver Árbol Sintáctico (AST)", command=self.ver_arbol_sintactico,
                                    bg="#9C27B0", fg="white", font=("Arial", 10, "bold"), state=tk.DISABLED)
        self.btn_arbol.pack(side=tk.LEFT, padx=5)
        
        # Frame inferior para la tabla de resultados léxicos
        bottom_frame = tk.Frame(self.root)
        bottom_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        tk.Label(bottom_frame, text="Tabla de Tokens:", font=("Arial", 12, "bold")).pack(anchor="w")
        
        columns = ("Lexema", "Token", "Posición")
        self.tree = ttk.Treeview(bottom_frame, columns=columns, show="headings", height=8)
        self.tree.heading("Lexema", text="Lexema")
        self.tree.heading("Token", text="Token (Tipo)")
        self.tree.heading("Posición", text="Posición (Inicio - Fin)")
        
        self.tree.column("Lexema", width=150)
        self.tree.column("Token", width=150)
        self.tree.column("Posición", width=100)
        # Configuramos el color para las filas con errores
        self.tree.tag_configure("error_lexico", background="#ffcccc", foreground="red")

        self.tree.pack(fill=tk.BOTH, expand=True)

    def obtener_codigo(self):
        return self.text_area.get("1.0", tk.END)

    def limpiar_resaltado(self):
        self.text_area.tag_remove("error", "1.0", tk.END)

    def analisis_lexico(self):
        self.limpiar_resaltado()
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
        sintáctico sin errores (igual que en la diapositiva 3)."""
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

if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()