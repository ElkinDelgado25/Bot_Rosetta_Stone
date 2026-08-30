# CLAUDE.md — Guía de Desarrollo

Instrucciones y contexto para trabajar en este repositorio. Léeme primero.

---

## El Proyecto

**Rosetta Stone Bot** — automatiza la completación de lecciones sin resolverlas. Obtiene el árbol del curso desde GraphQL, fabrica puntajes y duraciones, y los envía al endpoint de tracking.

- **Soporta:** Foundations y Fluency Builder (cada uno con su propio backend y modelo).
- **No resuelve:** las lecciones reales; solo marca rutas como completadas.
- **Entrada:** credenciales Rosetta Stone (email + contraseña).
- **Salida:** lecciones marcadas completadas, reportes, historial de progreso.

### Dos formas de usar

| Modo | Cuándo | Cuentas |
|------|--------|---------|
| **CLI** | Terminal, una pasada | 1 (del `.env`) |
| **Web** | Navegador, múltiples usuarios, paralelo | N (con UI en Docker o local) |

---

## Stack

- **Python ≥ 3.14** — único lenguaje del proyecto
- **uv** — gestor de dependencias (no pip, no venv manual)
- **FastAPI** — servidor web (opcional, solo si usas interfaz web)
- **Playwright** — automatización del navegador (Chromium/Chrome/Edge)
- **Docker** — aislamiento de corridas (opcional, recomendado para la web)
- **pytest** — tests (119 tests)

---

## Puesta en Marcha

### 1. Clonar y sincronizar

```bash
git clone https://github.com/ElkinDelgado25/Bot_Rosetta_Stone.git
cd Bot_Rosetta_Stone
uv sync --extra web
```

`--extra web` añade FastAPI. Para solo CLI: `uv sync` a secas.

### 2. Si no tienes Chrome/Edge (Linux, Docker)

```bash
uv run playwright install chromium
```

---

## Comandos Principales

### CLI — una cuenta, una pasada

```bash
uv run python -m rosseta_stone_script_a
```

Lee del `.env`. Primera ejecución lo crea interactivamente.

### Tests — 119 tests, sin navegador ni contenedores

```bash
uv run pytest -q
```

### Web local — multi-usuario, sin Docker

```bash
uv run rosseta-web
```

Abre http://127.0.0.1:8000. Corridas en cola (comparten navegador).

### Web en Docker — multi-usuario, paralelo (recomendado)

```bash
docker compose up -d --build --force-recreate
```

Abre http://127.0.0.1:8000. Cada corrida en su propio contenedor.

> **Siempre usa `--force-recreate`.** `--build` reconstruye la imagen pero deja el contenedor viejo, así que verías el código anterior sin saber por qué.

### Compilar `.exe`

```bash
uv run --group dev python build.py
```

Sale en `dist/rosseta-script-a.exe` (CLI puro, sin web).

---

## Estructura del Proyecto

```
src/rosseta_stone_script_a/
├── domain/               Entidades de negocio, valores, errores
├── application/
│   ├── orchestrators/    Coordinadores de flujo (Foundations, Fluency, Exam)
│   ├── use_cases/        Casos de uso específicos
│   └── services/         Lógica reutilizable (cálculos, filtros, reportes)
├── infrastructure/
│   ├── adapters/         Playwright, APIs, parsers
│   └── state/            Persistencia de progreso (JSON)
└── presentation/
    ├── cli.py            Entrada CLI
    ├── worker.py         Un contenedor efímero por corrida
    └── web/              FastAPI + HTML (sin build, sin CDN)

docs/
├── ARCHITECTURE.md       Modularización y capas
└── FLUENCY_BUILDER.md    Detalles del producto Fluency

tests/                    119 tests, por capas
```

---

## Cómo Funciona (Ciclo)

### Fase 1: Captura de credenciales (navegador)

1. Login en `login.rosettastone.com`
2. Selección institucional (si aparece)
3. Dashboard → detecta Foundations o Fluency Builder
4. **Captura pasiva de headers:** JWT, session token, user_id, school_id, lang_code
5. El navegador queda inerte (no navega más)

### Fase 2: Lectura del curso (GraphQL)

```
POST https://graph.rosettastone.com/graphql
```

Query `GetCourseMenu` → árbol de unidades, lecciones, paths con metadatos.

### Fase 3: Filtrado y fabricación

- `ContentFilter` descarta por config (unidades, lecciones, tipos)
- `StateStore` descarta lo ya enviado en corridas previas
- `PathCalculator` genera duraciones (realistas, con variación)

### Fase 4: Envío (REST + XML)

```
POST https://tracking.rosettastone.com/ee/ce/{school}/users/{user}/path_scores
     ?course=...&unit_index=...&lesson_index=...&path_type=...&_method=put
```

Auth por `x-rosettastone-session-token`. Un POST por path completado.

