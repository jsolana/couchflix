# Imagen multi-arquitectura (linux/arm64 para Raspberry Pi, linux/amd64). Solo Python puro: sin compilaciones.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    COUCHFLIX_HOST=0.0.0.0 COUCHFLIX_PORT=8765 COUCHFLIX_DB=/data/couchflix.db

WORKDIR /app
COPY pyproject.toml ./
COPY couchflix_app ./couchflix_app
RUN pip install .

RUN useradd --system --create-home --uid 1000 couchflix && mkdir /data && chown couchflix /data
USER couchflix
VOLUME /data
EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import os,urllib.request as u; u.urlopen('http://127.0.0.1:'+os.environ['COUCHFLIX_PORT']+'/', timeout=4)"

CMD ["python", "-m", "couchflix_app"]
