import os
import pytest
from deltalake import DeltaTable

def test_fct_escala_plantao_has_no_id_na():
    """Valida que nenhum plantão em fct_escala_plantao possui identificador_profissional_hash == 'ID_NA'."""
    silver_path = os.path.abspath("lakehouse/silver/fct_escala_plantao")
    assert os.path.exists(silver_path), f"Caminho não encontrado: {silver_path}"
    
    dt = DeltaTable(silver_path)
    df = dt.to_pandas()
    assert not df.empty, "Tabela fct_escala_plantao está vazia!"
    
    id_na_count = (df["identificador_profissional_hash"] == "ID_NA").sum()
    assert id_na_count == 0, (
        f"Encontrados {id_na_count} plantões com identificador_profissional_hash == 'ID_NA'! "
        f"Distribuição por equipe: {df[df['identificador_profissional_hash'] == 'ID_NA']['tipo_equipe'].value_counts().to_dict()}"
    )

def test_fct_escala_plantao_covers_all_shifts():
    """Valida integridade total de 1800 plantões com equipe médica e de enfermagem sem nulos."""
    silver_path = os.path.abspath("lakehouse/silver/fct_escala_plantao")
    dt = DeltaTable(silver_path)
    df = dt.to_pandas()
    
    assert len(df) == 1800, f"Esperado 1800 plantões, obtido {len(df)}"
    assert set(df["tipo_equipe"].unique()) == {"MEDICO", "ENFERMAGEM"}
    assert df["identificador_profissional_hash"].isna().sum() == 0
