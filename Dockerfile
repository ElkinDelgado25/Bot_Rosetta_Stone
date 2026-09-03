# Imagen para la UI web multi-usuario.
#
# Base: python:3.14-slim. Las imágenes oficiales de Playwright
# (mcr.microsoft.com/playwright/python) traen Python 3.12, y el proyecto exige
# >=3.14, así que el navegador se instala aquí en vez de heredarlo.
FROM python:3.14-slim AS base

# Chromium se instala en una ruta fija del sistema para que el usuario no-root
# lo encuentre: por defecto Playwright lo pondría en el ~/.cache del que ejecuta
# `playwright install`, que es root en el build.
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Capa de dependencias: solo se reconstruye si cambian los manifiestos.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --extra web --no-dev --no-install-project

# Chromium + sus librerías de sistema. --with-deps necesita root, por eso va
# antes de cambiar de usuario. Debian publica la imagen con repos HTTP; usar
# HTTPS evita fallos en redes que bloquean tráfico HTTP saliente.
RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources
RUN /opt/venv/bin/python -m playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

COPY src/ ./src/

# curl solo para el HEALTHCHECK.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# El paquete raíz no tiene __init__.py (namespace packages), así que se ejecuta
# desde el árbol de fuentes vía PYTHONPATH, igual que en local.
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/app/src \
    ROSETTA_HOME=/data \
    ROSETTA_WEB_HOST=0.0.0.0 \
    ROSETTA_WEB_PORT=8000 \
    BROWSER_HEADLESS=true \
    BROWSER_CHANNEL=""

# /data guarda .env, profiles.json, state/ y logs/. Es el único volumen.
RUN useradd --create-home --uid 1000 app \
    && mkdir -p /data \
    && chown -R app:app /data /app
USER app
WORKDIR /data

EXPOSE 8000
VOLUME ["/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1

CMD ["python", "-m", "Resolucion_script_rosseta.presentacion.web.server"]
