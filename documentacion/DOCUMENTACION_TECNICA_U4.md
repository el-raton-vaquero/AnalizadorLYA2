# DOCUMENTACIÓN TÉCNICA DEL PROYECTO
## COMPILADOR C++: FASE FINAL DE GENERACIÓN DE CÓDIGO OBJETO Y ASIGNACIÓN DE REGISTROS

---

### 1. Resumen Ejecutivo y Alcance
El presente proyecto implementa la fase final del compilador de un subconjunto representativo de C++, integrando la **Generación de Código Objeto** a partir del **Código Intermedio Optimizado** (cuádruplas), la **Asignación Óptima de Registros mediante Coloración de Grafos de Interferencia**, el control de flujo y la producción de un archivo objeto ensamblador (.asm) ordenado, completo y ejecutable.

El sistema garantiza que:
1. Las variables activas simultáneamente (con interferencia) **nunca** compartan el mismo registro.
2. Se minimiza el número de registros utilizados mediante el cálculo del número cromático mínimo $\chi(G)$.
3. Todas las operaciones aritméticas, lógicas, asignaciones y estructuras de control se traducen con estricta equivalencia semántica.
4. Se proporciona una herramienta de simulación de arquitectura x86 para validar y evidenciar el 100% de la funcionalidad de ejecución.

---

### 2. Arquitectura Modular del Compilador

```
AnalizadorLYA2/
├── main.py                     # Interfaz Gráfica (Tkinter) y orquestación general
├── AnalisisSema.py             # Compatibilidad de punto de entrada
├── compilador/
│   ├── ir/
│   │   └── generator.py        # Generador de Código Intermedio (Cuádruplos, 3AC, Postfija)
│   ├── opt/
│   │   ├── basic_block.py      # Particionado formal de Bloques Básicos
│   │   ├── cfg.py              # Grafo de Flujo de Control y Tabla de Sucesores
│   │   ├── optimizer.py        # Motor de optimizaciones (Folding, CSE, DCE, etc.)
│   │   ├── graph_coloring.py   # Algoritmo DSATUR y búsqueda exacta de coloración
│   │   ├── visualizer.py       # Canvas interactivo para renderizado del CFG
│   │   └── metrics.py          # Reportes y análisis de reducción
│   └── codegen/                # NUEVO MÓDULO: Generación de Código Objeto
│       ├── __init__.py         # API pública y pipeline orquestador
│       ├── liveness.py         # Análisis de variables vivas y grafo de interferencia
│       ├── register_allocator.py # Asignación de registros por coloración de grafos
│       ├── code_generator.py   # Generador de ensamblador x86 (.asm)
│       └── simulator.py        # Emulador y runner de ejecución x86
├── ejemplos/                   # Códigos fuente, .ir, .asm y evidencias de ejecución
├── documentacion/              # Documentación técnica y especificaciones
└── tests/                      # Suite de 56 pruebas automatizadas integradas
```

---

### 3. Módulo de Análisis de Variables Vivas (Liveness Analysis)

#### 3.1 Fundamento Teórico
El análisis de liveness determina en qué puntos del programa el valor de una variable puede ser potencialmente leído antes de ser reescrito. Una variable está **viva** (activa) en una instrucción si su valor actual es utilizado posteriormente en alguna trayectoria de ejecución.

Se resuelve mediante el sistema de ecuaciones de flujo de datos hacia atrás (*backward dataflow equations*):
$$\text{Out}[i] = \bigcup_{s \in \text{Succ}[i]} \text{In}[s]$$
$$\text{In}[i] = \text{Use}[i] \cup (\text{Out}[i] \setminus \text{Def}[i])$$

Donde:
- $\text{Def}[i]$: conjunto de variables que son definidas (escritas) en la instrucción $i$.
- $\text{Use}[i]$: conjunto de variables que son leídas en la instrucción $i$.
- $\text{Succ}[i]$: conjunto de instrucciones sucesoras en el grafo de flujo de control.

#### 3.2 Construcción del Grafo de Interferencia
1. **Nodos**: Cada variable del programa y cada temporal generado por el compilador constituye un nodo del grafo.
2. **Aristas**: Se genera una arista no dirigida entre dos nodos $u$ y $v$ ($u \neq v$) si y solo si ambas variables interfieren, es decir, están activas simultáneamente en algún punto del programa:
   - Para toda definición $d \in \text{Def}[i]$, se añade arista con cada $v \in \text{Out}[i]$ (salvo cuando $i$ es una asignación de copia directa $d = v$).
   - Para todo par de variables $u, v \in \text{Out}[i]$, se añade arista indicando coexistencia activa simultánea.
