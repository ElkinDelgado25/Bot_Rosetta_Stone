# CLAUDE.md

Guía para trabajar en este repositorio. Complementa `docs/ARCHITECTURE.md`, que
describe la modularización por capas; este archivo cubre el ciclo de ejecución,
los comandos y las trampas del entorno.

## Qué es el proyecto

Bot que marca lecciones de Rosetta Stone completadas. No
resuelve las lecciones: obtiene el árbol del curso, fabrica puntaje y duración a
partir de los metadatos que la propia plataforma declara, y los envía al endpoint
de tracking.

**Soporta Foundations y Fluency Builder.** Cada producto usa su propio backend y
modelo de contenido, con adaptadores y orquestadores independientes.

## Comandos

Ejecutar:

```bash
.\.venv\Scripts\python.exe -m rosseta_stone_script_a
```

Tests (119 tests):

```bash
.\.venv\Scripts\python.exe -m pytest -q
```

Levantar la UI web (requiere `uv sync --extra web`):

```bash
.\.venv\Scripts\python.exe -m rosseta_stone_script_a.presentation.web.server
```

Levantarla en Docker:

```bash
docker compose up -d --build
```

Compilar el .exe:

```bash
.\.venv\Scripts\python.exe build.py
```

Recrear el entorno:

```bash
uv sync
```

Nota: el módulo se invoca como `rosseta_stone_script_a`, **sin** prefijo `src.`.
La forma `src.rosseta_stone_script_a` funciona solo por namespace package
implícito y depende de estar parado en la raíz del repo.

## Dos entradas, un solo motor

`presentation/` tiene dos capas hermanas sobre los **mismos** orquestadores:

- **`cli.py`** — una cuenta, la del `.env`, ejecutada de una pasada.
- **`web/`** — varios usuarios, cada uno con sus credenciales, filtros y
  progreso. Es solo una fachada: construye el mismo `DependencyFactory` y llama
  a `RosettaCLI.enter_rosetta`. Nada bajo `application/` o `domain/` sabe que
  existe.

Piezas de `web/`:

| Archivo | Responsabilidad |
|---|---|
| `profiles.py` | `profiles.json` en `get_base_dir()`, permisos 0600. Contraseñas en texto plano, como el `.env` |
| `backends.py` | Dónde corre una corrida: `DockerBackend` (un contenedor por usuario) o `InProcessBackend` (fallback local) |
| `run_manager.py` | Estado por perfil, buffer de logs, ingesta de eventos, redacción de JWT/tokens |
| `session_store.py` | Tokens capturados por usuario en `state/sessions/<id>.json`, 0600 |
| `app.py` | Rutas FastAPI. Token compartido opcional vía `ROSETTA_WEB_TOKEN` |
| `static/index.html` | UI entera: sin build, sin CDN, sin dependencias de front |

**Dos modos de corrida.** `mode="run"` hace el ciclo completo; `mode="verify"`
para tras la fase del navegador (`enter_rosetta(verify_only=True)`): inicia
sesión, pasa por la selección institucional, detecta el producto y cosecha los
tokens, pero **no envía nada**. Es el botón *Verificar*, y se dispara solo al
crear un usuario. El modo viaja por el mismo camino que todo lo demás: perfil →
`RunManager.enqueue(mode=...)` → backend → config del worker.

**Los endpoints que lanzan corridas son `async def`.** `enqueue` programa una
`asyncio.Task`; un endpoint síncrono lo ejecuta FastAPI en un hilo del pool, sin
event loop, y `create_task` lanza `RuntimeError`. Como los tests de error
(400/404/409) nunca llegan a esa línea, el fallo solo aparecía en producción —
por eso hay un test del camino feliz por HTTP.

Y `presentation/worker.py`: el comando que ejecuta **un** contenedor efímero.
Lee su config de un JSON en el volumen, corre una sola corrida, y devuelve los
tokens capturados por un archivo de resultado.

## Arquitectura de ejecución

