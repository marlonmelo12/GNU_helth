"""
Loader do GNU Health: nunca faz fallback silencioso quando um modelo do ERP falha (testes com mocks).
"""
import json
import pytest
from datetime import datetime, date, timedelta
from unittest.mock import MagicMock, patch



def test_loader_no_silent_fallback_with_mock_models(tmp_path):
    """
    Invariante do Loader:
    Quando um registro faz referência a um paciente ou profissional inexistente,
    ou código de exame inválido, o loader NUNCA deve pegar o primeiro objeto [0]
    como fallback silencioso, e sim pular o registro e registrar em 'skipped'.
    """
    import src.generators.gnuhealth_erp_loader as erp_loader_mod
    from src.generators.gnuhealth_erp_loader import GnuHealthERPLoader

    batch_dir = tmp_path / "batch"
    batch_dir.mkdir()

    # Cria batch com 1 paciente e 1 médico válidos
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

    # Cria atendimentos: 1 válido, 1 com paciente inexistente, 1 com médico inexistente
    with open(batch_dir / "encounters.json", "w") as f:
        json.dump([
            {"patient_id": "PAT_001", "professional_id": "DOC_001", "appointment_date": "2026-01-01T10:00:00"},
            {"patient_id": "PAT_UNKNOWN", "professional_id": "DOC_001", "appointment_date": "2026-01-01T11:00:00"},
            {"patient_id": "PAT_001", "professional_id": "DOC_UNKNOWN", "appointment_date": "2026-01-01T12:00:00"},
        ], f)

    # Cria exames: 1 com exame desconhecido
    with open(batch_dir / "labs.json", "w") as f:
        json.dump([
            {"patient_id": "PAT_001", "requesting_doctor_id": "DOC_001", "test_category": "INVALID_CODE", "request_date": "2026-01-01T10:00:00"}
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
    mock_party_instance = MagicMock()
    mock_party.find.return_value = [mock_party_instance]

    mock_patient = MagicMock()
    mock_patient_inst = MagicMock()
    mock_patient.find.return_value = [mock_patient_inst]

    mock_hp = MagicMock()
    mock_hp_inst = MagicMock()
    mock_hp.find.return_value = [mock_hp_inst]

    mock_appt = MagicMock()
    mock_tt = MagicMock()
    mock_tt.find.return_value = []

    def model_get_side_effect(name):
        if name == "party.party": return mock_party
        if name == "gnuhealth.patient": return mock_patient
        if name == "gnuhealth.healthprofessional": return mock_hp
        if name == "gnuhealth.appointment": return mock_appt
        if name == "gnuhealth.lab.test.type": return mock_tt
        if name == "gnuhealth.lab": return MagicMock()
        if name == "gnuhealth.hospital.bed": return MagicMock()
        return MagicMock()

    mock_model.get.side_effect = model_get_side_effect

    report = loader.sync_batch(str(batch_dir))

    # Apenas 1 atendimento válido criado, 2 pulados por ausência de entidade
    assert report["counts"]["encounters"] == 1
    assert report["skipped"]["encounters"] == 2
    # O exame com código inválido foi pulado
    assert report["counts"]["labs"] == 0
    assert report["skipped"]["labs"] == 1
