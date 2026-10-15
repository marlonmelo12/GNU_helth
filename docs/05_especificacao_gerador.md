# Especificação Técnica Obrigatória — Gerador Parametrizável de Dados Hospitalares Sintéticos do GNU Health

**Versão:** 1.0  
**Data:** 13 de Outubro de 2026  
**Status:** Especificação Técnica Homologada para Implementação

---

## 1. Objetivo e Responsabilidade

Implementar um gerador parametrizável de dados hospitalares sintéticos integrado ao GNU Health HIS e ao pipeline QIMED.

O componente simula a operação de um hospital geral, produzindo um ecossistema de dados demográficos, clínicos, administrativos e operacionais coerente, persistente e rastreável.

O gerador não se limita a produzir arquivos CSV, JSON ou Parquet. Sua função principal é criar e relacionar registros no GNU Health por meio dos mecanismos oficiais de aplicação, utilizando **Proteus** quando compatível com os modelos, os serviços e a versão efetivamente instalados.

A implementação respeita as regras de negócio do ERP, as validações dos modelos, as permissões e a integridade referencial.

Posteriormente, os registros são extraídos e processados pelo pipeline QIMED, utilizando os contratos, os adaptadores e os mecanismos de rastreabilidade já existentes.

**Princípio fundamental:** o GNU Health é o sistema operacional de origem dos dados hospitalares sintéticos; o QIMED é responsável por ingerir, validar, transformar, rastrear e disponibilizar esses dados conforme sua arquitetura existente.

---

## 2. Auditoria de Compatibilidade Prévia

Antes da escrita do gerador, foram auditados e verificados:
1. GNU Health HIS versão 5.0 sobre Tryton 7.0 LTS e Python 3.11.
2. Biblioteca oficial `proteus` compatível com Tryton 7.0.
3. Módulos hospitalares: `health`, `health_inpatient`, `health_lab`, `health_socioeconomics`, `health_stock`, `health_calendar`.
4. Modelos e relacionamentos: `gnuhealth.patient`, `gnuhealth.healthprofessional`, `gnuhealth.institution`, `gnuhealth.appointment`, `gnuhealth.inpatient.registration`, `gnuhealth.lab.test`, `gnuhealth.medicament`, `stock.move`, `health_calendar.schedule`.
5. Autenticação oficial JSON-RPC/HTTP sobre a porta do Trytond.
6. Catálogos clínicos no repositório:
   * Municípios: `config/dim_municipios_ibge.parquet` (códigos oficiais IBGE de 6 e 7 dígitos).
   * Diagnósticos: `config/dim_cid10_datasus.parquet` (tabela de códigos CID-10 OMS da DATASUS).
7. Gateway LGPD do QIMED: `PIIDetector` (`config/pii_manifest.yaml`), `Anonymizer` (`SALT_SECRET`) e `PatientIdentityResolver` (`QIMED_MPI_SALT`).
8. Contratos canônicos da Silver: `dim_paciente`, `dim_estabelecimento`, `fct_atendimentos_ambulatoriais`, `fct_internacao`, `dim_medicamento_estoque`, `fct_escala_plantao`.

---

## 3. Interface de Execução e Parâmetros

### 3.1. Parâmetros Obrigatórios da CLI

| Parâmetro | Tipo | Padrão | Finalidade |
|---|---|---|---|
| `--seed` | Inteiro | `42` | Controlar a geração pseudoaleatória |
| `--patients` | Inteiro | 200 na Fase A; 2.000 na Fase B | Quantidade de pacientes |
| `--professionals` | Inteiro | 60 | Quantidade de profissionais |
| `--encounters` | Inteiro | 800 na Fase A; 8.000 na Fase B | Quantidade de atendimentos |
| `--inpatients` | Inteiro | 50 na Fase A; 500 na Fase B | Quantidade de internações |
| `--labs` | Inteiro | 500 na Fase A; 5.000 na Fase B | Quantidade de solicitações ou registros laboratoriais |
| `--stock-items` | Inteiro | 30 na Fase A; 100 na Fase B | Quantidade de tipos de medicamentos e insumos |
| `--start-date` | Data | `2026-01-01` | Início do período clínico |
| `--end-date` | Data | `2026-10-01` | Fim do período clínico |
| `--batch-id` | String | Identificador determinístico | Identificar a execução e a proveniência |

* **Fase A — Validação Inicial:** Volume reduzido para testar os modelos, relacionamentos, validações e o caminho de integração ponta a ponta.
* **Fase B — Simulação Hospitalar:** Volume médio completo para benchmark operacional e ingestão no Lakehouse.

### 3.2. Regras de Validação dos Parâmetros
Antes de executar qualquer escrita no GNU Health:
- Quantidades devem ser inteiros não negativos.
- Formato de datas estritamente `YYYY-MM-DD`.
- Rejeição obrigatória se `start-date > end-date`.
- Validação de formato e unicidade do `batch-id`.
- Teste prévio de conectividade com o GNU Health.
- Verificação se o lote já existe (idempotência).