```
contenedor web (orquestador)          docker.sock
  · gestiona usuarios          ──────────────────► worker usuario1  (efímero)
  · lanza un worker por usuario                    worker usuario2  (efímero)
  · lee stdout de cada worker  ◄──────────────────  worker usuario3  (efímero)
```

**Contenedores hermanos, no Docker-in-Docker.** DinD exige `--privileged` y
anida Chromium; los hermanos usan el daemon que ya corre. El precio: el
contenedor web monta `docker.sock`, y quien controle esa web controla el daemon
— por eso el puerto está en loopback en el compose.

**Dos canales de vuelta.** El worker escribe a stdout: líneas de log normales y
eventos JSON con prefijo `@@EVENT` (`shared/events.py`). El orquestador separa
unos de otros en `RunManager.ingest`; los eventos alimentan el avance por
unidad/lección, el resto va a la consola en vivo.

**Los tokens no van por stdout.** Cualquiera con acceso al daemon puede leer los
logs de un contenedor, así que la sesión capturada vuelve por
`<config>.result.json` en el volumen, y config y resultado se borran al terminar.

**Dos backends, uno se elige solo.** `select_backend` usa contenedores solo si
la web *misma* corre en uno (`/.dockerenv` o `ROSETTA_DATA_HOST_PATH`): un
Docker Desktop en el portátil responde al socket, pero un worker lanzado desde
ahí no podría montar el `/data` del proceso. Se fuerza con
`ROSETTA_RUN_BACKEND=docker|in-process`.

**Con contenedores no hay cola; sin ellos sí.** `DockerBackend.supports_parallel`
es `True` y cada usuario arranca de inmediato. `InProcessBackend` comparte
navegador y archivo de estado, así que `RunManager` serializa y los demás quedan
en `queued` con su posición.

**El worker necesita el `/data` del host, no el suyo.** Un bind mount apunta a
una ruta del host que desde dentro no se ve; `_host_data_path()` la deduce
inspeccionando los propios mounts vía la API de Docker, con
`ROSETTA_DATA_HOST_PATH` como respaldo.

**El progreso no se guarda en memoria.** `progress_for()` relee
`RunProgressState` del disco en cada consulta. Como `complete_foundations`
persiste tras cada POST aceptado, eso da el avance real a mitad de corrida y
sobrevive a un reinicio del contenedor. Un contador en RAM no haría ninguna de
las dos cosas.

**El `user_id` se aprende.** El archivo de estado se llama `<user_id>.json`, y
ese id no se conoce hasta que una corrida lo captura. Por eso `enter_rosetta`
devuelve `captured_data` y el perfil guarda `last_user_id`; antes de la primera
corrida el progreso se busca por el slug del email.

## Ciclo de ejecución

Cuatro fases. La entrada es `presentation/cli.py` (o `presentation/web/`); la
coordinación vive en `application/orchestrators/`.

### 1. Captura de credenciales (navegador)

Es la **única** fase con navegador. `open_fundations.py` registra
`page.on("request")` **antes** del login y deja que `RosettaSessionCapturer` lea
headers y URLs del tráfico saliente. No lee cookies.

#### Recorrido de pantallas

Todas las acciones pasan por `web_session.interactor`; los selectores son
semánticos (rol + regex de nombre), no CSS frágil.

**1 · `login.rosettastone.com/login`** — `LoginPage.login()`

- `fill` email → textbox con nombre `correo electrónico|email address`
- `fill` password → textbox con nombre `contraseña|password`
- `click` botón `iniciar sesión|sign in|log in|ingresar`
- screenshot `before_login`

**2 · Selección de cuenta institucional** — `_handle_institutional_account_selection()`

Solo si aparece. Prueba cinco selectores en orden (`by_text("uleam")`, luego
cuatro variantes CSS) y hace `click_first` en el primero que exista. Si acierta,
**vuelve a llenar la contraseña y re-envía el formulario**: el flujo institucional
pide autenticarse otra vez tras elegir la organización.

