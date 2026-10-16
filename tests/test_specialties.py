import json
import pytest
from unittest.mock import MagicMock


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
