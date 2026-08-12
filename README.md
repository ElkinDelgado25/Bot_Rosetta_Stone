# Rosseta-Stone-Script-A

Bot que marca lecciones de Rosetta Stone como completadas. No las resuelve:
obtiene el árbol del curso desde la propia plataforma, fabrica puntaje y
duración a partir de los metadatos que ella misma declara, y los envía al
endpoint de seguimiento.

Soporta los dos productos: **Foundations** y **Fluency Builder**. Cada uno usa
su propio backend y modelo de contenido; el bot detecta cuál tiene la cuenta.

Hay dos formas de usarlo:

| | Para qué | Cuántas cuentas |
|---|---|---|
| **CLI** | Una pasada, desde la terminal | Una, la del `.env` |
| **Interfaz web** | Gestionar usuarios y lanzarlos desde el navegador | Varias, cada una con lo suyo |

---

## Requisitos

- **Python >= 3.14**. No hay `requirements.txt`: las dependencias están en
  `pyproject.toml` y fijadas en `uv.lock`.
- [**uv**](https://docs.astral.sh/uv/). Si no lo tienes:

  ```bash
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  ```

- Un navegador **Chrome o Edge** instalado (lo normal en Windows). El bot usa el
  del sistema; si no encuentra ninguno, cae al Chromium que trae Playwright.
- **Docker Desktop**, solo si vas a usar la interfaz web en contenedores.

---

## Puesta en marcha

```bash
git clone https://github.com/ElkinDelgado25/Bot_Rosetta_Stone.git
cd Bot_Rosetta_Stone
uv sync --extra web
```

`--extra web` añade FastAPI y el cliente de Docker. Si solo vas a usar la CLI,
`uv sync` a secas es suficiente.

Si no tienes Chrome ni Edge (típico en Linux), instala el navegador de
Playwright una vez:

```bash
uv run playwright install chromium
```

---

## Opción A · Interfaz web en Docker (recomendada)

Es la forma completa: gestionas varios usuarios desde el navegador y **cada uno
corre en su propio contenedor**, todos a la vez.

```bash
docker compose up -d --build --force-recreate
```

Abre <http://127.0.0.1:8000>.

> **`--force-recreate` no sobra.** `--build` reconstruye la imagen pero deja
> corriendo el contenedor viejo, así que verías el código anterior sin entender
> por qué. Úsalo siempre que hayas tocado el código.

En Linux, el contenedor necesita el grupo del socket de Docker:

```bash
DOCKER_GID=$(getent group docker | cut -d: -f3) docker compose up -d --build --force-recreate
```

Comandos útiles:

```bash
docker compose logs -f rosetta-web
```

```bash
docker compose down
```

Todo el estado vive en `./data` (`profiles.json`, `state/`, `logs/`). Es la
única carpeta que hay que respaldar; si la borras, se pierde el progreso.

### Cómo usarla

1. **+ Nuevo usuario** → correo y contraseña de Rosetta Stone. Nada más: el
   resto lo averigua el bot solo.
2. Al guardar se **verifica automáticamente**: inicia sesión, pasa por la
   selección institucional si aparece, y detecta si la cuenta usa Foundations o
   Fluency Builder. **No envía nada.**
3. La ficha muestra el producto detectado y si la ruta institucional apareció.
4. **Ejecutar** lanza el ciclo completo. El registro en vivo y la tabla de
   avance por lección muestran cómo va.

Los botones **Verificar** y **Ejecutar** son distintos a propósito: Verificar
solo comprueba que la cuenta entra, Ejecutar sí modifica el progreso real.

Repite por cada cuenta. Todas pueden correr a la vez, cada una aislada en su
contenedor: si un navegador se cuelga, se lleva solo el suyo.

---

## Opción B · Interfaz web en local, sin Docker

```bash
uv run rosseta-web
```

Igual que la anterior, en <http://127.0.0.1:8000>, pero **sin aislamiento**: las
corridas comparten navegador y archivo de estado, así que se ejecutan **de una
en una** y las demás esperan en cola con su posición.

`GET /api/health` dice en qué modo está:

```bash
curl http://127.0.0.1:8000/api/health
```

`"backend":"docker"` = un contenedor por usuario, en paralelo.
`"backend":"in-process"` = todo en este proceso, en cola.

---

## Opción C · CLI, una sola cuenta

```bash
uv run python -m rosseta_stone_script_a
```

Lee todo del `.env`. Si no existe, la primera ejecución lo crea preguntando
correo y contraseña. Usa `.env.example` como plantilla para el resto de
opciones.

Sin `uv`, con el entorno ya sincronizado:

```bash
.\.venv\Scripts\python.exe -m rosseta_stone_script_a
```

**Códigos de salida** (útiles si lo programas en una tarea automática):

| Código | Significa |
|---|---|
| `0` | Todo bien |
| `1` | Error |
| `3` | La sesión no se capturó completa: **no se envió nada**, normalmente falló el login |
| `130` | Interrumpido con Ctrl+C |

---

## Variables de entorno

Van en el `.env` (o en el `environment:` del compose).

| Variable | Por defecto | Para qué |
|---|---|---|
| `ROSETTA_EMAIL` / `ROSETTA_PASSWORD` | — | Credenciales de la CLI |
| `ROSETTA_HOME` | directorio actual | Dónde viven `.env`, `profiles.json`, `state/` y `logs/` |
| `ROSETTA_WEB_HOST` | `127.0.0.1` | Interfaz donde escucha la web |
| `ROSETTA_WEB_PORT` | `8000` | Puerto |
| `ROSETTA_WEB_TOKEN` | *(vacío)* | Token compartido. Vacío = API abierta |
| `ROSETTA_RUN_BACKEND` | automático | `docker` o `in-process`, para forzar el modo |
| `BROWSER_HEADLESS` | `false` | `true` para no ver la ventana del navegador |
| `LOG_LEVEL` | `INFO` | `DEBUG` para diagnosticar |

---

## Seguridad

**Las contraseñas se guardan en texto plano** en `profiles.json`, igual que en
el `.env`. El archivo se escribe con permisos 0600, y eso es toda la protección
que hay. Si prefieres no guardarlas, deja el campo vacío al crear el usuario y
la UI la pedirá en cada ejecución.

**No expongas el puerto sin token.** El compose publica solo en `127.0.0.1` a
propósito. La API puede lanzar corridas con las credenciales ya guardadas, y el
contenedor web monta `docker.sock` para crear los workers — quien controle esa
web controla el daemon de Docker, que en la práctica equivale a root en la
máquina. Si necesitas exponerlo, define `ROSETTA_WEB_TOKEN` primero.

Los tokens de sesión que captura cada corrida se guardan por usuario en
`state/sessions/<id>.json` con permisos 0600, y la API nunca los devuelve
enteros: en la UI aparecen enmascarados.

---

## Si algo falla

| Síntoma | Causa habitual |
|---|---|
| Cambias código y la web no cambia | Faltó `--force-recreate` al levantar el compose |
| `did not find executable at ...` | El Python del venv desapareció: `uv python install 3.14` y `uv sync` |
| La corrida sale con código `3` | Login incompleto; verifica el usuario desde la UI para ver dónde se corta |
| Un usuario dice `0 completadas` tras ejecutar | Mira el registro en vivo: si no envió nada, la sesión no se capturó |
| `Could not launch a browser` | No hay Chrome ni Edge: `uv run playwright install chromium` |
| La UI no responde y Docker acaba de reiniciar | El contenedor arranca solo, pero con la imagen previa: reconstruye |

---

## Desarrollo

Tests (119):

```bash
uv run pytest -q
```

Ninguno abre un navegador ni lanza contenedores: la capa web se prueba con un
backend falso inyectado.

Compilar el `.exe`:

```bash
uv run --group dev python build.py
```

Sale en `dist/rosseta-script-a.exe`. Copia el `.exe` a una carpeta y pon un
`.env` **en esa misma carpeta** (lee el suyo, no el del directorio actual). El
binario **no incluye la interfaz web**, a propósito, para no arrastrar FastAPI.

### Estructura

```
src/rosseta_stone_script_a/
├── domain/           Entidades, valores y errores del dominio
├── application/      Orquestadores, casos de uso, puertos y servicios
├── infrastructure/   Adaptadores (Playwright, APIs), estado, configuración
└── presentation/
    ├── cli.py        Entrada de terminal, una cuenta
    ├── worker.py     Una corrida dentro de un contenedor efímero
    └── web/          Interfaz web multi-usuario (FastAPI + un HTML)
```

`docs/ARCHITECTURE.md` explica la modularización y `CLAUDE.md` el ciclo de
ejecución y las trampas del entorno.

---

## Licencia

MIT.