El literal `"uleam"` está hardcodeado en `login_page.py:89-94`. Con otra
institución esta fase no encuentra nada, no falla, y el login queda a medias.

**3 · `login.rosettastone.com/launchpad`** — `DashboardPage`

- `get_user_name()` lee `[data-qa="DashboardUserName"]` y extrae el nombre del
  texto `Hello, {nombre}!` con regex. Si falla solo emite warning: es opcional,
  se usa para el reporte.
- `open_foundations()` busca texto `foundations|fundamentos` con timeout 2000ms.
  Si no está, comprueba `fluency builder` para dar un error específico.

**4 · Workspace de Foundations** — screenshot y nada más.

Después de esto `_wait_for_session_capture()` hace polling cada 0.5s hasta 15s
esperando las cinco credenciales, quita el listener, y **el navegador queda
inerte** hasta que el `finally` de `cli.py` lo cierra.

#### Nota: los POSTs no dependen de las pantallas

Es la confusión habitual con este código. La navegación **no** dispara envíos, y
no hay un POST "por lo que se hizo en pantalla". Las pantallas sirven solo para
cosechar los cinco tokens. A partir de la fase 2 la fuente de verdad es el árbol
que devuelve GraphQL: qué se envía sale de ahí, no de nada visible.

Por eso el bot puede marcar cientos de actividades sin abrir ninguna, y por eso
un cambio de DOM en el workspace no afecta a los envíos — solo rompe la cosecha
de tokens.

Necesita cinco valores, de dos sistemas distintos:

| Valor | Origen |
|---|---|
| `authorization` | Header, filtrado por prefijo `eyJ` para tomar el JWT y no el Bearer UUID |
| `school_id`, `user_id` | Regex sobre `/ee/ce/{school}/users/{user}/recommended_course` |
| `lang_code` | Query param `product_identifier` |
| `session_token` | Header `x-rosettastone-session-token` |

`is_complete()` verifica que estén los cinco. Si falta alguno, el orquestador
lanza `SessionCaptureIncomplete` y la corrida **falla con código 3**: no se
envía nada y se nota.

Después de esta fase el navegador ya no interviene: todo lo demás va por
`APIRequestContext`.

### 2. Lectura del curso (GraphQL)

```
POST https://graph.rosettastone.com/graphql
```

Operación `GetCourseMenu`, auth por header `authorization`. Devuelve
`units → lessons → paths` con `complete`, `percentComplete`, `numChallenges` y
`timeEstimate` por path. `CourseMenuParser` lo convierte a entidades de dominio.
La respuesta cruda se vuelca en `logs/diagnostics/` para inspección.

### 3. Selección y fabricación

- `ContentFilter` descarta unidades/lecciones/tipos según config del `.env`.
- `StateStore` (`state/`) descarta lo ya enviado en corridas previas.
- `PathCalculator` genera los números:
  - duración = `timeEstimate` ± hasta un tercio, al azar
  - `questions_correct` = `ceil(num_challenges * target_score_percent/100)`,
    con `target_score_percent=100` por defecto

No se mide nada real. `start_time` y `time_so_far` llegan como `0` desde
`complete_foundations.py`, así que el `time_completed` que calcula se descarta.

Los timestamps salen de un cursor que arranca en
`now - jitter - suma_de_duraciones` y avanza sumando cada duración, de modo que
ninguna marca caiga en el futuro.

### 4. Envío (REST + XML)

```
POST https://tracking.rosettastone.com/ee/ce/{school_id}/users/{user_id}/path_scores
     ?course=...&unit_index=...&lesson_index=...&path_type=...&_method=put
```

Auth por `x-rosettastone-session-token`. Body XML con `<complete>true</complete>`.
Un POST por path; si responde OK se marca en `state/` y se persiste de inmediato
para que una caída no pierda progreso.

Al terminar, `ReportGenerator` escribe el reporte en `logs/user_data/` y
`ReportHistoryAnalyzer` acumula unidades completadas entre corridas.

