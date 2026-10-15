"""
Suite de Testes Automatizados de Integração GNU Health HIS -> QIMED Lakehouse.
Implementa os 12 testes obrigatórios da Seção 17 da Especificação Técnica:
1. Validação da Configuração
2. Geração Determinística
3. Integridade Relacional
4. Coerência Temporal
5. Persistência pelo GNU Health
6. Estoque e Farmácia
7. Escalas de Plantão
8. Idempotência
9. Geração Incremental
10. Proveniência e Privacidade LGPD
11. Integração de Ponta a Ponta (Bronze -> Silver -> DuckDB)
12. Recuperação e Resiliência
"""
import os
import json
import pytest
import asyncio
from datetime import datetime, date
import duckdb

from src.generators.gnuhealth_synthetic_generator import (
    GnuHealthSyntheticGenerator,
    GeneratorConfig,
)
from src.ingestion.adapters.gnuhealth_adapter import GnuHealthAdapter
from src.silver.mappers.gnuhealth_mapper import GnuHealthSemanticMapper


@pytest.fixture(scope="module")
def generator():
    return GnuHealthSyntheticGenerator()


@pytest.fixture(scope="module")
def generated_dataset(tmp_path_factory, generator):
    temp_dir = str(tmp_path_factory.mktemp("test_dataset"))
    cfg = GeneratorConfig(
        seed=42,
        patients=20,
        professionals=10,
        encounters=40,
        inpatients=10,
        labs=30,
        stock_items=10,
        start_date="2026-01-01",
        end_date="2026-06-01",
        batch_id="test_batch_seed42",
        output_dir=temp_dir,
    )
    generator.run(cfg)
    batch_dir = os.path.join(temp_dir, cfg.batch_id)
    return {
        "cfg": cfg,
        "batch_dir": batch_dir,
        "patients": json.load(open(os.path.join(batch_dir, "patients.json"), encoding="utf-8")),
        "professionals": json.load(open(os.path.join(batch_dir, "professionals.json"), encoding="utf-8")),
        "encounters": json.load(open(os.path.join(batch_dir, "encounters.json"), encoding="utf-8")),
        "inpatients": json.load(open(os.path.join(batch_dir, "inpatients.json"), encoding="utf-8")),
        "labs": json.load(open(os.path.join(batch_dir, "labs.json"), encoding="utf-8")),
        "stock_items": json.load(open(os.path.join(batch_dir, "stock_items.json"), encoding="utf-8")),
        "stock_moves": json.load(open(os.path.join(batch_dir, "stock_moves.json"), encoding="utf-8")),
        "shifts": json.load(open(os.path.join(batch_dir, "shifts.json"), encoding="utf-8")),
    }


# Teste 1 — Validação da Configuração
def test_01_config_validation(generator):
    with pytest.raises(ValueError):
        generator.validate_config(GeneratorConfig(patients=-10))

    with pytest.raises(ValueError):
        generator.validate_config(
            GeneratorConfig(start_date="2026-10-01", end_date="2026-01-01")
        )

    with pytest.raises(ValueError):
        generator.validate_config(GeneratorConfig(batch_id="invalid id with spaces"))


# Teste 2 — Geração Determinística
def test_02_deterministic_generation(tmp_path, generator):
    dir1 = str(tmp_path / "run1")
    dir2 = str(tmp_path / "run2")
    cfg1 = GeneratorConfig(seed=123, patients=15, encounters=20, output_dir=dir1, batch_id="b1")
    cfg2 = GeneratorConfig(seed=123, patients=15, encounters=20, output_dir=dir2, batch_id="b2")

    generator.run(cfg1)
    generator.run(cfg2)

    p1 = json.load(open(os.path.join(dir1, "b1", "patients.json"), encoding="utf-8"))
    p2 = json.load(open(os.path.join(dir2, "b2", "patients.json"), encoding="utf-8"))

    assert [p["name"] for p in p1] == [p["name"] for p in p2]
    assert [p["cpf"] for p in p1] == [p["cpf"] for p in p2]


# Teste 3 — Integridade Relacional
def test_03_relational_integrity(generated_dataset):
    pat_ids = {p["id"] for p in generated_dataset["patients"]}
    prof_ids = {p["id"] for p in generated_dataset["professionals"]}

    for enc in generated_dataset["encounters"]:
        assert enc["patient_id"] in pat_ids, f"Encounter orphan patient {enc['patient_id']}"
        assert enc["professional_id"] in prof_ids, f"Encounter orphan professional {enc['professional_id']}"

    for inp in generated_dataset["inpatients"]:
        assert inp["patient_id"] in pat_ids, f"Inpatient orphan patient {inp['patient_id']}"

    for lab in generated_dataset["labs"]:
        assert lab["patient_id"] in pat_ids, f"Lab orphan patient {lab['patient_id']}"


