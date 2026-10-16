# Homologação do ERP (GNU Health) e do hospital simulado

Roteiro validado em 16/10/2026, em Windows 11 + Docker Desktop, partindo de uma máquina sem
nenhum container ou volume do ERP. Tempo total: cerca de 15 minutos, a maior parte no primeiro build.

## Pré-requisitos

- Docker Desktop com pelo menos 4 GB de memória para os containers.
- Git.
- Portas **8001** (ERP) e **5434** (Postgres do ERP) livres.

Os comandos funcionam iguais no PowerShell, no cmd e no bash.

## 1. Obter o código

```bash
git clone https://github.com/marlonmelo12/GNU_helth.git
cd GNU_helth
git checkout homologacao/hospital-simulado-v2
```

## 2. Subir o ERP com a base pré-carregada

```bash
# imagem do servidor (primeira vez: ~6 min)
docker compose build gnuhealth-server

# banco de dados
docker compose up -d gnuhealth-db
docker compose ps            # aguarde gnuhealth-db "healthy"

# carregar a base de demonstração (dump PostgreSQL versionado no repositório)
docker compose cp data/gnuhealth_backup_20261014.dump gnuhealth-db:/tmp/erp.dump
docker compose exec gnuhealth-db pg_restore -U gnuhealth -d gnuhealth --no-owner --exit-on-error /tmp/erp.dump

# servidor (na primeira subida ele atualiza os módulos: ~3 min)
docker compose up -d gnuhealth-server
docker compose ps            # aguarde gnuhealth-server "healthy"
```

## 3. Acessar

- Endereço: http://localhost:8001/
- Banco: `gnuhealth` · Usuário: `admin` · Senha: `admin` (apenas ambiente local)

## 4. O que conferir

| Menu | Esperado na base de demonstração |
|---|---|
| Saúde > Pacientes | 1.905 pacientes |
| Saúde > Internações | 548 internações, com leito e motivo de alta |
| Estoque > Movimentações | 2.057 movimentações |
| Calendário > Eventos | 1.800 plantões médicos e de enfermagem |

Conferência rápida pelo banco, sem abrir a interface:

```bash
docker compose exec gnuhealth-db psql -U gnuhealth -d gnuhealth -c "select count(*) from gnuhealth_patient"
```

## 5. Hospital simulado v2 (gerador + verificação)

O gerador cria a operação de um mês do hospital (escala, internações, prescrições e estoque)
calibrada pelo Hospital Regional Norte (Sobral/CE). O lote só é aprovado se passar nas 23 regras
de consistência.

```bash
docker compose --profile tools build hospital-sim

# porte médio (139 leitos), maio/2026: ~9 min
docker compose --profile tools run --rm hospital-sim gerar --inicio 2026-05-01 --fim 2026-05-31 --semente 42 --escala-porte 0.4 --saida data/lotes_v2/hrn_medio_202605

# relatório das regras (código de saída 0 = aprovado)
docker compose --profile tools run --rm hospital-sim verificar --lote data/lotes_v2/hrn_medio_202605
# abrir data/lotes_v2/hrn_medio_202605/relatorio_invariantes.md

# o lote do gerador antigo deve ser REPROVADO (prova de que as regras detectam os defeitos)
docker compose --profile tools run --rm hospital-sim verificar --lote data/synthetic_output/batch_fase_b_v1

# testes automatizados do gerador (~4 min)
docker compose --profile tools run --rm --entrypoint python hospital-sim -m pytest -q tests/test_hospital_sim.py
```

A mesma semente sempre gera o mesmo lote. Sem `--escala-porte`, o hospital tem o porte real
(345 leitos) e a geração leva cerca de 12 min.

## 6. Encerrar

```bash
docker compose down        # para os containers e mantém os dados
docker compose down -v     # para e APAGA a base do ERP (para refazer do zero)
```

## Limites desta versão

- A base do ERP vem do dump de demonstração, gerado pelo gerador antigo. A carga dos lotes v2 no
  ERP pelo ORM é a fase 3 e ainda não está pronta. Por isso o passo 5 valida o gerador fora do
  ERP.
- O aviso `a network with name qimed_pipeline_qimed-network exists` aparece quando o
  `qimed_pipeline` também está rodando na máquina. É inofensivo.
