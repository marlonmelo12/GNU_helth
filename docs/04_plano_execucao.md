# Plano de Execução Detalhado — Implantação e Integração GNU Health / QIMED

**Versão:** 1.2  
**Data:** 13 de Outubro de 2026  
**Status:** Plano Completo e Auditado com Especificação Técnica do Gerador

---

## 1. Etapas de Execução

### Etapa 1 — Infraestrutura Dedicada para o GNU Health (Zero Impacto no QIMED)
1. **Configuração do Docker Compose Dedicado (`docker-compose.gnuhealth.yml`):**
   * Rede compartilhada: `qimed-network`.
   * Serviço `gnuhealth-db`: Imagem `postgres:16-alpine`, volume dedicado `gnuhealth-postgres-data`, portas `5434:5432`.
   * Serviço `gnuhealth-server`: Imagem Python 3.11 com Trytond 7.0, Tryton-Sao (web client) e módulos do GNU Health HIS, portas `8001:8000`.
2. **Healthcheck e Inicialização da Base:**
   * Script de inicialização da base de dados Tryton com senha de administrador, idioma `pt_BR` e módulos essenciais pré-carregados.

### Etapa 2 — Instalação e Ativação dos Módulos Hospitalares
1. Módulos Assistenciais:
   * `health` (core hospitalar)
   * `health_inpatient` (internações, leitos e enfermarias)
   * `health_lab` (exames laboratoriais e laudos)
   * `health_socioeconomics` (determinantes sociais)
2. Módulos Operacionais e de Apoio:
   * `health_stock` & `stock` (gestão de farmácia, medicamentos, insumos hospitalares e movimentação de estoque)
   * `health_calendar` (gestão de escalas de trabalho, plantões de profissionais e alocação por turno)
3. Parametrização da Instituição de Saúde Fictícia:
   * "Hospital Geral de Ensino QIMED" (CNES fictício: `7654321`).
   * Configuração de especialidades médicas (Clínica Médica, Cardiologia, Cirurgia Geral, Pediatria, UTI).
   * Cadastro de 5 unidades assistenciais / enfermarias e leitos.
   * Cadastro de 3 locais de estoque (Almoxarifado Central, Farmácia Central, Farmácia Satélite UTI).

### Etapa 3 — Cliente Gráfico Oficial (Tryton-Sao Web & Desktop)
1. Ativação do **Tryton-Sao** integrado ao servidor na porta `8001`, permitindo operação gráfica pelo navegador web.
2. Execução de testes de usabilidade com evidências:
   * Login do operador administrativo/médico.
   * Navegação em Pacientes, Consultas, Internações, Farmácia/Estoque e Calendário de Escalas.

### Etapa 4 — Gerador Parametrizável de Dados Hospitalares Sintéticos
1. Implementação do gerador em `src/generators/gnuhealth_synthetic_generator.py` estruturado nas 14 responsabilidades da especificação (`docs/gnuhealth/05_especificacao_gerador.md`):
   * Configuration Manager, Reference Data Loader, Scenario Generator, Demographic Generator, Professional Generator, Clinical Generator, Laboratory Generator, Inpatient Generator, Stock & Pharmacy Generator, Schedule Generator, Persistence Adapter, Provenance Manager, Validation Engine, Execution Reporter.
2. Catálogos reais utilizados:
   * `config/dim_municipios_ibge.parquet` (códigos IBGE de 7 dígitos: Fortaleza `2304400`, Sobral `2312908`).
   * `config/dim_cid10_datasus.parquet` (códigos oficiais CID-10 OMS).
3. Execução em Duas Fases:
   * **Fase A (Validação Rápida):** 200 pacientes, 60 profissionais, 800 atendimentos, 50 internações, 500 exames, 30 medicamentos em estoque e escala semanal.
   * **Fase B (Simulação Hospitalar):** 2.000 pacientes, 60 profissionais, 8.000 atendimentos, 500 internações, 5.000 exames, 100 itens de estoque e escala mensal ininterrupta.

### Etapa 5 — Adaptador de Integração QIMED (`GnuHealthAdapter`)
1. Implementação em `src/ingestion/adapters/gnuhealth_adapter.py`:
   * Herda de `BaseIngestionAdapter`.
   * Métodos: `test_connection()`, `discover_schema()`, `extract()`, `extract_incremental(watermark)`.
   * Extração de entidades assistenciais, estoque e escalas em tabelas Apache Arrow (`pa.Table`).
   * Ingestão na camada Bronze Delta Lake com injeção de metadados técnicos de linhagem.
   * Tratamento de LGPD (`PIIDetector` e `Anonymizer`).

### Etapa 6 — Normalização Canônica e Camada Silver
1. Criação do mapper semântico `src/silver/mappers/gnuhealth_mapper.py`:
   * Transforma tabelas brutas da Bronze nas entidades canônicas do Star Schema:
     - `dim_paciente` (com MPI e pseudonimização HMAC-SHA256).
     - `dim_estabelecimento`.
     - `fct_atendimentos_ambulatoriais`.
     - `fct_internacao`.
     - `dim_medicamento_estoque` / `fct_movimentacao_estoque`.
     - `fct_escala_plantao`.
   * Gravação idempotente com deduplicação por chave primária via `SilverWriter`.

### Etapa 7 — Orquestração via Apache Airflow
1. Criação da DAG `dags/dag_gnuhealth_ingestion.py`:
   * Tarefas:
     - `task_check_availability`: Verifica status da API do GNU Health.
     - `task_extract_to_bronze`: Extração incremental e gravação Delta Bronze (clínica, estoque e escala).
     - `task_transform_to_silver`: Transformação semântica e gravação Delta Silver.
     - `task_quality_audit`: Auditoria forense de integridade e verificação de métricas.
     - `task_notify_completion`: Webhook de finalização do pipeline.

### Etapa 8 — Execução da Suíte Completa de 12 Testes Automatizados
1. **Teste 1 — Validação da Configuração**
2. **Teste 2 — Geração Determinística**
3. **Teste 3 — Integridade Relacional**
4. **Teste 4 — Coerência Temporal**
5. **Teste 5 — Persistência pelo GNU Health**
6. **Teste 6 — Estoque (movimentação e saldo)**
7. **Teste 7 — Escalas (profissionais e plantões)**
8. **Teste 8 — Idempotência (reexecução de lote)**
9. **Teste 9 — Geração Incremental (novo período preservando histórico)**
10. **Teste 10 — Proveniência e Privacidade (LGPD Gate)**
11. **Teste 11 — Integração de Ponta a Ponta (GNU Health -> Bronze -> Silver -> Gold)**
12. **Teste 12 — Recuperação (tolerância a falhas)**

### Etapa 9 — Métricas e Relatório Final
* Consolidação das métricas obrigatórias da especificação técnica em relatório operacional auditável.
