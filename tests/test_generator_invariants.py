"""
Testes Unitários de Invariantes do Gerador Sintético e Loader do GNU Health.
Valida regras clínicas e operacionais sem dependência do banco do ERP (testes puros).
"""
import os
import json
import pytest
from datetime import datetime, date, timedelta
from unittest.mock import MagicMock, patch

from src.generators.gnuhealth_synthetic_generator import (
    GnuHealthSyntheticGenerator,
    GeneratorConfig,
)


def test_generator_shift_ids_contiguous_no_gaps(tmp_path):
    """
    Invariante: Os IDs de escala gerados devem ser estritamente sequenciais e contínuos.
    A presença do bug shift_id_seq += 1 duplicado fazia pular sequências.
    """
    output_dir = str(tmp_path / "output")
    config = GeneratorConfig(
        seed=42,
        patients=20,
        professionals=30,
        nursing_staff=30,
        encounters=20,
        inpatients=5,
        labs=10,
        start_date="2026-01-01",
        end_date="2026-01-03",
        batch_id="test_seq_batch",
        output_dir=output_dir,
    )
    gen = GnuHealthSyntheticGenerator()
    res = gen.run(config)
    assert res.status == "SUCCESS"

    shifts_file = os.path.join(output_dir, config.batch_id, "shifts.json")
    with open(shifts_file, "r", encoding="utf-8") as f:
        shifts = json.load(f)

    assert len(shifts) > 0
    expected_ids = [f"ESC_{i:06d}" for i in range(1, len(shifts) + 1)]
    actual_ids = [s["id"] for s in shifts]
    assert actual_ids == expected_ids, "Os IDs de plantão possuem saltos/gaps na numeração!"


def test_choose_with_rest_raises_when_no_rested_professional_available(tmp_path):
    """
    Invariante: choose_with_rest NUNCA deve fazer fallback silencioso.
    Se nenhum profissional tiver >= 12h de descanso, deve lançar ValueError.
    """
    output_dir = str(tmp_path / "output")
    # Configura cenário com profissionais insuficientes para a escala (1 médico para 5 alas dia e noite)
    config = GeneratorConfig(
        seed=42,
        patients=5,
        professionals=1,
        nursing_staff=1,
        encounters=2,
        inpatients=1,
        labs=2,
        start_date="2026-01-01",
        end_date="2026-01-02",
        batch_id="test_fail_rest_batch",
        output_dir=output_dir,
    )
    gen = GnuHealthSyntheticGenerator()

    with pytest.raises(ValueError, match="sem profissional com descanso >= 12h"):
        gen.run(config)


def test_bed_allocation_raises_when_no_bed_available(tmp_path):
    """
    Invariante: Se todos os leitos estiverem ocupados no intervalo, o gerador
    deve lançar ValueError em vez de alocar silenciosamente com modulo % beds_count.
    """
    output_dir = str(tmp_path / "output")
    # 150 internações em apenas 2 dias com 60 leitos disponíveis deve estourar a capacidade
    config = GeneratorConfig(
        seed=42,
        patients=200,
        professionals=50,
        nursing_staff=50,
        encounters=400,
        inpatients=150,
        labs=10,
        start_date="2026-01-01",
        end_date="2026-01-02",
        batch_id="test_fail_bed_batch",
        output_dir=output_dir,
    )
    gen = GnuHealthSyntheticGenerator()

    with pytest.raises(ValueError, match="sem leito livre no intervalo"):
        gen.run(config)


def test_generator_invariants_on_standard_batch(tmp_path):
    """
    Validação de invariantes em um lote sintético completo válido:
    1. Sem sobreposição de leito
    2. Todo profissional com descanso >= 12h entre plantões
    3. Todo estoque com quantity_available >= 0
    4. Escala cobre todos os dias do período
    """
    output_dir = str(tmp_path / "output")
    config = GeneratorConfig(
        seed=42,
        patients=50,
        professionals=40,
        nursing_staff=40,
        encounters=80,
        inpatients=15,
        labs=50,
        stock_items=20,
        start_date="2026-01-01",
        end_date="2026-01-07",
        batch_id="test_invariants_batch",
        output_dir=output_dir,
    )
    gen = GnuHealthSyntheticGenerator()
    res = gen.run(config)
    assert res.status == "SUCCESS"

    batch_dir = os.path.join(output_dir, config.batch_id)

    # 1. Sem sobreposição de leito
    with open(os.path.join(batch_dir, "inpatients.json"), "r", encoding="utf-8") as f:
        inps = json.load(f)
    bed_intervals = {}
    for inp in inps:
        bed = inp["bed"]
        adm = datetime.fromisoformat(inp["hospitalization_date"])
        disch = datetime.fromisoformat(inp["discharge_date"])
        if bed not in bed_intervals:
            bed_intervals[bed] = []
        for prev_adm, prev_disch in bed_intervals[bed]:
            assert not (adm < prev_disch and disch > prev_adm), f"Sobreposição detectada no leito {bed}!"
        bed_intervals[bed].append((adm, disch))

    # 2. Todo profissional com descanso >= 12h entre plantões
    with open(os.path.join(batch_dir, "shifts.json"), "r", encoding="utf-8") as f:
        shifts = json.load(f)
    prof_shifts = {}
    for s in shifts:
        pid = s["professional_id"]
        st = datetime.fromisoformat(s["start_time"])
        et = datetime.fromisoformat(s["end_time"])
        if pid not in prof_shifts:
            prof_shifts[pid] = []
        prof_shifts[pid].append((st, et))

    for pid, s_list in prof_shifts.items():
        s_list.sort(key=lambda x: x[0])
        for i in range(len(s_list) - 1):
            curr_end = s_list[i][1]
            next_start = s_list[i + 1][0]
            rest_hours = (next_start - curr_end).total_seconds() / 3600.0
            assert rest_hours >= 11.99, f"Profissional {pid} com descanso insuficiente: {rest_hours}h!"

    # 3. Todo estoque com quantity_available >= 0
    with open(os.path.join(batch_dir, "stock_items.json"), "r", encoding="utf-8") as f:
        stock_items = json.load(f)
    for item in stock_items:
        assert item["quantity_available"] >= 0, f"Item {item['name']} com estoque negativo: {item['quantity_available']}"

    # 4. Escala cobre todos os dias do período
    start_d = date(2026, 1, 1)
    end_d = date(2026, 1, 7)
    expected_dates = {start_d + timedelta(days=i) for i in range((end_d - start_d).days + 1)}
    covered_dates = {date.fromisoformat(s["date"]) for s in shifts}
    assert expected_dates.issubset(covered_dates), "Nem todos os dias do período foram cobertos pela escala!"


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
