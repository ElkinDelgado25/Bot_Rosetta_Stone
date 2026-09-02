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
- **pytest** — tests (359 tests)

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

### Tests — 359 tests, sin navegador ni contenedores

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

tests/                    359 tests, por capas
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
| `FLUENCY_SEND_USAGE_OVERHEAD` | `false` | `true` para enviar `AddUsageOverhead` (esquema ya capturado; falta confirmar que el servidor lo acepta) |
| `FLUENCY_SPEECH_BROWSER` | `1` | `0` apaga la ruta de voz por navegador |
| `FLUENCY_SPEECH_TRACE` | `0` | `1` graba una traza de Playwright por actividad de voz fallida |
| `FLUENCY_BROWSER_EXTRA_TYPES` | vacío | Tipos extra a completar por navegador, separados por coma |
| `STORIES_TARGET_HOURS` | `1` | Horas a acreditar por corrida de Stories |
| `STORIES_CHUNK_MIN_SEC` | `300` | Tramo mínimo por envío de uso |
| `STORIES_CHUNK_MAX_SEC` | `900` | Tramo máximo por envío de uso |
| `STORIES_REPORT_DELAY_SEC` | `0` | Espera entre envíos; `0` los manda seguidos |
| `STORIES_LANGUAGE` | `ENG` | Idioma que se declara a la API de Stories |

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

### Stories acredita horas por otra API distinta

Foundations y Fluency envían *contenido completado*; Stories envía **tiempo**.
Son dos POST a `lcp.rosettastone.com/api/v3/app_usage`: `report_usage` abre la
sesión de uso y `report_additional_usage` le suma segundos. Auth **por
cookies**, no por Bearer — por eso el adaptador emite desde el contexto de
peticiones del navegador y no recibe credenciales.

Dos detalles que no se ven en el código si no se cuentan:

- **Hay que entrar en una historia con el navegador.** No es decorado: ese paso
  deja la sesión válida del lado del servidor a la que se le suman los
  segundos. Sin él los POST no tienen a qué colgarse.
- **Se reporta en tramos, no de golpe.** El reproductor real no manda un
  resumen al final; va reportando según avanza. `StoriesUsagePlanner` corta el
  presupuesto en trozos de 5-15 min, y `started_ago` vale el primer trozo para
  que la sesión no nazca en el instante exacto de la primera llamada.

Si el propio reproductor ya abrió su sesión de uso, se reutiliza su
`session_identifier` (`StoriesSessionCapturer`) en vez de abrir una segunda en
paralelo para la misma historia.

En la portada, **"Continuar" aparece dos veces**: el texto de Dynamic
Immersion® y el botón. Un locator con dos coincidencias hace saltar el modo
estricto de Playwright, así que los empujones se pulsan con `click_first`, no
con `click`. `exists()` no avisa del choque porque ya mira solo la primera.

### El GUID del panel no es el `user_id` del tracking

El panel del aprendiz (`prism.rosettastone.com/reports/learner/dashboard/<guid>`)
pide un **GUID** y un Bearer del servicio de login. No sirve ninguno de los dos
valores que ya capturábamos: el `user_id` del tracking es numérico y el
`authorization` es el JWT de gaia. Los dos correctos viajan en el *cuerpo* de la
respuesta del login (`auth_data.access_token` / `auth_data.userId`), por eso
`LearnerAuthCapturer` escucha respuestas y no peticiones como los otros dos
capturadores. Es la única lectura que confirma que lo enviado quedó registrado:
el tracking responde 200 pase lo que pase.

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
| Lección en ~95% | Le quedan conversaciones (`DialogueExpression*`) | Son las únicas `ordering: tree`: no se acreditan por API, van por navegador. Ver `docs/FLUENCY_BUILDER.md` |
| "el paso N no llegó a seleccionar ninguna respuesta" | El modal de micrófono está encima (`z-index: 7000`) | No es un problema de clics: mira el medidor en el log. Ver `docs/FLUENCY_BUILDER.md` |
| Chips vuelven a `idle` tras reiniciar | Último estado vive en memoria | Sí, el progreso persiste en disco |
| `Could not launch a browser` | No hay Chrome/Edge en el PATH | `uv run playwright install chromium` |
| La UI no responde (Docker reinició) | Imagen vieja | Reconstruye: `docker compose up -d --build --force-recreate` |

---