3. **Garantía**: Dos variables conectadas por una arista en el grafo **no pueden** compartir la misma posición de registro de la CPU.

---

### 4. Módulo de Asignación de Registros mediante Coloración de Grafos

#### 4.1 Algoritmo de Coloración
El problema de asignación de registros se modela como el problema clásico de **coloración de vértices en grafos**:
- Cada color representa un registro físico de la máquina.
- Nodos adyacentes no pueden recibir el mismo color.
- Se busca la coloración que utilice el menor número posible de colores ($\chi(G)$, número cromático).

El módulo implementa una combinación de la heurística **DSATUR** (Degree of Saturation) con **búsqueda exacta por ramificación y acotación (Branch & Bound)** para garantizar el número cromático mínimo exacto.

#### 4.2 Mapeo a Registros de la CPU
Se utiliza el pool estándar de registros de propósito general de la arquitectura x86 (IA-32):
- Color 0 ($C_1$) $\rightarrow$ Registro Virtual $R_0$ $\rightarrow$ **EAX**
- Color 1 ($C_2$) $\rightarrow$ Registro Virtual $R_1$ $\rightarrow$ **EBX**
- Color 2 ($C_3$) $\rightarrow$ Registro Virtual $R_2$ $\rightarrow$ **ECX**
- Color 3 ($C_4$) $\rightarrow$ Registro Virtual $R_3$ $\rightarrow$ **EDX**
- Color 4 ($C_5$) $\rightarrow$ Registro Virtual $R_4$ $\rightarrow$ **ESI**
- Color 5 ($C_6$) $\rightarrow$ Registro Virtual $R_5$ $\rightarrow$ **EDI**

Si la cantidad de variables simultáneamente vivas supera $K=6$, los colores excedentes se asignan como **derrames en memoria (spills)** en el marco de pila (`[ebp - 4*k]`) o variables estáticas en `.bss`.

#### 4.3 Tabla de Asignación de Registros
La tabla generada por el compilador incluye:
1. **Variable**: Nombre de la variable o identificador temporal ($t_1, t_2$).
2. **Tipo**: Variable de usuario o temporal interno del compilador.
3. **Rango de Vida**: Intervalo $[\text{inicio}, \text{fin}]$ en número de cuádruplas.
4. **Grado**: Cantidad de variables con las que interfiere.
5. **Variables con Interferencia**: Lista explícita de vecinos en el grafo.
6. **Color**: Índice del color asignado ($C_1, C_2, \dots$).
7. **Reg. Virtual**: Etiqueta $R_0, R_1, \dots$
8. **Reg. Físico x86**: Registro asignado (EAX, EBX, ECX, EDX, ESI, EDI).
9. **Ubicación**: Indicación formal de residencia (Registro o Memoria Spill).

---

### 5. Módulo de Generación de Código Objeto (.asm)

#### 5.1 Estructura del Archivo Ensamblador (Compatible con TASM / GUI Turbo Assembler)
El archivo generado sigue el formato estándar de **Borland Turbo Assembler (TASM)** y MASM x86 en modo 32 bits real/protegido:
```assembly
; Cabecera informativa con fecha, optimización y número cromático

.386
.MODEL SMALL
.STACK 1000h

.DATA
    ; Variables del programa almacenadas en memoria principal
    x           DD 0
    spill_t1    DD 0
    ; Cadenas de texto del programa
    str_0       DB "Texto...", 13, 10, "$"

.CODE

; Rutinas auxiliares autónomas de E/S con interrupciones de DOS (INT 21h):
; - PRINT_INT: Imprime el entero en EAX con salto de línea.
; - PRINT_STR: Imprime la cadena terminada en '$' (offset en DX).
; - READ_INT:  Lee un entero desde teclado y lo retorna en EAX.

START:
main:
    mov ax, @data
    mov ds, ax
    mov es, ax

    push ebp                    ; Prólogo estándar de marco de pila
    mov ebp, esp
    sub esp, 16                 ; Reserva de espacio para derrames y variables locales

    ; --- Cuerpo traducido de cuádruplas optimizadas ---
    ...

    ; --- Epílogo de terminación exitosa ---
    mov esp, ebp
    pop ebp
    mov ax, 4C00h               ; Servicio de retorno al sistema operativo DOS
    int 21h

END START
```

