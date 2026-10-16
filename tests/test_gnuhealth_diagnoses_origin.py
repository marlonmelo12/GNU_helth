import pytest
from unittest.mock import MagicMock, patch


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
