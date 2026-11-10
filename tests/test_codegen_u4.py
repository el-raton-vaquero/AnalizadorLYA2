"""
Suite de Pruebas Automatizadas para la Generación de Código Objeto y Asignación de Registros.
Verifica:
  1. Análisis de variables vivas (liveness analysis) y cálculo de rangos de vida.
  2. Construcción formal del grafo de interferencia y lista de adyacencia.
  3. Asignación óptima de registros mediante coloración de grafos (chi mínimo).
  4. Generación y consistencia de la Tabla de Asignación de Registros.
  5. Traducción de operaciones aritméticas y de asignación (+, -, *, /, %, neg, =).
  6. Traducción de estructuras condicionales, comparaciones y saltos (if-else, while, cmp, je, jne, jmp).
  7. Estructura ordenada, modular y funcional del archivo objeto ensamblador (.asm).
  8. Ejecución funcional completa y evidencia de simulación de arquitectura x86.
  9. Integración integral desde código fuente C++ hasta código objeto ejecutable.
  10. Manejo de derrames en memoria (spills) ante exceso de variables vivas.
"""

import sys
import os
import unittest

_raiz = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _raiz not in sys.path:
    sys.path.insert(0, _raiz)

from compilador.ir.generator import Cuadruplo, generar_ir
from compilador.opt import optimizar_ir_completo
from compilador.codegen.liveness import (
    LivenessAnalyzer, LiveRange, LivenessResult,
    construir_grafo_interferencia, es_identificador_variable
)
from compilador.codegen.register_allocator import (
    RegisterAllocator, RegistroInfo, REGISTROS_X86
)
from compilador.codegen.code_generator import CodeGenerator
from compilador.codegen.simulator import SimulatorASM, ExecutionResult
from compilador.codegen import generar_codigo_objeto_completo


