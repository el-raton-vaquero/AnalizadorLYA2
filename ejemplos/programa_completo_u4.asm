; ============================================================================
; ARCHIVO OBJETO GENERADO (.ASM) - COMPATIBLE CON TURBO ASSEMBLER (TASM)
; Arquitectura: x86 (IA-32 / 80386) - Modo DOS Real / Protegido
; Compilador C++: Generación de Código Objeto con Asignación de Registros
; Algoritmo: Coloración Mínima de Grafos de Interferencia (chi = 4)
; Fecha de Generación: 2026-11-09 09:30:47
; Registros x86 Asignados: 4 / 6
; ============================================================================

.MODEL SMALL
.386
.STACK 1000h

.DATA
    ; Búferes y constantes para E/S del sistema
    buffer_num   DB 16 DUP('$')
    str_cero     DB '0', '$'
    newline_str  DB 13, 10, '$'
    ; Variables del programa almacenadas en memoria principal
    a            DD 0
    b            DD 0
    c            DD 0
    i            DD 0
    total        DD 0

.CODE

; --- Entrada principal del programa ---
START:
main:
    mov ax, @data
    mov ds, ax
    mov es, ax

    push bp
    mov bp, sp
    sub sp, 16               ; Espacio reservado para marco de pila y derrames

    mov eax, 5     ; #1 (=, 5, , a)
    mov dword ptr [a], eax
    mov eax, 10     ; #2 (=, 10, , b)
    mov dword ptr [b], eax
    mov eax, 15     ; #3 (=, 15, , c)
    mov dword ptr [c], eax
    mov ebx, 0     ; #4 (=, 0, , total)
    mov dword ptr [total], ebx
    mov ecx, 1     ; #5 (=, 1, , i)
    mov dword ptr [i], ecx
L1:
    cmp ecx, 3        ; #7 (<=, i, 3, t2)
    setle dl
    movzx edx, dl
    cmp edx, 0
    je L2                    ; #8 (IF_FALSE, t2, , L2)
    add ebx, eax    ; #9 (+, total, c, t3)
    ; mov ebx, ebx (mismo registro asignado por coloración) ; #10 (=, t3, , total)
    mov dword ptr [total], ebx
    add ecx, 1    ; #11 (+, i, 1, t4)
    ; mov ecx, ecx (mismo registro asignado por coloración) ; #12 (=, t4, , i)
    mov dword ptr [i], ecx
    jmp L1                   ; #13 (GOTO, , , L1)
L2:
    cmp ebx, 20        ; #15 (>, total, 20, t5)
    setg al
    movzx eax, al
    cmp eax, 0
    je L3                    ; #16 (IF_FALSE, t5, , L3)
    push eax
    mov eax, ebx
    call PRINT_INT             ; #17 (print, total, , )
    pop eax
L3:

; --- Epílogo de terminación exitosa ---
    mov sp, bp
    pop bp
    mov ax, 4C00h               ; Retorno a DOS (EXIT_SUCCESS)
    int 21h

; ============================================================================
; RUTINAS AUXILIARES DE ENTRADA / SALIDA (DOS INT 21h)
; ============================================================================

; --- Rutina auxiliar para imprimir entero en EAX con salto de línea ---
PRINT_INT PROC NEAR
    push eax
    push ebx
    push ecx
    push edx
    push si
    push di

    cmp eax, 0
    jne PI_NOT_ZERO
    mov dx, offset str_cero
    mov ah, 09h
    int 21h
    mov dx, offset newline_str
    mov ah, 09h
    int 21h
    jmp PI_DONE

PI_NOT_ZERO:
    mov di, offset buffer_num + 14
    mov byte ptr [di + 1], '$'
    mov ecx, 0

    cmp eax, 0
    jge PI_DIV_LOOP
    neg eax
    mov ecx, 1

PI_DIV_LOOP:
    mov edx, 0
    mov ebx, 10
    div ebx
    add dl, '0'
    mov [di], dl
    dec di
    cmp eax, 0
    jne PI_DIV_LOOP

    cmp ecx, 1
    jne PI_SHOW
    mov byte ptr [di], '-'
    dec di

PI_SHOW:
    inc di
    mov dx, di
    mov ah, 09h
    int 21h

    mov dx, offset newline_str
    mov ah, 09h
    int 21h

PI_DONE:
    pop di
    pop si
    pop edx
    pop ecx
    pop ebx
    pop eax
    ret
PRINT_INT ENDP

; --- Rutina auxiliar para imprimir cadena terminada en '$' (offset en DX) ---
PRINT_STR PROC NEAR
    push ax
    mov ah, 09h
    int 21h
    pop ax
    ret
PRINT_STR ENDP

; --- Rutina auxiliar para leer un entero desde teclado a EAX ---
READ_INT PROC NEAR
    push ebx
    push ecx
    push edx
    mov ebx, 0
    mov ecx, 0
RI_READ:
    mov ah, 01h
    int 21h
    cmp al, 13
    je RI_END
    cmp al, 10
    je RI_END
    cmp al, ' '
    je RI_END
    cmp al, '-'
    jne RI_DIGIT
    mov ecx, 1
    jmp RI_READ
RI_DIGIT:
    sub al, '0'
    movzx edx, al
    imul ebx, 10
    add ebx, edx
    jmp RI_READ
RI_END:
    cmp ecx, 1
    jne RI_DONE
    neg ebx
RI_DONE:
    mov eax, ebx
    pop edx
    pop ecx
    pop ebx
    ret
READ_INT ENDP

END START
