"""
Pruebas unitarias para el módulo de Coloración de Grafos (Asignación de Registros).
Verifica:
- Parseo de listas de adyacencia (formatos estándar, comas, espacios, comentarios).
- Número cromático mínimo exacto para grafo con subgrafo triangular K3.
- Coloración propia sin conflictos para diversos grafos (bipartito, ciclos, completos, ruedas).
- Integración y verificación de restricciones de adyacencia.
"""

import unittest
from compilador.opt.graph_coloring import (
    Grafo, parsear_grafo_texto, colorear_grafo_minimo, verificar_coloracion
)


class TestColoracionGrafos(unittest.TestCase):

    def test_grafo_conexo_g1(self):
        """
        Caso de prueba: Grafo G1 con 6 nodos y subgrafo K3 (D-E-F).
        A: B,F
        B: C
        C: D
        D: E, F
        E: F
        Triángulo D-E-F (K3) -> Requiere exactamente 3 colores.
        Nodos adyacentes deben tener colores diferentes.
        """
        texto = (
            "A: B,F\n"
            "B: C\n"
            "C: D\n"
            "D: E, F\n"
            "E: F\n"
        )
        grafo = parsear_grafo_texto(texto)
        self.assertEqual(len(grafo.nodos), 6)
        # Verificar aristas
        aristas = grafo.obtener_aristas()
        self.assertIn(("A", "B"), aristas)
        self.assertIn(("A", "F"), aristas)
        self.assertIn(("B", "C"), aristas)
        self.assertIn(("C", "D"), aristas)
        self.assertIn(("D", "E"), aristas)
        self.assertIn(("D", "F"), aristas)
        self.assertIn(("E", "F"), aristas)

        coloracion, k, valida = colorear_grafo_minimo(grafo)
        self.assertTrue(valida, "La coloración debe ser propia y sin conflictos")
        self.assertEqual(k, 3, "El número cromático mínimo debe ser 3")

        # Verificar directamente que no hay vecinos con el mismo color
        es_val, conflictos = verificar_coloracion(grafo, coloracion)
        self.assertTrue(es_val)
        self.assertEqual(len(conflictos), 0)

    def test_grafo_bipartito(self):
        """Grafo bipartito debe colorearse con exactamente 2 colores."""
        texto = (
            "X1: Y1, Y2\n"
            "X2: Y1, Y2\n"
            "Y1:\n"
            "Y2:\n"
        )
        grafo = parsear_grafo_texto(texto)
        coloracion, k, valida = colorear_grafo_minimo(grafo)
        self.assertTrue(valida)
        self.assertEqual(k, 2)
        self.assertEqual(coloracion["X1"], coloracion["X2"])
        self.assertEqual(coloracion["Y1"], coloracion["Y2"])
        self.assertNotEqual(coloracion["X1"], coloracion["Y1"])

    def test_grafo_completo_k4(self):
        """Grafo completo K4 requiere exactamente 4 colores."""
        texto = (
            "A: B, C, D\n"
            "B: C, D\n"
            "C: D\n"
            "D:\n"
        )
        grafo = parsear_grafo_texto(texto)
        coloracion, k, valida = colorear_grafo_minimo(grafo)
        self.assertTrue(valida)
        self.assertEqual(k, 4)
        colores_usados = {coloracion[n] for n in grafo.nodos}
        self.assertEqual(len(colores_usados), 4)

    def test_ciclo_impar_c5(self):
        """Ciclo impar C5 requiere 3 colores."""
        texto = (
            "1: 2, 5\n"
            "2: 3\n"
            "3: 4\n"
            "4: 5\n"
            "5:\n"
        )
        grafo = parsear_grafo_texto(texto)
        coloracion, k, valida = colorear_grafo_minimo(grafo)
        self.assertTrue(valida)
        self.assertEqual(k, 3)

    def test_nodos_aislados(self):
        """Nodos sin aristas deben poder usar 1 solo color."""
        texto = (
            "N1:\n"
            "N2:\n"
            "N3:\n"
        )
        grafo = parsear_grafo_texto(texto)
        coloracion, k, valida = colorear_grafo_minimo(grafo)
        self.assertTrue(valida)
        self.assertEqual(k, 1)
        self.assertEqual(coloracion["N1"], 0)
        self.assertEqual(coloracion["N2"], 0)
        self.assertEqual(coloracion["N3"], 0)

    def test_parseo_formatos_flexibles(self):
        """Verifica que el parser soporte comentarios, espacios variados y flechas."""
        texto = (
            "# Comentario inicial\n"
            "  A -> B, C   // aristas desde A\n"
            "B: C\n"
            "D // nodo aislado sin dos puntos\n"
        )
        grafo = parsear_grafo_texto(texto)
        self.assertIn("A", grafo.nodos)
        self.assertIn("B", grafo.nodos)
        self.assertIn("C", grafo.nodos)
        self.assertIn("D", grafo.nodos)
        self.assertIn("B", grafo.adyacencia["A"])
        self.assertIn("C", grafo.adyacencia["A"])
        self.assertIn("C", grafo.adyacencia["B"])
        self.assertEqual(len(grafo.adyacencia["D"]), 0)


if __name__ == "__main__":
    unittest.main()