class TestCodegenU4(unittest.TestCase):

    def test_01_liveness_secuencial_y_rangos_vida(self):
        """Verifica que el análisis de liveness calcule correctamente conjuntos def, use, in, out y rangos de vida."""
        cuads = [
            Cuadruplo(1, '=', '10', '', 'a'),
            Cuadruplo(2, '=', '20', '', 'b'),
            Cuadruplo(3, '+', 'a', 'b', 'c'),
            Cuadruplo(4, '*', 'c', '2', 'd'),
            Cuadruplo(5, 'print', 'd', '', '')
        ]

        liv = construir_grafo_interferencia(cuads)
        self.assertEqual(sorted(liv.variables), ['a', 'b', 'c', 'd'])

        # Rangos de vida
        r_a = liv.rangos_vida['a']
        r_b = liv.rangos_vida['b']
        r_c = liv.rangos_vida['c']
        r_d = liv.rangos_vida['d']

        self.assertEqual((r_a.inicio, r_a.fin), (1, 3))
        self.assertEqual((r_b.inicio, r_b.fin), (2, 3))
        self.assertEqual((r_c.inicio, r_c.fin), (3, 4))
        self.assertEqual((r_d.inicio, r_d.fin), (4, 5))

    def test_02_grafo_interferencia_y_adyacencia(self):
        """Verifica que dos variables vivas al mismo tiempo interfieran y que variables con rangos disjuntos no."""
        cuads = [
            Cuadruplo(1, '=', '10', '', 'a'),
            Cuadruplo(2, '=', '20', '', 'b'),
            Cuadruplo(3, '+', 'a', 'b', 'c'),
            Cuadruplo(4, '*', 'c', '2', 'd')
        ]

        liv = construir_grafo_interferencia(cuads)
        # a y b están vivas al mismo tiempo en la instrucción 3
        self.assertIn('b', liv.interferencias_por_variable['a'])
        self.assertIn('a', liv.interferencias_por_variable['b'])

        # d se define después de que a y b murieron: d no debe interferir con a ni b
        self.assertNotIn('d', liv.interferencias_por_variable['a'])
        self.assertNotIn('d', liv.interferencias_por_variable['b'])

        texto_ady = liv.generar_texto_adyacencia()
        self.assertIn("a: b", texto_ady)
        self.assertIn("b: a", texto_ady)

    def test_03_coloracion_y_asignacion_optima_registros(self):
        """Verifica que la coloración asigne registros sin conflictos y permita la reutilización de registros."""
        cuads = [
            Cuadruplo(1, '=', '5', '', 'a'),
            Cuadruplo(2, '=', '10', '', 'b'),
            Cuadruplo(3, '+', 'a', 'b', 'c'),
            Cuadruplo(4, '*', 'c', '2', 'd'),
            Cuadruplo(5, 'print', 'd', '', '')
        ]

        liv = construir_grafo_interferencia(cuads)
        alloc = RegisterAllocator(liv, k_fisicos=6)

        # La coloración debe ser 100% válida
        self.assertTrue(alloc.es_valida)
        # chi(G) debe ser 2 (solo a y b interfieren simultáneamente)
        self.assertEqual(alloc.chi, 2)

        reg_a = alloc.tabla_asignacion['a'].registro_fisico
        reg_b = alloc.tabla_asignacion['b'].registro_fisico
        reg_c = alloc.tabla_asignacion['c'].registro_fisico
        reg_d = alloc.tabla_asignacion['d'].registro_fisico

        # a y b deben tener registros diferentes
        self.assertNotEqual(reg_a, reg_b)
        # c y d deben reutilizar alguno de los registros disponibles
        self.assertIn(reg_c, (reg_a, reg_b))
        self.assertIn(reg_d, (reg_a, reg_b))

    def test_04_tabla_asignacion_registros_formato_y_metricas(self):
        """Verifica que la tabla de asignación de registros contenga todos los campos exigidos y métricas precisas."""
        cuads = [
            Cuadruplo(1, '=', '1', '', 'x'),
            Cuadruplo(2, '=', '2', '', 'y'),
            Cuadruplo(3, '+', 'x', 'y', 't1')
        ]
        liv = construir_grafo_interferencia(cuads)
        alloc = RegisterAllocator(liv)

        filas = alloc.obtener_filas_tabla()
        self.assertEqual(len(filas), 3)

        # Columnas: (Variable, Tipo, Rango, Grado, Interfiere, Color, Virtual, x86, Ubicación)
        vars_tabla = [f[0] for f in filas]
        self.assertIn('x', vars_tabla)
        self.assertIn('y', vars_tabla)
        self.assertIn('t1', vars_tabla)

        tabla_ascii = alloc.generar_tabla_texto()
        self.assertIn("| Variable", tabla_ascii)
        self.assertIn("| Rango Vida", tabla_ascii)
        self.assertIn("| Reg. x86", tabla_ascii)

        m = alloc.obtener_metricas()
        self.assertEqual(m["total_variables"], 3)
        self.assertGreaterEqual(m["numero_cromatico"], 2)
        self.assertEqual(m["spills"], 0)
        self.assertTrue(m["coloracion_valida"])

    def test_05_traduccion_operaciones_aritmeticas_y_asignacion(self):
        """Verifica la traducción y ejecución de suma, resta, multiplicación, división, módulo y asignación."""
        codigo = """
        int a = 20;
        int b = 6;
        int suma = a + b;
        int resta = a - b;
        int mult = a * b;
        int div = a / b;
        int mod = a % b;
        cout << suma;
        cout << resta;
        cout << mult;
        cout << div;
        cout << mod;
        """
        res = generar_codigo_objeto_completo(codigo, optimizar=False)
        self.assertTrue(res.resultado_ejecucion.exitoso)
        salida_lineas = [int(x) for x in res.resultado_ejecucion.salida.strip().splitlines()]

        self.assertEqual(salida_lineas[0], 26)   # 20 + 6
        self.assertEqual(salida_lineas[1], 14)   # 20 - 6
        self.assertEqual(salida_lineas[2], 120)  # 20 * 6
        self.assertEqual(salida_lineas[3], 3)    # 20 / 6
        self.assertEqual(salida_lineas[4], 2)    # 20 % 6

    def test_06_traduccion_condicional_if_else(self):
        """Verifica la traducción de comparaciones relacionales y bifurcaciones condicionales if-else."""
        codigo_true = """
        int a = 10;
        int b = 5;
        int res;
        if (a > b) {
            res = 100;
        } else {
            res = 200;
        }
        cout << res;
        """
        res_t = generar_codigo_objeto_completo(codigo_true, optimizar=False)
        self.assertTrue(res_t.resultado_ejecucion.exitoso)
        self.assertEqual(res_t.resultado_ejecucion.salida.strip(), "100")

        codigo_false = """
        int a = 3;
        int b = 8;
        int res;
        if (a > b) {
            res = 100;
        } else {
            res = 200;
        }
        cout << res;
        """
        res_f = generar_codigo_objeto_completo(codigo_false, optimizar=False)
        self.assertTrue(res_f.resultado_ejecucion.exitoso)
        self.assertEqual(res_f.resultado_ejecucion.salida.strip(), "200")

    def test_07_traduccion_ciclo_while(self):
        """Verifica la traducción y ejecución funcional de ciclos con salto incondicional y condicional."""
        codigo = """
        int sum = 0;
        int i = 1;
        while (i <= 5) {
            sum = sum + i;
            i = i + 1;
        }
        cout << sum;
        """
        res = generar_codigo_objeto_completo(codigo, optimizar=True)
        self.assertTrue(res.resultado_ejecucion.exitoso)
        self.assertEqual(res.resultado_ejecucion.salida.strip(), "15")
        self.assertEqual(res.resultado_ejecucion.memoria_final.get("sum"), 15)
        self.assertEqual(res.resultado_ejecucion.memoria_final.get("i"), 6)

    def test_08_estructura_archivo_objeto_asm(self):
        """Verifica que el código .asm contenga secciones compatibles con TASM, entrada y epílogo."""
        codigo = "int x = 42; cout << x;"
        res = generar_codigo_objeto_completo(codigo)
        asm = res.codigo_asm

        # Directivas de ensamblador TASM / x86
        self.assertIn(".386", asm)
        self.assertIn(".MODEL SMALL", asm)
        self.assertIn(".STACK", asm)
        self.assertIn(".DATA", asm)
        self.assertIn(".CODE", asm)

        # Procedimientos auxiliares y entrada principal
        self.assertIn("PRINT_INT PROC NEAR", asm)
        self.assertIn("START:", asm)
        self.assertIn("main:", asm)
        self.assertIn("mov ax, @data", asm)
        self.assertIn("mov ds, ax", asm)
        self.assertIn("push bp", asm)
        self.assertIn("mov bp, sp", asm)

        # Epílogo compatible con DOS / TASM
        self.assertIn("mov ax, 4C00h", asm)
        self.assertIn("int 21h", asm)
        self.assertIn("END START", asm)

        # Si TASM32 está instalado, verificar que compila con 0 errores
        tasm_path = r"C:\Program Files (x86)\GUI Turbo Assembler\BIN\TASM32.EXE"
        if os.path.exists(tasm_path):
            import subprocess
            temp_asm = os.path.join(os.path.dirname(__file__), "temp_tasm_test.asm")
            with open(temp_asm, "w", encoding="utf-8") as f:
                f.write(asm)
            try:
                proc = subprocess.run([tasm_path, "/ml", "/z", "/zi", temp_asm], capture_output=True, text=True)
                self.assertEqual(proc.returncode, 0, f"TASM falló: {proc.stdout}")
            finally:
                for ext in (".asm", ".obj"):
                    p = os.path.splitext(temp_asm)[0] + ext
                    if os.path.exists(p):
                        try:
                            os.remove(p)
                        except OSError:
                            pass

    def test_09_pipeline_integrado_con_optimizacion(self):
        """Verifica el flujo integral completo desde código intermedio optimizado hasta código objeto."""
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
        cout << x;
        """
        res = generar_codigo_objeto_completo(codigo, optimizar=True)

        # El optimizador debió eliminar redundancias
        self.assertIsNotNone(res.optimizador)
        self.assertLess(len(res.cuadruplos_optimizados), len(res.cuadruplos_originales))

        # El archivo .asm y ejecución deben ser correctos
        self.assertTrue(res.resultado_ejecucion.exitoso)
        self.assertEqual(res.resultado_ejecucion.salida.strip(), "1")

    def test_10_manejo_de_derrames_spills(self):
        """Verifica que si la cantidad de variables vivas concurrentes supera K registros, se asignen derrames."""
        # Creamos un grafo de interferencia con 8 variables que interfieren todas entre sí (K8)
        # y limitamos los registros físicos a K=4
        cuads = []
        for i in range(1, 9):
            cuads.append(Cuadruplo(i, '=', str(i), '', f'v{i}'))
        # Una instrucción que use todas a la vez para forzar interferencia simultánea
        for i in range(1, 8):
            cuads.append(Cuadruplo(10 + i, '+', f'v{i}', f'v{i+1}', f't{i}'))

        liv = construir_grafo_interferencia(cuads)
        alloc = RegisterAllocator(liv, k_fisicos=4)

        # Con 8 variables y temporales con alta concurrencia y solo 4 registros físicos,
        # deben generarse derrames (spills)
        m = alloc.obtener_metricas()
        self.assertGreater(m["numero_cromatico"], 4)
        self.assertGreater(m["spills"], 0)

        # Comprobar que las variables derramadas tienen ubicación en memoria
        spill_encontrado = any(info.es_spill for info in alloc.tabla_asignacion.values())
        self.assertTrue(spill_encontrado)


if __name__ == "__main__":
    unittest.main()

