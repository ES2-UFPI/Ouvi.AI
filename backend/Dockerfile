# Imagem base enxuta com Python 3.12
FROM python:3.12-slim

# Não gera .pyc e não bufferiza stdout (logs aparecem na hora no `docker logs`)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Copia só o requirements antes do código: enquanto ele não mudar,
# o Docker reaproveita a camada de dependências do cache
COPY requirements.txt .
RUN pip install -r requirements.txt

# Usuário sem privilégios: o processo da API não roda como root
RUN useradd --create-home --uid 1000 appuser

COPY --chown=appuser:appuser . .
USER appuser

EXPOSE 8000

# Verifica a cada 30s se a API responde em /health (usa o python, pois a imagem slim não tem curl)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Comando padrão (sem --reload). O docker-compose sobrescreve com --reload para desenvolvimento
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
