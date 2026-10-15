import os
import json
import pytest
import pandas as pd
import pyarrow as pa
from unittest.mock import MagicMock
from deltalake import write_deltalake, DeltaTable

from src.silver.mappers.gnuhealth_mapper import GnuHealthSemanticMapper


def test_mapper_specialty_no_fallback_to_clinica_medica(tmp_path):
    """
    Testa que o mapper não utiliza o fallback literal 'Clínica Médica' quando
    a especialidade for ausente (deve ser None), e preserva as especialidades reais
    quando presentes, garantindo diversidade > 1.
    """
    bronze_dir = tmp_path / "bronze" / "gnuhealth"
    appts_dir = str(bronze_dir / "appointments")
    os.makedirs(appts_dir, exist_ok=True)

    appts_df = pd.DataFrame([
        {
            "appointment_id": 1,
            "patient_id": 101,
            "healthprof_id": 1,
            "appointment_date": "2026-03-01T10:00:00",
            "chief_complaint": "Febre",
            "specialty_name": "Pediatria",
            "specialty_code": "PED",
            "_ingested_at": "2026-03-01T10:05:00",
        },
        {
            "appointment_id": 2,
            "patient_id": 102,
            "healthprof_id": 2,
            "appointment_date": "2026-03-02T11:00:00",
            "chief_complaint": "Dor precordial",
            "specialty_name": "Cardiologia",
            "specialty_code": "CARD",
            "_ingested_at": "2026-03-02T11:05:00",
        },
        {
            "appointment_id": 3,
            "patient_id": 103,
            "healthprof_id": 3,
            "appointment_date": "2026-03-03T14:00:00",
            "chief_complaint": "Consulta geral",
            "specialty_name": None,  # Sem especialidade
            "specialty_code": None,
            "_ingested_at": "2026-03-03T14:05:00",
        },
    ])
    write_deltalake(appts_dir, pa.Table.from_pandas(appts_df))

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

    assert row1["codigo_especialidade"] == "Pediatria"
    assert row2["codigo_especialidade"] == "Cardiologia"

    # Row 3 não pode ter recebido 'Clínica Médica' como fallback silencioso; deve ser None/NaN
    assert pd.isna(row3["codigo_especialidade"]) or row3["codigo_especialidade"] is None

    # Diversidade de especialidades > 1
    valid_specs = df_silver["codigo_especialidade"].dropna()
    assert valid_specs.nunique() > 1


def test_loader_saves_hp_specialty_with_mainsp_true(tmp_path):
    """
    Verifica que o GnuHealthERPLoader instancia e salva gnuhealth.hp_specialty
    com mainsp=True para cada profissional de saúde.
    """
    import src.generators.gnuhealth_erp_loader as erp_loader_mod
    from src.generators.gnuhealth_erp_loader import GnuHealthERPLoader

    batch_dir = tmp_path / "batch"
    batch_dir.mkdir()

    with open(batch_dir / "patients.json", "w") as f:
        json.dump([], f)
    with open(batch_dir / "shifts.json", "w") as f:
        json.dump([], f)
    with open(batch_dir / "stock_items.json", "w") as f:
        json.dump([], f)
    with open(batch_dir / "stock_moves.json", "w") as f:
        json.dump([], f)
    with open(batch_dir / "encounters.json", "w") as f:
        json.dump([], f)
    with open(batch_dir / "inpatients.json", "w") as f:
        json.dump([], f)
    with open(batch_dir / "labs.json", "w") as f:
        json.dump([], f)

    # 1 profissional com especialidade Cardiologia
    with open(batch_dir / "professionals.json", "w") as f:
        json.dump([
            {
                "id": "DOC_001",
                "name": "Dr. Carlos Silva",
                "role": "MEDICO",
                "specialty_code": "CARD",
                "specialty_name": "Cardiologia",
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
    mock_party.find.return_value = []
    mock_hp = MagicMock()
    mock_hp.find.return_value = []
    mock_specialty = MagicMock()
    mock_specialty_inst = MagicMock()
    mock_specialty.find.return_value = [mock_specialty_inst]

    mock_hp_spec = MagicMock()
    created_hp_specs = []
    def hp_spec_init_mock(**kwargs):
        inst = MagicMock()
        inst.kwargs = kwargs
        created_hp_specs.append(kwargs)
        return inst
    mock_hp_spec.side_effect = hp_spec_init_mock
    mock_hp_spec.find.return_value = []

    def model_get_side_effect(name):
        if name == "party.party": return mock_party
        if name == "gnuhealth.healthprofessional": return mock_hp
        if name == "gnuhealth.specialty": return mock_specialty
        if name == "gnuhealth.hp_specialty": return mock_hp_spec
        return MagicMock()

    mock_model.get.side_effect = model_get_side_effect

    loader.sync_batch(str(batch_dir))

    # Deve ter criado um registro em gnuhealth.hp_specialty com mainsp=True
    assert len(created_hp_specs) == 1
    assert created_hp_specs[0].get("mainsp") is True
    assert created_hp_specs[0].get("specialty") == mock_specialty_inst