### 3.3. Interface Programática
```python
from src.generators.gnuhealth_synthetic_generator import GeneratorConfig, GnuHealthSyntheticGenerator

config = GeneratorConfig(
    seed=42,
    patients=200,
    professionals=60,
    encounters=800,
    inpatients=50,
    labs=500,
    stock_items=30,
    start_date="2026-01-01",
    end_date="2026-10-01",
    batch_id="batch_20261013_v1",
)

generator = GnuHealthSyntheticGenerator()
result = generator.run(config)
```

---

## 4. Arquitetura Interna do Gerador (14 Responsabilidades)

1. **Configuration Manager:** Valida parâmetros e carrega opções.
2. **Reference Data Loader:** Carrega `dim_municipios_ibge.parquet` e `dim_cid10_datasus.parquet`.
3. **Scenario Generator:** Define cenários hospitalares e regras de negócio.
4. **Demographic Generator:** Gera pacientes, CPFs sintéticos controlados e datas de nascimento coerentes.
5. **Professional Generator:** Gera 60 profissionais, especialidades, registros e vínculos.
6. **Clinical Generator:** Gera consultas ambulatoriais, atendimentos de emergência e queixas com CID-10.
7. **Laboratory Generator:** Gera solicitações laboratoriais, exames e resultados numéricos com unidades reais.
8. **Inpatient Generator:** Gera internações, leitos, evolução temporal e desfechos clínicos (alta/óbito).
9. **Stock and Pharmacy Generator:** Gera catálogo de produtos, 3 locais de estoque e movimentações reais de dispensação.
10. **Schedule Generator:** Gera escalas de plantão (diurno 07h-19h, noturno 19h-07h, ambulatório) e alocação por setor.
11. **GNU Health Persistence Adapter:** Persiste os registros utilizando a API oficial do Proteus/Tryton.
12. **Provenance Manager:** Injeta metadados de lote, origem sintética e rastreabilidade.
13. **Validation Engine:** Valida integridade referencial, limites biológicos e consistência temporal.
14. **Execution Reporter:** Gera logs estruturados, métricas e relatório de execução.

---

## 5. Regras de Realismo Clínico e Operacional

* **Território:** Códigos de 7 dígitos do IBGE (`config/dim_municipios_ibge.parquet`), ex.: Fortaleza (`2304400`), Sobral (`2312908`).
* **Diagnósticos:** Códigos válidos da CID-10 OMS (`config/dim_cid10_datasus.parquet`), ex.: `J18`, `I10`, `K35`.
* **Internações:** Exigência estrita de $\text{data de admissão} < \text{data de alta}$. Permanência calibrada por cenário clínico.
* **Estoque:** Três locais físicos (Almoxarifado Central, Farmácia Central, Farmácia Satélite UTI). Consumo vinculado a internações com movimentações reais e controle de saldo não negativo.
* **Escalas:** Turnos diurnos e noturnos. Validação cruzada obrigatória: o profissional associado ao atendimento ou à internação deve estar efetivamente escalado naquele setor e horário.
* **LGPD Gate:** Tratamento obrigatório pelo `PIIDetector` e `Anonymizer` com `SALT_SECRET` e `QIMED_MPI_SALT`.

---

## 6. Plano de Testes Automatizados (12 Testes Obrigatórios)

1. **Teste 1 — Validação da Configuração:** Parâmetros inválidos rejeitados sem iniciar escrita.
2. **Teste 2 — Geração Determinística:** Mesma semente gera registros logicamente idênticos.
3. **Teste 3 — Integridade Relacional:** Zero referências órfãs entre pacientes, profissionais, atendimentos e leitos.
4. **Teste 4 — Coerência Temporal:** Validação estrita de sequências temporais (nascimento < atendimento < internação < alta).
5. **Teste 5 — Persistência pelo GNU Health:** Registros persistidos e consultáveis via API oficial.
6. **Teste 6 — Estoque:** Movimentações atualizam saldos reais e permanecem rastreáveis.
7. **Teste 7 — Escalas:** Associações respeitam turnos, horários e setores alocados.
8. **Teste 8 — Idempotência:** Reexecução do mesmo lote não duplica registros nem repete débitos de estoque.
9. **Teste 9 — Geração Incremental:** Novo período adiciona apenas novos eventos sem corromper o histórico anterior.
10. **Teste 10 — Proveniência e Privacidade:** Metadados preservados, gateway LGPD validado sem vazamento de segredos.
11. **Teste 11 — Integração de Ponta a Ponta:** Evento criado no GNU Health flui até as camadas Bronze e Silver do QIMED.
12. **Teste 12 — Recuperação:** Interrupção controlada de lote é retomada com integridade.