# Teste 4 — Coerência Temporal
def test_04_temporal_coherence(generated_dataset):
    pats_map = {p["id"]: p for p in generated_dataset["patients"]}

    for inp in generated_dataset["inpatients"]:
        pat = pats_map[inp["patient_id"]]
        birth_d = date.fromisoformat(pat["birth_date"])
        adm_d = datetime.fromisoformat(inp["hospitalization_date"]).date()
        dis_d = datetime.fromisoformat(inp["discharge_date"]).date()

        assert birth_d <= adm_d, "Nascimento deve preceder internação"
        assert adm_d <= dis_d, "Data de admissão deve ser menor ou igual à alta"
        assert inp["length_of_stay_days"] >= 0


# Teste 5 — Persistência pelo GNU Health
def test_05_gnuhealth_erp_persistence():
    adapter = GnuHealthAdapter()
    ok = asyncio.run(adapter.test_connection())
    assert ok, "Conexão com PostgreSQL do GNU Health falhou"

    schema = asyncio.run(adapter.discover_schema())
    assert "gnuhealth_patient" in schema
    assert "gnuhealth_appointment" in schema
    assert "gnuhealth_inpatient_registration" in schema


# Teste 6 — Estoque e Farmácia
def test_06_stock_and_pharmacy(generated_dataset):
    stock_items = generated_dataset["stock_items"]
    stock_moves = generated_dataset["stock_moves"]

    assert len(stock_items) > 0
    assert len(stock_moves) > 0

    valid_locations = {"Almoxarifado Central", "Farmácia Central", "Farmácia Satélite UTI"}
    for st in stock_items:
        assert st["quantity_available"] >= 0
        assert st["location"] in valid_locations

    for sm in stock_moves:
        assert sm["quantity"] > 0
        assert sm["origin_location"] in valid_locations


# Teste 7 — Escalas de Plantão
def test_07_staff_duty_rosters(generated_dataset):
    shifts = generated_dataset["shifts"]
    assert len(shifts) > 0

    for s in shifts:
        t_start = datetime.fromisoformat(s["start_time"])
        t_end = datetime.fromisoformat(s["end_time"])
        valid_wards = {
            "Enfermaria Clínica", "Enfermaria Cirúrgica", "UTI Adulto",
            "Pronto Atendimento", "Ambulatório de Especialidades",
            "Clínica Médica", "Cirurgia Geral", "Cardiologia", "Pediatria", "UTI", "Pronto Socorro"
        }
        assert s["ward"] in valid_wards

    team_types = {s.get("team_type") for s in shifts}
    assert "ENFERMAGEM" in team_types, "Escalas de plantão de enfermagem devem estar presentes"
    assert "MEDICA" in team_types, "Escalas de plantão médico devem estar presentes"


# Teste 8 — Idempotência
def test_08_idempotency():
    mapper = GnuHealthSemanticMapper(silver_path="lakehouse/silver")
    res1 = mapper.map_and_write_silver()
    res2 = mapper.map_and_write_silver()

    assert res1["dim_paciente"]["rows_written"] == res2["dim_paciente"]["rows_written"]
    assert res1["fct_internacao"]["rows_written"] == res2["fct_internacao"]["rows_written"]


# Teste 9 — Geração Incremental
def test_09_incremental_generation(tmp_path, generator):
    dir_p1 = str(tmp_path / "period1")
    dir_p2 = str(tmp_path / "period2")

    cfg1 = GeneratorConfig(seed=42, encounters=30, start_date="2026-01-01", end_date="2026-03-01", output_dir=dir_p1, batch_id="p1")
    cfg2 = GeneratorConfig(seed=42, encounters=30, start_date="2026-03-02", end_date="2026-06-01", output_dir=dir_p2, batch_id="p2")

    generator.run(cfg1)
    generator.run(cfg2)

    enc1 = json.load(open(os.path.join(dir_p1, "p1", "encounters.json"), encoding="utf-8"))
    enc2 = json.load(open(os.path.join(dir_p2, "p2", "encounters.json"), encoding="utf-8"))

    d1_dates = [datetime.fromisoformat(e["appointment_date"]) for e in enc1]
    d2_dates = [datetime.fromisoformat(e["appointment_date"]) for e in enc2]

    assert max(d1_dates) < min(d2_dates), "Janelas temporais incrementais devem ser estritamente sequenciais"


