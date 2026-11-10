
import sys
import os
import unittest

_base = os.path.dirname(os.path.abspath(__file__))


from compilador.ir.generator import generar_ir, IRGenerator, Cuadruplo, LexerCPP, ParserCPP


class TestGeneradorIRCompleto(unittest.TestCase):

    def test_01_aritmetica_basica_precedencia(self):
        codigo = "x = 3 + 4 * 2;"
        insts, _, ir = generar_ir(codigo)
        self.assertEqual(len(insts), 3)
        self.assertEqual(insts[0].to_ir_tuple(), "#1 (*, 4, 2, t1)")
        self.assertEqual(insts[1].to_ir_tuple(), "#2 (+, 3, t1, t2)")
        self.assertEqual(insts[2].to_ir_tuple(), "#3 (=, t2, , x)")

    def test_02_aritmetica_resta_multiplicacion(self):
        codigo = "y = 8 - 2 * 3;"
        insts, _, ir = generar_ir(codigo)
        self.assertEqual(len(insts), 3)
        self.assertEqual(insts[0].to_ir_tuple(), "#1 (*, 2, 3, t1)")
        self.assertEqual(insts[1].to_ir_tuple(), "#2 (-, 8, t1, t2)")
        self.assertEqual(insts[2].to_ir_tuple(), "#3 (=, t2, , y)")

    def test_03_control_flujo_if_else(self):
        codigo = "if (a > b) {\n    x = 1;\n} else {\n    x = 2;\n}"
        insts, _, ir = generar_ir(codigo)
        self.assertEqual(len(insts), 7)
        self.assertEqual(insts[0].to_ir_tuple(), "#1 (>, a, b, t1)")
        self.assertEqual(insts[1].to_ir_tuple(), "#2 (IF_FALSE, t1, , L1)")
        self.assertEqual(insts[2].to_ir_tuple(), "#3 (=, 1, , x)")
        self.assertEqual(insts[3].to_ir_tuple(), "#4 (GOTO, , , L2)")
        self.assertEqual(insts[4].to_ir_tuple(), "#5 (LABEL, , , L1)")
        self.assertEqual(insts[5].to_ir_tuple(), "#6 (=, 2, , x)")
        self.assertEqual(insts[6].to_ir_tuple(), "#7 (LABEL, , , L2)")

    def test_04_parentesis_alteran_precedencia(self):
        codigo = "y = (8 - 2) * 3;"
        insts, _, _ = generar_ir(codigo)
        self.assertEqual(len(insts), 3)
        self.assertEqual(insts[0].to_ir_tuple(), "#1 (-, 8, 2, t1)")
        self.assertEqual(insts[1].to_ir_tuple(), "#2 (*, t1, 3, t2)")
        self.assertEqual(insts[2].to_ir_tuple(), "#3 (=, t2, , y)")

    def test_05_parentesis_anidados_complejos(self):
        codigo = "res = ((a + b) * (c - d)) / (e + f);"
        insts, _, _ = generar_ir(codigo)
        self.assertEqual(len(insts), 6)
        self.assertEqual(insts[0].op, "+")
        self.assertEqual(insts[1].op, "-")
        self.assertEqual(insts[2].op, "*")
        self.assertEqual(insts[3].op, "+")
        self.assertEqual(insts[4].op, "/")
        self.assertEqual(insts[5].op, "=")
        self.assertEqual(insts[5].resultado, "res")

    def test_06_multiples_operadores_aritmeticos(self):
        codigo = "res = a + b * c - d / e % f;"
        insts, _, _ = generar_ir(codigo)
        ops = [i.op for i in insts]
        self.assertEqual(ops, ["*", "+", "/", "%", "-", "="])
        self.assertEqual(insts[-1].resultado, "res")

    def test_07_negacion_unaria(self):
        codigo = "x = -a * b + -c;"
        insts, _, _ = generar_ir(codigo)
        ops = [i.op for i in insts]
        self.assertIn("neg", ops)
        self.assertEqual(insts[0].op, "neg")
        self.assertEqual(insts[0].arg1, "a")

    def test_08_declaracion_con_tipo(self):
        codigo = "int x = 3 + 4 * 2;"
        insts, _, _ = generar_ir(codigo)
        self.assertEqual(len(insts), 3)
        self.assertEqual(insts[0].to_ir_tuple(), "#1 (*, 4, 2, t1)")
        self.assertEqual(insts[1].to_ir_tuple(), "#2 (+, 3, t1, t2)")
        self.assertEqual(insts[2].to_ir_tuple(), "#3 (=, t2, , x)")

    def test_09_if_simple_sin_else(self):
        codigo = "if (x <= 10) { y = 1; }"
        insts, _, _ = generar_ir(codigo)
        self.assertEqual(len(insts), 4)
        self.assertEqual(insts[0].to_ir_tuple(), "#1 (<=, x, 10, t1)")
        self.assertEqual(insts[1].to_ir_tuple(), "#2 (IF_FALSE, t1, , L1)")
        self.assertEqual(insts[2].to_ir_tuple(), "#3 (=, 1, , y)")
        self.assertEqual(insts[3].to_ir_tuple(), "#4 (LABEL, , , L1)")

    def test_10_if_else_anidado(self):
        codigo = """
        if (x > 0) {
            if (y > 0) {
                z = 1;
            } else {
                z = 2;
            }
        } else {
            z = 3;
        }
        """
        insts, _, _ = generar_ir(codigo)
        ops = [i.op for i in insts]
        self.assertEqual(ops.count("IF_FALSE"), 2)
        self.assertEqual(ops.count("GOTO"), 2)
        self.assertEqual(ops.count("LABEL"), 4)

    def test_11_operadores_relacionales_completos(self):
        for op in ("<", ">", "<=", ">=", "==", "!="):
            codigo = f"res = a {op} b;"
            insts, _, _ = generar_ir(codigo)
            self.assertEqual(insts[0].op, op)
            self.assertEqual(insts[0].arg1, "a")
            self.assertEqual(insts[0].arg2, "b")
            self.assertEqual(insts[1].op, "=")
            self.assertEqual(insts[1].resultado, "res")

    def test_12_operadores_logicos_and_or_not(self):
        codigo = "res = !a && (b || c);"
        insts, _, _ = generar_ir(codigo)
        ops = [i.op for i in insts]
        self.assertIn("!", ops)
        self.assertIn("||", ops)
        self.assertIn("&&", ops)

    def test_13_ciclo_while(self):
        codigo = "while (x < 10) { x = x + 1; }"
        insts, _, _ = generar_ir(codigo)
        self.assertEqual(insts[0].to_ir_tuple(), "#1 (LABEL, , , L1)")
        self.assertEqual(insts[1].to_ir_tuple(), "#2 (<, x, 10, t1)")
        self.assertEqual(insts[2].to_ir_tuple(), "#3 (IF_FALSE, t1, , L2)")
        self.assertEqual(insts[3].to_ir_tuple(), "#4 (+, x, 1, t2)")
        self.assertEqual(insts[4].to_ir_tuple(), "#5 (=, t2, , x)")
        self.assertEqual(insts[5].to_ir_tuple(), "#6 (GOTO, , , L1)")
        self.assertEqual(insts[6].to_ir_tuple(), "#7 (LABEL, , , L2)")

    def test_14_ciclo_for(self):
        codigo = "for (i = 0; i < 5; i = i + 1) { cout << i; }"
        insts, _, _ = generar_ir(codigo)
        ops = [i.op for i in insts]
        self.assertIn("=", ops)
        self.assertIn("LABEL", ops)
        self.assertIn("<", ops)
        self.assertIn("IF_FALSE", ops)
        self.assertIn("print", ops)
        self.assertIn("+", ops)
        self.assertIn("GOTO", ops)

    def test_15_io_cin_cout(self):
        codigo = 'cin >> x; cout << "Valor: " << x << endl;'
        insts, _, _ = generar_ir(codigo)
        ops = [i.op for i in insts]
        self.assertEqual(ops[0], "read")
        self.assertEqual(ops[1], "print")
        self.assertEqual(ops[2], "print")
        self.assertEqual(ops[3], "print")

    def test_16_funciones_con_return(self):
        codigo = "int suma(int a, int b) { return a + b; }"
        insts, _, _ = generar_ir(codigo)
        self.assertEqual(insts[0].op, "func_begin")
        self.assertEqual(insts[0].arg1, "suma")
        self.assertEqual(insts[1].op, "+")
        self.assertEqual(insts[2].op, "return")
        self.assertEqual(insts[3].op, "func_end")

    def test_17_operador_ternario(self):
        codigo = "res = (x > 0) ? 10 : 20;"
        insts, _, _ = generar_ir(codigo)
        ops = [i.op for i in insts]
        self.assertIn("IF_FALSE", ops)
        self.assertIn("GOTO", ops)
        self.assertIn("LABEL", ops)

    def test_18_post_incremento_decremento(self):
        codigo = "x++; y--;"
        insts, _, _ = generar_ir(codigo)
        ops = [i.op for i in insts]
        self.assertEqual(ops, ["+", "=", "-", "="])

    def test_19_arreglos_acceso_y_asignacion(self):
        codigo = "a[i] = b[j] + 1;"
        insts, _, _ = generar_ir(codigo)
        ops = [i.op for i in insts]
        self.assertIn("[]", ops)
        self.assertIn("+", ops)
        self.assertIn("[]=", ops)

    def test_20_flotantes_expresion(self):
        codigo = "area = 3.1416 * r * r;"
        insts, _, _ = generar_ir(codigo)
        self.assertEqual(insts[0].arg1, "3.1416")
        self.assertEqual(insts[-1].resultado, "area")


if __name__ == "__main__":
    unittest.main(verbosity=2)
