# GNU Health HIS 5.0 — Sistema Hospitalar & Gerador Clínico Sintético

Este repositório contém a implantação completa, conteinerizada e autônoma do **GNU Health Hospital Information System (HIS) 5.0** baseado no framework **Tryton 7.0 LTS** e **PostgreSQL 16**, incluindo:

1. **Infraestrutura Docker Completa**: Servidor GNU Health HIS com cliente oficial web (Tryton-Sao) e banco relacional isolado.
2. **Interface Gráfica Web Oficial (Tryton-Sao)**: Acessível na porta `8001` sem necessidade de bibliotecas gráficas nativas X11/GTK.
3. **Escopo Clínico e Operacional Hospitalar**:
   * Pacientes, Dados Demográficos e PUID único
   * Consultas Ambulatoriais e Agendamentos
   * Internações Hospitalares, Gestão de Enfermarias e Leitos
   * Exames Laboratoriais (Hemograma CBC e Bioquímica RFT)
   * Estoque & Farmácia (`gnuhealth-stock`, controle de lotes e dispensações)
   * Escala de Plantão e RH (`health_calendar`, escalas médicas e de enfermagem de 12h/12h)
4. **Gerador Parametrizável de Dados Hospitalares Sintéticos**: Geração determinística e consistente (`gnuhealth_synthetic_generator.py`) com códigos oficiais CID-10 e municípios IBGE.
5. **Carga Oficial via ORM Proteus**: Carregador de alta performance (`gnuhealth_erp_loader.py`) respeitando 100% das restrições e regras de negócio do Tryton.
6. **Scripts de Higienização e Reparo**: Auditoria cirúrgica de leitos, cancelamento pós-óbito e reconciliação de estoques (`repair_gnuhealth_erp.py`).
7. **Dumps e Backups Pré-Populados**: Dumps PostgreSQL prontos para restauração imediata (`data/gnuhealth_backup_*.dump`).
8. **Documentação de Arquitetura e Engenharia**: Manuais completos em `docs/`.

---

## 1. Estrutura do Repositório

```text
GNU_helth/
├── docker-compose.yml              # Orquestração dos contêineres HIS + PostgreSQL
├── Dockerfile                      # Imagem GNU Health Server + Trytond + Sao Web GUI
├── docker/
│   └── gnuhealth/
│       ├── Dockerfile              # Dockerfile de produção
│       └── entrypoint.sh           # Inicialização e auto-instalação de módulos
├── config/
│   ├── gnuhealth/trytond.conf      # Configurações do servidor Trytond
│   └── dim_cid10_datasus.json      # Catálogo oficial de patologias CID-10 OMS
├── src/
│   └── generators/
│       ├── gnuhealth_synthetic_generator.py # Gerador de dados clínicos sintéticos
│       └── gnuhealth_erp_loader.py          # Loader oficial via Proteus ORM
├── scripts/
│   ├── load_cid10_gnuhealth.py     # Carga de catálogo CID-10 no ERP
│   ├── repair_gnuhealth_erp.py     # Higienização e auditoria transacional
│   └── sync_nursing_shifts.py      # Sincronizador de escalas de enfermagem
├── data/
│   ├── gnuhealth_backup_20261013.dump # Dump relacional PostgreSQL Fase A
│   ├── gnuhealth_backup_20261014.dump # Dump relacional PostgreSQL Fase B
│   └── synthetic_output/              # Datasets JSON gerados
├── docs/                           # Documentação arquitetural detalhada
└── tests/                          # Suíte de testes de integridade e regras
```

---

## 2. Início Rápido (Quickstart)

### 2.1. Subir os Contêineres

```bash
docker compose up -d
```

Os serviços expostos são:
* **GNU Health HIS Web GUI (Tryton-Sao)**: `http://localhost:8001/`
* **GNU Health PostgreSQL DB**: `localhost:5434` (Porta interna 5432)

### 2.2. Acesso à Interface Gráfica

* **URL**: [http://localhost:8001/](http://localhost:8001/)
* **Banco de Dados (Database)**: `gnuhealth`
* **Usuário**: `admin`
* **Senha**: `admin`

---

## 3. Geração e Carga de Dados Sintéticos

### 3.1. Gerar Dataset Clínico

Gere um lote clínico determinístico com o perfil desejado (`fase_a` para validação rápida ou `fase_b` para volume médio):

```bash
python src/generators/gnuhealth_synthetic_generator.py --profile fase_a --batch-id batch_fase_a_v1
```

### 3.2. Carregar no ERP via Proteus ORM

Execute o carregador dentro do contêiner do GNU Health:

```bash
docker exec -e PYTHONPATH=/app qimed-gnuhealth-server python /app/src/generators/gnuhealth_erp_loader.py --batch-dir /app/data/synthetic_output/batch_fase_a_v1
```

---

## 4. Restauração de Backup (Dump PostgreSQL)

Para restaurar um dos backups pré-populados diretamente no contêiner:

```bash
# Restaurar o dump de produção
docker exec -i qimed-gnuhealth-db pg_restore -U gnuhealth -d gnuhealth --clean --if-exists /app/data/gnuhealth_backup_20261014.dump
```

---

## 5. Scripts de Reparo e Manutenção

Para rodar uma auditoria e higienização das regras de negócio (cancelamento de consultas pós-óbito, ajuste de saldos de estoque e correção de sobreposição de leitos):

```bash
# Modo simulação (dry-run)
python scripts/repair_gnuhealth_erp.py --dry-run

# Modo aplicação
python scripts/repair_gnuhealth_erp.py --apply
```

---

## 6. Testes Automatizados

Para executar os testes de validação dos geradores, integridade relacional e regras do GNU Health:

```bash
python -m pytest tests/ -v
```