---

## Lo que tenemos dentro de la repo

### ✅ Entra en este repo y mas cosas que podemos hacer contribuyendo a medida que pasa el tiempo

- Empaquetado (entorno, `.exe`, contenedores)
- Interfaz web y CLI
- Tests, logging, códigos de salida
- Refactors, documentación
- **Extender el motor** a nuevos productos (Fluency, Exam ya está)
- Mejoras de confiabilidad y rendimiento
- **Evasión de detección:** análisis de logs del servidor, patrones de fingerprinting, ofuscación de tráfico
- Saber como se estructura los servicios para mejorar el programa
- agregar mas modulos de aprendizaje y soporte a nuevos productos
---

## Variables de Entorno

Van en `.env` o en `environment:` del compose.

| Variable | Defecto | Para qué |
|----------|---------|----------|
| `ROSETTA_EMAIL` | — | Credencial CLI |
| `ROSETTA_PASSWORD` | — | Credencial CLI |
| `ROSETTA_HOME` | cwd | Dónde viven `.env`, `profiles.json`, `state/`, `logs/` |
| `ROSETTA_WEB_HOST` | `127.0.0.1` | Interfaz de escucha (web) |
| `ROSETTA_WEB_PORT` | `8000` | Puerto (web) |
| `ROSETTA_WEB_TOKEN` | vacío | Token compartido; vacío = abierto |
| `ROSETTA_RUN_BACKEND` | auto | Fuerza `docker` o `in-process` |
| `BROWSER_HEADLESS` | `false` | `true` para no ver la ventana del navegador |
| `LOG_LEVEL` | `INFO` | `DEBUG` para diagnosticar |
| `FLUENCY_MAX_LESSONS` | 1 (CLI) / all (web) | Lecciones por corrida |
| `FLUENCY_DRY_RUN` | `false` | `true` para construir sin enviar |
| `FLUENCY_TOTAL_COURSE_HOURS` | `70` | Horas de estudio fabricadas, repartidas entre lecciones/steps de la corrida |

---

## Detalles No Obvios

### Los POSTs no dependen de las pantallas

La navegación **solo** captura tokens. No hay un POST "por lo que se hizo en pantalla". El árbol GraphQL es la fuente de verdad: qué se envía sale de ahí, no de nada visible.

Por eso:
- El bot marca cientos de actividades sin abrir ninguna
- Un cambio de DOM no afecta a los envíos (solo rompe la cosecha de tokens)

### `unit_index % 4`

GraphQL numera unidades globalmente (0-19 entre 5 niveles), pero tracking espera índice relativo al curso (0-3). Sin módulo, solo nivel 1 registra; L2-L5 escriben en coordenadas inexistentes.

### Dos APIs de épocas distintas

- **GraphQL:** capa nueva (`graph.rosettastone.com`)
- **Tracking:** API del cliente Totale (`tracking.rosettastone.com`, usa `x-rosettastone-session-token` y `x-rosettastone-app-version`)

### Fluency: 1 lección por defecto

`FLUENCY_MAX_LESSONS=1` en la CLI (conservador, para pruebas). Desde la UI se traduce a `"all"` (el perfil puede limitarlo). El default no se toca: CLI sigue siendo cautelosa.

### Estado de Fluency: por usuario, no global

Las claves de actividad son `fluency|curso|secuencia|actividad` **sin la cuenta**. El archivo es `fluency_<user_id>.json` porque el `user_id` no se conoce hasta que la corrida lo captura.

### Progreso: suma de dos esquemas

`progress_for()` lee `<user_id>.json` (Foundations) + `fluency_<user_id>.json` (Fluency). Mirar solo uno hacía reportar "0 completadas" falsamente.

### Sesión incompleta = error, no silencio

Si no se capturan los 5 valores (JWT, user_id, school_id, lang_code, session_token), el orquestador lanza `SessionCaptureIncomplete` → código de salida 3. **No se envía nada.** Antes salía con código 0, engañando al scheduler.

### Códigos de salida

- `0` — ok
- `1` — error
- `2` — config ilegible (solo worker)
- `3` — sesión incompleta
- `130` — interrumpido (Ctrl+C)

El `3` está separado a propósito: "falló el login" se distingue de errores aleatorios.

---

## Trampas del Entorno (Verificadas)

### El venv usa Python gestionado por uv

Si `%APPDATA%\uv\python\cpython-3.14-...` no existe, cualquier comando falla. Solución:

```bash
uv python install 3.14
uv sync
```

### No hay `pip` en el venv

Intencional. VS Code lo intenta igual; `.vscode/settings.json` tiene `python-envs.alwaysUv`.

### No existe `requirements.txt`

Las dependencias están en `pyproject.toml` y fijadas en `uv.lock`. Requiere Python ≥ 3.14.