## Tests

```bash
uv run pytest -q
```

359 tests. Ninguno abre navegador ni lanza contenedores:
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

- **Stories (horas de uso)** — implementado (`StoriesOrchestrator`,
  `StoriesApiPort` / `PlaywrightStoriesApiAdapter`, `StoriesUsagePlanner`,
  `StoriesPage`), disponible como modo `stories` en la CLI, el worker y la UI
  (botón "Reportar horas"). **Pendiente real:** confirmar contra una cuenta
  viva que los dos endpoints siguen aceptando los envíos y que las horas
  aparecen en el panel. Del navegador ya hay confirmación parcial: una cuenta
  Foundations llega a la portada de Stories; una Fluency no ve el listado.
- **Verificación de horas** — implementada (`LearnerDashboardPort` /
  `PlaywrightLearnerDashboardAdapter` + `LearnerAuthCapturer`): tras el login
  se leen las horas que la plataforma reconoce y se guardan en la sesión
  (`hours_total`, `hours_elearning`), visibles en la UI. De mejor esfuerzo:
  si no hay credenciales o el panel falla, la corrida sigue igual.
  **Confirmado en una cuenta real** (31-08-2026): la respuesta del login trae
  `auth_data`, el capturador lo pesca y el panel devolvió 77,313 h.
- ~~AddUsageOverhead~~ — **esquema capturado** (02-09-2026) del tráfico real
  que guardan las trazas de actividades de voz fallidas: la mutación toma
  `$messages` (no `$overheads`), no lleva `userId` y devuelve un escalar, y el
  mensaje es `{id, userAgent, learningContext, durationMs, endTimestamp}`. La
  versión inferida era inválida contra el esquema por los tres motivos a la
  vez. Sigue apagada por default (`FLUENCY_SEND_USAGE_OVERHEAD=0`).
  **Pendiente real:** encenderla una vez y confirmar que el servidor la acepta.

- **Conversaciones `DialogueExpression*`** — las 46 actividades
  `ordering: "tree"` del catálogo (27 `WithReco` + 19 `WithoutReco`) son las
  únicas que la API deja en `percentComplete=0` hagas lo que hagas: lo que el
  servidor no acredita fabricado es el árbol, no la voz. Las dos van ahora por
  navegador. `WithoutReco` estuvo apuntada como "hueco imposible" por una
  conclusión mal sacada — se enrutó a la ruta de voz sin adaptarla, esperó un
  micrófono que esos pasos (`inputType: select`) no tienen y se leyó el timeout
  como imposibilidad.

  **CONFIRMADO contra la cuenta viva** (02-09-2026, leyendo `logs/runs/`): las
  seis corridas de ese día suman **38 conversaciones verificadas con
  `percentComplete=1` y ninguna en 0** — 13 por la ruta de elegir
  (`WithoutReco`) y 10 por la de hablar (`WithReco`), más 15 que el log no
  permite atribuir. La nota que decía "el código está sin ejercitar desde el
  01-09 11:02" estaba equivocada: sí se ejercitó, y funciona. El servidor
  acredita las dos rutas.

  Lo que queda al 89-94% no es que la ruta falle: es que **las corridas se
  interrumpían** antes de acabar (navegador cerrado, esperas agotadas). Los dos
  arreglos del 02-09 —`BrowserGone` y el audio atascado— van justo a eso.

  Ojo con la cuenta: la del `.env` es **Foundations** y ya está al 100%, así que
  `CompleteFluencyOrchestrator` ni se ejecuta con ella. Fluency es
  `e1314209030@live.uleam.edu.ec`, cuya contraseña no está guardada en el repo.
- ~~Ajuste de las horas~~ — implementado (`FluencyDurationCalculator`):
  presupuesto total de horas de estudio (`FLUENCY_TOTAL_COURSE_HOURS`,
  default 70) repartido con jitter entre las lecciones y steps de la
  corrida, reemplazando el `durationMs` fijo de 5000ms.
---

## Links Útiles

- **Rosetta Stone GraphQL:** https://graph.rosettastone.com/graphql
- **Tracking API:** https://tracking.rosettastone.com
- **Playwright docs:** https://playwright.dev/python/
- **FastAPI docs:** https://fastapi.tiangolo.com/
- **Docker Compose:** https://docs.docker.com/compose/

---

**Por Elkin Delgado** | MIT License
