# Contratos de Integração e Mapeamento Canônico — GNU Health para QIMED (Atualizado com Estoque e Escalas)

**Versão:** 1.1  
**Data:** 13 de Outubro de 2026  
**Status:** Especificação Técnica de Contratos Completa

---

## 1. Visão Geral dos Contratos

A integração mapeia tanto os eventos assistenciais quanto os dados operacionais de **suporte hospitalar (estoque de farmácia/insumos e escalas de plantão de profissionais)** do GNU Health para as tabelas do **Star Schema em Português** da camada Silver do QIMED (`src/silver/` e `src/processing/transformations.py`).

---

## 2. Matriz de Mapeamento Canônico Assistencial

### 2.1. Entidade Paciente: `gnuhealth.patient` $\rightarrow$ `dim_paciente`

| Campo Origem (GNU Health) | Tipo Origem | Campo Destino (QIMED Silver) | Tipo Destino | Regra de Transformação / Validação |
|---|---|---|---|---|
| `puid` / `id` | String / Int | `codigo_paciente_origem` | String | Prefixo `'gh_pat_' || id`. Identificador estável do HIS. |
| `name.name` / `name.lastname` | String | `nome_paciente_anonimizado` | String | **LGPD:** HMAC-SHA256 (`QIMED_MPI_SALT`). Nunca gravado em claro. |
| `name.ref` / CPF simulado | String | `pseudonimo_paciente` | String (PK) | Gerado pelo `PatientIdentityResolver` (MPI Nível 1 ou Nível 3). |
| `gender` | Enum ('m', 'f') | `sexo_biologico` | String (1) | Normalização: `'m' -> 'M'`, `'f' -> 'F'`, default `'I'`. |
| `dob` | Date | `data_nascimento_paciente` | Date (`YYYY-MM-DD`) | Validação: data $\le$ data atual e idade $\le$ 130 anos. |
| `address.city` | String | `codigo_municipio_residencia_paciente` | String (6) | Validação via `TerminologyService.normalize_ibge_municipality`. |
| - | - | `origem_registro` | String | Constante `'GNU_HEALTH'`. |
| - | - | `indicador_sintetico` | Boolean | Constante `TRUE`. |
| `write_date` / `create_date` | Timestamp | `data_atualizacao_silver` | Timestamp | Timestamp UTC do processamento. |

---

### 2.2. Entidade Estabelecimento / Unidade: `gnuhealth.institution` $\rightarrow$ `dim_estabelecimento`

| Campo Origem (GNU Health) | Tipo Origem | Campo Destino (QIMED Silver) | Tipo Destino | Regra de Transformação / Validação |
|---|---|---|---|---|
| `name.ref` / CNES | String | `codigo_estabelecimento_cnes` | String (7) (PK) | Código CNES de 7 dígitos atribuído à instituição do teste. |
| `name.name` | String | `nome_razao_social_estabelecimento` | String | Nome fantasia / Razão social da instituição hospitalar fictícia. |
| `institution_type` | String | `tipo_unidade_saude` | String | Normalização para taxonomia SUS (ex.: `'Hospital Geral'`). |
| `address.city` | String | `codigo_municipio_estabelecimento` | String (6) | Resolução de município via dicionário IBGE. |
| `address.subdivision` | String | `sigla_uf_estabelecimento` | String (2) | Validação: UF válida entre as 27 do Brasil. |
| - | - | `indicador_sintetico` | Boolean | Constante `TRUE`. |

---

### 2.3. Entidade Atendimento Ambulatorial: `gnuhealth.appointment` / `gnuhealth.patient.evaluation` $\rightarrow$ `fct_atendimentos_ambulatoriais`

| Campo Origem (GNU Health) | Tipo Origem | Campo Destino (QIMED Silver) | Tipo Destino | Regra de Transformação / Validação |
|---|---|---|---|---|
| `id` / `appointment_id` | String / Int | `id_atendimento_ambulatorial` | String (PK) | Prefixo `'gh_amb_' || id`. |
| `patient.id` | Int | `pseudonimo_paciente` | String (FK) | Chave estrangeira resolvida via `dim_paciente`. |
| `institution.ref` | String | `codigo_estabelecimento_cnes` | String (7) (FK) | CNES da instituição onde o atendimento ocorreu. |
| `appointment_date` | Timestamp | `data_atendimento` | Date | Data extraída em formato ISO (`YYYY-MM-DD`). |
| `specialty.code` | String | `codigo_especialidade` | String | Especialidade médica do atendimento. |
| `healthprof.name.name` | String | `identificador_profissional_hash` | String | HMAC-SHA256 do identificador do profissional. |
| `chief_complaint` | String | `motivo_consulta` | String | Sanitização de texto. |
| `primary_condition.code` | String | `codigo_cid10_principal` | String (4) | Validação e normalização via `TerminologyService.normalize_cid10`. |
| - | - | `indicador_sintetico` | Boolean | Constante `TRUE`. |

---

### 2.4. Entidade Internação Hospitalar: `gnuhealth.inpatient.registration` $\rightarrow$ `fct_internacao`

