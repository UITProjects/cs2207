# Gathering demo on PUBG trajectories (CS2207 · Nhóm 12), Streamlit app on port 8501.
# Multi-platform: build with `docker buildx build --platform linux/amd64,linux/arm64` (see README).
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# dependencies first, so code changes do not reinstall them (requirements.txt = `uv export --no-dev` + pytest)
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY config.yaml ./
COPY .streamlit/ .streamlit/
COPY assets/ assets/
COPY src/ src/
COPY app/ app/
COPY tests/ tests/
COPY data/sample/ data/sample/

# build-time check: synthetic mining tests + parser tests + full pipeline on one sample match
RUN python -m pytest -q tests/test_mining.py tests/test_parse.py -p no:cacheprovider \
 && python -c "import json,pathlib; from src.config import default_params; from src.mining.pipeline import run_pipeline; \
from src.parse.telemetry import read_tables; d=sorted(p for p in pathlib.Path('data/sample/mock').iterdir() if (p/'meta.json').exists())[0]; \
r=run_pipeline(read_tables(d), default_params()); assert r.gatherings, 'no gathering on sample'; \
print('pipeline ok', d.name, len(r.crowds), 'crowds', len(r.gatherings), 'gatherings')" \
 && rm -rf tests

RUN useradd --create-home --uid 1000 app && chown -R app /app
USER app

EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')"

# .streamlit/config.toml in /app holds the theme; the base URL path comes from the k8s manifest env
CMD ["streamlit", "run", "app/Home.py", \
     "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