### Namespace packages sin `__init__.py`

`src/rosseta_stone_script_a/` y otros son namespace packages. `pyproject.toml` declara `packages.find` explícito.

### `ROSETTA_HOME` manda sobre el cwd

`get_base_dir()` y `detect_project_root()` la respetan. En el contenedor es `/data`. Sin ella caería al directorio de trabajo, que en la imagen no es escribible.

### `BROWSER_CHANNEL` vacío = "sin canal"

El provider prueba Chrome → Edge → Chromium bundled. La imagen lo deja vacío para ir directo a Chromium (más rápido en Linux).

### Las imágenes Playwright no sirven aquí

`mcr.microsoft.com/playwright/python` trae Python 3.12. Este proyecto exige ≥ 3.14. El Dockerfile parte de `python:3.14-slim`.

### JSON del worker: `utf-8-sig`

Un JSON tocado a mano en Windows lleva BOM. `json.load` revienta. Se lee con `encoding="utf-8-sig"`.

---

## Seguridad

**Las contraseñas se guardan en texto plano** (`.env` y `profiles.json`). El archivo se escribe con permisos 0600 (solo lectura para el propietario). Eso es toda la protección.

- **Tokens de sesión:** guardados por usuario en `state/sessions/<id>.json` (0600), nunca devueltos enteros por API (enmascarados en la UI).
- **No expongas la web sin token.** El compose publica solo en `127.0.0.1` a propósito. Quien controle esa web controla `docker.sock` = acceso root a la máquina.

---

## Si algo falla

| Síntoma | Causa | Solución |
|---------|-------|----------|
| Cambias código y la web no cambia | Faltó `--force-recreate` | `docker compose up -d --build --force-recreate` |
| `did not find executable at ...` | Python gestionado por uv desapareció | `uv python install 3.14` + `uv sync` |
| Código 3 al ejecutar | Sesión incompleta (login fallido) | Verifica en la UI: ¿dónde se corta? |
| "0 completadas" tras ejecutar | Sesión no se capturó | Mira el log en vivo: ¿envió algo? |
| Corrida detiene en una lección | `fluency_max_lessons` puesto | Saca el límite del perfil |
| Lección en ~95% | Tiene actividades de voz | Está documentado: no se puede completar por API |
| Chips vuelven a `idle` tras reiniciar | Último estado vive en memoria | Sí, el progreso persiste en disco |
| `Could not launch a browser` | No hay Chrome/Edge en el PATH | `uv run playwright install chromium` |
| La UI no responde (Docker reinició) | Imagen vieja | Reconstruye: `docker compose up -d --build --force-recreate` |

---

## Tests

```bash
uv run pytest -q
```

119 tests. Ninguno abre navegador ni lanza contenedores:
- `FakeBackend` inyectado en tests de web
- Tests de adapters mockean APIs
- Todo se ejecuta en ~5 segundos

Para debug:

```bash
uv run pytest -q -vv [path/test_file.py]  # verbose
uv run pytest -q -s [path/test_file.py]   # sin capturar print()
```

---

## Desarrollo y Contribuciones

### Antes de hacer un commit

1. **Tests pasan:** `uv run pytest -q`
2. **Código es válido:** `uv run python -m py_compile src/...`
3. **Commits claros:** título corto en inglés, descripción (si hay)

### Estructura que mantenemos

- Las capas no saben de capas superiores (`domain/` y `application/` nunca importan `presentation/`)
- Los tests **nunca** abren navegadores (`FakeBackend` lo evita)
- Los orquestadores orquestan; los servicios hacen
- Sin abstracciones prematuras; tres líneas iguales es ok

### Scope para PRs

**Bienvenidos:**
- Bugs, refactors, mejoras de testing
- Soporte a nuevos productos (Fluency, Exam)
- Optimizaciones de rendimiento y confiabilidad
- Documentación
- Evasión de detección, análisis anti-bot, ofuscación
- Resolver lecciones reales
- Integración con plataformas no autorizadas

---
### siguientes pasos

- realizar la implementacion de correccion de AddUsageOverhead, mas la implementacion de la clase de FluencyBuilderOrchestrator, y la implementacion de la clase de FluencyBuilderUseCase, para poder realizar el envio de las lecciones completadas al endpoint de tracking. de la parte de audio y poder completarla, 
-  Ajuste de las horas asi como se realizan en el foundaments con un total de maximo 70 horas en division de las lecciones que exista 
---

## Links Útiles

- **Rosetta Stone GraphQL:** https://graph.rosettastone.com/graphql
- **Tracking API:** https://tracking.rosettastone.com
- **Playwright docs:** https://playwright.dev/python/
- **FastAPI docs:** https://fastapi.tiangolo.com/
- **Docker Compose:** https://docs.docker.com/compose/

---

**Por Elkin Delgado** | MIT License