## Detalles no obvios

**`unit_index % 4`** — `complete_foundations.py:400`. El GraphQL numera unidades
globalmente (0-19 entre los 5 niveles), pero el endpoint de tracking espera el
índice relativo al curso (0-3). Sin el módulo, solo el nivel 1 registra; L2-L5
escriben en coordenadas inexistentes.

**Dos APIs de épocas distintas** — GraphQL es la capa nueva; `tracking.` es la
API del cliente de escritorio Totale (de ahí `x-rosettastone-app-version:
ZoomCourse/11.11.2` y el Referer `totale.rosettastone.com`). Por eso hay dos
esquemas de auth y dos formatos de body.

**`_method=put`** — el endpoint quiere un PUT tunelizado sobre POST, convención
vieja de Rails.

**`human_mode`** — cuando está activo aplica topes diarios, lotes aleatorios y
pausas entre envíos. Por defecto está apagado (modo rápido, todo de una).

**Screenshot mal nombrado** — `go_to_foundations.py:36` guarda la captura del
workspace como `fluency_builder_workspace`, pero ese use case navega a
Foundations. Es un nombre heredado y confunde justamente donde más importa;
conviene renombrarlo.

**El motor de Fluency completa 1 lección por corrida si nadie dice otra cosa** —
`FLUENCY_MAX_LESSONS` vale `1` por defecto en `DependencyFactory`, pensado para
una primera prueba controlada desde la terminal. Desde la UI eso se leía como
un fallo: completaba una lección y paraba con éxito. El perfil tiene
`fluency_max_lessons` (None = todas) y los dos backends lo traducen con
`fluency_limit_env()` a `"all"` antes de lanzar. El default del motor no se
tocó: la CLI sigue siendo conservadora.

**El estado de Fluency es por cuenta, no global** — las claves de actividad son
`fluency|curso|secuencia|actividad`, **sin la cuenta dentro**. Con el antiguo
`fluency_state.json` único, el segundo usuario veía como hechas las actividades
del primero y las saltaba: terminaba con código 0 sin enviar nada. Ahora es
`fluency_<user_id>.json` (`_state_for`), resuelto en `execute()` porque el
`user_id` no se conoce hasta que la corrida lo captura. Foundations ya lo hacía
así vía `StateStore`.

**El progreso de la UI suma los dos esquemas** — `progress_for` lee
`<user_id>.json` *y* `fluency_<user_id>.json`. Mirar solo el primero hacía que
una cuenta de Fluency mostrara siempre "0 completadas" por muchas lecciones que
hubiera hecho.

**Los eventos aceptan unidad/lección no numéricas** — Foundations las numera,
Fluency las nombra (`"Preflight"`) y no tiene unidad. `_apply_event` guarda el
valor tal cual; un `int()` sobre el título reventaba dentro del lock y mataba la
ingesta entera.

**Sesión incompleta = error, no silencio** — si la fase del navegador no cosecha
los cinco valores, ambos orquestadores lanzan `SessionCaptureIncomplete`
(`domain/errors.py`) en vez de avisar y volver. Antes esa ruta salía con código
0 habiendo enviado nada: el scheduler veía éxito y la UI un chip verde.

**Códigos de salida** — `0` ok · `1` error · `2` config ilegible (solo el
worker) · `3` sesión incompleta · `130` interrumpido. El `3` está separado a
propósito: distingue "falló el login" de un fallo cualquiera.

**Lo que sí sigue degradando** — el nombre de usuario (solo se usa para el
reporte) y la selección institucional emiten warning y continúan. El primero es
opcional de verdad; el segundo se manifiesta después, porque sin elegir la
organización el login no llega al launchpad y la captura queda incompleta —
que ahora sí falla.

## Entorno (trampas verificadas)

**El venv usa un Python gestionado por uv.** `pyvenv.cfg` apunta a
`%APPDATA%\uv\python\cpython-3.14-...`. Si esa ruta no existe, cualquier comando
falla con `did not find executable at '...'`. Se arregla con
`uv python install 3.14` y recreando el venv.

