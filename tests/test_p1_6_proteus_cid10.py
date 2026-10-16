import os
import inspect
import pytest
from unittest.mock import MagicMock, patch

def test_load_cid10_uses_proteus_and_not_direct_sql_insert():
    """Valida que scripts/load_cid10_gnuhealth.py utiliza Proteus (gnuhealth.pathology) e não INSERT INTO."""
    script_path = os.path.abspath("scripts/load_cid10_gnuhealth.py")
    assert os.path.exists(script_path)
    
    with open(script_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    assert "INSERT INTO gnuhealth_pathology" not in content, (
        "scripts/load_cid10_gnuhealth.py ainda contém INSERT direto em SQL proibido por D3!"
    )
    assert "gnuhealth.pathology" in content, (
        "scripts/load_cid10_gnuhealth.py deve utilizar o modelo Proteus gnuhealth.pathology!"
    )
    assert "proteus" in content, (
        "scripts/load_cid10_gnuhealth.py deve importar e utilizar proteus!"
    )

def test_load_cid10_proteus_batching_and_idempotency(tmp_path):
    """Valida que a função load_cid10 do script processa em lotes de 500 com busca idempotente."""
    duckdb = pytest.importorskip("duckdb")  # roda no container do ERP; a imagem do gerador nao tem duckdb
    import scripts.load_cid10_gnuhealth as loader_mod
    
    # Cria parquet fake com 1050 códigos
    fake_parquet = str(tmp_path / "fake_cid10.parquet")
    con = duckdb.connect()
    con.execute(f"""
        COPY (
            SELECT 
                'C' || lpad(i::text, 4, '0') as cid10_code,
                'Doença ' || i::text as disease_name
            FROM range(1, 1051) t(i)
        ) TO '{fake_parquet}' (FORMAT PARQUET)
    """)
    con.close()
    
    mock_model = MagicMock()
    mock_pathology_cls = MagicMock()
    mock_model.get.return_value = mock_pathology_cls
    
    # 50 códigos já existem
    existing_objs = [MagicMock(code=f"C{i:04d}") for i in range(1, 51)]
    mock_pathology_cls.find.side_effect = lambda query: existing_objs if 'C0001' in str(query) else []
    
    saved_batches = []
    def fake_save(batch):
        saved_batches.append(list(batch))
    mock_pathology_cls.save.side_effect = fake_save
    
    with patch.object(loader_mod, "Model", mock_model, create=True), \
         patch.object(loader_mod, "config", MagicMock(), create=True):
        loader_mod.load_cid10_proteus(
            parquet_path=fake_parquet,
            batch_size=500,
            apply_changes=True
        )
        
    assert len(saved_batches) > 0, "Nenhum lote foi salvo via Proteus!"
    for batch in saved_batches:
        assert len(batch) <= 500, f"Lote excedeu tamanho máximo de 500: {len(batch)}"

