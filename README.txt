==============================================================================
  COMPILADOR C++ - GENERADOR DE CÓDIGO INTERMEDIO (IR)
  Materia: Lenguajes y Autómatas II
  Implementación: Python 3
  Interfaz Principal de Usuario: Interfaz Gráfica de Usuario (GUI)
==============================================================================

1. DESCRIPCIÓN GENERAL
Este sistema es un compilador completo para un subconjunto representativo
del lenguaje C++, abarcando las fases esenciales del proceso de compilación:
  • Análisis Léxico (tokenización y detección de errores léxicos)
  • Análisis Sintáctico (construcción y visualización del árbol AST)
  • Análisis Semántico (comprobación de tipos y tabla de símbolos)
  • Generación de Código Intermedio (IR):
      - Cuádruplos estándar: #N (operador, argumento1, argumento2, resultado)
      - Código de Tres Direcciones (3AC): instrucciones simples legibles
      - Notación Postfija (RPN): recorrido en postorden del AST de expresiones
      - Exportación oficial a archivos .ir

El medio principal y recomendado para interactuar y evaluar el proyecto
es la Interfaz Gráfica (GUI).


2. ESTRUCTURA DE ARCHIVOS Y CARPETAS
CompiladorU2/
├── main.py                     <-- Punto de entrada principal para abrir la GUI
├── AnalisisSema.py             <-- Entorno gráfico y motor de análisis léxico,      ├── compilador/
│   ├── __init__.py
│   └── ir/
│       ├── __init__.py
│       └── generator.py        <-- Generador unificado de Código Intermedio (IR)
├── ejemplos/                   <-- Programas de prueba en C++ y archivos .ir generados
│   ├── aritmetica.cpp          <-- Expresión: x = 3 + 4 * 2;
│   ├── aritmetica.ir           <-- Cuádruplos generados de aritmetica.cpp
│   ├── if_else.cpp             <-- Control de flujo: if (a > b) ...
│   └── if_else.ir              <-- Cuádruplos generados de if_else.cpp
├── tests/                      <-- Suite de pruebas automatizadas
│   ├── __init__.py
│   ├── test_ir_generator.py    <-- Pruebas unitarias del generador de IR
│   └── test_casos_completos.py <-- Pruebas exhaustivas de todas las construcciones 

3. REQUISITOS DEL SISTEMA
  • Python 3.8 o superior (con soporte estándar para Tkinter).
  • Compatible con sistemas operativos Windows, Linux y macOS.


4. INSTRUCCIONES DE EJECUCIÓN (INTERFAZ GRÁFICA)

Paso 1: Abrir una terminal en la carpeta principal del proyecto y ejecutar:
       python main.py
       (O bien: python AnalisisSema.py)

Paso 2: En la ventana gráfica del Compilador:
  • Utilice el menú desplegable "Cargar caso de prueba" en la barra superior
    para cargar inmediatamente cualquiera de los casos preparados:
      1. Aritmética básica (x = 3 + 4 * 2;)
      2. Precedencia con resta (y = 8 - 2 * 3;)
      3. Paréntesis modifican precedencia ((8 - 2) * 3)
      4. Condicional (if - else)
      5. Ciclo While
      6. Ciclo For con salida
      7. Operador Ternario
      8. Función con retorno
      9. Ejemplo original (cuadradoLimitado)
  • O bien, escriba o pegue libremente cualquier código C++ en el editor.

Paso 3: Presione el botón:
       [ Código Intermedio (IR) ]

Paso 4: Visualización de resultados:
  • En la misma ventana principal, en el panel de pestañas inferior, se
    actualizarán automáticamente:
      - Pestaña "Cuádruplos (IR)": tabla ordenada con columnas (#, op, arg1, arg2, res)
      - Pestaña "Tres Direcciones (3AC)": código 3AC claro
      - Pestaña "Notación Postfija": expresiones en notación postorden (RPN)
  • Simultáneamente, se abre una ventana modal completa donde puede:
      - Guardar directamente el archivo en formato estándar .ir mediante "Guardar archivo .ir"
      - Copiar las instrucciones al portapapeles con "Copiar código .ir"


5. EJECUCIÓN POR LÍNEA DE COMANDOS (CLI - OPCIONAL)
Si desea compilar directamente un archivo fuente .cpp a código intermedio .ir:
    python compilador/ir/generator.py ejemplos/aritmetica.cpp
Generará automáticamente el archivo: ejemplos/aritmetica.ir


6. EJECUCIÓN DE PRUEBAS AUTOMATIZADAS
Para ejecutar la suite completa de 26 pruebas unitarias integradas:
    python -m unittest discover -s tests -p "test_*.py"
