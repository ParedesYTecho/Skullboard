# Guía de Onboarding para Nuevas IAs & Replicación Desde Cero

Esta guía está diseñada para dos propósitos:
1. **Para cualquier IA nueva que entre a este repositorio**: Guía de inmersión rápida para alinearse al 100% en menos de 30 segundos sin gastar tokens.
2. **Para humanos o agentes que quieran replicar este sistema desde cero** en un nuevo proyecto.

---

# PARTE 1: Onboarding Rápido (Si eres una IA entrando a este proyecto)

Si acabas de iniciar una sesión en este repositorio (como Antigravity, Codex, Claude Code, Cursor u OpenCode), sigue esta secuencia estricta:

### Paso 0: Adopta el Modo Caveman Incondicionalmente
- **Estilo**: Ultra-conciso, directo, técnico, sin saludos, sin despedidas, sin frases de relleno (*"Sure, I will help you with that..."*).
- **Excepción**: Solo si el usuario escribe explícitamente "normal mode".

### Paso 1: Ejecuta Change Awareness (Detecta qué hizo otra IA)
Antes de proponer o tocar una sola línea de código, ejecuta:
```bash
git status
git diff --stat
```
Si se detectan cambios recientes no comiteados, léelos para entender el estado exacto del código antes de asumir que el proyecto está en el estado de tu última sesión.

### Paso 2: Lectura de Directivas y Memoria (En este orden exacto)
No leas archivos de código enteros. Lee únicamente estos archivos clave de directivas:
1. [AGENTS.md](AGENTS.md) — Contrato universal del repositorio.
2. [.agent/memory/personal/PREFERENCES.md](.agent/memory/personal/PREFERENCES.md) — Convenciones del usuario y estilo.
3. [.agent/protocols/permissions.md](.agent/protocols/permissions.md) — Reglas duras de ejecución y acciones bloqueadas.
4. [SecondBrain/wiki/index.md](SecondBrain/wiki/index.md) — Mapa de temas, arquitectura y ADRs.

### Paso 3: Pregunta a Graphify Antes de Leer Archivos Masivos
**NUNCA hagas grep global ni leas archivos de cientos de líneas a ciegas.**
- Para entender flujos o arquitectura:
  ```bash
  python -m graphify query "<concepto o pregunta>"
  ```
- Para ver dependencias entre símbolos:
  ```bash
  python -m graphify path "ClaseA" "ClaseB"
  python -m graphify explain "NombreDeFuncion"
  ```
- Solo usa `view_file` sobre los rangos de líneas exactos señalados por Graphify.

### Paso 4: Recall Proactivo Antes de Tareas Delicadas
Antes de tocar bases de datos, despliegues, migraciones, timestamps o refactors, consulta lecciones previas:
```bash
python .agent/tools/recall.py "<descripción corta de lo que vas a hacer>"
```
Si devuelve lecciones (`Consulted lessons for intent:`), acátalas estrictamente para no repetir errores pasados.

### Paso 5: Checklist de Cierre Obligatorio (Antes de dar por terminada la tarea)
1. **Compilar y Testear**:
   ```bash
   python -m py_compile main.py webserver.py
   python scripts/safeguards_test.py
   ```
2. **Cerrar Ciclo de Memoria**:
   - Si tomaste una decisión de diseño: crea `SecondBrain/wiki/decisions/<id>-<tema>.md`, enlázalo en `SecondBrain/wiki/index.md` y refléjalo en `docs/DECISIONS.md`.
   - Si descubriste un bug o regla operativa: ejecuta `python .agent/tools/learn.py "<regla>" --rationale "<motivo>"` y regístralo en `SecondBrain/wiki/lessons/`.
3. **Sincronizar Grafo**:
   ```bash
   python -m graphify extract . --code-only
   ```
4. **Commit + Push Automático**: Haz `git commit` y `git push origin main` salvo orden expresa de pausa o mantenimiento.

---

# PARTE 2: Cómo Replicar Este Sistema Desde Cero en un Proyecto Nuevo

Sigue este procedimiento paso a paso para transformar cualquier repositorio en un entorno multi-agente hiper-eficiente.

### 1. Requisitos Previos en el Sistema
- Python 3.11 o superior.
- Git instalado.
- Graphify instalado:
  ```bash
  pip install graphifyy
  ```

---

### 2. Paso 1: Configurar las Directivas Raíz (AGENTS.md)
Crea en la raíz del nuevo proyecto el archivo `AGENTS.md` con las 4 directivas obligatorias:
1. **Caveman Always-On**:
   ```markdown
   ## 1. Caveman Mode (Always-On)
   Always respond in Caveman style: terse, direct, technical, no fluff, no pleasantries, no filler. Keep this style unless the user explicitly says 'normal mode'.
   ```
2. **Change Awareness Rule**:
   ```markdown
   ## 2. Change Awareness Rule
   At the beginning of any non-trivial task, or when resuming work after a possible change from another tool/editor, you MUST:
   1. Run git status and git diff --stat to detect recent changes.
   2. Check if the Graphify graph is stale.
   3. Prefer reading current state of files + Graphify over assuming previous knowledge is valid.
   4. Record major architectural changes in SecondBrain/wiki/decisions/ and mirror in docs/DECISIONS.md.
   ```
