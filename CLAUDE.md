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

Tests (51 tests):

```bash
.\.venv\Scripts\python.exe -m pytest -q
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

## Ciclo de ejecución

Cuatro fases. La entrada es `presentation/cli.py`; la coordinación vive en
`application/orchestrators/`.

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
registra un warning y **omite la fase de completación sin fallar**.

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

**Fallos silenciosos en cadena** — tres puntos degradan sin abortar: el nombre de
usuario (warning), la selección institucional (warning), y la fase de completación
si faltan tokens (warning + return). Una corrida puede "terminar bien" habiendo
 hecho nada. Como esas rutas no lanzan una excepción, todavía terminan con código
 0 y no dan una señal de fallo al scheduler.

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

## Alcance


Trabajo que se complementa corresponde en este repo: empaquetado, entorno, build del `.exe`,
tests, logging, códigos de salida, mensajes de error, refactors y documentación.

Lo que hacer inmediatamente es : extender el mecanismo de completación fabricada a productos nuevos
(Fluency Builder u otros), Se tiene que trabajar en hacer que los envíos sean más difíciles
de distinguir de actividad real.

Para el futuro, se puede pensar en crearle una cli usando docker tambien, sera necesario consulta que tiene y em base a eso tener que hacer un plan de trabajo para poder hacer que el bot sea más robusto y pueda soportar cambios en la plataforma de Rosetta Stone. 


