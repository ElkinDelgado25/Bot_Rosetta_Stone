# Rosseta-Stone-Script-A

Rosseta-Stone-Script-A es una herramienta automatizada diseñada para interactuar con la plataforma Rosetta Stone, facilitando el avance y la finalización de lecciones de idiomas de manera eficiente. El proyecto permite gestionar sesiones, analizar el progreso, generar reportes y optimizar el camino de aprendizaje para usuarios de Rosetta Stone.

## ¿Qué hace?

- Automatiza la navegación y finalización de lecciones en Rosetta Stone.
- Captura y analiza el historial de sesiones de usuario.
- Genera reportes de avance y recomendaciones personalizadas.
- Filtra contenido y calcula rutas óptimas de aprendizaje.
- Permite la integración con APIs y adaptadores para ampliar funcionalidades.

## ¿Cómo funciona?

El proyecto está estructurado en módulos que separan la lógica de negocio, la infraestructura, la presentación y el dominio. Utiliza orquestadores para coordinar el flujo de trabajo, servicios para procesar datos y adaptadores para interactuar con fuentes externas (como la API de Rosetta Stone).

### Estructura principal

- `src/rosseta_stone_script_a/application/`: Orquestadores, puertos y servicios.
- `src/rosseta_stone_script_a/domain/`: Entidades, valores y constantes del dominio.
- `src/rosseta_stone_script_a/infrastructure/`: Adaptadores y configuración.
- `src/rosseta_stone_script_a/presentation/`: CLI y dependencias.
- `logs/`: Registro de sesiones, errores y reportes.

### Flujo básico

1. El usuario inicia el script desde la CLI.
2. Se capturan las credenciales y preferencias.
3. El orquestador coordina la interacción con la plataforma.
4. Se procesan los datos de avance y se generan reportes.
5. Los resultados se almacenan en logs y pueden ser consultados o exportados.

## Instalación

1. Clona el repositorio:
 ```bash
 git clone https://github.com/ElkinDelgado25/Bot_Rosetta_Stone.git
 ```

2. Instala las dependencias. El proyecto usa [uv](https://docs.astral.sh/uv/) y
   requiere **Python >= 3.14** (no hay `requirements.txt`; las dependencias viven
   en `pyproject.toml` y están fijadas en `uv.lock`):

 ```bash
 uv sync
 ```

 Si no tienes `uv`, instálalo con:

 ```bash
 powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
 ```

3. Copia `.env.example` a `.env` y ajusta las credenciales y preferencias.

## Uso

Ejecuta el script principal:

```bash
uv run python -m rosseta_stone_script_a
```

Si prefieres no usar `uv`, activa el entorno creado por `uv sync` y ejecuta el
módulo directamente:

```bash
.\.venv\Scripts\python.exe -m rosseta_stone_script_a
```

Puedes personalizar el comportamiento mediante argumentos CLI o modificando el `.env`.

## Compilar el .exe

```bash
uv run --group dev python build.py
```

O, sin `uv`, con el entorno ya sincronizado:

```bash
.\.venv\Scripts\python.exe build.py
```

El ejecutable se genera en `dist/rosseta-script-a.exe`. Para usarlo:

1. Copia `rosseta-script-a.exe` a una carpeta y pon un archivo `.env` **en la misma
   carpeta** (usa `.env.example` como plantilla — el `.exe` lee el `.env` de su
   propia carpeta, no del directorio actual).
2. Necesita Chrome o Edge instalado (lo normal en Windows). No hace falta
   `playwright install`: el bot usa el navegador del sistema vía `BROWSER_CHANNEL`
   (`chrome` → `msedge` → Chromium de Playwright como último recurso).

## Contribución

Si deseas contribuir, por favor abre un issue o pull request. Revisa la arquitectura en `docs/ARCHITECTURE.md` para entender el flujo interno.

## Licencia

Este proyecto está bajo la licencia MIT.

---
Para dudas o soporte, contacta al propietario del repositorio.
