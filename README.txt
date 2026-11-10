==============================================================================
  COMPILADOR C++ - ANÁLISIS, GENERACIÓN DE IR, OPTIMIZACIÓN Y CÓDIGO OBJETO
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
  • Asignación de Registros mediante Coloración de Grafos de Interferencia:
      - Análisis formal de variables vivas (Liveness Analysis) hacia atrás punto fijo.
      - Cálculo de conjuntos In[i], Out[i], Def[i], Use[i] e intervalos de vida útil.
      - Construcción formal del Grafo de Interferencia: variables simultáneamente vivas
        no pueden compartir registro (garantía de no interferencia).
      - Algoritmo de coloración mínima exacta (chi(G)) y heurística DSATUR.
      - Mapeo consistente a registros físicos x86 (EAX, EBX, ECX, EDX, ESI, EDI)
        y virtuales (R0..Rn), con manejo formal de derrames (spills) en memoria si se requiere.
      - Tabla de Asignación de Registros detallada con rangos, grado y ubicación.
  • Generación y Simulación de Código Objeto (.asm):
      - Traducción de operaciones aritméticas y asignación (+, -, *, /, %, neg, =).
      - Traducción de estructuras de control y saltos condicionales/incondicionales (if, while, cmp, je, jne, jmp, labels).
      - Traducción de rutinas de entrada/salida (print / cout con printf, read / cin con scanf).
      - Estructuración modular en secciones de ensamblador x86:
          * section .data: literales de cadena y cadenas de formato.
          * section .bss: variables de memoria principal y derrames.
          * section .text: etiquetas, prólogo, cuerpo de funciones y epílogo de salida.
      - Simulador / Emulador de arquitectura x86 integrado para validación funcional autónoma
        con captura de salida estándar (stdout), registros de CPU y memoria de variables.

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
│   ├── opt/                    <-- Motor de Optimización y Grafo de Flujo (GFG / CFG)
│   │   ├── __init__.py
│   │   ├── basic_block.py      <-- Particionado e identificación de Bloques Básicos
│   │   ├── cfg.py              <-- Grafo de Flujo de Control, Sucesores y Complejidad
│   │   ├── optimizer.py        <-- Motor de transformación y punto fijo (Folding, CSE, DCE)
│   │   ├── graph_coloring.py   <-- Motor de coloración de grafos y canvas interactivo
│   │   ├── visualizer.py       <-- Canvas interactivo para renderizado del CFG
│   │   └── metrics.py          <-- Reportes formales y exportación before.ir / after.ir
│   └── codegen/                <-- Módulo de Generación de Código Objeto y Asignación
│       ├── __init__.py         <-- Orquestador del pipeline final y exportaciones
│       ├── liveness.py         <-- Análisis de variables vivas y grafo de interferencia
│       ├── register_allocator.py <-- Asignador óptimo de registros por coloración
│       ├── code_generator.py   <-- Traductor a ensamblador x86 (.asm)
│       └── simulator.py        <-- Emulador y runner de pruebas x86 simplificado
├── ejemplos/                   <-- Casos de prueba en C++, .ir, .asm y evidencias
│   ├── aritmetica.cpp          <-- Expresión: int x = 3 + 4 * 2;
│   ├── aritmetica_optimizado.ir<-- Cuádruplos intermedios optimizados
│   ├── aritmetica.asm          <-- Código objeto ensamblador generado
│   ├── aritmetica_tabla_registros.txt <-- Asignación de registros
│   ├── aritmetica_evidencia_ejecucion.txt <-- Salida de ejecución y estado CPU
│   ├── if_else.cpp             <-- Control de flujo if-else
│   ├── if_else_optimizado.ir   <-- Cuádruplos optimizados
│   ├── if_else.asm             <-- Código objeto ensamblador generado
│   ├── if_else_tabla_registros.txt
│   ├── if_else_evidencia_ejecucion.txt
│   ├── ciclo_while.cpp         <-- Ciclo con acumulador y condición
│   ├── ciclo_while_optimizado.ir
│   ├── ciclo_while.asm
│   ├── ciclo_while_tabla_registros.txt
│   ├── ciclo_while_evidencia_ejecucion.txt
│   ├── programa_completo_u4.cpp <-- Integración completa (aritmética, while e if)
│   ├── programa_completo_u4_optimizado.ir
│   ├── programa_completo_u4.asm
│   ├── programa_completo_u4_tabla_registros.txt
│   └── programa_completo_u4_evidencia_ejecucion.txt
├── documentacion/              <-- Documentación técnica y especificaciones
│   └── DOCUMENTACION_TECNICA_U4.md <-- Documento técnico exhaustivo
└── tests/                      <-- Suite completa de pruebas automatizadas (56 tests)
    ├── __init__.py
    ├── test_ir_generator.py    <-- Pruebas del generador de IR
    ├── test_casos_completos.py <-- Pruebas de construcciones sintácticas
    ├── test_optimizacion_u3.py <-- Pruebas de optimización y CFG
    ├── test_coloracion_grafos.py <-- Pruebas de coloración de grafos
    └── test_codegen_u4.py      <-- Pruebas de código objeto, liveness y ejecución (10 tests)


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
      13. Clase y Función (CodigoIntermedio)
      14. Código Objeto y Ciclo While (U4)
      15. Reutilización de Registros (Coloración Óptima)
  • O bien, escriba o pegue libremente cualquier código C++ en el editor.

