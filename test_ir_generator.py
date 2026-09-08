"""
Pruebas automatizadas para el Generador de Código Intermedio (IR).
"""
import unittest
from AnalisisSema import Lexer, Parser, SemanticAnalyzer
from compilador.ir.generator import IRGenerator, Cuadruplo, generar_ir

class TestIRGenerator(unittest.TestCase):

    def setUp(self):
        self.generator = IRGenerator()

    def compilar_a_ast(self, codigo):
        lexer = Lexer(codigo)
        tokens = lexer.tokenize()
        parser = Parser(tokens, codigo)
        ast = parser.parse()
        self.assertEqual(len(parser.errors), 0, f"Errores de sintaxis en: {codigo}\n{parser.errors}")
        return ast

    def test_aritmetica_basica(self):
        """
        Caso de evaluación aritmética con precedencia:
        int x = 3 + 4 * 2;
        Debe generar:
        #1 (*, 4, 2, t1)
        #2 (+, 3, t1, t2)
        #3 (=, t2, , x)
        Y postfija: 3 4 2 * +
        """
        codigo = "int x = 3 + 4 * 2;"
        ast = self.compilar_a_ast(codigo)
        insts, postfijas, texto_ir = self.generator.generar(ast)

        self.assertEqual(len(insts), 3)
        self.assertEqual(insts[0].to_ir_tuple(), "#1 (*, 4, 2, t1)")
        self.assertEqual(insts[1].to_ir_tuple(), "#2 (+, 3, t1, t2)")
        self.assertEqual(insts[2].to_ir_tuple(), "#3 (=, t2, , x)")

        # Verificar 3AC
        lineas_3ac = self.generator.obtener_texto_3ac().splitlines()
        self.assertEqual(lineas_3ac, ["t1 = 4 * 2", "t2 = 3 + t1", "x = t2"])

        # Verificar Postfija
        self.assertTrue(any(p["postfija"] == "3 4 2 * +" for p in postfijas))

    def test_if_else_control_flujo(self):
        """
        Caso de control de flujo if-else:
        if (x > 5) { x = x - 1; } else { x = 0; }
        """
        codigo = "if (x > 5) { x = x - 1; } else { x = 0; }"
        ast = self.compilar_a_ast(codigo)
        insts, _, _ = self.generator.generar(ast)

        self.assertEqual(len(insts), 8)
        self.assertEqual(insts[0].to_ir_tuple(), "#1 (>, x, 5, t1)")
        self.assertEqual(insts[1].to_ir_tuple(), "#2 (ifFalse, t1, , L1)")
        self.assertEqual(insts[2].to_ir_tuple(), "#3 (-, x, 1, t2)")
        self.assertEqual(insts[3].to_ir_tuple(), "#4 (=, t2, , x)")
        self.assertEqual(insts[4].to_ir_tuple(), "#5 (goto, , , L2)")
        self.assertEqual(insts[5].to_ir_tuple(), "#6 (label, , , L1)")
        self.assertEqual(insts[6].to_ir_tuple(), "#7 (=, 0, , x)")
        self.assertEqual(insts[7].to_ir_tuple(), "#8 (label, , , L2)")

    def test_while_loop(self):
        """Verifica la generación de cuádruplos para ciclo while."""
        codigo = "while (x < 10) { x = x + 1; }"
        ast = self.compilar_a_ast(codigo)
        insts, _, _ = self.generator.generar(ast)

        # Debe tener L1, condición, ifFalse L2, cuerpo, goto L1, L2
        ops = [i.op for i in insts]
        self.assertIn("label", ops)
        self.assertIn("<", ops)
        self.assertIn("ifFalse", ops)
        self.assertIn("+", ops)
        self.assertIn("goto", ops)

    def test_for_loop(self):
        """Verifica la generación de cuádruplos para ciclo for."""
        codigo = "for (i = 0; i < 5; i = i + 1) { cout << i; }"
        ast = self.compilar_a_ast(codigo)
        insts, _, _ = self.generator.generar(ast)

        ops = [i.op for i in insts]
        self.assertIn("=", ops)
        self.assertIn("<", ops)
        self.assertIn("ifFalse", ops)
        self.assertIn("print", ops)
        self.assertIn("+", ops)
        self.assertIn("goto", ops)

    def test_postfija_compleja(self):
        """
        Verifica postfija a + b * c -> a b c * +
        """
        codigo = "int r = a + b * c;"
        ast = self.compilar_a_ast(codigo)
        _, postfijas, _ = self.generator.generar(ast)
        self.assertTrue(any("a b c * +" in p["postfija"] for p in postfijas))

    def test_cuadrado_limitado_ternario_y_funcion(self):
        """
        Verifica la función completa con operador ternario y return.
        """
        codigo = """float cuadradoLimitado(x) float x {
            return (x<=-10.0||x>=10.0)?100:x*x;
        }"""
        ast = self.compilar_a_ast(codigo)
        insts, postfijas, _ = self.generator.generar(ast)

        self.assertEqual(insts[0].op, "func_begin")
        self.assertEqual(insts[-1].op, "func_end")
        ops = [i.op for i in insts]
        self.assertIn("neg", ops)
        self.assertIn("<=", ops)
        self.assertIn(">=", ops)
        self.assertIn("||", ops)
        self.assertIn("ifFalse", ops)
        self.assertIn("return", ops)

if __name__ == "__main__":
    unittest.main()
