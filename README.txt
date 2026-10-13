==============================================================================
  COMPILADOR C++ - ANÁLISIS, GENERACIÓN DE IR Y OPTIMIZACIÓN (CFG / GFG)
  Materia: Lenguajes y Autómatas II
  Implementación: Python 3
  Interfaz Principal de Usuario: Interfaz Gráfica de Usuario (GUI)
==============================================================================

1. DESCRIPCIÓN GENERAL
Este sistema es un compilador completo para un subconjunto representativo
del lenguaje C++, abarcando todas las fases esenciales del proceso de compilación:
  • Análisis Léxico: tokenización y detección de errores léxicos.
  • Análisis Sintáctico: construcción y visualización del árbol AST.
  • Análisis Semántico: comprobación de tipos y tabla de símbolos con ámbitos.
  • Generación de Código Intermedio (IR):
      - Cuádruplos estándar: #N (operador, argumento1, argumento2, resultado)
      - Código de Tres Direcciones (3AC): instrucciones simples legibles
      - Notación Postfija (RPN): recorrido en postorden del AST de expresiones
      - Exportación oficial a archivos .ir
  • Optimización de Código Intermedio mediante Grafo de Flujo de Control (GFG / CFG):
      - Identificación y delimitación formal de Bloques Básicos (algoritmo del dragón).
      - Construcción del Grafo de Flujo de Control (CFG / GFG) con nodos, aristas y Tabla de Sucesores.
      - Análisis de alcanzabilidad y detección de código inalcanzable.
      - Técnicas de optimización aplicadas:
          * Constant Folding (Plegado de Constantes aritméticas, relacionales y lógicas).
          * Propagación de Constantes (local e inter-bloque) y Propagación de Copias.
          * Eliminación de Subexpresiones Comunes (CSE con soporte conmutativo).
          * Eliminación de Código Muerto (DCE respetando efectos secundarios).
          * Eliminación de Bloques Inalcanzables (tras return o ramas podadas).
          * Simplificación de Saltos y Evaluación de Condiciones Constantes.
      - Tabla de Transformaciones formal (#, Bloque, Técnica, Original, Optimizado, Justificación).
      - Tabla comparativa de transformaciones y reducción del CFG.
      - Cálculo de Complejidad Ciclomática (McCabe) y caminos de ejecución antes y después.
      - Exportación de archivos estándar: before.ir, after.ir y reporte completo.

El medio principal y recomendado para interactuar y evaluar el proyecto
es la Interfaz Gráfica (GUI).


2. ESTRUCTURA DE ARCHIVOS Y CARPETAS
AnalizadorLYA2/
├── main.py                     <-- Punto de entrada principal para abrir la GUI
├── AnalisisSema.py             <-- Módulo de compatibilidad hacia main.py
├── compilador/
│   ├── __init__.py
│   ├── ir/
│   │   ├── __init__.py
│   │   └── generator.py        <-- Generador unificado de Código Intermedio (IR)
│   └── opt/                    <-- Motor de Optimización y Grafo de Flujo (GFG / CFG)
│       ├── __init__.py
│       ├── basic_block.py      <-- Particionado e identificación de Bloques Básicos
│       ├── cfg.py              <-- Grafo de Flujo de Control, Sucesores y Complejidad
│       ├── optimizer.py        <-- Motor de transformación y punto fijo (Folding, CSE, DCE)
│       ├── visualizer.py       <-- Canvas interactivo para renderizado del CFG
│       └── metrics.py          <-- Reportes formales y exportación before.ir / after.ir
├── ejemplos/                   <-- Programas de prueba en C++ y archivos .ir generados
│   ├── aritmetica.cpp          <-- Expresión: x = 3 + 4 * 2;
│   ├── aritmetica.ir           <-- Cuádruplos generados de aritmetica.cpp
│   ├── if_else.cpp             <-- Control de flujo: if (a > b) ...
│   └── if_else.ir              <-- Cuádruplos generados de if_else.cpp
├── tests/                      <-- Suite de pruebas automatizadas
│   ├── __init__.py
│   ├── test_ir_generator.py    <-- Pruebas unitarias del generador de IR
│   ├── test_casos_completos.py <-- Pruebas exhaustivas de todas las construcciones sintácticas
│   └── test_optimizacion_u3.py <-- Pruebas completas de optimización y CFG (11 pruebas)


3. REQUISITOS DEL SISTEMA
  • Python 3.8 o superior (con soporte estándar para Tkinter).
  • Compatible con sistemas operativos Windows, Linux y macOS.
  • Sin dependencias externas obligatorias (100% biblioteca estándar de Python).


4. INSTRUCCIONES DE EJECUCIÓN (INTERFAZ GRÁFICA)

Paso 1: Abrir una terminal en la carpeta principal del proyecto y ejecutar:
       python main.py
       (O bien: python AnalisisSema.py)

Paso 2: En la ventana gráfica del Compilador:
  • Utilice el menú desplegable "Cargar caso de prueba" en la barra superior:
      1. Aritmética básica (x = 3 + 4 * 2;)
      2. Precedencia con resta (y = 8 - 2 * 3;)
      3. Paréntesis modifican precedencia ((8 - 2) * 3)
      4. Condicional (if - else)
      5. Ciclo While
      6. Ciclo For con salida
      7. Operador Ternario
      8. Función con retorno
      9. Ejemplo original (cuadradoLimitado)
      10. Optimización CFG (Integrador U3)
      11. Plegado y Subexpresiones (CSE)
      12. Control de Flujo y Código Inalcanzable
  • O bien, escriba o pegue libremente cualquier código C++ en el editor.

Paso 3: Botones de análisis disponibles:
  • [ Análisis Léxico ]       -> Muestra tabla de tokens y posiciones
  • [ Análisis Sintáctico ]   -> Valida estructura y habilita [ Ver AST ]
  • [ Análisis Semántico ]    -> Comprueba tipos y tabla de símbolos
  • [ Código Intermedio (IR) ]-> Genera Cuádruplos, 3AC y Notación Postfija
  • [ Optimización (CFG / IR) ]-> Ejecuta el pipeline completo de la Unidad 3

Paso 4: Pestañas de resultados integrados:
  • "📋 Tokens Léxicos": tokens con tipo y posición
  • "⚡ Cuádruplos (IR)": cuádruplos originales (#N op, arg1, arg2, res)
  • "🔤 Tres Direcciones (3AC)": código 3AC original
  • "🏷️ Notación Postfija": expresiones en postorden (RPN)
  • "📊 Tabla de Símbolos": variables, tipos y ámbitos
  • "🧱 Bloques Básicos": bloques B1..Bn con líderes y alcanzabilidad
  • "🕸️ Grafo de Flujo (CFG)": visualizador gráfico interactivo con zoom y conmutador (CFG Original vs Optimizado)
  • "📑 Tabla de Sucesores": sucesores en el grafo (Fin, bifurcaciones, inalcanzables)
  • "✨ IR Optimizado": cuádruplos optimizados, 3AC y comparativa lado a lado
  • "📋 Tabla de Transformaciones": detalle formal de cada optimización aplicada
  • "📈 Métricas y Análisis": reducción %, complejidad ciclomática y conclusiones

Paso 5: Opciones de exportación:
  • "💾 Guardar before.ir" -> Guarda el código intermedio previo a la optimización
  • "💾 Guardar after.ir"  -> Guarda el código intermedio final optimizado
  • "📄 Guardar Reporte (.txt)" -> Exporta el informe técnico formal estructurado


5. EJECUCIÓN DE PRUEBAS AUTOMATIZADAS
Para ejecutar la suite completa de 37 pruebas unitarias integradas:
    python -m unittest discover -s tests -p "test_*.py"
