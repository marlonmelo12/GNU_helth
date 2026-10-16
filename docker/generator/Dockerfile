# Imagem do gerador do hospital simulado (v2) e das verificacoes de lote.
# Nao precisa do GNU Health: gera e valida lotes; a carga no ERP usa o container do servidor.
FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app
COPY requirements-generator.txt /tmp/requirements-generator.txt
RUN pip install --no-cache-dir -r /tmp/requirements-generator.txt && pip check
WORKDIR /app
ENTRYPOINT ["python", "-m", "src.hospital_sim"]