| Campo Origem (GNU Health) | Tipo Origem | Campo Destino (QIMED Silver) | Tipo Destino | Regra de Transformação / Validação |
|---|---|---|---|---|
| `id` | Int | `id_internacao_hospitalar` | String (PK) | Prefixo `'gh_int_' || id`. |
| `registration_code` | String | `numero_aih` | String (13) | Número sintético gerado com prefixo controlado (ex.: `'99' || zfill(11)`). |
| `patient.id` | Int | `pseudonimo_paciente` | String (FK) | Chave estrangeira ligada à `dim_paciente`. |
| `hospitalization_date` | Timestamp | `data_internacao` | Date | Início da internação (`YYYY-MM-DD`). |
| `discharge_date` | Timestamp | `data_alta` | Date | Término da internação. Validação: `data_alta >= data_internacao`. |
| - | - | `dias_permanencia_real` | Integer | Diferença em dias: `(data_alta - data_internacao)`. |
| `discharge_reason` | String | `motivo_saida_permanencia` | String | Normalização para códigos canônicos (ex.: `'ALTA_CURADO'`, `'OBITO'`). |
| `primary_condition.code` | String | `codigo_cid10_principal` | String (4) | Validação contra tabela mestre CID-10 OMS. |
| `bed.name` | String | `identificador_leito` | String | Código ou número do leito hospitalar. |
| `bed.bed_type` | String | `tipo_leito` | String | Ex.: `'ENFERMARIA'`, `'UTI'`, `'CLINICO'`. |
| - | - | `valor_total_brl` | Double | Custo estimado da internação. |
| - | - | `indicador_sintetico` | Boolean | Constante `TRUE`. |

---

## 3. Matriz de Mapeamento Canônico Operacional (Estoque & Escalas)

### 3.1. Entidade Estoque & Farmácia: `gnuhealth.medicament` / `stock.move` $\rightarrow$ `dim_medicamento_estoque` / `fct_movimentacao_estoque`

| Campo Origem (GNU Health) | Tipo Origem | Campo Destino (QIMED Silver) | Tipo Destino | Regra de Transformação / Validação |
|---|---|---|---|---|
| `medicament.id` | Int | `id_medicamento` | String (PK) | Prefixo `'gh_med_' || id`. |
| `name.name` | String | `nome_medicamento_principio_ativo` | String | Nome comercial e químico (ex.: `'Dipirona 500mg/mL'`). |
| `category.name` | String | `categoria_farmacologica` | String | Ex.: `'Analgésico'`, `'Antibiótico'`, `'Insumo Descartável'`. |
| `stock_location.name` | String | `local_estoque` | String | Ex.: `'Farmácia Central'`, `'Almoxarifado Geral'`, `'Farmácia Satélite UTI'`. |
| `quantity` | Float | `quantidade_disponivel` | Float | Saldo físico atual em estoque. Validação: $\ge 0$. |
| `uom.name` | String | `unidade_medida` | String | Ex.: `'Ampola'`, `'Frasco'`, `'Comprimido'`, `'Unidade'`. |
| `move.effective_date` | Date | `data_movimentacao` | Date | Data em que a movimentação/dispensação ocorreu. |
| `inpatient_registration.id` | Int | `id_internacao_hospitalar` | String (FK) | Chave estrangeira que vincula a dispensação à internação que consumiu o item. |
| - | - | `indicador_sintetico` | Boolean | Constante `TRUE`. |

---

### 3.2. Entidade Escala de Funcionários: `health_calendar.schedule` / `healthprofessional` $\rightarrow$ `fct_escala_plantao`

| Campo Origem (GNU Health) | Tipo Origem | Campo Destino (QIMED Silver) | Tipo Destino | Regra de Transformação / Validação |
|---|---|---|---|---|
| `schedule.id` | Int | `id_escala_plantao` | String (PK) | Prefixo `'gh_esc_' || id`. |
| `healthprof.id` | Int | `identificador_profissional_hash` | String (FK) | HMAC-SHA256 (`QIMED_MPI_SALT`) do ID do profissional. |
| `healthprof.specialty.name`| String | `especialidade_profissional` | String | Especialidade médica ou categoria (Enfermeiro, Médico Intensivista, etc.). |
| `unit_service.name` | String | `setor_alocacao` | String | Ex.: `'UTI Adulto'`, `'Pronto Socorro'`, `'Centro Cirúrgico'`. |
| `start_time` | Timestamp | `inicio_plantao` | Timestamp | Horário de início do turno (ex.: `2026-10-01 07:00:00`). |
| `end_time` | Timestamp | `fim_plantao` | Timestamp | Horário de término do turno. Validação: `fim_plantao > inicio_plantao`. |
| `shift_type` | Enum / String | `tipo_turno` | String | Ex.: `'DIURNO_12H'`, `'NOTURNO_12H'`, `'AMBULATORIAL_4H'`. |
| `status` | String | `status_escala` | String | Ex.: `'CONFIRMADO'`, `'CUMPRIDO'`, `'SUBSTITUIDO'`. |
| - | - | `indicador_sintetico` | Boolean | Constante `TRUE`. |

---

## 4. Gestão de Estado Incremental e Watermarks

A extração respeitará o modelo de persistência de estado do QIMED na tabela `pipeline_state`:

* **`pipeline_id`**: `'gnuhealth_lakehouse_pipeline'`
* **`connection_id`**: `'conn_gnuhealth_main'`
* **`source`**: `'gnuhealth'`
* **`strategy`**: `'TIMESTAMP'`
* **`last_successful_watermark`**: Timestamp ISO 8601 da última alteração (`write_date`) extraída com sucesso para cada partição/entidade.
