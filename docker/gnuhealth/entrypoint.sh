#!/bin/bash
set -e

echo "=== [GNU HEALTH] Iniciando contêiner do GNU Health HIS ==="

ADMIN_PASSWORD="${TRYTON_ADMIN_PASSWORD:-admin}"
DB_NAME="${TRYTON_DB_NAME:-gnuhealth}"
CONF_FILE="/etc/trytond.conf"

echo "=== [GNU HEALTH] Aguardando PostgreSQL em gnuhealth-db:5432 ==="
python3 -c "
import socket, time, sys
for i in range(40):
    try:
        s = socket.create_connection(('gnuhealth-db', 5432), 2)
        s.close()
        print('PostgreSQL disponível!')
        sys.exit(0)
    except Exception:
        time.sleep(2)
sys.exit(1)
"

# Configuração da senha não-interativa do admin
PASSFILE="/tmp/tryton_admin_pass"
echo -n "${ADMIN_PASSWORD}" > "${PASSFILE}"
chmod 600 "${PASSFILE}"
export TRYTONPASSFILE="${PASSFILE}"

echo "=== [GNU HEALTH] Inicializando / Atualizando base de dados '${DB_NAME}' ==="
trytond-admin -c "${CONF_FILE}" -d "${DB_NAME}" --all --activate-dependencies \
    -u health health_inpatient health_lab health_stock health_calendar health_socioeconomics \
    --email admin@qimed.local -p -v || true

rm -f "${PASSFILE}"

echo "=== [GNU HEALTH] Iniciando Servidor Trytond (HTTP / Web Sao / JSON-RPC) ==="
exec trytond -c "${CONF_FILE}" -d "${DB_NAME}"
