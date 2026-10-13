"""
Suite de Pruebas Automatizadas para la Unidad 3:
Optimización de Código Intermedio mediante Grafo de Flujo de Control (GFG / CFG).
Materia: Lenguajes y Autómatas II.
"""

import sys
import os
import unittest
import tempfile
import shutil

_raiz = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _raiz not in sys.path:
    sys.path.insert(0, _raiz)

from compilador.ir.generator import Cuadruplo, generar_ir
from compilador.opt import (
    BasicBlock,
    identificar_bloques_basicos,
    ControlFlowGraph,
    CFGEdge,
    IROptimizer,
    OptimizationReport,
    optimizar_ir_completo
)


class TestOptimizacionU3(unittest.TestCase):
    """Pruebas exhaustivas para todas las técnicas y requerimientos de la Unidad 3."""

    def test_01_identificacion_bloques_basicos(self):
        """
        Verifica el algoritmo de particionado en bloques básicos y sus líderes:
        - Líder 1: Primera instrucción.
        - Líder 2: Destino de un salto.
        - Líder 3: Instrucción posterior a un salto o return.
        """
        insts = [
            Cuadruplo(1, "=", "5", "", "a"),
            Cuadruplo(2, "=", "10", "", "b"),
            Cuadruplo(3, "+", "a", "b", "t1"),
            Cuadruplo(4, "IF_FALSE", "t1", "", "L1"),
            Cuadruplo(5, "=", "1", "", "x"),
            Cuadruplo(6, "GOTO", "", "", "L2"),
            Cuadruplo(7, "LABEL", "", "", "L1"),
            Cuadruplo(8, "=", "0", "", "x"),
            Cuadruplo(9, "LABEL", "", "", "L2"),
            Cuadruplo(10, "return", "x", "", ""),
            Cuadruplo(11, "=", "200", "", "w")  # Inalcanzable tras return
        ]

        bloques = identificar_bloques_basicos(insts)
        self.assertGreaterEqual(len(bloques), 4)

        # Primer bloque debe contener las primeras instrucciones
        self.assertEqual(bloques[0].id, "B1")
        self.assertEqual(bloques[0].instrucciones[0].numero, 1)
        self.assertTrue(bloques[0].es_entrada)

        # El bloque tras return debe estar separado
        ultimo_bloque = bloques[-1]
        self.assertEqual(ultimo_bloque.instrucciones[-1].resultado, "w")

    def test_02_construccion_cfg_y_sucesores(self):
        """Verifica la construcción del Grafo de Flujo de Control y la Tabla de Sucesores."""
        insts = [
            Cuadruplo(1, "=", "1", "", "x"),
            Cuadruplo(2, "IF_FALSE", "x", "", "L1"),
            Cuadruplo(3, "=", "10", "", "y"),
            Cuadruplo(4, "GOTO", "", "", "L2"),
            Cuadruplo(5, "LABEL", "", "", "L1"),
            Cuadruplo(6, "=", "20", "", "y"),
            Cuadruplo(7, "LABEL", "", "", "L2"),
            Cuadruplo(8, "return", "y", "", "")
        ]

        bloques = identificar_bloques_basicos(insts)
        cfg = ControlFlowGraph(bloques)

        tabla_suc = cfg.obtener_tabla_sucesores()
        self.assertTrue(len(tabla_suc) >= 4)

        # El bloque con IF_FALSE debe bifurcarse (2 sucesores)
        bloque_bifurcacion = None
        for b in bloques:
            if any(i.op.upper() == "IF_FALSE" for i in b.instrucciones):
                bloque_bifurcacion = b
                break
        self.assertIsNotNone(bloque_bifurcacion)
        self.assertEqual(len(cfg.sucesores[bloque_bifurcacion.id]), 2)

    def test_03_analisis_alcanzabilidad_codigo_inalcanzable(self):
        """Verifica que el código situado tras un return se detecte como inalcanzable."""
        insts = [
            Cuadruplo(1, "=", "10", "", "x"),
            Cuadruplo(2, "return", "x", "", ""),
            Cuadruplo(3, "=", "999", "", "z")  # Instrucción inalcanzable
        ]

        bloques = identificar_bloques_basicos(insts)
        cfg = ControlFlowGraph(bloques)
        alcanzables, inalcanzables = cfg.analizar_alcanzabilidad()

        self.assertIn("B1", alcanzables)
        self.assertIn("B2", inalcanzables)
        self.assertTrue(bloques[1].es_inalcanzable)

    def test_04_constant_folding(self):
        """Verifica el cálculo en tiempo de compilación (Constant Folding)."""
        insts = [
            Cuadruplo(1, "+", "20", "30", "t1"),
            Cuadruplo(2, "*", "4", "5", "t2"),
            Cuadruplo(3, ">", "15", "10", "t3"),
            Cuadruplo(4, "-", "50", "20", "t4"),
            Cuadruplo(5, "return", "t1", "", "")
        ]

        opt = IROptimizer(insts)
        opt_insts = opt.optimizar()

        # Comprobar que 20 + 30 se convirtió en 50
        folding_transf = [t for t in opt.transformaciones if "Folding" in t.tecnica]
        self.assertGreaterEqual(len(folding_transf), 3)

        # Verificar que el resultado de t1 fue plegado a 50
        t1_fold = any("50" in t.optimizado for t in folding_transf)
        self.assertTrue(t1_fold)

    def test_05_propagacion_constantes(self):
        """Verifica la propagación de valores constantes conocidos."""
        insts = [
            Cuadruplo(1, "=", "5", "", "a"),
            Cuadruplo(2, "=", "10", "", "b"),
            Cuadruplo(3, "+", "a", "b", "t1"),
            Cuadruplo(4, "return", "t1", "", "")
        ]

        opt = IROptimizer(insts)
        opt_insts = opt.optimizar()

        prop_transf = [t for t in opt.transformaciones if "Propagación" in t.tecnica]
        self.assertGreater(len(prop_transf), 0)

        # Al final t1 = 5 + 10 = 15, y return 15
        ret_inst = opt_insts[-1]
        self.assertEqual(ret_inst.op.lower(), "return")
        self.assertEqual(ret_inst.arg1, "15")

    def test_06_eliminacion_subexpresiones_comunes_cse(self):
        """Verifica la reutilización de cálculos idénticos (CSE)."""
        insts = [
            Cuadruplo(1, "+", "x", "y", "t1"),
            Cuadruplo(2, "*", "a", "b", "t2"),
            Cuadruplo(3, "+", "x", "y", "t3"),  # Idéntico a t1
            Cuadruplo(4, "+", "y", "x", "t4"),  # Conmutativo a t1
            Cuadruplo(5, "print", "t3", "", ""),
            Cuadruplo(6, "print", "t4", "", "")
        ]

        opt = IROptimizer(insts)
        opt_insts = opt.optimizar()

        cse_transf = [t for t in opt.transformaciones if "CSE" in t.tecnica]
        self.assertGreaterEqual(len(cse_transf), 2)

    def test_07_simplificacion_saltos_condicion_constante(self):
        """Verifica que ifFalse con condición verdadera elimine la bifurcación muerta."""
        insts = [
            Cuadruplo(1, "=", "1", "", "cond"),
            Cuadruplo(2, "IF_FALSE", "cond", "", "L_else"),
            Cuadruplo(3, "=", "100", "", "x"),
            Cuadruplo(4, "GOTO", "", "", "L_fin"),
            Cuadruplo(5, "LABEL", "", "", "L_else"),
            Cuadruplo(6, "=", "200", "", "x"),
            Cuadruplo(7, "LABEL", "", "", "L_fin"),
            Cuadruplo(8, "return", "x", "", "")
        ]

        opt = IROptimizer(insts)
        opt_insts = opt.optimizar()

        # Debe eliminarse la rama de L_else (x = 200)
        self.assertFalse(any("200" in (i.arg1 or "") for i in opt_insts))
        # Debe retornar 100
        self.assertEqual(opt_insts[-1].arg1, "100")

    def test_08_eliminacion_codigo_muerto_dce(self):
        """Verifica que variables no leídas se eliminen pero con efectos secundarios se preserven."""
        insts = [
            Cuadruplo(1, "=", "500", "", "muerta1"),
            Cuadruplo(2, "=", "600", "", "muerta2"),
            Cuadruplo(3, "print", "123", "", ""),      # Efecto secundario: no eliminar
            Cuadruplo(4, "call", "mi_funcion", "0", "t1"), # Llamada: no eliminar
            Cuadruplo(5, "return", "42", "", "")
        ]

        opt = IROptimizer(insts)
        opt_insts = opt.optimizar()

        # muerta1 y muerta2 deben eliminarse
        self.assertFalse(any(i.resultado in ("muerta1", "muerta2") for i in opt_insts))
        # print y call deben preservarse
        self.assertTrue(any(i.op == "print" for i in opt_insts))
        self.assertTrue(any(i.op == "call" for i in opt_insts))

    def test_09_caso_integrador_completo_u3(self):
        """
        Verifica el programa integrador oficial de la Unidad 3:
        int a = 5;
        int b = 10;
        int t1 = a + b;
        int t2 = a + b;
        int x;
        if (t1 > 10) { x = 1; } else { x = 0; }
        int y = x;
        int z = 20 + 30;
        int w = 100;
        return y;
        w = 200;
        """
        codigo = """
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
        return y;
        w = 200;
        """

        insts, _, _ = generar_ir(codigo)
        self.assertGreater(len(insts), 10)

        opt = IROptimizer(insts)
        opt_insts = opt.optimizar()

        # 1. Comprobar que se ejecutó CSE
        self.assertTrue(any("CSE" in t.tecnica for t in opt.transformaciones))

        # 2. Comprobar Constant Folding
        self.assertTrue(any("Folding" in t.tecnica for t in opt.transformaciones))

        # 3. Comprobar Propagación de Constantes
        self.assertTrue(any("Propagación" in t.tecnica for t in opt.transformaciones))

        # 4. Comprobar Eliminación de Bloques Inalcanzables (B5 w=200 o rama muerta)
        self.assertTrue(any("Inalcanzables" in t.tecnica for t in opt.transformaciones))

        # 5. Comprobar Eliminación de Código Muerto (z, w, etc.)
        self.assertTrue(any("Muerto" in t.tecnica for t in opt.transformaciones))

        # 6. Comprobar que el resultado final es return 1
        self.assertEqual(len(opt_insts), 1)
        self.assertEqual(opt_insts[0].op.lower(), "return")
        self.assertEqual(opt_insts[0].arg1, "1")

        # 7. Comprobar reducción de métricas
        comp_cfg = opt.obtener_tabla_comparativa_cfg()
        self.assertGreater(len(comp_cfg), 3)
        self.assertGreater(opt.calcular_porcentaje_reduccion(), 80.0)

    def test_10_generacion_reporte_y_exportacion(self):
        """Verifica la generación del reporte técnico y la exportación de before.ir y after.ir."""
        codigo = "int x = 3 + 4 * 2; return x;"
        insts, _, _ = generar_ir(codigo)

        opt = IROptimizer(insts)
        opt.optimizar()

        reporte = OptimizationReport(opt)
        texto_rep = reporte.generar_reporte_texto()

        self.assertIn("REPORTE FORMAL DE OPTIMIZACIÓN", texto_rep)
        self.assertIn("TABLA DE TRANSFORMACIONES APLICADAS", texto_rep)
        self.assertIn("ANÁLISIS DE RESULTADOS Y CONCLUSIONES", texto_rep)

        # Exportar a directorio temporal
        tmp_dir = tempfile.mkdtemp()
        try:
            archivos = reporte.exportar_archivos(tmp_dir)
            self.assertTrue(os.path.exists(archivos["before_ir"]))
            self.assertTrue(os.path.exists(archivos["after_ir"]))
            self.assertTrue(os.path.exists(archivos["reporte"]))

            with open(archivos["after_ir"], "r", encoding="utf-8") as f:
                contenido_after = f.read()
                self.assertIn("#1 (return, 11, , )", contenido_after)
        finally:
            shutil.rmtree(tmp_dir)

    def test_11_seguridad_en_bucles_while(self):
        """Verifica que las variables redefinidas dentro de un loop no se sobre-propaguen erróneamente."""
        codigo = """
        int x = 0;
        while (x < 10) {
            x = x + 1;
        }
        return x;
        """
        insts, _, _ = generar_ir(codigo)
        opt = IROptimizer(insts)
        opt_insts = opt.optimizar()

        # Debe conservar el bucle y la comparación
        self.assertTrue(any(i.op in ("<", "IF_FALSE", "IFFALSE") for i in opt_insts))
        self.assertTrue(any(i.op.lower() == "return" for i in opt_insts))
    def test_12_generacion_y_optimizacion_desde_ast_y_tupla(self):
        """Verifica que generar_ir y IRGenerator acepten tanto AST como tuplas (codigo, parser, ast)."""
        from AnalisisSema import Lexer, Parser
        from compilador.ir.generator import IRGenerator

        codigo = "int a = 10; int b = 20; int c = a + b;"
        lexer = Lexer(codigo)
        tokens = lexer.tokenize()
        parser = Parser(tokens, codigo)
        ast = parser.parse()

        # 1. Pasando el AST directamente
        gen1 = IRGenerator()
        insts1, _, _ = gen1.generar(ast)
        self.assertGreater(len(insts1), 0)

        # 2. Pasando la tupla (codigo, parser, ast) como devolvía _parsear()
        gen2 = IRGenerator()
        insts2, _, _ = gen2.generar((codigo, parser, ast))
        self.assertEqual(len(insts1), len(insts2))

        # 3. Optimizar las instrucciones generadas
        opt = IROptimizer(insts1)
        opt.optimizar()
        self.assertGreater(len(opt.transformaciones), 0)

    def test_13_optimizacion_expresiones_diversas(self):
        """Verifica que el optimizador funcione con distintas expresiones y programas."""
        from AnalisisSema import Lexer, Parser
        from compilador.ir.generator import IRGenerator

        ejemplos = [
            "int x = 3 + 4 * 2;",
            "int a = 5; int b = a * 2;",
            "x = 10; y = x + 5;",
            "int x = 10; if (x > 5) { x = x - 1; } else { x = 0; } return x;"
        ]
        for codigo in ejemplos:
            lexer = Lexer(codigo)
            tokens = lexer.tokenize()
            parser = Parser(tokens, codigo)
            ast = parser.parse()
            gen = IRGenerator()
            insts, _, _ = gen.generar(ast)
            self.assertGreater(len(insts), 0, f"No se generaron instrucciones para: {codigo}")

            opt = IROptimizer(insts)
            opt_insts = opt.optimizar()
            self.assertIsInstance(opt_insts, list)
            self.assertGreater(len(opt_insts), 0)


if __name__ == "__main__":
    unittest.main()
