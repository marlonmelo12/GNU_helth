FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

# Instala dependências do sistema necessárias para compilação e cliente PostgreSQL
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    libpq-dev \
    gcc \
    build-essential \
    libc6-dev \
    libxml2-dev \
    libxslt1-dev \
    tar \
    git \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

# Baixa, descompacta e compila dependências do cliente gráfico web oficial (Tryton-Sao 7.0)
RUN mkdir -p /var/www/sao \
    && curl -sSL https://downloads.tryton.org/7.0/tryton-sao-last.tgz | tar -xz -C /var/www/sao --strip-components=1 \
    && cd /var/www/sao \
    && echo '{"allow_root": true}' > .bowerrc \
    && npm install --production --legacy-peer-deps

# Instala Trytond 7.0 LTS, Proteus, GNU Health 5.0 e os módulos hospitalares essenciais
RUN pip install --no-cache-dir \
    psycopg2-binary \
    bcrypt \
    pytz \
    "trytond>=7.0,<7.1" \
    "proteus>=7.0,<7.1" \
    "gnuhealth>=5.0,<5.1" \
    "gnuhealth-inpatient>=5.0,<5.1" \
    "gnuhealth-lab>=5.0,<5.1" \
    "gnuhealth-stock>=5.0,<5.1" \
    "gnuhealth-calendar>=5.0,<5.1" \
    "gnuhealth-socioeconomics>=5.0,<5.1" \
    "trytond-party>=7.0,<7.1" \
    "trytond-company>=7.0,<7.1" \
    "trytond-currency>=7.0,<7.1" \
    "trytond-country>=7.0,<7.1" \
    "trytond-stock>=7.0,<7.1"

# Copia configurações e script de entrada
COPY config/gnuhealth/trytond.conf /etc/trytond.conf
COPY docker/gnuhealth/entrypoint.sh /entrypoint.sh
# remove CR de checkouts Windows (autocrlf) para o shebang funcionar
RUN sed -i 's/\r$//' /entrypoint.sh && chmod +x /entrypoint.sh && mkdir -p /var/lib/trytond/db

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
