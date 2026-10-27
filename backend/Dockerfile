# API de Talentia Insights (FastAPI). Se construye desde la raiz del proyecto
# (docker-compose.yml) porque necesita backend/ y db/.
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Mismo acomodo que el repositorio: el codigo busca db/ dos niveles arriba de app/
WORKDIR /app/backend
COPY backend/requirements.txt .
RUN pip install -r requirements.txt

COPY db /app/db
COPY backend/app ./app
COPY backend/scripts ./scripts

# Sin permisos de administrador dentro del contenedor
RUN useradd --create-home --uid 10001 talentia
USER talentia

EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --start-period=60s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"

# Siembra los datos ficticios si la base esta vacia, prepara la demo y arranca la API
CMD ["python", "-m", "scripts.arranque"]
