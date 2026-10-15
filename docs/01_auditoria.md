# Auditoria Técnica do Repositório e Ambiente — QIMED Pipeline & GNU Health

**Data da Auditoria:** 13 de Outubro de 2026  
**Ambiente de Execução:** Windows 10/11 (AMD64) com Docker Desktop 4.92.0 (Engine 29.8.0, Contexto `desktop-linux`, WSL2 Backend).  
**Escopo:** Avaliação completa de conformidade arquitetural, recursos computacionais, infraestrutura de containers, contratos de dados e diagnóstico de erros preliminares.

---

## 1. Fatos Verificados

### 1.1. Diagnóstico do Erro do Airflow Relatado pelo Usuário
* **Erro observado:**  
  `airflow command error: argument GROUP_OR_COMMAND: invalid choice: '/home/airflow/.local/bin/pytest' (choose from 'cheat-sheet', 'config', 'connections', ...)`
* **Causa Raiz Comprovada:**  
  A imagem base oficial do Airflow (`apache/airflow:2.10.5-python3.11`) define o entrypoint `/entrypoint`. Quando um comando é passado sem prefixo explícito (`docker compose exec airflow-webserver /home/airflow/.local/bin/pytest` ou similar), o entrypoint assume que o primeiro argumento é um subcomando do executável `airflow`, invocando internamente:
  ```bash
  airflow /home/airflow/.local/bin/pytest
  ```
  Como `pytest` não é um subcomando CLI do Airflow, o CLI aborta com o erro relatado.
* **Solução Comprovada:**  
  A execução correta de testes e scripts arbitrários no container do Airflow requer a invocação via `bash -c`:
  ```bash
  docker compose run --rm airflow-webserver bash -c "pytest tests/test_naming.py"
  ```
  O teste foi executado e passou com 100% de sucesso.

### 1.2. Recursos de Hardware e Ambiente Host
* **CPU:** 20 núcleos lógicos disponíveis no Docker Desktop.
* **Memória RAM:** 11.44 GB alocados para o Docker Engine.
* **Armazenamento em Disco Host (C:):** 140.45 GB livres (348.2 GB usados de ~499 GB).
* **Python no Host:** Python 3.11.9 (`C:\Program Files\Python311\python.exe`) com `pytest 9.1.1` instalado (sem `deltalake` nativo no host Windows; o runtime completo com dependências reside dentro do container Docker).

### 1.3. Portas de Rede Locais
* **Porta 5433 (Host) -> 5432 (Container):** PostgreSQL 13 do QIMED (`qimed_pipeline-postgres-1`). **A porta 5432 no host está livre**.
* **Porta 8000 (Host):** Ocupada pelo `qimed-api` (`qimed_pipeline-qimed-api-1`).
* **Porta 9000 / 9001 (Host):** MinIO S3 API e MinIO Console Web (`qimed-minio`).
* **Porta 8088 (Host) -> 8080 (Container):** Reservada no `docker-compose.yml` para o `airflow-webserver`.

### 1.4. Serviços de Infraestrutura QIMED Ativos
1. **`qimed_pipeline-postgres-1` (postgres:13):**
   * Estado: `Up` (healthy) na porta 5433 (externa) e rede `qimed-network`.
   * Base `airflow` contém 52 tabelas: tabelas operacionais do Airflow 2.10.5 + tabelas de controle do QIMED (`pipeline_state`, `upload_metadata`, `jobs`, `runs`, `alembic_version`).
2. **`qimed-minio` (minio/minio:latest):**
   * Estado: `Up` (healthy) nas portas 9000 e 9001.
   * Bucket `qimed-lakehouse` criado e configurado.
3. **`qimed_pipeline-qimed-api-1`:**
   * Estado: `Up` na porta 8000 (FastAPI).
4. **`airflow-webserver` e `airflow-scheduler`:**
   * Configurados no `docker-compose.yml`, utilizam a rede `qimed-network`.

### 1.5. Camadas do Lakehouse e Armazenamento
* **Bronze:** Delta Lake particionado (`s3://qimed-lakehouse/bronze` ou local `lakehouse/bronze`). Gerenciado por `src/lakehouse/bronze_writer.py` e `src/ingestion/staging_writer.py`.
* **Silver:** Delta Lake transacional (`s3://qimed-lakehouse/silver` ou local `lakehouse/silver`). Tabelas canônicas: `dim_paciente`, `dim_estabelecimento`, `dim_operadoras_saude`, `dim_tempo`, `fct_internacao`, `fct_atendimentos_ambulatoriais`, `fct_glosas_hospitalares`, `fct_ressarcimento_sus`.
* **Gold / DW:** DuckDB Data Warehouse localizado em `warehouse/qimed_dw.duckdb` (334 MB, materializado e versionado via Git LFS). Gerenciado por `src/dw/dw_manager.py` e `src/gold/`.

