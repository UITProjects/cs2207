# Demo Gathering · buổi hòa nhạc (CS2207 · Nhóm 12), Streamlit app on port 8501.
# Multi-platform: build with `docker buildx build --platform linux/amd64,linux/arm64` (see README).
# The base image and every pinned wheel exist for both architectures, so nothing compiles.
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# dependencies first, so code changes do not reinstall them
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
# check the dataset and the expected mining result at build time
RUN python check_core.py

RUN useradd --create-home --uid 1000 app && chown -R app /app
USER app

EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')"

# .streamlit/config.toml in /app holds the theme
CMD ["streamlit", "run", "app.py", \
     "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