**No hay `pip` en el venv.** Es intencional: uv no lo instala. La extensión de
Python de VS Code lo intenta igual y llena el log de errores; por eso
`.vscode/settings.json` tiene `python-envs.alwaysUseUv`.

**No existe `requirements.txt`.** Las dependencias están en `pyproject.toml` y
fijadas en `uv.lock`. Requiere Python >= 3.14.

**El paquete raíz no tiene `__init__.py`.** `src/rosseta_stone_script_a/` y otras
14 carpetas son namespace packages. Por eso `pyproject.toml` declara
`packages.find` explícito con `where = ["src"]` en vez de confiar en la
autodetección de setuptools.

**`AppData\Roaming` puede estar virtualizado.** Si trabajas desde un entorno
sandboxed, `Test-Path` sobre esa ruta puede dar falsos positivos apuntando a una
copia privada. Verifica con `(Get-Item ruta).Target`.

**`ROSETTA_HOME` manda sobre el cwd.** `get_base_dir()` y
`detect_project_root()` la respetan, y de ahí cuelgan `.env`, `profiles.json`,
`state/` y `logs/`. El contenedor la fija en `/data`; sin ella todo caería
relativo al directorio de trabajo, que en la imagen no es escribible por el
usuario no-root.

**`BROWSER_CHANNEL` vacío significa "sin canal".** El provider prueba
`chrome` → `msedge` → Chromium bundled. En Linux los dos primeros no existen, y
cada intento fallido cuesta una excepción; la imagen lo deja vacío para ir
directo al Chromium de Playwright.

**Las imágenes de Playwright no sirven aquí.** `mcr.microsoft.com/playwright/python`
trae Python 3.12 y el proyecto exige >=3.14. Por eso el Dockerfile parte de
`python:3.14-slim` e instala Chromium con `playwright install --with-deps`.

**Los tests de la web nunca abren un navegador ni un contenedor.**
`tests/presentation/web/conftest.py` da un `FakeBackend` que se inyecta en
`RunManager` y `create_app`. Ninguno de los dos resuelve un backend por su
cuenta en los tests. Si se quita, un test que lance una corrida abrirá Chrome de
verdad e intentará loguearse en Rosetta Stone — pasó durante el desarrollo y
cuelga la suite.

**El JSON del worker se lee con `utf-8-sig`.** Un archivo de configuración
tocado a mano en Windows lleva BOM, y `json.load` revienta con un traceback que
no explica nada.

## Alcance

Trabajo que corresponde en este repo: empaquetado, entorno, build del `.exe`,
contenedores, la UI web, tests, logging, códigos de salida, mensajes de error,
refactors y documentación.

Extender el mecanismo de completación fabricada a productos nuevos (Fluency
Builder u otros) también entra.

**Fuera de alcance:** hacer que los envíos sean más difíciles de distinguir de
actividad real. Es evasión de detección y no se trabaja aquí. La línea es:
implementar la funcionalidad sí, disfrazarla no.

### Pendiente

- No hay CLI con argumentos: `main_cli()` sigue leyendo todo del `.env`.
- El `.exe` de PyInstaller no incluye la UI web (el extra `web` es opcional a
  propósito, para no arrastrar FastAPI al binario).
- El literal `"uleam"` sigue hardcodeado en `login_page.py`; con otra
  institución el login queda a medias y ahora falla con `SessionCaptureIncomplete`,
  que es mejor que antes pero no explica la causa real.
- La vista de avance por lección se ha probado con eventos sintéticos y con una
  corrida real de Foundations; con Fluency los eventos son nuevos y aún no se
  han visto en vivo.
- `data/state/fluency_state.json.compartido.bak` es el estado global de antes
  del arreglo. Se apartó en vez de repartirlo porque no hay forma fiable de
  saber de qué cuenta era; se puede borrar cuando ambos usuarios hayan corrido.