Paso 3: Botones de análisis disponibles en la barra superior:
  • [ Análisis Léxico ]         -> Muestra tabla de tokens y posiciones
  • [ Análisis Sintáctico ]     -> Valida estructura y habilita [ Ver AST ]
  • [ Análisis Semántico ]      -> Comprueba tipos y tabla de símbolos
  • [ Código Intermedio (IR) ]  -> Genera Cuádruplos, 3AC y Notación Postfija
  • [ Optimización (CFG / IR) ] -> Ejecuta el pipeline de optimización de cuádruplos
  • [ Coloración de Grafos ]    -> Visualiza el grafo de interferencia y coloración interactiva
  • [ Código Objeto (.asm) ]    -> Genera el archivo ensamblador y asigna registros
  • [ Ejecutar Objeto ]         -> Simula la ejecución y muestra evidencias en consola
  • [ Compilar Todo ]           -> Ejecuta todo el flujo del compilador de principio a fin

Paso 4: Pestañas de resultados integradas en la interfaz:
  • "Tokens Léxicos": tokens con tipo y posición.
  • "Cuádruplos (IR)": cuádruplos originales (#N op, arg1, arg2, res).
  • "Tres Direcciones (3AC)": código 3AC original.
  • "Notación Postfija": expresiones en postorden (RPN).
  • "Tabla de Símbolos": variables, tipos y ámbitos.
  • "Bloques Básicos": bloques B1..Bn con líderes y alcanzabilidad.
  • "Grafo de Flujo (CFG)": visualizador gráfico interactivo con zoom y conmutador.
  • "Tabla de Sucesores": sucesores en el grafo (Fin, bifurcaciones, inalcanzables).
  • "IR Optimizado": cuádruplos optimizados, 3AC y comparativa lado a lado.
  • "Tabla de Transformaciones": detalle formal de cada optimización aplicada.
  • "Métricas y Análisis": reducción %, complejidad ciclomática y conclusiones.
  • "Coloración de Grafos": visualizador interactivo de grafos de interferencia.
  • "Tabla de Registros": tabla formal de variables, rangos de vida, grado de interferencia,
    color mínimo asignado, registros físicos x86 (EAX..EDI) y memoria.
  • "Código Objeto (.asm)": visor del archivo ensamblador x86 (.asm) completo, ordenado
    y estructurado en .data, .bss y .text.
  • "Evidencia de Ejecución": consola de salida (STDOUT), estado de registros de la CPU,
    estado de variables en memoria y reporte formal de ejecución.

Paso 5: Opciones de exportación de archivos:
  • "Guardar before.ir"              -> Cuádruplos previos a optimizar
  • "Guardar after.ir"               -> Cuádruplos finales optimizados
  • "Guardar Archivo .asm"           -> Archivo ensamblador x86 ejecutable
  • "Guardar Tabla Registros (.txt)" -> Tabla formal de asignación de registros
  • "Exportar Evidencias U4 (.txt)"  -> Reporte integral de todas las evidencias


5. EJECUCIÓN DE PRUEBAS AUTOMATIZADAS
Para ejecutar la suite completa de 56 pruebas unitarias e integradas:
    python -m unittest discover -s tests -p "test_*.py"

Para ejecutar exclusivamente las pruebas de generación de código objeto:
    python -m unittest tests/test_codegen_u4.py