# Teste 10 — Proveniência e Privacidade LGPD
def test_10_provenance_and_lgpd_privacy(generated_dataset):
    adapter = GnuHealthAdapter()
    arrow_pats = asyncio.run(adapter.extract_patients())
    df_pats = arrow_pats.to_pandas()

    assert not df_pats.empty
    for val in df_pats["patient_name"].dropna():
        # Hash SHA-256 possui exatamente 64 caracteres hexadecimais
        assert len(str(val)) == 64, f"Nome deve estar pseudoanonimizado com SHA-256 (64 hex): {val}"


# Teste 11 — Integração de Ponta a Ponta (Bronze -> Silver -> DuckDB)
def test_11_end_to_end_lakehouse_pipeline():
    con = duckdb.connect()

    pats_count = con.execute("SELECT COUNT(1) FROM delta_scan('lakehouse/silver/dim_paciente')").fetchone()[0]
    org_count = con.execute("SELECT COUNT(1) FROM delta_scan('lakehouse/silver/dim_estabelecimento')").fetchone()[0]
    appts_count = con.execute("SELECT COUNT(1) FROM delta_scan('lakehouse/silver/fct_atendimentos_ambulatoriais')").fetchone()[0]
    inps_count = con.execute("SELECT COUNT(1) FROM delta_scan('lakehouse/silver/fct_internacao')").fetchone()[0]
    labs_count = con.execute("SELECT COUNT(1) FROM delta_scan('lakehouse/silver/fct_exame_laboratorial')").fetchone()[0]
    med_count = con.execute("SELECT COUNT(1) FROM delta_scan('lakehouse/silver/dim_medicamento_estoque')").fetchone()[0]
    shifts_count = con.execute("SELECT COUNT(1) FROM delta_scan('lakehouse/silver/fct_escala_plantao')").fetchone()[0]

    assert pats_count > 0, "dim_paciente deve conter registros"
    assert org_count == 1, "dim_estabelecimento deve conter exatamente 1 hospital"
    assert appts_count > 0, "fct_atendimentos_ambulatoriais deve conter registros"
    assert inps_count > 0, "fct_internacao deve conter registros"
    assert labs_count > 0, "fct_exame_laboratorial deve conter registros"
    assert med_count > 0, "dim_medicamento_estoque deve conter registros"
    assert shifts_count > 0, "fct_escala_plantao deve conter registros"

    # Auditoria de Integridade Referencial Star Schema (Zero Órfãos)
    orphans_inps = con.execute("""
        SELECT COUNT(1) 
        FROM delta_scan('lakehouse/silver/fct_internacao') i
        LEFT JOIN delta_scan('lakehouse/silver/dim_paciente') p
          ON i.pseudonimo_paciente = p.pseudonimo_paciente
        WHERE p.pseudonimo_paciente IS NULL
    """).fetchone()[0]
    assert orphans_inps == 0, f"Integridade violada: {orphans_inps} internações sem paciente correspondente."

    orphans_amb = con.execute("""
        SELECT COUNT(1) 
        FROM delta_scan('lakehouse/silver/fct_atendimentos_ambulatoriais') a
        LEFT JOIN delta_scan('lakehouse/silver/dim_paciente') p
          ON a.pseudonimo_paciente = p.pseudonimo_paciente
        WHERE p.pseudonimo_paciente IS NULL
    """).fetchone()[0]
    assert orphans_amb == 0, f"Integridade violada: {orphans_amb} consultas sem paciente correspondente."

    orphans_labs = con.execute("""
        SELECT COUNT(1) 
        FROM delta_scan('lakehouse/silver/fct_exame_laboratorial') l
        LEFT JOIN delta_scan('lakehouse/silver/dim_paciente') p
          ON l.pseudonimo_paciente = p.pseudonimo_paciente
        WHERE p.pseudonimo_paciente IS NULL
    """).fetchone()[0]
    assert orphans_labs == 0, f"Integridade violada: {orphans_labs} exames sem paciente correspondente."

    orphans_stock = con.execute("""
        SELECT COUNT(1) 
        FROM delta_scan('lakehouse/silver/fct_movimentacao_estoque') m
        LEFT JOIN delta_scan('lakehouse/silver/dim_medicamento_estoque') d
          ON m.id_medicamento = d.id_medicamento
        WHERE d.id_medicamento IS NULL
    """).fetchone()[0]
    assert orphans_stock == 0, f"Integridade violada: {orphans_stock} movimentações sem medicamento correspondente."


# Teste 12 — Recuperação e Resiliência
def test_12_recovery_and_resilience():
    adapter = GnuHealthAdapter()
    schema = asyncio.run(adapter.discover_schema())
    assert len(schema) >= 5, "Esquemas essenciais devem ser descobertos"

    mapper = GnuHealthSemanticMapper(silver_path="lakehouse/silver")
    results = mapper.map_and_write_silver()
    assert all(r["status"] == "success" for r in results.values()), "Recuperação do pipeline Silver deve ser 100% exitosa"
