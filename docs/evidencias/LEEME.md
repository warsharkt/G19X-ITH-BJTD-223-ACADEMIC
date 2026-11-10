# Evidencias

Pruebas con el sistema y el modelo de verdad, no simulados. Las pruebas automáticas (`pytest`) usan un modelo falso, así que no miden cómo redacta el modelo ni cuánto tarda, y no instalan el sistema como lo haría alguien nuevo. Para eso sirve esta carpeta. Cada prueba dice con qué commit se hizo.

| Fecha | Prueba | Commit |
|---|---|---|
| 10 de noviembre de 2026 | [Instalación desde cero y recorrido sugerido](instalacion-2026-11-10-8c59caf.md) | `8c59caf` |
| 4 de noviembre de 2026 | [Qwen3 8B con los 12 casos de la evaluación](#4-de-noviembre-de-2026-qwen3-8b-en-ollama) | `29bcdd0` |

## 4 de noviembre de 2026: Qwen3 8B en Ollama

| Dato | Valor |
|---|---|
| Commit | `29bcdd0` (4 de noviembre de 2026): el código con el que se corrió; esta evidencia se subió en ese mismo commit |
| Modelo | `qwen3:8b` (Q4_K_M) en Ollama, en CPU, en el equipo de desarrollo (Windows 11) |
| Prompt | v6, con los guardarrailes de la revisión de noviembre de 2026 (causas con "porque" o "por eso", "mejoró" contra lo que calculó el sistema, y años) |
| Datos | Nordika recién sembrada (`scripts/seed.py`, semilla fija), en una base aparte (`rrhh_evaluacion`) |
| Casos | La muestra curada de 12: crisis, solo amarillos, solo "por vigilar", un área chica y tres meses estables |
| Intentos | `LLM_INTENTOS=3` por ronda |

```powershell
cd backend
$env:POSTGRES_DB = "rrhh_evaluacion"   # base aparte, sembrada con scripts.seed
python -m scripts.evaluar_narrativa --salida ..\docs\evidencias\qwen3-8b-2026-11-04.csv --narrativas ..\docs\evidencias\qwen3-8b-2026-11-04-textos.jsonl
```

### Resultado

| Resultado | Casos |
|---|---|
| Correcto al primer intento | **11 / 12** (92 %) |
| Correcto tras corregir | 1 / 12 (Almacén 2026-06) |
| Sin narrativa válida | **0 / 12** |
| Tiempo total | 39.5 min (promedio de 198 s por caso; entre 64 y 387 s) |

| Área | Mes | Rojo | Amarillo | Por vigilar | Resultado | Segundos |
|---|---|---:|---:|---:|---|---:|
| Corporativo | 2026-08 | 0 | 0 | 5 | A la primera | 386.8 |
| Corporativo | 2026-03 | 1 | 2 | 4 | A la primera | 285.7 |
| Operaciones | 2026-04 | 2 | 4 | 1 | A la primera | 256.3 |
| Operaciones | 2026-02 | 1 | 0 | 3 | A la primera | 177.6 |
| Operaciones | 2026-07 | 0 | 1 | 3 | A la primera | 149.8 |
| Ventas | 2026-06 | 0 | 3 | 3 | A la primera (ver abajo) | 204.5 |
| Transporte | 2026-05 | 0 | 3 | 0 | A la primera | 144.4 |
| Finanzas | 2026-01 | 0 | 2 | 1 | A la primera | 139.6 |
| Almacén | 2026-06 | 0 | 0 | 3 | Tras 1 corrección | 288.2 |
| Jurídico | 2026-08 | 0 | 0 | 0 | A la primera (mes estable) | 63.5 |
| Ventas | 2024-10 | 0 | 0 | 0 | A la primera (mes estable) | 146.1 |
| Finanzas | 2025-04 | 0 | 0 | 0 | A la primera (mes estable) | 129.6 |

**Lo que se rechazó.** Solo una respuesta en toda la corrida. En Almacén 2026-06, el primer resumen no traía ninguna cifra ("resumen: no incluye ninguna cifra"); en el segundo intento ya las traía. Ninguna respuesta disparó las reglas nuevas (causas con "porque" o "por eso", "mejoró" contra lo calculado, años que no son del reporte). Esas reglas están probadas con casos hechos a mano en `tests/test_narrativa.py`.

**La alerta de la heurística.** El script marca los hallazgos que agrupan hechos con direcciones distintas y usan un solo verbo. Marcó Ventas 2026-06: *"El cumplimiento de metas bajó a 79.2 % (empeoró), la productividad también disminuyó a 70.1 % (empeoró), y la tasa de finalización de cursos cayó a 83.1 % (empeoró)."* Revisado a mano contra los hechos, el texto es correcto: los tres empeoraron frente al mes anterior (-4.5, -1.4 y -3.9 pts). Solo la productividad mejoró frente al año anterior (+1.3 pts), y el texto no habla de esa comparación. Es un falso positivo de la heurística, no un error del modelo.

**Lo que no mide.** Los guardarrailes comprueban cifras, citas, causas, direcciones y cobertura, pero no si un texto es útil. Por ejemplo, en Corporativo 2026-08 los hallazgos repiten la acción sugerida ("Se recomienda reforzar...") además de describir el dato. Es correcto, pero redundante con las recomendaciones. Por eso cada reporte lo firma una persona.

**Comparación con la evaluación anterior** (2 de octubre de 2026, prompt v5, mismos 12 casos): 8 de 12 a la primera, 1 sin narrativa válida y 400 s de promedio. Las correcciones de octubre (rango de hallazgos según los hechos, valor exacto en el error y muestra mínima) se notan: ahora salen 11 de 12 a la primera, ninguno falla y el promedio baja a 198 s. Ojo: el tiempo depende de qué tan cargado esté el equipo. Durante los primeros casos de esta corrida también corrían las pruebas y una compilación de Docker.

**Lo que cambió después.** Desde `157254d` (5 de noviembre) el prompt es v7: ya no le da al modelo el nombre del área, solo "un área de la empresa". Los guardarrailes no cambiaron hasta `8c59caf`; después se agregaron "atribuible a" y las contracciones "al" y "del" ("debido al", "a raíz del"; regla 16 de `guardrails.py`). Esta corrida no se repitió con v7, pero los 12 textos aceptados seguirían pasando con la regla nueva, porque ninguno usa esas formas. El reporte del [recorrido del 10 de noviembre](instalacion-2026-11-10-8c59caf.md) sí se generó con v7.

### Archivos

| Archivo | Qué tiene |
|---|---|
| `qwen3-8b-2026-11-04.csv` | Una fila por caso: conteo de estados, resultado, intentos, motivo de fallo, lo rechazado y los segundos |
| `qwen3-8b-2026-11-04-textos.jsonl` | Una línea por caso con el texto aceptado (resumen, hallazgos y recomendaciones) y las respuestas rechazadas con sus motivos |
| `qwen3-8b-2026-11-04-consola.txt` | La salida del script tal como se vio en la terminal |
