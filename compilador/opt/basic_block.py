
from typing import List, Optional
import copy

try:
    from compilador.ir.generator import Cuadruplo
except ImportError:
    from ..ir.generator import Cuadruplo


class BasicBlock:
    def __init__(self, id_bloque: str, instrucciones: Optional[List[Cuadruplo]] = None, etiqueta: str = ""):
        self.id = id_bloque
        self.instrucciones: List[Cuadruplo] = list(instrucciones or [])
        self.etiqueta: str = etiqueta
        self.es_inalcanzable: bool = False
        self.es_entrada: bool = False
        self.es_salida: bool = False

    @property
    def primera_instruccion(self) -> Optional[Cuadruplo]:
        return self.instrucciones[0] if self.instrucciones else None

    @property
    def ultima_instruccion(self) -> Optional[Cuadruplo]:
        return self.instrucciones[-1] if self.instrucciones else None

    @property
    def nombre_completo(self) -> str:
        if self.etiqueta:
            return f"{self.id} ({self.etiqueta})"
        return self.id

    def clonar(self) -> 'BasicBlock':
        nuevo = BasicBlock(self.id, [copy.copy(i) for i in self.instrucciones], self.etiqueta)
        nuevo.es_inalcanzable = self.es_inalcanzable
        nuevo.es_entrada = self.es_entrada
        nuevo.es_salida = self.es_salida
        return nuevo

    def obtener_texto_3ac(self) -> str:
        lineas = []
        for inst in self.instrucciones:
            lineas.append(inst.to_3ac())
        return "\n".join(lineas)

    def obtener_texto_bloque(self) -> str:
        encabezado = self.nombre_completo
        if self.es_inalcanzable:
            encabezado += " [Inalcanzable]"
        lineas = [encabezado]
        for inst in self.instrucciones:
            lineas.append(f"  {inst.numero}: {inst.to_3ac()}")
        return "\n".join(lineas)

    def __repr__(self) -> str:
        return f"BasicBlock({self.nombre_completo!r}, insts={len(self.instrucciones)}, inalcanzable={self.es_inalcanzable})"


def es_salto(inst: Cuadruplo) -> bool:
    op = (inst.op or "").upper()
    return op in ("GOTO", "IF_FALSE", "IFFALSE", "IF_TRUE", "IFTRUE", "IF", "RETURN", "FUNC_END")


def es_salto_condicional(inst: Cuadruplo) -> bool:
    op = (inst.op or "").upper()
    return op in ("IF_FALSE", "IFFALSE", "IF_TRUE", "IFTRUE", "IF")


def es_salto_incondicional(inst: Cuadruplo) -> bool:
    op = (inst.op or "").upper()
    return op == "GOTO"


def es_retorno(inst: Cuadruplo) -> bool:
    op = (inst.op or "").lower()
    return op == "return"


def identificar_bloques_basicos(instrucciones: List[Cuadruplo]) -> List[BasicBlock]:
    if not instrucciones:
        return []

    n = len(instrucciones)
    es_lider = [False] * n

    es_lider[0] = True

    mapa_etiquetas = {}
    for idx, inst in enumerate(instrucciones):
        op = (inst.op or "").upper()
        if op == "LABEL":
            etq = inst.resultado or inst.arg1
            if etq:
                mapa_etiquetas[etq] = idx

    for idx, inst in enumerate(instrucciones):
        op = (inst.op or "").upper()
        if op in ("LABEL", "FUNC_BEGIN"):
            es_lider[idx] = True

        elif es_salto(inst):
            destino = inst.resultado or inst.arg1
            if destino in mapa_etiquetas:
                es_lider[mapa_etiquetas[destino]] = True

            if idx + 1 < n:
                es_lider[idx + 1] = True

    bloques: List[BasicBlock] = []
    bloque_actual_insts: List[Cuadruplo] = []
    bloque_num = 1
    etiqueta_actual = ""

    for idx, inst in enumerate(instrucciones):
        if es_lider[idx] and bloque_actual_insts:
            b = BasicBlock(f"B{bloque_num}", bloque_actual_insts, etiqueta_actual)
            bloques.append(b)
            bloque_num += 1
            bloque_actual_insts = []
            etiqueta_actual = ""

        if (inst.op or "").upper() == "LABEL":
            etiqueta_actual = inst.resultado or inst.arg1

        bloque_actual_insts.append(inst)

    if bloque_actual_insts:
        b = BasicBlock(f"B{bloque_num}", bloque_actual_insts, etiqueta_actual)
        bloques.append(b)

    if bloques:
        bloques[0].es_entrada = True
        for b in bloques:
            if b.instrucciones:
                if (b.instrucciones[0].op or "").lower() == "func_begin":
                    b.es_entrada = True
                if es_retorno(b.instrucciones[-1]):
                    b.es_salida = True
        if not any(b.es_salida for b in bloques):
            bloques[-1].es_salida = True

    return bloques