### 1.6. Requisitos Oficiais do GNU Health HIS
* **Versão de Referência:** GNU Health HIS 5.0 (ou 4.4 LTS).
* **RDBMS Backend:** PostgreSQL estritamente $\ge$ 15.x (requer UTF-8 e recursos incompatíveis com PostgreSQL 13).
* **Framework ERP:** Tryton 7.0 LTS (Python 3.10+).
* **Cliente Gráfico Oficial:** `tryton` / `gnuhealth-client` baseado em PyGObject / GTK.

---

## 2. Decisões de Implementação

1. **Isolamento Estrito do Banco de Dados:**
   * O GNU Health HIS **não** utilizará o banco de dados PostgreSQL 13 existente do Airflow/QIMED.
   * Será provisionado um serviço PostgreSQL 16 dedicado (`gnuhealth-db`) na mesma rede Docker (`qimed-network`), com persistência em volume isolado (`gnuhealth-db-data`) e porta interna 5432 (mapeada para porta externa 5434 no host, caso necessário).
2. **Porta do Servidor GNU Health:**
   * Como a porta 8000 do host já está ocupada pelo `qimed-api`, o serviço do GNU Health Server (`trytond`) escutará internamente na porta padrão 8000, mapeada no host para a porta `8001` (ou `8069`).
3. **Mecanismo de Execução do Cliente Gráfico Oficial:**
   * No ambiente host Windows, o cliente oficial do GNU Health pode ser conectado diretamente ao servidor em `localhost:8001`, ou através de container dedicado com interface gráfica web/X11 (sem instalação de cliente pesado no host).

---

## 3. Hipóteses

1. A geração de dados sintéticos para o GNU Health deve contemplar as entidades centrais do modelo hospitalar oficial: Pacientes (`gnuhealth.patient`), Profissionais (`gnuhealth.healthprofessional`), Unidades/Instituições (`gnuhealth.institution`), Atendimentos/Encontros Clínicos (`gnuhealth.appointment` ou `gnuhealth.patient.evaluation`), Internações (`gnuhealth.inpatient.registration`) e Exames/Laboratório (`gnuhealth.lab.test`).
2. A extração dos dados hospitalares do GNU Health pode ser realizada de forma estruturada e idempotente através da camada de serviços Tryton (`proteus` / Python API oficial do Trytond) ou via consultas SQL somente-leitura com isolamento de transação, mapeando os registros para o formato PyArrow / Delta Lake da Bronze.

---

## 4. Riscos e Mitigações

| Risco | Impacto | Mitigação |
|---|---|---|
| Colisão de portas de rede (8000 e 5432) | Médio | Manter `qimed-api` na 8000 e mapear GNU Health para 8001. Mapear PostgreSQL 16 do ERP para 5434. |
| Incompatibilidade de versão de PostgreSQL | Alto | PostgreSQL 13 do QIMED mantido intacto. GNU Health recebe PostgreSQL 16 dedicado. |
| Degradação de memória RAM do Docker | Médio | Limitar recursos do container GNU Health a 2 GB RAM e 2 vCPUs; Docker possui 11.44 GB alocados. |
| Concorrência no Delta Lake Bronze | Baixo | Uso do `LockManager` existente do QIMED (`src/ingestion/lock_manager.py`) para partição GNU Health. |
| Mistura de dados sintéticos com reais | Crítico | Tags estritas de proveniência (`_source_type = 'gnuhealth_synthetic'`, `is_synthetic = True`, lote e hash de controle). |

---

## 5. Pendências

1. Confirmação do modo de operação preferido para o cliente gráfico oficial (Desktop no Windows host vs. Containerizado com interface gráfica via navegador).
2. Confirmação do volume definitivo de dados sintéticos para o primeiro lote de homologação (ex.: 2.000 pacientes, 8.000 atendimentos ou lote reduzido de aquecimento).

---

## 6. Itens que Dependem de Autorização

* **Adição do serviço GNU Health ao `docker-compose.yml` (ou em `docker-compose.gnuhealth.yml` complementar acoplado à rede `qimed-network`).**  
  *Justificativa:* Preserva o arquivo original sem riscos de regressão no ambiente de produção/CI do QIMED.