3. **Graph-First Navigation**:
   ```markdown
   ## 3. Graph-First Code Exploration (Prefer Graphify)
   Prefer querying Graphify (graphify query, graphify path, graphify explain) before broad grep, glob, or reading many files.
   ```
4. **Checklist de Cierre Obligatorio**:
   ```markdown
   ## 4. Checklist de Cierre y Memoria (Obligatorio)
   1. Verificación y pruebas locales.
   2. Cierre de memoria: redactar ADR en SecondBrain/wiki/decisions/, graduar lección con python .agent/tools/learn.py.
   3. Sincronización Graphify: python -m graphify update .
   4. Commit + Push autónomo.
   ```
*(Opcional: Crea enlaces o copias en `GEMINI.md`, `CLAUDE.md` y `.cursor/rules/` para cubrir todas las herramientas).*

---

### 3. Paso 2: Desplegar el Runtime de Memoria (.agent/)
Copia o clona la estructura portátil de `agentic-stack`:
- Estructura mínima de `.agent/`:
  ```text
  .agent/
  ├── AGENTS.md
  ├── memory/
  │   ├── personal/PREFERENCES.md
  │   ├── semantic/lessons.jsonl
  │   ├── semantic/LESSONS.md
  │   ├── episodic/AGENT_LEARNINGS.jsonl
  │   └── candidates/
  └── tools/
      ├── recall.py
      ├── learn.py
      ├── graduate.py
      └── show.py
  ```

> [!IMPORTANT]
> **Parche Obligatorio para Windows**:
> En `.agent/tools/recall.py`, `graduate.py`, `learn.py` y `show.py`, asegúrate de incluir inmediatamente después de `import sys`:
> ```python
> if hasattr(sys.stdout, "reconfigure"):
>     sys.stdout.reconfigure(encoding="utf-8", errors="replace")
> if hasattr(sys.stderr, "reconfigure"):
>     sys.stderr.reconfigure(encoding="utf-8", errors="replace")
> ```
> Sin este parche, cualquier salida que contenga flechas `→` o caracteres ANSI crasheará con `UnicodeEncodeError` en consolas Windows.

---

### 4. Paso 3: Estructurar el SecondBrain Local (SecondBrain/)
Crea la estructura de carpetas en la raíz del proyecto:
```bash
mkdir -p SecondBrain/config SecondBrain/catalog SecondBrain/wiki/projects SecondBrain/wiki/decisions SecondBrain/wiki/lessons SecondBrain/wiki/workflows SecondBrain/operations
```
- Archivos indispensables:
  - `SecondBrain/README.md`: Propósito de la wiki.
  - `SecondBrain/AGENTS.md`: Reglas de consulta selectiva para agentes.
  - `SecondBrain/wiki/index.md`: Índice de ADRs, lecciones y enlaces a proyectos.
  - `SecondBrain/catalog/exclusions.jsonl`: Exclusiones de secretos (*.env*, .git/*).

---

### 5. Paso 4: Inicializar Graphify
En la raíz del proyecto:
```bash
# 1. Extraer el grafo inicial basado en AST
python -m graphify extract . --code-only

# 2. Generar clusters semánticos
python -m graphify cluster-only .

# 3. Instalar hooks automáticos de git
graphify hook install
```
A partir de este momento, cada commit actualizará el grafo en segundo plano.

---

### 6. Paso 5: Lista de Skills Recomendadas a Instalar
Para dotar al agente de capacidades avanzadas sin saturar el contexto, sincroniza en `.agents/skills/`:

| Skill | Función Principal |
| :--- | :--- |
| **caveman** | Respuestas ultra-cortas y directas (-60% tokens). |
| **ponytail** | Filosofía YAGNI extrema, soluciones más simples y limpias. |
| **graphify** | Navegación de código asistida por AST y GraphRAG. |
| **code-review** | Revisiones duales (Spec vs Standards) antes de fusionar. |
| **memory-manager** | Gestión de episodios, consolidación y archivo de memorias. |
| **debug-investigator** | Metodología de depuración quirúrgica sin suposiciones. |
| **deploy-checklist** | Verificaciones previas a puesta en producción. |
| **tldraw** *(opcional)* | Diagramado visual en pizarra interactiva local. |
| **supabase / supabase-postgres-best-practices** *(si aplica)* | Índices optimizados, RPCs y seguridad RLS. |

---

### 7. Paso 6: Prueba de Certificación de 3 Fases
Para certificar que el nuevo proyecto está conectado al 100%, ejecuta:
1. **Prueba de Recall**:
   ```bash
   python .agent/tools/recall.py "test"
   ```
   *Debe responder sin errores de codificación indicando el número de lecciones.*
2. **Prueba de Aprendizaje**:
   ```bash
   python .agent/tools/learn.py "Regla de prueba de inicializacion" --rationale "Verificacion de conexion de memoria"
   ```
   *Debe graduar la lección y re-renderizar LESSONS.md.*
3. **Prueba de Dashboard**:
   ```bash
   python .agent/tools/show.py
   ```
   *Debe mostrar la caja ANSI en terminal con memoria, lecciones y skills.*