import os
import pytest
import pandas as pd
import pyarrow as pa
from unittest.mock import MagicMock, patch
from deltalake import write_deltalake, DeltaTable

from src.ingestion.adapters.gnuhealth_adapter import GnuHealthAdapter
from src.silver.mappers.gnuhealth_mapper import GnuHealthSemanticMapper


def test_adapter_has_extract_diagnoses():
    adapter = GnuHealthAdapter()
    assert hasattr(adapter, "extract_diagnoses")
    assert callable(getattr(adapter, "extract_diagnoses"))


def test_mapper_associates_cid_from_diagnoses_not_regex(tmp_path):
    """
    Testa que o mapper associa codigo_cid10_principal a partir da Bronze 'diagnoses'
    (patient_id + data) e que o regex sobre chief_complaint foi removido:
    - Atendimento com match em diagnoses -> recebe CID correto
    - Atendimento sem match em diagnoses (mesmo com CID no texto do complaint) -> recebe None
    """
    bronze_dir = tmp_path / "bronze" / "gnuhealth"
    appts_dir = str(bronze_dir / "appointments")
    diag_dir = str(bronze_dir / "diagnoses")
    os.makedirs(appts_dir, exist_ok=True)
    os.makedirs(diag_dir, exist_ok=True)

    # 1. Cria Bronze appointments:
    # appt 1: paciente 101, data 2026-03-01, complaint tem 'J18 Tosse...'
    # appt 2: paciente 102, data 2026-03-02, complaint tem 'J18 Tosse...' (mas NÃO está em diagnoses!)
    # appt 3: paciente 103, data 2026-03-03, complaint sem CID
    appts_df = pd.DataFrame([
        {
            "appointment_id": 1,
            "patient_id": 101,
            "healthprof_id": 1,
            "appointment_date": "2026-03-01T10:00:00",
            "chief_complaint": "J18 Tosse produtiva",
            "specialty_name": "Clínica Médica",
            "specialty_code": "CLI",
            "_ingested_at": "2026-03-01T10:05:00",
        },
        {
            "appointment_id": 2,
            "patient_id": 102,
            "healthprof_id": 2,
            "appointment_date": "2026-03-02T11:00:00",
            "chief_complaint": "J18 Tosse e febre",  # Complaint tem J18, mas não há diagnóstico oficial
            "specialty_name": "Cardiologia",
            "specialty_code": "CARD",
            "_ingested_at": "2026-03-02T11:05:00",
        },
        {
            "appointment_id": 3,
            "patient_id": 103,
            "healthprof_id": 3,
            "appointment_date": "2026-03-03T14:00:00",
            "chief_complaint": "Glicemia elevada",
            "specialty_name": "Endocrinologia",
            "specialty_code": "ENDO",
            "_ingested_at": "2026-03-03T14:05:00",
        },
    ])
    write_deltalake(appts_dir, pa.Table.from_pandas(appts_df))

    # 2. Cria Bronze diagnoses:
    # Paciente 101 em 2026-03-01 tem J18
    # Paciente 103 em 2026-03-03 tem E11
    diag_df = pd.DataFrame([
        {
            "disease_id": 1,
            "patient_id": 101,
            "pathology_code": "J18",
            "pathology_name": "Pneumonia",
            "diagnosed_date": "2026-03-01",
            "healthprof_id": 1,
            "_ingested_at": "2026-03-01T10:05:00",
        },
        {
            "disease_id": 2,
            "patient_id": 103,
            "pathology_code": "E11",
            "pathology_name": "Diabetes Mellitus Tipo 2",
            "diagnosed_date": "2026-03-03",
            "healthprof_id": 3,
            "_ingested_at": "2026-03-03T14:05:00",
        },
    ])
    write_deltalake(diag_dir, pa.Table.from_pandas(diag_df))

    silver_dir = tmp_path / "silver"
    mapper = GnuHealthSemanticMapper(silver_path=str(silver_dir))
    results = mapper.map_and_write_silver(bronze_base_dir=str(bronze_dir))

    assert "fct_atendimentos_ambulatoriais" in results
    silver_table_path = str(silver_dir / "fct_atendimentos_ambulatoriais")
    dt_silver = DeltaTable(silver_table_path)
    df_silver = dt_silver.to_pandas()

    row1 = df_silver[df_silver["id_atendimento_ambulatorial"] == "gh_amb_1"].iloc[0]
    row2 = df_silver[df_silver["id_atendimento_ambulatorial"] == "gh_amb_2"].iloc[0]
    row3 = df_silver[df_silver["id_atendimento_ambulatorial"] == "gh_amb_3"].iloc[0]

    # Atendimento 1 tem diagnóstico de origem -> J18
    assert row1["codigo_cid10_principal"] == "J18"

    # Atendimento 2 NÃO tem diagnóstico de origem -> DEVE ser None/NaN, provando ausência de regex
    assert pd.isna(row2["codigo_cid10_principal"]) or row2["codigo_cid10_principal"] is None

    # Atendimento 3 tem diagnóstico de origem -> E11
    assert row3["codigo_cid10_principal"] == "E11"

    # Verificações de contagem
    valid_cids = df_silver["codigo_cid10_principal"].dropna()
    assert len(valid_cids) == 2
    assert valid_cids.nunique() == 2


