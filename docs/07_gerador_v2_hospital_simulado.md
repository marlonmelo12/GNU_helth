# Gerador v2 — hospital simulado calibrado (fases 1 e 2)

O gerador v2 (`src/hospital_sim`) substitui o gerador v1 como fonte de dados do ERP de prova.
Ele simula a operação de um hospital calibrado pelos dados públicos do **Hospital Regional Norte
(Sobral/CE, CNES 6848710)** já carregados no QIMED. Cada lote só segue para o ERP se passar
em todas as invariantes.

## Como rodar

```powershell
docker compose --profile tools build hospital-sim
# gerar (porte real, maio/2026)
docker compose --profile tools run --rm hospital-sim gerar --inicio 2026-05-01 --fim 2026-05-31 --semente 42 --saida data/lotes_v2/hrn_202605
# porte medio com as mesmas proporcoes (~140 leitos)
docker compose --profile tools run --rm hospital-sim gerar --inicio 2026-05-01 --fim 2026-05-31 --escala-porte 0.4 --saida data/lotes_v2/hrn_medio_202605
# verificar qualquer lote (v2 ou v1)
docker compose --profile tools run --rm hospital-sim verificar --lote data/synthetic_output/batch_fase_b_v1
# testes
docker compose --profile tools run --rm --entrypoint python hospital-sim -m pytest -q tests/test_hospital_sim.py
```

Código de saída: 0 = lote aprovado; 1 = reprovado. O relatório fica em
`<lote>/relatorio_invariantes.{md,json}`.

## De onde vem cada número

| Parâmetro | Fonte |
|---|---|
| Leitos por setor | CNES-LT 2026-05 (345 leitos SUS) |
| Quadro de pessoal, CBO e carga horária | CNES-PF 2026-05 (contagens agregadas) |
| Internações por mês, CID, idade e sexo, permanência, óbito, UTI, caráter, residência, valor | SIH-RD jun/2025–mai/2026 (15.187 AIH) |
| Volume do pronto-socorro | SIA-PA, subgrupo 030106 |
| Enfermagem mínima por turno | Resolução COFEN 543/2017 (horas por paciente) e RDC 7/2010 (UTI) |
| Controle especial | Portaria SVS/MS 344/1998 |
| Capacidade do PS, salas cirúrgicas, triagem, custos de referência, prazos de fornecedor | **Parâmetros** marcados no perfil (sem fonte pública) |

A calibração (`config/calibracao/hrn_6848710.json`) é gerada no QIMED por
`scripts/exportar_calibracao_hospital.py`. Ela contém apenas agregados, com células de
n < 5 suprimidas. Nomes, CPF (com dígitos verificadores inválidos de propósito), CNPJ de
fornecedores e registros de conselho são sintéticos.

## O que é simulado

- **Assistencial:** chegada ao PS e eletivas; fila de leitos por setor (espera e transferência por falta de leito); UTI no início ou no fim (óbito); alta da UTI retida sem vaga; centro cirúrgico com salas; prescrição diária pelo médico de plantão; exames com valores conforme o quadro; contas (AIH). Um aquecimento de 45 dias faz o período começar com o hospital ocupado.
- **Escala:** a planejada é otimizada por OR-Tools CP-SAT, com 1 worker e tempo determinístico para que a mesma semente gere a mesma escala. A realizada inclui faltas, atestados, trocas, horas extras e ponto. Os furos de cobertura são registrados.
- **Estoque:** livro-razão com inventário inicial documentado, pedido de compra, recebimento por NF com lote e validade, transferência para as farmácias satélites, dispensação FEFO, devolução, perdas, inventário cíclico e livro de controlados. Sem saldo, a dispensação não acontece e a ruptura é registrada.

## Invariantes

| Grupo | Regras |
|---|---|
| Estoque | E1 saldo nunca negativo · E2 lote cadastrado · E3 sem saída de vencido · E4 FEFO · E5 saldo final = movimentos · E6 recebimento ligado a pedido · E7 dispensação com prescrição/cirurgia · E8 dispensação durante a internação · E9 ruptura coerente |
| Escala | R1 sem sobreposição · R2 descanso ≥ 11 h e jornada contínua dentro do regime · R3 12×36 no planejado · R4 teto mensal · R5 habilitação/lotação · R6 furos = exigido − presentes · R7 prescrição e atendimento por médico de plantão · R8 déficit executado ≤ 10% por categoria |
| Clínico | C1 nada após óbito · C2 leito e paciente sem dupla ocupação · C3 CID × sexo × idade · C4 cronologia · C5 prescrição no setor onde o paciente está |
| Calibração | Q1 volume, mortalidade e permanência na faixa da referência (períodos ≥ 28 dias) |

O lote v1 (`batch_fase_b_v1`) é **reprovado** em E1–E7, R2, R5, R6, R8, C1 e C3. Esse era o critério de aceite da fase 1.

## Resultado de referência (maio/2026, porte real, semente 42)

Lote `data/lotes_v2/hrn_202605`: **aprovado em todas as invariantes**; geração em 11,6 min.

| Indicador | Gerado | Referência (SIH/CNES) |
|---|---|---|
| Mortalidade das saídas | 6,9% | 7,4% |
| Permanência média das saídas | 9,4 dias | 8,5 dias |
| Ocupação das enfermarias | 95–98% + leitos extras | — |
| Ocupação das UTIs | 65–75% | — |
| Admissões no mês | 938 | 1.266 AIH/mês |
| Déficit de cobertura executado | médicos 1,4% · enfermeiros 4,7% · técnicos 1,7% | — |
| Movimentos de estoque | 69.357 (54 recebimentos, 489 transferências, 1.431 devoluções) | — |
| Rupturas | 27 | — |

Em porte médio (`--escala-porte 0.4`, 139 leitos), o lote de maio/2026 também foi aprovado: mortalidade de 6,4%, permanência de 8,5 dias e déficit de cobertura de 1,4% (médicos), 3,9% (enfermeiros) e 4,5% (técnicos). Em porte reduzido, o quadro de enfermagem e de médicos acompanha os turnos exigidos, e não só os leitos, porque cada setor tem um mínimo por turno. Assim se mantém a razão pessoas por turno do hospital de referência.

O volume da referência não cabe nos 345 leitos com a permanência sorteada (a ocupação teórica passa de 100%). O gerador registra 301 transferências por falta de leito no mês. Ou a superlotação é real, ou as AIHs do SIH contam a mesma internação mais de uma vez. Isso precisa ser validado com a equipe que conhece o hospital.

## Limites conhecidos

- O catálogo tem 98 itens (74 medicamentos e 24 materiais); a meta da proposta é ~600.
- O PS gera atendimentos, mas ainda não gera consumo de estoque.
- O ambulatório e as agendas eletivas ainda não estão simulados.
- A carga no ERP (fase 3) ainda usa o loader v1; a carga do lote v2 pelo ORM é o próximo passo.