#### 5.2 Reglas de Traducción por Tipo de Instrucción

| Operación IR | Cuádruplo | Traducción Ensamblador TASM (x86) |
|---|---|---|
| **Asignación** | `(=, 10, , x)` | `mov reg_x, 10` o `mov dword ptr [x], reg_x` |
| **Suma** | `(+, a, b, t1)` | `mov reg_t1, reg_a`<br>`add reg_t1, reg_b` |
| **Resta** | `(-, a, b, t1)` | `mov reg_t1, reg_a`<br>`sub reg_t1, reg_b` |
| **Multiplicación** | `(*, a, b, t1)` | `mov reg_t1, reg_a`<br>`imul reg_t1, reg_b` |
| **División** | `(/, a, b, t1)` | `mov eax, reg_a`<br>`cdq`<br>`idiv reg_b`<br>`mov reg_t1, eax` |
| **Módulo** | `(%, a, b, t1)` | `mov eax, reg_a`<br>`cdq`<br>`idiv reg_b`<br>`mov reg_t1, edx` |
| **Negación** | `(neg, a, , t1)` | `mov reg_t1, reg_a`<br>`neg reg_t1` |
| **Comparación** | `(<=, a, b, t1)` | `cmp reg_a, reg_b`<br>`setle reg8`<br>`movzx reg_t1, reg8` |
| **Salto Condicional** | `(IF_FALSE, t1, , L1)` | `cmp reg_t1, 0`<br>`je L1` |
| **Salto Incondicional** | `(GOTO, , , L2)` | `jmp L2` |
| **Etiqueta** | `(LABEL, , , L1)` | `L1:` |
| **Impresión** | `(print, x, , )` | `mov eax, reg_x`<br>`call PRINT_INT` |
| **Lectura** | `(read, , , x)` | `call READ_INT`<br>`mov reg_x, eax` |
| **Retorno** | `(return, x, , )` | `mov eax, reg_x`<br>`mov esp, ebp`<br>`pop ebp`<br>`mov ax, 4C00h`<br>`int 21h` |

---

### 6. Módulo Simulador / Emulador de Ejecución

Para garantizar la verificación funcional autónoma tanto dentro del entorno gráfico como en ensambladores externos:
- Se desarrolló un emulador de arquitectura x86 (`SimulatorASM`) que mantiene el banco de registros (`EAX`, `EBX`, `ECX`, `EDX`, `ESI`, `EDI`, `EBP`, `ESP`), banderas aritméticas (`ZF`, `SF`, `OF`), pila de ejecución y servicios de interrupción DOS (`INT 21h` servicios 01h, 02h, 09h y 4Ch).
- Adicionalmente, el código objeto ensamblador generado es **100% compatible y validado directamente con Borland Turbo Assembler (TASM 4.1 / 5.0 / GUI Turbo Assembler)** y TLINK, ensamblando y enlazando de forma limpia con 0 errores y 0 advertencias.

### 7. Evidencias de Ejecución y Casos de Prueba

Se incluyen casos de prueba automatizados y ejemplos completamente funcionales en `ejemplos/`:
1. `aritmetica.cpp` $\rightarrow$ Traducción de expresiones con operadores aritméticos (`+`, `*`) y precedencia.
2. `if_else.cpp` $\rightarrow$ Control de flujo bifurcado mediante saltos condicionales y comparaciones.
3. `ciclo_while.cpp` $\rightarrow$ Ciclo con acumulador y condición relacional repetitiva.
4. `programa_completo_u4.cpp` $\rightarrow$ Integración completa con aritmética, ciclo while y condición if.

Para cada caso se proveen:
- Código fuente C++ (`.cpp`).
- Código intermedio optimizado (`.ir`).
- Archivo objeto generado (`.asm`).
- Tabla formal de asignación de registros (`_tabla_registros.txt`).
- Evidencia formal de ejecución (`_evidencia_ejecucion.txt`).

---

### 8. Suite de Pruebas Automatizadas

La suite integral de pruebas se ejecuta mediante:
```bash
python -m unittest discover -s tests -p "test_*.py"
```
**Resultado:**
```
Ran 56 tests in 0.039s
OK
```
Todas las 56 pruebas unitarias e integradas pasan con un 100% de éxito, cubriendo desde el análisis léxico hasta la ejecución del código objeto.