def test_loader_creates_patient_disease_via_proteus(tmp_path):
    """
    Verifica que o loader do GNU Health cria instâncias de gnuhealth.patient.disease
    via Proteus quando o encontro possui diagnosis_cid10.
    """
    import json
    import src.generators.gnuhealth_erp_loader as erp_loader_mod
    from src.generators.gnuhealth_erp_loader import GnuHealthERPLoader

    batch_dir = tmp_path / "batch"
    batch_dir.mkdir()

    with open(batch_dir / "patients.json", "w") as f:
        json.dump([{"id": "PAT_001", "name": "Paciente Valido", "external_ref": "REF_001"}], f)
    with open(batch_dir / "professionals.json", "w") as f:
        json.dump([{"id": "DOC_001", "name": "Dr. Valido", "role": "MEDICO"}], f)
    with open(batch_dir / "shifts.json", "w") as f:
        json.dump([], f)
    with open(batch_dir / "stock_items.json", "w") as f:
        json.dump([], f)
    with open(batch_dir / "stock_moves.json", "w") as f:
        json.dump([], f)
    with open(batch_dir / "inpatients.json", "w") as f:
        json.dump([], f)
    with open(batch_dir / "labs.json", "w") as f:
        json.dump([], f)

    # 1 encontro com diagnóstico J18
    with open(batch_dir / "encounters.json", "w") as f:
        json.dump([
            {
                "patient_id": "PAT_001",
                "professional_id": "DOC_001",
                "appointment_date": "2026-01-01T10:00:00",
                "diagnosis_cid10": "J18",
                "chief_complaint": "Tosse produtiva",
            }
        ], f)

    mock_model = MagicMock()
    erp_loader_mod.Model = mock_model

    loader = GnuHealthERPLoader(connection_url="http://mock:8000")
    loader.ensure_hospital_environment = MagicMock(return_value={
        "institution": MagicMock(),
        "company": MagicMock(),
        "currency": MagicMock(),
        "customer_loc": MagicMock(),
        "storage_base": MagicMock(),
        "storage_locs": {}
    })

    mock_party = MagicMock()
    mock_party.find.return_value = [MagicMock()]
    mock_patient = MagicMock()
    mock_patient.find.return_value = [MagicMock()]
    mock_hp = MagicMock()
    mock_hp.find.return_value = [MagicMock()]
    mock_appt = MagicMock()
    mock_pathology = MagicMock()
    mock_pathology_inst = MagicMock()
    mock_pathology.find.return_value = [mock_pathology_inst]
    mock_disease = MagicMock()

    def model_get_side_effect(name):
        if name == "party.party": return mock_party
        if name == "gnuhealth.patient": return mock_patient
        if name == "gnuhealth.healthprofessional": return mock_hp
        if name == "gnuhealth.appointment": return mock_appt
        if name == "gnuhealth.pathology": return mock_pathology
        if name == "gnuhealth.patient.disease": return mock_disease
        return MagicMock()

    mock_model.get.side_effect = model_get_side_effect

    report = loader.sync_batch(str(batch_dir))
    assert report["counts"]["encounters"] == 1
    # Verifica que PatientDisease.save foi chamado
    assert mock_disease.save.called
    saved_diseases = mock_disease.save.call_args[0][0]
    assert len(saved_diseases) == 1
