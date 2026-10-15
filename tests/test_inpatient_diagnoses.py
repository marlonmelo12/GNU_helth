import os
import json
import pytest
from unittest.mock import MagicMock
from collections import Counter

def test_loader_sets_discharge_dx_from_inpatient_dict(tmp_path):
    """
    Verifica que o GnuHealthERPLoader associa discharge_dx e admission_reason
    a partir do campo 'primary_diagnosis_cid10' do inpatients.json,
    sem rodízio e sem deixar nulo.
    """
    import src.generators.gnuhealth_erp_loader as erp_loader_mod
    from src.generators.gnuhealth_erp_loader import GnuHealthERPLoader

    batch_dir = tmp_path / "batch"
    batch_dir.mkdir()

    with open(batch_dir / "patients.json", "w") as f:
        json.dump([{"id": "PAT_001", "name": "Paciente 1"}], f)
    with open(batch_dir / "professionals.json", "w") as f:
        json.dump([], f)
    with open(batch_dir / "shifts.json", "w") as f:
        json.dump([], f)
    with open(batch_dir / "stock_items.json", "w") as f:
        json.dump([], f)
    with open(batch_dir / "stock_moves.json", "w") as f:
        json.dump([], f)
    with open(batch_dir / "encounters.json", "w") as f:
        json.dump([], f)
    with open(batch_dir / "labs.json", "w") as f:
        json.dump([], f)

    # 2 internações com CIDs específicos dos seus cenários
    with open(batch_dir / "inpatients.json", "w") as f:
        json.dump([
            {
                "id": "GH_INT_000001",
                "patient_id": "PAT_001",
                "hospitalization_date": "2026-03-01T08:00:00",
                "discharge_date": "2026-03-05T10:00:00",
                "primary_diagnosis_cid10": "J18",
                "discharge_reason": "ALTA_CURADO",
            },
            {
                "id": "GH_INT_000002",
                "patient_id": "PAT_001",
                "hospitalization_date": "2026-03-10T08:00:00",
                "discharge_date": "2026-03-15T10:00:00",
                "primary_diagnosis_cid10": "K35",
                "discharge_reason": "ALTA_CURADO",
            },
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

    mock_patient = MagicMock()
    mock_patient_inst = MagicMock()
    mock_patient.find.return_value = [mock_patient_inst]

    mock_bed = MagicMock()
    mock_bed_inst = MagicMock()
    mock_bed_inst.id = 1
    mock_bed.find.return_value = [mock_bed_inst]

    mock_inpatient_cls = MagicMock()
    created_inpatient_instances = []
    def inpatient_init_mock(**kwargs):
        inst = MagicMock()
        inst.kwargs = kwargs
        created_inpatient_instances.append(kwargs)
        return inst
    mock_inpatient_cls.side_effect = inpatient_init_mock

    mock_pathology = MagicMock()
    def pathology_find_mock(query):
        code = query[0][2]
        p = MagicMock()
        p.code = code
        return [p]
    mock_pathology.find.side_effect = pathology_find_mock

    def model_get_side_effect(name):
        if name == "party.party": return MagicMock()
        if name == "gnuhealth.patient": return mock_patient
        if name == "gnuhealth.healthprofessional": return MagicMock()
        if name == "gnuhealth.appointment": return MagicMock()
        if name == "gnuhealth.inpatient.registration": return mock_inpatient_cls
        if name == "gnuhealth.hospital.bed": return mock_bed
        if name == "gnuhealth.pathology": return mock_pathology
        return MagicMock()

    mock_model.get.side_effect = model_get_side_effect

    loader.sync_batch(str(batch_dir))

    assert len(created_inpatient_instances) == 2
    # Inpatient 1 deve ter recebido discharge_dx apontando para J18
    assert "discharge_dx" in created_inpatient_instances[0]
    assert created_inpatient_instances[0]["discharge_dx"].code == "J18"
    assert created_inpatient_instances[0]["admission_reason"].code == "J18"

    # Inpatient 2 deve ter recebido discharge_dx apontando para K35
    assert "discharge_dx" in created_inpatient_instances[1]
    assert created_inpatient_instances[1]["discharge_dx"].code == "K35"
    assert created_inpatient_instances[1]["admission_reason"].code == "K35"


def test_inpatient_dataset_diagnosis_distribution_and_scenarios():
    """
    Verifica que no lote sintético gerado a distribuição de primary_diagnosis_cid10
    NÃO é uniforme (não é round-robin 34/35) e que os CIDs correspondem estritamente
    aos seus respectivos cenários clínicos geradores.
    """
    batch_file = "data/synthetic_output/batch_fase_b_v1/inpatients.json"
    encounters_file = "data/synthetic_output/batch_fase_b_v1/encounters.json"
    if not os.path.exists(batch_file) or not os.path.exists(encounters_file):
        pytest.skip("Lote fase B não encontrado para teste de distribuição.")

    with open(batch_file, "r", encoding="utf-8") as f:
        inps = json.load(f)
    with open(encounters_file, "r", encoding="utf-8") as f:
        encs = {e["id"]: e for e in json.load(f)}

    cids = [inp["primary_diagnosis_cid10"] for inp in inps]
    counts = Counter(cids)

    # 1. Distribuição NÃO uniforme
    # Num rodízio uniforme de 5 CIDs sobre 500 internações, cada um teria exatamente 100.
    # No modelo clínico real: Apendicite (K35) tem ~274 e Gastroenterite (A09) tem ~34.
    assert len(set(counts.values())) > 1, "Distribuição de diagnósticos é artificialmente uniforme!"
    assert max(counts.values()) - min(counts.values()) > 50, "Variação clínica insuficiente!"

    # 2. Correspondência estrita cenário -> CID em 5 exemplos
    # Cada internação deve casar exatamente com o diagnóstico do encontro de origem
    for inp in inps[:5]:
        enc_id = inp.get("encounter_id")
        assert enc_id in encs
        enc = encs[enc_id]
        assert inp["primary_diagnosis_cid10"] == enc["diagnosis_cid10"]
