# GNU Health HIS de prova + hospital simulado (QIMED)

ERP hospitalar usado como prova de integração do QIMED com sistemas de gestão hospitalar
(TOTVS, Tasy). Contém:

- **GNU Health HIS 5.0** (Tryton 7.0 LTS + PostgreSQL 16), com cliente web Tryton-Sao na porta 8001.
- **Gerador v2 do hospital simulado** (`src/hospital_sim`), calibrado por dados públicos agregados do Hospital Regional Norte (Sobral/CE). Cada lote passa por invariantes de estoque, escala e coerência clínica antes de ir para o ERP. Detalhes em `docs/07_gerador_v2_hospital_simulado.md`.
- **Loader do ERP** (`src/generators/gnuhealth_erp_loader.py`), que carrega lotes pelo ORM Proteus, sem SQL direto.

## Estrutura

```text
GNU_helth/
+-- docker-compose.yml          # ERP (Postgres + Trytond/Sao) e o servico hospital-sim (perfil tools)
+-- docker/                     # Dockerfiles do ERP e do gerador
+-- config/
|   +-- hospital_profiles/      # Perfil do hospital simulado (setores, leitos, regras)
|   +-- calibracao/             # Agregados de calibracao exportados do QIMED
|   +-- gnuhealth/trytond.conf
+-- src/
|   +-- hospital_sim/           # Gerador v2 + invariantes
|   +-- generators/gnuhealth_erp_loader.py
+-- scripts/                    # Carga do catalogo CID-10 e das escalas no ERP (Proteus)
+-- data/                       # Dumps do ERP, lote v1 de referencia e lotes v2 (gitignored)
+-- docs/
+-- tests/
```

## Uso

Passo a passo completo (subir o ERP, carregar a base, gerar e verificar lotes): **[docs/HOMOLOGACAO.md](docs/HOMOLOGACAO.md)**.

Resumo:

```bash
docker compose build gnuhealth-server
docker compose up -d gnuhealth-db
docker compose cp data/gnuhealth_backup_20261014.dump gnuhealth-db:/tmp/erp.dump
docker compose exec gnuhealth-db pg_restore -U gnuhealth -d gnuhealth --no-owner --exit-on-error /tmp/erp.dump
docker compose up -d gnuhealth-server          # http://localhost:8001/  (gnuhealth / admin / admin)

docker compose --profile tools run --rm hospital-sim gerar --inicio 2026-05-01 --fim 2026-05-31 --escala-porte 0.4 --saida data/lotes_v2/hrn_medio_202605
```

## Histórico

O gerador v1 e o script de reparo com SQL direto foram removidos. Ambos foram substituídos pelo gerador v2, porque o lote v1 é reprovado pelas invariantes. O lote v1 (`data/synthetic_output/batch_fase_b_v1`) fica como referência desse teste. Os documentos `docs/01` a `docs/06` registram a implantação original.
